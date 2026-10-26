#!/usr/bin/env python3
"""Apertus Data Search — FastAPI proxy for the ES pretraining index."""

import html
import logging
import os
import re
from typing import List, Literal, Optional

from elasticsearch import Elasticsearch
from fastapi import FastAPI, HTTPException, Query as QParam
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import apikeys

ES_HOST = os.environ.get("ES_HOST", "localhost")
ES_PORT = int(os.environ.get("ES_PORT", "9200"))
ES_INDEX = os.environ.get("ES_INDEX", "apertus-data")

# ── API-key mode ──────────────────────────────────────────────────────────────
# Off by default, so the browser-facing deployment behaves exactly as before and
# keeps its oauth2-proxy login. The separate API deployment sets this to true.
REQUIRE_API_KEY = os.environ.get("REQUIRE_API_KEY", "false").lower() == "true"
API_KEYS_FILE = os.environ.get("API_KEYS_FILE", "/etc/apertus-search/api-keys.json")
# A single request asking Elasticsearch for thousands of documents is what
# actually hurts a 4.85B-document index, so the ceiling is per-request rather
# than a rate limit.
MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", "100"))

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Apertus Data Search", docs_url=None, redoc_url=None)


@app.middleware("http")
async def require_api_key(request, call_next):
    """Gate every /api/ route when running in API mode.

    Deliberately a middleware rather than a per-route dependency: a route added
    later is protected without anyone having to remember to decorate it. The
    failure mode of forgetting is then a 401, not an open door onto the index.
    """
    path = request.url.path
    if REQUIRE_API_KEY and path.startswith("/api/"):
        presented = request.headers.get("x-api-key")
        if not presented:
            # Also accept the Bearer convention, which most HTTP clients and
            # API tools reach for first.
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                presented = auth[7:].strip()

        name = apikeys.verify(presented, API_KEYS_FILE)
        if not name:
            log.warning("rejected %s %s: %s api key",
                        request.method, path, "missing" if not presented else "invalid")
            return JSONResponse(
                status_code=401,
                content={"detail": "Valid API key required. Send it as the "
                                   "X-API-Key header (or Authorization: Bearer <key>)."},
            )
        # Attribution: which key ran which query, without logging the key itself.
        log.info("%s %s key=%s", request.method, path, name)

    return await call_next(request)


@app.get("/healthz")
def healthz():
    """Liveness for Kubernetes. Unauthenticated and deliberately uninformative —
    /api/health reports ES status and document counts, so it stays behind the key."""
    return {"status": "ok"}


def es_client() -> Elasticsearch:
    return Elasticsearch(
        [{"host": ES_HOST, "port": ES_PORT, "scheme": "http"}],
        timeout=30,
        max_retries=2,
        retry_on_timeout=True,
    )


# Phrase queries and exact totals over 4.85B documents can run for minutes. With the
# default client they would be cut at 30s and then re-sent twice, tripling the load for
# nothing. This client waits up to just under the ingress's 300s and never retries a
# timed-out query.
HEAVY_REQUEST_TIMEOUT = int(os.environ.get("HEAVY_REQUEST_TIMEOUT", "290"))


def es_heavy_client() -> Elasticsearch:
    return Elasticsearch(
        [{"host": ES_HOST, "port": ES_PORT, "scheme": "http"}],
        timeout=HEAVY_REQUEST_TIMEOUT,
        max_retries=0,
        retry_on_timeout=False,
    )


# ── Query building ────────────────────────────────────────────────────────────
# Matching runs on the analyzed `text` field (standard tokenizer, lowercase,
# asciifolding, html_strip; positions indexed), so "phrase" means the exact word
# sequence up to case, accents and punctuation.
Mode = Literal["all", "any", "phrase"]


def text_clause(q: str, mode: str, slop: int) -> dict:
    """all: every word, any order (the original behaviour). any: at least one word.
    phrase: the words in order, at most `slop` position moves apart."""
    if mode == "phrase":
        return {"match_phrase": {"text": {"query": q, "slop": slop}}}
    return {"match": {"text": {"query": q, "operator": "and" if mode == "all" else "or"}}}


def phrase_clause(p: str, slop: int) -> dict:
    return {"match_phrase": {"text": {"query": p, "slop": slop}}}


