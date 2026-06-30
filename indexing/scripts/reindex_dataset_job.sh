#!/bin/bash
#SBATCH --partition=normal
#SBATCH --account=a145
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --job-name=reindex-dataset

# Full reindex of a single posttrain dataset:
#   1. delete_by_query  — remove all existing docs for this dataset
#   2. index_worker     — re-index from preprocessed parquet (pass 1 only)
#
# Required env vars (set via --export or environment):
#   DATASET_NAME   e.g. "alignment" or "sft-mixture"
#   PARQUET_DIR    path to preprocessed parquet shards
#   INDEX_NAME     ES index name
#
# Optional:
#   ES_INFO_FILE   path to es-cluster-*.info file

set -euo pipefail

SCRATCH="/iopsstor/scratch/cscs/${USER}"
VENV="${SCRATCH}/indexer-venv/bin/python3"
REPO_DIR="/users/alexandersternfeld/apertus-pretraining-data-indexing"
STATUS_DIR="${SCRATCH}/index-status/${INDEX_NAME}"
MANIFEST_BASE="${SCRATCH}/worker-manifests-${INDEX_NAME}"
ES_INFO_FILE="${ES_INFO_FILE:-${SCRATCH}/es-cluster-${INDEX_NAME}.info}"

ES_HOST=$(grep ^ES_HOST "$ES_INFO_FILE" | cut -d= -f2)
ES_PORT=$(grep ^ES_PORT "$ES_INFO_FILE" | cut -d= -f2)

echo "[reindex] =========================================="
echo "[reindex] Date:         $(date)"
echo "[reindex] Node:         ${SLURM_NODELIST:-local}"
echo "[reindex] Dataset:      ${DATASET_NAME}"
echo "[reindex] Parquet dir:  ${PARQUET_DIR}"
echo "[reindex] ES:           ${ES_HOST}:${ES_PORT}  index=${INDEX_NAME}"
echo "[reindex] =========================================="

# ── 1. Delete existing documents for this dataset ────────────────────────────
echo ""
echo "[reindex] Step 1: delete_by_query for dataset=${DATASET_NAME} ..."
RESPONSE=$("$VENV" - <<PYEOF
import json, sys, time
from elasticsearch import Elasticsearch

es = Elasticsearch([{"host": "${ES_HOST}", "port": ${ES_PORT}}], timeout=60)

# Submit async — delete_by_query on millions of docs can take many minutes
resp = es.delete_by_query(
    index="${INDEX_NAME}",
    body={"query": {"term": {"datasets": "${DATASET_NAME}"}}},
    wait_for_completion=False,
    conflicts="proceed",
)
task_id = resp["task"]
print(f"delete_by_query task: {task_id}", flush=True)

# Poll until done
while True:
    t = es.tasks.get(task_id=task_id)
    if t.get("completed"):
        result = t.get("response", t.get("error", {}))
        deleted = result.get("deleted", "?")
        print(json.dumps({"deleted": deleted, "failures": len(result.get("failures", []))}))
        break
    status = t.get("task", {}).get("status", {})
    print(f"  ... deleted {status.get('deleted',0):,} / {status.get('total',0):,}", flush=True)
    time.sleep(10)
PYEOF
)
echo "[reindex] delete_by_query result: ${RESPONSE}"

# ── 2. Remove any stale .done marker so the worker runs ──────────────────────
rm -f "${STATUS_DIR}/${DATASET_NAME}.done"

# ── 3. Write manifest and run index_worker inline ────────────────────────────
echo ""
echo "[reindex] Step 2: indexing from ${PARQUET_DIR} ..."
mkdir -p "$MANIFEST_BASE" "$STATUS_DIR"

MANIFEST="${MANIFEST_BASE}/reindex-${DATASET_NAME}.manifest"
echo "raw|${DATASET_NAME}|${PARQUET_DIR}||${DATASET_NAME}||" > "$MANIFEST"

WORK_MANIFEST="$MANIFEST" \
WORKER_ID="reindex-${DATASET_NAME}" \
UPDATE_DUPLICATES=false \
bash "${REPO_DIR}/scripts/index/index_worker.sh"

echo ""
echo "[reindex] Done at $(date)"
