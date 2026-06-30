#!/usr/bin/env python3
"""
Phase 2: Index aggregated parquet output into Elasticsearch.

Reads the fixed schema produced by spark_aggregate.py:
  sha256        string   -- pre-computed SHA256, used as ES _id
  text          string
  language      string   -- top-level for fast keyword filtering
  date          string   -- earliest crawl date across all sources
  source_count  integer
  sources       array of {dataset, id, language, date, url, language_score, folder_path}

No deduplication is performed here — that was fully handled in Phase 1.
Each row becomes exactly one ES document.

language and date are arrays at the top level (unique values across all sources),
enabling fast ES keyword/date range filtering. All other per-source detail lives
in sources[] which is stored but not indexed.

Usage
-----
python3 index_aggregated.py \\
    --data-dir  /iopsstor/scratch/.../fineweb-1_3_0-quality_33-filterrobots-aggregated \\
    --index-name fineweb-1_3_0-quality_33-filterrobots-eng \\
    --es-host localhost --es-port 9200
"""

import argparse
import logging
import multiprocessing
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import pyarrow.parquet as pq
from elasticsearch import Elasticsearch
from elasticsearch import helpers


# ============================================================
# Scripted update for duplicate-document merging (pass 2)
# ============================================================

_UPDATE_SCRIPT = (
    "if(ctx._source.sources==null){ctx._source.sources=new ArrayList();}"
    "for(def ns:params.new_sources){"
    "  boolean dup=false;"
    "  for(def es:ctx._source.sources){"
    "    if(es.dataset==ns.dataset&&es.id==ns.id){dup=true;break;}"
    "  }"
    "  if(!dup){ctx._source.sources.add(ns);ctx._source.source_count+=1;}"
    "}"
    "if(ctx._source.language==null){ctx._source.language=new ArrayList();}"
    "for(def l:params.new_langs){if(!ctx._source.language.contains(l)){ctx._source.language.add(l);}}"
    "if(ctx._source.date==null){ctx._source.date=new ArrayList();}"
    "for(def d:params.new_dates){if(!ctx._source.date.contains(d)){ctx._source.date.add(d);}}"
    "if(ctx._source.datasets==null){ctx._source.datasets=new ArrayList();}"
    "for(def ds:params.new_datasets){if(!ctx._source.datasets.contains(ds)){ctx._source.datasets.add(ds);}}"
)


def _update_action(sha256: str, index_name: str,
                   new_sources: list, new_langs: list,
                   new_dates: list, new_datasets: list) -> dict:
    return {
        "_op_type":          "update",
        "_index":            index_name,
        "_id":               sha256,
        "retry_on_conflict": 5,
        "script": {
            "source": _UPDATE_SCRIPT,
            "lang":   "painless",
            "params": {
                "new_sources":  new_sources,
                "new_langs":    [l for l in new_langs if l],
                "new_dates":    [d for d in new_dates if d],
                "new_datasets": new_datasets,
            },
        },
    }


