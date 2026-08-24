import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
from v4_release_health import release_health
r=release_health(Path(__file__).resolve().parents[1]); print(json.dumps(r,indent=2)); raise SystemExit(0 if r["ready"] else 2)
