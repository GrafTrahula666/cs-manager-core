"""HLTW: the scene's media and memory (an HLTV-like world). It has no formal power: invites go by
leagues and the official ranking. What it has is attention.

- World ranking every week: a year of results, recent ones weigh more, the tier of the event
  matters and prize money does not. Different from the official ranking on purpose: the two
  can disagree. A high place pulls the club's brand up (soft power).
- Player rating from public stats: kills and survival per round against the average of the
  same sample, so 1.00 is average (the match engine is not calibrated yet, see
  docs/match-engine-plan.md; the rating is relative for that reason).
- MVP of every S and A event: the best rating there, with a small bonus for going deep.
- Top 20 players of the season. MVPs and the Top 20 bring fame, and fame feeds envy and status
  in the emergent engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TIER_WEIGHT = {"S": 100.0, "A": 60.0, "B": 25.0, "C": 10.0}
WINDOW = 52            # weeks of results in the ranking
PUBLISHED = 30         # places the ranking shows
MVP_TIERS = ("S", "A")
MVP_FAME = {"S": 8.0, "A": 4.0}
DEEP_RUN = {1: 0.10, 2: 0.05, 3: 0.02, 4: 0.02}   # MVP bonus by the club's place


def _stats(p) -> tuple[int, int, int, int]:
    st = p.__dict__.get("season_stats") or {}
    return st.get("kills", 0), st.get("deaths", 0), st.get("rounds", 0), st.get("maps", 0)


def ratings(lines: dict[str, tuple[int, int, int, int]], min_maps: int = 1) -> dict[str, float]:
    """name -> rating for (kills, deaths, rounds, maps); 1.00 is the average of the sample."""
    ok = {n: x for n, x in lines.items() if x[2] > 0 and x[3] >= min_maps}
    rounds = sum(x[2] for x in ok.values())
    if not rounds:
        return {}
    kpr = sum(x[0] for x in ok.values()) / rounds
    spr = max(0.01, sum(x[2] - x[1] for x in ok.values()) / rounds)
    return {n: 0.6 * (k / r) / max(0.01, kpr) + 0.4 * ((r - d) / r) / spr for n, (k, d, r, _) in ok.items()}


@dataclass
class Hltw:
    results: list[tuple[int, str, float]] = field(default_factory=list)   # (week, club, score)
    points: dict[str, float] = field(default_factory=dict)
    ranking: list[str] = field(default_factory=list)
    mvps: list[dict] = field(default_factory=list)
    top20: dict[int, list[dict]] = field(default_factory=dict)
    _snap: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    _club_of: dict[str, str] = field(default_factory=dict)

    # ---- events ----
    def event_start(self, t, field_) -> None:
        self._snap = {p.name: _stats(p) for c in field_ for p in c.roster}
        self._club_of = {p.name: c.name for c in field_ for p in c.roster}

    def event_end(self, t, order, week: int, season: int) -> list[str]:
        n = len(order)
        for place, c in enumerate(order, 1):
            self.results.append((week, c.name, TIER_WEIGHT.get(t.tier, 10.0) * (n - place + 1) / n))
        if t.tier not in MVP_TIERS or n < 2:
            return []
        by_name = {p.name: p for c in order for p in c.roster}
        lines = {}
        for name, before in self._snap.items():
            p = by_name.get(name)
            if p is not None:
                lines[name] = tuple(a - b for a, b in zip(_stats(p), before))
        place = {c.name: i for i, c in enumerate(order, 1)}
        rated = ratings(lines, min_maps=2)
        if not rated:
            return []
        score = {k: v + DEEP_RUN.get(place.get(self._club_of.get(k, ""), 99), 0.0) for k, v in rated.items()}
        best = max(sorted(score), key=lambda k: score[k])
        p, club = by_name[best], self._club_of[best]
        p.fame += MVP_FAME[t.tier]
        p.history.append(f"сезон {season}: MVP {t.name} по версии HLTW")
        self.mvps.append({"season": season, "week": week, "event": t.name, "player": best, "club": club,
                          "rating": round(rated[best], 2)})
        return [f"HLTW: MVP {t.name} — {best} ({club}), рейтинг {rated[best]:.2f}"]

    # ---- weekly ranking ----
    def week(self, clubs, week: int) -> list[str]:
        self.results = [r for r in self.results if week - r[0] < WINDOW]
        pts: dict[str, float] = {}
        for w, club, score in self.results:
            pts[club] = pts.get(club, 0.0) + score * (1 - (week - w) / WINDOW)
        names = {c.name for c in clubs}
        self.points = {k: v for k, v in pts.items() if k in names}
        old = self.ranking[0] if self.ranking else None
        self.ranking = sorted(self.points, key=lambda k: (-self.points[k], k))[:PUBLISHED]
        by = {c.name: c for c in clubs}
        for i, name in enumerate(self.ranking[:20]):   # being talked about pulls the brand up, never down
            c = by[name]
            target = 90.0 - 2.0 * i
            if c.brand < target:
                c.brand += 0.02 * (target - c.brand)
        if self.ranking and old is not None and self.ranking[0] != old:
            return [f"HLTW: {self.ranking[0]} — новый №1 мирового рейтинга (был {old})"]
        return []

    def place(self, club: str) -> int | None:
        return self.ranking.index(club) + 1 if club in self.ranking else None

    # ---- the season ----
    def season_end(self, clubs, season: int, week: int) -> list[str]:
        lines, club_of = {}, {}
        for c in clubs:
            for p in c.roster:
                lines[p.name], club_of[p.name] = _stats(p), c.name
        most = max((x[3] for x in lines.values()), default=0)
        rated = ratings(lines, min_maps=max(5, int(most * 0.4)))
        if not rated:
            return []
        mvp = {}
        for m in self.mvps:
            if m["season"] == season:
                mvp[m["player"]] = mvp.get(m["player"], 0) + 1
        score = {k: v + 0.04 * min(3, mvp.get(k, 0)) for k, v in rated.items()}
        top = sorted(score, key=lambda k: (-score[k], k))[:20]
        by = {p.name: p for c in clubs for p in c.roster}
        self.top20[season] = []
        for i, name in enumerate(top, 1):
            p = by[name]
            p.fame += (21 - i) * 0.5
            p.history.append(f"сезон {season}: №{i} в топ-20 игроков HLTW")
            self.top20[season].append({"rank": i, "player": name, "club": club_of[name],
                                       "rating": round(rated[name], 2), "maps": lines[name][3],
                                       "mvps": mvp.get(name, 0)})
        five = ", ".join(f"{i}. {n} ({club_of[n]})" for i, n in enumerate(top[:5], 1))
        return [f"HLTW: игрок сезона {season} — {top[0]} ({club_of[top[0]]}), рейтинг {rated[top[0]]:.2f}",
                f"HLTW топ-20 сезона {season}: {five}…"]
