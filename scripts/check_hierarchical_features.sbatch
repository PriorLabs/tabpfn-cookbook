#!/bin/bash
#SBATCH --job-name=hierarchical-check
#SBATCH --partition=cpun416mtspot
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=00:15:00
set -euo pipefail
cd "${COOKBOOK_REPO:?Set COOKBOOK_REPO}"
export OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16
.venv/bin/python scripts/check_hierarchical_features.py
