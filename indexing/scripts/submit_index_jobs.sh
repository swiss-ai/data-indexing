#!/bin/bash
# ============================================================
# Submit (or re-submit) the full pretraining indexing pipeline.
#
# Safe to run multiple times: chunks that already have a .done
# marker are skipped automatically inside index_worker.sh, so
# re-running after a cluster timeout only queues the remaining work.
#
#   1. One N-node ES cluster job (12h, persistent data on iopsstor)
#   2. Exactly NUM_WORKERS_PER_JOB worker jobs, each reading a
#      manifest file and processing its chunks sequentially.
#      This bounds ES concurrency to NUM_WORKERS_PER_JOB connections.
#
# Usage:
#   ./submit_index_jobs.sh [--dry-run] [OPTIONS]
#
# Required env vars (or pass on command line):
#   INDEX_NAME         - ES index name (e.g. global-pretraining)
#
# Optional env vars:
#   GLOBAL_MERGE_DIR   - path to english-web-dedup parquet (500 files)
#                        omit to skip english-web-dedup (submit later)
#   FW2_AGG_DIR        - FW2 per-language aggregated dir
#   CAPSTOR_BASE       - root for raw capstor datasets
#   ES_NODES           - nodes for the ES cluster job (default: 30)
#   NUM_SHARDS         - ES primary shards; auto-computed from data size
#                        if not set (~20 GB/shard + 1TB headroom)
#   ENG_SPLIT_JOBS     - how many work items to split english-web into (default: 10)
#   NUM_WORKERS_PER_JOB - number of worker SLURM jobs to submit (default: 5)
#   FW2_TARGET_GB      - target GB per FW2 batch (default: 50)
#   DRY_RUN            - "true" or --dry-run to print commands only
# ============================================================

set -euo pipefail

DRY_RUN="${DRY_RUN:-false}"
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN="true"

INDEX_NAME="${INDEX_NAME:?INDEX_NAME must be set}"
GLOBAL_MERGE_DIR="${GLOBAL_MERGE_DIR:-}"
FW2_AGG_DIR="${FW2_AGG_DIR:-}"
CAPSTOR_BASE="${CAPSTOR_BASE:-/capstor/store/cscs/swissai/infra01/datasets/swiss-ai}"
ES_NODES="${ES_NODES:-30}"
ENG_SPLIT_JOBS="${ENG_SPLIT_JOBS:-10}"
NUM_WORKERS_PER_JOB="${NUM_WORKERS_PER_JOB:-5}"
FW2_TARGET_GB="${FW2_TARGET_GB:-50}"
SKIP_RAW="${SKIP_RAW:-false}"
NO_UPDATE_DUPLICATES="${NO_UPDATE_DUPLICATES:-false}"
EXTRA_DEP="${EXTRA_DEP:-}"  # optional extra SLURM dependency (e.g. afterany:JOB1:JOB2)

# ---- Compute NUM_SHARDS from actual data size (if not set explicitly) ----
if [[ -z "${NUM_SHARDS:-}" ]]; then
    total_gb=0
    for dir in "${GLOBAL_MERGE_DIR:-}" "${FW2_AGG_DIR:-}"; do
        [[ -d "$dir" ]] && total_gb=$(( total_gb + $(du -sB1G "$dir" 2>/dev/null | awk '{print $1}') ))
    done
    total_gb=$(( total_gb + 200 ))   # rough estimate for raw datasets
    es_gb=$(( total_gb * 2 ))        # ES overhead (~2× compressed parquet)
    es_gb=$(( es_gb + 1000 ))        # +1 TB headroom for future datasets
    raw_shards=$(( es_gb / 20 ))
    NUM_SHARDS=$(( ((raw_shards + 49) / 50) * 50 ))  # round up to nearest 50
    echo "[INFO] Auto-computed NUM_SHARDS=${NUM_SHARDS}  (data=${total_gb}GB, ES est.=${es_gb}GB @ 20GB/shard)"
fi

SCRATCH="/iopsstor/scratch/cscs/${USER}"
STATUS_DIR="${SCRATCH}/index-status/${INDEX_NAME}"
MANIFEST_BASE="${SCRATCH}/worker-manifests-${INDEX_NAME}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_SCRIPT="${REPO_DIR}/indexing/scripts/start_es_cluster.sh"
WORKER_SCRIPT="${REPO_DIR}/indexing/scripts/index_worker.sh"

