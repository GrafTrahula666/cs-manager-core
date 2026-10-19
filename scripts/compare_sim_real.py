"""Measure simulated maps and real demo records the same way and print them side by side.

    python scripts/compare_sim_real.py --maps 400                    # simulation only
    python scripts/compare_sim_real.py --maps 400 --real real.jsonl  # against parsed demos

Simulated maps are played by the strongest clubs of a generated world (pro-level rosters),
with the same engine and defaults the season uses but no meta or form context. Real records
come from scripts/demo_analysis.py. The table is a comparison: with fewer than 2000 real rounds
every row says it is not a calibration.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csmcore.engine import play_map  # noqa: E402
from csmcore.matchstats import compare, from_sim, metrics, table  # noqa: E402
from csmcore.worldgen import generate  # noqa: E402


def sim_maps(n: int, seed: int, top: int = 30) -> list[dict]:
    clubs, *_ = generate(seed, 120)
    clubs = sorted(clubs, key=lambda c: -sum(p.overall() for p in c.lineup()))[:top]
    rng = random.Random(seed)
    out = []
    for i in range(n):
        a, b = rng.sample(clubs, 2)
        la, lb = a.lineup(), b.lineup()
        out.append(from_sim(play_map(la, lb, seed=seed * 100_000 + i), la, lb))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--real")
    ap.add_argument("--json")
    a = ap.parse_args()
    sim = metrics(sim_maps(a.maps, a.seed))
    real = {}
    if a.real:
        with open(a.real, encoding="utf-8") as fh:
            real = metrics([json.loads(line) for line in fh if line.strip()])
    rows = compare(sim, real)
    print(table(rows))
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
