"""Characterization of Game.advance() ordering and deterministic continuation.

These tests intentionally avoid changing the simulation's mechanics or save layout.
"""

from types import SimpleNamespace

import pytest

from csmcore import game as game_module, save
from csmcore.game import Game, WeekNews
from csmcore.world import WeekPlan


@pytest.mark.parametrize("last_week", [0, 51])
def test_advance_preserves_week_order_and_consumes_plan_once(monkeypatch, last_week):
    game = Game.new(seed=19, n_clubs=24)
    game.run.wk = last_week
    game.desk.plan = WeekPlan(practice_hours=27, rest_days=2)
    previous_plan = game.desk.plan
    order = []

    def tick(run, clubs, graph, calendar, systems, plans):
        order.append("season_week")
        assert run is game.run
        assert clubs is game.clubs and systems is game.sysm
        assert plans == {game.club_name: previous_plan}
        assert plans[game.club_name] is previous_plan
        run.wk += 1

    def collect():
        order.append("collect")
        return ["week news"]

    def living():
        order.append("living")
        return ["manager news"]

    def base_week(g):
        assert g is game
        order.append("base")
        return ["base news"]

    def finish(run, clubs, systems):
        order.append("season_finish")
        assert run.wk == 52

    def rollover():
        order.append("new_season")
        return ["season news"]

    def trim():
        order.append("trim")

    def counts():
        order.append("counts")
        return (0, 0, 0, 0)

    monkeypatch.setattr(game, "_assistant_decides", lambda: order.append("assistant"))
    monkeypatch.setattr(game_module, "season_week", tick)
    monkeypatch.setattr(game_module, "season_finish", finish)
    monkeypatch.setattr(game, "_collect", collect)
    monkeypatch.setattr(game, "_living_week", living)
    monkeypatch.setattr(game, "_new_season", rollover)
    monkeypatch.setattr(game, "_trim", trim)
    monkeypatch.setattr(game, "_counts", counts)
    game.base = SimpleNamespace(week=base_week)

    news = game.advance()
    expected_order = ["assistant", "season_week", "collect", "living", "base"]
    if last_week == 51:
        expected_order += ["season_finish", "new_season"]
    expected_order += ["trim", "counts"]
    assert order == expected_order
    assert (news.week, news.season) == (last_week + 1, 1)
    assert news.lines == ["week news", "manager news", "base news"] + (
        ["season news"] if last_week == 51 else []
    )
    assert game.history[-1] is news
    assert game._seen == (0, 0, 0, 0)
    assert game.desk.plan is not previous_plan
    assert game.desk.plan == WeekPlan()


def _world_snapshot(game):
    return [(c.name, c.rank, c.cash, c.debt, c.season_points,
             tuple(p.name for p in c.roster), len(c.ledger)) for c in game.clubs]


def _random_streams(game):
    return (game.rng.getstate(), game.run.rng.getstate(), game.run.meta_rng.getstate(),
            game.run.story_rng.getstate(), game.run.mgmt_rng.getstate())


def test_real_week_continues_identically_from_save_with_all_random_streams():
    game = Game.new(seed=31, n_clubs=24)
    for _ in range(2):
        game.advance()
    game.desk.set_week(practice_hours=25, rest_days=2)
    resumed = save.loads(save.dumps(game))

    for _ in range(3):
        assert game.advance() == resumed.advance()
        assert _world_snapshot(game) == _world_snapshot(resumed)
        assert _random_streams(game) == _random_streams(resumed)
        assert game._seen == resumed._seen
        assert game.history == resumed.history
        assert game.desk.plan == resumed.desk.plan == WeekPlan()


def test_advance_keeps_only_latest_sixty_week_news():
    game = Game.new(seed=37, n_clubs=24)
    game.history = [WeekNews(i, 1, []) for i in range(60)]
    news = game.advance()
    assert len(game.history) == 60
    assert game.history[0].week == 1
    assert game.history[-1] is news