def _iter_retry_create(files: List[Path], index_name: str,
                       rejected: set, chunk_size: int, op_type: str = "create",
                       dataset_name: Optional[str] = None,
                       max_rows: Optional[int] = None):
    """Re-read parquet files; yield create actions for 429-rejected SHA256s."""
    logger = logging.getLogger(__name__)
    rows_seen = 0
    for fp in files:
        if max_rows is not None and rows_seen >= max_rows:
            break
        try:
            pf = pq.ParquetFile(str(fp))
            schema_names = pf.schema_arrow.names
            has_date = "date" in schema_names
            for batch in pf.iter_batches(batch_size=chunk_size):
                if max_rows is not None and rows_seen >= max_rows:
                    break
                rows = batch.to_pydict()
                n = len(rows["sha256"])
                for i in range(n):
                    if max_rows is not None and rows_seen >= max_rows:
                        break
                    rows_seen += 1
                    sha256 = rows["sha256"][i]
                    if sha256 is None or sha256 not in rejected:
                        continue
                    sources_raw = rows["sources"][i]
                    if sources_raw is not None:
                        sources = [
                            {k: s.get(k) or (dataset_name if k == "dataset" else None)
                             for k in ("dataset", "id", "language", "date",
                                       "url", "language_score", "folder_path")}
                            for s in sources_raw
                        ]
                    else:
                        sources = []
                    language = _coerce_list(rows["language"][i])
                    if has_date:
                        date = _coerce_list(rows["date"][i])
                    else:
                        seen: List[str] = []
                        for s in sources:
                            d = s.get("date")
                            if d and d not in seen:
                                seen.append(d)
                        date = seen
                    datasets = sorted({s["dataset"] for s in sources if s.get("dataset")})
                    if not datasets and dataset_name:
                        datasets = [dataset_name]
                    yield {
                        "_id":      sha256,
                        "_index":   index_name,
                        "_op_type": op_type,
                        "_source": {
                            "text":         rows["text"][i],
                            "language":     language,
                            "date":         date,
                            "source_count": rows["source_count"][i],
                            "datasets":     datasets,
                            "sources":      sources,
                        },
                    }
        except Exception as e:
            logger.error(f"Error in retry-create read of {fp}: {e}")


def _iter_conflict_updates(files: List[Path], index_name: str,
                            conflicts: set, chunk_size: int,
                            dataset_name: Optional[str] = None,
                            max_rows: Optional[int] = None):
    """Re-read parquet files; yield scripted update actions for conflicted SHA256s.

    max_rows must match pass-1 --max-docs so we don't scan beyond what was indexed.
    """
    logger = logging.getLogger(__name__)
    rows_seen = 0
    for fp in files:
        if max_rows is not None and rows_seen >= max_rows:
            break
        try:
            pf = pq.ParquetFile(str(fp))
            schema_names = pf.schema_arrow.names
            has_date = "date" in schema_names
            for batch in pf.iter_batches(batch_size=chunk_size):
                if max_rows is not None and rows_seen >= max_rows:
                    break
                rows = batch.to_pydict()
                n = len(rows["sha256"])
                for i in range(n):
                    if max_rows is not None and rows_seen >= max_rows:
                        break
                    rows_seen += 1
                    sha256 = rows["sha256"][i]
                    if sha256 is None or sha256 not in conflicts:
                        continue
                    sources_raw = rows["sources"][i]
                    sources = (
                        [{k: s.get(k) or (dataset_name if k == "dataset" else None)
                           for k in ("dataset", "id", "language", "date",
                                     "url", "language_score", "folder_path")}
                          for s in sources_raw]
                        if sources_raw else []
                    )
                    language = _coerce_list(rows["language"][i])
                    if has_date:
                        date = _coerce_list(rows["date"][i])
                    else:
                        seen: List[str] = []
                        for s in sources:
                            d = s.get("date")
                            if d and d not in seen:
                                seen.append(d)
                        date = seen
                    datasets = sorted({s["dataset"] for s in sources if s.get("dataset")})
                    if not datasets and dataset_name:
                        datasets = [dataset_name]
                    yield _update_action(sha256, index_name, sources, language, date, datasets)
        except Exception as e:
            logger.error(f"Error in conflict-update read of {fp}: {e}")


# ============================================================
# ES index creation
# ============================================================

def _shard_count(size_gb: float) -> int:
    if size_gb <= 0:
        return 1
    n = max(1, int(size_gb / 30) + 1)
    return min(n, 50)