def build_filters(datasets, languages, date_from, date_to, include_no_lang, include_no_date) -> list:
    no_lang_clause = {"bool": {"must_not": {"exists": {"field": "language"}}}}
    no_date_clause = {"bool": {"must_not": {"exists": {"field": "date"}}}}

    filters = []
    if datasets:
        filters.append({"terms": {"datasets": datasets}})

    if languages and include_no_lang:
        filters.append({
            "bool": {
                "should": [{"terms": {"language": languages}}, no_lang_clause],
                "minimum_should_match": 1,
            }
        })
    elif languages:
        filters.append({"terms": {"language": languages}})

    if date_from or date_to:
        dr: dict = {}
        if date_from:
            dr["gte"] = date_from
        if date_to:
            dr["lte"] = date_to
        if include_no_date:
            filters.append({
                "bool": {
                    "should": [{"range": {"date": dr}}, no_date_clause],
                    "minimum_should_match": 1,
                }
            })
        else:
            filters.append({"range": {"date": dr}})
    return filters


def build_query(q, mode, slop, must, should, must_not, filters) -> dict:
    """`q` is matched per `mode`. The optional boolean lists are phrases (same `slop`):
    every `must` phrase, at least one `should` phrase, no `must_not` phrase."""
    must_clauses = ([text_clause(q, mode, slop)] if q else []) + [phrase_clause(p, slop) for p in must]
    should_clauses = [phrase_clause(p, slop) for p in should]
    must_not_clauses = [phrase_clause(p, slop) for p in must_not]

    if not (should_clauses or must_not_clauses or filters) and len(must_clauses) <= 1:
        # Same shape as before for a plain query, so UI scoring is unchanged.
        return must_clauses[0] if must_clauses else {"match_all": {}}

    query: dict = {"must": must_clauses or [{"match_all": {}}]}
    if should_clauses:
        query["should"] = should_clauses
        query["minimum_should_match"] = 1
    if must_not_clauses:
        query["must_not"] = must_not_clauses
    if filters:
        query["filter"] = filters
    return {"bool": query}


def _clean(values: List[str]) -> List[str]:
    return [v.strip() for v in values if v and v.strip()]


def sanitize_snippet(raw: str) -> str:
    """Escape HTML in snippet but preserve <mark> highlight tags from ES."""
    if not raw:
        return ""
    parts = re.split(r"(</?mark>)", raw)
    result = []
    for part in parts:
        if part in ("<mark>", "</mark>"):
            result.append(part)
        else:
            stripped = re.sub(r"<[^>]+>", " ", part)
            stripped = re.sub(r"\s+", " ", stripped).strip()
            result.append(html.escape(stripped))
    return "".join(result)


@app.get("/api/health")
def health():
    try:
        es = es_client()
        h = es.cluster.health(timeout="5s")
        try:
            count = int(es.cat.count(index=ES_INDEX, h="count", format="json")[0]["count"])
        except Exception:
            count = None
        return {"status": "ok", "es_status": h["status"], "doc_count": count}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.get("/api/aggregations")
