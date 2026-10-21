"""PR A (LC-001, LC-003, LC-013, LC-063): statuses are honest, XP and construction money never repeat,
the start rooms do not raise the monthly bill, and the ledger adds up."""
import pytest

from csmcore import api, base, livingdata


@pytest.fixture()
def g():
    api.new_game(7)
    return api._g()


# ---- LC-001: planned means "not active" everywhere the player can see it ----
def test_every_talent_channel_has_a_known_status_and_none_is_active_yet():
    assert livingdata.validate() == []
    ch = livingdata.load("talents")["channels"]
    assert {c["status"] for c in ch.values()} <= set(livingdata.STATUSES)
    assert not any(livingdata.is_active(c["status"]) for c in ch.values())


def test_api_marks_inactive_talent_effects(g):
    node = next(n for n in api.living()["nodes"] if n["tier"] == 1)
    for i in range(5):
        g.living.grant("career_milestone", f"test-points-{i}", 1)
    assert g.living.available_points >= 1
    api.unlock_talent(node["id"])
    L = api.living()
    assert L["channels"] and all(c["active"] is False for c in L["channels"])
    assert all(e["active"] is False for n in L["nodes"] for e in n["effect"])


def test_facility_effects_are_inactive_until_wired(g, monkeypatch):
    h = api.home()
    assert all(not e["active"] for f in h["facilities"] if f["next"] for e in f["next"]["effects"]
               if e["key"] not in ("analysis.demo_depth", "analysis.slots"))   # these two are wired in staff.py
    f = next(x for x in h["facilities"] if x["id"] == "training_zone")
    assert f["now"] and all(not e["active"] for e in f["now"])
    monkeypatch.setitem(base.EFFECT_STATUS, "training.quality", "wired")
    f = next(x for x in api.home()["facilities"] if x["id"] == "training_zone")
    assert any(e["active"] for e in f["now"])


# ---- LC-013: construction and upkeep are charged exactly once ----
def test_start_rooms_add_no_hidden_upkeep(g):
    assert api.home()["upkeep_month"] == 0
    n0 = len(g.club.ledger)
    g.advance()
    assert not [l for l in g.club.ledger[n0:] if l.item == "facilities" and ("Тренировоч" in l.why or "отдыха" in l.why)]


def test_upgrade_charges_only_what_is_above_the_start_level(g):
    d = base.fac_data()["lounge"]["levels"]
    assert g.base.upkeep_of("lounge", 1) == 0
    assert g.base.upkeep_of("lounge", 2) == pytest.approx(d[1]["upkeep_month"] - d[0]["upkeep_month"])


def test_construction_and_upkeep_each_charged_once_and_ledger_adds_up(g):
    g.club.cash = 30_000_000
    cash0, n0 = g.club.cash, len(g.club.ledger)
    api.build("analytics_center")
    api.build("academy")
    for _ in range(12):
        g.advance()
    new = g.club.ledger[n0:]
    constr = [l for l in new if l.item == "construction"]
    assert sorted(l.amount for l in constr) == sorted([-180_000, -200_000])
    built = {f: g.base.level(f) for f in ("analytics_center", "academy")}
    assert built == {"analytics_center": 1, "academy": 1}
    weeks_up = {}
    for l in new:
        if l.item == "facilities":
            weeks_up.setdefault((l.week, l.why), 0)
            weeks_up[(l.week, l.why)] += 1
    assert weeks_up and max(weeks_up.values()) == 1            # never twice in the same week for one room
    assert g.club.cash == pytest.approx(cash0 + sum(l.amount for l in new))   # every cash move is a ledger line


# ---- LC-003 / LC-063: reloads and old saves never repay money or XP ----
def test_reloading_many_times_changes_neither_xp_nor_cash(g):
    for _ in range(10):
        g.advance()
    g.club.cash = 20_000_000
    api.build("academy")
    xp, lvl, cash, proj = g.living.xp, g.living.level, g.club.cash, dict(g.base.projects)
    blob = api.save_b64()
    for _ in range(3):
        api.load_b64(blob)
        g2 = api._g()
        g2.ensure_living()
        assert (g2.living.xp, g2.living.level, g2.club.cash, g2.base.projects) == (xp, lvl, cash, proj)
        blob = api.save_b64()


def test_old_save_without_living_club_gets_no_retroactive_xp_or_charges(g):
    """A save made before LIVING CLUB: it has titles in the chronicle and no manager profile or base."""
    ch = g.sysm.chronicle
    ch.titles.setdefault(g.club_name, []).extend(["Старый кубок (сезон 1)", "Другой кубок (сезон 1)"])
    g.living = None
    g.__dict__.pop("base", None)
    g.__dict__.pop("_titles_seen", None)
    blob = api.save_b64()
    for _ in range(2):
        api.load_b64(blob)
        g2 = api._g()
        s = api.state()
        assert (s["level"], s["xp"]) == (1, 0)
        cash = g2.club.cash
        n0 = len(g2.club.ledger)
        g2.advance()
        assert g2.living.xp == 0                                  # old titles are not paid out as XP
        assert not [l for l in g2.club.ledger[n0:] if l.item == "construction"]
        assert cash != 0
        blob = api.save_b64()
