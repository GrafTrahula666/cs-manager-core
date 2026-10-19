from csmcore import save
from csmcore.game import Game
from csmcore.worldgen import _dist, generate


def test_world_has_100_150_clubs_with_tiers_and_concept_trio():
    clubs, graph, cal, sysm, home = generate(3, 120)
    assert len(clubs) == 120
    tiers = [c.tier for c in clubs]
    assert tiers.count("super") >= 3 and tiers.count("tier3") > 40
    assert len({c.name for c in clubs}) == 120
    names = [p.name for c in clubs for p in c.roster] + [p.name for p in sysm.market.free_agents]
    assert len(names) == len(set(names))
    home_club = next(c for c in clubs if c.name == home)
    assert {"vanta", "north", "sable"} <= {p.name for p in home_club.roster}
    assert len({c.region for c in clubs}) == 6
    assert abs(sum(_dist(16)) - 1) < 1e-9


def test_regional_events_invite_only_their_region():
    clubs, _, cal, _, _ = generate(3, 120)
    eu = next(t for t in cal[4] if t.region == "EU")
    invited = [c for c in clubs if eu.invited(c)]
    assert invited and all(c.region == "EU" and c.rank >= 17 for c in invited)


def test_save_load_continues_identically(tmp_path):
    g = Game.new(seed=11, n_clubs=40)
    for _ in range(10):
        g.advance()
    path = tmp_path / "career.sav"
    size = save.save(g, str(path))
    assert size > 1000
    h = save.load(str(path))
    for _ in range(8):
        a, b = g.advance(), h.advance()
        assert a.lines == b.lines
    assert [(c.name, c.rank, round(c.cash)) for c in g.clubs] == [(c.name, c.rank, round(c.cash)) for c in h.clubs]


def test_game_rolls_into_next_season_and_assistant_answers_inbox():
    g = Game.new(seed=5, n_clubs=24)
    for _ in range(53):
        g.advance()
    assert g.season == 2 and g.run.wk == 1
    assert all(g.week - f.week <= 2 for f in g.sysm.stories.pending)
    assert all(s.end_week > 52 for c in g.clubs for s in c.sponsors)


def test_api_is_json_friendly_and_playable():
    import json
    from csmcore import api
    s = api.new_game(seed=4, n_clubs=30)
    assert s["club"] and s["week"] == 0
    for fn in ("roster", "table", "finances", "inbox", "market", "chronicle", "rivalries", "meta_info"):
        json.dumps(getattr(api, fn)(), ensure_ascii=False)
    news = api.advance(3)
    assert news and all("lines" in n for n in news)
    assert api.talk("calm")
    data = api.save_b64()
    assert api.load_b64(data)["abs_week"] == api.state()["abs_week"]
