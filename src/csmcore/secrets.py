"""Secrets and hooks, after Crusader Kings III.

Some events leave a secret behind (gambling, a quiet match-fixing contact, stimulants, a fake
age on a youth contract, old toxic posts, a side deal with an agent). Secrets are known by
someone or no one. Teammates, scouts and rival clubs can discover them. Knowing a secret gives
a hook: leverage to make a player stay, accept a lower salary or drop a transfer request, or
to leak it before a big match. Using a hook works, but the player remembers.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .economy import Club
from .player import Player
from .relations import RelationGraph

SECRET_KINDS = {
    # severity 1-3: how bad exposure is; base weekly discovery chance per knower-candidate
    "gambling": {"severity": 2, "discover": 0.02, "text": "играет в казино и на ставках"},
    "fixing_contact": {"severity": 3, "discover": 0.01, "text": "имел контакт с организаторами договорных матчей"},
    "stimulants": {"severity": 2, "discover": 0.015, "text": "принимает стимуляторы перед LAN"},
    "fake_age": {"severity": 1, "discover": 0.01, "text": "подписал юниорский контракт с неверным возрастом"},
    "toxic_past": {"severity": 1, "discover": 0.03, "text": "писал токсичные посты в прошлом"},
    "side_deal": {"severity": 2, "discover": 0.015, "text": "тайно договорился с агентом другого клуба"},
}


@dataclass
class Secret:
    player: str
    kind: str
    week: int
    known_by: set[str] = field(default_factory=set)   # club names and player names
    exposed: bool = False

    @property
    def severity(self) -> int:
        return SECRET_KINDS[self.kind]["severity"]


@dataclass
class Secrets:
    items: list[Secret] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def add(self, p: Player, kind: str, week: int) -> Secret:
        for s in self.items:
            if s.player == p.name and s.kind == kind and not s.exposed:
                return s
        s = Secret(p.name, kind, week)
        self.items.append(s)
        p.flags.add(f"secret:{kind}")
        return s

    def of(self, name: str) -> list[Secret]:
        return [s for s in self.items if s.player == name and not s.exposed]

    def hooks(self, holder: str) -> list[Secret]:
        """Secrets a club or person can use as leverage."""
        return [s for s in self.items if holder in s.known_by and not s.exposed]

    def discovery_week(self, clubs: list[Club], graph: RelationGraph, week: int, rng: random.Random) -> list[str]:
        """Teammates notice, clubs' analysts dig, rival clubs dig harder."""
        notes = []
        where = {p.name: c for c in clubs for p in c.roster}
        for s in self.items:
            if s.exposed or s.player not in where:
                continue
            home = where[s.player]
            base = SECRET_KINDS[s.kind]["discover"]
            for mate in home.roster:
                if mate.name == s.player or mate.name in s.known_by:
                    continue
                closeness = graph.get(mate.name, s.player).friendship / 100
                if rng.random() < base * (0.5 + closeness + mate.stat("analytical") / 200):
                    s.known_by.add(mate.name)
                    notes.append(f"{mate.name} узнал секрет {s.player}")
            if home.name not in s.known_by and rng.random() < base * (0.5 + home.scout_quality / 100):
                s.known_by.add(home.name)
                notes.append(f"клуб {home.name} узнал, что {s.player} {SECRET_KINDS[s.kind]['text']}")
            for other in clubs:
                if other is home or other.name in s.known_by:
                    continue
                if rng.random() < base * 0.08 * (other.scout_quality / 50):
                    s.known_by.add(other.name)
                    notes.append(f"{other.name} раскопал секрет игрока {s.player} из {home.name}")
        self.log += [f"week {week}: {n}" for n in notes]
        return notes

    def use_hook(self, holder: Club, p: Player, action: str, graph: RelationGraph, week: int) -> str:
        """Leverage a known secret. Actions: 'stay' (drop transfer request), 'pay_cut' (accept 20% less),
        'sign' (agree to join holder; caller does the transfer), 'leak' (expose to media)."""
        hooks = [s for s in self.hooks(holder.name) if s.player == p.name]
        if not hooks:
            raise ValueError(f"{holder.name} has no hook on {p.name}")
        s = max(hooks, key=lambda x: x.severity)
        if action == "leak":
            return self.expose(s, p, holder, week, graph)
        key = "coach_trust" if p in holder.roster else "morale"
        p.state[key] = max(0.0, p.s(key) - 15 * s.severity)
        p.state["stress"] = min(100.0, p.s("stress") + 10 * s.severity)
        for q in holder.roster:
            if q is not p:
                graph.nudge(p.name, q.name, "resentment", 5)
        p.history.append(f"week {week}: на него надавили секретом ({s.kind})")
        if action == "stay":
            p.flags.discard("transfer_requested")
            return f"{p.name} забрал просьбу о трансфере под давлением"
        if action == "pay_cut":
            c = holder.contracts.get(p.name)
            if c:
                c.salary_month *= 0.8
            return f"{p.name} согласился на зарплату на 20% ниже под давлением"
        if action == "sign":
            return f"{p.name} согласился перейти в {holder.name} под давлением"
        raise ValueError(action)

    def expose(self, s: Secret, p: Player, by: Club | None, week: int, graph: RelationGraph,
               home: Club | None = None) -> str:
        s.exposed = True
        p.flags.discard(f"secret:{s.kind}")
        p.state["stress"] = min(100.0, p.s("stress") + 20 * s.severity)
        p.state["morale"] = max(0.0, p.s("morale") - 15 * s.severity)
        p.fame = max(0.0, p.fame - 5 * s.severity)
        if s.severity >= 3:
            p.flags.add("benched")
        if home is not None:
            home.brand = max(0.0, home.brand - 3 * s.severity)
        p.history.append(f"week {week}: всплыл секрет: {SECRET_KINDS[s.kind]['text']}")
        who = f" (слил {by.name})" if by else ""
        line = f"Всплыл секрет {p.name}: {SECRET_KINDS[s.kind]['text']}{who}"
        self.log.append(f"week {week}: {line}")
        return line

    def rival_leaks(self, home: Club, opponent: Club, rivalry_score: float, week: int,
                    graph: RelationGraph, rng: random.Random) -> list[str]:
        """Before a big match a hostile rival may leak what it knows about the opponent."""
        out = []
        if rivalry_score < 60:
            return out
        for p in opponent.roster:
            for s in self.of(p.name):
                if home.name in s.known_by and rng.random() < (rivalry_score - 50) / 200:
                    out.append(self.expose(s, p, home, week, graph, home=opponent))
        return out
