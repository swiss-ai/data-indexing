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
#   --index NAME        ES index name              (default: apertus-data)
#   --nodes N           SLURM nodes for cluster    (default: 5)
#   --port PORT         Web server port            (default: 8888)
#   --data-dir DIR      ES data directory          (default: $SCRATCH/es-data-<INDEX>)
#   --no-web            Skip starting the web server
#   --restore           Force restore from capstor snapshot even if local
#                       data exists (automatic when local data is absent)
#   --snapshot-path P   Path to snapshot repo      (default: see below)
#   --es-only           Start ES cluster only, skip web server (non-blocking)
#
# After this script returns, search via:
#   Browser  → SSH tunnel (instructions printed below)
#   Terminal → apertus-search "your query"
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────
INDEX_NAME="${INDEX_NAME:-apertus-data}"
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
LOG_FILE="${SCRATCH}/es-launch-${INDEX_NAME}.log"

# ── Helper ────────────────────────────────────────────────────────────
W=68
hr()  { printf '%.0s─' $(seq 1 $W); echo; }
box() { printf "│ %-$((W-3))s│\n" "$1"; }

_slurm_error() {
    local job_id="$1"
    local log
    log=$(find "$SCRATCH" -maxdepth 1 -name "slurm-${job_id}*" 2>/dev/null | head -1)
    if [[ -n "$log" ]]; then
        echo "  Last lines of ${log}:"
        tail -20 "$log" | sed 's/^/    /'
    else
        echo "  (no SLURM log found — try: scontrol show job ${job_id})"
    fi
}

