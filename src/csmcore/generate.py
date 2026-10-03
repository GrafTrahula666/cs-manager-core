"""Procedural players and the concept's example players."""
from __future__ import annotations

import json
import random
from importlib import resources

from .player import PERSONALITY, STATS, Player
from .traits import roll_traits

# Role -> which stats get a boost and which trait families are more likely (non-uniform RNG).
ROLE_PROFILE = {
    "entry": ({"aim": 8, "reaction": 8, "movement": 6}, {"mechanics": 2.0, "match": 1.5}),
    "awp": ({"aim": 6, "reaction": 10, "positioning": 5}, {"mechanics": 2.0}),
    "igl": ({"game_sense": 10, "leadership": 15, "communication": 10, "analytical": 10}, {"team": 2.5, "learning": 1.5}),
    "support": ({"utility_iq": 10, "teamwork": 10}, {"team": 1.8}),
    "lurker": ({"timing": 10, "map_awareness": 8}, {"learning": 1.5}),
    "rifler": ({"weapon_control": 6}, {}),
}


def make_player(name: str, level: float, rng: random.Random, role: str = "rifler", age: int | None = None) -> Player:
    from .traits import library
    boosts, fam_w = ROLE_PROFILE[role]
    stats = {s: max(1.0, min(100.0, rng.gauss(level, 7) + boosts.get(s, 0))) for s in STATS}
    personality = {k: max(0.0, min(100.0, rng.gauss(50, 18))) for k in PERSONALITY}
    weights = {tid: fam_w.get(t.family, 1.0) for tid, t in library().items()}
    return Player(name, stats, personality, roll_traits(rng, weights),
                  age=age if age is not None else rng.randint(16, 30), role=role)


def concept_examples() -> dict[str, Player]:
    raw = json.loads(resources.files("csmcore.data").joinpath("examples.json").read_text(encoding="utf-8"))
    out = {}
    for d in raw["players"]:
        out[d["name"]] = Player(d["name"], d["stats"], d["personality"], d["traits"],
                                age=d["age"], country=d["country"], role=d["role"])
    return out
