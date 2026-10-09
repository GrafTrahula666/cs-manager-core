"""Patches, meta and the map pool: the part of a tactical FPS that keeps moving.

* Active map pool of 7 from a wider list; each patch can rotate one map out and one in.
* Each patch favours some roles ("AWP patch", "rifle patch", "utility patch").
* Every club has familiarity 0-100 per map; it grows with practice and matches, a new map
  starts everyone from zero (Meta Chameleon and adaptability learn faster).
* Bo3 veto: each side bans its worst map and picks its best; the decider is left over.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .economy import Club

ALL_MAPS = ("Harbor", "Citadel", "Dunes", "Foundry", "Monastery", "Railyard", "Glacier", "Bazaar", "Reactor")
PATCHES = [
    {"name": "AWP-патч", "roles": {"awp": 3.0, "entry": -1.0}},
    {"name": "Райфл-патч", "roles": {"rifler": 2.0, "entry": 2.0, "awp": -2.0}},
    {"name": "Патч гранат", "roles": {"support": 2.5, "igl": 1.5}},
    {"name": "Патч экономики", "roles": {"lurker": 2.0, "igl": 1.0}},
]


@dataclass
class Meta:
    pool: list[str] = field(default_factory=lambda: list(ALL_MAPS[:7]))
    patch: dict = field(default_factory=lambda: {"name": "Старт", "roles": {}})
    familiarity: dict[tuple[str, str], float] = field(default_factory=dict)  # (club, map)
    history: list[str] = field(default_factory=list)

    def fam(self, club: Club, m: str) -> float:
        return self.familiarity.get((club.name, m), 50.0)

    def new_patch(self, week: int, rng: random.Random) -> str:
        self.patch = rng.choice(PATCHES)
        line = f"week {week}: вышел {self.patch['name']}"
        if rng.random() < 0.6:
            out = rng.choice(self.pool)
            options = [m for m in ALL_MAPS if m not in self.pool]
            new = rng.choice(options)
            self.pool[self.pool.index(out)] = new
            line += f"; {out} убрали из маппула, добавили {new}"
        self.history.append(line)
        return line

    def practice(self, club: Club, weeks: float = 1.0) -> None:
        """Weekly practice: familiarity grows on the pool and fades on maps out of it."""
        speed = sum(p.stat("adaptability") / 100 * p.mod("meta_adaptation")[1] for p in club.roster) / max(1, len(club.roster))
        for m in ALL_MAPS:
            key = (club.name, m)
            f = self.familiarity.get(key, 50.0 if m in self.pool else 0.0)
            if m in self.pool:
                f += (100 - f) * 0.03 * (0.5 + speed) * weeks
            else:
                f *= 0.98
            self.familiarity[key] = f

    def veto(self, a: Club, b: Club, maps: int = 3) -> list[str]:
        """Ban the worst matchup, pick the best one (familiarity vs the opponent's); the rest decide."""
        pool = list(self.pool)
        order = [a, b, a, b, a, b]
        picks: list[str] = []
        for i, side in enumerate(order):
            if len(pool) == 1:
                break
            ranked = sorted(pool, key=lambda m: self.fam(side, m) - self.fam(b if side is a else a, m))
            if i < 2 or (maps == 3 and i >= 4):
                pool.remove(ranked[0])                 # ban
            elif len(picks) < maps - 1:
                picks.append(ranked[-1])               # pick
                pool.remove(ranked[-1])
            else:
                pool.remove(ranked[0])
        return (picks + pool)[:maps]

    def map_bonus(self, club: Club, m: str) -> float:
        return (self.fam(club, m) - 50) / 12

    def after_map(self, club: Club, m: str) -> None:
        key = (club.name, m)
        self.familiarity[key] = min(100.0, self.familiarity.get(key, 50.0) + 1.5)
