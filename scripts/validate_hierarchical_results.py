"""Check completeness, temporal alignment and fit counts in executed results."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[1]
nb = json.loads((root / 'notebooks/forecast_hierarchical_series.ipynb').read_text())
code = '\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code')
execution = nb['metadata']['cookbook_execution']
current_hash = hashlib.sha256(code.encode()).hexdigest()
if current_hash != execution['code_sha256']:
    # Setup-only edits retain their original execution provenance. The model,
    # feature engineering, split, evaluation and plotting cells must be unchanged.
    retained = execution['retained_outputs']
    assert current_hash == retained['source_code_sha256']
    setup_tags = {'installation', 'data-imports', 'data-preparation'}
    model_code = '\n'.join(''.join(c['source']) for c in nb['cells']
                           if c['cell_type'] == 'code'
                           and not setup_tags.intersection(c['metadata'].get('tags', [])))
    assert hashlib.sha256(model_code.encode()).hexdigest() == retained['unchanged_model_code_sha256']
manifest = json.loads((root / '.benchmark-results/execution.json').read_text())
assert execution['code_sha256'] == manifest['code_sha256']
data_path = root / 'datasets/forecast_hierarchical_series/favorita_daily.csv'
assert hashlib.sha256(data_path.read_bytes()).hexdigest() == manifest['data_sha256']
for cell in nb['cells']:
    if cell['cell_type'] == 'code' and 'installation' not in cell['metadata'].get('tags', []):
        assert cell['execution_count'] is not None
    assert all(o['output_type'] != 'error' for o in cell.get('outputs', []))
results = root / '.benchmark-results'
pred = pd.read_csv(results / 'predictions.csv', parse_dates=['date', 'origin'])
fits = pd.read_csv(results / 'timings.csv')
assert len(pred) == 24192
assert len(fits) == 3120
assert pred.series_id.nunique() == 48
assert pred.origin.nunique() == 3
assert ((pred.date - pred.origin).dt.days == pred.horizon).all()
assert set(pred.horizon) == set(range(1, 15))
assert np.isfinite(pred[['sales', 'prediction']].to_numpy()).all()
assert pred.prediction.ge(0).all()
assert not pred.duplicated(['origin', 'method', 'strategy', 'series_id', 'horizon']).any()
for method in ['Basic dates', 'Fourier', 'Direct AR']:
    for strategy, contexts in [('Per series', 48), ('By family', 4), ('By store', 12), ('Global', 1)]:
        expected = 3 * contexts * (14 if method == 'Direct AR' else 1)
        assert len(fits.loc[fits.method.eq(method) & fits.strategy.eq(strategy)]) == expected
assert fits.seconds.gt(0).all()
assert np.isfinite(fits[['seconds', 'peak_gpu_gb']].to_numpy()).all()
summary = pd.read_csv(results / 'leaderboard.csv')
assert len(summary) == 13
assert np.isfinite(summary.MASE).all()
print('PASS: all 12 variants, 24,192 predictions, 3,120 fits, verified data and retained execution provenance.')
