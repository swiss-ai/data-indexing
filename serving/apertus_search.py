#!/usr/bin/env python3
"""
Apertus Data Search — command-line client

Usage:
    apertus-search "query text" [options]
    apertus-search --list-datasets
    apertus-search --list-languages

Options:
    -n, --limit N           Number of results            (default: 5)
    -d, --dataset NAME      Filter by dataset (repeatable)
    -l, --language CODE     Filter by language code (repeatable)
    --date-from YYYY-MM-DD  Filter: from date
    --date-to   YYYY-MM-DD  Filter: to date
    --text-only             Print only full document text, one per line
    --json [FILE]           Save results as newline-delimited JSON
                            (auto-named under ./results/ if FILE omitted)
    --list-datasets         Dataset breakdown with doc counts
    --list-languages        Language breakdown with doc counts
    --es-host HOST          ES host  (auto-detected if omitted)
    --es-port PORT          ES port  (default: 9200)
    --index NAME            Index name  (default: global-pretraining)

ES host is auto-detected from $SCRATCH/es-cluster-<index>.info if present,
or from the ES_HOST environment variable. --es-host overrides both.
"""

import argparse, datetime, json, os, re, shutil, sys, textwrap
from urllib.request import urlopen, Request
from urllib.error import URLError


# ── Terminal helpers ──────────────────────────────────────────────────
_TTY = sys.stdout.isatty()
_W   = shutil.get_terminal_size((100, 24)).columns

def _c(code: str, t: str) -> str:
    return f"\033[{code}m{t}\033[0m" if _TTY else t

bold   = lambda t: _c("1",    str(t))
dim    = lambda t: _c("2",    str(t))
cyan   = lambda t: _c("96",   str(t))
yellow = lambda t: _c("93",   str(t))
green  = lambda t: _c("92",   str(t))
red    = lambda t: _c("91",   str(t))
blue   = lambda t: _c("94",   str(t))
mark   = lambda t: _c("1;33", str(t))   # bold yellow for highlights

def hr(char="─", width=None) -> str:
    return (char * (width or _W))

def _wrap(text, indent=4, width=None):
    w = (width or _W) - indent
    prefix = " " * indent
    # Preserve paragraph breaks but collapse runs of newlines
    paragraphs = re.split(r"\n{2,}", text.strip())
    out = []
    for para in paragraphs:
        collapsed = re.sub(r"\s+", " ", para).strip()
        if collapsed:
            out.append(textwrap.fill(collapsed, w, initial_indent=prefix,
                                     subsequent_indent=prefix))
    return "\n".join(out)


# ── Highlight <mark> tags ─────────────────────────────────────────────
def _highlight(snippet: str) -> str:
    return re.sub(r"<mark>(.*?)</mark>", lambda m: mark(m.group(1)), snippet)

def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


# ── ES helpers ────────────────────────────────────────────────────────
def _get(base, path):
    try:
        return json.loads(urlopen(base + "/" + path.lstrip("/"), timeout=30).read())
    except URLError as e:
        print(red("  Connection error: " + str(e)), file=sys.stderr)
        print(dim("  → " + base), file=sys.stderr)
        sys.exit(1)

def _post(base, path, body):
    req = Request(base + "/" + path.lstrip("/"),
                  data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urlopen(req, timeout=30).read())
    except URLError as e:
        print(red("  ES error: " + str(e)), file=sys.stderr)
        sys.exit(1)


# ── Auto-discover ES host ─────────────────────────────────────────────
def _discover_host(index):
    scratch = os.environ.get("SCRATCH",
              f"/iopsstor/scratch/cscs/{os.environ.get('USER', '')}")
    info = os.path.join(scratch, f"es-cluster-{index}.info")
    if os.path.isfile(info):
        for line in open(info):
            if line.startswith("ES_HOST="):
                return line.split("=", 1)[1].strip()
    return None


