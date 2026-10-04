"""A tiny season loop that wires everything together: weekly world tick, money, tournaments
with ranking-based invites, match results feeding state, ranking and fans."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import development, economy, promises as promises_mod, squad, world
from .board import Owner
from .chronicle import Chronicle
from .legacy import Legacy
from .meta import Meta
from .rivalry import Rivalries
from .market import Market
from .economy import Club, Tournament
from .engine import play_map
from .relations import RelationGraph
from .storylets import Fired, StoryEngine


@dataclass
class SeasonLog:
    events: list[world.Event] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    stories: list[Fired] = field(default_factory=list)
    management: list[str] = field(default_factory=list)  # market, board, promises, squad notes


@dataclass
class Systems:
    """Optional management layers. Leave a field as None to switch that layer off."""
    stories: StoryEngine | None = None
    market: Market | None = None
    owners: dict[str, Owner] | None = None
    promises: dict[str, list] | None = None     # club name -> [Promise]
    development: bool = True
    manager_club: str | None = None
    rivalries: Rivalries | None = None
    meta: Meta | None = None
    chronicle: Chronicle | None = None
    legacy: Legacy | None = None
    talents_per_season: int = 6
    patch_every: int = 13


def play_series(a: Club, b: Club, graph: RelationGraph, seed: int, ctx: dict, maps: int = 3,
                sysm: "Systems | None" = None, stage: str = "group", decisive: bool = True,
                week: int = 0, notes: list[str] | None = None) -> tuple[Club, Club, str]:
    """Bo3 by default. Underdog flag from ranking; chemistry from the relation graph; with
    Systems: map veto and familiarity, patch meta, rivalry context and memory."""
    wins = [0, 0]
    la, lb = a.lineup(), b.lineup()
    chem = (graph.chemistry(la), graph.chemistry(lb))
    lost_prev = [False, False]
    meta = sysm.meta if sysm else None
    riv = sysm.rivalries if sysm else None
    map_list = meta.veto(a, b, maps) if meta else [None] * maps
    base_a, base_b = dict(ctx), dict(ctx)
    if meta:
        base_a["meta_roles"] = base_b["meta_roles"] = meta.patch["roles"]
    if riv:
        rc = riv.context(a, b, la + lb)
        for base in (base_a, base_b):
            base.update({k: v for k, v in rc.items() if k != "team_bonus"})
        if rc.get("rivalry"):
            base_a["playoffs"] = base_b["playoffs"] = True   # a derby feels like a playoff
            base_a["team_bonus"] = base_b["team_bonus"] = 0.0
    logs: list[str] = []
    for m in range(maps):
        if max(wins) > maps // 2:
            break
        mp = map_list[m] if m < len(map_list) else None
        ca = {**base_a, "opponent": b.name, "underdog": a.rank > b.rank, "after_map_loss": lost_prev[0], "late_series": m >= 1, "map": mp}
        cb = {**base_b, "opponent": a.name, "underdog": b.rank > a.rank, "after_map_loss": lost_prev[1], "late_series": m >= 1, "map": mp}
        if meta and mp:
            ca["team_bonus"] = ca.get("team_bonus", 0.0) + meta.map_bonus(a, mp)
            cb["team_bonus"] = cb.get("team_bonus", 0.0) + meta.map_bonus(b, mp)
        r = play_map(la, lb, seed=seed * 10 + m, ctx_a=ca, ctx_b=cb, chemistry=chem)
        if meta and mp:
            meta.after_map(a, mp)
            meta.after_map(b, mp)
        for rr in r.rounds:
            logs += rr.log
        w = 0 if r.score[0] > r.score[1] else 1
        wins[w] += 1
        lost_prev = [w == 1, w == 0]
    winner, loser = (a, b) if wins[0] > wins[1] else (b, a)
    if riv:
        lines = riv.record_series(week, a, b, winner, (wins[0], wins[1]), logs, stage, decisive)
        if notes is not None:
            notes += lines
    for p in (la if winner is a else lb):
        world.after_match(p, True, False, ctx)
    for p in (lb if winner is a else la):
        world.after_match(p, False, False, ctx)
    return winner, loser, f"{a.name} {wins[0]}:{wins[1]} {b.name}"


def run_tournament(t: Tournament, clubs: list[Club], graph: RelationGraph, week: int, rng: random.Random,
                   log: SeasonLog, sysm: "Systems | None" = None, season: int = 1) -> list[Club]:
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
        stage = "final" if len(alive) == 2 else "semi" if len(alive) == 4 else "group"
        for i in range(0, len(alive), 2):
            ctx = {"lan": t.lan, "playoffs": playoffs}
            notes: list[str] = []
            w, l, txt = play_series(alive[i], alive[i + 1], graph, rng.randrange(1 << 30), ctx,
                                    sysm=sysm, stage=stage, week=week, notes=notes)
            if sysm and sysm.chronicle:
                for n in notes:
                    sysm.chronicle.add(season, week, "rivalry", n)
                if stage == "final":
                    sysm.chronicle.add(season, week, "final", f"Финал {t.name}: {txt}")
            log.results.append(f"week {week} {t.name} R{rnd + 1}: {txt}")
            nxt.append(w)
            order.insert(0, l)
        alive, rnd = nxt, rnd + 1
    order.insert(0, alive[0])
    if sysm and sysm.chronicle:
        sysm.chronicle.record_title(season, week, alive[0], t.name, t.major)
    for place, c in enumerate(order, 1):
        economy.award(c, t, place, week, len(order))
        c.rating_points += t.prize_pool / 10_000 * max(0, len(order) - place + 1)
    return order


def rerank(clubs: list[Club]) -> None:
    for i, c in enumerate(sorted(clubs, key=lambda c: -c.rating_points), 1):
        c.rank = i


def run_season(clubs: list[Club], graph: RelationGraph, calendar: dict[int, Tournament], seed: int,
               weeks: int = economy.WEEKS_PER_YEAR, plans: dict | None = None,
               stories: StoryEngine | None = None, manager_club: str | None = None,
               systems: Systems | None = None, season: int = 1, start_week: int = 0) -> SeasonLog:
    """Pass a StoryEngine (or a full Systems bundle) to switch on life events, the market,
    owners, promises and development. The manager's club gets its choices in
    stories.pending / market.offers instead of having the AI decide."""
    sysm = systems or Systems(stories=stories, manager_club=manager_club, development=False)
    rng = random.Random(seed)
    meta_rng = random.Random(seed + 3)
    story_rng = random.Random(seed + 1)  # separate streams: adding layers does not reshuffle matches
    mgmt_rng = random.Random(seed + 2)
    log = SeasonLog()
    for o_club in clubs:
        if sysm.owners and o_club.name in sysm.owners and not sysm.owners[o_club.name].objectives:
            sysm.owners[o_club.name].set_objectives(o_club)
    for wk in range(1, weeks + 1):
        week = start_week + wk  # absolute week: contracts and sponsors use it
        week_plans = dict(plans or {})
        if wk in calendar:
            for c in clubs:
                if calendar[wk].invited(c):
                    week_plans.setdefault(c.name, world.WeekPlan(travel=calendar[wk].lan))
        if sysm.meta and wk % sysm.patch_every == 1:
            line = sysm.meta.new_patch(week, meta_rng)
            if sysm.chronicle:
                sysm.chronicle.add(season, week, "patch", line.split(": ", 1)[1])
        if sysm.meta:
            for c in clubs:
                sysm.meta.practice(c)
        if sysm.rivalries:
            sysm.rivalries.decay()
        log.events += world.world_week(clubs, graph, week, rng, week_plans)
        if sysm.stories is not None:
            fired = sysm.stories.week(clubs, graph, week, story_rng, sysm.manager_club)
            log.stories += fired
            if sysm.chronicle:
                for f in fired:
                    if sysm.stories.events[f.event_id].get("chain_only") or f.event_id in ("wedding", "festival_grant"):
                        sysm.chronicle.add(season, week, "story", f.title, [f.a.name] if f.a else [])
        for c in clubs:
            log.management += squad.leader_mood_spread(c, graph, week)
            if sysm.promises and c.name in sysm.promises:
                log.management += promises_mod.check(sysm.promises[c.name], c, graph, week)
        if sysm.market is not None:
            deals = sysm.market.week(clubs, week, mgmt_rng, sysm.manager_club)
            log.management += deals
            if sysm.chronicle:
                for d in deals:
                    if "→" in d or "подписал" in d:
                        sysm.chronicle.add(season, week, "transfer", d)
        if week % 4 == 0:
            for c in clubs:
                if sysm.development:
                    mentor = any(p.mod("team_youth_learning")[1] > 1 for p in c.roster)
                    lineup = c.lineup()
                    for p in c.roster:
                        development.month(p, c, mgmt_rng, played=p in lineup, mentor_in_team=mentor)
                if sysm.owners and c.name in sysm.owners:
                    review = sysm.owners[c.name].monthly_review(c, week)
                    log.management += review
                    if sysm.chronicle:
                        for r in review:
                            if "увольняет" in r:
                                sysm.chronicle.add(season, week, "board", r.split(": ", 1)[1])
        if wk in calendar:
            run_tournament(calendar[wk], clubs, graph, week, rng, log, sysm, season)
            rerank(clubs)
    if sysm.legacy:
        for line in sysm.legacy.season_end(clubs, start_week + weeks, mgmt_rng):
            log.management.append(line)
            if sysm.chronicle:
                sysm.chronicle.add(season, start_week + weeks, "retirement", line)
        talents = sysm.legacy.new_talents(sysm.talents_per_season, mgmt_rng, season)
        if sysm.market is not None:
            sysm.market.free_agents += talents
    if sysm.development:
        development.season_end([p for c in clubs for p in c.roster])
    return log
