# Indexing

Build and snapshot an Elasticsearch index from parquet/JSONL datasets on a SLURM cluster.

## Architecture

```
Parquet/JSONL datasets
  └─► index_raw.py / index_aggregated.py   (parallel bulk-indexing, SHA256 dedup)
        └─► Elasticsearch 7.17 index        (SHA256 _id, BM25 full-text search)
              └─► snapshot_job.sh           (persist to shared filesystem)

ES cluster: multi-node via SLURM  (start_es_cluster.sh + start_es_node.sh)
Orchestrator: submit_index_jobs.sh submits cluster + all worker jobs
Workers: index_worker.sh processes a manifest of chunks sequentially
```

Documents are deduplicated by SHA-256 of text. Each unique text is stored once; its `sources[]` array records every occurrence across all datasets.

---

## 1. Set up Python venv

Run once from any compute node (the venv is shared across all worker jobs via the shared filesystem):

```bash
SCRATCH=/iopsstor/scratch/cscs/$USER    # adjust to your site
python3 -m venv "$SCRATCH/indexer-venv"
"$SCRATCH/indexer-venv/bin/pip" install -r indexing/environment/requirements.txt
```

## 2. Key environment variables

All paths are configurable. The most important ones for `submit_index_jobs.sh`:

| Variable | Description | Default |
|---|---|---|
| `INDEX_NAME` | ES index name | *(required)* |
| `ES_NODES` | Number of ES cluster nodes | `30` |
| `NUM_WORKERS_PER_JOB` | Concurrent worker SLURM jobs | `5` |
| `GLOBAL_MERGE_DIR` | English-web-dedup parquet dir (Spark output) | *(skip if unset)* |
| `FW2_AGG_DIR` | FineWeb-2 aggregated parquet dir | *(skip if unset)* |
| `CAPSTOR_BASE` | Base path for first-pass raw datasets | `/capstor/store/cscs/swissai/infra01/datasets/swiss-ai` |
| `INFRA01_BASE` | Base path for second-pass datasets (Wikipedia, math, code) | `/capstor/store/cscs/swissai/infra01` |
| `POSTTRAIN_PRE_BASE` | Base path for post-training datasets (alignment, SFT) | `/capstor/store/cscs/swissai/a145/es_indices_2026/posttrain_preprocessing` |
| `SNAPSHOT_REPO_PATH` | Filesystem path for ES snapshots | `/capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index` |
| `SCRATCH` | Scratch filesystem root | `/iopsstor/scratch/cscs/$USER` |
| `ES_ENV` | Container environment name | `es-python` |

## 3. Submit the pipeline

```bash
export INDEX_NAME=my-index
export ES_NODES=30
export NUM_WORKERS_PER_JOB=5
export GLOBAL_MERGE_DIR=/path/to/english-web-dedup   # optional
export FW2_AGG_DIR=/path/to/fineweb-2-aggregated     # optional

# Preview what would be submitted
./indexing/scripts/submit_index_jobs.sh --dry-run

# Submit for real
./indexing/scripts/submit_index_jobs.sh
```

This submits:
1. One ES cluster job (`start_es_cluster.sh`) — starts the cluster and writes a discovery info file
2. `NUM_WORKERS_PER_JOB` worker jobs (`index_worker.sh`) — each processes a manifest of chunks

Workers wait for the cluster info file before starting. Submitting again after a cluster timeout is safe — chunks with `.done` markers are skipped automatically.

## 4. Monitor progress

```bash
STATUS_DIR="$SCRATCH/index-status/$INDEX_NAME"

# Chunk completion
echo "Done:   $(ls $STATUS_DIR/*.done 2>/dev/null | wc -l)"
echo "Failed: $(ls $STATUS_DIR/*.failed 2>/dev/null | wc -l)"

# SLURM jobs
squeue -u $USER

# Worker logs (progress lines logged every 500k docs)
tail -f $SCRATCH/slurm-index-worker-*-$INDEX_NAME-*.out

# Cluster log (heap, queue depth every 2 min)
tail -f $SCRATCH/slurm-es-cluster-$INDEX_NAME-*.out
```

## 5. Resume after cluster timeout

ES data persists in `$SCRATCH/es-data-$INDEX_NAME/`. Simply resubmit:

```bash
# If cluster is still running, reuse it
CLUSTER_JOB_ID=<existing-job-id> ./indexing/scripts/submit_index_jobs.sh

# Otherwise start a fresh cluster (same data dir)
./indexing/scripts/submit_index_jobs.sh
```

**Node count constraint:** always restart with at least as many nodes as were used when the data was written. Each SLURM node writes shard data to `node-{PROCID}/` under `ES_DATA_DIR`. Fewer nodes means those shard directories are unreachable. After a snapshot + restore to a new cluster this constraint disappears.

## 6. Post-indexing: force merge

After all chunks are done, consolidate ES segments for faster search:

```bash
ES_HOST=$(grep ^ES_HOST $SCRATCH/es-cluster-$INDEX_NAME.info | cut -d= -f2)
curl -X POST "http://$ES_HOST:9200/$INDEX_NAME/_forcemerge?max_num_segments=5"
```

This is blocking and can take hours for a billion-document index. Do it once before serving.

## 7. Snapshot

A snapshot job is automatically chained after all workers. To trigger one manually:

```bash
sbatch \
  --dependency=after:<cluster-job-id> \
  --export=ALL,INDEX_NAME=$INDEX_NAME,REPO_PATH=$SNAPSHOT_REPO_PATH \
  indexing/scripts/snapshot_job.sh
```

---

## Dataset support

`index_raw.py` — datasets indexed without prior Spark deduplication:

| `--dataset` value | Format | Key metadata |
|---|---|---|
| `europarl`, `paradocs` | Parquet | `language_pair` from directory name |
| `flan` | Parquet | English assumed |
| `euroblocks` | Parquet | Multilingual; no language field — `language` left empty |
| `institutional-books` | Parquet | `author`, `title`, `date`, `language` |
| `wikipedia` | Parquet | `language` (iso639-3 column) |
| `gutenberg` | JSONL | `language` |
| `canaries` | JSONL.gz | — |
| `stackv2-edu` | JSONL.gz | `url`, `date`, `score` |
| `finemath`, `infiwebmath`, `megamath-web` | Parquet | `language`, `url`, `score` |
| `starcoder`, `starcoder-extras` | Parquet | `repo_name`, quality score |
| `alignment`, `sft-mixture` | Parquet | `id` = `{shard_filename}:{row_within_shard}`, e.g. `sft-merged-0007.parquet:23104` |

`index_aggregated.py` — Spark-deduplicated parquet (has `sha256` column pre-computed):
- FineWeb-1 + FineWeb-edu + DCLM (global merge)
- FineWeb-2 (per-language aggregated)

---

## ES index schema

| Field | Type | Description |
|---|---|---|
| `text` | full-text | Document content, analyzed with `web_content_analyzer` (html-strip → tokenize → lowercase → ascii-fold) |
| `datasets` | keyword[] | Source dataset names; filterable |
| `language` | keyword[] | ISO 639 language codes; filterable |
| `date` | date[] | Web crawl or publication dates; range-filterable |
| `source_count` | integer | Times this text appeared before deduplication |
| `sources` | object (stored, not indexed) | Full provenance: `dataset`, `id`, `url`, `date`, `language_score`, `folder_path`, `author`, `title`, `repo_name`, … |
