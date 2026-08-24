import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
from v4_release_health import release_health
def test_release_health_schema(tmp_path):
 r=release_health(tmp_path); assert r["schema"]=="tradingpulse.release_health.v1"; assert r["total"]>=7; assert not r["ready"]