def create_index(es: Elasticsearch, index_name: str, size_gb: float,
                 keep_existing: bool = False) -> None:
    logger = logging.getLogger(__name__)

    if es.indices.exists(index=index_name):
        if keep_existing:
            logger.info(f"Index '{index_name}' exists — keeping (append mode)")
            return
        logger.warning(f"Index '{index_name}' exists — deleting and recreating")
        es.indices.delete(index=index_name)

    num_shards = _shard_count(size_gb)
    logger.info(f"Creating index '{index_name}' with {num_shards} shards "
                f"(estimated {size_gb:.1f} GB indexed)")

    mapping = {
        "settings": {
            "number_of_shards": num_shards,
            "number_of_replicas": 0,
            "refresh_interval": "30s",
            "index.translog.durability": "async",
            "index.translog.flush_threshold_size": "2gb",
            "index": {"codec": "best_compression"},
            "analysis": {
                "analyzer": {
                    "web_content_analyzer": {
                        "type": "custom",
                        "char_filter": ["html_strip"],
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    }
                }
            },
        },
        "mappings": {
            "dynamic": "false",
            "properties": {
                # Full-text search
                "text": {
                    "type": "text",
                    "analyzer": "web_content_analyzer",
                    "index_options": "positions",
                    "norms": True,
                    "store": False,
                },
                # Core filterable fields
                "language":      {"type": "keyword"},           # array of unique languages
                "date":          {"type": "date", "format": "strict_date_optional_time||epoch_millis"},  # array of unique dates
                "source_count":  {"type": "integer"},
                "datasets":      {"type": "keyword"},           # array of dataset names
                # Full provenance stored but not indexed — use for retrieval only
                "sources":       {"type": "object", "enabled": False},
            },
        },
    }

    es.indices.create(index=index_name, body=mapping)
    logger.info(f"Index '{index_name}' created")


# ============================================================
# Document parsing worker
# ============================================================

def _coerce_list(v):
    """Ensure v is a list: wrap scalars, pass lists through, return [] for None."""
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if x is not None]
    return [v]


def _parse_file(file_path: Path, index_name: str, op_type: str,
                doc_queue: multiprocessing.Queue, chunk_size: int,
                max_docs: Optional[int] = None,
                dataset_name: Optional[str] = None) -> int:
    """Read one aggregated parquet file and push docs to queue. Returns doc count."""
    count = 0
    try:
        pf = pq.ParquetFile(str(file_path))
        schema_names = pf.schema_arrow.names
        has_date = "date" in schema_names

        for batch in pf.iter_batches(batch_size=chunk_size):
            rows = batch.to_pydict()
            n = len(rows["sha256"])
            docs = []
            for i in range(n):
                if max_docs is not None and count + len(docs) >= max_docs:
                    break
                sha256 = rows["sha256"][i]
                if sha256 is None:
                    continue
                sources_raw = rows["sources"][i]
                if sources_raw is not None:
                    sources = [
                        {
                            "dataset":        s.get("dataset") or dataset_name,
                            "id":             s.get("id"),
                            "language":       s.get("language"),
                            "date":           s.get("date"),
                            "url":            s.get("url"),
                            "language_score": s.get("language_score"),
                            "folder_path":    s.get("folder_path"),
                        }
                        for s in sources_raw
                    ]
                else:
                    sources = []

                # language may be a string (per-language agg output) or a list (merged output)
                language = _coerce_list(rows["language"][i])
                # date column may be absent (FW2 per-language agg has no top-level date);
                # fall back to unique dates collected from sources[]
                if has_date:
                    date = _coerce_list(rows["date"][i])
                else:
                    seen = []
                    for s in sources:
                        d = s.get("date")
                        if d and d not in seen:
                            seen.append(d)
                    date = seen

                doc = {
                    "_id":      sha256,
                    "_index":   index_name,
                    "_op_type": op_type,
                    "_source": {
                        "text":         rows["text"][i],
                        "language":     language,
                        "date":         date,
                        "source_count": rows["source_count"][i],
                        "datasets":     sorted({s["dataset"] for s in sources if s.get("dataset")}) or ([dataset_name] if dataset_name else []),
                        "sources":      sources,
                    },
                }
                docs.append(doc)

            if docs:
                doc_queue.put(docs)
                count += len(docs)
            if max_docs is not None and count >= max_docs:
                break

    except Exception as e:
        logging.getLogger(__name__).error(f"Error parsing {file_path}: {e}")

    return count


def parse_worker(file_list: List[Path], index_name: str, op_type: str,
                 doc_queue: multiprocessing.Queue,
                 chunk_size: int, result_queue: multiprocessing.Queue,
                 max_docs: Optional[int] = None,
                 dataset_name: Optional[str] = None) -> None:
    total = 0
    for fp in file_list:
        remaining = None if max_docs is None else max(0, max_docs - total)
        if remaining == 0:
            break
        total += _parse_file(fp, index_name, op_type, doc_queue, chunk_size, remaining, dataset_name)
    result_queue.put(total)


