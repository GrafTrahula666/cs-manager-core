"""Guards against events that fire all the time (the world should feel alive, not spammy)."""
from collections import Counter

from csmcore.season import run_season
from csmcore.worldgen import generate


def _season(seed=2, n=40):
    clubs, graph, cal, sysm, _ = generate(seed, n)
    log = run_season(clubs, graph, cal, seed, systems=sysm)
    return clubs, sysm, log


def test_no_life_event_hits_a_quarter_of_players_per_season():
    clubs, _, log = _season()
    players = sum(len(c.roster) for c in clubs)
    per_event = Counter(f.event_id for f in log.stories)
    worst, n = per_event.most_common(1)[0]
    assert n / players < 0.25, (worst, n, players)
    assert len(log.stories) / players < 1.5


def test_repeating_notes_fire_on_change_not_every_week():
    clubs, _, log = _season()
    sour = [m for m in log.management if "настроение падает" in m]
    owner = [m for m in log.management if "владелец обеспокоен" in m or "ультиматум" in m]
    assert len(sour) <= len(clubs) * 2
    assert len(owner) <= len(clubs) * 2


def test_transfer_requests_are_not_universal():
    clubs, _, log = _season()
    players = sum(len(c.roster) for c in clubs)
    requests = [e for e in log.events if e.kind == "transfer_request"]
    assert len(requests) / players < 0.35
