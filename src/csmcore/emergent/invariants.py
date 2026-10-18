"""Checks that must hold in any world after any number of weeks. Used by tests and the soak
script; each returns a list of human-readable violations (empty = fine)."""
from __future__ import annotations

import math

from . import actions as A
from .minds import MAX_MEMORIES
from .sim import MAX_CHAIN_DEPTH, NEG_PER_WINDOW, NEG_WINDOW

STATE_KEYS = ("form", "morale", "fatigue", "sleep", "stress", "health", "burnout", "motivation",
              "role_satisfaction", "coach_trust", "confidence")
NEG_ACTIONS = {a.name for a in A.ALL if a.tone == A.NEG}


def social(clubs, graph) -> list[str]:
    bad = []
    seen: dict[str, str] = {}
    for c in clubs:
        for p in c.roster:
            if p.name in seen:
                bad.append(f"{p.name} в двух составах: {seen[p.name]} и {c.name}")
            seen[p.name] = c.name
            for k in STATE_KEYS:
                v = p.s(k)
                if not 0.0 <= v <= 100.0 or math.isnan(v):
                    bad.append(f"{p.name}.{k}={v}")
            if p.fame < 0 or math.isnan(p.fame):
                bad.append(f"{p.name}.fame={p.fame}")
        if math.isnan(c.cash) or math.isinf(c.cash):
            bad.append(f"{c.name}: касса {c.cash}")
    for (a, b), r in list(graph.edges.items())[:20000]:
        for d, v in r.__dict__.items():
            if not 0.0 <= v <= 100.0:
                bad.append(f"ребро {a}->{b}.{d}={v}")
                break
    return bad


def engine(ew) -> list[str]:
    bad = []
    by_club: dict[str, list[int]] = {}
    for fid, f in ew.facts.facts.items():
        if any(c >= fid for c in f.causes):
            bad.append(f"факт {fid}: причина позже следствия")
        live = [ew.facts.facts[c] for c in f.causes if c in ew.facts.facts]
        if live and f.depth < 1 + max(x.depth for x in live):
            bad.append(f"факт {fid}: глубина {f.depth} меньше глубины причин")
        if f.data.get("action") and f.depth > MAX_CHAIN_DEPTH:
            bad.append(f"факт {fid}: действие на глубине {f.depth} > {MAX_CHAIN_DEPTH}")
        if not set(f.misbelief) <= set(f.knowers):
            bad.append(f"факт {fid}: ложное убеждение у того, кто факта не знает")
        if f.data.get("action") in NEG_ACTIONS and f.club and f.kind != "changed_mind":
            by_club.setdefault(f.club, []).append(f.week)
    for club, weeks in by_club.items():
        weeks.sort()
        for i, w in enumerate(weeks):
            n = sum(1 for x in weeks[i:] if x < w + NEG_WINDOW)
            if n > NEG_PER_WINDOW:
                bad.append(f"{club}: {n} вредных поступков за {NEG_WINDOW} недель с недели {w}")
                break
    for name, m in ew.minds.minds.items():
        if len(m.memories) > MAX_MEMORIES:
            bad.append(f"{name}: {len(m.memories)} воспоминаний")
        for k, v in m.emotions.items():
            if not 0.0 <= v <= 100.0:
                bad.append(f"{name}: эмоция {k}={v}")
    open_by_club: dict[str, int] = {}
    for s in ew.situations:
        if s.choice is None:
            open_by_club[s.club] = open_by_club.get(s.club, 0) + 1
    for c, n in open_by_club.items():
        if n > 2:
            bad.append(f"{c}: {n} открытых ситуаций")
    return bad
