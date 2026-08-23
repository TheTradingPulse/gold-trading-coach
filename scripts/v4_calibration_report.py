import json,argparse
p=argparse.ArgumentParser();p.add_argument("--file",default="research_data/v4_calibration.json");a=p.parse_args()
r=json.load(open(a.file,encoding="utf-8"))
print("V4 CALIBRATION",r["version"],"ROWS",r["rows"],"MONOTONIC",r["score_monotonic"])
valid=[g for g in r["groups"] if g.get("sample_ok") and "bucket" in g]
valid.sort(key=lambda x:(x["evidence_quality10"] or -1),reverse=True)
print("\nTOP EVIDENCE GROUPS")
for g in valid[:30]:
    print(g["symbol"],g["setup_type"],g["direction"],g["bucket"],
          "Q",g["evidence_quality10"],"TRIG",g["triggered"],
          "3R%",g["hit_3r_pct"],"5R%",g["hit_5r_pct"])
