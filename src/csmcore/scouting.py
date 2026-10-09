"""Scouting with uncertainty (concept section 5, FM's attribute masking).

The manager never reads true stats. A club holds `knowledge` 0-100 of each player; the visible
value is a range around the truth (with a fixed per-player bias that fades as knowledge grows),
plus a confidence number. Personality and hidden traits are revealed only past thresholds.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .economy import Club
from .player import PERSONALITY, STATS, Player
from .traits import library

TRAIT_REVEAL = 45        # knowledge needed to see ordinary Gold Traits
HIDDEN_TRAIT_REVEAL = 80  # traits marked hidden_until="behaviour"
PERSONALITY_REVEAL = 60


@dataclass
class Report:
    player: str
    knowledge: float
    confidence: float
    stats: dict[str, tuple[int, int]]
    traits: list[str]
    personality: dict[str, str] = field(default_factory=dict)
    potential: str = "?"


class Scouting:
    def __init__(self, club: Club, seed: int = 0) -> None:
        self.club = club
        self.knowledge: dict[str, float] = {}
        self.seed = seed

    def observe(self, p: Player, weeks: float = 1.0, source: str = "scout") -> float:
        """Learning curve: fast at first, slow near 100. Teammates are known best."""
        rate = {"scout": 0.5 + self.club.scout_quality / 100, "match": 0.6, "teammate": 2.0}[source]
        k = self.knowledge.get(p.name, 0.0)
        k = 100 - (100 - k) * (1 - min(0.9, 0.08 * rate)) ** weeks
        self.knowledge[p.name] = min(100.0, k)
        return self.knowledge[p.name]

    def report(self, p: Player) -> Report:
        k = self.knowledge.get(p.name, 0.0)
        width = 30 * (1 - k / 100) + 1          # half-width of the range
        rng = random.Random(f"{self.seed}:{self.club.name}:{p.name}")  # stable bias per scout/player
        stats = {}
        for s in STATS:
            bias = rng.gauss(0, 8) * (1 - k / 100)
            centre = p.stats.get(s, 50.0) + bias
            stats[s] = (max(0, round(centre - width)), min(100, round(centre + width)))
        lib = library()
        traits = [t for t in p.traits
                  if k >= (HIDDEN_TRAIT_REVEAL if lib[t].hidden_until else TRAIT_REVEAL)]
        persona = {}
        if k >= PERSONALITY_REVEAL:
            for axis in PERSONALITY:
                v = p.p(axis)
                persona[axis] = "низко" if v < 35 else "высоко" if v > 65 else "средне"
        pot = "?"
        if k >= 50:
            gap = p.potential - p.overall()
            pot = "большой" if gap > 10 else "есть" if gap > 4 else "на пике"
        return Report(p.name, round(k), round(min(95, 20 + 0.75 * k)), stats, traits, persona, pot)
