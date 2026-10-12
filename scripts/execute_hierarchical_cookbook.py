"""Execute the forecasting recipe on a worker, checkpointing individual contexts.

Private execution artifacts stay in .benchmark-results. The notebook itself contains
ordinary sklearn calls; this runner adds resumption without obscuring the lesson.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'notebooks/forecast_hierarchical_series.ipynb'
RUN = ROOT / '.benchmark-results'
RUN.mkdir(exist_ok=True)
original = SOURCE.read_bytes()
notebook = nbformat.reads(original.decode(), as_version=4)
code_hash = hashlib.sha256('\n'.join(c.source for c in notebook.cells if c.cell_type == 'code').encode()).hexdigest()
model_source = next(c.source for c in notebook.cells if 'model-helper' in c.metadata.get('tags', []))
cache_namespace = hashlib.sha256(model_source.split('# Warm')[0].encode()).hexdigest()
run_id = os.environ.get('SLURM_JOB_ID', 'manual')
output = RUN / f'executed_{run_id}.ipynb'
for cell in notebook.cells:
    if cell.cell_type == 'code':
        cell.outputs = []
        cell.execution_count = None
    if 'installation' in cell.metadata.get('tags', []):
        cell.metadata['tags'].append('skip-execution')

# Isolate this process's kernel rather than using a user's default python3 kernel.
kernel_dir = RUN / 'jupyter/kernels/hierarchical'
kernel_dir.mkdir(parents=True, exist_ok=True)
(kernel_dir / 'kernel.json').write_text(json.dumps({
    'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
    'display_name': 'Hierarchical forecasting', 'language': 'python'}))
os.environ['JUPYTER_PATH'] = str(RUN / 'jupyter')

checkpoint_code = r'''
import hashlib as _hashlib
import pickle as _pickle
import json as _json
import importlib.metadata as _metadata
import os as _os
_cache_dir = Path('../.benchmark-results/contexts') / CACHE_NAMESPACE
_cache_dir.mkdir(parents=True, exist_ok=True)
_uncached_predict_context = predict_context
_completed_contexts = 0
_legacy_path = Path('../.benchmark-results/legacy_cache_namespaces.json')
_legacy_namespaces = _json.loads(_legacy_path.read_text()).get(CACHE_NAMESPACE, []) if _legacy_path.exists() else []

def predict_context(train, query, columns):
    global _completed_contexts
    def cache_path(namespace):
        digest = _hashlib.sha256(namespace.encode())
        digest.update(_metadata.version('tabpfn').encode())
        digest.update('|'.join(columns).encode())
        for frame in [train[columns + ['sales']], query[columns]]:
            digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
            digest.update(str(frame.dtypes).encode())
        return _cache_dir.parent / namespace / (digest.hexdigest() + '.pkl')
    path = cache_path(CACHE_NAMESPACE)
    cached = next((p for p in [path, *[cache_path(n) for n in _legacy_namespaces]] if p.exists()), None)
    if cached is not None:
        values, stats = _pickle.loads(cached.read_bytes())
    else:
        values, stats = _uncached_predict_context(train, query, columns)
    if not path.exists():
        partial = path.with_suffix('.tmp')
        partial.write_bytes(_pickle.dumps((values, stats)))
        partial.replace(path)
    _completed_contexts += 1
    (_cache_dir.parent.parent / 'progress.json').write_text(_json.dumps(
        {'completed_contexts': _completed_contexts, 'last_context': stats,
         'updated': time.time(), 'job_id': _os.environ.get('SLURM_JOB_ID')}))
    return values, stats
'''
checkpoint = nbformat.v4.new_code_cell(
    f'CACHE_NAMESPACE = {cache_namespace!r}\nEXECUTION_CODE_HASH = {code_hash!r}\n' + checkpoint_code,
    metadata={'tags': ['execution-internal']})
idx = next(i for i, c in enumerate(notebook.cells) if 'model-helper' in c.metadata.get('tags', []))
notebook.cells.insert(idx + 1, checkpoint)
export = nbformat.v4.new_code_cell(r'''
import importlib.metadata as _metadata
import json as _json
from datetime import datetime, timezone
_artifacts = Path('../.benchmark-results')
for _name in ['predictions', 'timings', 'leaderboard', 'pooling_summary', 'date_comparison', 'h2_predictions', 'scored']:
    globals()[_name].to_csv(_artifacts / f'{_name}.csv', index=_name == 'pooling_summary')
_manifest = {
    'finished_utc': datetime.now(timezone.utc).isoformat(),
    'gpu': torch.cuda.get_device_name(), 'cpu_threads': torch.get_num_threads(),
    'allocated_cpus': int(_os.environ.get('SLURM_CPUS_PER_TASK', torch.get_num_threads())),
    'slurm_job_id': _os.environ.get('SLURM_JOB_ID'), 'partition': _os.environ.get('SLURM_JOB_PARTITION'),
    'packages': {name: _metadata.version(name) for name in ['tabpfn', 'torch', 'numpy', 'pandas', 'scikit-learn']},
    'model_version': 'v3.5', 'seed': 42,
    'origins': [str(x.date()) for x in TEST_ORIGINS], 'horizons': H,
    'fits': len(timings), 'code_sha256': EXECUTION_CODE_HASH,
    'ensemble_members': sorted(timings.ensemble_members.unique().astype(int).tolist()),
    'data_sha256': _hashlib.sha256(Path('favorita_daily.csv').read_bytes()).hexdigest(),
}
(_artifacts / 'execution.json').write_text(_json.dumps(_manifest, indent=2))
print(_json.dumps(_manifest, indent=2))
''', metadata={'tags': ['execution-internal']})
notebook.cells.append(export)

def started(cell, cell_index, **kwargs):
    print(f'Cell {cell_index}: {cell.source.splitlines()[0][:100]}', flush=True)

def finished(cell, cell_index, **kwargs):
    nbformat.write(notebook, output)
    for out in cell.get('outputs', []):
        if out.output_type == 'stream':
            print(out.text[-2000:], flush=True)

try:
    NotebookClient(notebook, timeout=172800, kernel_name='hierarchical',
                   resources={'metadata': {'path': str(ROOT / 'notebooks')}},
                   on_cell_start=started, on_cell_executed=finished).execute()
finally:
    nbformat.write(notebook, output)

if SOURCE.read_bytes() != original:
    raise RuntimeError('Notebook source changed during execution; results saved privately, not promoted.')
notebook.cells = [c for c in notebook.cells if 'execution-internal' not in c.metadata.get('tags', [])]
for cell in notebook.cells:
    if 'installation' in cell.metadata.get('tags', []):
        cell.metadata['tags'].remove('skip-execution')
manifest = json.loads((RUN / 'execution.json').read_text())
notebook.metadata['cookbook_execution'] = {
    'code_sha256': code_hash, 'model_version': 'v3.5',
    'packages': manifest['packages'], 'gpu': manifest['gpu'],
    'allocated_cpus': manifest['allocated_cpus'], 'torch_threads': manifest['cpu_threads']}
nbformat.write(notebook, SOURCE)
print(f'Promoted executed notebook: {SOURCE}', flush=True)
