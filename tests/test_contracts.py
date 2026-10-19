"""Contracts that end (P0 from the research handoff): extension talks, free transfers, the hiring
journal with a reason for every failed signing, the academy fallback and the roster-core rule."""
import random

import pytest

from csmcore import contracts
from csmcore.economy import Club, Contract, Tournament
from csmcore.game import Game
from csmcore.market import Market
from csmcore.player import STATS, Player
from csmcore.relations import RelationGraph
from csmcore.season import (
    SeasonLog,
    SeasonRun,
    Systems,
    run_tournament,
    snapshot_invites,
)


def pl(name, level=60, age=25, loyalty=50.0, ambition=50.0):
    p = Player(name, {s: level for s in STATS}, age=age)
    p.personality["loyalty"], p.personality["ambition"] = loyalty, ambition
    return p


def club_with(name, players, end_week=100, tier="tier2", cash=1_000_000.0, **kw):
    c = Club(name, tier=tier, cash=cash, roster=list(players), **kw)
    for p in players:
        c.contracts[p.name] = Contract(p.name, 3_000, end_week, 0.0)
    return c


@pytest.fixture(scope="module")
def two_seasons():
    g = Game.new(seed=5, n_clubs=40)
    for _ in range(110):
        g.advance()
    return g


def test_an_expired_contract_ends_and_the_player_becomes_a_free_agent():
    m = Market()
    leaver = pl("leaver")
    c = club_with("C", [leaver] + [pl(f"p{i}") for i in range(5)], end_week=200)
    c.contracts["leaver"].end_week = 10
    c.contracts["leaver"].status = "leaving"
    lines = contracts.week([c], m, 11, random.Random(1))
    assert leaver not in c.roster and leaver in m.free_agents and "leaver" not in c.contracts
    assert "free_agent" in leaver.flags and leaver.free_since == 11
    assert any("свободным агентом" in x for x in lines) and m.stats["expired_left"] == 1
    assert m.journal[-1]["rule"].startswith("контракт закончился")


def test_a_loyal_starter_extends_and_a_bench_player_is_not_offered():
    m = Market()
    star = pl("star", level=70, loyalty=95, ambition=20)
    bench = pl("bench", level=40)
    c = club_with("C", [star, bench] + [pl(f"p{i}", 65) for i in range(4)], end_week=200)
    c.contracts["star"].end_week = c.contracts["bench"].end_week = 20
    contracts.week([c], m, 13, random.Random(2))
    assert c.contracts["star"].end_week > 20 and c.contracts["star"].contract_id > 0
    assert m.stats["renewed"] == 1 and c.contracts["bench"].status == "leaving"
    no = next(e for e in m.journal if e["player"] == "bench")
    assert no["kind"] == "not_offered" and "запасной" in no["rule"]


def test_a_player_who_asked_to_leave_refuses_an_extension_and_says_why():
    m = Market()
    p = pl("rebel", loyalty=5, ambition=95)
    p.flags.add("transfer_requested")
    c = club_with("C", [p] + [pl(f"p{i}") for i in range(4)], end_week=200, tier="tier3")
    c.contracts["rebel"].end_week = 20
    ok, line = contracts.offer(m, c, p, 500, 104, 13, random.Random(3), "менеджер")
    assert not ok and c.contracts["rebel"].status == "leaving"
    assert "сам просил трансфер" in m.journal[-1]["reasons"] or "rebel" in line


def test_a_leaver_is_on_the_market_and_cheaper_as_the_end_nears():
    m = Market()
    p = pl("leaver", level=70)
    c = club_with("C", [p] + [pl(f"p{i}") for i in range(5)], end_week=200)
    c.contracts["leaver"].status, c.contracts["leaver"].end_week = "leaving", 40
    assert (p, c) in m.listed([c], 10)
    late, early = contracts.sale_fee(c, p, 38), contracts.sale_fee(c, p, 10)
    c.contracts["leaver"].status = "active"
    assert late < early < contracts.sale_fee(c, p, 10)


def test_every_failed_hire_has_reasons_and_the_academy_closes_the_hole():
    m = Market()
    rich = pl("rich", level=85)          # wants more than a small club can pay
    rich.free_since = 0
    m.free_agents.append(rich)
    short = club_with("Short", [pl(f"s{i}", 50) for i in range(3)], tier="tier3", cash=50_000.0, region="EU")
    full = club_with("Full", [pl(f"f{i}", 50) for i in range(5)], tier="tier3", rank=2)
    rng = random.Random(4)
    for w in range(1, 6):
        m.week([short, full], w, rng)
    failed = [e for e in m.journal if e["kind"] == "hire_failed"]
    assert failed and all(e["reasons"] for e in failed)
    assert any(r.startswith("wage_gap") for e in failed for r in e["reasons"])
    assert len(short.roster) >= 5 and m.stats["academy"] >= 1
    kid = next(p for p in short.roster if any("академии" in h for h in p.history))
    assert 17 <= kid.age <= 19 and short.contracts[kid.name].salary_month <= 2_000


