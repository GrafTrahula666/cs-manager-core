"""LC-034 / LC-063: a save made by main (save v4: LIVING CLUB, a built academy, XP) loads under the club-money P1 code
(save v5) without paying construction or XP twice, and the money keeps adding up through the ledger.
The fixture was produced by running main at 99583ee: seed 5, 24 clubs, 8 weeks, academy built and finished."""
import json
import pathlib

import pytest

from csmcore import api

D = pathlib.Path(__file__).parent / "data"


@pytest.fixture()
def meta():
    return json.loads((D / "save_v4_main_living.json").read_text())


def _load():
    api.load_b64((D / "save_v4_main_living.b64").read_text())
    return api._g()


def test_v4_main_save_loads_with_everything_intact(meta):
    g = _load()
    g.ensure_living()
    assert g.club_name == meta["club"] and g.week == meta["week"]
    assert (g.living.xp, g.living.level) == (meta["xp"], meta["level"])
    assert g.club.cash == pytest.approx(meta["cash"], abs=0.01)
    assert g.base.level("academy") == 1 and g.base.projects == meta["projects"]


def test_p1_fields_exist_after_migration():
    g = _load()
    assert hasattr(g.club, "money_history") and hasattr(g.sysm.market, "level_scale")


def test_reloading_never_repays_or_regrants(meta):
    for _ in range(3):
        g = _load()
        g.ensure_living()
        assert (g.living.xp, g.living.level) == (meta["xp"], meta["level"])
        assert g.club.cash == pytest.approx(meta["cash"], abs=0.01)


def test_playing_on_keeps_the_ledger_honest(meta):
    g = _load()
    g.ensure_living()
    cash0, n0, xp0 = g.club.cash, len(g.club.ledger), g.living.xp
    for _ in range(6):
        g.advance()
    new = g.club.ledger[n0:]
    assert not [l for l in new if l.item == "construction"]           # the academy is not paid a second time
    assert g.club.cash == pytest.approx(cash0 + sum(l.amount for l in new), abs=1.0)
    assert g.living.xp >= xp0
    ups = [l for l in new if l.item == "facilities" and "Академия" in l.why]
    assert len(ups) == 6                                              # upkeep: exactly one line a week
