#!/bin/bash
#SBATCH --partition=normal
#SBATCH --account=infra01
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --job-name=preprocess-sft

# ============================================================
# Download swiss-ai/apertus-sft-mixture from HuggingFace and
# preprocess into parquet shards ready for indexing.
#
# Output goes to: posttrain_preprocessing/sft-mixture-v2/
#
# Usage:
#   sbatch scripts/posttrain/preprocess_sft_job.sh
# ============================================================

set -euo pipefail

SCRATCH="/iopsstor/scratch/cscs/${USER}"
VENV="${SCRATCH}/indexer-venv/bin/python3"

REPO_DIR="/users/alexandersternfeld/apertus-pretraining-data-indexing"
SCRIPT="${REPO_DIR}/scripts/posttrain/preprocess_sft.py"

export HF_DATASET="swiss-ai/apertus-sft-mixture"
export DOWNLOAD_DIR="${SCRATCH}/sft-mixture-raw"
OUTPUT_DIR="/capstor/store/cscs/swissai/infra01/es_indices/posttrain_preprocessing/sft-mixture-v2"

echo "[Preprocess] ======================================"
echo "[Preprocess] Date:       $(date)"
echo "[Preprocess] Node:       ${SLURM_NODELIST:-local}"
echo "[Preprocess] Dataset:    ${HF_DATASET}"
echo "[Preprocess] Download:   ${DOWNLOAD_DIR}"
echo "[Preprocess] Output:     ${OUTPUT_DIR}"
echo "[Preprocess] ======================================"

mkdir -p "${DOWNLOAD_DIR}"
mkdir -p "${OUTPUT_DIR}"

# Download parquet files from HuggingFace (public dataset, no auth needed)
echo "[Preprocess] Fetching file list ..."
HF_BASE="https://huggingface.co/datasets/${HF_DATASET}/resolve/main/data"
# Get list of train parquet files via the HF API
FILE_LIST=$(curl -sL "https://huggingface.co/api/datasets/${HF_DATASET}" \
    | python3 -c "
import json, sys
meta = json.load(sys.stdin)
siblings = meta.get('siblings', [])
for s in siblings:
    rfilename = s.get('rfilename', '')
    if rfilename.startswith('data/train') and rfilename.endswith('.parquet'):
        print(rfilename)
")

echo "[Preprocess] Files to download:"
echo "$FILE_LIST"

echo "[Preprocess] Downloading ..."
while IFS= read -r rfilename; do
    fname=$(basename "$rfilename")
    dest="${DOWNLOAD_DIR}/${fname}"
    if [[ -f "$dest" ]]; then
        echo "  Already exists: $fname"
    else
        echo "  Downloading: $fname"
        wget -q -O "$dest" "${HF_BASE}/${fname}"
    fi
done <<< "$FILE_LIST"

echo "[Preprocess] Download complete. Running preprocessing ..."

"$VENV" "$SCRIPT" \
    --input-dir  "${DOWNLOAD_DIR}" \
    --output-dir "${OUTPUT_DIR}" \
    --shard-size 50000

echo "[Preprocess] Done at $(date)"
echo "[Preprocess] Output parquet files:"
ls -lh "${OUTPUT_DIR}/"*.parquet 2>/dev/null || echo "(no parquet files found)"
