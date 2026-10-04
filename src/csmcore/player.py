"""Player: the six layers of the concept doc.

1 base stats (20, 0-100)   2 hidden personality (10 axes)   3 Gold Traits
4 dynamic state            5 social graph (see relations.py) 6 history
"""
from __future__ import annotations

from . import traits as T

# Layer 1: the 20 base stats from the concept doc, 0-100.
STATS = (
    "aim", "reaction", "movement", "weapon_control",
    "game_sense", "positioning", "timing", "map_awareness", "utility_iq", "tactical_discipline",
    "adaptability", "analytical", "learning_speed",
    "stress_resistance", "tilt_control", "confidence_stability",
    "discipline", "teamwork", "communication", "leadership",
)

# Layer 2: hidden personality, 0-100 between the two poles.
PERSONALITY = (
    "ambition",       # happy with stability <-> demands tier-1 and titles
    "ego",            # accepts a role <-> wants to be the centre
    "loyalty",        # changes clubs fast <-> endures for the org
    "money_focus",    # ready to take less for the roster <-> maximises the contract
    "risk",           # avoids uncertainty <-> likes sharp career moves
    "criticism",      # takes it as feedback <-> takes it as a threat
    "social_need",    # fine alone <-> depends on the atmosphere
    "home_attachment",# relocates easily <-> tied to country/family
    "media",          # avoids publicity <-> loves attention
    "conflict",       # de-escalates <-> goes to confrontation fast
)

# Layer 4: dynamic state, 0-100. 50 is neutral; fatigue/stress/burnout: higher is worse.
STATE_DEFAULTS = {
    "form": 50.0, "morale": 60.0, "fatigue": 20.0, "sleep": 70.0, "stress": 25.0, "health": 95.0,
    "burnout": 5.0, "motivation": 65.0, "role_satisfaction": 65.0, "coach_trust": 60.0,
    "confidence": 55.0, "adaptation": 80.0,
}


class Player:
    """name, stats (layer 1), personality (2), traits (3), state (4), history (6).
    Layer 5, the social graph, lives outside the player in relations.RelationGraph."""

    # Backward-compatible shortcuts used by the first engine.
    @property
    def form(self) -> float:
        return self.s("form")

    @form.setter
    def form(self, v: float) -> None:
        self.state["form"] = v

    @property
    def morale(self) -> float:
        return self.s("morale")

    @morale.setter
    def morale(self, v: float) -> None:
        self.state["morale"] = v

    def __init__(self, name, stats=None, personality=None, traits=None, state=None, age=21,
                 country="XX", role="rifler", history=None, earnings=0.0, form=None, morale=None):
        self.name, self.age, self.country, self.role = name, age, country, role
        self.stats = dict(stats or {})
        self.personality = dict(personality or {})
        self.traits = list(traits or [])
        self.state = {**STATE_DEFAULTS, **(state or {})}
        self.history = list(history or [])
        self.earnings = earnings
        self.flags: set[str] = set()  # open situations, e.g. "transfer_requested"
        # Hidden ceiling for the average of the 20 stats (FM-style potential ability). Defaults to
        # a little above the current level; generators set it explicitly.
        self.potential: float = min(100.0, self.overall() + 5) if self.stats else 60.0
        self.fame: float = 0.0          # public profile, grows with results and media events
        self.joined_week: int = 0       # for tenure in the squad hierarchy
        if form is not None:
            self.state["form"] = form
        if morale is not None:
            self.state["morale"] = morale

    def __repr__(self) -> str:
        return f"Player({self.name!r}, {self.role}, traits={self.traits})"

    def stat(self, key: str, ctx: dict | None = None) -> float:
        add, mul = T.modifier(self.traits, f"stat:{key}", ctx)
        return max(0.0, min(100.0, (self.stats.get(key, 50.0) + add) * mul))

    def p(self, key: str) -> float:
        return self.personality.get(key, 50.0)

    def s(self, key: str) -> float:
        return self.state.get(key, STATE_DEFAULTS.get(key, 50.0))

    def mod(self, target: str, ctx: dict | None = None) -> tuple[float, float]:
        return T.modifier(self.traits, target, ctx)

    def pressure_penalty(self, ctx: dict | None) -> float:
        """Skill points lost to pressure: playoffs / match point vs stress resistance and state."""
        ctx = ctx or {}
        pressure = 0.5 * bool(ctx.get("playoffs")) + 0.5 * bool(ctx.get("match_point"))
        if not pressure:
            return 0.0
        vulnerability = (100 - self.stat("stress_resistance", ctx)) / 100 + self.s("stress") / 200
        _, mul = self.mod("pressure_penalty", ctx)
        return 10.0 * pressure * vulnerability * mul

    def duel_skill(self, ctx: dict | None = None) -> float:
        """Single number for a duel in a context. Weights follow the concept's opening-duel table
        (aim 24, reaction 16, positioning 13, timing 12, game sense 9 ...) and are placeholders
        until calibrated on demo data."""
        st = lambda k: self.stat(k, ctx)  # noqa: E731
        base = (
            0.40 * st("aim") + 0.25 * st("reaction") + 0.15 * st("positioning")
            + 0.10 * st("timing") + 0.10 * st("game_sense")
        )
        state = (0.10 * (self.s("form") - 50) + 0.05 * (self.s("morale") - 60)
                 + 0.04 * (self.s("confidence") - 55) - 0.05 * max(0.0, self.s("fatigue") - 40))
        add, mul = self.mod("duel", ctx)
        return (base + state + add) * mul - self.pressure_penalty(ctx)

    def overall(self) -> float:
        """Rough public rating, used by market value and AI clubs. Not used by the match engine."""
        return sum(self.stats.get(k, 50.0) for k in STATS) / len(STATS)