# ── Shared restore function (runs Python inline) ──────────────────────
_run_restore() {
    local _host="$1" _port="$2"
    echo "Restoring from latest snapshot in ${SNAPSHOT_REPO_PATH} ..."
    python3 -u - <<PYEOF
import json, sys, time
from urllib.request import urlopen, Request

base  = "http://${_host}:${_port}"
repo  = "${SNAPSHOT_REPO_NAME}"
path  = "${SNAPSHOT_REPO_PATH}"
index = "${INDEX_NAME}"

# Register snapshot repo (idempotent)
req = Request(base + "/_snapshot/" + repo, method="PUT",
    data=json.dumps({"type": "fs", "settings": {"location": path, "compress": True}}).encode(),
    headers={"Content-Type": "application/json"})
print("Registered snapshot repo:", json.load(urlopen(req)))

# Relax disk watermarks and speed up recovery
req = Request(base + "/_cluster/settings", method="PUT",
    data=json.dumps({"transient": {
        "cluster.routing.allocation.disk.watermark.low":        "95%",
        "cluster.routing.allocation.disk.watermark.high":       "97%",
        "cluster.routing.allocation.disk.watermark.flood_stage":"99%",
        "cluster.routing.allocation.node_initial_primaries_recoveries": 200,
        "indices.recovery.max_bytes_per_sec": "10240mb",
    }}).encode(),
    headers={"Content-Type": "application/json"})
json.load(urlopen(req))
print("Cluster settings updated")

# Delete empty index that start_es_cluster.sh may have created
try:
    req = Request(base + "/" + index, method="DELETE")
    urlopen(req)
    print("Deleted pre-existing empty index")
except Exception:
    pass

# Find latest successful snapshot
snaps   = json.load(urlopen(base + "/_snapshot/" + repo + "/_all"))["snapshots"]
success = [s for s in snaps if s["state"] == "SUCCESS"]
if not success:
    print("ERROR: no successful snapshots found in repo", file=sys.stderr)
    sys.exit(1)
latest    = sorted(success, key=lambda s: s.get("start_time_in_millis", 0))[-1]
snap_name = latest["snapshot"]
snap_indices = latest.get("indices", [])
print("Restoring snapshot: " + snap_name + "  (contains: " + str(snap_indices) + ")")

# Build restore body — handle index name mismatch via rename if needed
body = {"include_global_state": False}
if index in snap_indices:
    body["indices"] = index
elif len(snap_indices) == 1:
    src = snap_indices[0]
    body["indices"] = src
    body["rename_pattern"] = src
    body["rename_replacement"] = index
    print("Renaming snapshot index " + src + " -> " + index)
    # Also delete the old name in case it exists
    try:
        req2 = Request(base + "/" + src, method="DELETE")
        urlopen(req2)
    except Exception:
        pass
else:
    print("WARNING: snapshot indices " + str(snap_indices) + " don't match target " + index + "; restoring all")

# Kick off restore (async)
req = Request(
    base + "/_snapshot/" + repo + "/" + snap_name + "/_restore?wait_for_completion=false",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
print("Restore started:", json.load(urlopen(req)))

# Poll until green/yellow
print("Polling restore progress...")
t0 = time.time()
while True:
    r = json.load(urlopen(base + "/_cat/indices/" + index + "?h=health,status,docs.count&format=json"))
    if r:
        h = r[0].get("health", "?")
        s = r[0].get("status", "?")
        d = r[0].get("docs.count", "?")
        elapsed = int(time.time() - t0)
        print("  [" + str(elapsed) + "s] health=" + h + " status=" + s + " docs=" + str(d))
        if h in ("green", "yellow"):
            break
    time.sleep(30)
print("Restore complete.")
PYEOF
}

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

    # For restore, always wipe the data dir so stale cluster state
    # (voting configs, node IDs) from a previous run can't block election.
    if [[ "$DO_RESTORE" == true && -d "$ES_DATA_DIR" ]]; then
        echo "  Removing stale restore data dir: ${ES_DATA_DIR}"
        rm -rf "$ES_DATA_DIR"
    fi

    echo ""
    echo "Submitting ES cluster SLURM job ($NODES nodes) ..."
    CLUSTER_JOB_ID=$(sbatch \
        --nodes="$NODES" \
        --export="ALL,INDEX_NAME=${INDEX_NAME},ES_DATA_DIR=${ES_DATA_DIR},REPO_DIR=${REPO_DIR}" \
        "${REPO_DIR}/indexing/scripts/start_es_cluster.sh" \
        | awk '{print $NF}')
    echo "  SLURM job ID: ${CLUSTER_JOB_ID}"

    # ── shared wait-for-cluster logic (used by both modes) ────────────
    # Prints PENDING/RUNNING status, then counts time until info file appears.
    _wait_for_cluster() {
        local job_id="$1" info="$2"
        local YELLOW='\033[1;33m' GREEN='\033[0;32m' RESET='\033[0m'
        local last_state="" wait_secs=0

        while [[ ! -f "$info" ]]; do
            STATE=$(squeue -j "$job_id" -h -o '%T' 2>/dev/null || true)
            if [[ -z "$STATE" ]]; then
                printf "\n"
                echo "ERROR: SLURM job $job_id exited unexpectedly."
                _slurm_error "$job_id"
                return 1
            fi

            if [[ "$STATE" == "PENDING" ]]; then
                if [[ "$last_state" != "PENDING" ]]; then
                    printf "\r${YELLOW}  ◌ PENDING${RESET}  job ${job_id} waiting for nodes...                    "
                    last_state="PENDING"
                fi
            elif [[ "$STATE" == "RUNNING" ]]; then
                if [[ "$last_state" != "RUNNING" ]]; then
                    printf "\n${GREEN}  ● RUNNING${RESET}  job ${job_id}\n"
                    last_state="RUNNING"
                    wait_secs=0
                fi
                printf "\r  ${GREEN}[%3ds]${RESET} starting up, waiting for cluster..." "$wait_secs"
                wait_secs=$((wait_secs+5))
            fi
            sleep 5
        done
        printf "\n"
    }

    # ── --es-only: non-blocking — background the health check + restore ──
    if [[ "$DO_WEB" == false ]]; then
        echo ""
        echo "  Progress tracking:"
        echo ""
        echo "    tail -f ${LOG_FILE}"
        echo ""

        _bg_info="$INFO_FILE"
        _bg_job="$CLUSTER_JOB_ID"
        _bg_index="$INDEX_NAME"
        _bg_do_restore="$DO_RESTORE"

        (
            echo "[$(date '+%T')] Job ${_bg_job} submitted — waiting for SLURM..."
            WAIT=0
            last_state=""
            while [[ ! -f "$_bg_info" ]]; do
                sleep 5; WAIT=$((WAIT+5))
                STATE=$(squeue -j "$_bg_job" -h -o '%T' 2>/dev/null || true)
                if [[ -z "$STATE" ]]; then
                    echo "ERROR: SLURM job $_bg_job exited unexpectedly."
                    _slurm_error "$_bg_job"
                    exit 1
                fi
                if [[ "$STATE" != "$last_state" ]]; then
                    echo "[$(date '+%T')] Job state: ${STATE}"
                    last_state="$STATE"
                fi
                [[ "$STATE" == "RUNNING" ]] && echo "  [${WAIT}s] cluster starting..."
            done

            ES_HOST=$(grep ^ES_HOST "$_bg_info" | cut -d= -f2)
            ES_PORT=$(grep ^ES_PORT "$_bg_info" | cut -d= -f2)
            echo "[$(date '+%T')] Info file written — waiting for HTTP..."

            for i in $(seq 1 60); do
                if curl -sf "http://${ES_HOST}:${ES_PORT}/_cluster/health" >/dev/null 2>&1; then
                    echo "[$(date '+%T')] ✓ Cluster healthy at ${ES_HOST}:${ES_PORT}"
                    break
                fi
                sleep 5
                (( i == 60 )) && { echo "ERROR: cluster never responded"; exit 1; }
            done

            if [[ "$_bg_do_restore" == true ]]; then
                _run_restore "$ES_HOST" "$ES_PORT"
            fi

            echo ""
            echo "[$(date '+%T')] ✓ Ready — apertus-search \"your query\""
        ) >> "$LOG_FILE" 2>&1 &
        disown
        exit 0
    fi

    # ── Blocking mode (web server follows) ────────────────────────────
    echo ""
    _wait_for_cluster "$CLUSTER_JOB_ID" "$INFO_FILE" || exit 1

    ES_HOST=$(grep ^ES_HOST "$INFO_FILE" | cut -d= -f2)
    ES_PORT=$(grep ^ES_PORT "$INFO_FILE" | cut -d= -f2)

    for i in $(seq 1 60); do
        if curl -sf "http://${ES_HOST}:${ES_PORT}/_cluster/health" >/dev/null 2>&1; then
            break
        fi
        sleep 5
        (( i == 60 )) && { echo "ERROR: cluster never responded"; exit 1; }
    done

    GREEN='\033[0;32m'; RESET='\033[0m'
    printf "${GREEN}  ✓ Cluster online${RESET}  ${ES_HOST}:${ES_PORT}\n\n"

    if [[ "$DO_RESTORE" == true ]]; then
        _run_restore "$ES_HOST" "$ES_PORT"
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
    echo "    apertus-search \"your query\""
    echo "    apertus-search --help"
    hr
    echo ""

    exec env \
        ES_HOST="$ES_HOST" \
        ES_PORT="$ES_PORT" \
        ES_INDEX="$INDEX_NAME" \
        PORT="$PORT" \
        "${SCRIPT_DIR}/website/run.sh"
fi
