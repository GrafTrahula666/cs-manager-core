"""Weekly world tick: training, state drift, emergent events with causal chains, money.

Concept section 2: "bad sleep -> worse practice -> form drops -> mistake in a big match -> coach
criticism -> irritation -> conflict -> transfer request -> team weaker -> sponsor cuts bonus".
None of that chain is scripted here; each link is a rule on state, and the tick records the
causes when a threshold is crossed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import decisions, economy
from .economy import Club
from .player import Player
from .relations import RelationGraph


@dataclass
class WeekPlan:
    """What the manager decided for this week (the player's levers)."""
    practice_hours: float = 30.0   # 0-50
    travel: bool = False
    bootcamp: bool = False
    rest_days: int = 1
    commercial_days: int = 0       # sponsor activities


@dataclass
class Event:
    week: int
    kind: str
    who: list[str]
    text: str
    causes: list[str] = field(default_factory=list)


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def update_state(p: Player, plan: WeekPlan, rng: random.Random, club: Club) -> list[str]:
    """One week of dynamic state. Returns notes on notable changes (used as causes)."""
    st, notes = p.state, []
    disc = p.stat("discipline")

    sleep_loss = (8 if plan.travel else 0) + rng.gauss(0, 4) + (55 - disc) / 6
    sleep_loss *= p.mod("sleep_loss")[1]
    st["sleep"] = _clamp(st["sleep"] - sleep_loss + 6)
    if st["sleep"] < 45:
        notes.append(f"плохой сон ({st['sleep']:.0f})")

    load = plan.practice_hours / 30 * 8 + (6 if plan.travel else 0) + 3 * plan.commercial_days
    rec = (6 + 4 * plan.rest_days + (3 if club.facilities.get("bootcamp") and plan.bootcamp else 0)) * p.mod("recovery")[1]
    st["fatigue"] = _clamp(st["fatigue"] + load - rec - (st["sleep"] - 60) / 10)
    if plan.travel:
        add_stress = 4 * p.mod("travel_stress")[1] * (0.5 + p.p("home_attachment") / 100)
        st["stress"] = _clamp(st["stress"] + add_stress)
    # CK3-style: acting against your own personality is stressful.
    against = []
    if plan.commercial_days and p.p("media") < 35:
        against.append(("коммерция при закрытом характере", 3 * plan.commercial_days))
    if "benched" in p.flags and p.p("ego") > 60:
        against.append(("сидит в запасе при высоком эго", 5))
    if p.role == "support" and p.p("ego") > 70:
        against.append(("роль support при высоком эго", 3))
    if plan.practice_hours > 40 and p.stat("discipline") < 45:
        against.append(("жёсткий режим при низкой дисциплине", 3))
    for why, amount in against:
        st["stress"] = _clamp(st["stress"] + amount)
        notes.append(f"стресс: {why}")
    relief = (3 + plan.rest_days) * p.mod("stress_relief")[1]
    st["stress"] = _clamp(st["stress"] - relief)

    if st["fatigue"] > 65:
        st["burnout"] = _clamp(st["burnout"] + (st["fatigue"] - 65) / 5 * p.mod("burnout_gain")[1])
        notes.append(f"перегруз ({st['fatigue']:.0f})")
    else:
        st["burnout"] = _clamp(st["burnout"] - 1)

    quality = (plan.practice_hours / 30) * (st["sleep"] / 70) * (1 - st["fatigue"] / 150) * (1 - st["burnout"] / 120)
    if quality < 0.6:
        notes.append(f"слабая тренировка (качество {quality:.2f})")
    target_form = 40 + 25 * quality + (st["morale"] - 60) / 4
    st["form"] = _clamp(st["form"] + (target_form - st["form"]) * 0.3 + rng.gauss(0, 2))

    commercial_cost = 2 * plan.commercial_days * p.mod("commercial_morale_cost")[1]
    st["morale"] = _clamp(st["morale"] - commercial_cost + (st["confidence"] - 55) / 20)
    st["motivation"] = _clamp(st["motivation"] + (2 if club.rank <= 20 else -0.5) * (p.p("ambition") / 50) - st["burnout"] / 40)

    if rng.random() < 0.002 * (1 + st["fatigue"] / 50) * p.mod("injury_risk")[1]:
        st["health"] = _clamp(st["health"] - 30)
        notes.append("травма")
    return notes


def after_match(p: Player, won: bool, mistake: bool, ctx: dict) -> None:
    """Match consequences on confidence/morale; traits change how much it hurts."""
    st = p.state
    if won:
        st["confidence"] = _clamp(st["confidence"] + 4)
        st["morale"] = _clamp(st["morale"] + 3 * p.mod("morale_recovery", ctx)[1])
    else:
        loss = 5 * (1.5 - p.stat("confidence_stability") / 100) * p.mod("confidence_loss", ctx)[1]
        st["confidence"] = _clamp(st["confidence"] - loss)
        st["morale"] = _clamp(st["morale"] - 3 * (1.3 - p.stat("tilt_control") / 100))
    if mistake:
        st["confidence"] = _clamp(st["confidence"] - 6)


def stress_level(p: Player) -> int:
    """CK3-style stress levels: 0 calm, 1 strained (>35), 2 breaking (>65), 3 crisis (>85)."""
    s = p.s("stress")
    return 3 if s > 85 else 2 if s > 65 else 1 if s > 35 else 0


def world_week(clubs: list[Club], graph: RelationGraph, week: int, rng: random.Random,
               plans: dict[str, WeekPlan] | None = None) -> list[Event]:
    """Advance the world by one week. Deterministic for a given rng seed and world state."""
    events: list[Event] = []
    plans = plans or {}
    for club in clubs:
        plan = plans.get(club.name, WeekPlan())
        causes: dict[str, list[str]] = {}
        for p in club.roster:
            causes[p.name] = update_state(p, plan, rng, club)

        # Coach criticism of out-of-form players feeds irritation edges (criticism axis).
        for p in club.roster:
            if p.s("form") < 40:
                irritation = 6 * p.p("criticism") / 50
                p.state["coach_trust"] = _clamp(p.s("coach_trust") - irritation / 2)
                for q in club.roster:
                    if q is not p and q.s("form") > 55 and q.p("ego") > 60:
                        graph.nudge(p.name, q.name, "irritation", irritation / 2)
                causes[p.name].append(f"критика за форму ({p.s('form'):.0f})")

        # Irritation fades over calm weeks, faster with a stabilizer in the roster.
        calm = 1.0 / min([p.mod("team_tilt_spread")[1] for p in club.roster] or [1.0])
        for a in club.roster:
            for b in club.roster:
                if a is b:
                    continue
                rel = graph.get(a.name, b.name)
                # Competing for the same role keeps irritation alive, more so with a big ego.
                grind = rel.role_rivalry / 25 * (0.5 + a.p("ego") / 100)
                graph.nudge(a.name, b.name, "irritation", grind - 0.6 * calm)

        # Irritation may turn into open conflict.
        for a in club.roster:
            for b in club.roster:
                if a is b:
                    continue
                irr = graph.get(a.name, b.name).irritation
                if irr < 25:
                    continue
                v = decisions.conflict_chance(a, b, irr)
                if v.decide(rng.random()):
                    # The blow-up vents irritation but leaves resentment behind.
                    graph.nudge(a.name, b.name, "irritation", -20)
                    graph.nudge(a.name, b.name, "resentment", 15)
                    graph.nudge(b.name, a.name, "irritation", 10)
                    a.state["morale"] = _clamp(a.s("morale") - 8)
                    graph.spread_tilt(club.roster, a, 8)
                    events.append(Event(week, "conflict", [a.name, b.name],
                                        f"{a.name} открыто конфликтует с {b.name}", causes[a.name] + v.reasons))

        # Role satisfaction: big egos (and Role Thieves) sour when they are not the team's focus.
        by_form = sorted(club.roster, key=lambda q: -q.s("form"))
        for p in club.roster:
            focus = p in by_form[:2] or p.role == "igl"
            hunger = (p.p("ego") - 50) / 25 + p.mod("role_hunger")[0]
            delta = 1.0 if focus else -max(0.0, hunger)
            p.state["role_satisfaction"] = _clamp(p.s("role_satisfaction") + delta)
            if delta < 0 and p.s("role_satisfaction") < 50:
                causes[p.name].append(f"не в центре системы (эго {p.p('ego'):.0f})")

        # Ambition/role unhappiness may become a transfer request.
        for p in club.roster:
            if "transfer_requested" in p.flags:
                continue
            v = decisions.transfer_request(p, club)
            if v.reasons and v.decide(rng.random()):
                p.flags.add("transfer_requested")
                events.append(Event(week, "transfer_request", [p.name],
                                    f"{p.name} просит выставить его на трансфер", causes[p.name] + v.reasons))

        economy.weekly_finances(club, week)
        if club.weeks_negative == 4:
            events.append(Event(week, "finance_warning", [club.name], f"{club.name}: касса в минусе 4 недели",
                                [f"{k}: {v:,.0f}" for k, v in sorted(club.balance(week - 4).items(), key=lambda x: x[1])[:3]]))
        if club.weeks_negative == 13:
            events.append(Event(week, "bankruptcy", [club.name], f"{club.name} банкрот", ["касса < 0 13 недель подряд"]))
    return events
