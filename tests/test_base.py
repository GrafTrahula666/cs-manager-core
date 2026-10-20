"""LIVING CLUB stage 3-4: the base. Money only through Club.book, requirements, build time, upkeep, old saves."""
import pytest

from csmcore import api


@pytest.fixture()
def g():
    api.new_game(7)
    return api._g()


def test_home_lists_nine_facilities(g):
    h = api.home()
    assert len(h["facilities"]) == 9
    assert {f["id"] for f in h["facilities"] if f["level"] == 1} == {"training_zone", "lounge"}


def test_build_pays_through_ledger_and_takes_weeks(g):
    cash0 = g.club.cash
    api.build("streaming_room")
    assert g.club.cash == pytest.approx(cash0 - 150_000)
    assert any(l.item == "construction" and l.amount == -150_000 for l in g.club.ledger)
    assert g.base.level("streaming_room") == 0 and "streaming_room" in g.base.projects
    for _ in range(3):
        g.advance()
    assert g.base.level("streaming_room") == 1
    assert any(l.item == "facilities" and "Стриминг" in l.why for l in g.club.ledger)


def test_cannot_build_twice_or_without_money_or_requirements(g):
    api.build("academy")
    with pytest.raises(ValueError):
        api.build("academy")
    g.club.cash = 10
    with pytest.raises(ValueError):
        api.build("media_center")
    g.club.cash = 10_000_000
    g.club.fans = 10
    with pytest.raises(ValueError, match="фанатов"):
        api.build("lounge")      # level 2 needs fans


def test_parallel_limit(g):
    g.club.cash = 50_000_000
    api.build("academy")
    api.build("media_center")
    with pytest.raises(ValueError):
        api.build("medical_center")


def test_level_gets_xp_once(g):
    g.club.cash = 50_000_000
    xp0 = g.living.xp
    api.build("medical_center")
    for _ in range(4):
        g.advance()
    assert g.base.level("medical_center") == 1
    assert g.living.xp > xp0


def test_old_save_gets_a_base(g):
    g.base = None
    g.ensure_living()
    assert g.base is not None and g.base.level("training_zone") == 1


def test_upkeep_only_for_built_levels(g):
    m0 = api.home()["upkeep_month"]
    g.club.cash = 50_000_000
    api.build("lounge") if g.base.level("lounge") == 0 else api.build("academy")
    assert api.home()["upkeep_month"] == m0       # nothing is charged until the building is done
