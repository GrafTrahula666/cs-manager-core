import random

from csmcore.economy import Club, Sponsor
from csmcore.player import STATS, Player
from csmcore.relations import RelationGraph
from csmcore.storylets import StoryEngine, check, library

COND_KEYS = {"any", "not", "stat", "state", "personality", "age", "trait", "role", "flag", "no_flag",
             "club_flag", "no_club_flag", "rel", "club", "sponsor"}
EFFECT_KEYS = {"secret", "state", "stat", "personality", "rel", "team_morale", "cash", "fans_pct", "brand", "sponsor_leaves",
               "flag", "unflag", "club_flag", "add_trait", "bench", "release", "follow", "follow_random", "history"}


def club_with(*players, **kw):
    return Club("C", roster=list(players), **kw)


def p(name, **kw):
    return Player(name, {s: 70 for s in STATS}, **kw)


def _conds(ev):
    out = list(ev.get("when", [])) + [m["if"] for m in ev.get("weight", [])]
    for o in ev.get("options", []):
        out += [m["if"] for m in o.get("ai_weight", [])]
    flat = []
    while out:
        c = out.pop()
        flat.append(c)
        out += c.get("any", []) + ([c["not"]] if "not" in c else [])
    return flat


def _effects(ev):
    out = list(ev.get("effects", []))
    for o in ev.get("options", []):
        out += o.get("effects", [])
    return out


def test_event_library_is_well_formed():
    lib = library()
    assert len(lib) >= 30
    from csmcore.traits import library as traits
    for ev in lib.values():
        assert ev["who"] in ("player", "pair", "club")
        for c in _conds(ev):
            assert COND_KEYS & set(c), (ev["id"], c)
        for e in _effects(ev):
            assert EFFECT_KEYS & set(e), (ev["id"], e)
            if "follow" in e:
                assert e["follow"] in lib, (ev["id"], e["follow"])
            for target, _ in e.get("follow_random", []):
                assert target in lib
            if "add_trait" in e:
                assert e["add_trait"] in traits()
        # every chain_only event is reachable from somewhere
    targets = {e.get("follow") for ev in lib.values() for e in _effects(ev)}
    targets |= {t for ev in lib.values() for e in _effects(ev) for t, _ in e.get("follow_random", [])}
    for ev in lib.values():
        if ev.get("chain_only"):
            assert ev["id"] in targets, ev["id"]


def test_conditions():
    g = RelationGraph()
    a, b = p("a", personality={"risk": 80}, traits=["unfiltered"]), p("b")
    club = club_with(a, b, sponsors=[Sponsor("x", "betting", 1, 99)])
    assert check({"personality": "risk", "gt": 65}, club, a, b, g)
    assert check({"trait": "unfiltered"}, club, a, b, g)
    assert check({"sponsor": "betting"}, club, a, b, g)
    assert not check({"not": {"sponsor": "betting"}}, club, a, b, g)
    assert check({"any": [{"trait": "nope"}, {"age": "", "lt": 30}]}, club, a, b, g)


def test_same_seed_same_stories():
    def run():
        players = [p(f"x{i}", personality={"media": 80, "risk": 80, "home_attachment": 80}) for i in range(5)]
        club = club_with(*players, cash=1e6)
        eng, g, rng = StoryEngine(), RelationGraph(), random.Random(5)
        return [(f.week, f.event_id, f.a.name if f.a else None, f.choice)
                for w in range(1, 80) for f in eng.week([club], g, w, rng)]
    a, b = run(), run()
    assert a == b and len(a) > 5


def test_scandal_chain_like_real_life():
    """A partner's provocative post -> media scandal -> club must choose. Silence always escalates."""
    star = p("star", personality={"media": 90})
    star.flags.add("has_partner")
    club = club_with(star, p("t1"), p("t2"), p("t3"), p("t4"), brand=70, cash=1e6,
                     sponsors=[Sponsor("S", "bank", 100_000, 999)])
    lib = dict(library())
    lib["partner_posts"] = {**lib["partner_posts"], "base": 0.9}  # force the first link for the test
    eng, g, rng = StoryEngine(lib), RelationGraph(), random.Random(1)
    fired = []
    for w in range(1, 4):
        fired += eng.week([club], g, w, rng, manager_club="C")
        for f in list(eng.pending):
            if f.event_id == "partner_posts":
                eng.resolve(f, 2, g, rng)  # "Промолчать"
    ids = [f.event_id for f in fired]
    assert "partner_posts" in ids and "scandal_viral" in ids
    viral = next(f for f in eng.pending if f.event_id == "scandal_viral")
    assert len(viral.options) == 3 and viral.why == ["продолжение цепочки"]
    eng.resolve(viral, 0, g, rng)  # bench the player
    assert "benched" in star.flags and star not in club.lineup()


def test_ai_resolves_and_manager_waits():
    players = [p(f"x{i}", personality={"media": 90}) for i in range(5)]
    for q in players:
        q.flags.add("has_partner")
    lib = {"partner_posts": {**library()["partner_posts"], "base": 0.9}, **{k: v for k, v in library().items() if k != "partner_posts"}}
    ai, me = club_with(*players[:2]), Club("Me", roster=players[2:])
    eng, g = StoryEngine(lib), RelationGraph()
    eng.week([ai, me], g, 1, random.Random(0), manager_club="Me")
    assert eng.pending and all(f.club is me for f in eng.pending)
