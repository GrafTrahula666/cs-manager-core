"""Club money (P1): salaries and prices follow the world's level, not an absolute scale."""
import pytest

from csmcore.economy import Club, market_value
from csmcore.game import Game
from csmcore.market import Market, expected_salary, world_level
from csmcore.player import STATS, Player


def club(name, level, n=5):
    return Club(name, roster=[Player(f"{name}{i}", {s: level for s in STATS}, age=25) for i in range(n)])


def test_when_the_whole_world_gets_better_a_player_keeps_his_price():
    clubs = [club("A", 70), club("B", 60), club("C", 50)]
    m = Market()
    assert m.rescale(clubs) == 0.0
    star = clubs[0].roster[0]
    pay, value = expected_salary(star, m.level_shift), market_value(star, m.level_shift)
    for c in clubs:
        for p in c.roster:
            for s in STATS:
                p.stats[s] += 8
    assert m.rescale(clubs) == pytest.approx(8.0)
    assert expected_salary(star, m.level_shift) == pytest.approx(pay)
    assert market_value(star, m.level_shift) == pytest.approx(value)
    assert expected_salary(star) > pay * 2   # on the absolute scale he would ask for much more


def test_the_scale_is_the_best_sixth_of_rostered_players():
    clubs = [club("A", 80, 1), club("B", 50, 5)]
    assert world_level(clubs) == pytest.approx(80.0)


def test_a_version_4_save_gets_the_world_scale():
    from csmcore import save
    g = Game.new(seed=6, n_clubs=40)
    for _ in range(3):
        g.advance()
    m = g.sysm.market
    for k in ("level_ref", "level_shift"):   # a pickle from before the world scale
        m.__dict__.pop(k, None)
    raw = save.dumps(g)
    g2 = save.loads(raw[:len(save.MAGIC)] + bytes([4]) + raw[len(save.MAGIC) + 1:])
    m2 = g2.sysm.market
    assert m2.level_ref <= save.WORLD_LEVEL_AT_START
    assert m2.level_shift == pytest.approx(world_level(g2.clubs) - m2.level_ref)
    for _ in range(3):
        g2.advance()
