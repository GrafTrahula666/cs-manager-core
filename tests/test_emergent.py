"""Emergent World Engine: causal chains, knowledge and misbeliefs, limits, memory across
transfers, delayed consequences of manager decisions, the optional LLM layer."""
from csmcore import economy
from csmcore.emergent import actions as A
from csmcore.emergent.appraisal import appraise
from csmcore.emergent.history import arc, render_tree, retrospective
from csmcore.emergent.invariants import engine as engine_inv, social as social_inv
from csmcore.emergent.manager_view import resolve
from csmcore.emergent.narrate import LLMNarrator, propose_action
from csmcore.worldgen import generate

NEG_KINDS = {a.name for a in A.ALL if a.tone == A.NEG}
HOSTILE = {"public_jab", "freeze_out", "private_confront", "side_with", "leak"}   # complaining is not war


def world(seed=1):
    clubs, graph, _, sysm, _ = generate(seed, 8)
    return clubs, graph, sysm, sysm.emergent


def tick(ew, clubs, graph, sysm, week, inject=None):
    ctx = ew.begin(clubs, graph, week, 1, sysm, None)
    if inject:
        inject(ctx)
    ew.week(ctx)
    return ctx


def setup_rivals(clubs, graph, envious: dict, stats: dict):
    club = clubs[3]
    x, y, z = club.roster[0], club.roster[1], club.roster[2]
    y.role, y.age, y.fame = x.role, 18, 0.0
    x.age, x.fame = 25, 8.0
    x.personality.update(envious)
    x.stats.update(stats)
    z.personality.update({"social_need": 85, "conflict": 65, "ego": 40})
    z.stats["leadership"] = 70
    graph.set_pair(z.name, y.name, friendship=90, trust=80)
    for q in club.roster:
        q.state["coach_trust"] = 30.0
    return club, x, y, z


def spotlight(ew, club, y, weeks):
    def inject(ctx):
        if ctx.week in weeks:
            ew.fame(y, 4)
            ew.emit(ctx, "standout", actor=y.name, club=club.name, visibility="public", engine_made=False,
                    impacts={y.name: {"status": 8, "attention": 10}}, salience=14,
                    text=f"{y.name} (18) разнёс плей-офф")
    return inject


def neg_acts(ew, actor, target, kinds=NEG_KINDS):
    return [f for f in ew.facts.facts.values() if f.actor == actor and (f.target == target or f.third == target)
            and f.data.get("action") in kinds]


ENVIOUS = ({"ego": 92, "conflict": 80, "media": 80, "criticism": 70, "risk": 75, "loyalty": 20, "social_need": 25},
           {"teamwork": 25.0})


def test_young_star_threatens_an_ego_and_a_third_party_steps_in():
    clubs, graph, sysm, ew = world(1)
    club, x, y, z = setup_rivals(clubs, graph, *ENVIOUS)
    standouts = set()
    for w in range(1, 15):
        tick(ew, clubs, graph, sysm, w, spotlight(ew, club, y, {1, 2, 3, 5}))
    standouts = {f.id for f in ew.facts.facts.values() if f.kind == "standout"}
    hits = neg_acts(ew, x.name, y.name)
    assert hits, "ревнивый ветеран так и не отреагировал на успех юниора"
    first = hits[0]
    assert standouts & set(ew.facts.ancestors(first.id)), render_tree(ew.why(first.id))
    # the young player's close friend gets involved: angry at the veteran, or acts about it
    third = [f for f in ew.facts.facts.values() if f.actor not in (x.name, y.name) and f.data.get("action")
             and (x.name in (f.target, f.third) or y.name in (f.target, f.third))]
    assert third or ew.minds.of(z.name).emotion("anger", x.name) > 0
    assert not engine_inv(ew) and not social_inv(clubs, graph)


CALM = ({"ego": 62, "conflict": 10, "media": 15, "criticism": 20, "ambition": 95, "loyalty": 70, "social_need": 50},
        {"teamwork": 85.0, "discipline": 92.0})


def test_same_spotlight_different_character_different_answer():
    """Same circumstances, six worlds each: the hothead goes to war more, the grinder goes to the gym.
    Nothing is scripted per personality, and people still sometimes act out of character."""
    totals = {}
    for label, (pers, stats) in (("envious", ENVIOUS), ("calm", CALM)):
        hostile = work = 0
        for seed in range(1, 7):
            clubs, graph, sysm, ew = world(seed)
            club, x, y, z = setup_rivals(clubs, graph, pers, stats)
            for w in range(1, 15):
                tick(ew, clubs, graph, sysm, w, spotlight(ew, club, y, {1, 2, 3, 5}))
            hostile += len(neg_acts(ew, x.name, y.name, HOSTILE))
            work += sum(1 for f in ew.facts.facts.values() if f.actor == x.name and f.kind == "outwork")
        totals[label] = (hostile, work)
    assert totals["envious"][0] > totals["calm"][0], totals
    assert totals["calm"][1] >= 6, totals


