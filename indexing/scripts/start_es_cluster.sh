#!/bin/bash
#SBATCH --partition=normal
#SBATCH --time=12:00:00
#SBATCH --nodes=30
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=256
#SBATCH --mem=800G
#SBATCH --job-name=es-cluster

# ============================================================
# Persistent multi-node Elasticsearch cluster for the pretraining index.
#
# Starts all ES nodes, waits for cluster health, creates the index
# (if it doesn't exist), then writes an info file so worker jobs
# can discover the cluster address.  Stays alive for 12 h.
#
# Override #SBATCH --nodes at submission time:
#   sbatch --nodes=40 start_es_cluster.sh
#
# IMPORTANT: always use at least as many nodes as the last run that
# wrote data to ES_DATA_DIR.  Each node writes shard data to
# node-{SLURM_PROCID}/ under ES_DATA_DIR.  Missing nodes mean
# inaccessible shards.  After a snapshot+restore this restriction
# goes away.
#
# Required env vars:
#   INDEX_NAME          - ES index name (e.g. global-pretraining)
#
# Optional env vars:
#   ES_DATA_DIR         - persistent ES data path (default: $SCRATCH/es-data-$INDEX_NAME)
#   NUM_SHARDS          - number of primary shards (default: 50)
#   ES_HEAP             - JVM heap flags (default: -Xms200g -Xmx200g)
#   ES_ENV              - container environment name (default: es-python)
#   SNAPSHOT_REPO_PATH  - filesystem path for ES snapshot repository
#                         (default: /capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index)
# ============================================================

set -euo pipefail

INDEX_NAME="${INDEX_NAME:?INDEX_NAME must be set}"
SCRATCH="/iopsstor/scratch/cscs/${USER}"
ES_DATA_DIR="${ES_DATA_DIR:-${SCRATCH}/es-data-${INDEX_NAME}}"
NUM_SHARDS="${NUM_SHARDS:-50}"
ES_PORT=9200
ES_ENV="${ES_ENV:-es-python}"
ES_HEAP="${ES_HEAP:--Xms200g -Xmx200g}"
NUM_NODES="${SLURM_NNODES:?}"
SNAPSHOT_REPO_PATH="${SNAPSHOT_REPO_PATH:-/capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index}"

REPO_DIR="${REPO_DIR:-}"
if [[ -z "$REPO_DIR" ]]; then
    _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ "$_SCRIPT_DIR" != /var/spool* ]] && REPO_DIR="$(cd "${_SCRIPT_DIR}/../.." && pwd)"
fi
[[ -z "$REPO_DIR" ]] && { echo "[ERROR] REPO_DIR not set"; exit 1; }

ES_NODE_SCRIPT="${REPO_DIR}/indexing/scripts/start_es_node.sh"
INFO_FILE="${SCRATCH}/es-cluster-${INDEX_NAME}.info"

mapfile -t NODES < <(scontrol show hostnames "$SLURM_NODELIST")
MASTER_NODE="${NODES[0]}"
SEED_HOSTS=$(printf "%s:9300\n" "${NODES[@]}" | paste -sd,)
CLUSTER_NAME="fw-es-${INDEX_NAME}"
BASE_LOGS="${SCRATCH}/es-logs-${INDEX_NAME}-${SLURM_JOB_ID}"

echo "[INFO] =============================================="
echo "[INFO] ES Cluster — ${NUM_NODES} nodes, 12h"
echo "[INFO] Date:         $(date)"
echo "[INFO] Nodes:        $SLURM_NODELIST"
echo "[INFO] Master node:  $MASTER_NODE"
echo "[INFO] INDEX_NAME:   $INDEX_NAME"
echo "[INFO] NUM_SHARDS:   $NUM_SHARDS"
echo "[INFO] ES_DATA_DIR:  $ES_DATA_DIR"
echo "[INFO] INFO_FILE:    $INFO_FILE"
echo "[INFO] =============================================="

ulimit -n 65536
mkdir -p "$ES_DATA_DIR" "$BASE_LOGS"

export ES_BASE_DATA="$ES_DATA_DIR"
export ES_BASE_LOGS="$BASE_LOGS"
export ES_SEED_HOSTS="$SEED_HOSTS"
export ES_MASTER_NAME="es-node-0"
export ES_PORT="$ES_PORT"
export ES_HEAP="$ES_HEAP"
export CLUSTER_NAME="$CLUSTER_NAME"
export ES_NUM_NODES="$NUM_NODES"
export SNAPSHOT_REPO_PATH="$SNAPSHOT_REPO_PATH"

echo "[INFO] Starting Elasticsearch on ${NUM_NODES} node(s)..."
export HOME="${HOME:-/users/${USER}}"
srun --ntasks="$NUM_NODES" --ntasks-per-node=1 \
     --environment="$ES_ENV" \
     "$ES_NODE_SCRIPT" &
SRUN_ES_PID=$!

stop_es() {
    echo "[INFO] Stopping ES cluster (srun PID $SRUN_ES_PID)..."
    kill "$SRUN_ES_PID" 2>/dev/null || true
    wait "$SRUN_ES_PID" 2>/dev/null || true
    rm -f "$INFO_FILE"
}
trap stop_es EXIT

