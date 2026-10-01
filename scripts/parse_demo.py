"""Parse one CS2 demo into a compact kills table, then delete the demo.

UNTESTED SKELETON: written against demoparser2's documented API, not yet run on a real demo.
Usage: python scripts/parse_demo.py path/to/match.dem out_dir/ [--keep]
Raw demos are big (100-400 MB); we keep only the small aggregate table.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(demo: str, out_dir: str, keep: bool = False) -> None:
    from demoparser2 import DemoParser  # pip install -e ".[data]"

    parser = DemoParser(demo)
    kills = parser.parse_event(
        "player_death",
        player=["X", "Y", "team_num", "current_equip_value"],
        other=["total_rounds_played"],
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kills.to_parquet(out / (Path(demo).stem + "_kills.parquet"))
    if not keep:
        Path(demo).unlink()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--keep" in sys.argv)
