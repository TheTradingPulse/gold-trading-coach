from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json
import pandas as pd
from .v4_blind_metrics import summarize, grouped_metrics

class FrozenRuleGuard:
    def __init__(self, paths):
        self.paths=[Path(p) for p in paths]
        self.before={str(p): self._hash(p) for p in self.paths if p.exists()}
    @staticmethod
    def _hash(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    def assert_unchanged(self):
        after={str(p): self._hash(p) for p in self.paths if p.exists()}
        if after != self.before:
            raise RuntimeError("FROZEN RULE GUARD FAILED: research rules changed during blind validation")
        return True

class FiveYearBlindValidationLab:
    """
    Aggregates replay observations produced by the existing TradingPulse engine.
    It deliberately does not learn thresholds or mutate scoring.
    """
    DIMENSIONS=("symbol","year","month","session_utc","setup_type","direction","tier","grade")

    def __init__(self, output_root=r"C:\TradingPulse\research_data\v4\five_year_blind_validation"):
        self.root=Path(output_root); self.root.mkdir(parents=True,exist_ok=True)

    def analyze(self, observations: pd.DataFrame):
        d=observations.copy()
        if "as_of" in d:
            d["as_of"]=pd.to_datetime(d["as_of"],utc=True)
            d["year"]=d["as_of"].dt.year
            d["month"]=d["as_of"].dt.to_period("M").astype(str)
        report={
            "generated_utc":datetime.now(timezone.utc).isoformat(),
            "rows":len(d),
            "primary_3r":summarize(d,3),
            "stretch_5r":summarize(d,5),
        }
        for target,name in ((3,"3r"),(5,"5r")):
            for dim in self.DIMENSIONS:
                if dim in d.columns:
                    grouped_metrics(d,[dim],target).to_csv(self.root/f"metrics_{name}_by_{dim}.csv",index=False)
        combo=[x for x in ("symbol","year","tier","direction","setup_type","session_utc") if x in d.columns]
        if combo:
            grouped_metrics(d,combo,3).to_csv(self.root/"metrics_3r_multidimensional.csv",index=False)
            grouped_metrics(d,combo,5).to_csv(self.root/"metrics_5r_multidimensional.csv",index=False)
        (self.root/"blind_validation_summary.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        return report
