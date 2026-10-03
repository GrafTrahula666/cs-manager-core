"""Layer 5: the social graph. Chemistry is not one number, it is computed from directed edges
between concrete people (concept section 9)."""
from __future__ import annotations

from dataclasses import dataclass

from .player import Player

# Edge dimensions, 0-100. Positive ones help, negative ones hurt.
POSITIVE = ("trust", "respect", "friendship", "pro_respect", "leader_loyalty", "culture")
NEGATIVE = ("irritation", "role_rivalry", "resentment", "fear")


@dataclass
class Relation:
    trust: float = 50.0
    respect: float = 50.0
    friendship: float = 40.0
    pro_respect: float = 50.0
    leader_loyalty: float = 50.0
    culture: float = 50.0  # cultural / language closeness
    irritation: float = 10.0
    role_rivalry: float = 0.0
    resentment: float = 0.0
    fear: float = 0.0

    def score(self) -> float:
        """-100..100: how well A works with B."""
        pos = sum(getattr(self, k) for k in POSITIVE) / len(POSITIVE)
        neg = sum(getattr(self, k) for k in NEGATIVE) / len(NEGATIVE)
        return pos - 50 - 1.5 * neg


class RelationGraph:
    def __init__(self) -> None:
        self.edges: dict[tuple[str, str], Relation] = {}

    def get(self, a: str, b: str) -> Relation:
        return self.edges.setdefault((a, b), Relation())

    def set_pair(self, a: str, b: str, **dims: float) -> None:
        for x, y in ((a, b), (b, a)):
            r = self.get(x, y)
            for k, v in dims.items():
                setattr(r, k, v)

    def nudge(self, a: str, b: str, dim: str, delta: float) -> None:
        r = self.get(a, b)
        setattr(r, dim, max(0.0, min(100.0, getattr(r, dim) + delta)))

    def chemistry(self, team: list[Player]) -> float:
        """Team chemistry -100..100 from all directed edges, weighted by who influences whom."""
        if len(team) < 2:
            return 0.0
        total, weight = 0.0, 0.0
        for a in team:
            for b in team:
                if a is b:
                    continue
                w = 1.0 + b.stat("leadership") / 100 * b.mod("influence")[1]
                total += self.get(a.name, b.name).score() * w
                weight += w
        return total / weight

    def friction_report(self, team: list[Player], top: int = 3) -> list[str]:
        """Human-readable 'why': the worst pairs in the roster."""
        pairs = []
        for i, a in enumerate(team):
            for b in team[i + 1:]:
                s = (self.get(a.name, b.name).score() + self.get(b.name, a.name).score()) / 2
                pairs.append((s, a.name, b.name))
        pairs.sort()
        return [f"{x} ↔ {y}: {s:+.0f}" for s, x, y in pairs[:top] if s < 0]

    def spread_tilt(self, team: list[Player], source: Player, morale_drop: float) -> dict[str, float]:
        """After a bad event, morale loss spreads through friendship and influence.
        Atmosphere Stabilizer in the roster halves the spread; Lone Wolf barely catches it."""
        spread_mul = 1.0
        for p in team:
            spread_mul *= p.mod("team_tilt_spread")[1]
        influence = source.mod("influence")[1] * (0.5 + source.stat("leadership") / 100)
        out = {}
        for p in team:
            if p is source:
                continue
            closeness = self.get(p.name, source.name).friendship / 100
            sens = (0.5 + p.p("social_need") / 100) * p.mod("atmosphere_sensitivity")[1]
            out[p.name] = morale_drop * 0.4 * closeness * influence * sens * spread_mul
            p.state["morale"] = max(0.0, p.s("morale") - out[p.name])
        return out
