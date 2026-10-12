#!/bin/bash
#SBATCH --job-name=hierarchical-prepare
#SBATCH --partition=cpun416mtspot
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=01:00:00
#SBATCH --requeue
set -euo pipefail
cd "${COOKBOOK_REPO:?Set COOKBOOK_REPO}"
export OMP_NUM_THREADS=16 OPENBLAS_NUM_THREADS=16 MKL_NUM_THREADS=16
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r scripts/requirements-hierarchical.txt
.venv/bin/python - <<'PY'
import os, json, hashlib, importlib.metadata as im
from pathlib import Path
root=Path.cwd()
nb=json.loads((root/'notebooks/forecast_hierarchical_series.ipynb').read_text())
os.chdir(root/'notebooks')
namespace={}
for cell in nb['cells']:
    if set(cell['metadata'].get('tags',[])) & {'data-imports','data-preparation'}:
        exec(''.join(cell['source']),namespace)
manifest={'packages':{n:im.version(n) for n in ['tabpfn','torch','numpy','pandas','scikit-learn','nbclient']},
          'data_sha256':hashlib.sha256(namespace['panel_path'].read_bytes()).hexdigest(),
          'dataset_revision':'1ac138dfdfafc520bc29831e73373954b1b7bc05'}
(root/'.benchmark-results/preparation.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
PY
