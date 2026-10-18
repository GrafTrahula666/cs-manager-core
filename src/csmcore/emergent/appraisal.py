"""Appraisal: how a person feels about a fact they learned (after the OCC model of emotions).

Rules read a fact's impacts (who won or lost status, attention, pride, belonging, harmony,
career, trust) and the observer's stance toward the people involved. They never look at the
fact's kind, so a new kind of fact needs no new rules:

    my loss caused by someone        -> anger at him, a memory of it
    my gain caused by someone        -> gratitude, a memory of it
    a rival's status/attention gain  -> envy, or a threat to my place if we compete for a role
    a friend's loss caused by X      -> anger at X on the friend's behalf
    my team's harmony suffers        -> distress about the team (leaders and social people)

Observers act on the version of the fact they believe, so a rumour that blames the wrong person
makes people angry at the wrong person.
"""
from __future__ import annotations

# How strongly each axis makes a resource matter to someone: resource -> (personality/stat, base)
SENSITIVITY = {
    "pride": ("criticism", 0.5), "status": ("ego", 0.4), "attention": ("media", 0.3),
    "belonging": ("social_need", 0.4), "career": ("ambition", 0.4), "trust": ("loyalty", 0.5),
    "harmony": ("social_need", 0.3),
}
MEMORY_MIN = 12.0    # a feeling at least this strong becomes a memory
SCALE = 2.5          # impacts are written in small units; feelings live on 0..100
ENVY_CAP = 15.0      # one good game of a rival is not enough to hate him; a run of them is


def _sens(p, res: str) -> float:
    axis, base = SENSITIVITY.get(res, ("ego", 0.4))
    return base + p.p(axis) / 100


def _person(x: str | None) -> bool:
    return bool(x) and ":" not in x


def _liking(graph, a: str, b: str) -> float:
    """-1..1 from the edge: friendship and trust above the default, minus resentment."""
    r = graph.get(a, b)
    return (r.friendship + r.trust) / 200 - 0.45 - r.resentment / 100 - r.irritation / 300


def competition(o, q, graph) -> float:
    """How much o competes with q for the same place and spotlight (0..~2)."""
    c = 0.6 if o.role == q.role else 0.0                  # one slot for two players
    c += graph.get(o.name, q.name).role_rivalry / 100
    c += max(0.0, (o.p("ego") - 50) / 60)                 # wants to be the face of the team
    if q.fame >= o.fame - 3 and o.fame >= q.fame - 10:
        c += 0.3                                           # the other one is catching up or ahead
    if q.age < o.age - 2:
        c += 0.3 if o.role == q.role else 0.15             # the young one is coming for my place
    return c


def appraise(ew, ctx, o, mind, f) -> list[str]:
    """Update o's emotions and memories from fact f. Returns notes for debugging."""
    seen = f.believed(o.name)
    actor = seen["actor"]
    notes = []
    g = ctx.graph
    my_club = ew.club_name(ctx, o.name)
    for who in sorted(f.impacts):
        for res in sorted(f.impacts[who]):
            d = f.impacts[who][res]
            if not d:
                continue
            if who == o.name:
                s = abs(d) * _sens(o, res) * SCALE
                if d < 0:
                    mind.feel("distress", None, s, f.id)
                    if _person(actor) and actor != o.name or (actor or "").startswith("mgr:"):
                        anger = s * (0.6 + o.p("conflict") / 100) * (1.4 if res == "pride" else 1.0)
                        mind.feel("anger", actor, anger, f.id)
                        if anger >= MEMORY_MIN:
                            mind.remember(f.id, actor, f.kind, -anger * 2.5, f.week)
                            notes.append(f"{o.name} злится на {actor} ({anger:.0f})")
                else:
                    mind.feel("joy", None, s, f.id)
                    if (_person(actor) or (actor or "").startswith("mgr:")) and actor != o.name:
                        mind.feel("gratitude", actor, s, f.id)
                        if s >= MEMORY_MIN:
                            mind.remember(f.id, actor, f.kind, s * 2.0, f.week)
            elif who.startswith("club:"):
                if who[5:] != my_club:
                    continue
                care = (o.p("social_need") / 100 + o.stat("leadership") / 200) * SCALE
                if d < 0:
                    mind.feel("distress", who, abs(d) * care * 2, f.id)
                    if _person(actor) and actor != o.name:
                        mind.feel("anger", actor, abs(d) * o.stat("leadership") / 250 * SCALE, f.id)
                else:
                    mind.feel("joy", who, d * care, f.id)
            elif _person(who) and who != o.name:
                q = ew.player(ctx, who)
                if q is None:
                    continue
                liking = _liking(g, o.name, who) + mind.opinion(who) / 100
                same_club = ew.club_name(ctx, who) == my_club
                shared = f.impacts.get(o.name, {}).get(res, 0.0) >= d * 0.5   # we won it together
                if d > 0 and res in ("status", "attention") and same_club and not shared:
                    threat = d * competition(o, q, g) * (0.4 + o.p("ego") / 70) - max(0.0, liking) * d * 1.5
                    if threat > 0.5:
                        kind = "threat" if o.role == q.role and q.age < o.age else "envy"
                        amount = min(ENVY_CAP, threat * SCALE)
                        mind.feel(kind, who, amount, f.id)
                        notes.append(f"{o.name}: {kind} к {who} ({amount:.0f})")
                elif d < 0 and _person(actor) and actor not in (o.name, who) and liking > 0.1:
                    anger = abs(d) * liking * (0.5 + o.p("social_need") / 100) * 1.5 * SCALE
                    mind.feel("anger", actor, anger, f.id)
                    if anger >= MEMORY_MIN:
                        mind.remember(f.id, actor, "hurt_friend", -anger * 2, f.week)
                elif d > 0 and _person(actor) and actor not in (o.name, who) and liking > 0.3:
                    mind.feel("gratitude", actor, d * liking * SCALE, f.id)
    return notes
