import random

from csmcore import circuit
from csmcore.game import Game
from csmcore.season import SeasonLog, run_tournament
from csmcore.worldgen import generate


def _events(cal, name):
    return next(t for ts in cal.values() for t in ts if t.name == name)


def test_120_clubs_split_into_four_leagues_by_ranking():
    clubs, _, cal, _, _ = generate(3, 120)
    sizes = [sum(c.division == k for c in clubs) for k in (1, 2, 3, 4)]
    assert sizes == [16, 16, 32, 56]
    assert {c.rank for c in clubs if c.division == 1} == set(range(1, 17))
    major, final = _events(cal, "Major"), _events(cal, "World Final")
    assert {c.name for c in clubs if major.invited(c)} == {c.name for c in clubs if c.division == 1}
    assert not any(_events(cal, "HACEIT Open Cup I").invited(c) for c in clubs if c.division <= 2)
    assert final.slots == 8 and final.seed_by_season


def test_the_major_qualifier_sends_two_tier2_clubs_and_the_last_direct_invites_make_room():
    clubs, graph, cal, _, _ = generate(4, 120)
    rng, log = random.Random(1), SeasonLog()
    qual = run_tournament(_events(cal, "HACEIT Major Qualifier"), clubs, graph, 22, rng, log)
    assert all(c.division == 2 for c in qual) and len(qual) == 16
    through = {c.name for c in qual[:2]}
    major = run_tournament(_events(cal, "Major"), clubs, graph, 24, rng, log)
    names = {c.name for c in major}
    assert len(major) == 16 and through <= names
    tier1 = sorted((c for c in clubs if c.division == 1), key=lambda c: c.rank)
    assert {c.name for c in tier1[:14]} <= names and not {c.name for c in tier1[14:]} & names
    assert not any(f.startswith("qual:") for c in clubs for f in c.flags)   # one ticket, one event


def test_season_table_decides_promotion_and_relegation():
    clubs, *_ = generate(5, 120)
    for c in clubs:   # the table runs against the ranking: the weakest of each league won the most
        c.season_points = float(c.rank)
    before = {c.name: c.division for c in clubs}
    lines = circuit.season_end(clubs)
    assert len(lines) == 3
    moved = {c.name: (before[c.name], c.division) for c in clubs if c.division != before[c.name]}
    assert sum(1 for a, b in moved.values() if (a, b) == (1, 2)) == 4
    assert sum(1 for a, b in moved.values() if (a, b) == (2, 1)) == 4
    assert sum(1 for a, b in moved.values() if (a, b) == (4, 3)) == 8
    top = {c.rank for c in clubs if before[c.name] == 1 and c.division == 2}
    assert top == {1, 2, 3, 4}            # relegation goes by the table, not by reputation
    assert [sum(c.division == k for c in clubs) for k in (1, 2, 3, 4)] == [16, 16, 32, 56]
    assert all(c.season_points == 0 for c in clubs)


def test_a_season_in_a_small_world_keeps_league_sizes_and_moves_clubs():
    g = Game.new(seed=2, n_clubs=40)
    first = {c.name: c.division for c in g.clubs}
    news = []
    for _ in range(52):
        news += g.advance().lines
    assert [sum(c.division == k for c in g.clubs) for k in (1, 2, 3, 4)] == [16, 16, 8, 0]
    assert any(c.division != first.get(c.name, 4) for c in g.clubs)
    assert any("Тир 1" in line for line in news)


def test_a_version_2_save_gets_leagues_and_the_league_calendar():
    from csmcore import save
    from csmcore.economy import Tournament
    g = Game.new(seed=6, n_clubs=40)
    for _ in range(3):
        g.advance()
    for c in g.clubs:      # what a pickle from before leagues looks like
        c.__dict__.pop("division", None), c.__dict__.pop("season_points", None)
    g.calendar = {24: [Tournament("Major", "S", 1_000_000, [1.0], max_rank_invite=16)]}
    raw = save.dumps(g)
    g2 = save.loads(raw[:len(save.MAGIC)] + bytes([2]) + raw[len(save.MAGIC) + 1:])
    assert [sum(c.division == k for c in g2.clubs) for k in (1, 2, 3)] == [16, 16, 8]
    assert any(t.name == "HACEIT Major Qualifier" for ts in g2.calendar.values() for t in ts)
    for _ in range(3):
        g2.advance()