# ── Subcommands ───────────────────────────────────────────────────────
def cmd_list(base, index, field, label, colour):
    body = {"size": 0, "aggs": {
        "items": {"terms": {"field": field, "size": 300}}
    }}
    res = _post(base, f"{index}/_search", body)
    buckets = res["aggregations"]["items"]["buckets"]
    if not buckets:
        print(dim("  (no data)"))
        return

    grand = sum(b["doc_count"] for b in buckets)
    bar_w = min(30, _W - 40)

    print()
    print(f"  {bold(label)}  {dim(f'({grand:,} docs across {len(buckets)} values)')}")
    print()
    kw = max(len(b["key"]) for b in buckets)
    for b in sorted(buckets, key=lambda x: -x["doc_count"]):
        pct  = b["doc_count"] / grand * 100
        bars = int(pct / 100 * bar_w) or (1 if pct > 0 else 0)
        bar  = "█" * bars + dim("░" * (bar_w - bars))
        print(f"  {colour(b['key'].ljust(kw))}  "
              f"{b['doc_count']:>14,}  {pct:5.1f}%  {bar}")
    print()


def cmd_search(base, index, args):
    q = " ".join(args.query).strip()

    filters = []
    if args.dataset:
        filters.append({"terms": {"datasets": args.dataset}})
    if args.language:
        filters.append({"terms": {"language": args.language}})
    if args.date_from or args.date_to:
        dr: dict = {}
        if args.date_from: dr["gte"] = args.date_from
        if args.date_to:   dr["lte"] = args.date_to
        filters.append({"range": {"date": dr}})

    must   = ({"match": {"text": {"query": q, "operator": "and"}}} if q
               else {"match_all": {}})
    query  = {"bool": {"must": must, "filter": filters}} if filters else must

    body = {
        "query": query,
        "_source": ["datasets", "language", "date", "source_count", "sources", "text"],
        "size": args.limit,
    }
    if q:
        body["highlight"] = {"fields": {"text": {
            "fragment_size": 480, "number_of_fragments": 1,
            "pre_tags": ["<mark>"], "post_tags": ["</mark>"],
        }}}

    res  = _post(base, f"{index}/_search", body)
    hits = res["hits"]["hits"]
    total = res["hits"]["total"]["value"]

    if args.text_only:
        for hit in hits:
            print(hit["_source"].get("text", ""))
            print()
        return

    if args.json is not None:
        outdir = os.path.join(os.getcwd(), "results")
        os.makedirs(outdir, exist_ok=True)
        if args.json:
            outpath = os.path.join(outdir, args.json)
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", " ".join(args.query).lower()).strip("-")
            ts   = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            outpath = os.path.join(outdir, ("results-" + slug + "-" + ts + ".jsonl") if slug
                                           else ("results-" + ts + ".jsonl"))
        with open(outpath, "w") as f:
            for hit in hits:
                record = hit["_source"].copy()
                record["_id"]    = hit["_id"]
                record["_score"] = hit.get("_score")
                f.write(json.dumps(record) + "\n")
        print(f"\n  {green('✓')}  {len(hits)} results saved to {bold(outpath)}\n")
        return

    # ── Header ───────────────────────────────────────────────────────
    print()
    parts = []
    if q:
        parts.append('“' + bold(q) + '”')
    if args.dataset:
        parts.append(f"dataset: {cyan(', '.join(args.dataset))}")
    if args.language:
        parts.append(f"lang: {yellow(', '.join(args.language))}")
    query_desc = "  ".join(parts) if parts else dim("(all documents)")

    count_str = f"{total:,}" if total < 10_000 else f"{total:,}+"
    print(f"  {query_desc}")
    print(f"  {dim(count_str + ' results')}  {dim('·')}  "
          f"{dim('showing ' + str(len(hits)))}")
    print()

    if not hits:
        print(f"  {dim('No results.')}\n")
        return

    # ── Result cards ─────────────────────────────────────────────────
    for i, hit in enumerate(hits, 1):
        src      = hit["_source"]
        text     = src.get("text", "")
        raw_snip = (hit.get("highlight", {}).get("text") or [""])[0]
        snip_raw = raw_snip or text[:500]

        datasets = src.get("datasets", [])
        langs    = src.get("language", [])
        dates    = src.get("date") or []
        score    = hit.get("_score")
        doc_id   = hit["_id"]

        # Pull best URL / title / author from sources[]
        sources  = src.get("sources") or []
        url      = next((s.get("url") for s in sources if s.get("url")), None)
        title    = next((s.get("title") for s in sources if s.get("title")), None)
        author   = next((s.get("author") for s in sources if s.get("author")), None)

        # ── Card header ───────────────────────────────────────────
        ds_str   = cyan("  ·  ".join(datasets)) if datasets else dim("—")
        lang_str = yellow(", ".join(langs)) if langs else dim("—")
        date_str = dim(str(dates[0])[:7]) if dates else dim("—")   # YYYY-MM
        score_str = dim(f"score {score:.1f}") if score else ""

        meta_parts = [ds_str, lang_str, date_str]
        if score_str:
            meta_parts.append(score_str)

        print(f"  {bold(str(i))}  {'  ·  '.join(meta_parts)}")

        if title:
            print(f"     {bold(title)}" + (f"  {dim(author)}" if author else ""))

        print()

        # ── Snippet ───────────────────────────────────────────────
        # Collapse whitespace in the plain text for wrapping, then re-apply highlights
        source_text = raw_snip if raw_snip else text[:600]
        plain_collapsed = re.sub(r"\s+", " ", _plain(source_text)).strip()
        wrapped_lines   = textwrap.wrap(plain_collapsed, _W - 6) or [""]

        # Re-apply highlights to each wrapped line by looking for the marked terms
        marked_terms = re.findall(r"<mark>(.*?)</mark>", source_text)
        def reapply(line):
            for term in marked_terms:
                line = line.replace(term, mark(term))
            return line

        for line in wrapped_lines[:4]:
            print(f"     {reapply(line)}")

        print()

        # ── Footer (url / id) ─────────────────────────────────────
        if url:
            max_url = _W - 12
            display_url = url if len(url) <= max_url else url[:max_url - 1] + "…"
            print(f"     {dim('↗')}  {blue(display_url)}")
        short_id = doc_id[:24] + dim("…")
        print(f"     {dim('#')}  {dim(short_id)}")
        print()
        print(f"  {dim(hr('─', _W - 2))}")
        print()