def test_people_act_on_what_they_believe_and_the_truth_can_correct_it():
    clubs, graph, sysm, ew = world(2)
    club = clubs[2]
    a, b, c, d = club.roster[0], club.roster[1], club.roster[2], club.roster[3]
    graph.set_pair(c.name, b.name, friendship=90, trust=85)
    ctx = ew.begin(clubs, graph, 1, 1, sysm, None)
    f = ew.emit(ctx, "freeze_out", actor=a.name, target=b.name, club=club.name, impacts={b.name: {"belonging": -8}},
                salience=8, text=f"{a.name} перестал общаться с {b.name}")
    ew.learned.clear()
    # b's friend c only heard a rumour that blames d
    assert ew.facts.learn(c.name, f.id, 1, "статья", {"actor": d.name})
    appraise(ew, ctx, c, ew.minds.of(c.name), f)
    m = ew.minds.of(c.name)
    assert m.emotion("anger", d.name) > 0 and m.emotion("anger", a.name) == 0
    # b tells him what really happened: the false belief is gone
    ew.facts.learn(c.name, f.id, 2, f"рассказал {b.name}")
    assert c.name not in f.misbelief and f.believed(c.name)["actor"] == a.name


def test_drama_has_limits_and_crisis_turns_toward_repair():
    clubs, graph, sysm, ew = world(3)
    club = clubs[1]
    for p in club.roster:
        p.personality.update({"conflict": 95, "ego": 95, "media": 90, "loyalty": 5, "risk": 90, "criticism": 90})
        p.stats["teamwork"] = 10.0
    for p in club.roster:
        for q in club.roster:
            if p is not q:
                graph.set_pair(p.name, q.name, irritation=70, resentment=50, friendship=5)
                ew.minds.of(p.name).feel("anger", q.name, 60)
    for w in range(1, 41):
        tick(ew, clubs, graph, sysm, w)
        for p in club.roster:                       # keep the hatred burning every week
            for q in club.roster:
                if p is not q:
                    ew.minds.of(p.name).feel("anger", q.name, 15)
    assert not engine_inv(ew), engine_inv(ew)
    neg = [f for f in ew.facts.facts.values() if f.club == club.name and f.data.get("action") in NEG_KINDS]
    assert len(neg) <= 40 // 6 * 3 + 3        # the drama budget held over 40 weeks
    assert all(f.depth <= 9 for f in ew.facts.facts.values() if f.data.get("action"))


def test_memory_survives_a_transfer_and_the_old_club_gets_beaten():
    clubs, graph, sysm, ew = world(4)
    old, new = clubs[2], clubs[5]
    p, rival = old.roster[0], old.roster[1]
    p.personality["loyalty"] = 10
    tick(ew, clubs, graph, sysm, 1)
    ctx = ew.begin(clubs, graph, 2, 1, sysm, None)
    hurt = ew.emit(ctx, "public_jab", actor=rival.name, target=p.name, club=old.name, visibility="public",
                   impacts={p.name: {"pride": -12, "status": -6}}, salience=14, text=f"{rival.name} унизил {p.name}")
    ew.week(ctx)
    grudges = [m for m in ew.minds.of(p.name).memories if m.about == rival.name]
    assert grudges and grudges[0].fact == hurt.id
    economy.transfer(new, old, p, 1000.0, economy.Contract(p.name, 1000.0, end_week=200, buyout=50_000.0), 3)
    tick(ew, clubs, graph, sysm, 3)
    moved = [f for f in ew.facts.of_person(p.name, ("transfer",))]
    assert moved and moved[0].data == {"from": old.name, "to": new.name}
    assert any(m.about == rival.name for m in ew.minds.of(p.name).memories), "обида пропала после трансфера"
    # a final against the old club: the win is linked to the move
    ctx = ew.begin(clubs, graph, 4, 1, sysm, None)
    t = economy.Tournament("Major Test", "S", 1_000_000, [0.5, 0.5], lan=True, major=True)
    ew.on_series(ctx, t, "final", new, old, new, f"{new.name} 2:1 {old.name}")
    ew.week(ctx)
    rev = ew.facts.of_person(p.name, ("beat_former_club",))
    assert rev and moved[0].id in ew.facts.ancestors(rev[0].id)
    r = retrospective(ew, p.name, 1)
    assert any("бывший клуб" in x or "обыграл" in x for x in r["paragraphs"])
    assert arc(ew, p.name)["revenge"]


