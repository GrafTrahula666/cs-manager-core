"""Something to chase: young free-agent talents with a huge ceiling and stars who ask to leave.

Every season (and at the start of a career) the market gets two hunt targets, and one star of a
rival club asks for a transfer. AI clubs shop in the same windows, so the manager races them:
`rivals()` says how many clubs would take the player today.
"""
from __future__ import annotations

import random

from .development import roll_potential
from .generate import make_player
from .market import TIER_SALARY_CAP, asking

HUNT_PER_SEASON = 2
HEAD_START_WEEKS = 8   # AI clubs ignore a fresh target this long, so the manager has time to chase it
ROLES = ["entry", "awp", "rifler", "support", "lurker", "igl"]


def rivals(game, p) -> int:
    """AI clubs for which the player is a clear upgrade and who could pay six months of his wages."""
    ask = asking(p, game.week, game.sysm.market.level_scale if game.sysm.market is not None else None)   # P1: priced on the world's scale
    wage = ask * 6
    n = 0
    for c in game.clubs:
        if c.name == game.club_name:
            continue
        weakest = min(q.overall() for q in c.lineup())
        if weakest + 2 <= p.overall() and c.cash > wage and ask <= TIER_SALARY_CAP[c.tier] * 1.1:
            n += 1
    return n


def spawn(game, rng: random.Random) -> list[str]:
    """Put new targets on the market. Returns world-news lines."""
    from .worldgen import Nicknames
    mk = game.sysm.market
    if mk is None:
        return []
    names = {p.name for c in game.clubs for p in c.roster + c.former} | {p.name for p in mk.free_agents}
    if game.sysm.legacy:
        names |= {r.player.name for r in game.sysm.legacy.retired}
    nick = Nicknames(rng, reserved=names)
    tops = sorted((q.overall() for c in game.clubs for q in c.lineup()), reverse=True)
    target = tops[min(len(tops) - 1, 2)]       # as good as the world's third best, at 18-22
    lines = []
    for _ in range(HUNT_PER_SEASON):
        age = rng.randint(18, 22)
        p = make_player(nick(), target, rng, rng.choice(ROLES), age=age)
        for _ in range(3):                        # nudge the stats so overall lands near the target
            gap = (target + rng.uniform(-3, 1)) - p.overall()
            p.stats = {k: max(1.0, min(100.0, v + gap)) for k, v in p.stats.items()}
        p.potential = max(roll_potential(p.overall(), age, rng), min(95.0, p.overall() + rng.uniform(6, 10)))
        p.flags.update({"free_agent", "hunt_target"})
        p.__dict__["free_since"] = game.week
        p.__dict__["hunt_until"] = game.week + HEAD_START_WEEKS
        p.history.append(f"week {game.week}: вышел на рынок, за ним охотятся")
        mk.free_agents.append(p)
        lines.append(f"мир: на рынке свободный талант {p.name} ({age}, {p.role}), уровень {p.overall():.0f}, "
                     f"потолок выше: {rivals(game, p)} клубов подключатся через {HEAD_START_WEEKS} недель")
    pool = [(q, c) for c in game.clubs if c.name != game.club_name and c.tier in ("tier1", "super")
            for q in c.roster if "legend_contract" not in q.flags and "transfer_requested" not in q.flags]
    if pool:
        q, c = max(pool, key=lambda x: x[0].overall())
        q.flags.add("transfer_requested")
        q.history.append(f"week {game.week}: попросил трансфер из {c.name}")
        lines.append(f"мир: {q.name} ({c.name}, уровень {q.overall():.0f}) выставлен на трансфер: самая громкая сделка окна")
    return lines