# Raw dataset paths — existing
EUROPARL_DIR="${CAPSTOR_BASE}/europarl_bidirectional_preprocessed/data"
PARADOCS_DIR="${CAPSTOR_BASE}/paradocs-bidirectional-piifiltered/data"
FLAN_DIR="${CAPSTOR_BASE}/provenance-flan-templated/data"
EUROBLOCKS_DIR="${CAPSTOR_BASE}/EuroBlocks-SFT-Synthetic-1124_preprocessed/data"
INSTBOOKS_DIR="${CAPSTOR_BASE}/institutional-books-1.0-filtered/data"
GUTENBERG_DEDUP_DIR="${CAPSTOR_BASE}/project_gutenberg_preprocessed/dedup"   # preprocess_gutenberg.py output
CANARIES_DIR="${CAPSTOR_BASE}/apertus-pretrain-poisonandcanaries"

# Raw dataset paths — second indexing pass additions
INFRA01_BASE="${INFRA01_BASE:-/capstor/store/cscs/swissai/infra01}"
WIKIPEDIA_DIR="${INFRA01_BASE}/datasets/HuggingFaceFW/clean-wikipedia"
FINEMATH_DIR="${INFRA01_BASE}/datasets/swiss-ai/finemath-filterrobots_fine/data/output/finemath-3plus"
INFIWEBMATH_DIR="${INFRA01_BASE}/datasets/swiss-ai/finemath-filterrobots_fine/data/output/infiwebmath-3plus"
MEGAMATH_DIR="${INFRA01_BASE}/datasets/swiss-ai/megamath-web/data/output"
STARCODER_DIR="${INFRA01_BASE}/datasets/swiss-ai/starcoderdata"
STARCODER_EXTRAS_DIR="${INFRA01_BASE}/datasets/swiss-ai/starcoderdata-extras"
STACKV2_EDU_DIR="${INFRA01_BASE}/datasets/common-pile/stackv2_edu_filtered/snapshot"

# Posttrain dataset paths (preprocessed output from preprocess_*.py scripts)
POSTTRAIN_PRE_BASE="${POSTTRAIN_PRE_BASE:-/capstor/store/cscs/swissai/a145/es_indices_2026/posttrain_preprocessing}"
ALIGNMENT_DIR="${POSTTRAIN_PRE_BASE}/alignment"    # preprocess_alignment.py output
SFT_DIR="${POSTTRAIN_PRE_BASE}/sft-mixture"        # preprocess_sft.py output

echo "============================================================"
echo "  Submit / resume pretraining index pipeline"
echo "  INDEX_NAME:          $INDEX_NAME"
echo "  ES_NODES:            $ES_NODES"
echo "  NUM_SHARDS:          $NUM_SHARDS  (~20 GB/shard → ~$((NUM_SHARDS * 20)) GB capacity)"
echo "  NUM_WORKERS_PER_JOB: $NUM_WORKERS_PER_JOB  (concurrent ES connections)"
echo "  ENG_SPLIT_JOBS:      $ENG_SPLIT_JOBS  (work items for english-web)"
echo "  FW2_TARGET_GB:       $FW2_TARGET_GB  GB per FW2 batch"
echo "  SKIP_RAW:            $SKIP_RAW"
echo "  NO_UPDATE_DUPLICATES: $NO_UPDATE_DUPLICATES"
echo "  GLOBAL_MERGE_DIR:    ${GLOBAL_MERGE_DIR:-(not set, skipping english-web)}"
echo "  FW2_AGG_DIR:         ${FW2_AGG_DIR:-(not set, skipping fw2)}"
echo "  STATUS_DIR:          $STATUS_DIR"
echo "  MANIFEST_BASE:       $MANIFEST_BASE"
echo "  DRY_RUN:             $DRY_RUN"
echo "============================================================"
echo ""

sbatch_or_dry() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY-RUN] sbatch $*" >&2
        echo "DRY_RUN_JOB_ID"
    else
        local out
        out=$(sbatch "$@")
        echo "$out" >&2
        echo "$out" | grep -oP '(?<=job )\d+'
    fi
}

# ---- 1. Submit ES cluster job (or reuse existing) ----
# Set CLUSTER_JOB_ID env var to reuse a running cluster instead of submitting a new one.
if [[ -n "${CLUSTER_JOB_ID:-}" ]]; then
    echo ">>> Reusing existing ES cluster job: $CLUSTER_JOB_ID"
