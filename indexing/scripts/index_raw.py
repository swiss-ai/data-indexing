#!/usr/bin/env python3
"""
Index datasets that do not have a pre-computed SHA256 into the global ES index.

For datasets already Spark-aggregated (FW1+FW-edu+DCLM merged, FW2), use
index_aggregated.py instead (sha256 is already in the parquet).

This script handles:
  - EuroParl, ParaDocs   — translation pairs, language from dir name
  - FLAN                  — English-only
  - EuroBlocks            — multilingual (no language field in parquet)
  - institutional-books   — rich metadata (author, title, date, language)
  - gutenberg             — JSONL files
  - canaries              — gzipped JSONL files

SHA256(text) is computed at index time and used as ES _id.
op_type="create" silently skips documents already present — so this script
can be run in any order and against an index that already contains other datasets.

All output lands in the same global index as FW1+FW-edu+DCLM and FW2.

Usage
-----
python3 index_raw.py \\
    --dataset europarl \\
    --data-dir /capstor/.../europarl_bidirectional_preprocessed/data \\
    --index-name global-pretraining \\
    --es-host nid006184 --es-port 9200
"""

import argparse
import gzip
import hashlib
import json
import logging
import multiprocessing
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pyarrow.parquet as pq
from elasticsearch import Elasticsearch, helpers


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
        "_op_type":         "update",
        "_index":           index_name,
        "_id":              sha256,
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


def _iter_conflict_updates_raw(files: List[Path], dataset: str, data_dir: str,
                                index_name: str, conflicts: set, chunk_size: int,
                                max_rows: Optional[int] = None):
    """Re-read files; yield scripted update actions for conflicted SHA256s.

    max_rows must match pass-1 --max-docs so we don't scan beyond what was indexed.
    """
    logger = logging.getLogger(__name__)
    is_jsonl = dataset in JSONL_DATASETS
    text_key = "document" if dataset == "canaries" else "text"
    parquet_text_col = "content" if dataset in CONTENT_FIELD_DATASETS else "text"
    rows_seen = 0

    def _open(p: Path):
        if p.name.endswith(".gz"):
            return gzip.open(p, "rt", encoding="utf-8", errors="replace")
        return open(p, "r", encoding="utf-8", errors="replace")

    for fp in files:
        if max_rows is not None and rows_seen >= max_rows:
            break
        try:
            if is_jsonl:
                with _open(fp) as fh:
                    for line_num, line in enumerate(fh):
                        if max_rows is not None and rows_seen >= max_rows:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        rows_seen += 1
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(record, dict):
                            continue
                        text = record.get(text_key, "")
                        if not text:
                            continue
                        sha = _sha256(text)
                        if not sha or sha not in conflicts:
                            continue
                        meta = extract_metadata_jsonl(dataset, record, str(fp), line_num)
                        doc = _build_doc(sha, text, meta, dataset, index_name)
                        src = doc["_source"]
                        yield _update_action(sha, index_name, src["sources"],
                                             src["language"], src["date"], src["datasets"])
            else:
                pf = pq.ParquetFile(str(fp))
                for batch in pf.iter_batches(batch_size=chunk_size):
                    if max_rows is not None and rows_seen >= max_rows:
                        break
                    rows = batch.to_pydict()
                    n = len(rows.get(parquet_text_col, []))
                    for i in range(n):
                        if max_rows is not None and rows_seen >= max_rows:
                            break
                        rows_seen += 1
                        text = rows.get(parquet_text_col, [None])[i]
                        if not text:
                            continue
                        sha = _sha256(text)
                        if not sha or sha not in conflicts:
                            continue
                        meta = extract_metadata_parquet(dataset, i, rows, str(fp), data_dir)
                        doc = _build_doc(sha, text, meta, dataset, index_name)
                        src = doc["_source"]
                        yield _update_action(sha, index_name, src["sources"],
                                             src["language"], src["date"], src["datasets"])
        except Exception as e:
            logger.error(f"Error in conflict-update read of {fp}: {e}")


# ============================================================
# Helpers
# ============================================================

