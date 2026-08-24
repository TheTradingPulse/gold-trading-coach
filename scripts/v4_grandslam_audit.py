import sys,json,argparse,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'core'))
from v4_grandslam_policy import decide_grandslam
p=argparse.ArgumentParser();p.add_argument('--evidence',default='research_data/v4/context_evidence_v4.db');a=p.parse_args()
db=Path(a.evidence)
if not db.exists() or db.stat().st_size==0: raise SystemExit(f'Evidence V4 missing/empty: {db}')
conn=sqlite3.connect(db); conn.row_factory=sqlite3.Row
q='''SELECT symbol,setup_type,direction,COUNT(*) n,SUM(entered) triggered,SUM(primary_hit) hit_3r,SUM(stretch_hit) hit_5r,AVG(score10) avg_score FROM observations GROUP BY symbol,setup_type,direction'''
rows=[]
for x in conn.execute(q):
 s=dict(x); d=decide_grandslam(s,completeness=.75,mean_similarity=.76,projected_rr=None,actionable=True);rows.append({**s,**d})
conn.close();rows.sort(key=lambda r:(r.get('tier')=='GRAND_SLAM',r.get('tier')=='ELITE',r.get('evidence_edge',-99)),reverse=True)
print(json.dumps({'policy':'V4_GRANDSLAM_1','groups':rows},indent=2,default=str))
print('\n[NOTE] This audit is broad identity-level evidence. Live contextual classification remains stricter and uses nearest contextual analogues.')
