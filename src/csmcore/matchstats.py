"""Match statistics that can be computed the same way for simulated maps and real demos.

Both sides are first turned into the same plain record (JSON-friendly dicts), then the same
functions measure them. A metric the simulator does not model yet (bomb, grenades, weapons,
headshots, buy types other than pistol/eco) is reported as N/A for the simulation instead of a
made-up number. This module only compares; it does not fit anything, and a comparison on a
handful of demos is not a calibration.

Record shape:
    map    = {"source": "sim"|"demo", "map": str, "teams": [a, b], "score": [x, y], "rounds": [round]}
    round  = {"n": 1.., "winner": 0|1, "kinds": [kind_a, kind_b] | None, "equip": [a, b] | None,
              "reason": str | None, "bomb": "planted"|"defused"|"exploded"|None, "nades": [a, b] | None,
              "util_dmg": [a, b] | None, "kills": [kill]}
    kill   = {"k": killer | None, "v": victim, "kt": 0|1|None, "vt": 0|1, "weapon": str | None, "hs": bool | None}
"""
from __future__ import annotations

import re

TEAM = 5
KILL_RE = re.compile(r"^(?P<k>.+) kills (?P<v>.+) \(p=")

# Metrics the simulator produces today. Everything else is demo-only until the engine models it.
SIM_MODELLED = {
    "maps", "rounds_per_map", "overtime_share", "close_map_share", "kills_per_round", "kpr_mean",
    "kd_p10", "kd_p50", "kd_p90", "first_kill_round_win", "first_two_kills_round_win",
    "pistol_next_round_win", "winner_survivors", "loser_survivors", "clutch_1vx_rate",
    "clutch_1v2_win", "clutch_1v3plus_win", "eco_round_win",
}


def from_sim(result, team_a, team_b, map_name: str = "sim") -> dict:
    """Turn an engine.MapResult into a record. Kills come from the round log."""
    side = {p.name: 0 for p in team_a} | {p.name: 1 for p in team_b}
    rounds = []
    for n, r in enumerate(result.rounds, 1):
        kills = []
        for line in r.log:
            m = KILL_RE.match(line)
            if m:
                k, v = m["k"], m["v"]
                kills.append({"k": k, "v": v, "kt": side.get(k), "vt": side.get(v), "weapon": None, "hs": None})
        rounds.append({"n": n, "winner": r.winner, "kinds": list(r.kind), "equip": None, "reason": "elimination",
                       "bomb": None, "nades": None, "util_dmg": None, "kills": kills})
    return {"source": "sim", "map": map_name, "teams": ["A", "B"], "score": list(result.score), "rounds": rounds}


def _alive_trace(rnd):
    """Alive counts after each kill (or death), in order."""
    alive = [TEAM, TEAM]
    out = []
    for k in rnd["kills"]:
        if k.get("vt") in (0, 1):
            alive[k["vt"]] = max(0, alive[k["vt"]] - 1)
        out.append((k, tuple(alive)))
    return out


def _rate(hits: int, n: int) -> dict:
    return {"value": round(hits / n, 4) if n else None, "n": n}


def _mean(xs) -> dict:
    xs = list(xs)
    return {"value": round(sum(xs) / len(xs), 4) if xs else None, "n": len(xs)}


def _quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 4)


