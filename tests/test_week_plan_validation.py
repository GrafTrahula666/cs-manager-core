"""Weekly manager actions reject invalid numeric payloads before touching the game."""

import math

import pytest

from csmcore import api, save
from csmcore.game import Game
from csmcore.world import WeekPlan


@pytest.fixture
def game(monkeypatch):
    g = Game.new(seed=61, n_clubs=24)
    monkeypatch.setattr(api, "G", g)
    return g


@pytest.mark.parametrize("bad", [
    {"practice_hours": -1},
    {"practice_hours": 50.1},
    {"practice_hours": float("nan")},
    {"practice_hours": float("inf")},
    {"practice_hours": float("-inf")},
    {"practice_hours": True},
    {"practice_hours": "40"},
    {"rest_days": -1},
    {"rest_days": 4},
    {"rest_days": 1.5},
    {"rest_days": float("nan")},
    {"rest_days": True},
    {"commercial_days": -1},
    {"commercial_days": 4},
    {"commercial_days": 1.5},
    {"commercial_days": float("inf")},
    {"commercial_days": "2"},
    {"bootcamp": "yes"},
])
def test_invalid_api_plan_does_not_replace_existing_plan_or_change_save(game, bad):
    old = game.desk.set_week(practice_hours=18, rest_days=2, commercial_days=1)
    before = save.dumps(game)
    before_rng = game.rng.getstate()

    with pytest.raises(ValueError):
        api.plan(**bad)

    assert game.desk.plan is old
    assert save.dumps(game) == before
    assert game.rng.getstate() == before_rng


@pytest.mark.parametrize("bad", [
    {"travel": "yes"},
    {"travel": 1},
    {"commercial_days": False},
])
def test_direct_manager_desk_week_plan_has_the_same_guards(game, bad):
    before = game.desk.plan
    before_bytes = save.dumps(game)

    with pytest.raises(ValueError):
        game.desk.set_week(**bad)

    assert game.desk.plan is before
    assert save.dumps(game) == before_bytes


def test_valid_boundaries_and_existing_week_plan_flow(game):
    old = game.desk.plan
    result = api.plan(0, 0, False, 0)
    assert result == {
        "practice_hours": 0, "rest_days": 0, "bootcamp": False, "commercial_days": 0
    }
    assert game.desk.plan == WeekPlan(practice_hours=0, rest_days=0, bootcamp=False, commercial_days=0)
    assert game.desk.plan is not old

    result = api.plan(50, 3.0, True, 3.0)
    assert result["practice_hours"] == 50
    assert game.desk.plan == WeekPlan(practice_hours=50, rest_days=3.0, bootcamp=True, commercial_days=3.0)
    assert game.desk.set_week(travel=True, practice_hours=24).travel is True
    assert all(math.isfinite(v) for v in (
        game.desk.plan.practice_hours, game.desk.plan.rest_days, game.desk.plan.commercial_days
    ))


def test_valid_plan_survives_save_load_and_remains_one_week_only(game):
    api.plan(25.5, 2, True, 1)
    resumed = save.loads(save.dumps(game))
    assert resumed.desk.plan == game.desk.plan
    assert resumed.desk.plan.practice_hours == 25.5

    news1, news2 = game.advance(), resumed.advance()
    assert news1 == news2
    assert game.desk.plan == resumed.desk.plan == WeekPlan()
    assert game.rng.getstate() == resumed.rng.getstate()
