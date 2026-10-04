"""Team talks and press conferences (Football Manager), driven by our personality model.

The idea from FM: morale sits on a line from nervous to complacent; a talk should pull each
player toward focus. The same words land differently on different people: criticism fires up
a thick-skinned player and breaks a sensitive one; pressure helps an ice-cold player and
freezes a nervous one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .economy import Club
from .player import Player

TONES = ("calm", "encourage", "demand", "aggressive", "praise", "criticize")


@dataclass
class Reaction:
    player: str
    delta_morale: float
    delta_confidence: float
    text: str


def _focus(p: Player) -> float:
    """-1 nervous .. 0 focused .. +1 complacent."""
    conf = (p.s("confidence") - 55) / 45
    stress = p.s("stress") / 100
    return max(-1.0, min(1.0, conf - stress))


def team_talk(club: Club, tone: str, favourite: bool | None = None) -> list[Reaction]:
    """Before a match. `favourite` True/False/None (even game)."""
    if tone not in TONES:
        raise ValueError(tone)
    out = []
    for p in club.lineup():
        f = _focus(p)
        thin_skin = p.p("criticism") / 100           # takes criticism as a threat
        cold = p.stat("stress_resistance") / 100
        trust = p.s("coach_trust") / 100
        if tone == "calm":
            d = -f * 6 if f < 0 else -2
        elif tone == "encourage":
            d = 5 - 6 * max(0.0, f) + (3 if favourite is False else 0)
        elif tone == "demand":
            d = 6 * f + 4 * (cold - 0.5) - 3 * thin_skin + (3 if favourite else 0)
        elif tone == "aggressive":
            d = 8 * f + 6 * (cold - 0.6) - 8 * thin_skin + (2 if p.p("conflict") > 60 else 0)
        elif tone == "praise":
            d = 6 - 8 * max(0.0, f) - (3 if p.p("ego") > 75 else 0)
        else:  # criticize
            d = 5 * f - 9 * thin_skin + 3 * cold
        d *= 0.5 + trust                               # the words of a trusted coach weigh more
        p.state["morale"] = max(0.0, min(100.0, p.s("morale") + d))
        p.state["confidence"] = max(0.0, min(100.0, p.s("confidence") + d * 0.6))
        text = "воодушевлён" if d > 4 else "собран" if d > 1 else "без реакции" if d > -1 else "растерян" if d > -4 else "раздражён"
        out.append(Reaction(p.name, round(d, 1), round(d * 0.6, 1), text))
    return out


PRESS = {
    # question -> answer -> effects: morale of named player / whole team, rivalry, brand, owner
    "about_rival": {
        "respect": {"rivalry": -5, "brand": 1},
        "trash_talk": {"rivalry": 15, "team_morale": 3, "fans_pct": 1.0, "pressure": 5},
        "no_comment": {},
    },
    "about_player_form": {
        "back_him": {"player_morale": 8, "player_trust": 8},
        "honest_criticism": {"player_morale": -10, "player_trust": -10, "team_morale": 2},
        "no_comment": {"player_morale": -2},
    },
    "about_transfer_rumours": {
        "deny": {"player_morale": 3},
        "open_door": {"player_morale": -5, "player_flag": "transfer_requested"},
        "no_comment": {},
    },
    "about_owner_goals": {
        "promise_title": {"owner_confidence": 5, "team_morale": -2, "pressure": 8},
        "manage_expectations": {"owner_confidence": -3, "team_morale": 2},
    },
}


def press_conference(club: Club, question: str, answer: str, player: Player | None = None,
                     rivals=None, opponent: Club | None = None, owner=None) -> list[str]:
    eff = PRESS[question][answer]
    out = []
    if "team_morale" in eff:
        for q in club.roster:
            q.state["morale"] = max(0.0, min(100.0, q.s("morale") + eff["team_morale"]))
        out.append(f"мораль команды {eff['team_morale']:+}")
    if "pressure" in eff:
        for q in club.roster:
            q.state["stress"] = min(100.0, q.s("stress") + eff["pressure"] * (1 - q.stat("stress_resistance") / 100))
        out.append("давление на игроков выросло")
    if player is not None:
        if "player_morale" in eff:
            player.state["morale"] = max(0.0, min(100.0, player.s("morale") + eff["player_morale"]))
            out.append(f"{player.name}: мораль {eff['player_morale']:+}")
        if "player_trust" in eff:
            player.state["coach_trust"] = max(0.0, min(100.0, player.s("coach_trust") + eff["player_trust"]))
        if "player_flag" in eff:
            player.flags.add(eff["player_flag"])
            out.append(f"{player.name} воспринял это как разрешение уйти")
    if "rivalry" in eff and rivals is not None and opponent is not None:
        r = rivals.get(club.name, opponent.name)
        r.score = max(0.0, min(100.0, r.score + eff["rivalry"]))
        out.append(f"соперничество с {opponent.name}: {r.score:.0f}")
    if "brand" in eff:
        club.brand = max(0.0, min(100.0, club.brand + eff["brand"]))
    if "fans_pct" in eff:
        club.fans = int(club.fans * (1 + eff["fans_pct"] / 100))
    if "owner_confidence" in eff and owner is not None:
        owner.confidence = max(0.0, min(100.0, owner.confidence + eff["owner_confidence"]))
        out.append(f"доверие владельца {eff['owner_confidence']:+}")
    return out