def metrics(maps: list[dict], min_rounds: int = 40) -> dict:
    """Every metric as {"value", "n"} where n is the sample it was measured on."""
    rounds = [r for m in maps for r in m["rounds"]]
    out: dict[str, dict] = {"maps": {"value": len(maps), "n": len(maps)}}
    out["rounds_per_map"] = _mean(len(m["rounds"]) for m in maps)
    out["overtime_share"] = _rate(sum(1 for m in maps if len(m["rounds"]) > 24), len(maps))
    out["close_map_share"] = _rate(sum(1 for m in maps if abs(m["score"][0] - m["score"][1]) <= 3), len(maps))
    real_kills = [[k for k in r["kills"] if k.get("k") and k.get("kt") in (0, 1) and k["kt"] != k.get("vt")]
                  for r in rounds]
    out["kills_per_round"] = _mean(len(ks) for ks in real_kills)

    # per player over the whole sample: KPR and K/D among regulars
    kills: dict[str, int] = {}
    deaths: dict[str, int] = {}
    played: dict[str, int] = {}
    for m in maps:
        names = set()
        for r in m["rounds"]:
            for k in r["kills"]:
                names.add(k["v"])
                if k.get("k"):
                    names.add(k["k"])
        for nm in names:
            played[nm] = played.get(nm, 0) + len(m["rounds"])
        for r in m["rounds"]:
            for k in r["kills"]:
                deaths[k["v"]] = deaths.get(k["v"], 0) + 1
                if k.get("k") and k.get("kt") != k.get("vt"):
                    kills[k["k"]] = kills.get(k["k"], 0) + 1
    regulars = [p for p, n in played.items() if n >= min_rounds]
    out["kpr_mean"] = _mean(kills.get(p, 0) / played[p] for p in regulars)
    kd = [kills.get(p, 0) / max(1, deaths.get(p, 0)) for p in regulars]
    for q, key in ((0.1, "kd_p10"), (0.5, "kd_p50"), (0.9, "kd_p90")):
        out[key] = {"value": _quantile(kd, q), "n": len(kd)}

    first = first2 = n_first = n_first2 = 0
    win_surv, lose_surv = [], []
    clutch_rounds = c2 = c2w = c3 = c3w = 0
    for r in rounds:
        trace = _alive_trace(r)
        ks = [k for k, _ in trace if k.get("kt") in (0, 1) and k.get("kt") != k.get("vt")]
        if ks:
            n_first += 1
            first += ks[0]["kt"] == r["winner"]
        if len(ks) >= 2 and ks[0]["kt"] == ks[1]["kt"]:
            n_first2 += 1
            first2 += ks[0]["kt"] == r["winner"]
        alive = trace[-1][1] if trace else (TEAM, TEAM)
        win_surv.append(alive[r["winner"]])
        lose_surv.append(alive[1 - r["winner"]])
        # the first team left with one player faces X opponents: a 1vX. (A 1v1 is never first:
        # the other side got to one player earlier, so 1v1 win rates are 50% by construction.)
        seen = None
        for _, a in trace:
            for t in (0, 1):
                if seen is None and a[t] == 1 and a[1 - t] >= 1:
                    seen = (t, a[1 - t])
        if seen:
            clutch_rounds += 1
            t, x = seen
            if x == 2:
                c2 += 1
                c2w += r["winner"] == t
            elif x >= 3:
                c3 += 1
                c3w += r["winner"] == t
    out["first_kill_round_win"] = _rate(first, n_first)
    out["first_two_kills_round_win"] = _rate(first2, n_first2)
    out["winner_survivors"] = _mean(win_surv)
    out["loser_survivors"] = _mean(lose_surv)
    out["clutch_1vx_rate"] = _rate(clutch_rounds, len(rounds))
    out["clutch_1v2_win"] = _rate(c2w, c2)
    out["clutch_1v3plus_win"] = _rate(c3w, c3)

    # pistol rounds 1 and 13: does the winner take the next round too
    nxt = n_pistol = 0
    for m in maps:
        rs = m["rounds"]
        for i in (0, 12):
            if i + 1 < len(rs):
                n_pistol += 1
                nxt += rs[i + 1]["winner"] == rs[i]["winner"]
    out["pistol_next_round_win"] = _rate(nxt, n_pistol)

    eco_w = eco_n = 0
    for r in rounds:
        kinds = r.get("kinds")
        if kinds and kinds.count("eco") == 1 and "pistol" not in kinds:
            eco_n += 1
            eco_w += kinds[r["winner"]] == "eco"
    out["eco_round_win"] = _rate(eco_w, eco_n)

    # only demos have these today
    hs = [k["hs"] for ks in real_kills for k in ks if k.get("hs") is not None]
    out["headshot_share"] = _rate(sum(hs), len(hs))
    with_bomb = any(m["source"] == "demo" for m in maps)    # the engine has no bomb yet
    planted = [r for r in rounds if r.get("bomb") in ("planted", "defused", "exploded")]
    out["bomb_plant_rate"] = _rate(len(planted), len(rounds)) if with_bomb else {"value": None, "n": 0}
    out["defuse_after_plant"] = _rate(sum(1 for r in planted if r["bomb"] == "defused"), len(planted))
    nades = [sum(r["nades"]) for r in rounds if r.get("nades")]
    out["nades_per_round"] = _mean(nades)
    ud = [sum(r["util_dmg"]) for r in rounds if r.get("util_dmg")]
    out["utility_damage_per_round"] = _mean(ud)
    weapons: dict[str, int] = {}
    for ks in real_kills:
        for k in ks:
            if k.get("weapon"):
                weapons[k["weapon"]] = weapons.get(k["weapon"], 0) + 1
    total = sum(weapons.values())
    for w in ("ak47", "m4a1_silencer", "m4a1", "awp", "deagle", "usp_silencer", "glock"):
        out[f"kill_share_{w}"] = _rate(weapons.get(w, 0), total)
    return out


def compare(sim: dict, real: dict, min_real_rounds: int = 2000) -> list[dict]:
    """Side by side. A metric the engine does not model shows N/A on the sim side; with a small
    real sample every row carries a warning, because the numbers cannot support a fit."""
    rows = []
    for key in sorted(set(sim) | set(real)):
        s, r = sim.get(key, {}), real.get(key, {})
        sv = s.get("value") if key in SIM_MODELLED else None
        rv = r.get("value")
        row = {"metric": key, "sim": sv if key in SIM_MODELLED else "N/A", "real": rv, "n_sim": s.get("n", 0),
               "n_real": r.get("n", 0), "diff": None, "note": ""}
        if isinstance(sv, (int, float)) and isinstance(rv, (int, float)):
            row["diff"] = round(sv - rv, 4)
        if key not in SIM_MODELLED:
            row["note"] = "движок этого пока не моделирует"
        rows.append(row)
    n_rounds = real.get("kills_per_round", {}).get("n", 0)
    if n_rounds < min_real_rounds:
        for row in rows:
            row["note"] = (row["note"] + "; " if row["note"] else "") + f"реальных раундов {n_rounds} < {min_real_rounds}: не калибровка"
    return rows


def table(rows: list[dict]) -> str:
    def f(v):
        return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    lines = [f"{'метрика':<28}{'симуляция':>11}{'реальность':>12}{'разница':>10}  n(sim/real)  примечание"]
    for r in rows:
        lines.append(f"{r['metric']:<28}{f(r['sim']):>11}{f(r['real']):>12}{f(r['diff']):>10}  "
                     f"{r['n_sim']}/{r['n_real']}  {r['note']}")
    return "\n".join(lines)
