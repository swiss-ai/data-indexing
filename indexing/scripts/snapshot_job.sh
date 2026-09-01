#!/bin/bash
#SBATCH --partition=normal
#SBATCH --account=infra01
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --job-name=es-snapshot

# ============================================================
# Take a filesystem snapshot of an ES index to capstor infra01.
#
# Depends on the ES cluster being up (path.repo must be set in
# start_es_node.sh — it is).  Submit with:
#   --dependency=after:<CLUSTER_JOB_ID>
# and optionally after all indexing workers are done:
#   --dependency=afterany:<W1>:<W2>:...
#
# Required env vars:
#   INDEX_NAME     - ES index name (e.g. global-pretraining)
#
# Optional env vars:
#   SNAPSHOT_NAME  - name for the snapshot (default: snapshot-<date>)
#   REPO_PATH      - filesystem path for the snapshot repo
#                    (default: /capstor/store/cscs/swissai/infra01/es_indices/apertus-index)
#   INFO_WAIT_SECS - seconds to wait for cluster info file (default: 3600)
# ============================================================

set -euo pipefail

INDEX_NAME="${INDEX_NAME:?INDEX_NAME must be set}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-snapshot-$(date +%Y%m%d-%H%M%S)}"
REPO_PATH="${REPO_PATH:-/capstor/store/cscs/swissai/infra01/es_indices/apertus-index}"
REPO_NAME="capstor-infra01"
INFO_WAIT_SECS="${INFO_WAIT_SECS:-3600}"

SCRATCH="/iopsstor/scratch/cscs/${USER}"
INFO_FILE="${SCRATCH}/es-cluster-${INDEX_NAME}.info"

echo "[snapshot] =============================================="
echo "[snapshot] Date:          $(date)"
echo "[snapshot] Node:          ${SLURM_NODELIST:-local}"
echo "[snapshot] INDEX_NAME:    $INDEX_NAME"
echo "[snapshot] SNAPSHOT_NAME: $SNAPSHOT_NAME"
echo "[snapshot] REPO_PATH:     $REPO_PATH"
echo "[snapshot] INFO_FILE:     $INFO_FILE"
echo "[snapshot] =============================================="

# ---- Wait for cluster info file ----
echo "[snapshot] Waiting for cluster info file (up to ${INFO_WAIT_SECS}s)..."
waited=0
until [[ -f "$INFO_FILE" ]]; do
    (( waited >= INFO_WAIT_SECS )) && { echo "[ERROR] Timed out waiting for $INFO_FILE"; exit 1; }
    sleep 10; (( waited += 10 ))
done
source "$INFO_FILE"
ES_HOST="${ES_HOST:?}"; ES_PORT="${ES_PORT:?}"
ES_URL="http://${ES_HOST}:${ES_PORT}"
echo "[snapshot] ES cluster: $ES_URL (found info file after ${waited}s)"

# ---- Wait for ES health ----
echo "[snapshot] Waiting for ES health..."
for (( i=0; i<600; i++ )); do
    health=$(curl -s "${ES_URL}/_cluster/health" 2>/dev/null || true)
    if [[ -n "$health" ]]; then
        status=$(echo "$health" | grep -o '"status":"[^"]*"' | grep -o '[a-z]*"$' | tr -d '"' || true)
        nodes=$(echo "$health" | grep -o '"number_of_nodes":[0-9]*' | grep -o '[0-9]*' || echo 0)
        if [[ "$status" == "green" || "$status" == "yellow" ]]; then
            echo "[snapshot] ES healthy: status=${status} nodes=${nodes}"
            break
        fi
    fi
    (( i == 599 )) && { echo "[ERROR] ES not healthy after 6000s"; exit 1; }
    sleep 10
done

