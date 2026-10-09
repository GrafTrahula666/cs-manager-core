"""Rivalries and nemeses, after Shadow of Mordor's Nemesis system.

Every series leaves a memory. Close games, eliminations, finals and former players raise the
rivalry between two clubs; a player who keeps killing the same opponent becomes his nemesis
and gets a title. Rivalries change the next meeting: more pressure, more motivation, more fans
watching, and the Revenge Game trait wakes up against a former club.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .economy import Club
from .player import Player

KILL = re.compile(r"^(\S+) kills (\S+)")


@dataclass
class Memory:
    week: int
    text: str


@dataclass
class Rivalry:
    score: float = 0.0                      # 0-100
    meetings: int = 0
    wins: dict[str, int] = field(default_factory=dict)
    memories: list[Memory] = field(default_factory=list)


@dataclass
class Rivalries:
    clubs: dict[frozenset, Rivalry] = field(default_factory=dict)
    duels: dict[tuple[str, str], int] = field(default_factory=dict)   # (killer, victim) -> kills
    nemesis: dict[str, str] = field(default_factory=dict)             # victim -> killer
    titles: dict[str, str] = field(default_factory=dict)              # player -> earned title
    eliminations: dict[tuple[str, str], int] = field(default_factory=dict)  # (winner club, loser club)

    def get(self, a: str, b: str) -> Rivalry:
        return self.clubs.setdefault(frozenset((a, b)), Rivalry())

    def context(self, a: Club, b: Club, players: list[Player]) -> dict:
        """Context flags for a match a vs b."""
        r = self.get(a.name, b.name)
        ctx = {"rivalry": r.score > 40}
        if r.score > 40:
            # Big rivalry: the crowd and the stakes add pressure, the history adds motivation.
            ctx["team_bonus"] = 0.5 + r.score / 100
        return ctx

    def record_series(self, week: int, a: Club, b: Club, winner: Club, score: tuple[int, int],
                      round_logs: list[str], stage: str, decisive: bool) -> list[str]:
        """Update memories after a series. Returns notable lines for the chronicle."""
        notes = []
        r = self.get(a.name, b.name)
        r.meetings += 1
        r.wins[winner.name] = r.wins.get(winner.name, 0) + 1
        loser = b if winner is a else a
        gain = 6.0
        if min(score) > 0:
            gain += 6  # went the distance
        if stage in ("final", "semi"):
            gain += 8 if stage == "final" else 4
        if decisive:
            gain += 4
            key = (winner.name, loser.name)
            self.eliminations[key] = self.eliminations.get(key, 0) + 1
            if self.eliminations[key] == 3:
                notes.append(f"{winner.name} в третий раз выбивает {loser.name}: у {loser.name} появился заклятый враг")
                r.score += 15
                kills: dict[str, int] = {}
                names = {p.name: p for p in winner.roster}
                for line in round_logs:
                    m = KILL.match(line)
                    if m and m.group(1) in names:
                        kills[m.group(1)] = kills.get(m.group(1), 0) + 1
                if kills:
                    star = names[max(kills, key=kills.get)]
                    if self.award_title(star, f"Палач {loser.name}"):
                        notes.append(f"{star.name} получил прозвище «Палач {loser.name}»")
        if any(loser.name in p.former_clubs for p in winner.roster):
            gain += 5  # a former player beat his old club
            notes.append(f"бывший игрок {loser.name} помог {winner.name} выбить старый клуб")
        r.score = min(100.0, r.score + gain)
        r.memories.append(Memory(week, f"{winner.name} {max(score)}:{min(score)} {loser.name} ({stage})"))

        # Player duels inside the series -> nemesis and titles.
        for line in round_logs:
            m = KILL.match(line)
            if m:
                k = (m.group(1), m.group(2))
                self.duels[k] = self.duels.get(k, 0) + 1
                back = self.duels.get((k[1], k[0]), 0)
                # A nemesis is lopsided, not just frequent: 40+ kills and at least double the reverse.
                if self.duels[k] >= 40 and self.duels[k] >= 2 * back and k[1] not in self.nemesis:
                    self.nemesis[k[1]] = k[0]
                    notes.append(f"{k[0]} стал немезидой {k[1]}: {self.duels[k]} убийств против {back} в личных дуэлях")
        return notes

    def decay(self) -> None:
        """Weekly: rivalries slowly cool if the clubs stop meeting."""
        for r in self.clubs.values():
            r.score = max(0.0, r.score - 0.15)

    def award_title(self, player: Player, title: str) -> bool:
        """One nickname per player: the first one sticks, like in real scenes."""
        if player.name in self.titles:
            return False
        self.titles[player.name] = title
        player.history.append(f"получил прозвище «{title}»")
        player.fame += 10
        return True
