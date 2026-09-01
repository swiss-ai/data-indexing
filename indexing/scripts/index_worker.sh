#!/bin/bash
#SBATCH --partition=normal
#SBATCH --account=infra01
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=256
#SBATCH --mem=800G
#SBATCH --job-name=index-worker

# ============================================================
# Worker-pool feeder: processes a list of indexing tasks
# sequentially from a manifest file.  Submit N of these
# (default 5) instead of one job per chunk — this bounds
# concurrent connections to the ES cluster and avoids
# overwhelming it.
#
# Required env vars:
#   INDEX_NAME       - must match the cluster job's INDEX_NAME
#   WORK_MANIFEST    - path to pipe-delimited file with one task per line:
#                      TYPE|CHUNK_ID|DATA_DIR|DATA_DIRS_FILE|DATASET_NAME|FILE_RANGE_START|FILE_RANGE_END
#   WORKER_ID        - integer identifier for this worker (for logging)
#
# Optional env vars:
#   NUM_WORKERS      - parquet parser processes per indexer (default: 32)
#   BATCH_SIZE       - ES bulk batch size (default: 12500)
#   CHUNK_SIZE       - parquet read chunk (default: 5000)
#   MAX_CHUNK_BYTES  - bulk request max MB (default: 50)
#   THREAD_COUNT     - parallel_bulk threads (default: 16)
#   QUEUE_SIZE       - parallel_bulk queue (default: 32)
#   INFO_WAIT_SECS   - seconds to wait for info file (default: 1800)
# ============================================================

set -euo pipefail

INDEX_NAME="${INDEX_NAME:?INDEX_NAME must be set}"
WORK_MANIFEST="${WORK_MANIFEST:?WORK_MANIFEST must be set}"
WORKER_ID="${WORKER_ID:?WORKER_ID must be set}"

NUM_WORKERS="${NUM_WORKERS:-32}"
BATCH_SIZE="${BATCH_SIZE:-12500}"
CHUNK_SIZE="${CHUNK_SIZE:-5000}"
MAX_CHUNK_BYTES="${MAX_CHUNK_BYTES:-50}"
THREAD_COUNT="${THREAD_COUNT:-16}"
QUEUE_SIZE="${QUEUE_SIZE:-32}"
INFO_WAIT_SECS="${INFO_WAIT_SECS:-1800}"
UPDATE_DUPLICATES="${UPDATE_DUPLICATES:-true}"

SCRATCH="/iopsstor/scratch/cscs/${USER}"
INFO_FILE="${INFO_FILE:-${SCRATCH}/es-cluster-${INDEX_NAME}.info}"
STATUS_DIR="${SCRATCH}/index-status/${INDEX_NAME}"

REPO_DIR="${REPO_DIR:-}"
if [[ -z "$REPO_DIR" ]]; then
    _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ "$_SCRIPT_DIR" != /var/spool* ]] && REPO_DIR="$(cd "${_SCRIPT_DIR}/../.." && pwd)"
fi
[[ -z "$REPO_DIR" ]] && { echo "[ERROR] REPO_DIR not set"; exit 1; }

INDEXER_AGG="${REPO_DIR}/indexing/scripts/index_aggregated.py"
INDEXER_RAW="${REPO_DIR}/indexing/scripts/index_raw.py"
VENV_DIR="${SCRATCH}/indexer-venv"
PYTHON_BIN="${VENV_DIR}/bin/python3"

echo "[Worker-${WORKER_ID}] =============================================="
echo "[Worker-${WORKER_ID}] Date:          $(date)"
echo "[Worker-${WORKER_ID}] Node:          ${SLURM_NODELIST:-local}"
echo "[Worker-${WORKER_ID}] INDEX_NAME:    $INDEX_NAME"
echo "[Worker-${WORKER_ID}] WORK_MANIFEST: $WORK_MANIFEST"
total_tasks=$(grep -c . "$WORK_MANIFEST" 2>/dev/null || echo 0)
echo "[Worker-${WORKER_ID}] Tasks:         $total_tasks"
echo "[Worker-${WORKER_ID}] =============================================="

