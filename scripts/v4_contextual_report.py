import sys,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'core'))
from v4_context_evidence import load
from v4_contextual_similarity import stats
p=argparse.ArgumentParser();p.add_argument('--evidence',default='research_data/v4/context_evidence_v4.db');a=p.parse_args();rows=load(a.evidence)
print('ROWS',len(rows));print(json.dumps(stats(rows),indent=2))
by={}
for r in rows:by.setdefault(r['symbol'],[]).append(r)
print('BY MARKET');print(json.dumps({k:stats(v) for k,v in sorted(by.items())},indent=2))
