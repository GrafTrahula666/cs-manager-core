"""Club money (P1): salaries and prices follow the world's level, not an absolute scale."""
import pytest

from csmcore.economy import Club, LevelScale, market_value
from csmcore.game import Game
from csmcore.market import Market, expected_salary
from csmcore.player import STATS, Player


def club(name, level, n=5):
    return Club(name, roster=[Player(f"{name}{i}", {s: level for s in STATS}, age=25) for i in range(n)])


def test_when_the_whole_world_gets_better_a_player_keeps_his_price():
    clubs = [club("A", 70), club("B", 60), club("C", 50)]
    m = Market()
    star = clubs[0].roster[0]
    scale = m.rescale(clubs)
    pay, value = expected_salary(star, scale), market_value(star, scale)
    for c in clubs:
        for p in c.roster:
            for s in STATS:
                p.stats[s] += 8
    scale = m.rescale(clubs)
    assert expected_salary(star, scale) == pytest.approx(pay)
    assert market_value(star, scale) == pytest.approx(value)
    assert expected_salary(star) > pay * 2   # on the absolute scale he would ask for much more


def test_the_scale_follows_the_place_in_the_world_when_the_top_pulls_away():
    scale = LevelScale(ref=[50.0, 60.0, 70.0], now=[52.0, 63.0, 82.0])
    assert scale(52.0) == pytest.approx(50.0) and scale(82.0) == pytest.approx(70.0)
    assert scale(72.5) == pytest.approx(65.0)        # halfway between the 50% and 100% marks
    assert scale(90.0) == pytest.approx(78.0)        # beyond the best: the same distance above
    assert scale.today(65.0) == pytest.approx(72.5)


def test_a_version_4_save_gets_the_world_scale():
    from csmcore import save
    g = Game.new(seed=6, n_clubs=40)
    for _ in range(3):
        g.advance()
    m = g.sysm.market
    for k in ("level_ref", "level_scale"):   # a pickle from before the world scale
        m.__dict__.pop(k, None)
    raw = save.dumps(g)
    g2 = save.loads(raw[:len(save.MAGIC)] + bytes([4]) + raw[len(save.MAGIC) + 1:])
    m2 = g2.sysm.market
    assert m2.level_ref == list(save.WORLD_QUANTILES_AT_START) and m2.level_scale is not None
    for _ in range(3):
        g2.advance()


def test_season_money_totals_survive_the_ledger_trim():
    from csmcore import api
    g = Game.new(seed=3, n_clubs=40)
    ai = next(c for c in g.clubs if c.name != g.club_name)
    cash0 = ai.cash
    for _ in range(53):
        g.advance()
    assert len(ai.money_history) == 1 and ai.money_season
    year = ai.money_history[0]
    assert year["salaries"] < 0 and year["staff"] < 0
    assert min(x.week for x in ai.ledger) > 26   # the ledger itself keeps only recent lines
    assert cash0 + sum(year.values()) + sum(ai.money_season.values()) == pytest.approx(ai.cash, abs=1.0)
    api.G = g
    assert api.finances()["past_seasons"]


def test_a_fairly_paid_player_of_a_small_club_mostly_extends_and_an_underpaid_one_leaves():
    from csmcore.decisions import contract_acceptance
    from csmcore.economy import Contract
    small = Club("Small", tier="tier3", rank=90)
    p = Player("mid", {s: 52 for s in STATS}, age=24)
    p.personality["ambition"], p.personality["loyalty"] = 50.0, 50.0
    fair = contract_acceptance(p, Contract("mid", 1_000, 104, 0.0), 1_000, small, staying=True)
    low = contract_acceptance(p, Contract("mid", 600, 104, 0.0), 1_000, small, staying=True)
    assert fair.p > 0.7 and low.p < 0.4
    assert any("лучшего предложения нет" in r for r in fair.reasons)
