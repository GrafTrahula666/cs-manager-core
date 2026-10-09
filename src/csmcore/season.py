"""A tiny season loop that wires everything together: weekly world tick, money, tournaments
with ranking-based invites, match results feeding state, ranking and fans."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import character, development, economy, promises as promises_mod, squad, world
from .board import Owner
from .chronicle import Chronicle
from .legacy import Legacy
from .meta import Meta
from .manager import Careers
from .rivalry import Rivalries
from .secrets import Secrets
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
    secrets: Secrets | None = None
    careers: Careers | None = None
    talents_per_season: int = 6
    patch_every: int = 13


def _count_stats(players, r) -> None:
    """Season K/D/rounds per player, read from the round logs (HLTV-style public stats)."""
    by = {p.name: p for p in players}
    rounds = len(r.rounds)
    for p in players:
        st = p.__dict__.setdefault("season_stats", {"maps": 0, "rounds": 0, "kills": 0, "deaths": 0})
        st["maps"] += 1
        st["rounds"] += rounds
    for rr in r.rounds:
        for line in rr.log:
            killer, _, rest = line.partition(" kills ")
            victim = rest.split(" ", 1)[0]
            if killer in by:
                by[killer].season_stats["kills"] += 1
            if victim in by:
                by[victim].season_stats["deaths"] += 1


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
    if riv and sysm.secrets and stage in ("semi", "final"):
        score = riv.get(a.name, b.name).score
        leaks = sysm.secrets.rival_leaks(a, b, score, week, graph, random.Random(seed)) + \
            sysm.secrets.rival_leaks(b, a, score, week, graph, random.Random(seed + 1))
        if notes is not None:
            notes += leaks
        if leaks:
            la, lb = a.lineup(), b.lineup()
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
        _count_stats(la + lb, r)
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


@dataclass
class SeasonRun:
    """Everything a season needs between weeks, so the game can stop after any week and
    resume (or be saved) without changing what happens next."""
    season: int
    start_week: int
    rng: random.Random
    meta_rng: random.Random
    story_rng: random.Random
    mgmt_rng: random.Random
    log: SeasonLog
    titles_before: dict
    wk: int = 0


def season_begin(clubs: list[Club], seed: int, sysm: Systems, season: int = 1, start_week: int = 0) -> SeasonRun:
    run = SeasonRun(season, start_week, random.Random(seed), random.Random(seed + 3),
                    random.Random(seed + 1),  # separate streams: adding layers does not reshuffle matches
                    random.Random(seed + 2), SeasonLog(),
                    {k: len(v) for k, v in (sysm.chronicle.titles.items() if sysm.chronicle else [])})
    if sysm.stories is not None and sysm.secrets is not None:
        sysm.stories.secrets = sysm.secrets
    if sysm.careers is not None:
        for c in clubs:
            if c.name not in sysm.careers.managers:
                sysm.careers.hire(c, start_week, run.mgmt_rng)
    for o_club in clubs:
        if sysm.owners and o_club.name in sysm.owners and not sysm.owners[o_club.name].objectives:
            sysm.owners[o_club.name].set_objectives(o_club)
    return run


def season_week(run: SeasonRun, clubs: list[Club], graph: RelationGraph, calendar: dict[int, Tournament],
                sysm: Systems, plans: dict | None = None) -> None:
    """Advance one week of the season."""
    run.wk += 1
    wk, season, log = run.wk, run.season, run.log
    rng, meta_rng, story_rng, mgmt_rng = run.rng, run.meta_rng, run.story_rng, run.mgmt_rng
    week = run.start_week + wk  # absolute week: contracts and sponsors use it
    week_plans = dict(plans or {})
    events = calendar.get(wk, [])
    events = events if isinstance(events, list) else [events]   # a big world runs several events a week
    for t in events:
        for c in clubs:
            if t.invited(c):
                week_plans.setdefault(c.name, world.WeekPlan(travel=t.lan))
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
    if sysm.secrets is not None:
        log.management += sysm.secrets.discovery_week(clubs, graph, week, mgmt_rng)
    if sysm.stories is not None:
        fired = sysm.stories.week(clubs, graph, week, story_rng, sysm.manager_club)
        log.stories += fired
        if sysm.chronicle:
            for f in fired:
                if sysm.stories.events[f.event_id].get("chain_only") or f.event_id in ("wedding", "festival_grant"):
                    sysm.chronicle.add(season, week, "story", f.title, [f.a.name] if f.a else [])
    for c in clubs:
        character.week(c, graph, week)
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
            log.management += [f"{c.name}: {n}" for n in character.month(c, week, mgmt_rng, graph)]
        for n in character.stars_update(clubs, week):
            log.management.append(n)
            if sysm.chronicle:
                sysm.chronicle.add(season, week, "record", n)
        for c in clubs:
            if sysm.development:
                mentor = any(p.mod("team_youth_learning")[1] > 1 for p in c.roster)
                lineup = c.lineup()
                for p in c.roster:
                    development.month(p, c, mgmt_rng, played=p in lineup, mentor_in_team=mentor)
                    if development.breakthrough(p, mgmt_rng):
                        p.history.append(f"week {week}: перерос свой потолок")
            if sysm.owners and c.name in sysm.owners:
                review = sysm.owners[c.name].monthly_review(c, week)
                log.management += review
                for r in review:
                    if "увольняет" not in r:
                        continue
                    if sysm.chronicle:
                        sysm.chronicle.add(season, week, "board", r.split(": ", 1)[1])
                    if sysm.careers is not None:
                        gone = sysm.careers.sack(c, week)
                        new = sysm.careers.hire(c, week, mgmt_rng)
                        owner = sysm.owners[c.name]
                        owner.fired, owner.confidence = False, 50.0   # new manager, fresh start
                        if sysm.chronicle and gone:
                            sysm.chronicle.add(season, week, "board",
                                               f"{c.name}: {gone.name} уволен, новый менеджер {new.name}")
    for t in events:
        run_tournament(t, clubs, graph, week, rng, log, sysm, season)
    if events:
        rerank(clubs)


def season_finish(run: SeasonRun, clubs: list[Club], sysm: Systems) -> None:
    """Season-end reviews, retirements, new talents and ageing."""
    season, mgmt_rng, log = run.season, run.mgmt_rng, run.log
    end_week = run.start_week + run.wk
    if sysm.careers is not None:
        for c in clubs:
            m = sysm.careers.managers.get(c.name)
            if m:
                won = len(sysm.chronicle.titles.get(c.name, [])) - run.titles_before.get(c.name, 0) if sysm.chronicle else 0
                m.season_review(c, sysm.owners.get(c.name) if sysm.owners else None, won, season)
    if sysm.legacy:
        for line in sysm.legacy.season_end(clubs, end_week, mgmt_rng):
            log.management.append(line)
            if sysm.chronicle:
                sysm.chronicle.add(season, end_week, "retirement", line)
        taken = {p.name for c in clubs for p in c.roster + c.former}
        if sysm.market is not None:
            taken |= {p.name for p in sysm.market.free_agents}
        talents = sysm.legacy.new_talents(sysm.talents_per_season, mgmt_rng, season, taken)
        if sysm.market is not None:
            sysm.market.free_agents += talents
    for c in clubs:
        for p in c.roster:
            if "season_stats" in p.__dict__:
                p.__dict__["last_season_stats"] = p.__dict__.pop("season_stats")
    if sysm.development:
        development.season_end([p for c in clubs for p in c.roster])


def run_season(clubs: list[Club], graph: RelationGraph, calendar: dict[int, Tournament], seed: int,
               weeks: int = economy.WEEKS_PER_YEAR, plans: dict | None = None,
               stories: StoryEngine | None = None, manager_club: str | None = None,
               systems: Systems | None = None, season: int = 1, start_week: int = 0) -> SeasonLog:
    """Pass a StoryEngine (or a full Systems bundle) to switch on life events, the market,
    owners, promises and development. The manager's club gets its choices in
    stories.pending / market.offers instead of having the AI decide."""
    sysm = systems or Systems(stories=stories, manager_club=manager_club, development=False)
    run = season_begin(clubs, seed, sysm, season, start_week)
    for _ in range(weeks):
        season_week(run, clubs, graph, calendar, sysm, plans)
    season_finish(run, clubs, sysm)
    return run.log
