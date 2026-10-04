"""Player development, borrowed from Football Manager's current/potential ability model.

Every player has a hidden `potential` (ceiling for the average of the 20 stats). Each month
stats move toward it at a speed set by age, learning speed, practice quality, coach, academy,
mentors, playing time and traits. After the peak, mechanics decline first while game
intelligence keeps growing for a few more years, so a 29-year-old aimer can become an IGL.
"""
from __future__ import annotations

import random

from .economy import Club
from .player import STATS, Player

MECHANICS = ("aim", "reaction", "movement", "weapon_control")
MENTAL = ("game_sense", "positioning", "timing", "map_awareness", "utility_iq", "tactical_discipline",
          "adaptability", "analytical", "communication", "leadership")


def age_growth(age: int) -> float:
    """Monthly growth multiplier by age: fast at 16-20, slowing to zero around 26."""
    if age <= 20:
        return 1.0
    return max(0.0, 1.0 - (age - 20) / 6)


def mechanics_decline(age: int) -> float:
    """Monthly loss of mechanical stats after 27 (reaction goes first)."""
    return max(0.0, (age - 27) * 0.12)


def month(p: Player, club: Club, rng: random.Random, played: bool = True, mentor_in_team: bool = False) -> dict[str, float]:
    """One month of development. Returns per-stat deltas for the report."""
    gap = p.potential - p.overall()
    learn = (0.5 + p.stat("learning_speed") / 100) * p.mod("learning")[1]
    practice = (1 - p.s("fatigue") / 150) * (1 - p.s("burnout") / 120) * (0.6 + p.stat("discipline") / 250)
    env = (0.6 + club.coach_quality / 125) * (1 + 0.1 * club.facilities.get("academy", 0) * (p.age < 21))
    env *= 1.3 if mentor_in_team and p.age < 21 else 1.0
    env *= 1.0 if played else 0.6
    rate = max(0.0, gap) * 0.06 * age_growth(p.age) * learn * practice * env
    deltas: dict[str, float] = {}
    for k in STATS:
        d = rate * rng.uniform(0.5, 1.5)
        if k in MENTAL and p.age > 24:
            d += 0.15 * learn * (p.age < 32)
        if k in MECHANICS:
            d -= mechanics_decline(p.age) * (1.5 if k == "reaction" else 1.0) * p.mod("decay")[1]
        if d:
            p.stats[k] = max(1.0, min(100.0, p.stats.get(k, 50.0) + d))
            deltas[k] = d
    return deltas


def season_end(players: list[Player]) -> None:
    """Birthday once a season. Potential can shift a little: late bloomers and busts."""
    for p in players:
        p.age += 1


def roll_potential(level: float, age: int, rng: random.Random) -> float:
    """Young players get wider, more uncertain ceilings."""
    spread = max(2.0, (24 - age) * 2.5)
    return min(100.0, max(level, level + abs(rng.gauss(spread * 0.6, spread))))
