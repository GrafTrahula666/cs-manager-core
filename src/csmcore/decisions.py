"""Non-match decisions driven by personality (concept: "every hidden parameter must take part in
decision formulas"). Each function returns a probability or verdict plus the reasons behind it."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .economy import Club, Contract
from .player import Player

TIER_PRESTIGE = {"tier3": 10, "tier2": 35, "tier1": 70, "super": 90}


@dataclass
class Verdict:
    p: float
    reasons: list[str] = field(default_factory=list)

    def decide(self, roll: float) -> bool:
        return roll < self.p


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def contract_acceptance(player: Player, offer: Contract, expected_salary: float, buyer: Club,
                        current: Club | None = None, relocation: bool = False) -> Verdict:
    """Will the player sign? Money vs wins, ambition vs club prestige, loyalty, home attachment."""
    reasons: list[str] = []
    money_ratio = offer.salary_month / max(1.0, expected_salary)
    money = (money_ratio - 1) * 4 * (0.5 + player.p("money_focus") / 100)
    reasons.append(f"деньги: {money_ratio:.0%} от ожиданий (вес {player.p('money_focus'):.0f})")

    prestige_gap = TIER_PRESTIGE[buyer.tier] - player.p("ambition")
    ambition = prestige_gap / 25 + max(0, 30 - buyer.rank) / 30
    reasons.append(f"амбиции {player.p('ambition'):.0f} vs уровень клуба {TIER_PRESTIGE[buyer.tier]}")

    loyalty = 0.0
    if current is not None and current is not buyer:
        loyalty = -(player.p("loyalty") / 100) * 1.5
        reasons.append(f"лояльность текущему клубу {player.p('loyalty'):.0f}")

    home = 0.0
    if relocation:
        _, travel = player.mod("travel_stress")
        home = -(player.p("home_attachment") / 100) * 1.5 * travel
        reasons.append(f"переезд: привязанность к дому {player.p('home_attachment'):.0f}")

    role = -0.8 if player.p("ego") > 70 and player.role in ("support",) else 0.0
    if role:
        reasons.append("эго не принимает роль support")

    return Verdict(_logistic(money + ambition + loyalty + home + role), reasons)


def transfer_request(player: Player, club: Club) -> Verdict:
    """Does the player ask to leave? Low role satisfaction + high ambition in a weak club."""
    reasons = []
    x = -3.0
    if player.s("role_satisfaction") < 45:
        x += (45 - player.s("role_satisfaction")) / 10
        reasons.append(f"недоволен ролью ({player.s('role_satisfaction'):.0f})")
    if player.p("ambition") > 65 and club.rank > 20:
        x += (player.p("ambition") - 65) / 15 + (club.rank - 20) / 40
        reasons.append(f"амбиция {player.p('ambition'):.0f}, а клуб на {club.rank}-м месте")
    if player.s("coach_trust") < 35:
        x += 1.0
        reasons.append("не доверяет тренеру")
    x += player.mod("role_hunger")[0] * (player.s("form") - 50) / 25
    return Verdict(_logistic(x), reasons)


def conflict_chance(a: Player, b: Player, irritation: float) -> Verdict:
    """Weekly chance an irritation edge becomes an open conflict."""
    x = -6.5 + irritation / 15 + (a.p("conflict") - 50) / 20 + (a.p("ego") - 50) / 30 - (a.stat("teamwork") - 50) / 30
    x += 0.8 if a.p("criticism") > 65 else 0.0
    reasons = [f"раздражение {a.name}→{b.name} {irritation:.0f}", f"конфликтность {a.p('conflict'):.0f}",
               f"эго {a.p('ego'):.0f}"]
    return Verdict(_logistic(x), reasons)