# ── Main ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        prog="search.py",
        description="Apertus Data Search — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        add_help=False,
    )
    ap.add_argument("query", nargs="*")
    ap.add_argument("-n", "--limit",         type=int, default=5, metavar="N")
    ap.add_argument("-d", "--dataset",       action="append", default=[], metavar="NAME")
    ap.add_argument("-l", "--language",      action="append", default=[], metavar="CODE")
    ap.add_argument("--date-from",           metavar="YYYY-MM-DD")
    ap.add_argument("--date-to",             metavar="YYYY-MM-DD")
    ap.add_argument("--text-only",           action="store_true")
    ap.add_argument("--json",                nargs="?", const="", metavar="FILE")
    ap.add_argument("--list-datasets",       action="store_true")
    ap.add_argument("--list-languages",      action="store_true")
    ap.add_argument("--es-host",             default=None)
    ap.add_argument("--es-port",             default=os.environ.get("ES_PORT", "9200"))
    ap.add_argument("--index",               default=os.environ.get("ES_INDEX", "global-pretraining"))
    ap.add_argument("-h", "--help",          action="store_true")
    args = ap.parse_args()

    if args.help:
        print(__doc__)
        return

    # Auto-discover ES host
    es_host = (args.es_host
               or os.environ.get("ES_HOST")
               or _discover_host(args.index))
    if not es_host:
        print(red("  Error: ES host not found."), file=sys.stderr)
        print(dim("  Set ES_HOST, pass --es-host, or start the cluster with serving/launch.sh"),
              file=sys.stderr)
        sys.exit(1)

    base = f"http://{es_host}:{args.es_port}"

    # Health check + status line
    h = _get(base, "_cluster/health")
    status  = h.get("status", "?")
    n_nodes = h.get("number_of_nodes", "?")
    colour  = green if status == "green" else (yellow if status == "yellow" else red)
    print(dim(f"\n  {es_host}  {colour('●')} {status}  {n_nodes} nodes"))

    if args.list_datasets:
        cmd_list(base, args.index, "datasets", "Datasets", cyan)
    elif args.list_languages:
        cmd_list(base, args.index, "language", "Languages", yellow)
    elif args.query or args.dataset or args.language or args.date_from or args.date_to:
        cmd_search(base, args.index, args)
    else:
        print(f"\n  {bold('Apertus Data Search')}\n")
        print(f"  {dim('Usage:')}  apertus-search \"your query\"")
        print(f"  {dim('       ')}  apertus-search --list-datasets")
        print(f"  {dim('       ')}  apertus-search --help\n")

if __name__ == "__main__":
    main()