else
    echo ">>> Submitting ES cluster job (${ES_NODES} nodes, 12h)..."
    CLUSTER_JOB_ID=$(
        sbatch_or_dry \
            --nodes="$ES_NODES" \
            --export="ALL,INDEX_NAME=${INDEX_NAME},NUM_SHARDS=${NUM_SHARDS},REPO_DIR=${REPO_DIR},HOME=${HOME}" \
            --output="${SCRATCH}/slurm-es-cluster-${INDEX_NAME}-%j.out" \
            "$CLUSTER_SCRIPT"
    )
    echo "    ES cluster job ID: $CLUSTER_JOB_ID"
fi
echo ""

# ============================================================
# Collect all work items into an array.
# Each element is one pipe-separated manifest line:
#   TYPE|CHUNK_ID|DATA_DIR|DATA_DIRS_FILE|DATASET_NAME|FILE_RANGE_START|FILE_RANGE_END
# ============================================================

declare -a ALL_WORK_ITEMS=()

add_work() {
    # add_work TYPE CHUNK_ID DATA_DIR DATA_DIRS_FILE DATASET_NAME FILE_RANGE_START FILE_RANGE_END
    ALL_WORK_ITEMS+=("${1}|${2}|${3}|${4}|${5}|${6}|${7}")
}

# ---- 2. English web dedup (split across ENG_SPLIT_JOBS work items) ----
if [[ -d "${GLOBAL_MERGE_DIR:-}" ]]; then
    TOTAL_FILES=$(find "$GLOBAL_MERGE_DIR" -name "*.parquet" | wc -l)
    FILES_PER_ITEM=$(( (TOTAL_FILES + ENG_SPLIT_JOBS - 1) / ENG_SPLIT_JOBS ))
    echo ">>> English web dedup: $TOTAL_FILES files → $ENG_SPLIT_JOBS work items × ~$FILES_PER_ITEM files"
    for (( i=0; i<ENG_SPLIT_JOBS; i++ )); do
        START=$(( i * FILES_PER_ITEM ))
        END=$(( START + FILES_PER_ITEM - 1 ))
        (( END >= TOTAL_FILES )) && END=$(( TOTAL_FILES - 1 ))
        CHUNK="eng-web-${START}-${END}"
        add_work "aggregated" "$CHUNK" "$GLOBAL_MERGE_DIR" "" "" "$START" "$END"
    done
elif [[ -n "${GLOBAL_MERGE_DIR:-}" ]]; then
    echo "[WARN] GLOBAL_MERGE_DIR not found ($GLOBAL_MERGE_DIR) — skipping english-web-dedup"
else
    echo "[INFO] GLOBAL_MERGE_DIR not set — skipping english-web-dedup"
fi

