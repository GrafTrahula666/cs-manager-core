"""World chronicle, Hall of Fame and headlines (Dwarf Fortress legends mode).

Everything notable lands here with week and season: titles, finals, transfers, scandals,
rivalries, nemeses, retirements, patches. The chronicle is what makes save files worth
sharing: after five seasons it reads as a history nobody wrote.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("title", "final", "transfer", "story", "rivalry", "retirement", "patch", "board", "record")


@dataclass
class Entry:
    season: int
    week: int
    kind: str
    text: str
    people: tuple[str, ...] = ()


@dataclass
class Chronicle:
    entries: list[Entry] = field(default_factory=list)
    titles: dict[str, list[str]] = field(default_factory=dict)          # club -> tournaments won
    player_titles: dict[str, int] = field(default_factory=dict)          # player -> titles

    def add(self, season: int, week: int, kind: str, text: str, people=()) -> None:
        assert kind in KINDS, kind
        self.entries.append(Entry(season, week, kind, text, tuple(people)))

    def record_title(self, season: int, week: int, club, tournament: str, major: bool) -> None:
        self.titles.setdefault(club.name, []).append(f"{tournament} (сезон {season})")
        for p in club.lineup():
            self.player_titles[p.name] = self.player_titles.get(p.name, 0) + 1
            p.fame += 15 if major else 5
            p.history.append(f"сезон {season}: чемпион {tournament}")
        n = len(self.titles[club.name])
        text = f"{club.name} выигрывает {tournament}" + (f", это {n}-й титул клуба" if n > 1 else ", первый титул в истории клуба")
        self.add(season, week, "title", text, [p.name for p in club.lineup()])

    def hall_of_fame(self, players, min_score: float = 40) -> list[tuple[str, float]]:
        """Score = titles x 10 + fame + years at the top. Works on active and retired players."""
        out, seen = [], set()
        for p in players:
            if id(p) in seen:
                continue
            seen.add(id(p))
            score = self.player_titles.get(p.name, 0) * 10 + p.fame + sum("чемпион" in h for h in p.history) * 2
            if score >= min_score:
                out.append((p.name, round(score)))
        return sorted(out, key=lambda x: -x[1])

    def headlines(self, n: int = 10, kinds=None) -> list[str]:
        picked = [e for e in self.entries if kinds is None or e.kind in kinds]
        return [f"С{e.season} Н{(e.week - 1) % 52 + 1}: {e.text}" for e in picked[-n:]]
