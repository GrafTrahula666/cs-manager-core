import random

from csmcore import development, promises
from csmcore.board import Owner
from csmcore.economy import Club, Contract
from csmcore.market import Market, expected_salary
from csmcore.player import STATS, Player
from csmcore.relations import RelationGraph
from csmcore.scouting import Scouting
from csmcore.squad import cliques, hierarchy
from csmcore.world import WeekPlan, stress_level, update_state


def p(name, level=65, **kw):
    return Player(name, {s: level for s in STATS}, **kw)


def test_young_players_grow_toward_potential_veterans_lose_mechanics():
    rng = random.Random(1)
    club = Club("C", coach_quality=70)
    kid, vet = p("kid", 60, age=17), p("vet", 75, age=31)
    kid.potential, vet.potential = 80, 75
    for _ in range(12):
        development.month(kid, club, rng)
        development.month(vet, club, rng)
    assert kid.overall() > 63
    assert vet.stats["reaction"] < 75 and vet.stats["game_sense"] > 75


def test_better_coach_develops_faster():
    def grow(q):
        k = p("k", 60, age=17)
        k.potential = 85
        for _ in range(6):
            development.month(k, Club("C", coach_quality=q), random.Random(0))
        return k.overall()
    assert grow(90) > grow(20)


def test_scouting_range_narrows_and_hidden_traits_reveal_late():
    target = p("t", 70, traits=["lan_animal", "wrist_of_glass"], personality={"ego": 90})
    sc = Scouting(Club("C", scout_quality=60))
    first = sc.report(target)
    assert first.traits == [] and first.personality == {}
    lo, hi = first.stats["aim"]
    assert hi - lo > 40
    sc.observe(target, weeks=10)
    mid = sc.report(target)
    assert "lan_animal" in mid.traits and "wrist_of_glass" not in mid.traits
    sc.observe(target, weeks=40, source="teammate")
    late = sc.report(target)
    lo, hi = late.stats["aim"]
    assert hi - lo <= 6 and lo <= 70 <= hi
    assert "wrist_of_glass" in late.traits and late.personality["ego"] == "высоко"


def test_promise_kept_vs_broken_and_leader_spreads_distrust():
    g = RelationGraph()
    leader = p("boss", personality={"ego": 80})
    leader.stats["leadership"] = 99
    others = [p(f"x{i}") for i in range(4)]
    club = Club("C", roster=[leader, *others])
    club.contracts["boss"] = Contract("boss", 10_000, 999, 0)
    ok = promises.make(leader, "raise", deadline=4, week=0, value=10_000)
    bad = promises.make(leader, "raise", deadline=4, week=0, value=50_000)
    trust_before = others[0].s("coach_trust")
    out = promises.check([ok, bad], club, g, week=4)
    assert ok.status == "kept" and bad.status == "broken"
    assert "transfer_requested" in leader.flags
    assert others[0].s("coach_trust") < trust_before
    assert any("лидер" in line for line in out)


def test_hierarchy_and_cliques():
    g = RelationGraph()
    a, b, c, d = p("a"), p("b"), p("c"), p("d")
    a.stats["leadership"] = 95
    club = Club("C", roster=[a, b, c, d])
    g.set_pair("a", "b", friendship=90, trust=90, respect=90)
    g.set_pair("c", "d", friendship=90, trust=90, respect=90)
    assert hierarchy(club, g)["leaders"] == [a]
    assert sorted(cliques(club, g)) == [["a", "b"], ["c", "d"]]


def test_owner_fires_manager_when_failing():
    club = Club("C", rank=40, cash=-500_000)
    o = Owner(patience=10, ambition=90, money_focus=80)
    o.set_objectives(club)
    for w in range(4, 60, 4):
        o.monthly_review(club, w)
    assert o.fired
    happy = Owner(patience=80)
    good = Club("G", rank=10, cash=1e6)
    happy.set_objectives(good)
    good.rank = 1
    for w in range(4, 30, 4):
        happy.monthly_review(good, w)
    assert happy.confidence > 60 and happy.next_budget(10_000) > 10_000


def test_acting_against_personality_is_stressful_and_coping_helps():
    rng = random.Random(0)
    shy = p("shy", personality={"media": 10})
    shy.state["stress"] = 50
    update_state(shy, WeekPlan(commercial_days=3), rng, Club("C"))
    calm = p("calm", personality={"media": 10}, traits=["party_animal"])
    calm.state["stress"] = 50
    update_state(calm, WeekPlan(commercial_days=3), random.Random(0), Club("C"))
    assert shy.s("stress") > 50 and calm.s("stress") < shy.s("stress")
    shy.state["stress"] = 90
    assert stress_level(shy) == 3


def test_market_signs_free_agent_and_sends_offers_to_manager():
    rng = random.Random(3)
    star = p("star", 75, personality={"money_focus": 50, "ambition": 30, "loyalty": 0})
    market = Market(free_agents=[star])
    weak = [p(f"w{i}", 55) for i in range(5)]
    ai = Club("AI", tier="super", cash=10_000_000, rank=1, roster=weak)
    notes = market.week([ai], 4, rng)
    assert star in ai.roster and notes
    assert expected_salary(p("x", 75)) > expected_salary(p("y", 55)) * 10

    mine = p("mine", 74)
    mine.flags.add("transfer_requested")
    me = Club("Me", cash=0, rank=5, roster=[mine])
    me.contracts["mine"] = Contract("mine", 20_000, 200, 1_000_000)
    buyer = Club("Buyer", tier="super", cash=50_000_000, rank=2, roster=[p(f"b{i}", 60) for i in range(5)])
    market.week([buyer, me], 8, rng, manager_club="Me")
    assert market.offers and market.offers[0].player is mine
