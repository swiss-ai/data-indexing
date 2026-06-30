#!/usr/bin/env python3
"""
Integration tests for the global pretraining Elasticsearch index.

Runs ~20 queries that exercise full-text search, metadata filtering,
field correctness, and deduplication invariants.

Usage
-----
# Against the sample index (while ES is still up in a SLURM job):
python3 test_index.py --es-host <node> --es-port 9200 --index sample-raw-only

# With defaults (localhost:9200, index from $INDEX_NAME env var):
python3 test_index.py
"""

import argparse
import hashlib
import json
import os
import sys
from typing import Callable, List, Optional, Tuple

from elasticsearch import Elasticsearch


# ============================================================
# Test harness
# ============================================================

class Result(object):
    def __init__(self, name, passed, detail=""):
        self.name = name
        self.passed = passed
        self.detail = detail


class Suite:
    def __init__(self, es: Elasticsearch, index: str):
        self.es    = es
        self.index = index
        self.results: List[Result] = []

    def run(self, name, fn):
        # type: (str, Callable) -> None
        try:
            passed, detail = fn()
        except Exception as e:
            passed, detail = False, f"EXCEPTION: {e}"
        self.results.append(Result(name, passed, detail))
        icon = "✓" if passed else "✗"
        print(f"  [{icon}] {name}")
        if detail:
            for line in detail.splitlines():
                print(f"       {line}")

    def _search(self, body: dict) -> dict:
        return self.es.search(index=self.index, body=body)

    def _count(self, body: dict = None) -> int:
        q = {"query": body["query"]} if body else {}
        return self.es.count(index=self.index, body=q)["count"]

    def _agg(self, field_name: str, size: int = 50) -> dict:
        r = self._search({"size": 0, "aggs": {
            "by_field": {"terms": {"field": field_name, "size": size}}
        }})
        return {b["key"]: b["doc_count"]
                for b in r["aggregations"]["by_field"]["buckets"]}

    def summary(self) -> bool:
        n_pass = sum(1 for r in self.results if r.passed)
        n_fail = sum(1 for r in self.results if not r.passed)
        print()
        print("=" * 60)
        print(f"  {n_pass} passed  |  {n_fail} failed  |  {len(self.results)} total")
        print("=" * 60)
        if n_fail:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  ✗ {r.name}: {r.detail}")
        return n_fail == 0


# ============================================================
# Tests
# ============================================================

