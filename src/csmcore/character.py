"""Character: stress from decisions against who you are, acquired traits, stars.

CK3 idea, CS setting. Every decision the manager (or the world) makes can be an *action*:
a luxury-watch ad is `show_off`, admitting defeat at the press conference is `admit_defeat`.
Each player feels it through his traits and personality: a Modest player hates showing off,
a Narcissist or a Pack Leader hates admitting defeat, a Narcissist loves the cameras. The
rarer and stronger the trait, the harder the hit (special x1.6, rare x1.25).

Acquired traits (Slob, Rude, Insomniac, Burned Out, Star Sickness ...) are not rolled at birth.
They appear and fade monthly from the player's state: long stress plus low discipline can make
a player stop washing; calm months clear it again.

A star (★) is a player with overall 90+. Very rare; NPCs can grow into one if potential and
character allow. Stars bring fame and brand, and an ego that may turn into Star Sickness.
"""
from __future__ import annotations

import random

from .economy import Club
from .player import Player
from .relations import RelationGraph
from .traits import library

ACTIONS = {
    "show_off": "выпендрёж и роскошь на публику",
    "admit_defeat": "публично признать поражение",
    "make_excuses": "оправдываться пингом и удачей",
    "trash_talk": "задеть соперника",
    "public_criticism": "публичная критика игрока",
    "big_promise": "громкое обещание титула",
    "promo_shoot": "рекламные съёмки",
    "silly_promo": "нелепая реклама",
    "camera": "камеры и документалка",
    "social_event": "светский вечер",
    "charity": "благотворительность",
    "retreat": "ретрит с командой",
    "dirty_deal": "мутная сделка",
    "support_role": "роль второго номера",
    "role_change": "смена роли",
    "bench": "скамейка",
}
RARITY_MUL = {"common": 1.0, "rare": 1.25, "special": 1.6, "acquired": 1.0}
STAR_LEVEL = 90.0
STAR_LOST = 88.0

# Personality axes react too, trait or not: (axis, "gt"/"lt", threshold, action, stress)
PERSONALITY_RULES = [
    ("ego", "gt", 70, "admit_defeat", 6), ("ego", "gt", 70, "public_criticism", 8),
    ("ego", "gt", 70, "support_role", 5), ("ego", "gt", 70, "bench", 6),
    ("criticism", "gt", 65, "public_criticism", 8),
    ("media", "lt", 35, "promo_shoot", 5), ("media", "lt", 35, "camera", 6),
    ("media", "lt", 35, "social_event", 4), ("media", "lt", 35, "show_off", 3),
    ("media", "gt", 70, "promo_shoot", -3), ("media", "gt", 70, "camera", -3),
    ("social_need", "lt", 30, "social_event", 6), ("social_need", "gt", 70, "social_event", -5),
    ("conflict", "lt", 30, "trash_talk", 5), ("conflict", "gt", 70, "trash_talk", -4),
    ("risk", "lt", 50, "dirty_deal", 6),
]
BASELINE = {"retreat": -8, "dirty_deal": 3}   # everyone breathes out on a retreat


def reaction(p: Player, action: str) -> tuple[float, list[str]]:
    """Stress change (positive = more stress) and why."""
    lib = library()
    total, why = BASELINE.get(action, 0.0), []
    for tid in p.traits:
        t = lib.get(tid)
        if t is None:
            continue
        mul = RARITY_MUL.get(t.rarity, 1.0)
        for act, v in t.stress_on:
            if act == action:
                total += v * mul
                why.append(f"{t.name}: {ACTIONS[action]} против характера (+{v * mul:.0f})")
        for act, v in t.relief_on:
            if act == action:
                total -= v
                why.append(f"{t.name}: это ему по душе (−{v:.0f})")
    for axis, op, thr, act, v in PERSONALITY_RULES:
        if act == action and (p.p(axis) > thr if op == "gt" else p.p(axis) < thr):
            total += v
            if v > 0:
                why.append(f"характер ({axis} {p.p(axis):.0f}): +{v}")
    return total, why


def act(players: list[Player], action: str, week: int, scale: float = 1.0, report_from: float = 5.0) -> list[str]:
    """Apply an action to people; returns readable notes for the ones who really felt it."""
    notes = []
    for p in players:
        d, why = reaction(p, action)
        d *= scale
        if abs(d) < 0.5:
            continue
        p.state["stress"] = max(0.0, min(100.0, p.s("stress") + d))
        if d >= report_from:
            if week > 0:
                p.history.append(f"week {week}: {ACTIONS[action]} — стресс +{d:.0f}")
            notes.append(f"{p.name}: стресс +{d:.0f} ({'; '.join(why[:2]) or ACTIONS[action]})")
        elif d <= -report_from:
            notes.append(f"{p.name}: стресс {d:.0f} ({ACTIONS[action]})")
    return notes


def week(club: Club, graph: RelationGraph, week_no: int) -> None:
    """Weekly side effects of character: a slob or a rude player slowly loses friends, a luxury
    sponsor makes the modest ones wear watches they hate."""
    for p in club.roster:
        add, _ = p.mod("mates_friendship")
        if add:
            for q in club.roster:
                if q is not p:
                    graph.nudge(q.name, p.name, "friendship", add)
    if any(s.category == "luxury" for s in club.sponsors):
        act(club.roster, "show_off", week_no, scale=0.15, report_from=99)


def month(club: Club, week_no: int, rng: random.Random, graph: RelationGraph) -> list[str]:
    """Acquired traits come and go."""
    from .storylets import check
    notes, lib = [], library()
    acquired = [t for t in lib.values() if t.acquired]
    for p in club.roster:
        for t in acquired:
            has = t.id in p.traits
            rule = t.lose if has else t.acquire
            if not rule:
                continue
            conds, chance = rule
            if not all(check(c, club, p, None, graph) for c in conds) or rng.random() >= chance:
                continue
            if has:
                p.traits.remove(t.id)
                p.history.append(f"week {week_no}: избавился от «{t.name}»")
                notes.append(f"{p.name} избавился от черты «{t.name}»")
            elif not any(t.id in lib[o].incompatible for o in p.traits):
                p.traits.append(t.id)
                p.history.append(f"week {week_no}: приобрёл «{t.name}»")
                notes.append(f"{p.name} приобрёл черту «{t.name}»: {t.desc}")
    return notes


def is_star(p: Player) -> bool:
    return "star" in p.flags


def stars_update(clubs: list[Club], week_no: int) -> list[str]:
    """A ★ appears next to the nick at overall 90+, disappears below 88."""
    notes = []
    for c in clubs:
        for p in c.roster:
            ovr = p.overall()
            if "star" not in p.flags and ovr >= STAR_LEVEL:
                p.flags.add("star")
                p.fame += 20
                c.brand = min(100.0, c.brand + 3)
                if "modest" not in p.traits:
                    p.personality["ego"] = min(100.0, p.p("ego") + 8)
                p.history.append(f"week {week_no}: ★ стал звездой (уровень {ovr:.1f})")
                notes.append(f"★ {p.name} ({c.name}) стал звездой: уровень {ovr:.1f}")
            elif "star" in p.flags and ovr < STAR_LOST:
                p.flags.discard("star")
                p.history.append(f"week {week_no}: потерял звезду")
                notes.append(f"{p.name} ({c.name}) потерял звезду")
    return notes
