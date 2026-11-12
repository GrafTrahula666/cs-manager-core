"""The two included starting rooms must not silently increase club expenses."""

import pytest

from csmcore import api, save
from csmcore.economy import WEEKS_PER_MONTH


@pytest.fixture
def game():
    api.new_game(71, 24)
    return api._g()


def test_starting_rooms_are_included_in_baseline_budget(game):
    assert game.base.level("training_zone") == 1
    assert game.base.level("lounge") == 1
    assert game.base.upkeep_of("training_zone", 1) == 0
    assert game.base.upkeep_of("lounge", 1) == 0
    assert game.base.upkeep_month() == api.home()["upkeep_month"] == 0
    report = api.home()
    room = next(x for x in report["facilities"] if x["id"] == "training_zone")
    assert room["next"]["upkeep_month"] == 4000


def test_starting_room_upkeep_does_not_create_hidden_ledger_lines(game):
    start = len(game.club.ledger)
    for _ in range(3):
        game.advance()
    charges = game.club.ledger[start:]
    assert not [line for line in charges if line.item == "facilities"]
    assert any(line.item == "staff" or line.item == "staff_month" for line in charges)


def test_upgrade_bills_only_difference_and_reports_incremental_price(game):
    game.base.levels["training_zone"] = 2
    game.base.levels["lounge"] = 2
    assert game.base.upkeep_of("training_zone", 2) == 4000
    assert game.base.upkeep_of("lounge", 2) == 2000
    assert game.base.upkeep_month() == 6000
    assert next(x for x in api.home()["facilities"] if x["id"] == "training_zone")["next"]["upkeep_month"] >= 0
    start = len(game.club.ledger)
    game.advance()
    fees = [line for line in game.club.ledger[start:] if line.item == "facilities"]
    assert len(fees) == 2
    assert sum(line.amount for line in fees) == pytest.approx(-6000 / WEEKS_PER_MONTH, abs=0.02)


def test_new_room_still_has_full_upkeep_after_building(game):
    game.base.levels["analytics_center"] = 1
    assert game.base.upkeep_of("analytics_center", 1) == 6000
    start = len(game.club.ledger)
    game.advance()
    fees = [line for line in game.club.ledger[start:] if line.item == "facilities"]
    assert len(fees) == 1
    assert fees[0].amount == pytest.approx(-6000 / WEEKS_PER_MONTH, abs=0.01)


def test_existing_save_keeps_rooms_and_projects_without_retroactive_refunds(game):
    game.club.cash = 20_000_000
    api.build("analytics_center")
    history = list(game.club.ledger)
    old_cash = game.club.cash
    loaded = save.loads(save.dumps(game))
    loaded.ensure_living()
    assert loaded.base.levels == game.base.levels
    assert loaded.base.projects == game.base.projects
    assert loaded.club.cash == old_cash
    assert len(loaded.club.ledger) == len(history)
    assert loaded.base.upkeep_month() == 0