def run_all(s: Suite, expected_datasets: List[str]) -> None:

    # ---- 1. Cluster health ----
    def t_health():
        h = s.es.cluster.health(index=s.index)
        status = h["status"]
        ok = status in ("green", "yellow")
        return ok, f"status={status}"
    s.run("Cluster health is green or yellow", t_health)

    # ---- 2. Total doc count > 0 ----
    def t_total():
        n = s._count()
        return n > 0, f"{n:,} documents"
    s.run("Index is non-empty", t_total)

    # ---- 3. All expected datasets present in terms agg ----
    def t_datasets():
        found = s._agg("datasets")
        missing = [d for d in expected_datasets if d not in found]
        counts_str = ", ".join(f"{d}={found.get(d, 0)}" for d in expected_datasets)
        return len(missing) == 0, f"missing={missing}  counts: {counts_str}"
    s.run("All expected datasets have docs", t_datasets)

    # ---- 4. datasets field is an array (keyword multi-value) ----
    def t_datasets_array():
        # A doc with source_count > 1 should have multiple datasets if it spans datasets,
        # but at minimum every doc must have datasets as a non-null list.
        r = s._search({"size": 1, "query": {"match_all": {}}})
        src = r["hits"]["hits"][0]["_source"]
        ds = src.get("datasets")
        ok = isinstance(ds, list)
        return ok, f"type={type(ds).__name__}  value={ds}"
    s.run("datasets field is a list, not a scalar", t_datasets_array)

    # ---- 5. FW2: datasets field contains 'fineweb-2' ----
    def t_fw2_dataset_tag():
        r = s._search({"size": 1, "query": {"term": {"datasets": "fineweb-2"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no fineweb-2 docs found"
        src = hits[0]["_source"]
        ds = src.get("datasets", [])
        sources = src.get("sources", [])
        src0_ds = sources[0].get("dataset") if sources else None
        ok = "fineweb-2" in ds and src0_ds == "fineweb-2"
        return ok, f"datasets={ds}  sources[0].dataset={src0_ds}"
    s.run("FW2: datasets[] and sources[0].dataset both say 'fineweb-2'", t_fw2_dataset_tag)

    # ---- 6. FW2: date array non-empty (derived from sources[].date) ----
    def t_fw2_date():
        r = s._search({"size": 5, "query": {"term": {"datasets": "fineweb-2"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no fineweb-2 docs"
        docs_with_date = [h for h in hits if h["_source"].get("date")]
        return len(docs_with_date) > 0, f"{len(docs_with_date)}/{len(hits)} docs have date"
    s.run("FW2: date array is populated", t_fw2_date)

    # ---- 7. EuroParl: language_pair in sources[0] ----
    def t_europarl_language_pair():
        r = s._search({"size": 1, "query": {"term": {"datasets": "europarl"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no europarl docs"
        src = hits[0]["_source"]
        sources = src.get("sources", [])
        pair = sources[0].get("language_pair") if sources else None
        ok = pair is not None and "-" in str(pair)
        return ok, f"language_pair={pair}"
    s.run("EuroParl: sources[0].language_pair is set", t_europarl_language_pair)

    # ---- 8. EuroParl: language array has ≥ 2 entries ----
    def t_europarl_multilang():
        r = s._search({"size": 5, "query": {"term": {"datasets": "europarl"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no europarl docs"
        multi = [h for h in hits if len(h["_source"].get("language", [])) >= 2]
        return len(multi) > 0, f"{len(multi)}/{len(hits)} docs have ≥2 languages"
    s.run("EuroParl: language[] has multiple entries", t_europarl_multilang)

    # ---- 9. Gutenberg: sources[0].id matches filename:line pattern ----
    def t_gutenberg_id():
        r = s._search({"size": 3, "query": {"term": {"datasets": "gutenberg"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no gutenberg docs"
        ids = [h["_source"]["sources"][0].get("id", "") for h in hits if h["_source"].get("sources")]
        ok = all(".jsonl:" in str(i) for i in ids)
        return ok, f"sample ids: {ids}"
    s.run("Gutenberg: sources[0].id has synthetic filename:line format", t_gutenberg_id)

    # ---- 10. Canaries: sources[0].dataset == 'canaries' ----
    def t_canaries_source():
        r = s._search({"size": 3, "query": {"term": {"datasets": "canaries"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no canaries docs"
        sources = [h["_source"].get("sources", [{}])[0] for h in hits]
        ok = all(src.get("dataset") == "canaries" for src in sources)
        return ok, f"sample sources[0].dataset: {[s.get('dataset') for s in sources]}"
    s.run("Canaries: sources[0].dataset == 'canaries'", t_canaries_source)

    # ---- 11. Institutional-books: author and title in sources[0] ----
    def t_instbooks_metadata():
        r = s._search({"size": 5, "query": {"term": {"datasets": "institutional-books"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no institutional-books docs"
        with_author = [h for h in hits
                       if h["_source"].get("sources") and h["_source"]["sources"][0].get("author")]
        sample = [(h["_source"]["sources"][0].get("author"), h["_source"]["sources"][0].get("title"))
                  for h in with_author[:2]]
        return len(with_author) > 0, f"{len(with_author)}/{len(hits)} have author. samples={sample}"
    s.run("Institutional-books: sources[0] has author/title", t_instbooks_metadata)

    # ---- 12. Institutional-books: date is ISO format ----
    def t_instbooks_date():
        r = s._search({"size": 5, "query": {
            "bool": {"must": [
                {"term": {"datasets": "institutional-books"}},
                {"exists": {"field": "date"}},
            ]}
        }})
        hits = r["hits"]["hits"]
        with_date = [h for h in hits if h["_source"].get("date")]
        if not with_date:
            return False, "no docs with date"
        sample = with_date[0]["_source"]["date"]
        # dates should look like YYYY-MM-DD
        ok = all("-" in str(d) for d in sample)
        return ok, f"sample date={sample}"
    s.run("Institutional-books: date is ISO format", t_instbooks_date)

    # ---- 13. FLAN: language is English ----
    def t_flan_language():
        r = s._search({"size": 5, "query": {"term": {"datasets": "flan"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no flan docs"
        langs = [h["_source"].get("language", []) for h in hits]
        ok = all("eng" in l for l in langs)
        return ok, f"languages: {langs}"
    s.run("FLAN: all docs have language='eng'", t_flan_language)

    # ---- 14. Full-text search returns results ----
    def t_fts():
        r = s._search({"size": 3, "query": {"match": {"text": "the"}}})
        n = r["hits"]["total"]["value"]
        return n > 0, f"{n:,} hits for 'the'"
    s.run("Full-text search for 'the' returns results", t_fts)

    # ---- 15. Language keyword filter works ----
    def t_lang_filter():
        n_eng = s._count({"query": {"term": {"language": "eng"}}})
        n_bg  = s._count({"query": {"term": {"language": "bg"}}})
        ok = n_eng > 0 and n_bg > 0
        return ok, f"docs with language=eng: {n_eng:,}  language=bg: {n_bg:,}"
    s.run("Language keyword filter returns correct subsets", t_lang_filter)

    # ---- 16. Dataset filter is exclusive ----
    def t_dataset_filter_exclusive():
        # Docs tagged 'gutenberg' should NOT be tagged 'canaries'
        r = s._search({"size": 5, "query": {"term": {"datasets": "gutenberg"}}})
        hits = r["hits"]["hits"]
        crossover = [h for h in hits if "canaries" in h["_source"].get("datasets", [])]
        return len(crossover) == 0, f"{len(crossover)} gutenberg docs also tagged as canaries"
    s.run("Dataset filter: gutenberg docs are not tagged as canaries", t_dataset_filter_exclusive)

    # ---- 17. source_count ≥ 1 on every sampled doc ----
    def t_source_count():
        r = s._search({"size": 20, "query": {"match_all": {}}})
        bad = [h["_id"] for h in r["hits"]["hits"]
               if h["_source"].get("source_count", 0) < 1]
        return len(bad) == 0, f"{len(bad)} docs with source_count < 1"
    s.run("source_count ≥ 1 on all sampled docs", t_source_count)

    # ---- 18. Dedup: source_count > 1 docs exist (europarl has many) ----
    def t_dedup_exists():
        n = s._count({"query": {"range": {"source_count": {"gt": 1}}}})
        return n > 0, f"{n:,} docs with source_count > 1"
    s.run("Dedup: docs with source_count > 1 exist", t_dedup_exists)

    # ---- 19. SHA256 dedup invariant: compute hash of a known text, find exactly 1 doc ----
    def t_sha256_dedup():
        # Grab any doc and re-derive its expected _id
        r = s._search({"size": 1, "query": {"term": {"datasets": "europarl"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no europarl docs to test"
        doc_id = hits[0]["_id"]
        text   = hits[0]["_source"]["text"]
        expected_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ok = doc_id == expected_id
        return ok, f"_id={doc_id[:16]}…  sha256(text)={expected_id[:16]}…  match={ok}"
    s.run("SHA256 dedup: _id == sha256(text)", t_sha256_dedup)

    # ---- 20. No doc has an empty text field ----
    def t_no_empty_text():
        # ES can't match empty string directly; use must_not exists trick
        n = s._count({"query": {"bool": {"must_not": {"exists": {"field": "text"}}}}})
        return n == 0, f"{n} docs with missing text field"
    s.run("No docs have a missing text field", t_no_empty_text)

    # ---- 21. sources array is non-empty on all sampled docs ----
    def t_sources_non_empty():
        r = s._search({"size": 20, "query": {"match_all": {}}})
        bad = [h["_id"] for h in r["hits"]["hits"]
               if not h["_source"].get("sources")]
        return len(bad) == 0, f"{len(bad)} docs with empty sources[]"
    s.run("sources[] is non-empty on all sampled docs", t_sources_non_empty)

    # ---- 22. sources[0].dataset matches datasets[] ----
    def t_sources_dataset_consistent():
        r = s._search({"size": 20, "query": {"match_all": {}}})
        bad = []
        for h in r["hits"]["hits"]:
            src = h["_source"]
            declared = set(src.get("datasets", []))
            from_sources = {s.get("dataset") for s in src.get("sources", []) if s.get("dataset")}
            if from_sources and not from_sources.issubset(declared):
                bad.append((h["_id"][:12], declared, from_sources))
        return len(bad) == 0, f"{len(bad)} docs where sources[].dataset not in datasets[]  examples={bad[:2]}"
    s.run("sources[].dataset values are all in datasets[]", t_sources_dataset_consistent)

    # ---- 23. EuroBlocks: language field is empty (multilingual, not English-only) ----
    def t_euroblocks_no_language():
        r = s._search({"size": 10, "query": {"term": {"datasets": "euroblocks"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no euroblocks docs"
        with_lang = [h for h in hits if h["_source"].get("language")]
        return len(with_lang) == 0, (
            f"{len(with_lang)}/{len(hits)} docs unexpectedly have language set "
            f"(expected empty — euroblocks is multilingual)"
        )
    s.run("EuroBlocks: language[] is empty (multilingual dataset)", t_euroblocks_no_language)

    # ---- 24. SFT-mixture: sources[0].id has shard:row format ----
    def t_sft_id_format():
        r = s._search({"size": 5, "query": {"term": {"datasets": "sft-mixture"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no sft-mixture docs"
        ids = [h["_source"].get("sources", [{}])[0].get("id", "") for h in hits]
        ok = all((".parquet:" in str(i) and "sft-merged-" in str(i)) for i in ids)
        return ok, f"sample ids: {ids[:3]}"
    s.run("SFT-mixture: sources[0].id is 'sft-merged-NNNN.parquet:ROW'", t_sft_id_format)

    # ---- 25. Alignment: sources[0].id has shard:row format ----
    def t_alignment_id_format():
        r = s._search({"size": 5, "query": {"term": {"datasets": "alignment"}}})
        hits = r["hits"]["hits"]
        if not hits:
            return False, "no alignment docs"
        ids = [h["_source"].get("sources", [{}])[0].get("id", "") for h in hits]
        ok = all((".parquet:" in str(i) and "alignment-merged-" in str(i)) for i in ids)
        return ok, f"sample ids: {ids[:3]}"
    s.run("Alignment: sources[0].id is 'alignment-merged-NNNN.parquet:ROW'", t_alignment_id_format)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--es-host",   default=os.environ.get("MASTER_NODE", "localhost"))
    parser.add_argument("--es-port",   type=int, default=int(os.environ.get("ES_PORT", "9200")))
    parser.add_argument("--index",     default=os.environ.get("INDEX_NAME", "global-pretraining"))
    parser.add_argument("--datasets",  nargs="+",
                        default=[
                            "fineweb-1", "fineweb-edu", "dclm", "fineweb-2",
                            "starcoder", "paradocs", "europarl", "wikipedia",
                            "stackv2-edu", "megamath-web", "finemath", "infiwebmath",
                            "starcoder-extras", "sft-mixture", "flan", "alignment",
                            "euroblocks", "institutional-books", "canaries", "gutenberg",
                        ],
                        help="Datasets expected in the index")
    args = parser.parse_args()

    es = Elasticsearch(
        [{"host": args.es_host, "port": args.es_port}],
        timeout=30, retry_on_timeout=True,
    )
    try:
        info = es.info()
        print(f"Connected to ES {info['version']['number']} "
              f"at {args.es_host}:{args.es_port}  index={args.index}")
    except Exception as e:
        print(f"[ERROR] Cannot connect to ES: {e}")
        sys.exit(1)

    if not es.indices.exists(index=args.index):
        print(f"[ERROR] Index '{args.index}' does not exist")
        sys.exit(1)

    es.indices.refresh(index=args.index)
    print(f"\nRunning tests against '{args.index}':\n")

    s = Suite(es, args.index)
    run_all(s, args.datasets)
    ok = s.summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
