"""Minimal match engine: duel -> round -> map. Seeded, deterministic, and explains itself.

Everything here is a PLACEHOLDER model. The point is the shape (seeded RNG, context-aware
skill with traits/state/pressure, team chemistry, event log with reasons); the numbers get
fitted on parsed demo data later.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .player import Player

# Steepness of the skill->win-probability curve. To be fitted on real duel data.
DUEL_SCALE = 18.0
# How many duel points one point of team chemistry (-100..100) is worth.
CHEMISTRY_WEIGHT = 1 / 12
# Duel points lost when a team plays a round on an eco/force buy.
ECO_PENALTY = 8.0


def duel_win_prob(a: Player, b: Player, ctx_a: dict | None = None, ctx_b: dict | None = None,
                  bonus_a: float = 0.0, bonus_b: float = 0.0) -> float:
    diff = (a.duel_skill(ctx_a) + bonus_a) - (b.duel_skill(ctx_b) + bonus_b)
    return 1.0 / (1.0 + math.exp(-diff / DUEL_SCALE))


def team_bonus(team: list[Player], ctx: dict | None, chemistry: float = 0.0) -> float:
    """Team-wide duel bonus: team-scoped traits (Utility Architect) + chemistry from the graph."""
    ctx = ctx or {}
    eco = -ECO_PENALTY if ctx.get("round") == "eco" else 0.0
    # ctx["team_bonus"]: map familiarity, rivalry motivation, team talk etc. computed by callers.
    return sum(p.mod("team_duel", ctx)[0] for p in team) + chemistry * CHEMISTRY_WEIGHT + eco + ctx.get("team_bonus", 0.0)


@dataclass
class RoundResult:
    winner: int  # 0 or 1
    survivors: tuple[int, int]
    kind: tuple[str, str] = ("full", "full")
    log: list[str] = field(default_factory=list)


def play_round(teams: tuple[list[Player], list[Player]], rng: random.Random,
               ctxs: tuple[dict, dict] = ({}, {}), chem: tuple[float, float] = (0.0, 0.0)) -> RoundResult:
    alive = [list(teams[0]), list(teams[1])]
    bonus = (team_bonus(teams[0], ctxs[0], chem[0]), team_bonus(teams[1], ctxs[1], chem[1]))
    log: list[str] = []
    while alive[0] and alive[1]:
        a = rng.choice(alive[0])
        b = rng.choice(alive[1])
        p = duel_win_prob(a, b, ctxs[0], ctxs[1], bonus[0], bonus[1])
        if rng.random() < p:
            alive[1].remove(b)
            log.append(f"{a.name} kills {b.name} (p={p:.2f})")
        else:
            alive[0].remove(a)
            log.append(f"{b.name} kills {a.name} (p={1 - p:.2f})")
    winner = 0 if alive[0] else 1
    kinds = (ctxs[0].get("round", "full"), ctxs[1].get("round", "full"))
    return RoundResult(winner, (len(alive[0]), len(alive[1])), kinds, log)


@dataclass
class MapResult:
    score: tuple[int, int]
    rounds: list[RoundResult]


def play_map(team_a: list[Player], team_b: list[Player], seed: int, rounds_to_win: int = 13,
             ctx_a: dict | None = None, ctx_b: dict | None = None,
             chemistry: tuple[float, float] = (0.0, 0.0)) -> MapResult:
    """MR12: pistol rounds 1 and 13; the pistol loser plays the next round on an eco."""
    rng = random.Random(seed)
    score = [0, 0]
    rounds: list[RoundResult] = []
    half = rounds_to_win - 1
    while max(score) < rounds_to_win:
        n = len(rounds) + 1
        kinds = ["full", "full"]
        if n in (1, half + 1):
            kinds = ["pistol", "pistol"]
        elif rounds and rounds[-1].kind[0] == "pistol":
            kinds[1 - rounds[-1].winner] = "eco"
        mp = max(score) == rounds_to_win - 1
        ctxs = tuple({**(c or {}), "round": k, "match_point": mp} for c, k in ((ctx_a, kinds[0]), (ctx_b, kinds[1])))
        r = play_round((team_a, team_b), rng, ctxs, chemistry)
        score[r.winner] += 1
        rounds.append(r)
    return MapResult((score[0], score[1]), rounds)
