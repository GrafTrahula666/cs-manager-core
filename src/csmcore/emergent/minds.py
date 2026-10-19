"""Minds: needs and goals, emotions, memories of other people, intentions.

A mind belongs to a person, not to a club: it is keyed by name, so a player keeps his grudges,
his gratitude and his ambitions through transfers, club closures and retirement.

Goals come from personality and situation (an ambitious ego wants to be the centre of the team,
a social player wants a calm dressing room) and from memories (someone who was humiliated wants
to prove the culprit wrong). Emotions are short-lived and aimed at someone. Intentions are what
a person has decided to do but has not done yet; they can be dropped when the feeling fades.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_MEMORIES = 16
MEMORY_FLOOR = 4.0           # weaker memories are forgotten
# Weekly decay. Anger burns out fast, envy lingers, gratitude and grudges (memories) last years.
DECAY = {"anger": 0.75, "envy": 0.85, "threat": 0.8, "gratitude": 0.93, "distress": 0.7, "joy": 0.7,
         "pride": 0.8, "shame": 0.8}
EMOTIONS = tuple(DECAY)


@dataclass
class Memory:
    fact: int
    about: str
    kind: str          # betrayal, humiliation, help, support, conflict, reconcile, sided_against ...
    valence: float     # -100..100 how this person feels about `about` because of it
    week: int
    strength: float    # fades slowly; strong grudges outlive careers

    def weight(self) -> float:
        return abs(self.valence) * self.strength / 100


@dataclass
class Intention:
    action: str
    target: str | None
    third: str | None
    causes: list[int]
    formed: int
    utility: float


@dataclass
class Mind:
    name: str
    emotions: dict[str, float] = field(default_factory=dict)    # "anger|vanta" -> 0..100
    memories: list[Memory] = field(default_factory=list)
    goals: dict[str, float] = field(default_factory=dict)       # "status" -> weight 0..1, "prove|X" ...
    intention: Intention | None = None
    cooldowns: dict[str, int] = field(default_factory=dict)     # "action|target" -> week available
    last_action: int = -100
    emotion_causes: dict[str, list[int]] = field(default_factory=dict)  # same keys as emotions

    # ---- emotions ----
    def feel(self, kind: str, about: str | None, amount: float, cause: int | None = None) -> None:
        key = f"{kind}|{about or ''}"
        self.emotions[key] = max(0.0, min(100.0, self.emotions.get(key, 0.0) + amount))
        if cause is not None and amount > 0:
            c = self.emotion_causes.setdefault(key, [])
            if cause not in c:
                c.append(cause)
                del c[:-3]

    def emotion(self, kind: str, about: str | None = None) -> float:
        return self.emotions.get(f"{kind}|{about or ''}", 0.0)

    def strongest(self, kinds=EMOTIONS) -> tuple[str, str, float]:
        best = ("", "", 0.0)
        for key in sorted(self.emotions):
            k, _, who = key.partition("|")
            if k in kinds and self.emotions[key] > best[2]:
                best = (k, who, self.emotions[key])
        return best

    def causes_of(self, kind: str, about: str | None) -> list[int]:
        return list(self.emotion_causes.get(f"{kind}|{about or ''}", []))

    def decay(self) -> None:
        for key in sorted(self.emotions):
            v = self.emotions[key] * DECAY.get(key.split("|", 1)[0], 0.8)
            if v < 1.0:
                del self.emotions[key]
                self.emotion_causes.pop(key, None)
            else:
                self.emotions[key] = v
        for m in self.memories:
            m.strength *= 0.995 if abs(m.valence) >= 40 else 0.98
        self.memories = [m for m in self.memories if m.weight() >= MEMORY_FLOOR / 10]

    # ---- memories ----
    def remember(self, fact: int, about: str, kind: str, valence: float, week: int) -> Memory:
        for m in self.memories:
            if m.fact == fact and m.about == about:
                return m
        m = Memory(fact, about, kind, max(-100.0, min(100.0, valence)), week, 100.0)
        self.memories.append(m)
        if len(self.memories) > MAX_MEMORIES:
            self.memories.sort(key=lambda x: (-x.weight(), -x.week))
            del self.memories[MAX_MEMORIES:]
        return m

    def opinion(self, about: str) -> float:
        """Net feeling about someone from memories (-100..100)."""
        return max(-100.0, min(100.0, sum(m.valence * m.strength / 100 for m in self.memories if m.about == about)))

    def grudges(self, min_valence: float = -25) -> list[Memory]:
        return sorted((m for m in self.memories if m.valence <= min_valence), key=lambda m: m.valence)

    def memories_about(self, about: str) -> list[Memory]:
        return [m for m in self.memories if m.about == about]


@dataclass
class Minds:
    minds: dict[str, Mind] = field(default_factory=dict)

    def of(self, name: str) -> Mind:
        m = self.minds.get(name)
        if m is None:
            m = self.minds[name] = Mind(name)
        return m

    def peek(self, name: str) -> Mind | None:
        return self.minds.get(name)


def goals_for(p, club, fame_rank: int, team_size: int) -> dict[str, float]:
    """Long-term needs from personality and situation; weights 0..1."""
    g = {
        "status": max(0.0, (p.p("ego") - 40) / 60) * (1.0 if fame_rank > 1 else 0.6),   # be the centre
        "attention": max(0.0, (p.p("media") - 45) / 55),
        "win": p.p("ambition") / 100,
        "harmony": max(0.0, (p.p("social_need") - 30) / 70) * 0.7 + p.stat("leadership") / 300,
        "money": p.p("money_focus") / 100 * 0.6,
        "stability": max(0.0, (p.p("home_attachment") + p.p("loyalty") - 100) / 100),
        "growth": max(0.0, (24 - p.age) / 8) * 0.6 + max(0.0, p.potential - p.overall()) / 40,
    }
    return {k: round(min(1.0, v), 3) for k, v in g.items() if v > 0.05}
