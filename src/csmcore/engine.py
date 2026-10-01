"""Minimal match engine: duel -> round -> map. Seeded, deterministic, and explains itself.

Everything here is a PLACEHOLDER model. The point is the shape (seeded RNG, event log with
reasons); the numbers get fitted on parsed demo data (see calibration/).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .player import Player

# Steepness of the skill->win-probability curve. To be fitted on real duel data.
DUEL_SCALE = 18.0


def duel_win_prob(a: Player, b: Player) -> float:
    diff = a.duel_skill() - b.duel_skill()
    return 1.0 / (1.0 + math.exp(-diff / DUEL_SCALE))


@dataclass
class RoundResult:
    winner: int  # 0 or 1
    survivors: tuple[int, int]
    log: list[str] = field(default_factory=list)


def play_round(teams: tuple[list[Player], list[Player]], rng: random.Random) -> RoundResult:
    alive = [list(teams[0]), list(teams[1])]
    log: list[str] = []
    while alive[0] and alive[1]:
        a = rng.choice(alive[0])
        b = rng.choice(alive[1])
        p = duel_win_prob(a, b)
        if rng.random() < p:
            alive[1].remove(b)
            log.append(f"{a.name} kills {b.name} (p={p:.2f})")
        else:
            alive[0].remove(a)
            log.append(f"{b.name} kills {a.name} (p={1 - p:.2f})")
    winner = 0 if alive[0] else 1
    return RoundResult(winner, (len(alive[0]), len(alive[1])), log)


@dataclass
class MapResult:
    score: tuple[int, int]
    rounds: list[RoundResult]


def play_map(team_a: list[Player], team_b: list[Player], seed: int, rounds_to_win: int = 13) -> MapResult:
    rng = random.Random(seed)
    score = [0, 0]
    rounds: list[RoundResult] = []
    while max(score) < rounds_to_win:
        r = play_round((team_a, team_b), rng)
        score[r.winner] += 1
        rounds.append(r)
    return MapResult((score[0], score[1]), rounds)
