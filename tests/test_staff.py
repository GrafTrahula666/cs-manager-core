"""Stage B (LC-018, LC-019, LC-021): a person with an ID is found, hired on a contract, assigned to a workplace,
paid through the ledger, and produces one concrete result: the dossier on a rival club."""
import pytest

from csmcore import api, staff as staff_mod


@pytest.fixture()
def g():
    api.new_game(7, 24)
    g = api._g()
    g.club.cash = 20_000_000
    return g


def _analyst(g, best=True):
    c = [m for m in g.staff.candidates() if m.role == "tactical_analyst"]
    return max(c, key=lambda m: m.skill) if best else min(c, key=lambda m: m.skill)


def _target(g):
    return api.staff()["targets"][0]["name"]


def test_market_has_unique_ids_and_every_phase1_role(g):
    ids = [m.id for m in g.staff.members.values()]
    assert len(ids) == len(set(ids)) >= 20
    assert {m.role for m in g.staff.candidates()} == set(staff_mod.ROLES)


def test_hire_refuses_a_lowball_offer_and_pays_through_the_ledger(g):
    a = _analyst(g)
    with pytest.raises(ValueError, match="отказался"):
        api.staff_hire(a.id, 12, a.expectation * 0.5)
    sm0 = g.club.staff_month
    api.staff_hire(a.id, 12)
    cash0, n0 = g.club.cash, len(g.club.ledger)
    for _ in range(4):
        g.advance()
    lines = [l for l in g.club.ledger[n0:] if l.item == "staff_named"]
    assert len(lines) == 4 and all(l.amount == pytest.approx(-a.salary / (52 / 12)) for l in lines)    # once a week, no duplicates
    assert g.club.cash == pytest.approx(cash0 + sum(l.amount for l in g.club.ledger[n0:]), abs=1.0)
    assert g.club.staff_month == sm0                                      # the aggregate baseline is not touched


def test_workplace_rules(g):
    a = _analyst(g)
    api.staff_hire(a.id)
    with pytest.raises(ValueError, match="нужно здание"):
        api.staff_assign(a.id)
    api.build("analytics_center")
    for _ in range(3):
        g.advance()
    api.staff_assign(a.id)
    b = next(m for m in g.staff.candidates() if m.role == "tactical_analyst")
    api.staff_hire(b.id)
    with pytest.raises(ValueError, match="заняты"):
        api.staff_assign(b.id)                                            # level 1 has one analysis slot


def test_a_centre_without_an_analyst_produces_nothing(g):
    api.build("analytics_center")
    for _ in range(3):
        g.advance()
    api.staff_target(_target(g))
    for _ in range(6):
        g.advance()
    assert api.dossier(_target(g))["knowledge"] == 0


def _dossier_after(g, skill_pick, weeks=8, level=1):
    a = _analyst(g, skill_pick)
    api.staff_hire(a.id)
    g.base.levels["analytics_center"] = level
    api.staff_assign(a.id)
    t = _target(g)
    api.staff_target(t)
    for _ in range(weeks):
        g.advance()
    return api.dossier(t)


def test_assigned_analyst_shrinks_the_ranges():
    api.new_game(7, 24)
    g = api._g()
    g.club.cash = 20_000_000
    t = _target(g)
    before = api.dossier(t)
    assert before["knowledge"] == 0
    after = _dossier_after(g, True)
    assert after["knowledge"] > 30
    width = lambda d: sum(p["ovr_range"][1] - p["ovr_range"][0] for p in d["players"])
    assert width(after) < width(before)


def test_better_analyst_and_better_centre_are_faster():
    res = {}
    for key, best, level in (("good", True, 1), ("weak", False, 1), ("good_l3", True, 3)):
        api.new_game(7, 24)
        g = api._g()
        g.club.cash = 20_000_000
        res[key] = _dossier_after(g, best, 6, level)["knowledge"]
    assert res["good"] > res["weak"] and res["good_l3"] > res["good"]


def test_contract_runs_out_and_release_costs_half_the_rest(g):
    a = _analyst(g)
    api.staff_hire(a.id, 6)
    left = a.end_week - g.week
    b = next(m for m in g.staff.candidates() if m.role == "scout")
    api.staff_hire(b.id, 6)
    n0 = len(g.club.ledger)
    expect = round(b.salary * (b.end_week - g.week) / (52 / 12) * staff_mod.FIRE_SHARE)
    api.staff_release(b.id)
    fee = -sum(l.amount for l in g.club.ledger[n0:] if "выходное" in l.why)
    assert fee == expect > 0
    assert b.club is None
    for _ in range(left + 1):
        g.advance()
    assert a.club is None and a.workplace is None                          # left at the end of the contract


def test_staff_does_not_change_the_world():
    def run(hire):
        api.new_game(11, 24)
        g = api._g()
        g.club.cash = 20_000_000
        if hire:
            m = _analyst(g)
            api.staff_hire(m.id)
            api.staff_target(_target(g))
        for _ in range(12):
            g.advance()
        return [(c.name, round(c.rating_points, 3), round(c.season_points, 3)) for c in g.clubs]
    assert run(False) == run(True)                                         # own random generator, no effect on results


def test_save_roundtrip_and_old_save(g):
    a = _analyst(g)
    api.staff_hire(a.id)
    blob = api.save_b64()
    cash = g.club.cash
    for _ in range(2):
        api.load_b64(blob)
        g2 = api._g()
        g2.ensure_living()
        assert g2.staff.members[a.id].club == g2.club_name and g2.club.cash == pytest.approx(cash)
    g2.staff = None                                                       # a save made before staff existed
    blob = api.save_b64()
    api.load_b64(blob)
    g3 = api._g()
    g3.ensure_living()
    assert len(g3.staff.candidates()) >= 20 and not g3.staff.mine(g3)
