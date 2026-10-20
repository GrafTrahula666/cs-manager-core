"""LIVING CLUB data: talents, XP rules, backgrounds, staff roles and facility levels, all in
`data/*.json` so that numbers are tuned in data, not scattered through code (docs/living-club.md).

`validate()` is the single place that states what a well-formed data set means; the tests call it.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    return json.loads(resources.files("csmcore.data").joinpath(f"{name}.json").read_text(encoding="utf-8"))


def talents() -> dict[str, dict]:
    return {n["id"]: n for n in load("talents")["nodes"]}


def channel_total(unlocked: set[str], channel: str) -> float:
    """Sum of unlocked talent effects on one channel, clamped by the channel's cap."""
    data = load("talents")
    nodes = talents()
    raw = sum(e["value"] for t in unlocked for e in nodes[t]["effects"] if e["channel"] == channel)
    return min(raw, data["channels"][channel]["cap"])


def validate() -> list[str]:
    """Return a list of problems; empty means the data is consistent."""
    errs: list[str] = []
    t = load("talents")
    nodes = {n["id"]: n for n in t["nodes"]}
    if len(nodes) != len(t["nodes"]):
        errs.append("talents: duplicate ids")
    for b in t["branches"]:
        mine = [n for n in t["nodes"] if n["branch"] == b]
        if len(mine) != 12:
            errs.append(f"talents: branch {b} has {len(mine)} nodes, need 12")
        if sum(1 for n in mine if n.get("capstone")) != 1:
            errs.append(f"talents: branch {b} needs exactly one capstone")
    for n in t["nodes"]:
        for r in n["requires"]:
            if r not in nodes:
                errs.append(f"talents: {n['id']} requires unknown {r}")
            elif nodes[r]["tier"] >= n["tier"]:
                errs.append(f"talents: {n['id']} requires {r} of the same or a higher tier")
            elif nodes[r]["branch"] != n["branch"]:
                errs.append(f"talents: {n['id']} requires {r} from another branch")
        if (n["tier"] == 1) != (not n["requires"]):
            errs.append(f"talents: {n['id']}: tier 1 and only tier 1 has no requirements")
        if n.get("capstone") and len(n["requires"]) < 2:
            errs.append(f"talents: capstone {n['id']} needs at least two requirements")
        for e in n["effects"]:
            if e["channel"] not in t["channels"]:
                errs.append(f"talents: {n['id']} uses unknown channel {e['channel']}")
    p = load("progression")
    if p["max_level"] < 2 or p["points_per_level"] != 1:
        errs.append("progression: one point per level, max level >= 2")
    bg = load("backgrounds")
    sums = {sum(b["stats"].values()) for b in bg["backgrounds"]}
    if len(sums) != 1:
        errs.append(f"backgrounds: start stat sums differ: {sorted(sums)}")
    roles = {r["id"] for r in load("staff_roles")["roles"]}
    f = load("facilities")
    workplaces = {r["workplace"] for r in load("staff_roles")["roles"]} - {"office"}
    rooms = {x["id"] for x in f["facilities"]}
    for w in workplaces - rooms:
        errs.append(f"staff_roles: workplace {w} is not a facility")
    for fac in f["facilities"]:
        prev = (0, 0, 0)
        for lv in fac["levels"]:
            cur = (lv["cost"], lv["build_weeks"], lv["upkeep_month"])
            if any(c <= q for c, q in zip(cur, prev)):
                errs.append(f"facilities: {fac['id']} level {lv['level']} is not more expensive than the previous one")
            prev = cur
        if [lv["level"] for lv in fac["levels"]] != [1, 2, 3, 4, 5]:
            errs.append(f"facilities: {fac['id']} must define levels 1-5")
    del roles
    return errs
