#!/usr/bin/env python3
"""Apertus Data Search — FastAPI proxy for the ES pretraining index."""

import html
import logging
import os
import re
from typing import List, Optional

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
    es = es_client()

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

    if (date_from or date_to) and include_no_date:
        dr: dict = {}
        if date_from:
            dr["gte"] = date_from
        if date_to:
            dr["lte"] = date_to
        filters.append({
            "bool": {
                "should": [{"range": {"date": dr}}, no_date_clause],
                "minimum_should_match": 1,
            }
        })
    elif date_from or date_to:
        dr = {}
        if date_from:
            dr["gte"] = date_from
        if date_to:
            dr["lte"] = date_to
        filters.append({"range": {"date": dr}})

    q = q.strip()
    must = {"match": {"text": {"query": q, "operator": "and"}}} if q else {"match_all": {}}
    query = {"bool": {"must": must, "filter": filters}} if filters else must

    body: dict = {
        "query": query,
        "_source": ["datasets", "language", "date", "source_count", "sources", "text"],
        "from": min(page * size, 9990),
        "size": size,
    }

    if q:
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

    return {"total": res["hits"]["total"]["value"], "page": page, "size": size, "hits": hits}


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