def test_backing_one_side_is_remembered_by_the_other():
    clubs, graph, sysm, ew = world(5)
    club = clubs[0]
    a, b = club.roster[0], club.roster[1]
    ctx = ew.begin(clubs, graph, 1, 1, sysm, club.name)
    f = ew.emit(ctx, "public_jab", actor=a.name, target=b.name, club=club.name, visibility="public",
                impacts={b.name: {"pride": -8}}, salience=14, text=f"{a.name} задел {b.name}")
    ew.week(ctx)
    sits = [s for s in ew.situations if s.club == club.name and s.fact == f.id]
    assert sits, "менеджер не узнал о публичном конфликте"
    s = sits[0]
    assert s.how and {o["key"] for o in s.options} >= {"back_a", "back_b", "mediate", "discipline", "ignore"}
    trust_before = a.s("coach_trust")
    resolve(ew, ew.begin(clubs, graph, 2, 1, sysm, club.name, open_week=False), s, "back_b")
    tick(ew, clubs, graph, sysm, 2)
    mgr = ew.manager_id(ctx, club)
    assert a.s("coach_trust") < trust_before
    assert ew.minds.of(a.name).opinion(mgr) < 0, "игрок не запомнил, что менеджер был против него"


def test_llm_is_optional_and_never_the_source_of_truth():
    clubs, graph, sysm, ew = world(6)
    club = clubs[1]
    p, q = club.roster[0], club.roster[1]
    ew.minds.of(p.name).feel("anger", q.name, 60)
    p.personality.update({"conflict": 80, "media": 80})
    ctx = ew.begin(clubs, graph, 1, 1, sysm, None)
    ok, why, f = propose_action(ew, ctx, p, club, lambda _: '{"action": "public_jab", "target": "nobody"}')
    assert not ok and f is None and "недоступно" in why
    ok, why, f = propose_action(ew, ctx, p, club, lambda _: "сломанный ответ")
    assert ok and f is None
    ok, why, f = propose_action(ew, ctx, p, club, lambda _: '{"action": "private_confront", "target": "%s", "third": null}' % q.name)
    assert ok and f is not None and f.kind == "private_confront"
    assert "решение предложено языковой моделью" in f.reasons
    narr = LLMNarrator(lambda _: "Говорят, во всём виноват vanta", )
    narr.known = {"vanta", p.name, q.name}
    assert narr.describe(f) == f.text            # names someone not in the fact: template wins
    narr = LLMNarrator(lambda _: (_ for _ in ()).throw(RuntimeError("нет сети")))
    assert narr.describe(f) == f.text and narr.failures == 1


def test_same_seed_same_story():
    def run():
        clubs, graph, sysm, ew = world(7)
        club = clubs[3]
        y = club.roster[1]
        for w in range(1, 20):
            tick(ew, clubs, graph, sysm, w, spotlight(ew, club, y, {2, 4}))
        return [(f.kind, f.actor, f.target, f.week) for f in ew.facts.facts.values()]
    assert run() == run()


def test_feelings_about_someone_who_left_the_game_do_not_break_the_week():
    clubs, graph, sysm, ew = world(8)
    p = clubs[0].roster[0]
    m = ew.minds.of(p.name)
    for k in ("gratitude", "anger", "envy"):
        m.feel(k, "retired_legend", 60)
    for w in range(1, 6):
        tick(ew, clubs, graph, sysm, w)
    assert not [f for f in ew.facts.facts.values() if "retired_legend" in (f.target, f.third)]


def test_pruned_knowers_take_their_false_beliefs_with_them():
    clubs, graph, sysm, ew = world(9)
    club = clubs[0]
    a, b, c = club.roster[0], club.roster[1], club.roster[2]
    other = clubs[1].roster[0]
    ctx = ew.begin(clubs, graph, 1, 1, sysm, None)
    f = ew.emit(ctx, "freeze_out", actor=a.name, target=b.name, club=club.name, salience=40, text="x")   # historic: kept
    ew.facts.learn(other.name, f.id, 1, "слух", {"actor": c.name})
    ew.facts.prune(1 + 60)
    assert f.id in ew.facts.facts and other.name not in f.knowers
    assert set(f.misbelief) <= set(f.knowers)


def test_a_new_season_or_a_new_signing_does_not_fake_a_standout():
    clubs, graph, sysm, ew = world(10)
    a, b = clubs[0], clubs[1]
    t = economy.Tournament("Cup", "A", 100_000, [0.6, 0.4])
    for p in a.lineup() + b.lineup():
        p.season_stats = {"kills": 200}            # a newcomer to the engine, kills from elsewhere
    ctx = ew.begin(clubs, graph, 1, 1, sysm, None)
    ew.on_series(ctx, t, "group", a, b, a, "2:0")
    for p in a.lineup() + b.lineup():
        p.season_stats = {"kills": 20}             # the season rolled over
    a.lineup()[0].season_stats = {"kills": 45}
    ew.on_series(ctx, t, "group", a, b, a, "2:0")
    ew.week(ctx)
    outs = [f for f in ew.facts.facts.values() if f.kind == "standout"]
    assert [f.actor for f in outs] == [a.lineup()[0].name]
    assert "при среднем по команде 25" in outs[0].reasons[0]
