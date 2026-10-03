"""A tiny season loop that wires everything together: weekly world tick, money, tournaments
with ranking-based invites, match results feeding state, ranking and fans."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import economy, world
from .economy import Club, Tournament
from .engine import play_map
from .relations import RelationGraph


@dataclass
class SeasonLog:
    events: list[world.Event] = field(default_factory=list)
    results: list[str] = field(default_factory=list)


def play_series(a: Club, b: Club, graph: RelationGraph, seed: int, ctx: dict, maps: int = 3) -> tuple[Club, Club, str]:
    """Bo3 by default. Underdog flag from ranking; chemistry from the relation graph."""
    wins = [0, 0]
    chem = (graph.chemistry(a.roster), graph.chemistry(b.roster))
    lost_prev = [False, False]
    for m in range(maps):
        if max(wins) > maps // 2:
            break
        ca = {**ctx, "underdog": a.rank > b.rank, "after_map_loss": lost_prev[0], "late_series": m >= 1}
        cb = {**ctx, "underdog": b.rank > a.rank, "after_map_loss": lost_prev[1], "late_series": m >= 1}
        r = play_map(a.roster, b.roster, seed=seed * 10 + m, ctx_a=ca, ctx_b=cb, chemistry=chem)
        w = 0 if r.score[0] > r.score[1] else 1
        wins[w] += 1
        lost_prev = [w == 1, w == 0]
    winner, loser = (a, b) if wins[0] > wins[1] else (b, a)
    for p in winner.roster:
        world.after_match(p, True, False, ctx)
    for p in loser.roster:
        world.after_match(p, False, False, ctx)
    return winner, loser, f"{a.name} {wins[0]}:{wins[1]} {b.name}"


def run_tournament(t: Tournament, clubs: list[Club], graph: RelationGraph, week: int, rng: random.Random,
                   log: SeasonLog) -> list[Club]:
    """Single elimination among invited clubs (top by rank, power of two). Returns final order."""
    invited = sorted([c for c in clubs if t.invited(c)], key=lambda c: c.rank)
    size = 1
    while size * 2 <= len(invited):
        size *= 2
    field_ = invited[:size]
    if len(field_) < 2:
        return field_
    order: list[Club] = []
    alive = field_
    rnd = 0
    while len(alive) > 1:
        nxt = []
        playoffs = len(alive) <= 4
        for i in range(0, len(alive), 2):
            ctx = {"lan": t.lan, "playoffs": playoffs}
            w, l, txt = play_series(alive[i], alive[i + 1], graph, rng.randrange(1 << 30), ctx)
            log.results.append(f"week {week} {t.name} R{rnd + 1}: {txt}")
            nxt.append(w)
            order.insert(0, l)
        alive, rnd = nxt, rnd + 1
    order.insert(0, alive[0])
    for place, c in enumerate(order, 1):
        economy.award(c, t, place, week, len(order))
        c.rating_points += t.prize_pool / 10_000 * max(0, len(order) - place + 1)
    return order


def rerank(clubs: list[Club]) -> None:
    for i, c in enumerate(sorted(clubs, key=lambda c: -c.rating_points), 1):
        c.rank = i


def run_season(clubs: list[Club], graph: RelationGraph, calendar: dict[int, Tournament], seed: int,
               weeks: int = economy.WEEKS_PER_YEAR, plans: dict | None = None) -> SeasonLog:
    rng = random.Random(seed)
    log = SeasonLog()
    for week in range(1, weeks + 1):
        week_plans = dict(plans or {})
        if week in calendar:
            for c in clubs:
                if calendar[week].invited(c):
                    week_plans.setdefault(c.name, world.WeekPlan(travel=calendar[week].lan))
        log.events += world.world_week(clubs, graph, week, rng, week_plans)
        if week in calendar:
            run_tournament(calendar[week], clubs, graph, week, rng, log)
            rerank(clubs)
    return log
