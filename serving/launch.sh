#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# Apertus Data Search — launch script
#
# Starts (or reuses) an ES cluster and optionally the web server.
#
# Usage:
#   ./serving/launch.sh [options]
#
# Options:
#   --index NAME        ES index name              (default: global-pretraining)
#   --nodes N           SLURM nodes for cluster    (default: 5)
#   --port PORT         Web server port            (default: 8888)
#   --data-dir DIR      ES data directory          (default: $SCRATCH/es-data-<INDEX>)
#   --no-web            Skip starting the web server
#   --restore           Force restore from capstor snapshot even if local
#                       data exists (automatic when local data is absent)
#   --snapshot-path P   Path to snapshot repo      (default: see below)
#   --es-only           Start ES cluster only, skip web server
#
# After this script returns, search via:
#   Browser  → SSH tunnel (instructions printed below)
#   Terminal → python3 serving/search.py "your query"
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────
INDEX_NAME="${INDEX_NAME:-global-pretraining}"
NODES="${NODES:-5}"
PORT="${PORT:-8888}"
SCRATCH="${SCRATCH:-/iopsstor/scratch/cscs/${USER}}"
SNAPSHOT_REPO_PATH="${SNAPSHOT_REPO_PATH:-/capstor/store/cscs/swissai/a145/es_indices_2026/apertus-index}"
SNAPSHOT_REPO_NAME="capstor-a145"
DO_WEB=true
DO_RESTORE=false
# ES_DATA_DIR default is set after arg parsing (depends on DO_RESTORE)
_ES_DATA_DIR_OVERRIDE=""

# ── Argument parsing ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --index)         INDEX_NAME="$2";            shift 2 ;;
        --nodes)         NODES="$2";                 shift 2 ;;
        --port)          PORT="$2";                  shift 2 ;;
        --data-dir)      _ES_DATA_DIR_OVERRIDE="$2"; shift 2 ;;
        --snapshot-path) SNAPSHOT_REPO_PATH="$2";    shift 2 ;;
        --no-web|--es-only) DO_WEB=false;            shift ;;
        --restore)       DO_RESTORE=true;            shift ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Use explicit --data-dir if given; otherwise, restore gets a fresh dir so it
# doesn't inherit stale voting config from a previous cluster's data directory.
if [[ -n "$_ES_DATA_DIR_OVERRIDE" ]]; then
    ES_DATA_DIR="$_ES_DATA_DIR_OVERRIDE"
elif [[ "$DO_RESTORE" == true ]]; then
    ES_DATA_DIR="${SCRATCH}/es-data-${INDEX_NAME}-restore"
else
    ES_DATA_DIR="${SCRATCH}/es-data-${INDEX_NAME}"
fi

INFO_FILE="${SCRATCH}/es-cluster-${INDEX_NAME}.info"

# ── Helper ────────────────────────────────────────────────────────────
W=68
hr()  { printf '%.0s─' $(seq 1 $W); echo; }
box() { printf "│ %-$((W-3))s│\n" "$1"; }

# ══════════════════════════════════════════════════════════════════════
# Step 1 — check if a cluster is already running
# ══════════════════════════════════════════════════════════════════════
CLUSTER_RUNNING=false
ES_HOST=""
ES_PORT=9200

