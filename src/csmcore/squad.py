"""Squad hierarchy and social groups (Football Manager's dynamics).

Influence comes from leadership, age, tenure, fame and results, not from the manager's say-so.
Leaders' moods spread; cliques form around friendship and shared culture. A group with an
unhappy leader is where trouble starts.
"""
from __future__ import annotations

from .economy import Club
from .player import Player
from .relations import RelationGraph


def influence(p: Player, club: Club, week: int = 0) -> float:
    tenure_years = max(0, week - p.joined_week) / 52
    return (0.45 * p.stat("leadership") + 0.15 * min(p.age, 30) / 30 * 100
            + 0.15 * min(tenure_years, 4) / 4 * 100 + 0.15 * min(p.fame, 100)
            + 0.10 * p.p("ego")) * p.mod("influence")[1]


def hierarchy(club: Club, graph: RelationGraph, week: int = 0) -> dict[str, list[Player]]:
    ranked = sorted(club.roster, key=lambda p: -influence(p, club, week))
    return {"leaders": ranked[:1], "influential": ranked[1:3], "others": ranked[3:]}


def cliques(club: Club, graph: RelationGraph, threshold: float = 15.0) -> list[list[str]]:
    """Connected groups where mutual relation score is above `threshold`."""
    names = [p.name for p in club.roster]
    seen, groups = set(), []
    for n in names:
        if n in seen:
            continue
        group, stack = [], [n]
        seen.add(n)
        while stack:
            a = stack.pop()
            group.append(a)
            for b in names:
                if b in seen:
                    continue
                s = (graph.get(a, b).score() + graph.get(b, a).score()) / 2
                if s > threshold:
                    seen.add(b)
                    stack.append(b)
        groups.append(sorted(group))
    return groups


def dressing_room_mood(club: Club, graph: RelationGraph, week: int = 0) -> float:
    """Morale weighted by influence: leaders count three times."""
    h = hierarchy(club, graph, week)
    w = {p.name: 3.0 for p in h["leaders"]} | {p.name: 2.0 for p in h["influential"]}
    total = sum(w.get(p.name, 1.0) for p in club.roster)
    return sum(p.s("morale") * w.get(p.name, 1.0) for p in club.roster) / max(1.0, total)


def leader_mood_spread(club: Club, graph: RelationGraph, week: int = 0) -> list[str]:
    """Weekly: an unhappy leader drags followers down, a happy one lifts them."""
    notes = []
    for leader in hierarchy(club, graph, week)["leaders"]:
        delta = (leader.s("morale") - 60) / 20
        if abs(delta) < 0.5:
            continue
        for q in club.roster:
            if q is leader:
                continue
            follow = graph.get(q.name, leader.name).leader_loyalty / 100
            q.state["morale"] = max(0.0, min(100.0, q.s("morale") + delta * follow))
        if delta < 0:
            notes.append(f"лидер {leader.name} недоволен (мораль {leader.s('morale'):.0f}), настроение падает у всей команды")
    return notes