# ---- Register snapshot repository ----
echo "[snapshot] Registering snapshot repository '${REPO_NAME}' at ${REPO_PATH} ..."
reg=$(curl -s -w "\n%{http_code}" -X PUT "${ES_URL}/_snapshot/${REPO_NAME}" \
    -H 'Content-Type: application/json' \
    -d "{\"type\":\"fs\",\"settings\":{\"location\":\"${REPO_PATH}\",\"compress\":true}}")
reg_body=$(echo "$reg" | head -n -1)
reg_code=$(echo "$reg" | tail -n 1)
echo "[snapshot] Register response (${reg_code}): ${reg_body}"
if [[ "$reg_code" != "200" ]]; then
    echo "[ERROR] Failed to register snapshot repository (HTTP ${reg_code})"
    exit 1
fi

# ---- Verify repo ----
echo "[snapshot] Verifying repository..."
curl -s -X POST "${ES_URL}/_snapshot/${REPO_NAME}/_verify" | python3 -c "
import sys, json
r = json.load(sys.stdin)
nodes = r.get('nodes', {})
print(f'[snapshot] Verified on {len(nodes)} node(s)')
for nid, info in nodes.items():
    print(f'  {info.get(\"name\", nid)}: {info.get(\"repository\", \"ok\")}')
" 2>/dev/null || echo "[snapshot] Verify parse failed (continuing)"

# ---- Take snapshot ----
echo "[snapshot] Starting snapshot '${SNAPSHOT_NAME}' of index '${INDEX_NAME}'..."
snap=$(curl -s -w "\n%{http_code}" -X PUT \
    "${ES_URL}/_snapshot/${REPO_NAME}/${SNAPSHOT_NAME}?wait_for_completion=false" \
    -H 'Content-Type: application/json' \
    -d "{\"indices\":\"${INDEX_NAME}\",\"include_global_state\":false}")
snap_body=$(echo "$snap" | head -n -1)
snap_code=$(echo "$snap" | tail -n 1)
echo "[snapshot] Snapshot initiated (HTTP ${snap_code}): ${snap_body}"
if [[ "$snap_code" != "200" ]]; then
    echo "[ERROR] Failed to initiate snapshot (HTTP ${snap_code})"
    exit 1
fi

# ---- Poll until complete ----
echo "[snapshot] Polling snapshot status (this can take hours for a large index)..."
while true; do
    status_json=$(curl -s "${ES_URL}/_snapshot/${REPO_NAME}/${SNAPSHOT_NAME}" 2>/dev/null || true)
    state=$(echo "$status_json" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)
    snaps = r.get('snapshots', [])
    if snaps:
        s = snaps[0]
        state = s.get('state','UNKNOWN')
        shards = s.get('shards', {})
        total = shards.get('total', 0)
        done  = shards.get('successful', 0)
        failed= shards.get('failed', 0)
        print(f'{state}|{done}/{total} shards|{failed} failed')
    else:
        print('NO_SNAPSHOT|?|?')
except Exception as e:
    print(f'PARSE_ERROR|{e}|0')
" 2>/dev/null || echo "POLL_ERROR|curl failed|0")
    snap_state=$(echo "$state" | cut -d'|' -f1)
    snap_progress=$(echo "$state" | cut -d'|' -f2)
    snap_failed=$(echo "$state" | cut -d'|' -f3)
    echo "[snapshot] $(date '+%H:%M:%S')  state=${snap_state}  progress=${snap_progress}  failed=${snap_failed}"
    case "$snap_state" in
        SUCCESS)
            echo "[snapshot] ✓ Snapshot '${SNAPSHOT_NAME}' completed successfully!"
            echo "[snapshot] Location: ${REPO_PATH}"
            break ;;
        FAILED|PARTIAL)
            echo "[ERROR] Snapshot ended with state=${snap_state}"
            exit 1 ;;
        IN_PROGRESS|STARTED)
            sleep 60 ;;
        *)
            echo "[snapshot] Unknown state '${snap_state}', waiting..."
            sleep 60 ;;
    esac
done

echo "[snapshot] Done at $(date)"
