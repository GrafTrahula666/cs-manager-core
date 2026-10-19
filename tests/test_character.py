import random

from csmcore import character, worldlife
from csmcore.economy import Club
from csmcore.game import Game
from csmcore.player import STATS, Player
from csmcore.traits import library, roll_traits


def p(name, traits=(), level=65, **personality):
    q = Player(name, {s: level for s in STATS}, traits=list(traits))
    q.personality.update(personality)
    return q


def test_acting_against_character_is_stressful():
    modest, show = p("m", ["modest"]), p("s", ego=50, media=50)
    assert character.reaction(modest, "show_off")[0] > 5
    assert character.reaction(show, "show_off")[0] <= 0.5
    for tid in ("narcissist", "pack_leader"):
        d, why = character.reaction(p(tid, [tid]), "admit_defeat")
        assert d >= 10 and why
    # a special trait costs more than the same number on a common one
    assert library()["pack_leader"].rarity == "special"
    assert character.reaction(p("x", ["modest"]), "charity")[0] < 0
    assert character.reaction(p("y"), "retreat")[0] < 0


def test_act_writes_stress_and_notes():
    a = p("a", ["modest"])
    a.state["stress"] = 10
    notes = character.act([a], "show_off", 5)
    assert a.s("stress") > 20 and notes and a.history


def test_trait_library_is_consistent():
    lib = library()
    for t in lib.values():
        assert t.desc and t.rarity in ("common", "rare", "special", "acquired"), t.id
        for act, _ in list(t.stress_on) + list(t.relief_on):
            assert act in character.ACTIONS, (t.id, act)
        if t.acquired:
            assert t.acquire, t.id
        if t.rarity == "special":
            assert t.cons, t.id
    rng = random.Random(1)
    rolled = {tid for _ in range(400) for tid in roll_traits(rng)}
    assert not rolled & {t.id for t in lib.values() if t.acquired}


def test_acquired_traits_come_from_state():
    from csmcore.relations import RelationGraph
    a = p("a", level=40, conflict=90)
    a.state["stress"] = 80
    club = Club("C", roster=[a])
    rng, got = random.Random(3), set()
    for w in range(200):
        character.month(club, w, rng, RelationGraph())
        got |= set(a.traits)
    assert {"slob", "rude"} & got


def test_stars_are_rare_and_come_and_go():
    a, b = p("a", level=95), p("b", level=70)
    club = Club("C", roster=[a, b])
    notes = character.stars_update([club], 3)
    assert "star" in a.flags and "star" not in b.flags and len(notes) == 1
    for s in STATS:
        a.stats[s] = 80
    character.stars_update([club], 4)
    assert "star" not in a.flags
    g = Game.new(seed=5)
    assert sum(q.overall() >= 90 for c in g.clubs for q in c.roster) <= 3


def test_weekly_choice_card_reaches_the_manager():
    g = Game.new(seed=2)
    deck = 0
    for _ in range(14):
        g.advance()
        st = g.sysm.stories
        deck += sum(1 for f in st.pending if st.events[f.event_id].get("deck"))
        for f in list(st.pending):
            g.desk.answer_event(f, 0)
    assert deck >= 3


def test_superteam_appears_and_vanishes():
    g = Game.new(seed=4, n_clubs=24)
    old = worldlife.SUPERTEAM_BASE
    worldlife.SUPERTEAM_BASE = 1.0
    try:
        rng = random.Random(1)
        notes = worldlife.superteam(g.clubs, g.sysm, 3, 1, rng, lambda: f"n{rng.random():.6f}", g.club_name)
    finally:
        worldlife.SUPERTEAM_BASE = old
    sup = [c for c in g.clubs if c.tier == "super" and any(f.startswith("superteam_until") for f in c.flags)]
    assert notes and len(sup) == 1 and len(g.clubs) == 24
    assert min(q.overall() for q in sup[0].roster) > 92
    worldlife.superteam(g.clubs, g.sysm, 6, 1, random.Random(2), lambda: "z", g.club_name)
    assert sup[0] not in g.clubs and len(g.clubs) == 24