def test_contract_invariants_hold_in_a_long_world(two_seasons):
    g = two_seasons
    seen, ids = {}, []
    for c in g.clubs:
        for p in c.roster:
            assert p.name not in seen, f"{p.name} in {seen.get(p.name)} and {c.name}"
            seen[p.name] = c.name
            k = c.contracts.get(p.name)
            if "legend_contract" in p.flags:
                continue
            assert k is not None and k.end_week >= g.week, f"{p.name} at {c.name} plays without a contract"
            ids.append(k.contract_id)
        assert set(c.contracts) <= {p.name for p in c.roster}
    assert not seen.keys() & {p.name for p in g.sysm.market.free_agents}
    assert len([i for i in ids if i]) == len({i for i in ids if i})
    st = g.sysm.market.stats
    assert st["renewed"] > 0 and st["expired_left"] > 0
    short = [c for c in g.clubs if len(c.roster) < 5 and c.name != g.club_name]
    assert len(short) <= 3


def test_wages_do_not_vanish_after_two_seasons(two_seasons):
    g = two_seasons
    paid = [k for c in g.clubs for k in c.contracts.values() if k.end_week >= g.week]
    assert len(paid) >= 0.97 * sum(len(c.contracts) for c in g.clubs)


def test_a_club_that_lost_its_core_declines_the_invite_and_the_next_one_plays():
    rng = random.Random(1)
    clubs = [club_with(f"C{i}", [pl(f"c{i}p{j}", 70 - i) for j in range(5)], rank=i + 1) for i in range(5)]
    for i, c in enumerate(clubs):
        c.division = 1 if i < 4 else 2
    t = Tournament("Masters", "A", 100_000, [0.6, 0.4], divisions=(1,))
    run = SeasonRun(1, 0, rng, rng, rng, rng, SeasonLog(), {})
    snapshot_invites(run, clubs, {14: [t]}, 14 - 4)
    assert set(run.invites["Masters"]) == {"C0", "C1", "C2", "C3"}
    broken = clubs[0]                     # three of the five leave before the event
    for p in broken.roster[:3]:
        p.flags.add("benched")
    for j in range(3):
        broken.roster.append(pl(f"new{j}", 75))
    log = SeasonLog()
    order = run_tournament(t, clubs, RelationGraph(), 14, rng, log, Systems(development=False), 1, run.invites)
    names = {c.name for c in order}
    assert "C0" not in names and "C4" in names and len(order) == 4
    assert any("C0 не может принять инвайт" in x and "в составе 2" in x for x in log.management)
    assert "Masters" not in run.invites


def test_a_version_3_save_keeps_its_players_and_gets_contracts_that_end():
    from csmcore import save
    g = Game.new(seed=6, n_clubs=40)
    for _ in range(3):
        g.advance()
    m = g.sysm.market
    for k in ("journal", "stats", "next_contract_id", "short_since"):   # a pickle from before contracts end
        m.__dict__.pop(k, None)
    del g.run.__dict__["invites"]
    victim = next(iter(g.clubs[3].contracts.values()))
    victim.end_week = 1
    raw = save.dumps(g)
    g2 = save.loads(raw[:len(save.MAGIC)] + bytes([3]) + raw[len(save.MAGIC) + 1:])
    k = g2.clubs[3].contracts[victim.player]
    assert g2.week + 4 <= k.end_week <= g2.week + 52 and k.contract_id > 0
    assert g2.sysm.market.journal == [] and g2.run.invites == {}
    players = sum(len(c.roster) for c in g2.clubs)
    for _ in range(3):
        g2.advance()
    assert sum(len(c.roster) for c in g2.clubs) >= players - 3


def test_same_seed_same_contract_history():
    a, b = Game.new(seed=8, n_clubs=40), Game.new(seed=8, n_clubs=40)
    for _ in range(40):
        a.advance(), b.advance()
    assert a.sysm.market.journal == b.sysm.market.journal
    assert [(c.name, sorted(c.contracts)) for c in a.clubs] == [(c.name, sorted(c.contracts)) for c in b.clubs]


def test_api_shows_contracts_renews_and_explains_hiring():
    from csmcore import api
    api.new_game(4, 40)
    api.advance(2)
    g = api.G
    rows = api.contracts()
    assert rows and {"status", "weeks_left", "offer"} <= rows[0].keys()
    assert "рано" in api.renew(rows[-1]["name"], 1_000, 104) or rows[-1]["weeks_left"] <= 24
    p = g.club.roster[0]
    g.club.contracts[p.name].end_week = g.week + 5
    line = api.renew(p.name, 200_000, 104)
    assert p.name in line
    h = api.hiring()
    assert "journal" in h and "stats" in h
    assert "contract_status" in api.roster()[0]


def test_a_free_agent_nobody_signs_leaves_the_scene():
    from csmcore.legacy import Legacy
    m = Market()
    idle, fresh = pl("idle", age=22), pl("fresh", age=22)
    idle.free_since, fresh.free_since = 0, 100
    idle.flags.add("free_agent")
    m.free_agents += [idle, fresh]
    lg = Legacy()
    assert lg.quit_chance(fresh, 104) == 0.0 and lg.quit_chance(idle, 104) > 0.7
    class Half(random.Random):
        def random(self):
            return 0.5
    lines = lg.free_agents_end(m, 104, Half())
    assert idle not in m.free_agents and fresh in m.free_agents
    assert "free_agent" not in idle.flags and lines and lg.retired[-1].player is idle
