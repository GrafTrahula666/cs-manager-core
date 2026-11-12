"""Compatibility and search regressions for the larger named-staff world."""

import pytest

from csmcore import api, save, staff as staff_module
from csmcore.game import Game


def test_old_staff_save_migrates_without_replacing_hires_or_consuming_rng():
    g = Game.new(seed=41, n_clubs=24)
    g.ensure_living()
    hired = g.staff.candidates()[0]
    g.club.cash = 5_000_000
    g.staff.hire(g, hired.id)
    old_market_size = len(g.staff.members)
    for member in g.staff.members.values():
        for key in ("country", "traits", "experience", "history", "employer", "employed_until"):
            member.__dict__.pop(key, None)
    g.staff.__dict__.pop("_world_v2", None)
    data = save.dumps(g)
    restored = save.loads(data)
    initial_rng = restored.staff.rng.getstate()
    restored.ensure_living()
    assert restored.staff.rng.getstate() == initial_rng
    assert len(restored.staff.members) == old_market_size
    assert restored.staff.members[hired.id].club == g.club_name
    assert restored.staff.members[hired.id].salary == hired.salary
    assert all(isinstance(m.traits, list) and isinstance(m.history, list) for m in restored.staff.members.values())
    assert all(m.employer is None for m in restored.staff.members.values())
    assert restored.staff._world_v2 is True


def test_old_staff_save_direct_advance_is_safe():
    g = Game.new(seed=43, n_clubs=24)
    g.ensure_living()
    for member in g.staff.members.values():
        member.__dict__.pop("employer", None)
        member.__dict__.pop("traits", None)
        member.__dict__.pop("history", None)
    g.staff.__dict__.pop("_world_v2", None)
    loaded = save.loads(save.dumps(g))
    loaded.advance()
    assert loaded.staff._world_v2
    assert loaded.run.wk == 1


def test_new_staff_world_has_420_unique_people_and_independent_rng():
    g = Game.new(seed=47, n_clubs=24)
    before = g.rng.getstate(), g.run.rng.getstate(), g.run.mgmt_rng.getstate()
    g.ensure_living()
    assert len(g.staff.members) == staff_module.WORLD_SIZE == 420
    assert len({m.id for m in g.staff.members.values()}) == 420
    assert len(g.staff.free()) > 0
    assert any(m.employer is not None for m in g.staff.members.values())
    assert (g.rng.getstate(), g.run.rng.getstate(), g.run.mgmt_rng.getstate()) == before


def test_search_paginates_and_rejects_employed_hires():
    api.new_game(49, 24)
    g = api._g()
    first = api.staff_search(role="tactical_analyst", page=0, per=7)
    assert first["total"] > 7 and len(first["items"]) == 7
    second = api.staff_search(role="tactical_analyst", page=1, per=7)
    assert {x["id"] for x in first["items"]}.isdisjoint({x["id"] for x in second["items"]})
    assert all(x["role"] == "tactical_analyst" for x in first["items"])
    busy = next(m for m in g.staff.members.values() if m.employer)
    with pytest.raises(ValueError, match="работает в клубе"):
        api.staff_hire(busy.id)
    assert g.staff.members[busy.id].club is None