# ---- 3. FineWeb-2 (bin-packed by size into ~FW2_TARGET_GB batches) ----
if [[ -d "${FW2_AGG_DIR:-}" ]]; then
    echo ">>> FineWeb-2: scanning dir sizes for bin-packing (target ${FW2_TARGET_GB} GB/batch)..."
    FW2_DIRS_BASE="${SCRATCH}/fw2-batch-dirs-${INDEX_NAME}"
    mkdir -p "$FW2_DIRS_BASE"

    mapfile -t FW2_BATCHES < <(python3 - <<PYEOF
import os, subprocess

agg_dir   = "$FW2_AGG_DIR"
bdir      = "$FW2_DIRS_BASE"
target_gb = int("$FW2_TARGET_GB")

dirs = sorted(d.path for d in os.scandir(agg_dir) if d.is_dir())
result = subprocess.run(["du", "-sB1G"] + dirs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
size_map = {}
for line in result.stdout.decode().splitlines():
    parts = line.split("\t", 1)
    if len(parts) == 2:
        gb = max(1, int(parts[0]))
        size_map[parts[1]] = gb

batch, cur_gb, batch_num = [], 0, 0
for d in dirs:
    gb = size_map.get(d, 1)
    if batch and cur_gb + gb > target_gb:
        path = os.path.join(bdir, f"batch-{batch_num}.dirs")
        open(path, "w").write("\n".join(batch) + "\n")
        print(path)
        batch, cur_gb, batch_num = [], 0, batch_num + 1
    batch.append(d)
    cur_gb += gb
if batch:
    path = os.path.join(bdir, f"batch-{batch_num}.dirs")
    open(path, "w").write("\n".join(batch) + "\n")
    print(path)
PYEOF
)

    echo "    ${#FW2_BATCHES[@]} FW2 batches"
    for dirs_file in "${FW2_BATCHES[@]}"; do
        batch_name="$(basename "$dirs_file" .dirs)"
        CHUNK="fw2-${batch_name}"
        add_work "aggregated" "$CHUNK" "" "$dirs_file" "fineweb-2" "" ""
    done
elif [[ -n "${FW2_AGG_DIR:-}" ]]; then
    echo "[WARN] FW2_AGG_DIR not found ($FW2_AGG_DIR) — skipping fineweb-2"
else
    echo "[INFO] FW2_AGG_DIR not set — skipping fineweb-2"
fi

# ---- 4. Raw datasets (chunked by file count for resilience) ----
# RAW_CHUNK_FILES: max indexable files per chunk. Datasets with more files are
# split into multiple work items so a cluster restart only re-does one chunk.
RAW_CHUNK_FILES="${RAW_CHUNK_FILES:-100}"

add_raw_chunked() {
    local ds="$1" dir="$2"
    if [[ ! -d "$dir" ]]; then
        echo "    [WARN] $ds: dir not found ($dir) — skipping"
        return
    fi
    local total
    total=$(find "$dir" -type f \( -name "*.parquet" -o -name "*.jsonl" \
            -o -name "*.jsonl.gz" -o -name "*.json.gz" \) 2>/dev/null | wc -l)
    if (( total == 0 )); then
        echo "    [WARN] $ds: no indexable files in $dir — skipping"
        return
    fi
    if (( total <= RAW_CHUNK_FILES )); then
        echo "    $ds: $total files → 1 chunk"
        add_work "raw" "$ds" "$dir" "" "$ds" "" ""
    else
        local n_chunks=$(( (total + RAW_CHUNK_FILES - 1) / RAW_CHUNK_FILES ))
        echo "    $ds: $total files → $n_chunks chunks of ~$RAW_CHUNK_FILES"
        for (( i=0; i<n_chunks; i++ )); do
            local start=$(( i * RAW_CHUNK_FILES ))
            local end=$(( start + RAW_CHUNK_FILES - 1 ))
            (( end >= total )) && end=$(( total - 1 ))
            add_work "raw" "${ds}-files-${start}-${end}" "$dir" "" "$ds" "$start" "$end"
        done
    fi
}

if [[ "$SKIP_RAW" == "true" ]]; then
    echo "[INFO] SKIP_RAW=true — skipping raw datasets"
else
    echo ">>> Raw datasets (RAW_CHUNK_FILES=${RAW_CHUNK_FILES})"
    for ds_and_dir in \
        "europarl:${EUROPARL_DIR}" \
        "paradocs:${PARADOCS_DIR}" \
        "flan:${FLAN_DIR}" \
        "euroblocks:${EUROBLOCKS_DIR}" \
        "institutional-books:${INSTBOOKS_DIR}" \
        "gutenberg:${GUTENBERG_DEDUP_DIR}" \
        "canaries:${CANARIES_DIR}" \
        "wikipedia:${WIKIPEDIA_DIR}" \
        "finemath:${FINEMATH_DIR}" \
        "infiwebmath:${INFIWEBMATH_DIR}" \
        "megamath-web:${MEGAMATH_DIR}" \
        "starcoder:${STARCODER_DIR}" \
        "starcoder-extras:${STARCODER_EXTRAS_DIR}" \
        "stackv2-edu:${STACKV2_EDU_DIR}" \
        "alignment:${ALIGNMENT_DIR}" \
        "sft-mixture:${SFT_DIR}"; do
        ds="${ds_and_dir%%:*}"
        dir="${ds_and_dir#*:}"
        add_raw_chunked "$ds" "$dir"
    done
fi

echo ""
echo ">>> Total work items collected: ${#ALL_WORK_ITEMS[@]}"

# ============================================================
# Distribute work items round-robin across NUM_WORKERS_PER_JOB
# manifest files, then submit exactly that many worker jobs.
# ============================================================

mkdir -p "$MANIFEST_BASE"

# Clear old manifests so we start clean
for (( w=0; w<NUM_WORKERS_PER_JOB; w++ )); do
    > "${MANIFEST_BASE}/worker-${w}.manifest"
done

# Round-robin assignment
for (( idx=0; idx<${#ALL_WORK_ITEMS[@]}; idx++ )); do
    w=$(( idx % NUM_WORKERS_PER_JOB ))
    echo "${ALL_WORK_ITEMS[$idx]}" >> "${MANIFEST_BASE}/worker-${w}.manifest"
done

# Show distribution
echo ""
echo ">>> Manifest distribution:"
for (( w=0; w<NUM_WORKERS_PER_JOB; w++ )); do
    mf="${MANIFEST_BASE}/worker-${w}.manifest"
    count=$(wc -l < "$mf" 2>/dev/null || echo 0)
    echo "    worker-${w}: $count tasks → $mf"
done

echo ""
dep_str="${EXTRA_DEP:-after:${CLUSTER_JOB_ID}}"
echo ">>> Submitting ${NUM_WORKERS_PER_JOB} worker jobs (dependency=${dep_str})..."

SUBMITTED_JOBS=()
WORKER_JOB_IDS=()
for (( w=0; w<NUM_WORKERS_PER_JOB; w++ )); do
    mf="${MANIFEST_BASE}/worker-${w}.manifest"
    count=$(wc -l < "$mf" 2>/dev/null || echo 0)
    if (( count == 0 )); then
        echo "    worker-${w}: no tasks — skipping"
        continue
    fi
    job_id=$(
        sbatch_or_dry \
            --dependency="${dep_str}" \
            --export="ALL,INDEX_NAME=${INDEX_NAME},WORK_MANIFEST=${mf},WORKER_ID=${w},REPO_DIR=${REPO_DIR},HOME=${HOME},UPDATE_DUPLICATES=$([[ "$NO_UPDATE_DUPLICATES" == "true" ]] && echo false || echo true)" \
            --output="${SCRATCH}/slurm-index-worker-${w}-${INDEX_NAME}-%j.out" \
            "$WORKER_SCRIPT"
    )
    echo "    worker-${w} (${count} tasks) → job $job_id"
    SUBMITTED_JOBS+=("$job_id (worker-${w})")
    WORKER_JOB_IDS+=("$job_id")
done

# ---- Snapshot job (after all workers) ----
SNAPSHOT_JOB_ID=""
SNAPSHOT_SCRIPT="${REPO_DIR}/indexing/scripts/snapshot_job.sh"
if [[ -f "$SNAPSHOT_SCRIPT" && ${#WORKER_JOB_IDS[@]} -gt 0 ]]; then
    snap_dep=$(printf "afterany:%s" "${WORKER_JOB_IDS[0]}")
    for jid in "${WORKER_JOB_IDS[@]:1}"; do snap_dep+=":${jid}"; done
    echo ""
    echo ">>> Submitting snapshot job (dependency=${snap_dep})..."
    SNAPSHOT_JOB_ID=$(
        sbatch_or_dry \
            --dependency="${snap_dep}" \
            --export="ALL,INDEX_NAME=${INDEX_NAME},REPO_DIR=${REPO_DIR},HOME=${HOME}" \
            --output="${SCRATCH}/slurm-snapshot-${INDEX_NAME}-%j.out" \
            "$SNAPSHOT_SCRIPT"
    )
    echo "    snapshot → job $SNAPSHOT_JOB_ID"
fi

# ---- Summary ----
echo ""
echo "============================================================"
echo "  ES cluster:      job $CLUSTER_JOB_ID (${ES_NODES} nodes)"
echo "  Worker jobs:     ${#SUBMITTED_JOBS[@]}"
for j in "${SUBMITTED_JOBS[@]}"; do echo "    $j"; done
[[ -n "$SNAPSHOT_JOB_ID" ]] && echo "  Snapshot job:    $SNAPSHOT_JOB_ID  (runs after all workers)"
echo ""
echo "  Monitor:"
echo "    squeue -u $USER"
echo "  Cluster log:"
echo "    tail -f ${SCRATCH}/slurm-es-cluster-${INDEX_NAME}-${CLUSTER_JOB_ID}.out"
echo "  Worker logs:"
echo "    tail -f ${SCRATCH}/slurm-index-worker-*-${INDEX_NAME}-*.out"
[[ -n "$SNAPSHOT_JOB_ID" ]] && echo "  Snapshot log:"
[[ -n "$SNAPSHOT_JOB_ID" ]] && echo "    tail -f ${SCRATCH}/slurm-snapshot-${INDEX_NAME}-${SNAPSHOT_JOB_ID}.out"
echo "  Done markers:"
echo "    ls ${STATUS_DIR}/*.done | wc -l"
echo "  Failed markers:"
echo "    ls ${STATUS_DIR}/*.failed 2>/dev/null || echo none"
echo "  To resume after cluster timeout, run this script again."
echo "============================================================"
