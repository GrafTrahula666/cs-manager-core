import random

from csmcore.chronicle import Chronicle
from csmcore.director import Director
from csmcore.economy import Club
from csmcore.legacy import Legacy
from csmcore.meta import Meta
from csmcore.player import STATS, Player
from csmcore.rivalry import Rivalries
from csmcore.talks import press_conference, team_talk


def p(name, level=65, **kw):
    return Player(name, {s: level for s in STATS}, **kw)


def test_director_modes_and_breather():
    club = Club("C")
    cas, pho = Director("cassandra"), Director("phoebe")
    assert pho.multiplier(club, "bad", 20) < cas.multiplier(club, "bad", 20)
    cas.hurt(club, 20)
    assert cas.multiplier(club, "bad", 21) < 0.5          # breather after a disaster
    assert cas.multiplier(club, "bad", 30) > 0.5
    # doing well raises adaptation -> more trouble later
    winner = Club("W", rank=10)
    d = Director("cassandra")
    for w in range(1, 20):
        winner.rank = max(1, 10 - w)
        winner.cash = 1e6
        d.observe(winner, w)
    assert d.adaptation["W"] > 30


def test_rivalry_grows_and_former_club_and_titles():
    r = Rivalries()
    a, b = Club("A", roster=[p("x")]), Club("B", roster=[p("y")])
    a.roster[0].former_clubs.add("B")
    notes = []
    for w in range(3):
        notes += r.record_series(w, a, b, a, (2, 1), ["x kills y"] * 5, "final", True)
    assert r.get("A", "B").score > 40 and r.context(a, b, [])["rivalry"]
    assert any("бывший игрок" in n for n in notes)
    assert any("Палач B" in n for n in notes)
    assert not r.award_title(a.roster[0], "другое")       # nickname sticks


def test_revenge_game_needs_former_club():
    hero = p("hero", traits=["revenge_game"])
    base = hero.duel_skill({"opponent": "Old"})
    hero.former_clubs.add("Old")
    assert hero.duel_skill({"opponent": "Old"}) > base


def test_meta_veto_and_familiarity():
    m = Meta()
    a, b = Club("A", roster=[p("x")]), Club("B", roster=[p("y")])
    m.familiarity[("A", m.pool[0])] = 95
    m.familiarity[("B", m.pool[1])] = 95
    maps = m.veto(a, b)
    assert len(maps) == 3 and len(set(maps)) == 3 and set(maps) <= set(m.pool)
    # like real vetoes: each side bans the map where the opponent is strongest
    assert m.pool[0] not in maps and m.pool[1] not in maps
    assert m.map_bonus(a, m.pool[0]) > m.map_bonus(b, m.pool[0])
    before = list(m.pool)
    rng = random.Random(1)
    for w in range(10):
        m.new_patch(w, rng)
    assert m.pool != before and len(m.pool) == 7


def test_meta_patch_shifts_roles():
    awp = p("a")
    awp.role = "awp"
    assert awp.duel_skill({"meta_roles": {"awp": 3.0}}) > awp.duel_skill({})


def test_team_talk_depends_on_personality():
    thin = p("thin", personality={"criticism": 95})
    thick = p("thick", personality={"criticism": 5})
    thick.stats["stress_resistance"] = 95
    club = Club("C", roster=[thin, thick])
    res = {r.player: r for r in team_talk(club, "criticize")}
    assert res["thin"].delta_morale < 0 < res["thick"].delta_morale


def test_press_trash_talk_heats_rivalry():
    riv = Rivalries()
    me, them = Club("Me", roster=[p("x")]), Club("Them")
    out = press_conference(me, "about_rival", "trash_talk", rivals=riv, opponent=them)
    assert riv.get("Me", "Them").score == 15 and out


def test_retirement_second_career_and_new_talents():
    rng = random.Random(0)
    leg = Legacy()
    old = p("old", 60, age=34, personality={"media": 95, "ambition": 10})
    old.stats["reaction"] = 40
    young = p("young", age=19)
    club = Club("C", roster=[old, young])
    for _ in range(5):
        leg.season_end([club], 52, rng)
    assert old not in club.roster and young in club.roster
    assert leg.retired[0].second_career == "caster"
    old.fame = 50
    talents = leg.new_talents(40, rng, 2)
    assert all(16 <= t.age <= 18 for t in talents)
    assert any("легенды old" in h for t in talents for h in t.history)


def test_chronicle_titles_and_hall_of_fame():
    ch = Chronicle()
    stars = [p(f"s{i}") for i in range(5)]
    club = Club("C", roster=stars)
    for s in range(1, 5):
        ch.record_title(s, 24, club, "Major", True)
    assert len(ch.titles["C"]) == 4 and "4-й титул" in ch.entries[-1].text
    hof = ch.hall_of_fame(stars + stars)
    assert len(hof) == 5 and hof[0][1] >= 40


def test_multi_season_world_is_deterministic():
    import sys
    sys.path.insert(0, "scripts")
    from demo_season import build_world
    from csmcore.legacy import Legacy
    from csmcore.market import Market
    from csmcore.season import Systems, run_season
    from csmcore.storylets import StoryEngine

    def run():
        clubs, graph, cal = build_world(4)
        sysm = Systems(stories=StoryEngine(director=Director()), market=Market(), rivalries=Rivalries(),
                       meta=Meta(), chronicle=Chronicle(), legacy=Legacy())
        for s in (1, 2):
            run_season(clubs, graph, cal, 40 + s, systems=sysm, season=s, start_week=(s - 1) * 52)
        return [e.text for e in sysm.chronicle.entries]
    a = run()
    assert a == run() and len(a) > 20
