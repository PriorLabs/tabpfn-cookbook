#!/bin/bash
#SBATCH --job-name=bo-batching
#SBATCH --partition=gpul4flex
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --output=logs/%j.log

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 TABPFN_NO_BROWSER=1
export PYTHONUNBUFFERED=1
export TORCHINDUCTOR_CACHE_DIR="/tmp/bo-batching-${SLURM_JOB_ID}"
hostname
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
sha256sum benchmark_bo_batching.py
~/.local/bin/uv run -q --no-project --python 3.12 \
    --with 'tabpfn==9.2.0' \
    --with "tabpfn-extensions[bayesian_optimization] @ file://${SLURM_SUBMIT_DIR}/../tabpfn-extensions" \
    python benchmark_bo_batching.py \
    --checkpoint /home/klemens_priorlabs_ai/.cache/tabpfn/tabpfn-v3.5-20260909.safetensors \
    > "results-${SLURM_JOB_ID}.jsonl"
