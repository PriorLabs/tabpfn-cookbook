"""Worker-side tests of the notebook's date and horizon alignment."""
import ast
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

root=Path(__file__).resolve().parents[1]
notebook=json.loads((root/'notebooks/forecast_hierarchical_series.ipynb').read_text())
for cell in notebook['cells']:
    cell['source']=''.join(cell['source'])
os.chdir(root/'notebooks')
ns={'Path':Path, 'pd':pd, 'np':np, 'display':lambda *a:None,
    'H':14,'HISTORY_DAYS':730,'DEMO_ORIGIN':pd.Timestamp('2017-05-31'),
    'EXAMPLES':['1 / BEVERAGES','2 / BEVERAGES']}
ns['panel']=pd.read_csv('favorita_daily.csv',parse_dates=['date'])
for prefix, until in [('IDENTIFIERS =',None),('FOURIER =','example_rows ='),('AR_COLUMNS =','h2_rows =')]:
    cell=next(c for c in notebook['cells'] if c['cell_type']=='code' and c['source'].startswith(prefix))
    exec(cell['source'].split(until)[0] if until else cell['source'],ns)
ns['CALENDAR_COLUMNS']=ns['IDENTIFIERS']+ns['KNOWN']+ns['BASIC']+ns['FOURIER']

def capture(train, query, columns, strategy, cutoff):
    assert train.date.max() <= cutoff
    assert train.origin.max() < cutoff
    assert query.origin.eq(cutoff).all()
    assert len(query)==48
    for row in query.itertuples():
        assert row.last_sales == ns['wide_sales'].at[cutoff,row.series_id]
        assert row.sales_7d_ago == ns['wide_sales'].at[cutoff-pd.Timedelta(days=7),row.series_id]
        expected=ns['wide_sales'].loc[cutoff-pd.Timedelta(days=6):cutoff,row.series_id].mean()
        assert np.isclose(row.mean_7d,expected)
    return query.copy()
ns['forecast_contexts']=capture
for cutoff in pd.to_datetime(['2017-05-31','2017-06-30','2017-07-14','2017-07-28']):
    queries=[]
    for h in [1,2,14]:
        query=ns['direct_forecast'](ns['features'],cutoff,h)
        assert query.date.eq(cutoff+pd.Timedelta(days=h)).all()
        queries.append(query.sort_values('series_id'))
    for column in ns['AR_COLUMNS']:
        assert np.allclose(queries[0][column],queries[-1][column])
# Missing calendar day must remain missing, not turn a 7-day lag into a 7-observation lag.
assert pd.Timestamp('2015-12-25') in ns['wide_sales'].index
assert ns['wide_sales'].loc['2015-12-25'].isna().all()
print('PASS: cutoff labels, all 48 query rows, fixed-origin history, calendar-day lags, rolling means.')

# Check each context boundary without fitting a model: the store strategy must
# contain multiple families from one store, and preserve all leaf query rows.
helper_cell=next(c for c in notebook['cells'] if c['cell_type']=='code' and c['source'].startswith('def calendar_forecast'))
module=ast.parse(helper_cell['source'])
functions=ast.Module(body=[node for node in module.body if isinstance(node,ast.FunctionDef)],type_ignores=[])
exec(compile(functions,'notebook_context_helpers','exec'),ns)
for strategy,expected in [('Per series',48),('By family',4),('By store',12),('Global',1)]:
    calls=[]
    def inspect_context(train,query,columns):
        calls.append(len(train))
        if strategy=='Per series':assert train.series_id.nunique()==1
        if strategy=='By family':assert train.family.nunique()==1 and train.store_nbr.nunique()==12
        if strategy=='By store':assert train.store_nbr.nunique()==1 and train.family.nunique()==4
        if strategy=='Global':assert train.series_id.nunique()==48
        assert set(query.series_id).issubset(set(train.series_id))
        return np.zeros(len(query)),{'seconds':0.0}
    ns['predict_context']=inspect_context
    predictions,timings=ns['calendar_forecast'](ns['features'],pd.Timestamp('2017-06-30'),ns['CALENDAR_COLUMNS'],strategy)
    assert len(calls)==expected and len(timings)==expected
    assert len(predictions)==48*14
    assert not predictions.duplicated(['series_id','date']).any()
print('PASS: per-series/family/store/global grouping boundaries and counts 48/4/12/1.')
