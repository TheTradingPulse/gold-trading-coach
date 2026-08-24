"""Create a small Phase 3L report ZIP without local replay checkpoints."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "research_data/v7/diamond_lab/overnight_20260823"
ALLOWED = {".json", ".csv", ".txt", ".log"}


def main(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in REPORT_ROOT.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED]
    if not files:
        raise SystemExit(f"No Phase 3L report files found in {REPORT_ROOT}")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, arcname=path.name)
    print(f"REPORT FILES PACKAGED: {len(files)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.output))
