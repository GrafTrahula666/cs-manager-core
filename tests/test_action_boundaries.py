"""Action-boundary regressions: invalid UI indices must never mutate the simulation."""

import random

import pytest

from csmcore import api, save
from csmcore.economy import Club
from csmcore.game import Game
from csmcore.relations import RelationGraph
from csmcore.storylets import Fired, StoryEngine


def _event(club, title):
    return Fired("index_guard", 1, club, None, None, title, title, ["Принять"], [])


def _engine():
    return StoryEngine({"index_guard": {
        "id": "index_guard", "who": "club", "title": "Сделка",
        "text": "Тест", "effects": [{"cash": 50}],
        "options": [{"label": "Принять", "effects": [{"cash": 10}]}],
    }})


@pytest.fixture
def game(monkeypatch):
    g = Game.new(seed=41, n_clubs=24)
    monkeypatch.setattr(api, "G", g)
    return g


def test_invalid_event_and_option_indices_leave_entire_save_untouched(game):
    eng = _engine()
    eng.pending.extend([_event(game.club, "Первая"), _event(game.club, "Вторая")])
    game.sysm.stories = game.desk.stories = eng
    before = save.dumps(game)

    for i, option in [(-1, 0), (2, 0), (0, -1), (0, 1), (True, 0), (0, False)]:
        with pytest.raises(ValueError, match="нет такого"):
            api.answer_event(i, option)
        assert save.dumps(game) == before
        assert len(eng.pending) == 2


def test_valid_event_keeps_existing_effects_and_ui_echo(game):
    eng = _engine()
    eng.pending.append(_event(game.club, "Сделка"))
    game.sysm.stories = game.desk.stories = eng
    cash = game.club.cash

    result = api.answer_event(0, 0)
    assert len(result) == 2
    assert game.club.cash == cash + 60
    assert not eng.pending
    assert game.echoes[-1]["choice"] == "Принять"


def test_invalid_offer_index_is_rejected_before_manager_desk(game, monkeypatch):
    game.sysm.market.offers[:] = [object(), object()]
    calls = []

    def answer(i, accept, week):
        calls.append((i, accept, week))
        return "ok"

    monkeypatch.setattr(game.desk, "answer_offer", answer)
    for i in (-1, 2, True, 0.5):
        with pytest.raises(ValueError, match="нет такого предложения"):
            api.answer_offer(i, True)
    assert calls == []
    assert len(game.sysm.market.offers) == 2
    assert api.answer_offer(1, False) == "ok"
    assert calls == [(1, False, game.week)]


def test_story_engine_rejects_invalid_choice_before_any_side_effect():
    club = Club("Test", cash=1_000)
    eng = _engine()
    fired = _event(club, "Тест")
    eng.pending.append(fired)
    rng = random.Random(7)
    before_rng = rng.getstate()

    for bad in (-1, 1, False):
        with pytest.raises(ValueError, match="нет такого варианта"):
            eng.resolve(fired, bad, RelationGraph(), rng)
        assert club.cash == 1_000
        assert club.ledger == []
        assert fired.choice is None and fired.outcome == []
        assert eng.pending == [fired]
        assert rng.getstate() == before_rng
