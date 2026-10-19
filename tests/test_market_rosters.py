"""Found by the world simulation lab: half the AI clubs played without five players while free
agents waited for offers they would accept."""
import random

from csmcore.decisions import contract_acceptance
from csmcore.economy import Club, Contract
from csmcore.game import Game
from csmcore.market import ROSTER_MAX, Market, asking, expected_salary, free_weeks
from csmcore.player import STATS, Player


def pl(name, level=55, ambition=80.0, age=24):
    p = Player(name, {s: level for s in STATS}, age=age)
    p.personality["ambition"] = ambition
    p.former_clubs.add("Old Club")
    return p


def test_a_free_agent_asks_less_and_cares_less_about_prestige_every_month():
    p = pl("fa")
    p.free_since = 0
    assert asking(p, 0) == expected_salary(p)
    assert asking(p, 16) < asking(p, 4) < expected_salary(p)
    assert asking(p, 400) >= expected_salary(p) * 0.45
    small = Club("Small", tier="tier3", rank=100)
    offer = Contract("fa", asking(p, 0), 52, 0.0)
    fresh = contract_acceptance(p, offer, asking(p, 0), small, free_weeks=free_weeks(p, 0)).p
    later = contract_acceptance(p, Contract("fa", asking(p, 30), 82, 0.0), asking(p, 30), small,
                                free_weeks=free_weeks(p, 30)).p
    assert fresh < 0.25 < later


def test_a_teenager_wants_his_first_contract():
    kid = Player("kid", {s: 50 for s in STATS}, age=17)
    kid.free_since = 10
    assert free_weeks(kid, 10) >= 24
    kid.former_clubs.add("Academy")
    assert free_weeks(kid, 10) == 0


def test_short_clubs_sign_between_windows_and_big_rosters_let_one_go():
    rng = random.Random(3)
    short = Club("Short", tier="tier3", rank=90, cash=200_000, roster=[pl(f"s{i}", 50) for i in range(3)])
    big = Club("Big", tier="tier1", rank=5, cash=5_000_000, roster=[pl(f"b{i}", 70) for i in range(ROSTER_MAX + 2)])
    fas = [pl(f"fa{i}", 52, ambition=10.0) for i in range(4)]
    m = Market(free_agents=fas)
    notes = m.week([short, big], 5, rng)            # not a window: only the short club looks
    assert len(short.roster) >= 4 and len(big.roster) == ROSTER_MAX + 2
    m.week([short, big], 8, rng)                    # a window: the big club trims one
    assert len(big.roster) == ROSTER_MAX + 1 and any(p.name.startswith("b") for p in m.free_agents)
    assert notes


def test_a_season_keeps_almost_every_club_at_five():
    g = Game.new(seed=4, n_clubs=40)
    worst = 0
    for w in range(52):
        g.advance()
        if 8 <= w <= 48:
            worst = max(worst, sum(len(c.roster) < 5 for c in g.clubs if c.name != g.club_name))
    assert worst <= 3
    assert max(len(c.roster) for c in g.clubs if c.name != g.club_name) <= ROSTER_MAX + 1