# ============================================================
# ES consumer (runs in main process, single thread)
# ============================================================

def es_consumer(doc_queue: multiprocessing.Queue, es: Elasticsearch,
                batch_size: int, max_chunk_bytes_mb: int,
                thread_count: int, queue_size: int,
                stats: Dict, stop_event: threading.Event,
                update_duplicates: bool = True,
                expected: int = 0) -> None:
    logger = logging.getLogger(__name__)
    log_every = 1_000_000
    next_log = log_every
    t_start = time.time()

    def _gen():
        while not (stop_event.is_set() and doc_queue.empty()):
            try:
                batch = doc_queue.get(timeout=1.0)
                yield from batch
            except Exception:
                continue

    try:
        for ok, info in helpers.parallel_bulk(
            es,
            _gen(),
            thread_count=thread_count,
            queue_size=queue_size,
            chunk_size=batch_size,
            max_chunk_bytes=max_chunk_bytes_mb * 1024 * 1024,
            raise_on_error=False,
        ):
            if ok:
                stats["indexed"] += 1
            else:
                action_info = info.get("create", info.get("index", info))
                err = action_info.get("error", {})
                if err.get("type") == "version_conflict_engine_exception":
                    if update_duplicates:
                        doc_id = action_info.get("_id")
                        if doc_id:
                            stats["conflicts"].add(doc_id)
                    else:
                        stats["skipped"] += 1
                elif err.get("type") == "es_rejected_execution_exception":
                    doc_id = action_info.get("_id")
                    if doc_id:
                        stats["rejected"].add(doc_id)
                    else:
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1
                    logger.warning(f"Failed doc: {info}")

            stats["processed"] += 1
            if stats["processed"] >= next_log:
                elapsed = time.time() - t_start
                rate = stats["processed"] / elapsed if elapsed > 0 else 0
                pct = f"{100 * stats['processed'] / expected:.1f}%" if expected > 0 else "?%"
                eta = ""
                if expected > 0 and rate > 0:
                    secs_left = (expected - stats["processed"]) / rate
                    eta = f"  ETA {int(secs_left/60)}m"
                logger.info(
                    f"[progress] {stats['processed']:,} / {expected:,} ({pct})  "
                    f"indexed={stats['indexed']:,}  skipped={stats['skipped'] + len(stats['conflicts']):,}  "
                    f"rejected={len(stats['rejected']):,}  rate={rate:.0f} docs/sec{eta}"
                )
                next_log += log_every
    except Exception as e:
        # TransportError(429) or other transport-level errors can escape parallel_bulk
        # even with raise_on_error=False. Catch here so the thread exits cleanly and
        # validation detects the shortfall via stats["failed"] > 0.
        stats["failed"] += 1
        logger.error(f"parallel_bulk raised unexpectedly (transport-level error): {e}")


# ============================================================
# Validation
# ============================================================

