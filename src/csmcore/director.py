"""Drama director, after RimWorld's AI storytellers.

Life events carry a tone ("bad", "good", "neutral"). The director scales the weekly odds of
each tone per club so a season has a shape instead of white noise:

  cassandra  rising tension; trouble follows success (adaptation), then a breather after a disaster
  phoebe     long calm stretches, the same disasters but rarer
  randy      no rules: big random swings week to week

Adaptation (RimWorld): it grows while a club does well and drops when the club gets hurt.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .economy import Club

MODES = {
    # base multipliers on bad / good events, how fast adaptation grows, how long a breather lasts
    "cassandra": {"bad": 1.0, "good": 1.0, "adapt": 1.0, "breather": 4},
    "phoebe": {"bad": 0.5, "good": 1.2, "adapt": 0.5, "breather": 8},
    "randy": {"bad": 1.0, "good": 1.0, "adapt": 0.0, "breather": 0},
}


@dataclass
class Director:
    mode: str = "cassandra"
    adaptation: dict[str, float] = field(default_factory=dict)   # club -> 0..100
    breather_until: dict[str, int] = field(default_factory=dict)  # club -> week
    _last_rank: dict[str, int] = field(default_factory=dict)
    _randy: dict[tuple[str, int], float] = field(default_factory=dict)

    def tension_curve(self, week: int) -> float:
        """Cassandra's slow rise within a season (1.0 -> 1.5) with a mid-season wave."""
        return 1.0 + 0.5 * min(1.0, week / 52) + 0.15 * math.sin(week / 52 * 2 * math.pi * 2)

    def observe(self, club: Club, week: int) -> None:
        """Weekly: success (climbing, money) raises adaptation; damage lowers it."""
        cfg = MODES[self.mode]
        a = self.adaptation.get(club.name, 30.0)
        last = self._last_rank.get(club.name, club.rank)
        climb = last - club.rank
        a += cfg["adapt"] * (0.6 + 2.0 * climb + (0.5 if club.cash > 0 else -1.5))
        self.adaptation[club.name] = max(0.0, min(100.0, a))
        self._last_rank[club.name] = club.rank

    def hurt(self, club: Club, week: int, amount: float = 15.0) -> None:
        """Called after a bad event: adaptation drops and a breather starts."""
        self.adaptation[club.name] = max(0.0, self.adaptation.get(club.name, 30.0) - amount)
        self.breather_until[club.name] = week + MODES[self.mode]["breather"]

    def multiplier(self, club: Club, tone: str, week: int, rng_seed: int = 0) -> float:
        cfg = MODES[self.mode]
        if tone == "neutral":
            return 1.0
        if self.mode == "randy":
            key = (club.name, week)
            if key not in self._randy:
                self._randy[key] = random.Random(f"{rng_seed}:{club.name}:{week}").lognormvariate(0, 0.9)
            r = self._randy[key]
            return r if tone == "bad" else 1 / r
        if tone == "good":
            return cfg["good"] * (1.3 if week < self.breather_until.get(club.name, -1) else 1.0)
        if week < self.breather_until.get(club.name, -1):
            return 0.2
        adapt = self.adaptation.get(club.name, 30.0)
        return cfg["bad"] * self.tension_curve(week) * (0.5 + adapt / 50)
