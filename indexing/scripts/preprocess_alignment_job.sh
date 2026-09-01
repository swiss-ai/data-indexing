#!/bin/bash
#SBATCH --partition=normal
#SBATCH --account=infra01
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --job-name=preprocess-alignment

# ============================================================
# Merge final_dataset_8B and final_dataset_70B into a single
# deduplicated parquet ready for indexing.
#
# Output goes to: posttrain_preprocessing/alignment-v2/
#
# Usage:
#   sbatch scripts/posttrain/preprocess_alignment_job.sh
# ============================================================

set -euo pipefail

SCRATCH="/iopsstor/scratch/cscs/${USER}"
CAPSTOR="/capstor/store/cscs/swissai/infra01"
VENV="${SCRATCH}/indexer-venv/bin/python3"

REPO_DIR="/users/alexandersternfeld/apertus-pretraining-data-indexing"
SCRIPT="${REPO_DIR}/scripts/posttrain/preprocess_alignment.py"

DIR_8B="${CAPSTOR}/posttrain_data/alignment_datasets_v1/final_dataset_8B"
DIR_70B="${CAPSTOR}/posttrain_data/alignment_datasets_v1/final_dataset_70B"
OUTPUT_DIR="/capstor/store/cscs/swissai/infra01/es_indices/posttrain_preprocessing/alignment-v2"

echo "[Preprocess] ======================================"
echo "[Preprocess] Date:   $(date)"
echo "[Preprocess] Node:   ${SLURM_NODELIST:-local}"
echo "[Preprocess] 8B dir: ${DIR_8B}"
echo "[Preprocess] 70B dir: ${DIR_70B}"
echo "[Preprocess] Output:  ${OUTPUT_DIR}"
echo "[Preprocess] ======================================"

mkdir -p "${OUTPUT_DIR}"

"$VENV" "$SCRIPT" \
    --dir-8b  "${DIR_8B}" \
    --dir-70b "${DIR_70B}" \
    --output-dir "${OUTPUT_DIR}" \
    --shard-size 50000

echo "[Preprocess] Done at $(date)"
echo "[Preprocess] Output parquet files:"
ls -lh "${OUTPUT_DIR}/"*.parquet 2>/dev/null || echo "(no parquet files found)"
