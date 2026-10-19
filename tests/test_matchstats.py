"""Sim-vs-demo statistics: both sides measured by the same code; demos read through a fake parser."""
from csmcore.demo_records import BUY_SAMPLE, demo_to_record
from csmcore.engine import play_map
from csmcore.matchstats import compare, from_sim, metrics
from csmcore.worldgen import generate

A = [f"a{i}" for i in range(5)]
B = [f"b{i}" for i in range(5)]


class FakeParser:
    """demoparser2's interface with hand-written tables. Round 1: team A on CT wins by elimination.
    Round 2 (after a side switch): team A on T plants and the bomb explodes."""

    def __init__(self):
        r1, r2 = 1000, 5000
        self.events = {
            "round_end": [{"tick": 500, "winner": "CT", "reason": "warmup"},       # warmup: no freeze end before it
                          {"tick": 3000, "winner": "CT", "reason": "t_killed"},
                          {"tick": 8000, "winner": "T", "reason": "bomb_exploded"}],
            "round_freeze_end": [{"tick": r1}, {"tick": r2}],
            "player_death": (
                [{"tick": 1500 + i, "attacker_name": "a0", "user_name": b, "weapon": "ak47", "headshot": i % 2 == 0}
                 for i, b in enumerate(B)]
                + [{"tick": 3100, "attacker_name": "b0", "user_name": "a1", "weapon": "glock", "headshot": False}]  # after the round
                + [{"tick": 6000, "attacker_name": "b1", "user_name": "a2", "weapon": "m4a1_silencer", "headshot": True},
                   {"tick": 6100, "attacker_name": "a3", "user_name": "a4", "weapon": "hegrenade", "headshot": False},  # team kill
                   {"tick": 6200, "attacker_name": None, "user_name": "b2", "weapon": "world", "headshot": False}]),
            "bomb_planted": [{"tick": 7000}],
            "bomb_exploded": [{"tick": 7900}],
            "smokegrenade_detonate": [{"tick": 1200, "user_name": "a0"}, {"tick": 5200, "user_name": "b4"}],
            "flashbang_detonate": [{"tick": 5300, "user_name": "a1"}],
            "player_hurt": [{"tick": 5400, "attacker_name": "a1", "user_name": "b3", "weapon": "hegrenade", "dmg_health": 40},
                            {"tick": 5450, "attacker_name": "a1", "user_name": "a2", "weapon": "hegrenade", "dmg_health": 10}],
        }
        self.ticks = []
        for tick, side_a, side_b, eq in ((r1 + BUY_SAMPLE, 3, 2, 800), (r2 + BUY_SAMPLE, 2, 3, 4500)):
            self.ticks += [{"tick": tick, "name": n, "team_num": side_a, "current_equip_value": eq} for n in A]
            self.ticks += [{"tick": tick, "name": n, "team_num": side_b, "current_equip_value": 700} for n in B]

    def parse_header(self):
        return {"map_name": "de_mirage"}

    def parse_event(self, name, player=None, other=None):
        if name not in self.events:
            raise KeyError(name)
        return list(self.events[name])

    def parse_ticks(self, props, ticks=None, players=None):
        return [t for t in self.ticks if ticks is None or t["tick"] in ticks]


def test_a_demo_becomes_a_round_record_with_teams_kept_across_sides():
    rec = demo_to_record(FakeParser(), "fake")
    assert rec["map"] == "de_mirage" and rec["teams"] == [A, B]
    r1, r2 = rec["rounds"]
    assert len(rec["rounds"]) == 2 and rec["score"] == [2, 0]   # team A won as CT, then as T
    assert r1["winner"] == 0 and r1["ct"] == 0 and r2["ct"] == 1 and r2["winner"] == 0
    assert len(r1["kills"]) == 5                                 # the kill after round end is not counted
    assert r1["kinds"] == ["pistol", "pistol"] and r2["kinds"] == ["full", "eco"]   # 5 x 4500 vs 5 x 700
    assert r2["bomb"] == "exploded" and r1["bomb"] is None
    assert r1["nades"] == [1, 0] and r2["nades"] == [1, 1]
    assert r2["util_dmg"] == [40.0, 0.0]                          # damage to a teammate is not utility damage
    tk = [k for k in r2["kills"] if k["v"] == "a4"][0]
    assert tk["kt"] == tk["vt"] == 0
    world = [k for k in r2["kills"] if k["v"] == "b2"][0]
    assert world["k"] is None


def test_demo_metrics_count_only_real_kills():
    m = metrics([demo_to_record(FakeParser(), "fake")], min_rounds=1)
    assert m["kills_per_round"]["value"] == 3.0                   # 5 + 1 (no team kill, no world death)
    assert m["headshot_share"] == {"value": 0.6667, "n": 6}
    assert m["bomb_plant_rate"] == {"value": 0.5, "n": 2}
    assert m["first_kill_round_win"] == {"value": 0.5, "n": 2}   # round 2: b1 opened, team A still won
    assert m["kill_share_ak47"]["value"] == round(5 / 6, 4)


def test_simulated_maps_are_measured_the_same_way():
    clubs, *_ = generate(2, 16)
    a, b = clubs[0].lineup(), clubs[1].lineup()
    maps = []
    for seed in range(30):
        r = play_map(a, b, seed=seed)
        rec = from_sim(r, a, b)
        assert rec["score"] == list(r.score) and len(rec["rounds"]) == len(r.rounds)
        for rr, rd in zip(r.rounds, rec["rounds"]):
            assert len(rd["kills"]) == 10 - sum(rr.survivors)       # every log line became a kill
        maps.append(rec)
    m = metrics(maps)
    assert m["loser_survivors"]["value"] == 0.0                  # no bomb or clock: every round is a wipe
    assert 0.5 < m["first_kill_round_win"]["value"] < 0.85
    assert 0.8 < m["kd_p50"]["value"] < 1.25
    assert m["headshot_share"]["n"] == 0 and m["bomb_plant_rate"]["value"] is None


def test_the_comparison_never_claims_a_fit_on_a_small_sample():
    clubs, *_ = generate(2, 16)
    a, b = clubs[0].lineup(), clubs[1].lineup()
    sim = metrics([from_sim(play_map(a, b, seed=s), a, b) for s in range(20)])
    real = metrics([demo_to_record(FakeParser(), "fake")], min_rounds=1)
    rows = {r["metric"]: r for r in compare(sim, real)}
    assert rows["bomb_plant_rate"]["sim"] == "N/A" and rows["bomb_plant_rate"]["real"] == 0.5
    assert rows["headshot_share"]["sim"] == "N/A"
    assert rows["kills_per_round"]["diff"] == round(sim["kills_per_round"]["value"] - 3.0, 4)
    assert all("не калибровка" in r["note"] for r in rows.values())
