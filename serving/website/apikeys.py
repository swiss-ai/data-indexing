#!/usr/bin/env python3
"""API-key authentication for the programmatic query endpoint.

Keys are never stored in plaintext. The Kubernetes Secret holds only SHA-256
hashes, so a leaked Secret — or an etcd dump — yields nothing a caller can use.
Issue a key with:

    python3 serving/website/make_api_key.py alice-cli

The key file is re-read whenever its mtime changes rather than being cached for
the process lifetime. Kubernetes updates a mounted Secret in place (typically
within a minute), so adding or revoking a key takes effect without restarting
pods — which matters because a redeploy here means re-cloning the repo and
re-running pip in the init containers.
"""

import hashlib
import json
import os
import secrets
import threading
from datetime import date
from typing import List, Optional

_lock = threading.Lock()
_cache: dict = {"mtime": None, "keys": []}


def _parse(raw: dict) -> List[dict]:
    keys = raw.get("keys", []) if isinstance(raw, dict) else raw
    out = []
    for k in keys:
        digest = (k.get("hash") or "").strip().lower()
        if not digest:
            continue  # entry with no hash can never match; skip rather than fail the whole file
        out.append({
            "name": k.get("name", "unnamed"),
            "hash": digest,
            "expires": k.get("expires"),  # optional "YYYY-MM-DD"
        })
    return out


def load_keys(path: str) -> List[dict]:
    """Return the current key set, reloading only when the file changes.

    On a malformed file we keep serving the last good set instead of locking
    everyone out — a bad edit to the Secret should not take the API down.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []

    with _lock:
        if _cache["mtime"] != mtime:
            try:
                with open(path) as f:
                    _cache["keys"] = _parse(json.load(f))
                _cache["mtime"] = mtime
            except Exception:
                return _cache["keys"]
        return _cache["keys"]


def verify(presented: Optional[str], path: str) -> Optional[str]:
    """Return the name of the matching key, or None if there is no valid match.

    Compares hashes with compare_digest so that a wrong key cannot be recovered
    by timing how long the comparison takes.
    """
    if not presented:
        return None

    digest = hashlib.sha256(presented.encode("utf-8")).hexdigest()
    today = date.today().isoformat()

    for k in load_keys(path):
        if secrets.compare_digest(digest, k["hash"]):
            expires = k.get("expires")
            # ISO-8601 dates compare correctly as strings, so no parsing needed.
            if expires and expires < today:
                return None
            return k["name"]
    return None
