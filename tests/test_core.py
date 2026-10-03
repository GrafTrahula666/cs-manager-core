import random

from csmcore import economy
from csmcore.decisions import contract_acceptance
from csmcore.economy import Club, Contract, Sponsor, Tournament
from csmcore.engine import play_map
from csmcore.generate import concept_examples, make_player
from csmcore.player import STATS, Player
from csmcore.relations import RelationGraph
from csmcore.traits import library, roll_traits
from csmcore.world import WeekPlan, world_week


def flat(name, level=70, **kw):
    return Player(name, {s: level for s in STATS}, **kw)


def test_trait_library_loads_and_respects_incompatibility():
    lib = library()
    assert len(lib) >= 36 and "lan_animal" in lib
    rng = random.Random(0)
    for _ in range(2000):
        picked = roll_traits(rng)
        assert 1 <= len(picked) <= 3
        assert not {"homebody", "nomad"} <= set(picked)


def test_traits_only_fire_in_their_context():
    plain, lan = flat("a"), flat("b", traits=["lan_animal"])
    assert lan.duel_skill({"lan": False}) == plain.duel_skill({"lan": False})
    assert lan.duel_skill({"lan": True}) > plain.duel_skill({"lan": True})


def test_pressure_hurts_and_match_point_ice_ignores_it():
    calm = {}
    mp = {"playoffs": True, "match_point": True}
    normal, ice = flat("a"), flat("b", traits=["match_point_ice"])
    assert normal.duel_skill(mp) < normal.duel_skill(calm)
    assert normal.duel_skill(mp) - normal.duel_skill(calm) < ice.duel_skill(mp) - ice.duel_skill(calm)


def test_concept_examples_are_loaded():
    ex = concept_examples()
    assert ex["vanta"].stats["aim"] == 91 and "role_thief" in ex["vanta"].traits
    assert ex["north"].stats["leadership"] == 96


def test_chemistry_main_criterion():
    """Concept: replace a conflicting star with a weaker but compatible player and the team
    should win more, for a reason the engine can show (chemistry)."""
    rng = random.Random(3)
    core = [make_player(f"p{i}", 68, rng) for i in range(4)]
    star, fit = flat("star", 74), flat("fit", 70)
    g = RelationGraph()
    for p in core:
        g.set_pair(star.name, p.name, irritation=80, resentment=60, trust=20)
        g.set_pair(fit.name, p.name, trust=75, friendship=70, respect=70)
    with_star, with_fit = core + [star], core + [fit]
    opp = [flat(f"o{i}", 70) for i in range(5)]
    assert g.chemistry(with_fit) > g.chemistry(with_star)
    assert g.friction_report(with_star)

    def wins(team):
        chem = (g.chemistry(team), 0.0)
        return sum(play_map(team, opp, seed=s, chemistry=chem).score[0] == 13 for s in range(300))

    assert wins(with_fit) > wins(with_star)


def test_contract_acceptance_depends_on_personality():
    club = Club("Rich", tier="tier1", rank=5)
    offer = Contract("x", 20_000, 100, 0)
    mercenary = flat("m", personality={"money_focus": 95, "ambition": 50, "loyalty": 10})
    idealist = flat("i", personality={"money_focus": 5, "ambition": 50, "loyalty": 10})
    low = Contract("x", 12_000, 100, 0)
    assert contract_acceptance(mercenary, low, 20_000, club).p < contract_acceptance(idealist, low, 20_000, club).p
    homebody = flat("h", personality={"home_attachment": 95}, traits=["homebody"])
    assert contract_acceptance(homebody, offer, 20_000, club, relocation=True).p < \
        contract_acceptance(homebody, offer, 20_000, club, relocation=False).p


def test_weekly_finances_ledger_and_bankruptcy():
    p = flat("a")
    club = Club("Poor", tier="tier3", cash=1_000, roster=[p], staff_month=0)
    club.contracts["a"] = Contract("a", 10_000, 999, 0)
    for w in range(1, 20):
        economy.weekly_finances(club, w)
    assert club.balance()["salaries"] < 0
    assert club.bankrupt

    rich = Club("Rich", tier="tier1", cash=0, roster=[flat("b")], staff_month=0)
    rich.sponsors.append(Sponsor("S", "hardware", 520_000, 999))
    economy.weekly_finances(rich, 1)
    assert round(rich.balance()["sponsors"]) == 10_000


def test_betting_pays_more_but_costs_fans():
    club = Club("C", tier="tier2", brand=50, rank=10, roster=[flat("a")])
    assert economy.sponsor_offer(club, "betting") > economy.sponsor_offer(club, "hardware")
    club.sponsors.append(Sponsor("Bet", "betting", 100_000, 999))
    fans = club.fans
    for w in range(1, 53):
        economy.weekly_finances(club, w)
    assert club.fans < fans


def test_prize_split_and_major_stickers():
    roster = [flat(f"p{i}") for i in range(5)]
    club = Club("C", roster=roster, cash=0)
    for p in roster:
        club.contracts[p.name] = Contract(p.name, 1, 999, 0, prize_share_player=0.8)
    major = Tournament("Major", "S", 1_000_000, [0.5, 0.2], major=True, sticker_revenue=10_000_000)
    kept = economy.award(club, major, 1, 1, 16)
    assert round(club.balance()["prizes"]) == 100_000            # club keeps 20% of 500k
    assert round(club.balance()["stickers"]) == round(10_000_000 * 0.0285 / 2)
    assert round(kept) == round(club.cash)
    assert all(p.earnings > 0 for p in roster)


def test_transfer_moves_money_and_player():
    p = flat("star")
    seller = Club("S", roster=[p], cash=0)
    seller.contracts["star"] = Contract("star", 50_000, 100, 2_000_000)
    buyer = Club("B", cash=5_000_000)
    economy.transfer(buyer, seller, p, 2_000_000, Contract("star", 80_000, 200, 3_000_000), week=1)
    assert p in buyer.roster and p not in seller.roster
    assert seller.cash == 2_000_000 and buyer.cash == 5_000_000 - 2_000_000 * 1.05


def test_buyout_rule_of_thumb():
    # ~1.5-3 annual salaries for a player with 1+ year left
    assert 1.5 * 12 * 50_000 <= economy.buyout_for(50_000, 52) <= 3 * 12 * 50_000


def test_world_week_is_deterministic_and_explains_events():
    def run():
        ex = concept_examples()
        club = Club("C", tier="tier1", cash=1e7, rank=30, roster=list(ex.values()))
        g = RelationGraph()
        g.set_pair("vanta", "sable", irritation=60, role_rivalry=60)
        rng = random.Random(42)
        evs = []
        for w in range(1, 40):
            evs += world_week([club], g, w, rng, {"C": WeekPlan(practice_hours=45, travel=w % 2 == 0)})
        return [(e.week, e.kind, tuple(e.who)) for e in evs], evs

    a, evs = run()
    b, _ = run()
    assert a == b
    assert evs and all(e.causes for e in evs)
    assert any(e.kind == "conflict" and "vanta" in e.who for e in evs)


def test_demo_season_runs():
    import sys
    sys.path.insert(0, "scripts")
    from demo_season import build_world
    from csmcore.season import run_season
    clubs, graph, cal = build_world(1)
    log = run_season(clubs, graph, cal, seed=1)
    assert log.results and sorted(c.rank for c in clubs) == list(range(1, 9))
