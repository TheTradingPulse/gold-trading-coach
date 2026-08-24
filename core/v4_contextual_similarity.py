from __future__ import annotations
IDENTITY=("symbol","setup_type","direction")
CAT=("session_utc","trend_15m","trend_1h","trend_4h","trend_d","volatility_15m","lifecycle","grade")
NUM=("score10","atr_pct_15m","atr_pct_1h","zone_quality","zone_freshness","zone_retests","zone_width","opposing_room_points","projected_rr","htf_aligned_count","reason_local_trend","reason_htf","reason_nesting","reason_room")

def _same(a,b):return a is not None and b is not None and str(a).lower()==str(b).lower()
def similarity(a,b):
    for k in IDENTITY:
        if a.get(k) and b.get(k) and not _same(a[k],b[k]):return 0.0
    score=12.0;weight=12.0
    for k in CAT:
        if a.get(k) is None or b.get(k) is None:continue
        weight+=1.5;score+=1.5 if _same(a[k],b[k]) else 0
    for k in NUM:
        try:av=float(a.get(k));bv=float(b.get(k))
        except:continue
        weight+=1;scale=max(abs(av),abs(bv),1.0);score+=max(0,1-abs(av-bv)/scale)
    return score/weight if weight else 0

def nearest_scored(rows,feature,limit=750,minimum=.68):
    ranked=[]
    for r in rows:
        f=r.get('_features',r);s=similarity(feature,f)
        if s>=minimum:ranked.append((s,r))
    ranked.sort(key=lambda z:z[0],reverse=True);return ranked[:limit]

def nearest(rows,feature,limit=500,minimum=.68):
    return [r for _,r in nearest_scored(rows,feature,limit,minimum)]

def stats(rows):
    trig=[r for r in rows if r.get('entered')];n=len(trig);h3=sum(bool(r.get('primary_hit')) for r in trig);h5=sum(bool(r.get('stretch_hit')) for r in trig)
    def avg(k):
        v=[float(r[k]) for r in trig if r.get(k) is not None];return round(sum(v)/len(v),3) if v else None
    return {"n":len(rows),"triggered":n,"hit_3r":h3,"hit_5r":h5,"hit_3r_pct":round(100*h3/n,2) if n else 0,
      "hit_5r_pct":round(100*h5/n,2) if n else 0,"avg_mfe_r":avg('mfe_r'),"avg_mae_r":avg('mae_r')}

def weighted_stats(scored_rows):
    trig=[(s,r) for s,r in scored_rows if r.get('entered')]
    if not trig:return {"n":len(scored_rows),"triggered":0,"hit_3r":0,"hit_5r":0,"hit_3r_pct":0,"hit_5r_pct":0,"mean_similarity":0}
    # Similarity weights emphasize the closest analogues without allowing one row to dominate.
    weights=[max(.05,(s-.60)/.40)**2 for s,_ in trig]; sw=sum(weights)
    h3=sum(w*bool(r.get('primary_hit')) for w,(_,r) in zip(weights,trig)); h5=sum(w*bool(r.get('stretch_hit')) for w,(_,r) in zip(weights,trig))
    # Integer Wilson counts remain conservative; weighted rates are diagnostic only.
    raw3=sum(bool(r.get('primary_hit')) for _,r in trig); raw5=sum(bool(r.get('stretch_hit')) for _,r in trig)
    return {"n":len(scored_rows),"triggered":len(trig),"hit_3r":raw3,"hit_5r":raw5,
      "hit_3r_pct":round(100*raw3/len(trig),2),"hit_5r_pct":round(100*raw5/len(trig),2),
      "weighted_3r_pct":round(100*h3/sw,2),"weighted_5r_pct":round(100*h5/sw,2),
      "mean_similarity":round(sum(s for s,_ in trig)/len(trig),4)}