ES_URL="http://${MASTER_NODE}:${ES_PORT}"
max_wait=120
for (( i=0; i<max_wait; i++ )); do
    ! kill -0 "$SRUN_ES_PID" 2>/dev/null && { echo "[ERROR] ES died during startup"; exit 1; }
    health=$(curl -s "${ES_URL}/_cluster/health" 2>/dev/null || true)
    if [[ -n "$health" ]]; then
        actual=$(echo "$health" | grep -o '"number_of_nodes":[0-9]*' | grep -o '[0-9]*' || echo 0)
        if (( actual == NUM_NODES )); then
            echo "[INFO] ES cluster ready: ${actual}/${NUM_NODES} nodes"
            break
        fi
        echo "[INFO] ES up, waiting for all nodes... (${actual}/${NUM_NODES})"
    fi
    (( i == max_wait-1 )) && { echo "[ERROR] ES did not reach ${NUM_NODES} nodes within $((max_wait*10))s"; exit 1; }
    sleep 10
done

# ---- Write info file so launch.sh / workers can discover the cluster ----
# Written here (before index creation) so the cluster stays usable even if
# the venv is absent — e.g. when launch.sh will restore the index from snapshot.
cat > "$INFO_FILE" <<EOF
ES_HOST=${MASTER_NODE}
ES_PORT=${ES_PORT}
ES_DATA_DIR=${ES_DATA_DIR}
INDEX_NAME=${INDEX_NAME}
NUM_NODES=${NUM_NODES}
CLUSTER_JOB_ID=${SLURM_JOB_ID}
STARTED_AT=$(date -Iseconds)
EOF
echo "[INFO] Info file written: $INFO_FILE"

# ---- Create index if it doesn't exist (requires indexer-venv) ----
VENV_DIR="${SCRATCH}/indexer-venv"
PYTHON_BIN="${VENV_DIR}/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "[INFO] Indexer venv not found at $VENV_DIR — skipping index creation."
    echo "[INFO] If you need to create the index (not restoring from snapshot), run:"
    echo "  python3.11 -m venv $VENV_DIR"
    echo "  $VENV_DIR/bin/pip install -r $REPO_DIR/indexing/environment/requirements.txt"
else

"$PYTHON_BIN" - <<PYEOF
from elasticsearch import Elasticsearch
import sys

es = Elasticsearch([{"host": "${MASTER_NODE}", "port": ${ES_PORT}}], timeout=120)
index = "${INDEX_NAME}"

if es.indices.exists(index=index):
    try:
        count = es.count(index=index)["count"]
        print(f"[INFO] Index '{index}' already exists with {count:,} docs — keeping as-is")
    except Exception as e:
        print(f"[INFO] Index '{index}' already exists — keeping as-is (count unavailable during shard recovery: {e})")
else:
    mapping = {
        "settings": {
            "number_of_shards": ${NUM_SHARDS},
            "number_of_replicas": 0,
            "refresh_interval": "30s",
            "analysis": {"analyzer": {"web_content_analyzer": {
                "type": "custom",
                "char_filter": ["html_strip"],
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding"],
            }}},
            "index.translog.durability": "async",
            "index.translog.sync_interval": "60s",
        },
        "mappings": {
            "dynamic": "false",
            "properties": {
                "text":         {"type": "text", "analyzer": "web_content_analyzer",
                                 "index_options": "positions", "norms": True},
                "language":     {"type": "keyword"},
                "date":         {"type": "date",
                                 "format": "strict_date_optional_time||epoch_millis"},
                "source_count": {"type": "integer"},
                "datasets":     {"type": "keyword"},
                "sources":      {"type": "object", "enabled": False},
            },
        },
    }
    es.indices.create(index=index, body=mapping)
    print(f"[INFO] Index '{index}' created ({${NUM_SHARDS}} shards, 0 replicas)")
PYEOF

fi  # end venv check

echo "[INFO] Cluster is live — worker jobs can now index data."

# ---- Background monitoring loop (every 2 min) ----
monitor_es() {
    local url="http://${MASTER_NODE}:${ES_PORT}"
    while kill -0 "$SRUN_ES_PID" 2>/dev/null; do
        sleep 120
        ts=$(date '+%H:%M:%S')
        stats=$(curl -s "${url}/_nodes/stats/indices,jvm,thread_pool" 2>/dev/null || true)
        [[ -z "$stats" ]] && { echo "[MONITOR ${ts}] ES unreachable"; continue; }
        index_current=$(echo "$stats" | grep -o '"index_current":[0-9]*' | awk -F: '{s+=$2} END {print s}')
        heap_pct=$(echo     "$stats" | grep -o '"heap_used_percent":[0-9]*' | awk -F: '{if($2>m)m=$2} END {print m}')
        bulk_queue=$(echo   "$stats" | grep -o '"queue":[0-9]*'          | awk -F: '{s+=$2} END {print s}')
        bulk_rejected=$(echo "$stats"| grep -o '"rejected":[0-9]*'       | awk -F: '{s+=$2} END {print s}')
        echo "[MONITOR ${ts}] heap_max=${heap_pct:-?}%  indexing_active=${index_current:-0}  bulk_queue=${bulk_queue:-0}  bulk_rejected=${bulk_rejected:-0}"
    done
}
monitor_es &
MONITOR_PID=$!

stop_es() {
    echo "[INFO] Stopping ES cluster (srun PID $SRUN_ES_PID)..."
    kill "$MONITOR_PID" 2>/dev/null || true
    kill "$SRUN_ES_PID" 2>/dev/null || true
    wait "$SRUN_ES_PID" 2>/dev/null || true
    rm -f "$INFO_FILE"
}
trap stop_es EXIT

echo "[INFO] Monitoring ES load every 120s — watch heap_max, bulk_queue, bulk_rejected in log."
echo "[INFO] Sleeping until job wall time expires..."
wait "$SRUN_ES_PID"
