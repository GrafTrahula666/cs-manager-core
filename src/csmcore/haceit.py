"""HACEIT: the platform where the scene plays outside official matches (a FACEIT-like world).

What it does in the game:
- Elo for every player, pros and free agents alike, from public matchmaking: it drifts toward
  what the player's skill and form are worth, with week-to-week noise. A newcomer starts at
  1000 and has to climb. Levels 1-10 use FACEIT-like thresholds. A new season soft-resets Elo.
- HPL, the invite-only pro league: every month the top Elo players get in. Being there is
  visibility (fame), and a young free agent entering HPL is talent discovery that makes the news.
- The league operator for everyone outside Тир 1: regional leagues, open cups and the Major
  qualifier (see worldgen.calendar and circuit.py).

Elo is a public signal, not the truth: scouting still sees through it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

START_ELO = 1000.0
LEVELS = (500, 750, 900, 1050, 1200, 1350, 1530, 1750, 2000)   # upper bounds of levels 1-9
HPL_SIZE = 40
HPL_MIN_ELO = 2001.0
SOFT_RESET = 0.85        # share of the distance from START_ELO a player keeps into the new season


def level(elo: float) -> int:
    return 1 + sum(elo > b for b in LEVELS)


def worth(p) -> float:
    """The Elo a player's game is worth right now: skill first, form on top."""
    return max(100.0, 1000.0 + (p.overall() - 45.0) * 60.0 + (p.s("form") - 50.0) * 6.0)


@dataclass
class Haceit:
    seed: int = 0
    elo: dict[str, float] = field(default_factory=dict)
    peak: dict[str, float] = field(default_factory=dict)
    hpl: list[str] = field(default_factory=list)
    ever_hpl: set[str] = field(default_factory=set)
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed * 31 + 7)

    def week(self, clubs, free_agents, week: int) -> list[str]:
        """A week of matchmaking for everyone; HPL invites once a month. Returns headlines."""
        people = [p for c in clubs for p in c.roster] + list(free_agents)
        if not self.elo:      # a new world: everyone already has a history on the platform
            self.elo = {p.name: worth(p) + self.rng.gauss(0.0, 60.0) for p in sorted(people, key=lambda q: q.name)}
        for p in sorted(people, key=lambda q: q.name):    # stable order: the same seed, the same Elo
            e = self.elo.get(p.name, START_ELO)
            e += 0.12 * (worth(p) - e) + self.rng.gauss(0.0, 25.0)
            e = max(100.0, e)
            self.elo[p.name] = e
            self.peak[p.name] = max(self.peak.get(p.name, 0.0), e)
        if week % 4:
            return []
        return self._hpl_invites(people, {p.name for p in free_agents}, week)

    def _hpl_invites(self, people, free: set[str], week: int) -> list[str]:
        best = sorted((p for p in people if self.elo.get(p.name, 0.0) >= HPL_MIN_ELO),
                      key=lambda p: -self.elo[p.name])[:HPL_SIZE]
        self.hpl = [p.name for p in best]
        if not self.ever_hpl:   # the first list is the status quo, not news
            self.ever_hpl = set(self.hpl)
            return []
        out = []
        for p in best:
            p.fame += 0.5 if p.fame >= 30 else 1.0
            if p.name in self.ever_hpl:
                continue
            self.ever_hpl.add(p.name)
            if (p.age <= 19 or p.name in free) and len(out) < 3:
                who = "свободный агент" if p.name in free else f"{p.age} лет"
                out.append(f"HACEIT: {p.name} ({who}, {p.role}) впервые попал в HPL с Elo {self.elo[p.name]:.0f}")
                p.history.append(f"week {week}: впервые попал в HPL на HACEIT")
        return out

    def season_reset(self) -> None:
        self.elo = {k: START_ELO + (v - START_ELO) * SOFT_RESET for k, v in self.elo.items()}

    def forget(self, alive: set[str]) -> None:
        """Retired players leave the ladder; their peak stays for the record."""
        self.elo = {k: v for k, v in self.elo.items() if k in alive}

    def card(self, name: str) -> dict:
        e = self.elo.get(name)
        if e is None:
            return {}
        return {"elo": round(e), "level": level(e), "peak": round(self.peak.get(name, e)), "hpl": name in self.hpl}

    def ladder(self, n: int = 20) -> list[tuple[str, float]]:
        return sorted(self.elo.items(), key=lambda kv: -kv[1])[:n]
