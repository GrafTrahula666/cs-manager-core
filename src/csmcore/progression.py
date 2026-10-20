"""Manager level, XP and talent points (LIVING CLUB, stage 1).

XP comes only for a named reason with a unique key, so the same achievement can never pay twice
(a repeated key is ignored and journalled). A season's XP is capped; levels are capped; one point
per new level; a talent needs its prerequisites. All numbers live in data/progression.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import livingdata


def xp_to_next(level: int) -> int:
    c = livingdata.load("progression")["xp_to_next"]
    return round(c["base"] * level ** c["exponent"])


@dataclass
class ManagerProgression:
    manager_id: str
    background: str = ""
    specialization: str = ""
    level: int = 1
    xp: int = 0                        # progress into the current level
    spent_points: int = 0
    unlocked: set[str] = field(default_factory=set)
    journal: list[dict] = field(default_factory=list)   # every grant: reason, key, xp, season, accepted
    _seen: set[str] = field(default_factory=set)
    _season_xp: dict[int, int] = field(default_factory=dict)
    _season_reason_n: dict[tuple[int, str], int] = field(default_factory=dict)

    @property
    def max_level(self) -> int:
        return livingdata.load("progression")["max_level"]

    @property
    def earned_points(self) -> int:
        return (self.level - 1) * livingdata.load("progression")["points_per_level"] + livingdata.load("progression")["start_points"]

    @property
    def available_points(self) -> int:
        return self.earned_points - self.spent_points

    def grant(self, reason: str, key: str, season: int, mult: float = 1.0) -> dict:
        """Try to award XP. Returns {'xp': granted, 'levels': new levels, 'why': text}."""
        cfg = livingdata.load("progression")
        rule = cfg["reasons"].get(reason)
        uid = f"{reason}:{key}"
        out = {"xp": 0, "levels": 0, "why": ""}
        if rule is None:
            out["why"] = "неизвестная причина"
        elif rule.get("once") and uid in self._seen:
            out["why"] = "уже начислено"
        elif rule.get("per_season_max") and self._season_reason_n.get((season, reason), 0) >= rule["per_season_max"]:
            out["why"] = "лимит за сезон"
        elif self.level >= self.max_level:
            out["why"] = "максимальный уровень"
        else:
            room = cfg["season_xp_cap"] - self._season_xp.get(season, 0)
            amount = max(0, min(round(rule["xp"] * mult), room))
            if amount == 0:
                out["why"] = "лимит опыта за сезон"
            else:
                self._seen.add(uid)
                self._season_reason_n[(season, reason)] = self._season_reason_n.get((season, reason), 0) + 1
                self._season_xp[season] = self._season_xp.get(season, 0) + amount
                self.xp += amount
                while self.level < self.max_level and self.xp >= xp_to_next(self.level):
                    self.xp -= xp_to_next(self.level)
                    self.level += 1
                    out["levels"] += 1
                if self.level >= self.max_level:
                    self.xp = 0
                out["xp"], out["why"] = amount, rule["desc"]
        self.journal.append({"reason": reason, "key": key, "season": season, **out})
        return out

    def can_unlock(self, tid: str) -> tuple[bool, str]:
        node = livingdata.talents().get(tid)
        if node is None:
            return False, "нет такого таланта"
        if tid in self.unlocked:
            return False, "уже изучен"
        if self.available_points < node["cost"]:
            return False, "нет свободных очков"
        missing = [r for r in node["requires"] if r not in self.unlocked]
        if missing:
            return False, "сначала: " + ", ".join(livingdata.talents()[m]["name"] for m in missing)
        return True, ""

    def unlock(self, tid: str) -> str:
        ok, why = self.can_unlock(tid)
        if not ok:
            raise ValueError(why)
        node = livingdata.talents()[tid]
        self.unlocked.add(tid)
        self.spent_points += node["cost"]
        return f"Изучен талант «{node['name']}»"

    def channel(self, name: str) -> float:
        """Total effect of the unlocked talents on one channel, clamped by the channel cap."""
        return livingdata.channel_total(self.unlocked, name)
