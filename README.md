# Apertus Pretraining Data Search

Full-text search over 4.85 billion documents from the Apertus pretraining and posttraining corpus. Search by keyword, filter by dataset or language, and trace any document back to its source file.

- **`serving/`** — launch script, CLI search tool, and web UI
- **`indexing/`** — build a new index from scratch (see [indexing/README.md](indexing/README.md))

---

## Quickstart

### 1. Start the index

```bash
cd /path/to/data-indexing
./serving/launch.sh --es-only
```

This starts a 5-node Elasticsearch cluster on SLURM (~2-4 min). If the index isn't on scratch, it automatically restores from the capstor snapshot (~5 min) — no flags needed.

**Options:**

| Flag | Description | Default |
|---|---|---|
| `--nodes N` | SLURM nodes for ES cluster | `5` |
| `--restore` | Force restore from snapshot (automatic when local data is absent) | — |
| `--snapshot-path P` | Snapshot repo path | `/capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index` |
| `--index NAME` | ES index name | `apertus-data` |
| `--data-dir DIR` | ES data directory on scratch | `$SCRATCH/es-data-apertus-data` |

### 2. Search from the command line

Install once:

```bash
uv tool install --editable /path/to/data-indexing/serving/
```

The running cluster is auto-detected. Basic usage:

```bash
apertus-search "attention is all you need"
apertus-search "gradient descent" --dataset wikipedia --language eng
apertus-search "RLHF" -n 20
```

Explore the corpus:

```bash
apertus-search --list-datasets       # doc counts and % per dataset
apertus-search --list-languages      # doc counts and % per language
```

Save results as structured JSON — useful for downstream processing or large-scale extraction:

```bash
# auto-named file in ./results/
apertus-search "instruction tuning" -n 100 --json

# explicit filename in ./results/
apertus-search "instruction tuning" -n 100 --json tuning.jsonl
```

Each line is a JSON object with `text`, `datasets`, `language`, `date`, `source_count`, `sources[]`, `_id`, and `_score`. The `sources[]` array gives full provenance — original file path, URL, author, title, etc.

Pipe plain text for scripting:

```bash
apertus-search "machine learning" -n 1000 --text-only | wc -l
apertus-search "code generation" --dataset starcoder --text-only > docs.txt
```

To uninstall: `uv tool uninstall apertus-search`

---

## Web UI (alternative)

The web UI provides a browser-based search interface. Start it instead of (or alongside) the CLI:

```bash
./serving/launch.sh        # starts ES cluster + web server on port 8888
```

Since the server runs on a CSCS login node, access it from your laptop via an SSH tunnel:

```bash
# On your laptop — replace placeholders with what launch.sh prints:
ssh -N -L 8888:localhost:8888 <your-cscs-username>@<login-node>

# ProxyJump if behind a bastion:
ssh -N -L 8888:localhost:8888 -J <bastion> <user>@<login-node>
```

Then open `http://localhost:8888`. Keep the tunnel terminal open; Ctrl-C to close it.

---

## Advanced: raw ES queries

Once the cluster is running, the Elasticsearch HTTP API is directly accessible for arbitrary queries, aggregations, or large-scale extraction. Get the host from the info file:

```bash
ES_HOST=$(grep ^ES_HOST $SCRATCH/es-cluster-apertus-data.info | cut -d= -f2)
```

Full-text search with filters:

```bash
curl -s "http://$ES_HOST:9200/apertus-data/_search" \
  -H "Content-Type: application/json" -d '{
    "query": {
      "bool": {
        "must":   { "match": { "text": "attention mechanism" } },
        "filter": { "terms": { "datasets": ["wikipedia"] } }
      }
    },
    "size": 10
  }' | python3 -m json.tool
```

Aggregations — e.g. doc count per dataset per language:

```bash
curl -s "http://$ES_HOST:9200/apertus-data/_search" \
  -H "Content-Type: application/json" -d '{
    "size": 0,
    "aggs": {
      "by_dataset": {
        "terms": { "field": "datasets", "size": 50 },
        "aggs": {
          "by_language": { "terms": { "field": "language", "size": 20 } }
        }
      }
    }
  }' | python3 -m json.tool
```

Scroll API for bulk extraction (>10k docs):

```bash
# Open scroll
curl -s "http://$ES_HOST:9200/apertus-data/_search?scroll=2m" \
  -H "Content-Type: application/json" -d '{
    "query": { "term": { "datasets": "wikipedia" } },
    "size": 1000, "_source": ["text", "language", "sources"]
  }' > page1.json

# Continue with scroll_id
SCROLL_ID=$(python3 -c "import json,sys; print(json.load(open('page1.json'))['_scroll_id'])")
curl -s "http://$ES_HOST:9200/_search/scroll" \
  -H "Content-Type: application/json" \
  -d "{\"scroll\": \"2m\", \"scroll_id\": \"$SCROLL_ID\"}" > page2.json
```

The [Elasticsearch 7.17 query DSL docs](https://www.elastic.co/guide/en/elasticsearch/reference/7.17/query-dsl.html) cover the full range of query types (fuzzy, phrase, range, geo, more-like-this, etc.).

---

## Smoke tests

Run against any live cluster to verify correctness:

```bash
pip install "elasticsearch>=7.0,<8.0"

python3 tests/smoke_test.py --es-host <es-host> --es-port 9200 --index apertus-data
```

25 tests cover cluster health, doc counts, full-text search, language/date filtering, SHA-256 deduplication, and field correctness for every dataset type.

---

## Index at a glance

| | |
|---|---|
| Documents | 4,847,028,638 |
| On-disk size | ~17 TB |
| Datasets | 20 (web, Wikipedia, code, math, books, multilingual, alignment, …) |
| Snapshot | `/capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index` |

For details on building a new index, see [indexing/README.md](indexing/README.md).
