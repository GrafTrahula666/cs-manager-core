"""Port of the LC-001 status display slice from draft PR #11.

Planned effects must not be presented as active mechanics in the UI.
This is visibility metadata only: no world, economy or save-format changes.
"""

import copy
from pathlib import Path

import pytest

from csmcore import api, base, livingdata


@pytest.fixture
def game():
    api.new_game(7)
    return api._g()


def test_all_talent_channels_have_known_status_and_are_not_wired():
    assert livingdata.validate() == []
    channels = livingdata.load("talents")["channels"]
    assert {c["status"] for c in channels.values()} <= set(livingdata.STATUSES)
    assert all(not livingdata.is_active(c["status"]) for c in channels.values())
    assert livingdata.is_active("wired")
    assert livingdata.is_active("tested")
    assert livingdata.is_active("calibrated")
    assert not livingdata.is_active("planned")


def test_unknown_channel_status_fails_data_validation(monkeypatch):
    original = livingdata.load
    bad = copy.deepcopy(original("talents"))
    name = next(iter(bad["channels"]))
    bad["channels"][name]["status"] = "magic"
    monkeypatch.setattr(livingdata, "load", lambda n: bad if n == "talents" else original(n))
    assert any("unknown status" in error and name in error for error in livingdata.validate())


def test_talent_nodes_and_unlocked_channels_report_inactive(game):
    node = next(n for n in api.living()["nodes"] if n["tier"] == 1)
    for i in range(5):
        game.living.grant("career_milestone", f"status-test-{i}", 1)
    api.unlock_talent(node["id"])
    state = api.living()
    assert state["channels"]
    assert all(effect["active"] is False for n in state["nodes"] for effect in n["effect"])
    assert all(channel["active"] is False for channel in state["channels"])


def test_existing_and_next_facility_effects_report_real_status(game, monkeypatch):
    home = api.home()
    assert all(not e["active"] for f in home["facilities"] if f["next"] for e in f["next"]["effects"])
    current = next(f for f in home["facilities"] if f["id"] == "training_zone")
    assert current["now"] and all(not e["active"] for e in current["now"])
    monkeypatch.setitem(base.EFFECT_STATUS, "training.quality", "wired")
    current = next(f for f in api.home()["facilities"] if f["id"] == "training_zone")
    assert any(e["active"] for e in current["now"])
    assert any(e["active"] for e in current["next"]["effects"])


def test_web_labels_unwired_effects_without_active_bonus_style():
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert 'const fx = (e) =>' in html
    assert 'e.active ? "plus" : "muted"' in html
    assert '!c.active ? "muted"' in html
    assert 'пока не действует' in html
