from __future__ import annotations
import sys, json, math, hashlib
from dataclasses import asdict, is_dataclass
from pathlib import Path
from contextlib import contextmanager
import pandas as pd

PROJECT_ROOT=Path(__file__).resolve().parents[1]
for p in (PROJECT_ROOT, PROJECT_ROOT/"core", PROJECT_ROOT/"analysis"):
    if str(p) not in sys.path: sys.path.insert(0,str(p))

import market_state_builder as msb
from setup_candidate_engine import build_setup_candidates
from v4_market_warehouse import MarketWarehouse

UNIVERSE=("GC","SI","ES","NQ","YM","RTY","CL","NG")
CONTEXT_TFS=("W","D","4H","1H","15m","5m","1m")

def _utc(v):
    t=pd.Timestamp(v)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")

def _objdict(obj):
    if obj is None: return {}
    if isinstance(obj,dict): return dict(obj)
    if hasattr(obj,"to_dict"):
        try: return obj.to_dict()
        except Exception: pass
    if is_dataclass(obj): return asdict(obj)
    return {k:v for k,v in vars(obj).items() if not k.startswith("_")} if hasattr(obj,"__dict__") else {}

class WarehouseMarketStateAdapter:
    """Runs the canonical MarketState builder against V4 warehouse candles at an as-of cutoff."""
    def __init__(self, warehouse_path="research_data/v4/market_warehouse.db", provider="yahoo"):
        self.wh=MarketWarehouse(warehouse_path); self.provider=provider

    def load(self,symbol,timeframe,limit=500,as_of=None):
        if as_of is None: raise ValueError("Canonical replay requires explicit as_of cutoff")
        df=self.wh.read(symbol,timeframe,as_of=as_of,limit=limit,provider=self.provider)
        cutoff=_utc(as_of)
        if len(df) and df.index.max()>cutoff: raise AssertionError("LOOK-AHEAD VIOLATION at warehouse boundary")
        return df.drop(columns=["provider"],errors="ignore")

    @contextmanager
    def patch_loader(self,symbol,as_of):
        original=msb.load_market_data
        adapter=self
        def replay_loader(timeframe, limit=500, as_of=None, *args, **kwargs):
            cutoff=as_of if as_of is not None else as_of_outer
            return adapter.load(symbol,timeframe,limit=limit,as_of=cutoff)
        as_of_outer=as_of
        msb.load_market_data=replay_loader
        try: yield
        finally: msb.load_market_data=original

    def build_state(self,symbol,as_of):
        symbol=symbol.upper()
        if symbol not in UNIVERSE: raise KeyError(symbol)
        cutoff=_utc(as_of)
        with self.patch_loader(symbol,cutoff):
            # Canonical builder already owns deterministic LIVE/REPLAY behavior.
            try:
                from market_clock import replay_clock
                state=msb.build_market_state(symbol,clock=replay_clock(cutoff))
            except TypeError:
                state=msb.build_market_state(symbol)
        # Independent final boundary assertion.
        for tf in CONTEXT_TFS:
            df=self.wh.read(symbol,tf,as_of=cutoff,limit=3,provider=self.provider)
            if len(df) and df.index.max()>cutoff: raise AssertionError(f"LOOK-AHEAD VIOLATION {symbol} {tf}")
        return state

    def candidates(self,symbol,as_of):
        state=self.build_state(symbol,as_of)
        return state, build_setup_candidates(state)

def candidate_record(symbol,as_of,state,candidate):
    d=_objdict(candidate)
    cid=d.get("candidate_id") or d.get("id")
    if not cid:
        raw=json.dumps({"s":symbol,"t":str(as_of),"z":d.get("zone_type"),"e":d.get("projected_entry"),
                        "x":d.get("projected_stop")},sort_keys=True,default=str)
        cid=hashlib.sha256(raw.encode()).hexdigest()[:24]
    return {
      "symbol":symbol.upper(),"as_of":_utc(as_of).isoformat(),"setup_id":str(cid),
      "timeframe":d.get("timeframe") or d.get("zone_timeframe"),
      "setup_type":d.get("setup_type") or d.get("zone_type") or d.get("type"),
      "direction":d.get("direction") or ("LONG" if str(d.get("zone_type","")).lower()=="demand" else "SHORT"),
      "score":d.get("setup_score",d.get("quality_score",d.get("score"))),
      "grade":d.get("grade"),"lifecycle":d.get("lifecycle"),
      "is_actionable":bool(d.get("is_actionable",False)),
      "entry":d.get("projected_entry",d.get("entry")),
      "stop":d.get("projected_stop",d.get("stop")),
      "t1":d.get("projected_target",d.get("target")),
      "t2":d.get("target_2"),"t3":d.get("target_3"),
      "projected_rr":d.get("projected_rr"),
      "reasons":d.get("reasons",[]),
      "candidate_payload":d,
      "market_state":{"market_bias":getattr(state,"market_bias",None),
                      "setup_state":getattr(state,"setup_state",None),
                      "setup_direction":getattr(state,"setup_direction",None),
                      "current_price":getattr(state,"current_price",None),
                      "is_actionable":getattr(state,"is_actionable",None)}
    }
