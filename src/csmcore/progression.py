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
    name: str = ""
    age: int = 35
    country: str = ""
    traits: list[str] = field(default_factory=list)
    face: dict = field(default_factory=dict)         # avatar seed and overrides, drawn by the UI
    stats: dict[str, int] = field(default_factory=dict)   # tactics/people/analytics/business/intrigue
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

    def journal_has(self, reason: str, key: str) -> bool:
        return f"{reason}:{key}" in self._seen

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

    def _base(self, name: str) -> float:
        """Background stats and character traits: what the manager brings before any talent."""
        bg = livingdata.load("backgrounds")
        x = 0.0
        for stat, chans in bg["stat_channels"].items():
            if name in chans:
                x += max(0, self.stats.get(stat, 0) - bg["stat_baseline"]) * bg["stat_step"]
        for tr in bg["traits"]:
            if tr["id"] in self.traits:
                x += sum(e["value"] for e in tr["effects"] if e["channel"] == name)
        return x

    def channel(self, name: str) -> float:
        """Total effect on one channel: stats + traits + unlocked talents, clamped by the cap."""
        return livingdata.channel_total(self.unlocked, name, self._base(name))

    def explain(self, name: str) -> list[str]:
        """Sources of a channel's value, for the interface: nothing is applied without a reason."""
        out = []
        nodes = livingdata.talents()
        for t in sorted(self.unlocked):
            for e in nodes[t]["effects"]:
                if e["channel"] == name:
                    out.append(f"талант «{nodes[t]['name']}»: {e['value']:+.0%}")
        bg = livingdata.load("backgrounds")
        for stat, chans in bg["stat_channels"].items():
            v = max(0, self.stats.get(stat, 0) - bg["stat_baseline"]) * bg["stat_step"]
            if name in chans and v:
                out.append(f"навык «{STAT_RU[stat]}» {self.stats.get(stat, 0)}: {v:+.1%}")
        for tr in bg["traits"]:
            if tr["id"] in self.traits:
                out += [f"черта «{tr['name']}»: {e['value']:+.0%}" for e in tr["effects"] if e["channel"] == name]
        return out


STAT_RU = {"tactics": "Тактика", "people": "Люди", "analytics": "Аналитика", "business": "Бизнес", "intrigue": "Интриги"}


def create(manager_id: str, name: str, age: int, country: str, background: str, specialization: str,
           traits: list[str], face: dict | None = None) -> ManagerProgression:
    """Validated creation: one background, one specialization, two different traits."""
    bg = livingdata.load("backgrounds")
    b = next((x for x in bg["backgrounds"] if x["id"] == background), None)
    if b is None:
        raise ValueError("неизвестная предыстория")
    if specialization not in bg["specialization_stat"]:
        raise ValueError("неизвестная специализация")
    ids = {t["id"] for t in bg["traits"]}
    if len(set(traits)) != 2 or not set(traits) <= ids:
        raise ValueError("нужно выбрать две разные черты характера")
    name = " ".join(name.split())
    if len(name) < 2 or len(name) > 40:
        raise ValueError("имя от 2 до 40 символов")
    if not 25 <= int(age) <= 65:
        raise ValueError("возраст от 25 до 65")
    stats = dict(b["stats"])
    stats[bg["specialization_stat"][specialization]] += bg["specialization_bonus"]
    return ManagerProgression(manager_id, background, specialization, name, int(age), country, sorted(traits), dict(face or {}), stats)
