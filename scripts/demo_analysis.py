"""Parse local CS2 demos into compact round records (rounds, kills, weapons, economy, grenades,
bomb, results) and print what they contain.

    pip install -e ".[data]"        # demoparser2, pandas, pyarrow
    python scripts/demo_analysis.py match1.dem match2.dem --out real.jsonl

Demos are read from disk only; this script downloads nothing (HLTV is not reachable from the
cloud sandbox, and its terms should be checked before any automated download). The output
feeds scripts/compare_sim_real.py. Raw demos are 100-400 MB; the records are a few hundred KB.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csmcore.demo_records import demo_to_record  # noqa: E402
from csmcore.matchstats import metrics  # noqa: E402


def summary(rec: dict) -> str:
    rs = rec["rounds"]
    kills = sum(len(r["kills"]) for r in rs)
    plants = sum(1 for r in rs if r["bomb"])
    nades = sum(sum(r["nades"]) for r in rs)
    kinds = {}
    for r in rs:
        for k in r["kinds"]:
            kinds[k] = kinds.get(k, 0) + 1
    return (f"{rec['name']}: {rec['map']} {rec['score'][0]}:{rec['score'][1]}, {len(rs)} раундов, {kills} убийств, "
            f"закладок {plants}, гранат {nades}, закупки {kinds}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("demos", nargs="+")
    ap.add_argument("--out", default="real.jsonl")
    a = ap.parse_args()
    from demoparser2 import DemoParser

    recs = []
    for path in a.demos:
        try:
            rec = demo_to_record(DemoParser(path), Path(path).stem)
        except Exception as e:            # one broken demo should not stop a batch
            print(f"{path}: пропущено ({e})", file=sys.stderr)
            continue
        recs.append(rec)
        print(summary(rec))
    with open(a.out, "w", encoding="utf-8") as fh:
        for rec in recs:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    m = metrics(recs)
    print(f"\n{len(recs)} карт, {m['kills_per_round']['n']} раундов -> {a.out}")
    for k in ("kills_per_round", "first_kill_round_win", "pistol_next_round_win", "clutch_1v2_win", "bomb_plant_rate"):
        print(f"  {k}: {m[k]['value']} (n={m[k]['n']})")
    return 0 if recs else 1


if __name__ == "__main__":
    raise SystemExit(main())
