import random

from csmcore.board import Owner
from csmcore.economy import Club, Contract
from csmcore.manager import Careers, Manager, ManagerDesk
from csmcore.market import Market
from csmcore.player import STATS, Player
from csmcore.relations import RelationGraph
from csmcore.secrets import Secrets
from csmcore.storylets import StoryEngine, library


def p(name, level=65, **kw):
    return Player(name, {s: level for s in STATS}, **kw)


def test_secret_discovery_hook_and_leak():
    g, sec, rng = RelationGraph(), Secrets(), random.Random(0)
    gambler, mate = p("g"), p("m")
    mate.stats["analytical"] = 95
    g.set_pair("g", "m", friendship=95)
    home, rival = Club("Home", roster=[gambler, mate], scout_quality=90), Club("Rival", scout_quality=90)
    home.contracts["g"] = Contract("g", 10_000, 999, 0)
    s = sec.add(gambler, "gambling", 1)
    for w in range(1, 200):
        sec.discovery_week([home, rival], g, w, rng)
    assert {"m", "Home"} <= s.known_by
    gambler.flags.add("transfer_requested")
    out = sec.use_hook(home, gambler, "stay", g, 200)
    assert "transfer_requested" not in gambler.flags and "давлением" in out
    assert g.get("g", "m").resentment > 0
    sec.use_hook(home, gambler, "pay_cut", g, 201)
    assert home.contracts["g"].salary_month == 8_000
    line = sec.use_hook(home, gambler, "leak", g, 202)
    assert s.exposed and "Всплыл секрет" in line and not sec.hooks("Home")


def test_rival_leaks_only_when_hostile():
    g, sec = RelationGraph(), Secrets()
    victim = p("v")
    me, them = Club("Me"), Club("Them", roster=[victim], brand=60)
    s = sec.add(victim, "stimulants", 1)
    s.known_by.add("Me")
    assert sec.rival_leaks(me, them, 30, 5, g, random.Random(0)) == []
    leaks = []
    for i in range(30):
        leaks += sec.rival_leaks(me, them, 100, 5, g, random.Random(i))
    assert leaks and s.exposed and them.brand < 60


def test_events_leave_secrets():
    sec, g = Secrets(), RelationGraph()
    lib = {"stimulants_offer": {**library()["stimulants_offer"], "base": 0.9, "when": []}}
    eng = StoryEngine(lib)
    eng.secrets = sec
    club = Club("C", roster=[p("x")])
    eng.week([club], g, 1, random.Random(0))
    assert sec.of("x") and "secret:stimulants" in club.roster[0].flags


def test_manager_career_sack_and_rehire_elsewhere():
    car, rng = Careers(), random.Random(0)
    big, small = Club("Big", tier="tier1", brand=60), Club("Small", tier="tier3", brand=20)
    star = Manager("star", reputation=70)
    car.pool.append(star)
    assert car.hire(big, 1, rng) is star
    car.sack(big, 30)
    assert star.reputation == 62 and star in car.pool
    again = car.hire(big, 31, rng)
    assert again is not star                       # a club never re-hires whom it sacked
    assert small not in car.job_offers(star, [small])   # too famous for a tier-3 club
    m = Manager("m", reputation=30)
    m.season_review(big, Owner(confidence=90), titles_won=2, season=1)
    assert m.reputation == 30 + 8 + 4


def test_manager_desk_one_api():
    rng, g = random.Random(1), RelationGraph()
    roster = [p(f"x{i}") for i in range(5)]
    club = Club("Me", cash=5_000_000, roster=roster)
    fa = p("free", 70, personality={"ambition": 10, "money_focus": 50})
    seller_star = p("star", 72)
    seller = Club("S", roster=[seller_star])
    seller.contracts["star"] = Contract("star", 30_000, 200, 5_000_000)
    desk = ManagerDesk(club, [club, seller], g, rng, market=Market(free_agents=[fa]), owner=Owner())
    assert any("владелец" in i for i in desk.inbox())
    assert "свободного агента" in desk.sign_free_agent(fa, desk.expected_salary(fa) * 1.5, 1)
    assert "отклонил" in desk.bid(seller_star, seller, 1_000, 30_000, 2)
    assert desk.talk("calm") and desk.promise(roster[0], "role", 10, 2)
    report = desk.scout(seller_star, 3)
    assert report.knowledge > 0
    assert "уровня 1" in desk.build("academy", 3)
    assert "Кредит" in desk.loan(100_000, 3)
