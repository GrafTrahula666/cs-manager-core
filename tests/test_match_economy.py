"""Gate 1 of the CS2 Combat Atlas: versioned rules and the in-map money ledger.

The atlas fixtures are synthetic states (synthetic=true in every case), used here only as
starting points for invariant checks, never as evidence about real CS2."""
import json
import random
from pathlib import Path

import pytest

from csmcore.match import CT, MAJOR_2026, PREMIER_2026, MapEconomy, T, preset

FIXTURES = [json.loads(line) for line in
            (Path(__file__).parent / "data" / "atlas_fixtures_economy.jsonl").read_text(encoding="utf-8").splitlines()]
SIDES = {**{f"t{i}": T for i in range(5)}, **{f"ct{i}": CT for i in range(5)}}


def eco(rules=PREMIER_2026):
    return MapEconomy(rules, dict(SIDES))


def test_rules_carry_their_source_and_tournaments_differ_only_where_the_rulebook_says():
    assert PREMIER_2026.status["t_planted_lost"] == "verified" and PREMIER_2026.t_planted_lost == 600
    assert PREMIER_2026.status["ot_start_money"] == "engine_default"
    assert [PREMIER_2026.loss_bonus(n) for n in range(1, 7)] == [1400, 1900, 2400, 2900, 3400, 3400]
    diff = {k for k in PREMIER_2026.__dataclass_fields__
            if getattr(PREMIER_2026, k) != getattr(MAJOR_2026, k)} - {"name", "status", "veto"}
    assert diff == {"shorthanded_bonus", "ot_limit"} and MAJOR_2026.ot_limit == 0
    assert MAJOR_2026.veto["bo1"].count("A:ban") + MAJOR_2026.veto["bo1"].count("B:ban") == 6
    custom = preset("major-2026", ot_start_money=10_000)
    assert custom.ot_start_money == 10_000 and custom.status["ot_start_money"] == "model"
    assert PREMIER_2026.rounds_per_half() == 12 and PREMIER_2026.rounds_per_half(overtime=True) == 3


def test_pistol_round_money_and_the_loss_ladder():
    e = eco()
    assert all(c == 800 for c in e.cash.values())
    e.kill("t0", "ct0", "pistol")
    e.plant("t1")
    e.end_round(T, "bomb", planted=True)
    assert e.cash["t0"] == 800 + 300 + 3500 and e.cash["t1"] == 800 + 300 + 3500
    assert e.cash["ct0"] == 800 + 1900                     # the pistol loser gets the second step
    for _ in range(4):
        e.end_round(T, "elimination")
    assert e.cash["ct1"] == 16000 or e.ledger[-1].amount == 3400
    assert e.losses[CT] == 5 and e.losses[T] == 0
    e.end_round(CT, "elimination")
    assert e.losses[CT] == 4                               # a win steps the counter down, not to zero
    e.end_round(T, "elimination")
    assert e.ledger[-1].amount == 3400 and e.losses[CT] == 5
    e.check()


def test_money_is_capped_and_a_purchase_never_goes_on_credit():
    e = eco()
    assert not e.buy("t0", 900, "kevlar+helmet")         # 800 is not enough
    assert e.buy("t0", 800, "p250") and e.cash["t0"] == 0
    for _ in range(8):
        e.end_round(CT, "time", alive={"t0"})
    assert all(c <= 16000 for c in e.cash.values()) and e.cash["ct0"] == 16000
    assert any(x.applied < x.amount for x in e.ledger if x.player == "ct0")   # the cap is recorded
    assert e.cash["t0"] == 0                              # alive when time ran out: no loss bonus
    assert e.cash["t1"] > 0
    e.check()


def test_a_kill_pays_the_killer_only_and_a_teamkill_costs():
    e = eco()
    before = dict(e.cash)
    e.kill("ct0", "t0", "awp")
    e.kill("ct1", "t1", "knife")
    e.kill("t2", "t3", "rifle")
    assert e.cash["ct0"] == before["ct0"] + 100 and e.cash["ct1"] == before["ct1"] + 1500
    assert e.cash["t0"] == before["t0"] and e.cash["t1"] == before["t1"]
    assert e.cash["t2"] == before["t2"] - 300
    e.check()


def test_round_end_has_one_lawful_reason():
    e = eco()
    with pytest.raises(ValueError):
        e.end_round(T, "defuse", planted=True)
    with pytest.raises(ValueError):
        e.end_round(CT, "elimination", planted=True)      # after a plant CT must defuse
    with pytest.raises(ValueError):
        e.end_round(CT, "time", planted=True)
    with pytest.raises(ValueError):
        e.end_round(T, "bomb")                            # no plant, no explosion
    with pytest.raises(ValueError):
        e.plant("ct0")
    e.end_round(CT, "defuse", planted=True)
    assert all(e.cash[p] == 800 + 1900 + 600 for p in e.team(T))   # planted but lost
    assert e.round == 1


def test_halftime_swaps_sides_and_overtime_gives_overtime_money():
    e = eco()
    e.end_round(T, "elimination")
    e.start_half(swap=True)
    assert e.sides["t0"] == CT and all(c == 800 for c in e.cash.values())
    e.start_half(overtime=True, swap=True)
    assert e.sides["t0"] == T and all(c == 12500 for c in e.cash.values())
    e.check()


@pytest.mark.parametrize("v", [1, 2])
def test_ledger_identity_holds_from_every_atlas_state(v):
    """cash_after = cash_before - purchases + rewards (capped), from each of the 990 states."""
    rng = random.Random(v)
    cases = [f for f in FIXTURES if f["id"].startswith(f"V{v}-")]
    assert len(cases) == 495
    for f in cases:
        share = {T: f["cash_t"] // 5, CT: f["cash_ct"] // 5}
        losses = {T: min(f["loss_streak_t"], 5), CT: min(f["loss_streak_ct"], 5)}
        e = MapEconomy.from_state(PREMIER_2026, SIDES, {p: share[s] for p, s in SIDES.items()}, losses)
        for _ in range(3):
            for p in sorted(SIDES):
                e.buy(p, rng.choice((0, 200, 650, 1000, 2700, 4700)))
            k, d = rng.choice(e.team(T)), rng.choice(e.team(CT))
            e.kill(*((k, d) if rng.random() < .5 else (d, k)), rng.choice(("rifle", "smg", "awp")))
            planted = rng.random() < .4
            if planted:
                e.plant(rng.choice(e.team(T)))
                win, why = rng.choice(((T, "bomb"), (T, "elimination"), (CT, "defuse")))
            else:
                win, why = rng.choice(((T, "elimination"), (CT, "elimination"), (CT, "time")))
            e.end_round(win, why, planted=planted, alive=set(rng.sample(sorted(SIDES), 3)))
        e.check()


def test_same_inputs_same_ledger():
    def run():
        e, rng = eco(MAJOR_2026), random.Random(7)
        for _ in range(10):
            e.buy("t0", rng.randrange(0, 900))
            e.end_round(rng.choice((T, CT)), "elimination")
        return [(x.player, x.kind, x.applied) for x in e.ledger]
    assert run() == run()


def test_the_current_engine_is_untouched():
    from csmcore import engine
    from csmcore.player import STATS, Player
    a = [Player(f"a{i}", {s: 60 for s in STATS}) for i in range(5)]
    b = [Player(f"b{i}", {s: 60 for s in STATS}) for i in range(5)]
    assert engine.play_map(a, b, 11).score == engine.play_map(a, b, 11).score
    assert not hasattr(engine, "MapEconomy")
