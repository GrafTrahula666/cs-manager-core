"""CS2 demo -> matchstats record, through any object with demoparser2's interface.

Only `parse_header`, `parse_event` and `parse_ticks` are used, and their results only need
`.to_dict("records")` (a pandas DataFrame) or to be a list of dicts. That keeps this module free
of numpy/pandas imports: the tests feed it a fake parser, scripts/demo_analysis.py feeds it
demoparser2.DemoParser.

Teams are tracked by roster, not by side: team 0 is whoever starts as CT, and stays team 0
after the half switch. Buy types are a heuristic on team equipment value shortly after the
freeze time ends (thresholds below), not an official classification.

NOT YET RUN ON A REAL DEMO: field names follow demoparser2 0.42 documentation and examples;
the first real run may need small renames (see docs/match-engine-plan.md).
"""
from __future__ import annotations

import math

TICKRATE = 64
BUY_SAMPLE = 5 * TICKRATE        # equipment is read 5 s after freeze end, when most buys are done
ECO_BELOW, FORCE_BELOW = 7_500, 20_000
SIDE = {2: "T", 3: "CT", "2": "T", "3": "CT", "T": "T", "CT": "CT", "TERRORIST": "T", "Terrorist": "T",
        "CounterTerrorist": "CT", "COUNTER_TERRORIST": "CT"}
NADE_EVENTS = ("hegrenade_detonate", "flashbang_detonate", "smokegrenade_detonate", "inferno_startburn",
               "decoy_started")
UTIL_WEAPONS = {"hegrenade", "inferno", "molotov", "incgrenade"}


def _rows(df) -> list[dict]:
    if df is None:
        return []
    rows = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    clean = []
    for r in rows:
        clean.append({k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()})
    return clean


def _event(parser, name, **kw) -> list[dict]:
    try:
        return _rows(parser.parse_event(name, **kw))
    except Exception:            # an event that never fired in this demo is not an error
        return []


def _side(v):
    return SIDE.get(v)


def buy_kind(n: int, equip: float) -> str:
    if n in (1, 13):
        return "pistol"
    return "eco" if equip < ECO_BELOW else "force" if equip < FORCE_BELOW else "full"


def demo_to_record(parser, name: str = "demo") -> dict:
    header = parser.parse_header() or {}
    starts = sorted(r["tick"] for r in _event(parser, "round_freeze_end"))
    ends = sorted(_event(parser, "round_end"), key=lambda r: r["tick"])
    # pair each freeze end with the first round end after it; warmup ends without a start are dropped
    spans = []
    for s in starts:
        e = next((r for r in ends if r["tick"] > s), None)
        if e is not None and (not spans or e["tick"] > spans[-1][1]["tick"]):
            spans.append((s, e))
    if not spans:
        raise ValueError(f"{name}: no rounds found")

    sample = [s + BUY_SAMPLE for s, _ in spans]
    ticks = _rows(parser.parse_ticks(["team_num", "current_equip_value"], ticks=sample))
    first = [t for t in ticks if t["tick"] == sample[0]]
    ct_start = sorted({t["name"] for t in first if _side(t["team_num"]) == "CT"})
    t_start = sorted({t["name"] for t in first if _side(t["team_num"]) == "T"})
    team_of = {n: 0 for n in ct_start} | {n: 1 for n in t_start}

    deaths = _event(parser, "player_death", player=["team_num"], other=["total_rounds_played"])
    bombs = {k: [r["tick"] for r in _event(parser, k)] for k in ("bomb_planted", "bomb_defused", "bomb_exploded")}
    nades = [(r["tick"], r.get("user_name")) for ev in NADE_EVENTS for r in _event(parser, ev)]
    hurts = [r for r in _event(parser, "player_hurt") if r.get("weapon") in UTIL_WEAPONS]

    rounds = []
    score = [0, 0]
    for n, (s, e) in enumerate(spans, 1):
        inside = lambda t: s <= t <= e["tick"]   # noqa: E731
        at = [t for t in ticks if t["tick"] == s + BUY_SAMPLE]
        ct_team = next((team_of[t["name"]] for t in at if t["name"] in team_of and _side(t["team_num"]) == "CT"), 0)
        equip = [0.0, 0.0]
        for t in at:
            if t["name"] in team_of:
                equip[team_of[t["name"]]] += t.get("current_equip_value") or 0
        win_side = _side(e.get("winner"))
        if win_side is None:
            continue                               # a round end with no winner (restart, draw)
        winner = ct_team if win_side == "CT" else 1 - ct_team
        score[winner] += 1
        kills = []
        for d in sorted((d for d in deaths if inside(d["tick"])), key=lambda d: d["tick"]):
            k, v = d.get("attacker_name"), d.get("user_name")
            if v not in team_of:
                continue
            kills.append({"k": k if k in team_of else None, "v": v, "kt": team_of.get(k), "vt": team_of[v],
                          "weapon": d.get("weapon"), "hs": bool(d.get("headshot")) if d.get("headshot") is not None else None,
                          "tick": d["tick"]})
        bomb = None
        for kind in ("bomb_planted", "bomb_defused", "bomb_exploded"):
            if any(inside(t) for t in bombs[kind]):
                bomb = kind.removeprefix("bomb_")
        thrown = [0, 0]
        for t, who in nades:
            if inside(t) and who in team_of:
                thrown[team_of[who]] += 1
        dmg = [0.0, 0.0]
        for h in hurts:
            if inside(h["tick"]) and h.get("attacker_name") in team_of and h.get("user_name") in team_of \
                    and team_of[h["attacker_name"]] != team_of[h["user_name"]]:
                dmg[team_of[h["attacker_name"]]] += h.get("dmg_health") or 0
        rounds.append({"n": n, "winner": winner, "ct": ct_team, "kinds": [buy_kind(n, equip[0]), buy_kind(n, equip[1])],
                       "equip": equip, "reason": e.get("reason"), "bomb": bomb, "nades": thrown, "util_dmg": dmg,
                       "kills": kills})
    return {"source": "demo", "map": header.get("map_name", "?"), "name": name,
            "teams": [ct_start, t_start], "score": score, "rounds": rounds}