ulimit -n 65536
[[ ! -x "$PYTHON_BIN" ]] && { echo "[ERROR] Indexer venv not found at $VENV_DIR"; exit 1; }
[[ ! -f "$WORK_MANIFEST" ]] && { echo "[ERROR] WORK_MANIFEST not found: $WORK_MANIFEST"; exit 1; }

# ---- Wait for cluster info file ----
echo "[Worker-${WORKER_ID}] Waiting for cluster info file (up to ${INFO_WAIT_SECS}s)..."
waited=0
until [[ -f "$INFO_FILE" ]]; do
    (( waited >= INFO_WAIT_SECS )) && { echo "[ERROR] Timed out waiting for $INFO_FILE"; exit 1; }
    sleep 10; (( waited += 10 ))
done
source "$INFO_FILE"
ES_HOST="${ES_HOST:?}"; ES_PORT="${ES_PORT:?}"
echo "[Worker-${WORKER_ID}] ES cluster: http://${ES_HOST}:${ES_PORT}"

# ---- Wait for ES health ----
ES_URL="http://${ES_HOST}:${ES_PORT}"
for (( i=0; i<600; i++ )); do
    health=$(curl -s "${ES_URL}/_cluster/health" 2>/dev/null || true)
    if [[ -n "$health" ]]; then
        status=$(echo "$health" | grep -o '"status":"[^"]*"' | grep -o '[a-z]*"$' | tr -d '"' || true)
        nodes=$(echo "$health" | grep -o '"number_of_nodes":[0-9]*' | grep -o '[0-9]*' || echo 0)
        if [[ "$status" == "green" || "$status" == "yellow" ]]; then
            echo "[Worker-${WORKER_ID}] ES healthy: status=${status} nodes=${nodes}"
            break
        fi
    fi
    (( i == 599 )) && { echo "[ERROR] ES not healthy after 6000s"; exit 1; }
    sleep 10
done

# ---- Process tasks sequentially ----
mkdir -p "$STATUS_DIR"
declare -a FAILED_CHUNKS=()
declare -a DONE_CHUNKS=()
task_num=0

