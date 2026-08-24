from __future__ import annotations
import argparse,csv,json,math,sqlite3,statistics
from collections import defaultdict
from pathlib import Path

BUCKETS=[(0,6,'<6'),(6,7,'6-6.9'),(7,8,'7-7.9'),(8,8.5,'8-8.4'),(8.5,9,'8.5-8.9'),(9,99,'9+')]
FEATURES=['trend_15m','trend_1h','trend_4h','trend_d','volatility_15m','session_utc','lifecycle','grade','htf_aligned_count','zone_retests','projected_rr','reason_zone_quality','reason_local_trend','reason_htf','reason_lifecycle','reason_nesting','reason_room','reason_width','atr_pct_15m','atr_pct_1h','zone_freshness','zone_quality']

def bucket(x):
    x=float(x or 0)
    return next((n for lo,hi,n in BUCKETS if lo<=x<hi),'9+')

def wilson(h,n,z=1.96):
    if not n:return 0.0
    p=h/n; den=1+z*z/n
    return max(0.0,(p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/den)

def stats(rows):
    trig=[r for r in rows if r['entered']]
    n=len(trig); h3=sum(r['primary_hit'] for r in trig); h5=sum(r['stretch_hit'] for r in trig)
    p3=h3/n if n else 0; p5=h5/n if n else 0
    # EV assumes non-hit eventually risks 1R. It is deliberately conservative and comparable.
    return {'n':len(rows),'triggered':n,'trigger_pct':round(100*n/len(rows),2) if rows else 0,
            'hit3':h3,'hit5':h5,'p3':round(p3,5),'p5':round(p5,5),
            'w3':round(wilson(h3,n),5),'w5':round(wilson(h5,n),5),
            'ev3':round(4*p3-1,5),'ev5':round(6*p5-1,5),
            'avg_mfe':round(statistics.fmean([r['mfe_r'] for r in trig if r['mfe_r'] is not None]),4) if any(r['mfe_r'] is not None for r in trig) else None,
            'avg_mae':round(statistics.fmean([r['mae_r'] for r in trig if r['mae_r'] is not None]),4) if any(r['mae_r'] is not None for r in trig) else None}

def load(db):
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    out=[]
    for x in con.execute('select * from observations order by as_of,id'):
        r=dict(x)
        try: f=json.loads(r.get('context_json') or '{}')
        except: f={}
        r['_f']=f; out.append(r)
    con.close(); return out

def valbin(v):
    if v is None or v=='':return None
    if isinstance(v,bool):return str(v)
    if isinstance(v,str):return v
    try:
        x=float(v)
        if not math.isfinite(x):return None
        # broad robust bins; enough support for held-out testing
        if x<0:return '<0'
        if x<0.5:return '0-.49'
        if x<1:return '.5-.99'
        if x<2:return '1-1.99'
        if x<3:return '2-2.99'
        if x<5:return '3-4.99'
        if x<8:return '5-7.99'
        if x<10:return '8-9.99'
        if x<20:return '10-19.99'
        if x<50:return '20-49.99'
        if x<80:return '50-79.99'
        return '80+'
    except:return str(v)

def analyze(rows,min_trig=30):
    # chronological 70/30 OOS by unique timestamp
    times=sorted({r['as_of'] for r in rows}); cut=times[max(1,int(len(times)*.70))-1] if times else ''
    dev=[r for r in rows if r['as_of']<=cut]; oos=[r for r in rows if r['as_of']>cut]
    report={'schema':'tradingpulse.overnight.deepdive.v1','rows':len(rows),'cutoff':cut,'development_rows':len(dev),'oos_rows':len(oos),'global':stats(rows)}
    # Raw score ordering on OOS
    score_groups=defaultdict(list)
    for r in oos: score_groups[bucket(r['score10'])].append(r)
    report['oos_score_buckets']={b:stats(score_groups[b]) for *_,b in BUCKETS}
    seq=[report['oos_score_buckets'][b]['w3'] for *_,b in BUCKETS if report['oos_score_buckets'][b]['triggered']>=min_trig]
    report['raw_score_monotonic_oos']=all(a<=b+1e-12 for a,b in zip(seq,seq[1:])) if len(seq)>1 else None
    # Identity groups and score inversions
    ids=defaultdict(list)
    for r in oos: ids[(r['symbol'],r['setup_type'],r['direction'],bucket(r['score10']))].append(r)
    groups=[]
    for k,rs in ids.items():
        s=stats(rs)
        if s['triggered']>=min_trig: groups.append({'symbol':k[0],'setup_type':k[1],'direction':k[2],'bucket':k[3],**s})
    groups.sort(key=lambda x:(x['w3']*.65+x['w5']*.35,x['triggered']),reverse=True)
    report['best_oos_identity_groups']=groups[:40]
    # Feature slices discovered on dev, verified on OOS. No cherry-pick from OOS.
    devmap=defaultdict(list); oosmap=defaultdict(list)
    for r in dev:
        for f in FEATURES:
            b=valbin(r['_f'].get(f))
            if b is not None:devmap[(r['symbol'],r['setup_type'],r['direction'],f,b)].append(r)
    for r in oos:
        for f in FEATURES:
            b=valbin(r['_f'].get(f))
            if b is not None:oosmap[(r['symbol'],r['setup_type'],r['direction'],f,b)].append(r)
    discoveries=[]
    for k,dr in devmap.items():
        ds=stats(dr)
        if ds['triggered']<min_trig:continue
        ors=oosmap.get(k,[]); os=stats(ors)
        if os['triggered']<min_trig:continue
        # Conservative quality uses Wilson 3R majority, 5R secondary, and stability penalty.
        dq=.65*ds['w3']+.35*ds['w5']; oq=.65*os['w3']+.35*os['w5']; stability=max(0,1-abs(dq-oq)/.20)
        q=10*oq*(.70+.30*stability)
        discoveries.append({'symbol':k[0],'setup_type':k[1],'direction':k[2],'feature':k[3],'value':k[4],
                            'dev':ds,'oos':os,'quality10':round(q,3),'stable':abs(dq-oq)<=.10})
    discoveries.sort(key=lambda x:(x['stable'],x['quality10'],x['oos']['triggered']),reverse=True)
    report['verified_context_edges']=discoveries[:100]
    # Recommend features only if repeated OOS support and stability exist.
    byf=defaultdict(list)
    for d in discoveries:
        if d['stable'] and d['quality10']>=3.0:byf[d['feature']].append(d)
    ranked=[]
    for f,ds in byf.items():
        ranked.append({'feature':f,'verified_slices':len(ds),'oos_triggered':sum(x['oos']['triggered'] for x in ds),
                       'mean_quality10':round(statistics.fmean(x['quality10'] for x in ds),3),
                       'max_quality10':max(x['quality10'] for x in ds)})
    ranked.sort(key=lambda x:(x['verified_slices'],x['oos_triggered'],x['mean_quality10']),reverse=True)
    report['feature_priority']=ranked
    report['recommendation']={
      'scoring':'Do not trust raw score rank until held-out score buckets are monotonic. Use identity + verified context evidence as an overlay.',
      'promotion':'Research only. Any production promotion requires repeated OOS/walk-forward ordering and minimum samples.',
      'targets':'Keep 3R primary. Permit 5R only where held-out 5R EV and Wilson evidence exceed the 3R alternative by a material margin.',
      'top_features':[x['feature'] for x in ranked[:8]]}
    return report

def write_csv(report,out):
    p=Path(out)/'verified_context_edges.csv'
    fields=['symbol','setup_type','direction','feature','value','quality10','stable','dev_triggered','dev_p3','dev_p5','oos_triggered','oos_p3','oos_p5','oos_w3','oos_w5','oos_ev3','oos_ev5']
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for x in report['verified_context_edges']:
            w.writerow({'symbol':x['symbol'],'setup_type':x['setup_type'],'direction':x['direction'],'feature':x['feature'],'value':x['value'],'quality10':x['quality10'],'stable':x['stable'],
                        'dev_triggered':x['dev']['triggered'],'dev_p3':x['dev']['p3'],'dev_p5':x['dev']['p5'],'oos_triggered':x['oos']['triggered'],'oos_p3':x['oos']['p3'],'oos_p5':x['oos']['p5'],'oos_w3':x['oos']['w3'],'oos_w5':x['oos']['w5'],'oos_ev3':x['oos']['ev3'],'oos_ev5':x['oos']['ev5']})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--db',default='research_data/v4/context_evidence_v4.db');ap.add_argument('--out',default='research_data/v4/overnight_deep_dive');ap.add_argument('--min-triggered',type=int,default=30);a=ap.parse_args()
    p=Path(a.db)
    if not p.exists() or p.stat().st_size==0:raise SystemExit(f'Context evidence missing/empty: {p}')
    rows=load(p); out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    r=analyze(rows,a.min_triggered);(out/'deep_dive_report.json').write_text(json.dumps(r,indent=2),encoding='utf-8');write_csv(r,out)
    print('ROWS',r['rows'],'OOS',r['oos_rows'],'RAW_SCORE_MONOTONIC_OOS',r['raw_score_monotonic_oos'])
    print('TOP VERIFIED FEATURES')
    for x in r['feature_priority'][:12]:print(x)
    print('REPORT',out/'deep_dive_report.json');print('CSV',out/'verified_context_edges.csv')
if __name__=='__main__':main()
