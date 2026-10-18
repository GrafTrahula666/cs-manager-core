"""Long runs of the whole world: time, memory, save size, invariants and story rates per season.

    python scripts/soak_world.py --seeds 1 2 3 --seasons 10 --clubs 120
    python scripts/soak_world.py --seeds 7 --seasons 30 --clubs 120 --json out.json

Prints one line per season and fails (exit 1) if any invariant breaks.
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csmcore import save  # noqa: E402
from csmcore.emergent.history import legends  # noqa: E402
from csmcore.emergent.invariants import engine as engine_inv, social as social_inv  # noqa: E402
from csmcore.game import Game  # noqa: E402

SOCIAL = ("public_jab", "private_confront", "freeze_out", "side_with", "complain", "leak", "ask_to_leave",
          "mediate", "reconcile", "mentor", "praise_publicly", "outwork", "seek_spotlight")


def run(seed: int, seasons: int, clubs: int) -> dict:
    g = Game.new(seed=seed, n_clubs=clubs)
    ew = g.sysm.emergent
    out = {"seed": seed, "clubs": clubs, "seasons": []}
    bad_total = 0
    for s in range(seasons):
        before = dict(ew.counts)
        t = time.perf_counter()
        for _ in range(52):
            g.advance()
        dt = time.perf_counter() - t
        data = save.dumps(g)
        bad = social_inv(g.clubs, g.graph) + engine_inv(ew)
        bad_total += len(bad)
        per = {k: ew.counts.get(k, 0) - before.get(k, 0) for k in ew.counts}
        neg = sum(per.get(k, 0) for k in ("public_jab", "private_confront", "freeze_out", "side_with", "leak"))
        row = {"season": s + 1, "sec": round(dt, 2), "save_kb": len(data) // 1024, "facts": len(ew.facts.facts),
               "minds": len(ew.minds.minds), "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
               "hostile_per_club": round(neg / clubs, 2), "kinds": {k: per.get(k, 0) for k in SOCIAL},
               "transfers": per.get("transfer", 0), "articles": per.get("article", 0),
               "revenge": per.get("beat_former_club", 0), "retro": per.get("retrospective", 0),
               "violations": bad[:3]}
        out["seasons"].append(row)
        print(f"seed {seed} S{s + 1:>2}: {dt:5.1f}s save {row['save_kb']:>5}KB facts {row['facts']:>6} minds {row['minds']:>5} "
              f"rss {row['rss_mb']}MB hostile/club {row['hostile_per_club']} transfers {row['transfers']} "
              f"articles {row['articles']} revenge {row['revenge']} retro {row['retro']}"
              + (f"  VIOLATIONS {bad[:2]}" if bad else ""), flush=True)
    out["legends"] = legends(ew, 5, 0)
    out["violations"] = bad_total
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1])
    ap.add_argument("--seasons", type=int, default=5)
    ap.add_argument("--clubs", type=int, default=120)
    ap.add_argument("--json")
    a = ap.parse_args()
    results = [run(s, a.seasons, a.clubs) for s in a.seeds]
    if a.json:
        Path(a.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if any(r["violations"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