if [[ -f "$INFO_FILE" ]]; then
    _host=$(grep ^ES_HOST "$INFO_FILE" | cut -d= -f2)
    _port=$(grep ^ES_PORT "$INFO_FILE" | cut -d= -f2)
    _job=$(grep ^CLUSTER_JOB_ID "$INFO_FILE" | cut -d= -f2 || echo "?")
    _started=$(grep ^STARTED_AT "$INFO_FILE" | cut -d= -f2 || echo "?")
    _nnodes=$(grep ^NUM_NODES "$INFO_FILE" | cut -d= -f2 || echo "?")
    if curl -sf "http://${_host}:${_port}/_cluster/health" >/dev/null 2>&1; then
        CLUSTER_RUNNING=true
        ES_HOST="$_host"
        ES_PORT="$_port"
        _docs=$(curl -sf "http://${ES_HOST}:${ES_PORT}/_cat/count/${INDEX_NAME}?h=count" 2>/dev/null || echo "?")
        _status=$(curl -sf "http://${ES_HOST}:${ES_PORT}/_cluster/health" 2>/dev/null \
                  | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
        echo ""
        hr
        box "  Cluster already running — reusing it"
        box ""
        box "  Host    : ${ES_HOST}:${ES_PORT}"
        box "  Index   : ${INDEX_NAME}"
        box "  Docs    : ${_docs}"
        box "  Status  : ${_status}  (${_nnodes} nodes)"
        box "  SLURM   : job ${_job}  started ${_started}"
        hr
        echo ""
    else
        echo ""
        echo "  Stale info file found (cluster not responding) — starting fresh."
        rm -f "$INFO_FILE"
        echo ""
    fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 2 — start cluster if needed
# ══════════════════════════════════════════════════════════════════════
if [[ "$CLUSTER_RUNNING" == false ]]; then
    # Auto-restore if scratch data dir is missing and no explicit --data-dir was given
    if [[ -z "$_ES_DATA_DIR_OVERRIDE" && ! -d "$ES_DATA_DIR" ]]; then
        echo ""
        echo "  No local data found at ${ES_DATA_DIR}"
        echo "  → Restoring from capstor snapshot automatically ..."
        echo ""
        DO_RESTORE=true
        ES_DATA_DIR="${SCRATCH}/es-data-${INDEX_NAME}-restore"
    fi

    echo ""
    echo "Submitting ES cluster SLURM job ($NODES nodes) ..."
    CLUSTER_JOB_ID=$(sbatch \
        --nodes="$NODES" \
        --export="ALL,INDEX_NAME=${INDEX_NAME},ES_DATA_DIR=${ES_DATA_DIR},REPO_DIR=${REPO_DIR}" \
        "${REPO_DIR}/indexing/scripts/start_es_cluster.sh" \
        | awk '{print $NF}')
    echo "  SLURM job ID: ${CLUSTER_JOB_ID}"
    echo ""
    echo "Waiting for cluster to become healthy ..."
    echo "(This usually takes 2-4 minutes. Ctrl-C to abort.)"
    echo ""

    WAIT_SECS=0
    until [[ -f "$INFO_FILE" ]]; do
        printf "\r  [%3ds] waiting for info file..." "$WAIT_SECS"
        sleep 5; WAIT_SECS=$((WAIT_SECS+5))
        # Check the job hasn't failed
        STATE=$(squeue -j "$CLUSTER_JOB_ID" -h -o '%T' 2>/dev/null || echo "UNKNOWN")
        if [[ -z "$STATE" ]]; then
            echo ""
            echo "ERROR: SLURM job $CLUSTER_JOB_ID is no longer in the queue."
            echo "Check: squeue -u $USER"
            echo "Log:   $(ls ${SCRATCH}/slurm-${CLUSTER_JOB_ID}* 2>/dev/null | head -1)"
            exit 1
        fi
    done
    echo ""

    ES_HOST=$(grep ^ES_HOST "$INFO_FILE" | cut -d= -f2)
    ES_PORT=$(grep ^ES_PORT "$INFO_FILE" | cut -d= -f2)

    # Wait for cluster to actually respond
    for i in $(seq 1 60); do
        if curl -sf "http://${ES_HOST}:${ES_PORT}/_cluster/health" >/dev/null 2>&1; then
            echo "✓ Cluster healthy at ${ES_HOST}:${ES_PORT}"
            break
        fi
        sleep 5
        (( i == 60 )) && { echo "ERROR: cluster never responded"; exit 1; }
    done

    # ── Restore from snapshot if requested ──────────────────────────
    if [[ "$DO_RESTORE" == true ]]; then
        echo ""
        echo "Restoring from latest snapshot in ${SNAPSHOT_REPO_PATH} ..."

        VENV="${SCRATCH}/indexer-venv/bin/python3"
        "$VENV" - <<PYEOF
import json, sys, time
from urllib.request import urlopen, Request

base = "http://${ES_HOST}:${ES_PORT}"
repo = "${SNAPSHOT_REPO_NAME}"
repo_path = "${SNAPSHOT_REPO_PATH}"
index = "${INDEX_NAME}"

# Register repo (idempotent)
req = Request(f"{base}/_snapshot/{repo}", method="PUT",
    data=json.dumps({"type":"fs","settings":{"location":repo_path,"compress":True}}).encode(),
    headers={"Content-Type":"application/json"})
print("Registered snapshot repo:", json.load(urlopen(req)))

# Relax disk watermarks so restore works even when filesystem is >85% full
req = Request(f"{base}/_cluster/settings", method="PUT",
    data=json.dumps({"transient": {
        "cluster.routing.allocation.disk.watermark.low": "95%",
        "cluster.routing.allocation.disk.watermark.high": "97%",
        "cluster.routing.allocation.disk.watermark.flood_stage": "99%",
        "cluster.routing.allocation.node_initial_primaries_recoveries": 200,
        "indices.recovery.max_bytes_per_sec": "10gb",
        "indices.recovery.max_concurrent_snapshot_file_downloads_per_node": 200,
        "indices.recovery.max_concurrent_snapshot_file_downloads": 20,
        "indices.recovery.max_concurrent_file_chunks": 5,
    }}).encode(),
    headers={"Content-Type":"application/json"})
json.load(urlopen(req))
print("Cluster settings updated (disk watermarks, recovery throttling removed)")

# Delete the index if it already exists (start_es_cluster.sh creates an empty one)
try:
    req = Request(f"{base}/{index}", method="DELETE")
    urlopen(req)
    print("Deleted pre-existing empty index")
except Exception:
    pass  # didn't exist, fine

# Find latest successful snapshot
snaps = json.load(urlopen(f"{base}/_snapshot/{repo}/_all"))["snapshots"]
success = [s for s in snaps if s["state"] == "SUCCESS"]
if not success:
    print("ERROR: no successful snapshots found in repo", file=sys.stderr); sys.exit(1)
latest = sorted(success, key=lambda s: s.get("start_time_in_millis",0))[-1]
snap_name = latest["snapshot"]
print("Restoring snapshot: " + snap_name)

# Start restore
req = Request(
    f"{base}/_snapshot/{repo}/{snap_name}/_restore?wait_for_completion=false",
    data=json.dumps({"indices": index, "include_global_state": False}).encode(),
    headers={"Content-Type":"application/json"}, method="POST")
print("Restore started:", json.load(urlopen(req)))

# Poll
print("Polling restore progress...")
t0 = time.time()
while True:
    r = json.load(urlopen(f"{base}/_cat/indices/{index}?h=health,status,docs.count&format=json"))
    if r:
        print(f"  [{int(time.time()-t0)}s] {r[0]}")
        if r[0].get("health") in ("green","yellow"):
            break
    time.sleep(30)
print("Restore complete.")
PYEOF
    fi
fi

# ── Print doc count ───────────────────────────────────────────────────
DOC_COUNT=$(curl -sf "http://${ES_HOST}:${ES_PORT}/_cat/count/${INDEX_NAME}?h=count" 2>/dev/null || echo "?")
hr
printf "  Index:     %s\n" "$INDEX_NAME"
printf "  ES host:   %s:%s\n" "$ES_HOST" "$ES_PORT"
printf "  Docs:      %s\n" "$DOC_COUNT"
hr

# ══════════════════════════════════════════════════════════════════════
# Step 3 — start web server
# ══════════════════════════════════════════════════════════════════════
if [[ "$DO_WEB" == true ]]; then
    echo ""
    echo "Starting web server on port ${PORT} ..."
    echo ""
    THIS_HOST="$(hostname -f 2>/dev/null || hostname)"
    hr
    echo "  PORT-FORWARDING (access from your laptop):"
    echo ""
    echo "    ssh -N -L ${PORT}:localhost:${PORT} ${USER}@${THIS_HOST}"
    echo ""
    echo "  Then open:  http://localhost:${PORT}"
    echo ""
    echo "  CLI SEARCH (on this machine):"
    echo ""
    echo "    ES_HOST=${ES_HOST} python3 ${REPO_DIR}/serving/search.py \"your query\""
    echo "    ES_HOST=${ES_HOST} python3 ${REPO_DIR}/serving/search.py --help"
    hr
    echo ""

    exec env \
        ES_HOST="$ES_HOST" \
        ES_PORT="$ES_PORT" \
        ES_INDEX="$INDEX_NAME" \
        PORT="$PORT" \
        "${SCRIPT_DIR}/website/run.sh"
else
    THIS_HOST="$(hostname -f 2>/dev/null || hostname)"
    hr
    echo "  ES cluster is ready. To start the web server:"
    echo ""
    echo "    ES_HOST=${ES_HOST} PORT=${PORT} ./serving/launch.sh"
    echo ""
    echo "  Or for CLI search:"
    echo ""
    echo "    ES_HOST=${ES_HOST} python3 ${REPO_DIR}/serving/search.py \"your query\""
    hr
fi
