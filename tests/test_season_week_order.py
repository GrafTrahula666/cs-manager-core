"""Protect ordering of the weekly simulation pipeline without changing game mechanics."""

import random
from types import SimpleNamespace

import pytest

from csmcore import season
from csmcore.economy import Club, Tournament
from csmcore.world import WeekPlan


@pytest.mark.parametrize(
    "previous_week,with_event",
    [(0, True), (1, False), (3, True)],
    ids=["opening-week-with-patch", "quiet-week", "monthly-tournament-week"],
)
def test_season_week_pipeline_order_and_rng_routing(monkeypatch, previous_week, with_event):
    """Stage ordering, streams and plan precedence are explicit compatibility contracts."""
    order = []
    clubs = [Club("A"), Club("B")]
    a, b = clubs
    run = season.SeasonRun(
        season=2, start_week=52,
        rng=random.Random(11), meta_rng=random.Random(12),
        story_rng=random.Random(13), mgmt_rng=random.Random(14),
        log=season.SeasonLog(), titles_before={}, wk=previous_week,
    )
    week = 52 + previous_week + 1
    plans = {"A": WeekPlan(practice_hours=21, rest_days=2)}
    graph = object()
    tournament = Tournament("Test Cup", "C", 1_000, [1.0], lan=True)
    calendar = {previous_week + 1: [tournament]} if with_event else {}

    def track(name):
        order.append(name)

    def patch(w, rng):
        assert w == week and rng is run.meta_rng
        track("patch")
        return "Patch: updated"

    def beginning(*args):
        assert args[2] == week and args[3] == 2
        track("emergent.begin")
        return SimpleNamespace(stories=None)

    def world_tick(cs, g, w, rng, week_plans):
        assert cs is clubs and g is graph and w == week and rng is run.rng
        assert week_plans["A"] is plans["A"]
        assert week_plans["A"].practice_hours == 21 and not week_plans["A"].travel
        assert ("B" in week_plans) is with_event
        if with_event:
            assert week_plans["B"].travel
        track("world")
        return ["world event"]

    def secrets(cs, g, w, rng):
        assert rng is run.mgmt_rng and w == week
        track("secrets")
        return ["secret notice"]

    def stories(cs, g, w, rng, manager_club):
        assert rng is run.story_rng and manager_club == "A" and w == week
        track("stories")
        return []

    def contract_tick(cs, market, w, rng, manager_club):
        assert rng is run.mgmt_rng and w == week and manager_club == "A"
        track("contracts")
        return ["contract notice"]

    def market_tick(cs, w, rng, manager_club):
        assert rng is run.mgmt_rng and w == week and manager_club == "A"
        track("market")
        return ["market notice"]

    def tournament_tick(t, cs, g, w, rng, log, sysm, season_no, invites):
        assert t is tournament and cs is clubs and w == week
        assert rng is run.rng and log is run.log and season_no == 2
        track("tournament")
        return []

    def report_month(club, w, rng, g):
        assert rng is run.mgmt_rng and w == week
        track("month:" + club.name)
        return ["monthly note"]

    def owner_review(name):
        def review(club, w):
            assert w == week and club.name == name
            track("owner:" + name)
            return []
        return SimpleNamespace(monthly_review=review)

    sysm = season.Systems(
        manager_club="A", development=False,
        meta=SimpleNamespace(new_patch=patch, practice=lambda c: track("practice:" + c.name)),
        rivalries=SimpleNamespace(decay=lambda: track("rivalries")),
        secrets=SimpleNamespace(discovery_week=secrets),
        stories=SimpleNamespace(week=stories),
        market=SimpleNamespace(week=market_tick),
        promises={"A": [object()]},
        owners={"A": owner_review("A"), "B": owner_review("B")},
        emergent=SimpleNamespace(begin=beginning),
    )

    monkeypatch.setattr(season, "snapshot_invites",
                        lambda r, cs, cal, wk: track("invites"))
    monkeypatch.setattr(season.world, "world_week", world_tick)
    monkeypatch.setattr(season.character, "week",
                        lambda c, g, w: track("character:" + c.name))
    monkeypatch.setattr(season.squad, "leader_mood_spread",
                        lambda c, g, w: (track("mood:" + c.name), ["mood notice"])[1])
    monkeypatch.setattr(season.promises_mod, "check",
                        lambda promises, c, g, w: (track("promises"), ["promise notice"])[1])
    monkeypatch.setattr(season.contracts, "week", contract_tick)
    monkeypatch.setattr(season.character, "month", report_month)
    monkeypatch.setattr(season.character, "stars_update",
                        lambda cs, w: (track("stars"), ["record notice"])[1])
    monkeypatch.setattr(season, "run_tournament", tournament_tick)
    monkeypatch.setattr(season, "rerank", lambda cs: track("rerank"))
    monkeypatch.setattr(season, "_platforms_week",
                        lambda cs, systems, log, s, w: track("platforms"))
    monkeypatch.setattr(season, "_emergent_week",
                        lambda ew, ctx, events, systems, log, s, wk: (
                            track("emergent.end"), events == ["world event"])[1])

    season.season_week(run, clubs, graph, calendar, sysm, plans)

    expected = ["invites"]
    if previous_week == 0:
        expected.append("patch")
    expected += [
        "practice:A", "practice:B", "rivalries", "emergent.begin", "world",
        "secrets", "stories", "character:A", "mood:A", "promises",
        "character:B", "mood:B", "contracts", "market",
    ]
    if previous_week == 3:
        expected += ["month:A", "month:B", "stars", "owner:A", "owner:B"]
    if with_event:
        expected += ["tournament", "rerank"]
    expected += ["platforms", "emergent.end"]
    assert order == expected
    assert run.wk == previous_week + 1
    assert run.log.events == ["world event"]
    assert run.log.management == [
        "secret notice", "mood notice", "promise notice", "mood notice",
        "contract notice", "market notice",
    ] + (["A: monthly note", "B: monthly note", "record notice"] if previous_week == 3 else [])
    assert list(plans) == ["A"] and plans["A"].travel is False