def aggregations():
    # Full-index scan — can be slow while indexing is active (many small segments).
    try:
        es = es_client()
        res = es.search(
            index=ES_INDEX,
            body={
                "size": 0,
                "timeout": "90s",
                "aggs": {
                    "datasets": {"terms": {"field": "datasets", "size": 50}},
                    "languages": {"terms": {"field": "language", "size": 300}},
                },
            },
            request_timeout=100,
        )
        timed_out = res.get("timed_out", False)
        return {
            "datasets": [
                {"key": b["key"], "count": b["doc_count"]}
                for b in res["aggregations"]["datasets"]["buckets"]
            ],
            "languages": [
                {"key": b["key"], "count": b["doc_count"]}
                for b in res["aggregations"]["languages"]["buckets"]
            ],
            "total": res["hits"]["total"]["value"],
            "partial": timed_out,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/search")
def search(
    q: str = "",
    mode: Mode = "all",
    slop: int = QParam(default=0, ge=0),
    must: List[str] = QParam(default=[]),
    should: List[str] = QParam(default=[]),
    must_not: List[str] = QParam(default=[]),
    # Default totals stop counting at 10,000 (total_relation "gte"); exact_total counts
    # every match, which costs more on common queries. /api/count is cheaper still.
    exact_total: bool = False,
    datasets: List[str] = QParam(default=[]),
    languages: List[str] = QParam(default=[]),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_no_lang: bool = False,
    include_no_date: bool = False,
    page: int = QParam(default=0, ge=0),
    # Bounded so one caller cannot ask for 10,000 documents in a single request.
    # The UI only ever asks for a page's worth, so this is invisible to it.
    size: int = QParam(default=10, ge=1, le=MAX_PAGE_SIZE),
):
    q = q.strip()
    must, should, must_not = _clean(must), _clean(should), _clean(must_not)
    filters = build_filters(datasets, languages, date_from, date_to, include_no_lang, include_no_date)
    query = build_query(q, mode, slop, must, should, must_not, filters)
    # The original mode and no extras keeps the original client, so the UI is unaffected.
    heavy = exact_total or mode == "phrase" or bool(must or should or must_not)
    es = es_heavy_client() if heavy else es_client()

    body: dict = {
        "query": query,
        "_source": ["datasets", "language", "date", "source_count", "sources", "text"],
        "from": min(page * size, 9990),
        "size": size,
    }
    if exact_total:
        body["track_total_hits"] = True

    if q or must or should:
        body["highlight"] = {
            "fields": {
                "text": {
                    "fragment_size": 350,
                    "number_of_fragments": 1,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                }
            },
            "require_field_match": True,
        }

    try:
        res = es.search(index=ES_INDEX, body=body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    hits = []
    for hit in res["hits"]["hits"]:
        src = hit.get("_source", {})
        text = src.get("text", "")
        raw_snippet = (hit.get("highlight", {}).get("text") or [""])[0]
        snippet = sanitize_snippet(raw_snippet) if raw_snippet else html.escape(
            re.sub(r"<[^>]+>", " ", text[:400])
        )
        hits.append({
            "id": hit["_id"],
            "score": hit.get("_score"),
            "datasets": src.get("datasets", []),
            "language": src.get("language", []),
            "date": src.get("date", []),
            "source_count": src.get("source_count", 1),
            "sources": src.get("sources", []),
            "text": text,
            "snippet": snippet,
        })

    total = res["hits"]["total"]
    return {
        "total": total["value"],
        # "eq": exact. "gte": at least `total` (Elasticsearch stopped counting at 10,000).
        "total_relation": total.get("relation", "eq"),
        "page": page,
        "size": size,
        "hits": hits,
    }


@app.get("/api/count")
def count(
    q: str = "",
    mode: Mode = "all",
    slop: int = QParam(default=0, ge=0),
    must: List[str] = QParam(default=[]),
    should: List[str] = QParam(default=[]),
    must_not: List[str] = QParam(default=[]),
    datasets: List[str] = QParam(default=[]),
    languages: List[str] = QParam(default=[]),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_no_lang: bool = False,
    include_no_date: bool = False,
):
    """Exact number of matching documents (no ranking, no 10,000 cap). Same query
    parameters as /api/search."""
    q = q.strip()
    must, should, must_not = _clean(must), _clean(should), _clean(must_not)
    filters = build_filters(datasets, languages, date_from, date_to, include_no_lang, include_no_date)
    query = build_query(q, mode, slop, must, should, must_not, filters)
    try:
        res = es_heavy_client().count(index=ES_INDEX, body={"query": query})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"count": res["count"], "exact": True}


@app.get("/api/similar/{doc_id}")
def similar(doc_id: str):
    es = es_client()
    try:
        res = es.search(
            index=ES_INDEX,
            body={
                "query": {
                    "more_like_this": {
                        "fields": ["text"],
                        "like": [{"_index": ES_INDEX, "_id": doc_id}],
                        "min_term_freq": 1,
                        "min_doc_freq": 1,
                        "max_query_terms": 25,
                    }
                },
                "_source": ["datasets", "language", "date", "source_count", "sources", "text"],
                "size": 6,
                "highlight": {
                    "fields": {"text": {"fragment_size": 280, "number_of_fragments": 1}},
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                },
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    hits = []
    for hit in res["hits"]["hits"]:
        if hit["_id"] == doc_id:
            continue
        src = hit.get("_source", {})
        text = src.get("text", "")
        raw_snippet = (hit.get("highlight", {}).get("text") or [""])[0]
        snippet = sanitize_snippet(raw_snippet) if raw_snippet else html.escape(text[:280])
        hits.append({
            "id": hit["_id"],
            "datasets": src.get("datasets", []),
            "language": src.get("language", []),
            "date": src.get("date", []),
            "source_count": src.get("source_count", 1),
            "sources": src.get("sources", []),
            "text": text,
            "snippet": snippet,
        })
    return {"hits": hits}


BASE = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE, "images")
STATIC_DIR = os.path.join(BASE, "static")

# In API mode there is no browser UI to serve: the page's own fetches would get
# a 401, since it has no key. Serving only the API also keeps the public host's
# surface down to the documented endpoints.
if not REQUIRE_API_KEY:
    if os.path.isdir(IMAGES_DIR):
        app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
