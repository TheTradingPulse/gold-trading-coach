"""Point-in-time V6 professional-zone detector extracted from research.

Pure detection only: no database writes, outcome replay, policy selection, live
promotion, or dashboard effects.
"""
from __future__ import annotations

import hashlib
import numpy as np
import pandas as pd

DETECTOR_VERSION="TP_CANONICAL_PROFESSIONAL_ZONE_1"
TICKS={"GC":.1,"SI":.005,"ES":.25,"NQ":.25,"YM":1.,"RTY":.1,"CL":.01,"NG":.001}


def setup_id(*values):
    return hashlib.sha256("|".join(map(str,values)).encode()).hexdigest()[:32]


def atr(frame,n=14):
    pc=frame.close.shift();tr=pd.concat([frame.high-frame.low,(frame.high-pc).abs(),(frame.low-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()


def known_series(series,duration):
    x=series.copy();x.index=x.index+pd.Timedelta(duration);return x


def prior(series,ts):
    i=series.index.searchsorted(ts,side="right")-1
    return float(series.iloc[i]) if i>=0 and pd.notna(series.iloc[i]) else None


def context_frames(m15,h1):
    ma20=m15.close.ewm(span=20,adjust=False).mean();ma50=m15.close.ewm(span=50,adjust=False).mean()
    trend=pd.DataFrame({"ma20":ma20,"ma50":ma50,"slope":ma20-ma20.shift(3)})
    trend.index=trend.index+pd.Timedelta("15min")
    hi=h1.high.rolling(20,min_periods=20).max();lo=h1.low.rolling(20,min_periods=20).min()
    curve=known_series((h1.close-lo)/(hi-lo).replace(0,np.nan),"1h")
    return trend,curve


def detect_professional_zones(symbol,m5,m15,h1,max_return_bars=2016):
    symbol=str(symbol).upper();tick=TICKS[symbol];x=m5.copy();x["atr"]=atr(x)
    rng=(x.high-x.low).replace(0,np.nan);x["body_ratio"]=(x.close-x.open).abs()/rng
    base_ok=(x.body_ratio<=.5)&(rng<=1.5*x.atr)&x.atr.notna();trend,curve=context_frames(m15,h1)
    hi=x.high.to_numpy(float);lo=x.low.to_numpy(float);op=x.open.to_numpy(float);cl=x.close.to_numpy(float)
    at=x.atr.to_numpy(float);ok=base_ok.to_numpy(bool);idx=x.index;rows=[];i=55
    while i<len(x)-10:
        if not ok[i]:i+=1;continue
        start=i;end=i
        while end+1<len(x)-4 and end-start+1<6 and ok[end+1]:
            union=max(hi[start:end+2])-min(lo[start:end+2])
            if union>2*at[start]:break
            end+=1
        count=end-start+1;dep_start=end+1;dep_end=end+3
        zone_hi=float(max(hi[start:end+1]));zone_lo=float(min(lo[start:end+1]));width=zone_hi-zone_lo
        if width<=0 or not np.isfinite(at[start]):i=end+1;continue
        up=float(max(hi[dep_start:dep_end+1])-zone_hi);down=float(zone_lo-min(lo[dep_start:dep_end+1]))
        direction="LONG" if up>down and up>=1.5*width else ("SHORT" if down>up and down>=1.5*width else None)
        if direction is None:i=end+1;continue
        dep_ratio=(up if direction=="LONG" else down)/width
        prior_hi=float(max(hi[max(0,start-20):start]));prior_lo=float(min(lo[max(0,start-20):start]))
        breakout=(max(hi[dep_start:dep_end+1])>prior_hi) if direction=="LONG" else (min(lo[dep_start:dep_end+1])<prior_lo)
        move_out=(dep_ratio>=2 and (cl[dep_end]>zone_hi if direction=="LONG" else cl[dep_end]<zone_lo))
        strength=2 if move_out and breakout else (1 if move_out or breakout else 0)
        if strength==0:i=end+1;continue
        formed=idx[dep_end]+pd.Timedelta("5min");prox=zone_hi if direction=="LONG" else zone_lo;dist=zone_lo if direction=="LONG" else zone_hi
        entry_j=None
        for j in range(dep_end+1,min(len(x),dep_end+1+max_return_bars)):
            if lo[j]<=prox<=hi[j]:entry_j=j;break
        if entry_j is None:i=end+1;continue
        entry_time=idx[entry_j];entry=prox;stop=dist-tick if direction=="LONG" else dist+tick;risk=abs(entry-stop)
        if risk<=0:i=end+1;continue
        ph=float(max(hi[max(0,start-100):start]));pl=float(min(lo[max(0,start-100):start]))
        room=max(0,(ph-entry)/risk if direction=="LONG" else (entry-pl)/risk);profit=2 if room>=3 else (1 if room>=2 else 0)
        if profit==0:i=end+1;continue
        pos=trend.index.searchsorted(entry_time,side="right")-1
        if pos>=0:
            tr=trend.iloc[pos];aligned=(direction=="LONG" and tr.ma20>tr.ma50 and tr.slope>0) or (direction=="SHORT" and tr.ma20<tr.ma50 and tr.slope<0)
            opposite=(direction=="LONG" and tr.ma20<tr.ma50 and tr.slope<0) or (direction=="SHORT" and tr.ma20>tr.ma50 and tr.slope>0)
            trend_score=2 if aligned else (0 if opposite else 1)
        else:trend_score=1
        cp=prior(curve,entry_time)
        if cp is None:curve_score=.5
        elif direction=="LONG":curve_score=1 if cp<=.33 else (.5 if cp<=.67 else 0)
        else:curve_score=1 if cp>=.67 else (.5 if cp>=.33 else 0)
        time_score=1 if count<=3 else .5;freshness=2;score=strength+time_score+freshness+trend_score+curve_score+profit
        arrival=float(cl[start]-cl[max(0,start-3)]);pattern=("DBR" if arrival<0 else "RBR") if direction=="LONG" else ("RBD" if arrival>0 else "DBD")
        rows.append({"zone_id":setup_id(symbol,idx[start],idx[end],direction,round(prox,8)),"symbol":symbol,"pattern":pattern,"direction":direction,
          "base_start":idx[start].isoformat(),"base_end":idx[end].isoformat(),"formed_at":formed.isoformat(),"entry_ts":entry_time.isoformat(),
          "proximal":prox,"distal":dist,"entry":entry,"stop":stop,"risk":risk,"risk_ticks":risk/tick,"base_candles":count,
          "departure_ratio":dep_ratio,"breakout":int(breakout),"strength_score":strength,"time_score":time_score,"freshness_score":freshness,
          "trend_score":trend_score,"curve_score":curve_score,"profit_score":profit,"profit_room_r":room,"ota_score":score,"curve_position":cp})
        i=end+1
    return pd.DataFrame(rows)
