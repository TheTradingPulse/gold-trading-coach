from pathlib import Path
import json
p=Path('research_data/v4/overnight_deep_dive/deep_dive_report.json')
if not p.exists(): print('Overnight report not finished yet.'); raise SystemExit(0)
r=json.loads(p.read_text(encoding='utf-8'))
print('ROWS:',r['rows']);print('OOS ROWS:',r['oos_rows']);print('RAW SCORE MONOTONIC OOS:',r['raw_score_monotonic_oos']);print('TOP FEATURES:')
for x in r.get('feature_priority',[])[:10]:print(' ',x['feature'],'verified slices',x['verified_slices'],'mean quality',x['mean_quality10'])
