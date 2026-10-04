"""Owner / board: season objectives, confidence in the manager, next season's budget.

Borrowed from Football Manager's board confidence and OOTP's owner goals. The owner has a
personality too: a patient owner forgives a bad start, a money-focused one cares about the
cash line more than the trophy cabinet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .economy import Club


@dataclass
class Objective:
    kind: str        # "rank" (finish at or above), "cash" (end season above), "youth" (U21 in lineup)
    target: float
    weight: float = 1.0
    text: str = ""


@dataclass
class Owner:
    name: str = "Owner"
    patience: float = 50.0
    ambition: float = 50.0
    money_focus: float = 50.0
    confidence: float = 60.0
    objectives: list[Objective] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    fired: bool = False

    def set_objectives(self, club: Club) -> list[Objective]:
        """Expectations come from where the club stands now (like FM's reputation-based
        predictions) and the owner's ambition: an ambitious owner wants to climb."""
        rank_target = max(1, round(club.rank * (1.25 - self.ambition / 200)))
        self.objectives = [
            Objective("rank", rank_target, 1.0 + self.ambition / 100, f"закончить сезон в топ-{rank_target}"),
            Objective("cash", 0.0 if self.money_focus < 60 else max(0.0, club.cash * 0.8), 0.5 + self.money_focus / 100,
                      "не уйти в минус" if self.money_focus < 60 else "сохранить 80% кассы"),
        ]
        if club.facilities.get("academy"):
            self.objectives.append(Objective("youth", 1, 0.5, "держать игрока до 21 года в основе"))
        return self.objectives

    def _score(self, o: Objective, club: Club) -> float:
        """-1 (failing badly) .. +1 (clearly on track)."""
        if o.kind == "rank":
            return max(-1.0, min(1.0, (o.target - club.rank) / max(3.0, o.target * 0.5)))
        if o.kind == "cash":
            scale = max(100_000.0, abs(o.target) or 100_000.0)
            return max(-1.0, min(1.0, (club.cash - o.target) / scale))
        if o.kind == "youth":
            return 1.0 if any(p.age < 21 for p in club.lineup()) else -0.5
        raise ValueError(o.kind)

    def monthly_review(self, club: Club, week: int) -> list[str]:
        if self.fired:
            return []
        total_w = sum(o.weight for o in self.objectives) or 1.0
        score = sum(self._score(o, club) * o.weight for o in self.objectives) / total_w
        speed = 6 * (1.5 - self.patience / 100)
        self.confidence = max(0.0, min(100.0, self.confidence + score * speed))
        notes = []
        if self.confidence < 12:
            self.fired = True
            notes.append(f"week {week}: владелец {club.name} увольняет менеджера (доверие {self.confidence:.0f})")
        elif self.confidence < 25:
            notes.append(f"week {week}: ультиматум от владельца: доверие {self.confidence:.0f}")
        elif self.confidence < 35:
            notes.append(f"week {week}: владелец обеспокоен: доверие {self.confidence:.0f}")
        self.log += notes
        return notes

    def next_budget(self, base_staff_month: float) -> float:
        """Trusted managers get more money to spend next season."""
        return base_staff_month * (0.7 + 0.6 * self.confidence / 100)
