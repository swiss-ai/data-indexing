# Apertus Pretraining Data Search

Full-text search over 4.85 billion documents from the Apertus pretraining corpus. Search by keyword, filter by dataset or language, and trace any document back to its source file.

- **`serving/`** — launch script, CLI search tool, and web UI
- **`indexing/`** — build a new index from scratch (see [indexing/README.md](indexing/README.md))

---

## Quickstart

### 1. Start the index

```bash
cd /path/to/data-indexing
./serving/launch.sh --es-only
```

This starts a 5-node Elasticsearch cluster on SLURM. If the index isn't on scratch, it automatically restores from the capstor snapshot.
**Options:**

| Flag | Description | Default |
|---|---|---|
| `--nodes N` | SLURM nodes for ES cluster | `5` |
| `--restore` | Force restore from snapshot (automatic when local data is absent) | — |
| `--snapshot-path P` | Snapshot repo path | `/capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index` |
| `--index NAME` | ES index name | `global-pretraining` |
| `--data-dir DIR` | ES data directory on scratch | `$SCRATCH/es-data-global-pretraining` |

### 2. Search from the command line

Install once:

```bash
uv tool install --editable /path/to/data-indexing/serving/
```

Then search from anywhere — the running cluster is auto-detected:

```bash
apertus-search "attention is all you need"
apertus-search "gradient descent" --dataset wikipedia --language eng
apertus-search "RLHF" -n 20
apertus-search --list-datasets
apertus-search --list-languages
apertus-search "instruction tuning" --text-only | head -100
apertus-search --help
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

## Smoke tests

Run against any live cluster to verify correctness:

```bash
pip install "elasticsearch>=7.0,<8.0"

python3 tests/smoke_test.py --es-host <es-host> --es-port 9200 --index global-pretraining
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
