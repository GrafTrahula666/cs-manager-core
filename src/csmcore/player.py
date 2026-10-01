from __future__ import annotations

from dataclasses import dataclass, field

# The 20 base stats from the concept doc, 0-100.
STATS = (
    "aim", "reaction", "movement", "weapon_control",
    "game_sense", "positioning", "timing", "map_awareness", "utility_iq", "tactical_discipline",
    "adaptability", "analytical", "learning_speed",
    "stress_resistance", "tilt_control", "confidence_stability",
    "discipline", "teamwork", "communication", "leadership",
)


@dataclass
class Player:
    name: str
    stats: dict[str, float] = field(default_factory=dict)
    # dynamic state, 0-100
    form: float = 50.0
    morale: float = 50.0

    def stat(self, key: str) -> float:
        return self.stats.get(key, 50.0)

    def duel_skill(self) -> float:
        """Single number for a duel. Weights are placeholders until calibrated on demo data."""
        base = (
            0.40 * self.stat("aim")
            + 0.25 * self.stat("reaction")
            + 0.15 * self.stat("positioning")
            + 0.10 * self.stat("timing")
            + 0.10 * self.stat("game_sense")
        )
        return base + 0.10 * (self.form - 50.0) + 0.05 * (self.morale - 50.0)
