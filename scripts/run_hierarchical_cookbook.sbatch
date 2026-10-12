#!/bin/bash
#SBATCH --job-name=hierarchical-tabpfn35
#SBATCH --partition=gpul416corespotinteractivemt
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=60G
#SBATCH --time=2-00:00:00
#SBATCH --requeue
set -euo pipefail
cd "${COOKBOOK_REPO:?Set COOKBOOK_REPO}"
export OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16
export PYTHONUNBUFFERED=1 MPLBACKEND=module://matplotlib_inline.backend_inline
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
.venv/bin/python scripts/execute_hierarchical_cookbook.py
.venv/bin/python scripts/convert_to_markdown.py --slug forecast_hierarchical_series
.venv/bin/python scripts/validate.py --all
.venv/bin/python scripts/validate_hierarchical_results.py
git diff --check