def _sha256(text: str) -> Optional[str]:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row_get(rows: dict, col: str, i: int, default=None):
    """Safely get rows[col][i], returning default if col is missing or too short."""
    col_data = rows.get(col)
    if not col_data or i >= len(col_data):
        return default
    return col_data[i]


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _iso_date_from_year(year_str) -> Optional[str]:
    """'1903' → '1903-01-01'"""
    if not year_str:
        return None
    try:
        y = str(year_str).strip()
        if y.isdigit() and 1000 <= int(y) <= 9999:
            return f"{y}-01-01"
    except Exception:
        pass
    return None


def _language_pair_from_path(file_path: str, data_dir: str) -> Optional[str]:
    """
    Derive language pair from the path component directly under data_dir.
    E.g. .../lt-sk/is_reverse_True/output/file.parquet → "lt-sk"
    """
    try:
        rel = Path(file_path).relative_to(data_dir)
        for part in rel.parts:
            if "-" in part and not part.startswith("is_") and not part.endswith(".parquet"):
                segs = part.split("-")
                if len(segs) == 2 and all(2 <= len(s) <= 3 for s in segs):
                    return part
    except Exception:
        pass
    return None


# ============================================================
# Per-dataset metadata extraction (parquet)
# ============================================================

def extract_metadata_parquet(dataset: str, i: int, rows: dict,
                             file_path: str, data_dir: str) -> dict:
    folder_path = str(Path(file_path).parent)
    meta = _row_get(rows, "metadata", i) or {}
    if not isinstance(meta, dict):
        meta = {}

    if dataset == "europarl" or dataset == "paradocs":
        pair  = _language_pair_from_path(file_path, data_dir)
        langs = pair.split("-") if pair else []
        return dict(id=_row_get(rows, "id", i), language=langs, date=None,
                    url=None, language_score=None, folder_path=folder_path,
                    language_pair=pair, author=None, title=None)

    elif dataset == "euroblocks":
        return dict(id=_row_get(rows, "id", i), language=[], date=None,
                    url=None, language_score=None, folder_path=folder_path,
                    language_pair=None, author=None, title=None)

    elif dataset == "institutional-books":
        lang = meta.get("language_gen")
        return dict(
            id=_row_get(rows, "id", i),
            language=[lang] if lang else [],
            date=_iso_date_from_year(meta.get("date1_src")),
            url=None,
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=meta.get("author_src"),
            title=meta.get("title_src"),
        )

    elif dataset == "finemath":
        # metadata is a JSON string
        m_raw = _row_get(rows, "metadata", i)
        m = json.loads(m_raw) if isinstance(m_raw, str) else (m_raw or {})
        ft = m.get("fetch_time")
        date = None
        if ft:
            try:
                date = datetime.fromtimestamp(ft / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
        lang = m.get("language")
        return dict(
            id=_row_get(rows, "id", i),
            language=[lang] if lang else [],
            date=date,
            url=m.get("url"),
            language_score=_to_float(m.get("language_score")),
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
            score=_to_float(m.get("score")),
        )

    elif dataset == "infiwebmath":
        # metadata is a JSON string; url and score are inside metadata
        m_raw = _row_get(rows, "metadata", i)
        m = json.loads(m_raw) if isinstance(m_raw, str) else (m_raw or {})
        lang_label = m.get("ft_lang_label", "")
        lang = lang_label.replace("__label__", "") if lang_label else None
        return dict(
            id=_row_get(rows, "id", i),
            language=[lang] if lang else [],
            date=None,
            url=m.get("url"),
            language_score=_to_float(m.get("ft_lang_prob")),
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
            score=_to_float(m.get("score")),
        )

    elif dataset == "megamath-web":
        # metadata is already a Python dict (pyarrow deserialises struct columns)
        m = _row_get(rows, "metadata", i) or {}
        lang = m.get("lang")
        return dict(
            id=_row_get(rows, "id", i),
            language=[lang] if lang else [],
            date=m.get("timestamp"),
            url=m.get("url"),
            language_score=_to_float(m.get("lang_score")),
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
            score=_to_float(m.get("math_score")),
        )

    elif dataset == "starcoder":
        # No natural language. score = quality (sum of clarity+practice+educational).
        # repo_name for provenance.
        return dict(
            id=_row_get(rows, "id", i),
            language=[],
            date=None,
            url=None,
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
            score=_to_float(_row_get(rows, "quality", i)),
            repo_name=_row_get(rows, "max_stars_repo_name", i),
        )

    elif dataset == "starcoder-extras":
        # Multiple subdirs with varying schemas; repo_name from whichever col is present.
        repo = (
            _row_get(rows, "max_stars_repo_name", i)
            or _row_get(rows, "repo_name", i)
        )
        return dict(
            id=_row_get(rows, "id", i),
            language=[],
            date=None,
            url=None,
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
            score=None,
            repo_name=repo,
        )

    elif dataset == "wikipedia":
        # Language column is "iso639-3" (e.g. "en", "de", "szl"), NOT "language".
        # No id column — use url as document id.
        lang = _row_get(rows, "iso639-3", i)
        url = _row_get(rows, "url", i)
        return dict(
            id=url,
            language=[lang] if lang else [],
            date=None,
            url=url,
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=_row_get(rows, "title", i),
        )

    elif dataset == "flan":
        # 4 sub-collections: Commercial-Flan-Collection-Chain-Of-Thought, Dialog,
        # Flan-2021, SNI. The collection is encoded in folder_path (stored in
        # sources[]) — sufficient for filtering/retrieval without extra fields.
        return dict(
            id=_row_get(rows, "id", i),
            language=["eng"],
            date=None,
            url=None,
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
        )

    elif dataset in ("alignment", "sft-mixture"):
        # Preprocessed parquet from preprocess_alignment.py / preprocess_sft.py.
        # Columns: text, id only. No language, date, or dataset_source stored.
        return dict(
            id=_row_get(rows, "id", i),
            language=[],
            date=None,
            url=None,
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
        )

    else:
        # Generic parquet fallback
        lang = _row_get(rows, "language", i) or meta.get("language")
        return dict(
            id=_row_get(rows, "id", i),
            language=[lang] if lang else [],
            date=_row_get(rows, "date", i) or meta.get("date"),
            url=_row_get(rows, "url", i) or meta.get("url"),
            language_score=_to_float(_row_get(rows, "language_score", i) or meta.get("language_score")),
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
        )


# ============================================================
# Per-dataset metadata extraction (JSONL)
# ============================================================

def extract_metadata_jsonl(dataset: str, record: dict, file_path: str,
                           line_num: int = 0) -> dict:
    folder_path = str(Path(file_path).parent)
    if dataset == "gutenberg":
        lang = record.get("language")
        # Gutenberg JSONL has no id field — synthesize one from filename + line number
        synth_id = f"{Path(file_path).name}:{line_num}"
        return dict(id=synth_id, language=[lang] if lang else [],
                    date=None, url=None, language_score=None,
                    folder_path=folder_path, language_pair=None,
                    author=record.get("author"), title=record.get("title"))
    elif dataset == "canaries":
        return dict(id=record.get("canary_idx"), language=[], date=None,
                    url=None, language_score=None, folder_path=folder_path,
                    language_pair=None, author=None, title=None)
    elif dataset == "stackv2-edu":
        meta = record.get("metadata") or {}
        created = record.get("created")
        return dict(
            id=record.get("id"),
            language=[],
            date=created,      # ISO datetime assumed UTC; no natural language
            url=meta.get("url"),
            language_score=None,
            folder_path=folder_path,
            language_pair=None,
            author=None,
            title=None,
            score=_to_float(record.get("score")),
            repo_name=meta.get("repo_name"),
        )
    else:
        lang = record.get("language")
        return dict(id=record.get("id"), language=[lang] if lang else [],
                    date=record.get("date"), url=record.get("url"),
                    language_score=_to_float(record.get("language_score")),
                    folder_path=folder_path, language_pair=None,
                    author=record.get("author"), title=record.get("title"))


# ============================================================
# Document builder
# ============================================================

def _build_doc(sha256: str, text: str, meta: dict,
               dataset: str, index_name: str) -> dict:
    langs = meta.get("language") or []
    date  = meta.get("date")
    dates = [date] if date else []

    source_entry = {k: v for k, v in {
        "dataset":          dataset,
        "id":               meta.get("id"),
        "language":         langs[0] if len(langs) == 1 else (langs or None),
        "date":             date,
        "url":              meta.get("url"),
        "language_score":   meta.get("language_score"),
        "folder_path":      meta.get("folder_path"),
        "language_pair":    meta.get("language_pair"),
        "author":           meta.get("author"),
        "title":            meta.get("title"),
        "score":            meta.get("score"),
        "repo_name":        meta.get("repo_name"),
        "dataset_source":   meta.get("dataset_source"),
    }.items() if v is not None}

    return {
        "_id":      sha256,
        "_index":   index_name,
        "_op_type": "create",
        "_source": {
            "text":         text,
            "language":     langs,
            "date":         dates,
            "source_count": 1,
            "datasets":     [dataset],
            "sources":      [source_entry],
        },
    }


# ============================================================
# File discovery
# ============================================================

# Datasets where the text lives in "content" instead of "text"
CONTENT_FIELD_DATASETS = {"starcoder", "starcoder-extras"}

# Datasets that use JSONL (or JSONL-in-.json.gz) instead of parquet
JSONL_DATASETS = {"gutenberg", "canaries", "stackv2-edu"}


def find_files(data_dir: Path, dataset: str) -> List[Path]:
    if dataset in JSONL_DATASETS:
        files = sorted(
            p for p in data_dir.rglob("*")
            if p.is_file() and (
                p.suffix == ".jsonl"
                or p.name.endswith(".jsonl.gz")
                or p.name.endswith(".json.gz")   # stackv2-edu uses .json.gz
            )
            # gutenberg dir also has *_token.jsonl (tokenized) — skip them
            and not (dataset == "gutenberg" and "token" in p.name)
            # canaries dir has templates.jsonl (bare string templates, not docs) — skip it
            and not (dataset == "canaries" and p.name == "templates.jsonl")
        )
    else:
        files = sorted(data_dir.rglob("*.parquet"))
    if not files:
        logging.getLogger(__name__).error(
            f"No files found under {data_dir} for dataset '{dataset}'"
        )
    return files


# ============================================================
# Parse workers
# ============================================================

def _parse_parquet(file_path: Path, dataset: str, data_dir: str,
                   index_name: str, doc_queue: multiprocessing.Queue,
                   chunk_size: int, max_docs: Optional[int] = None) -> int:
    text_col = "content" if dataset in CONTENT_FIELD_DATASETS else "text"
    count = 0
    try:
        pf = pq.ParquetFile(str(file_path))
        for batch in pf.iter_batches(batch_size=chunk_size):
            rows = batch.to_pydict()
            n    = len(rows.get(text_col, []))
            docs = []
            for i in range(n):
                if max_docs is not None and count + len(docs) >= max_docs:
                    break
                text = rows.get(text_col, [None])[i]
                if not text:
                    continue
                sha = _sha256(text)
                if not sha:
                    continue
                meta = extract_metadata_parquet(dataset, i, rows, str(file_path), data_dir)
                docs.append(_build_doc(sha, text, meta, dataset, index_name))
            if docs:
                doc_queue.put(docs)
                count += len(docs)
            if max_docs is not None and count >= max_docs:
                break
    except Exception as e:
        logging.getLogger(__name__).error(f"Error parsing parquet {file_path}: {e}")
    return count


def _parse_jsonl(file_path: Path, dataset: str, index_name: str,
                 doc_queue: multiprocessing.Queue, chunk_size: int,
                 max_docs: Optional[int] = None) -> int:
    count = 0
    docs  = []
    text_key = "document" if dataset == "canaries" else "text"

    def _open(p: Path):
        if p.name.endswith(".gz"):
            return gzip.open(p, "rt", encoding="utf-8", errors="replace")
        return open(p, "r", encoding="utf-8", errors="replace")

    try:
        with _open(file_path) as fh:
            for line_num, line in enumerate(fh):
                if max_docs is not None and count + len(docs) >= max_docs:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = record.get(text_key, "")
                if not text:
                    continue
                sha = _sha256(text)
                if not sha:
                    continue
                meta = extract_metadata_jsonl(dataset, record, str(file_path), line_num)
                docs.append(_build_doc(sha, text, meta, dataset, index_name))
                if len(docs) >= chunk_size:
                    doc_queue.put(docs)
                    count += len(docs)
                    docs = []
        if docs:
            doc_queue.put(docs)
            count += len(docs)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error parsing jsonl {file_path}: {e}")
    return count


def parse_worker(file_list: List[Path], dataset: str, data_dir: str,
                 index_name: str, doc_queue: multiprocessing.Queue,
                 chunk_size: int, result_queue: multiprocessing.Queue,
                 max_docs: Optional[int] = None) -> None:
    is_jsonl = dataset in JSONL_DATASETS
    total = 0
    for fp in file_list:
        remaining = None if max_docs is None else max(0, max_docs - total)
        if remaining == 0:
            break
        if is_jsonl:
            total += _parse_jsonl(fp, dataset, index_name, doc_queue, chunk_size, remaining)
        else:
            total += _parse_parquet(fp, dataset, data_dir, index_name, doc_queue, chunk_size, remaining)
    result_queue.put(total)


# ============================================================
# Pass-3 retry iterator (re-reads files for 429-rejected SHA256s)
# ============================================================

def _iter_retry_create_raw(
    files: List[Path], dataset: str, data_dir: str,
    index_name: str, chunk_size: int, rejected: set,
):
    text_col = "content" if dataset in CONTENT_FIELD_DATASETS else "text"
    text_key = "document" if dataset == "canaries" else "text"
    is_jsonl  = dataset in JSONL_DATASETS
    logger    = logging.getLogger(__name__)

    def _open_file(p: Path):
        if p.name.endswith(".gz"):
            return gzip.open(p, "rt", encoding="utf-8", errors="replace")
        return open(p, "r", encoding="utf-8", errors="replace")

    for fp in files:
        try:
            if is_jsonl:
                with _open_file(fp) as fh:
                    for line_num, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(record, dict):
                            continue
                        text = record.get(text_key, "")
                        if not text:
                            continue
                        sha = _sha256(text)
                        if sha and sha in rejected:
                            meta = extract_metadata_jsonl(dataset, record, str(fp), line_num)
                            yield _build_doc(sha, text, meta, dataset, index_name)
            else:
                pf = pq.ParquetFile(str(fp))
                for batch in pf.iter_batches(batch_size=chunk_size):
                    rows = batch.to_pydict()
                    n = len(rows.get(text_col, []))
                    for i in range(n):
                        text = rows.get(text_col, [None])[i]
                        if not text:
                            continue
                        sha = _sha256(text)
                        if sha and sha in rejected:
                            meta = extract_metadata_parquet(dataset, i, rows, str(fp), data_dir)
                            yield _build_doc(sha, text, meta, dataset, index_name)
        except Exception as e:
            logger.error(f"Error in retry-create read of {fp}: {e}")


# ============================================================
# ES consumer
# ============================================================

_LOG_EVERY_P1 = 500_000


def es_consumer(doc_queue: multiprocessing.Queue, es: Elasticsearch,
                batch_size: int, max_chunk_bytes_mb: int,
                thread_count: int, queue_size: int,
                stats: dict, stop_event: threading.Event,
                update_duplicates: bool = True,
                start_time: float = 0.0) -> None:
    logger = logging.getLogger(__name__)
    next_log = _LOG_EVERY_P1

    def _gen():
        while not (stop_event.is_set() and doc_queue.empty()):
            try:
                batch = doc_queue.get(timeout=1.0)
                yield from batch
            except Exception:
                continue

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
            action_info = info.get("create", info)
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
                logger.warning(f"Failed doc: {info}")

        stats["processed"] += 1
        if stats["processed"] >= next_log:
            elapsed = time.time() - start_time if start_time else 1.0
            rate = stats["processed"] / elapsed if elapsed > 0 else 0
            logger.info(
                f"[progress P1] {stats['processed']:,} docs  "
                f"indexed={stats['indexed']:,}  conflicts={len(stats['conflicts']):,}  "
                f"rejected={len(stats['rejected']):,}  rate={rate:,.0f} docs/sec"
            )
            next_log += _LOG_EVERY_P1


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    parser.add_argument(
        "--dataset", required=True,
        choices=[
            # Existing raw datasets
            "europarl", "paradocs", "flan", "euroblocks",
            "institutional-books", "gutenberg", "canaries",
            "wikipedia",        # Wikipedia (language from iso639-3 column)
            "generic",          # Generic parquet fallback
            # New code/math datasets
            "finemath",         # FineMath-3plus (math web crawl)
            "infiwebmath",      # InfiMM-WebMath-3plus (math web crawl)
            "megamath-web",     # LLM360 MegaMath Web (math web crawl)
            "starcoder",        # StarCoder annotated (code)
            "starcoder-extras", # StarCoder extras: issues, jupyter, rst (code)
            "stackv2-edu",      # CommonPile Stack-v2-Edu (code, JSONL .json.gz)
            # Posttraining datasets
            "alignment",        # Preprocessed alignment data (8B+70B union parquet)
            "sft-mixture",      # SFT mixture (parquet, once downloaded)
        ],
        help="Dataset type (selects metadata extraction logic)",
    )
    parser.add_argument("--data-dir",   required=True)
    parser.add_argument("--index-name", required=True,
                        help="Global ES index name (must already exist)")
    parser.add_argument("--es-host", default="localhost")
    parser.add_argument("--es-port", type=int, default=9200)

    # Subset of files — for splitting large datasets across jobs
    parser.add_argument("--file-range-start", type=int, default=None)
    parser.add_argument("--file-range-end",   type=int, default=None)

    # Performance
    parser.add_argument("--num-workers",     type=int, default=8)
    parser.add_argument("--chunk-size",      type=int, default=5000)
    parser.add_argument("--batch-size",      type=int, default=12500)
    parser.add_argument("--max-chunk-bytes", type=int, default=50, help="MB")
    parser.add_argument("--thread-count",    type=int, default=4)
    parser.add_argument("--queue-size",      type=int, default=8)
    parser.add_argument("--max-docs", type=int, default=None,
                        help="Stop after indexing this many documents total (for sampling/testing)")
    parser.add_argument("--update-duplicates", dest="update_duplicates",
                        action="store_true", default=True,
                        help="On SHA256 conflict, append new source entry to existing doc (default: on)")
    parser.add_argument("--no-update-duplicates", dest="update_duplicates",
                        action="store_false",
                        help="On SHA256 conflict, skip silently instead of updating sources[]")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    args.index_name = args.index_name.lower()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        logger.error(f"data-dir not found: {data_dir}")
        sys.exit(1)

    all_files = find_files(data_dir, args.dataset)
    if not all_files:
        sys.exit(1)

    start_idx = args.file_range_start if args.file_range_start is not None else 0
    end_idx   = args.file_range_end   if args.file_range_end   is not None else len(all_files) - 1
    files     = all_files[start_idx : end_idx + 1]
    if not files:
        logger.error(f"No files in range [{start_idx}, {end_idx}] (total: {len(all_files)})")
        sys.exit(1)

    total_bytes = sum(f.stat().st_size for f in files)
    total_gb    = total_bytes / (1024 ** 3)
    range_str   = f" [{start_idx}–{end_idx}]" if args.file_range_start is not None else ""

    logger.info("=" * 70)
    logger.info(f"Dataset:    {args.dataset}")
    logger.info(f"Data dir:   {data_dir}")
    logger.info(f"Files:      {len(files)}{range_str} of {len(all_files)} total  ({total_gb:.2f} GB)")
    logger.info(f"Index:      {args.index_name}  (op_type=create, SHA256 _id)")
    logger.info(f"Workers:    {args.num_workers}")
    logger.info("=" * 70)

    es = Elasticsearch(
        [{"host": args.es_host, "port": args.es_port}],
        timeout=300, retry_on_timeout=True, max_retries=3,
    )
    try:
        es.info()
        logger.info(f"Connected to ES at {args.es_host}:{args.es_port}")
    except Exception as e:
        logger.error(f"Cannot connect to ES: {e}")
        sys.exit(1)

    if not es.indices.exists(index=args.index_name):
        logger.error(
            f"Index '{args.index_name}' does not exist. "
            "Run index_aggregated.py first (it creates the index)."
        )
        sys.exit(1)

    ctx          = multiprocessing.get_context("spawn")
    doc_queue    = ctx.Queue(maxsize=args.queue_size * 8)
    result_queue = ctx.Queue()

    worker_files: List[List[Path]] = [[] for _ in range(args.num_workers)]
    for idx, f in enumerate(files):
        worker_files[idx % args.num_workers].append(f)

    workers = []
    for wfiles in worker_files:
        if not wfiles:
            continue
        p = ctx.Process(
            target=parse_worker,
            args=(wfiles, args.dataset, str(data_dir), args.index_name,
                  doc_queue, args.chunk_size, result_queue, args.max_docs),
            daemon=True,
        )
        p.start()
        workers.append(p)

    stats      = {"indexed": 0, "skipped": 0, "failed": 0, "conflicts": set(), "rejected": set(), "processed": 0}
    stop_event = threading.Event()
    start_time = time.time()

    consumer_thread = threading.Thread(
        target=es_consumer,
        args=(doc_queue, es, args.batch_size, args.max_chunk_bytes,
              args.thread_count, args.queue_size, stats, stop_event,
              args.update_duplicates, start_time),
        daemon=True,
    )
    consumer_thread.start()

    for p in workers:
        p.join()
    stop_event.set()
    consumer_thread.join()

    duration     = time.time() - start_time
    parsed_total = 0
    while not result_queue.empty():
        parsed_total += result_queue.get_nowait()

    logger.info("=" * 70)
    logger.info(f"Pass 1 complete in {duration:.1f}s")
    logger.info(f"Parsed:    {parsed_total:,}")
    logger.info(f"Indexed:   {stats['indexed']:,}  (new documents)")
    logger.info(f"Conflicts: {len(stats['conflicts']):,}  (SHA256 already in index)")
    logger.info(f"Skipped:   {stats['skipped']:,}  (conflicts silently dropped)")
    logger.info(f"Failed:    {stats['failed']:,}")
    if duration > 0:
        logger.info(f"Rate:      {stats['indexed'] / duration:,.0f} docs/sec")

    # ---- Pass 2: scripted update for duplicates ----
    # Skip entirely when Pass 1 indexed 0 new docs: every conflict is a re-run of
    # the same source, so all Painless executions would be no-ops (dup=true).
    # Running Pass 2 in this case saturates ES for nothing (seen with paradocs: 10h
    # for 73M no-op updates that blocked all other concurrent workers via 429s).
    if stats["indexed"] == 0 and stats["conflicts"]:
        logger.info(
            f"Pass 2: SKIPPED — 0 new docs indexed, all {len(stats['conflicts']):,} conflicts "
            "are re-runs of the same source (guaranteed no-ops)"
        )
    elif args.update_duplicates and stats["conflicts"]:
        n_conf = len(stats["conflicts"])
        logger.info("=" * 70)
        logger.info(f"Pass 2: updating sources[] on {n_conf:,} duplicate documents ...")
        p2_stats = {"updated": 0, "failed": 0}
        p2_start = time.time()
        p2_next_log = 100_000
        for ok, info in helpers.parallel_bulk(
            es,
            _iter_conflict_updates_raw(files, args.dataset, str(data_dir),
                                       args.index_name, stats["conflicts"], args.chunk_size,
                                       max_rows=args.max_docs),
            thread_count=args.thread_count,
            queue_size=args.queue_size,
            chunk_size=args.batch_size,
            max_chunk_bytes=args.max_chunk_bytes * 1024 * 1024,
            raise_on_error=False,
        ):
            if ok:
                p2_stats["updated"] += 1
            else:
                p2_stats["failed"] += 1
                logger.warning(f"Failed conflict update: {info}")
            p2_done = p2_stats["updated"] + p2_stats["failed"]
            if p2_done >= p2_next_log:
                p2_elapsed = time.time() - p2_start
                p2_rate = p2_done / p2_elapsed if p2_elapsed > 0 else 0
                p2_pct = 100 * p2_done / n_conf if n_conf else 0
                p2_eta = f"  ETA={int((n_conf - p2_done) / p2_rate)}s" if p2_rate > 0 else ""
                logger.info(
                    f"[progress P2] {p2_done:,} / {n_conf:,} ({p2_pct:.1f}%)"
                    f"  updated={p2_stats['updated']:,}  rate={p2_rate:,.0f}/sec{p2_eta}"
                )
                p2_next_log += 100_000
        p2_dur = time.time() - p2_start
        logger.info(f"Pass 2 complete in {p2_dur:.1f}s: "
                    f"{p2_stats['updated']:,} updated, {p2_stats['failed']:,} failed")

    # ---- Pass 3: retry 429-rejected docs ----
    if stats["rejected"]:
        n_rej = len(stats["rejected"])
        logger.info("=" * 70)
        logger.info(f"Pass 3: retrying {n_rej:,} 429-rejected docs ...")
        p3_stats: dict = {"indexed": 0, "failed": 0, "still_rejected": set()}
        p3_start = time.time()
        p3_next_log = 100_000
        for ok, info in helpers.parallel_bulk(
            es,
            _iter_retry_create_raw(files, args.dataset, str(data_dir),
                                   args.index_name, args.chunk_size, stats["rejected"]),
            thread_count=args.thread_count,
            queue_size=args.queue_size,
            chunk_size=args.batch_size,
            max_chunk_bytes=args.max_chunk_bytes * 1024 * 1024,
            raise_on_error=False,
        ):
            if ok:
                p3_stats["indexed"] += 1
            else:
                action_info = info.get("create", info)
                err = action_info.get("error", {})
                if err.get("type") == "es_rejected_execution_exception":
                    doc_id = action_info.get("_id")
                    if doc_id:
                        p3_stats["still_rejected"].add(doc_id)
                elif err.get("type") == "version_conflict_engine_exception":
                    p3_stats["indexed"] += 1  # already exists, counts as success
                else:
                    p3_stats["failed"] += 1
                    logger.warning(f"Pass 3 failed doc: {info}")
            p3_done = p3_stats["indexed"] + p3_stats["failed"] + len(p3_stats["still_rejected"])
            if p3_done >= p3_next_log:
                p3_elapsed = time.time() - p3_start
                p3_rate = p3_done / p3_elapsed if p3_elapsed > 0 else 0
                p3_pct = 100 * p3_done / n_rej if n_rej else 0
                p3_eta = f"  ETA={int((n_rej - p3_done) / p3_rate)}s" if p3_rate > 0 else ""
                logger.info(
                    f"[progress P3] {p3_done:,} / {n_rej:,} ({p3_pct:.1f}%)"
                    f"  indexed={p3_stats['indexed']:,}  rate={p3_rate:,.0f}/sec{p3_eta}"
                )
                p3_next_log += 100_000
        p3_dur = time.time() - p3_start
        logger.info(
            f"Pass 3 complete in {p3_dur:.1f}s: "
            f"{p3_stats['indexed']:,} indexed, "
            f"{len(p3_stats['still_rejected']):,} still rejected, "
            f"{p3_stats['failed']:,} failed"
        )
        stats["rejected"] = p3_stats["still_rejected"]

    logger.info("=" * 70)

    if stats["failed"] > 0:
        logger.warning(f"{stats['failed']} docs had non-retriable indexing errors (bad data) — cannot recover")
    if stats["rejected"]:
        logger.error(
            f"{len(stats['rejected'])} docs still 429-rejected after Pass 3 — "
            "ES too overloaded; chunk marked failed for retry"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