def validate(es: Elasticsearch, index_name: str, expected: int, stats: Dict,
             append_mode: bool = False) -> bool:
    logger = logging.getLogger(__name__)

    try:
        es.indices.refresh(index=index_name)
        es_count = es.indices.stats(index=index_name)["indices"][index_name]["total"]["docs"]["count"]
    except Exception as e:
        logger.error(f"Cannot query ES count: {e}")
        return False

    logger.info("=" * 70)
    logger.info("=== VALIDATION ===")
    logger.info(f"Unique docs in this batch:         {expected:>15,}")
    logger.info(f"Reported indexed this run:         {stats['indexed']:>15,}")
    logger.info(f"Reported skipped (dup SHA256):     {stats.get('skipped', 0):>15,}")
    logger.info(f"Reported failed:                   {stats['failed']:>15,}")
    logger.info(f"ES index total count:              {es_count:>15,}")
    if append_mode:
        logger.info("(append mode — ES total includes prior batches)")
    logger.info("-" * 70)

    ok = True

    if append_mode:
        # In append mode prior batches are already in ES; only check that:
        #   1. indexed + skipped ≥ 99% of expected (skipped = already in index, e.g. on retry)
        #   2. ES total is at least as large as this batch
        accounted = stats["indexed"] + stats.get("skipped", 0)
        if accounted < expected and stats["failed"] == 0:
            logger.warning(f"Only {accounted:,} docs accounted for "
                           f"(indexed={stats['indexed']:,}, skipped={stats.get('skipped',0):,}) "
                           f"vs expected {expected:,} with 0 failures")
            ok = False
        if es_count < expected:
            logger.warning(f"ES count {es_count:,} < this batch {expected:,} — something went wrong")
            ok = False
        else:
            logger.info(f"✓ ES total {es_count:,} >= this batch {expected:,}")
    else:
        if es_count == expected:
            logger.info("✓ ES count matches exactly")
        elif es_count < expected:
            logger.warning(f"ES count {es_count:,} < expected {expected:,} — "
                           f"{expected - es_count:,} docs missing (possible failures)")
            if stats["failed"] == 0:
                ok = False
        else:
            logger.error(f"ES count {es_count:,} > expected {expected:,} — duplication bug!")
            ok = False

    if stats["failed"] > 0:
        fail_rate = stats["failed"] / max(expected, 1)
        logger.error(f"{stats['failed']:,} documents permanently failed ({fail_rate*100:.4f}%) "
                     f"— 429-rejected docs are retried in Pass 3 and must not appear here")
        ok = False

    logger.info("=" * 70)
    logger.info("✓✓✓ VALIDATION PASSED" if ok else "❌❌❌ VALIDATION FAILED")
    logger.info("=" * 70)
    return ok


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )

    parser.add_argument("--data-dir", required=True,
                        help="Directory containing aggregated parquet files (Phase 1 output)")
    parser.add_argument("--index-name", required=True,
                        help="Target Elasticsearch index name")
    parser.add_argument("--es-host", default="localhost")
    parser.add_argument("--es-port", type=int, default=9200)
    parser.add_argument("--keep-existing-index", action="store_true",
                        help="Skip index deletion if it already exists (append mode)")
    parser.add_argument("--op-type", default="index", choices=["index", "create"],
                        help="ES op_type: 'index' (upsert) or 'create' (skip if _id exists). "
                             "Use 'create' when appending a dataset to an existing index so "
                             "duplicate SHA256s from a prior dataset are silently skipped.")

    # File-range splitting for multi-job chaining
    parser.add_argument("--file-range-start", type=int, default=None,
                        help="First file index (0-based, inclusive) to process in this job")
    parser.add_argument("--file-range-end", type=int, default=None,
                        help="Last file index (0-based, inclusive) to process in this job")

    # Performance
    parser.add_argument("--num-workers",      type=int, default=8)
    parser.add_argument("--chunk-size",       type=int, default=5000)
    parser.add_argument("--batch-size",       type=int, default=12500)
    parser.add_argument("--max-chunk-bytes",  type=int, default=50,   help="MB")
    parser.add_argument("--thread-count",     type=int, default=4)
    parser.add_argument("--queue-size",       type=int, default=8)

    parser.add_argument("--max-docs", type=int, default=None,
                        help="Stop after indexing this many documents total (for sampling/testing)")
    parser.add_argument("--dataset-name", default=None,
                        help="Fallback dataset name for sources[] entries that have no 'dataset' field "
                             "(e.g. 'fineweb-2' for FW2 aggregated parquets)")
    parser.add_argument("--update-duplicates", dest="update_duplicates",
                        action="store_true", default=True,
                        help="On SHA256 conflict, append new source entry to existing doc (default: on)")
    parser.add_argument("--no-update-duplicates", dest="update_duplicates",
                        action="store_false",
                        help="On SHA256 conflict, skip silently instead of updating sources[]")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    # Lowercase index name (ES requirement)
    args.index_name = args.index_name.lower()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # ---- Discover input files ----
    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        logger.error(f"data-dir not found: {data_dir}")
        sys.exit(1)

    all_files = sorted(data_dir.glob("*.parquet"))
    if not all_files:
        # Aggregated output might be in sub-partitions
        all_files = sorted(data_dir.glob("**/*.parquet"))
    if not all_files:
        logger.error(f"No parquet files found in {data_dir}")
        sys.exit(1)

    # Apply file-range slicing for multi-job chaining
    start_idx = args.file_range_start if args.file_range_start is not None else 0
    end_idx   = args.file_range_end   if args.file_range_end   is not None else len(all_files) - 1
    files = all_files[start_idx : end_idx + 1]
    if not files:
        logger.error(f"No files in range [{start_idx}, {end_idx}] (total: {len(all_files)})")
        sys.exit(1)

    total_bytes = sum(f.stat().st_size for f in files)
    total_gb = total_bytes / (1024 ** 3)

    # Quick row count from parquet metadata (fast — no full scan)
    ground_truth = sum(
        pq.ParquetFile(str(f)).metadata.num_rows for f in files
    )

    range_str = f" [{start_idx}–{end_idx}]" if (args.file_range_start is not None or args.file_range_end is not None) else ""
    logger.info("=" * 70)
    logger.info("=== Phase 2: Indexing Aggregated Data ===")
    logger.info(f"Data dir:     {data_dir}")
    logger.info(f"All files:    {len(all_files)}")
    logger.info(f"This batch:   {len(files)} files{range_str}, {total_gb:.2f} GB")
    logger.info(f"Unique docs:  {ground_truth:,}")
    logger.info(f"Index:        {args.index_name}")
    logger.info(f"Keep index:   {args.keep_existing_index}")
    logger.info(f"Workers:      {args.num_workers}")
    logger.info("=" * 70)

    # ---- Connect to ES ----
    # Use a long timeout: bulk requests with 150 MB of text can take >10s on a
    # loaded ES node. retry_on_timeout is safe because we use SHA256 as _id.
    es = Elasticsearch(
        [{"host": args.es_host, "port": args.es_port}],
        timeout=300,
        retry_on_timeout=True,
        max_retries=3,
    )
    try:
        es.info()
        logger.info(f"Connected to Elasticsearch at {args.es_host}:{args.es_port}")
    except Exception as e:
        logger.error(f"Cannot connect to ES: {e}")
        sys.exit(1)

    # ---- Create index ----
    # Estimate indexed size: aggregated data is text-heavy, ~2× raw parquet
    estimated_indexed_gb = total_gb * 2.0
    create_index(es, args.index_name, estimated_indexed_gb,
                 keep_existing=args.keep_existing_index)

    if args.dataset_name:
        logger.info(f"Dataset name: {args.dataset_name}  (fallback for sources with no dataset field)")
    logger.info(f"Update dupes: {args.update_duplicates} "
                f"({'append sources[] on conflict' if args.update_duplicates else 'skip on conflict'})")

    # ---- Launch workers ----
    ctx = multiprocessing.get_context("spawn")
    doc_queue = ctx.Queue(maxsize=args.queue_size * 4)
    result_queue = ctx.Queue()

    # Distribute files across workers
    worker_files = [[] for _ in range(args.num_workers)]
    for i, f in enumerate(files):
        worker_files[i % args.num_workers].append(f)

    workers = []
    for wfiles in worker_files:
        if not wfiles:
            continue
        p = ctx.Process(
            target=parse_worker,
            args=(wfiles, args.index_name, args.op_type, doc_queue,
                  args.chunk_size, result_queue, args.max_docs, args.dataset_name),
            daemon=True,
        )
        p.start()
        workers.append(p)

    # ---- ES consumer in main thread ----
    stats: Dict = {"indexed": 0, "failed": 0, "skipped": 0, "conflicts": set(), "rejected": set(), "processed": 0}
    stop_event = threading.Event()

    total_start = time.time()
    indexing_start = time.time()

    consumer_thread = threading.Thread(
        target=es_consumer,
        args=(doc_queue, es, args.batch_size, args.max_chunk_bytes,
              args.thread_count, args.queue_size, stats, stop_event,
              args.update_duplicates, ground_truth),
        daemon=True,
    )
    consumer_thread.start()

    # Progress reporting — poll ES doc count every 5 minutes
    rate_interval = 300  # seconds
    last_rate_log = time.time()
    prev_es_count: Optional[int] = None
    prev_rate_time: Optional[float] = None

    remaining_workers = list(workers)
    while remaining_workers:
        still_alive = []
        for p in remaining_workers:
            p.join(timeout=5)
            if p.is_alive():
                still_alive.append(p)
        remaining_workers = still_alive

        now = time.time()
        if now - last_rate_log >= rate_interval:
            try:
                es_count = es.count(index=args.index_name)["count"]
                local_rate = stats["indexed"] / max(now - indexing_start, 1)
                msg = (f"[throughput] local={stats['indexed']:,} indexed this chunk  "
                       f"({local_rate:.0f} docs/sec local)")
                if prev_es_count is not None and prev_rate_time is not None:
                    dt = now - prev_rate_time
                    delta = es_count - prev_es_count
                    global_rate = delta / dt if dt > 0 else 0
                    msg += (f"  |  ES total={es_count:,}  "
                            f"global={global_rate:.0f} docs/sec  "
                            f"({global_rate * 3600:,.0f}/hr)")
                else:
                    msg += f"  |  ES total={es_count:,}"
                logger.info(msg)
                prev_es_count = es_count
                prev_rate_time = now
            except Exception as e:
                logger.warning(f"[throughput] Could not query ES count: {e}")
            last_rate_log = now

    stop_event.set()
    consumer_thread.join()

    indexing_end = time.time()
    duration = indexing_end - indexing_start

    # Collect parsed counts
    parsed_total = 0
    while not result_queue.empty():
        parsed_total += result_queue.get_nowait()

    logger.info("=" * 70)
    logger.info(f"Pass 1 complete in {duration:.1f}s")
    logger.info(f"Parsed:    {parsed_total:,}")
    logger.info(f"Indexed:   {stats['indexed']:,}  (new documents)")
    logger.info(f"Conflicts: {len(stats['conflicts']):,}  (SHA256 already in index)")
    logger.info(f"Skipped:   {stats['skipped']:,}  (conflicts silently dropped)")
    logger.info(f"Rejected:  {len(stats['rejected']):,}  (429-rejected, will retry in Pass 3)")
    logger.info(f"Failed:    {stats['failed']:,}")
    if duration > 0:
        logger.info(f"Rate:      {stats['indexed'] / duration:.0f} docs/sec")

    # ---- Pass 2: scripted update for duplicates (with 429 retry) ----
    if args.update_duplicates and stats["conflicts"]:
        n_conf = len(stats["conflicts"])
        logger.info("=" * 70)
        logger.info(f"Pass 2: updating sources[] on {n_conf:,} duplicate documents ...")
        p2_stats = {"updated": 0, "failed": 0}
        p2_start = time.time()
        p2_rejected: set = set()

        def _run_p2_bulk(conflict_set: set) -> set:
            """Send update actions for conflict_set; return SHA256s that got 429'd."""
            rejected_this_round: set = set()
            for ok, info in helpers.parallel_bulk(
                es,
                _iter_conflict_updates(files, args.index_name, conflict_set, args.chunk_size,
                                       args.dataset_name, max_rows=args.max_docs),
                thread_count=args.thread_count,
                queue_size=args.queue_size,
                chunk_size=args.batch_size,
                max_chunk_bytes=args.max_chunk_bytes * 1024 * 1024,
                raise_on_error=False,
            ):
                if ok:
                    p2_stats["updated"] += 1
                else:
                    ai = info.get("update", info)
                    et = ai.get("error", {}).get("type", "")
                    if et == "es_rejected_execution_exception":
                        doc_id = ai.get("_id")
                        if doc_id:
                            rejected_this_round.add(doc_id)
                    else:
                        p2_stats["failed"] += 1
                        logger.warning(f"Failed conflict update: {info}")
            return rejected_this_round

        p2_rejected = _run_p2_bulk(stats["conflicts"])
        p2_max_rounds = 8
        p2_wait_cap = 60
        for attempt in range(p2_max_rounds):
            if not p2_rejected:
                break
            wait_secs = min(2 ** attempt, p2_wait_cap)
            logger.info(f"  Pass 2 round {attempt + 1}: {len(p2_rejected):,} updates still 429'd, "
                        f"waiting {wait_secs}s...")
            time.sleep(wait_secs)
            p2_rejected = _run_p2_bulk(p2_rejected)
            logger.info(f"  Pass 2 round {attempt + 1}: remaining={len(p2_rejected):,}")
        if p2_rejected:
            logger.error(f"Pass 2: {len(p2_rejected):,} conflict updates permanently failed")
            p2_stats["failed"] += len(p2_rejected)

        p2_dur = time.time() - p2_start
        logger.info(f"Pass 2 complete in {p2_dur:.1f}s: "
                    f"{p2_stats['updated']:,} updated, {p2_stats['failed']:,} failed")
        stats["updated"] = p2_stats["updated"]
        stats["update_failed"] = p2_stats["failed"]

    # ---- Pass 3: retry 429-rejected docs with exponential backoff ----
    if stats["rejected"]:
        max_retry_rounds = 10
        wait_cap_secs = 60
        logger.info("=" * 70)
        logger.info(f"Pass 3: retrying {len(stats['rejected']):,} 429-rejected docs "
                    f"(up to {max_retry_rounds} rounds, backoff capped at {wait_cap_secs}s)")
        for attempt in range(max_retry_rounds):
            if not stats["rejected"]:
                break
            n_pending = len(stats["rejected"])
            wait_secs = min(2 ** attempt, wait_cap_secs)
            logger.info(f"  Round {attempt + 1}/{max_retry_rounds}: {n_pending:,} docs, "
                        f"waiting {wait_secs}s...")
            time.sleep(wait_secs)
            retry_set = set(stats["rejected"])
            stats["rejected"] = set()
            p3_indexed = 0
            for ok_r, info_r in helpers.parallel_bulk(
                es,
                _iter_retry_create(files, args.index_name, retry_set, args.chunk_size,
                                   args.op_type, args.dataset_name, args.max_docs),
                thread_count=args.thread_count,
                queue_size=args.queue_size,
                chunk_size=args.batch_size,
                max_chunk_bytes=args.max_chunk_bytes * 1024 * 1024,
                raise_on_error=False,
            ):
                if ok_r:
                    stats["indexed"] += 1
                    p3_indexed += 1
                else:
                    ai = info_r.get("create", info_r.get("index", info_r))
                    et = ai.get("error", {}).get("type", "")
                    if et == "es_rejected_execution_exception":
                        doc_id = ai.get("_id")
                        if doc_id:
                            stats["rejected"].add(doc_id)
                    elif et == "version_conflict_engine_exception":
                        stats["skipped"] += 1  # already indexed by another worker
                    else:
                        stats["failed"] += 1
                        logger.warning(f"Permanent failure in Pass 3 retry: {info_r}")
            logger.info(f"  Round {attempt + 1}: indexed={p3_indexed:,}, "
                        f"still_rejected={len(stats['rejected']):,}, "
                        f"failed={stats['failed']:,}")
            if not stats["rejected"]:
                logger.info("  All 429-rejected docs successfully retried.")
                break
        if stats["rejected"]:
            n = len(stats["rejected"])
            logger.error(f"Still {n:,} docs rejected after exhausting retry rounds — "
                         f"counting as permanent failures")
            stats["failed"] += n
            stats["rejected"] = set()
        logger.info("=" * 70)

    # ---- Validate ----
    ok = validate(es, args.index_name, ground_truth, stats,
                  append_mode=args.keep_existing_index)

    if ok:
        logger.info("=== Indexing Job Completed Successfully ===")
        sys.exit(0)
    else:
        logger.error("=== Indexing Job Failed — Validation Errors ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
