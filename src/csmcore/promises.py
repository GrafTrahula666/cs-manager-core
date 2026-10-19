"""Promises to players (Football Manager). A promise buys calm now and costs trust later if broken.

Kinds:
  role          keep him in the starting five / give him the star role
  raise         raise salary to at least `value` by the deadline
  signing       sign a player of at least `value` overall
  rest          give him `value` rest days before the deadline (tracked via player.state)
  title_push    reach world rank <= `value`
Breaking a promise hurts more for proud players, and a broken promise to a squad leader
spreads through the dressing room.
"""
from __future__ import annotations

from dataclasses import dataclass

from .economy import Club
from .player import Player
from .relations import RelationGraph
from .squad import hierarchy


@dataclass
class Promise:
    player: str
    kind: str
    deadline: int
    value: float = 0.0
    made_week: int = 0
    status: str = "open"  # open / kept / broken


def make(p: Player, kind: str, deadline: int, week: int, value: float = 0.0) -> Promise:
    """Immediate effect: the player calms down and stops asking to leave for now."""
    p.state["morale"] = min(100.0, p.s("morale") + 8)
    p.state["role_satisfaction"] = min(100.0, p.s("role_satisfaction") + (15 if kind == "role" else 5))
    p.flags.discard("transfer_requested")
    p.flags.add("has_promise")
    return Promise(p.name, kind, deadline, value, week)


def _kept(pr: Promise, p: Player, club: Club) -> bool:
    if pr.kind == "role":
        return p in club.lineup() and "benched" not in p.flags
    if pr.kind == "raise":
        c = club.contracts.get(p.name)
        return c is not None and c.salary_month >= pr.value
    if pr.kind == "signing":
        return any(q.overall() >= pr.value and q.joined_week >= pr.made_week for q in club.roster if q is not p)
    if pr.kind == "title_push":
        return club.rank <= pr.value
    if pr.kind == "rest":
        return p.s("fatigue") < 40
    raise ValueError(pr.kind)


def check(promises: list[Promise], club: Club, graph: RelationGraph, week: int) -> list[str]:
    """Settle promises whose deadline has come. Returns readable outcomes."""
    out = []
    people = {p.name: p for p in club.roster}
    leaders = {p.name for p in hierarchy(club, graph)["leaders"]}
    for pr in promises:
        if pr.status != "open" or week < pr.deadline or pr.player not in people:
            continue
        p = people[pr.player]
        p.flags.discard("has_promise")
        if _kept(pr, p, club):
            pr.status = "kept"
            p.state["coach_trust"] = min(100.0, p.s("coach_trust") + 12)
            p.personality["loyalty"] = min(100.0, p.p("loyalty") + 3)
            out.append(f"Обещание {p.name} ({pr.kind}) выполнено: доверие растёт")
            continue
        pr.status = "broken"
        pride = 0.5 + (p.p("ego") + p.p("criticism")) / 200
        p.state["coach_trust"] = max(0.0, p.s("coach_trust") - 30 * pride)
        p.state["morale"] = max(0.0, p.s("morale") - 15 * pride)
        p.state["stress"] = min(100.0, p.s("stress") + 10)
        p.flags.add("transfer_requested")
        p.history.append(f"week {week}: клуб нарушил обещание ({pr.kind})")
        line = f"Обещание {p.name} ({pr.kind}) нарушено: он просит трансфер"
        if p.name in leaders:
            for q in club.roster:
                if q is not p:
                    q.state["coach_trust"] = max(0.0, q.s("coach_trust") - 8)
                    graph.nudge(q.name, p.name, "leader_loyalty", 5)
            line += "; он лидер раздевалки, доверие к тренеру падает у всех"
        out.append(line)
    return out
