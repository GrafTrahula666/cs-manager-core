import random

import pytest

from csmcore import haceit
from csmcore.economy import Club, Tournament
from csmcore.game import Game
from csmcore.haceit import Haceit
from csmcore.hltw import Hltw, ratings
from csmcore.player import STATS, Player
from csmcore.relations import RelationGraph
from csmcore.season import SeasonLog, Systems, run_tournament


def pl(name, level):
    return Player(name, {s: level for s in STATS})


@pytest.fixture(scope="module")
def season_game():
    g = Game.new(seed=3, n_clubs=40)
    for _ in range(53):
        g.advance()
    return g


def test_elo_levels_and_a_newcomer_climbs_to_what_his_game_is_worth():
    assert haceit.level(100) == 1 and haceit.level(1000) == 4 and haceit.level(2001) == 10
    hc = Haceit(seed=1)
    hc.elo = {"old": 1500.0}                       # not a new world: newcomers start at 1000
    star, weak = pl("star", 80), pl("weak", 50)
    for w in range(1, 30):
        hc.week([Club("C", roster=[star, weak])], [], w)
    assert hc.elo["star"] > 2600 > 1600 > hc.elo["weak"] > 1000
    assert haceit.level(hc.elo["star"]) == 10
    top = hc.elo["star"]
    hc.season_reset()
    assert 1000 < hc.elo["star"] < top             # a soft reset, not a wipe


def test_hpl_takes_the_top_of_the_ladder_and_makes_young_free_agents_news():
    hc = Haceit(seed=2)
    pros = [pl(f"pro{i}", 70 + i % 10) for i in range(50)]
    kid = pl("kid", 82)
    kid.age = 17
    hc.week([Club("C", roster=pros)], [], 4)                 # the first list is the status quo
    assert len(hc.hpl) == haceit.HPL_SIZE and not hc.ever_hpl ^ set(hc.hpl)
    news = []
    for w in range(5, 41):
        news += hc.week([Club("C", roster=pros)], [kid], w)
    assert "kid" in hc.hpl and any("kid (свободный агент" in n for n in news)
    assert hc.card("kid")["hpl"] and kid.fame > 0


def test_rating_is_relative_to_the_sample():
    r = ratings({"a": (20, 10, 20, 2), "b": (10, 10, 20, 2)})
    assert r["a"] > 1.0 > r["b"]
    assert abs((r["a"] + r["b"]) / 2 - 1.0) < 1e-9


def test_event_mvp_and_the_ranking_follow_results():
    rng = random.Random(1)
    clubs = [Club(f"C{i}", rank=i + 1, roster=[pl(f"p{i}{j}", 75 - i * 3) for j in range(5)]) for i in range(8)]
    hl = Hltw()
    sysm = Systems(hltw=hl, development=False)
    t = Tournament("Masters", "A", 500_000, [0.5, 0.3, 0.1, 0.1], divisions=(4,))
    order = run_tournament(t, clubs, RelationGraph(), 14, rng, SeasonLog(), sysm)
    assert len(hl.mvps) == 1 and hl.mvps[0]["event"] == "Masters"
    mvp = next(p for c in clubs for p in c.roster if p.name == hl.mvps[0]["player"])
    assert mvp.fame >= 4 and any("MVP Masters" in h for h in mvp.history)
    hl.week(clubs, 15)
    assert hl.ranking[0] == order[0].name and hl.place(order[-1].name) == 8
    small = Tournament("Open", "C", 1_000, [1.0], divisions=(4,))
    run_tournament(small, clubs, RelationGraph(), 16, rng, SeasonLog(), sysm)
    assert len(hl.mvps) == 1                      # no MVP for an open cup


def test_a_season_has_mvps_a_top20_and_an_elo_for_everyone(season_game):
    g = season_game
    hl, hc = g.sysm.hltw, g.sysm.haceit
    events = {m["event"] for m in hl.mvps}
    assert {"Major", "World Final"} <= events and not any("Open Cup" in e for e in events)
    top = hl.top20[1]
    assert len(top) == 20 and top[0]["rating"] >= top[-1]["rating"] - 0.12
    assert len(hl.ranking) == 30
    everyone = [p for c in g.clubs for p in c.roster]
    assert sum(p.name in hc.elo for p in everyone) >= len(everyone) - 12   # but new signings of week 53
    texts = [e.text for e in g.sysm.chronicle.entries if e.kind == "media"]
    assert any(t.startswith("HLTW: игрок сезона 1") for t in texts)