while IFS='|' read -r ds_type chunk_id data_dir data_dirs_file dataset_name file_range_start file_range_end; do
    [[ -z "$ds_type" || "$ds_type" == \#* ]] && continue
    task_num=$(( task_num + 1 ))

    echo ""
    echo "[Worker-${WORKER_ID}] ── Task ${task_num}/${total_tasks}: ${chunk_id} ──────────────────"

    DONE_MARKER="${STATUS_DIR}/${chunk_id}.done"
    if [[ -f "$DONE_MARKER" ]]; then
        echo "[Worker-${WORKER_ID}] [SKIP] Already done: $chunk_id"
        DONE_CHUNKS+=("$chunk_id (skipped-already-done)")
        continue
    fi

    # ── Build indexer command ──
    if [[ "$ds_type" == "aggregated" ]]; then
        # Determine dirs to process
        declare -a dirs_to_run=()
        if [[ -n "$data_dirs_file" ]]; then
            while IFS= read -r line; do
                [[ -z "$line" || "$line" == \#* ]] && continue
                dirs_to_run+=("$line")
            done < "$data_dirs_file"
        else
            dirs_to_run=("$data_dir")
        fi

        chunk_ok=true
        for dir in "${dirs_to_run[@]}"; do
            if [[ ! -d "$dir" ]]; then
                echo "[Worker-${WORKER_ID}] [WARN] Dir not found, skipping: $dir"
                continue
            fi
            cmd=(
                "$PYTHON_BIN" "$INDEXER_AGG"
                --data-dir        "$dir"
                --index-name      "$INDEX_NAME"
                --es-host         "$ES_HOST"
                --es-port         "$ES_PORT"
                --keep-existing-index
                --op-type         create
                --num-workers     "$NUM_WORKERS"
                --batch-size      "$BATCH_SIZE"
                --chunk-size      "$CHUNK_SIZE"
                --max-chunk-bytes "$MAX_CHUNK_BYTES"
                --thread-count    "$THREAD_COUNT"
                --queue-size      "$QUEUE_SIZE"
            )
            [[ -n "$dataset_name"     ]] && cmd+=(--dataset-name "$dataset_name")
            [[ -n "$file_range_start" ]] && cmd+=(--file-range-start "$file_range_start" --file-range-end "$file_range_end")
            [[ "$UPDATE_DUPLICATES" == "false" ]] && cmd+=(--no-update-duplicates)

            echo "[Worker-${WORKER_ID}] Running: $(basename "$dir")"
            if ! "${cmd[@]}"; then
                echo "[Worker-${WORKER_ID}] [ERROR] FAILED on dir: $dir"
                chunk_ok=false
                break
            fi
        done

    elif [[ "$ds_type" == "raw" ]]; then
        [[ ! -d "$data_dir" ]] && { echo "[Worker-${WORKER_ID}] [ERROR] Dir not found: $data_dir"; FAILED_CHUNKS+=("$chunk_id"); continue; }
        cmd=(
            "$PYTHON_BIN" "$INDEXER_RAW"
            --dataset         "$dataset_name"
            --data-dir        "$data_dir"
            --index-name      "$INDEX_NAME"
            --es-host         "$ES_HOST"
            --es-port         "$ES_PORT"
            --num-workers     "$NUM_WORKERS"
            --batch-size      "$BATCH_SIZE"
            --chunk-size      "$CHUNK_SIZE"
            --max-chunk-bytes "$MAX_CHUNK_BYTES"
            --thread-count    "$THREAD_COUNT"
            --queue-size      "$QUEUE_SIZE"
        )
        [[ -n "$file_range_start" ]] && cmd+=(--file-range-start "$file_range_start" --file-range-end "$file_range_end")
        [[ "$UPDATE_DUPLICATES" == "false" ]] && cmd+=(--no-update-duplicates)
        echo "[Worker-${WORKER_ID}] Running: $dataset_name"
        chunk_ok=true
        "${cmd[@]}" || chunk_ok=false
    else
        echo "[Worker-${WORKER_ID}] [ERROR] Unknown type: $ds_type"
        FAILED_CHUNKS+=("$chunk_id")
        continue
    fi

    if [[ "${chunk_ok:-false}" == "true" ]]; then
        echo "CHUNK_ID=${chunk_id}"            > "$DONE_MARKER"
        echo "WORKER_ID=${WORKER_ID}"         >> "$DONE_MARKER"
        echo "COMPLETED_AT=$(date -Iseconds)" >> "$DONE_MARKER"
        echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}">> "$DONE_MARKER"
        rm -f "${STATUS_DIR}/${chunk_id}.failed"
        echo "[Worker-${WORKER_ID}] [OK] $chunk_id"
        DONE_CHUNKS+=("$chunk_id")
    else
        FAIL_MARKER="${STATUS_DIR}/${chunk_id}.failed"
        echo "CHUNK_ID=${chunk_id}"            > "$FAIL_MARKER"
        echo "WORKER_ID=${WORKER_ID}"         >> "$FAIL_MARKER"
        echo "FAILED_AT=$(date -Iseconds)"    >> "$FAIL_MARKER"
        echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}">> "$FAIL_MARKER"
        echo "[Worker-${WORKER_ID}] [FAIL] $chunk_id — marker written to $FAIL_MARKER"
        FAILED_CHUNKS+=("$chunk_id")
    fi

done < "$WORK_MANIFEST"

# ---- Summary ----
echo ""
echo "[Worker-${WORKER_ID}] =============================================="
echo "[Worker-${WORKER_ID}] SUMMARY"
echo "[Worker-${WORKER_ID}]   Done:   ${#DONE_CHUNKS[@]} / ${task_num}"
echo "[Worker-${WORKER_ID}]   Failed: ${#FAILED_CHUNKS[@]} / ${task_num}"
if (( ${#FAILED_CHUNKS[@]} > 0 )); then
    echo "[Worker-${WORKER_ID}]   FAILED CHUNKS:"
    for c in "${FAILED_CHUNKS[@]}"; do
        echo "[Worker-${WORKER_ID}]     ✗ $c"
    done
fi
echo "[Worker-${WORKER_ID}] =============================================="

(( ${#FAILED_CHUNKS[@]} > 0 )) && exit 1 || exit 0
