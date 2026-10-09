"""Procedural world: 100-150 fictional clubs across six regions, four economic tiers, rosters
with potentials, owners, sponsors and a season calendar sized for a big world.

The concept's example trio (vanta, north, sable) always plays for one tier-1 club, which is
the default club for the human manager.
"""
from __future__ import annotations

import random

from . import economy
from .board import Owner
from .chronicle import Chronicle
from .development import roll_potential
from .director import Director
from .economy import Club, Contract, Sponsor, Tournament
from .generate import SUFFIX, SYL, Nicknames, concept_examples, make_player  # noqa: F401
from .legacy import Legacy
from .manager import Careers
from .market import Market
from .meta import Meta
from .relations import RelationGraph
from .rivalry import Rivalries
from .secrets import Secrets
from .season import Systems
from .storylets import StoryEngine

# Region share of clubs and the countries players come from (fictional clubs, real countries).
REGIONS = {
    "EU": (0.38, ["DE", "FR", "DK", "SE", "PL", "ES", "FI", "NO", "CZ", "PT", "BE", "NL"]),
    "CIS": (0.20, ["RU", "UA", "KZ", "BY", "UZ"]),
    "NA": (0.12, ["US", "CA"]),
    "SA": (0.12, ["BR", "AR", "CL"]),
    "Asia": (0.11, ["CN", "MN", "KR", "JP", "TR"]),
    "OCE": (0.07, ["AU", "NZ"]),
}
TIER_SHARE = [("super", 0.035), ("tier1", 0.13), ("tier2", 0.33), ("tier3", 1.0)]   # last one takes the rest
TIER_LEVEL = {"super": 72, "tier1": 66, "tier2": 58, "tier3": 50}
TIER_BRAND = {"super": 80, "tier1": 60, "tier2": 38, "tier3": 18}
TIER_FANS = {"super": 2_000_000, "tier1": 500_000, "tier2": 100_000, "tier3": 15_000}
ROLES = ["igl", "awp", "entry", "rifler", "support"]

NAME_A = ["Nova", "Iron", "Red", "Black", "Storm", "Frost", "Neon", "Apex", "Volt", "Ghost", "Rogue", "Titan",
          "Crimson", "Silent", "Wild", "Phantom", "Lunar", "Solar", "Arctic", "Venom", "Obsidian", "Golden",
          "Steel", "Shadow", "Ember", "Static", "Quantum", "Atlas", "Zenith", "Echo"]
NAME_B = ["Wolves", "Esports", "Gaming", "Hawks", "Dragons", "Kings", "Unit", "Squad", "Legion", "Five", "Riders",
          "Vipers", "Owls", "Bears", "Foxes", "Ravens", "Sharks", "Lynx", "Club", "Collective"]
def _names(rng: random.Random, n: int) -> list[str]:
    out: list[str] = []
    used: set[str] = set()
    while len(out) < n:
        nm = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
        if nm not in used:
            used.add(nm)
            out.append(nm)
    return out


def _dist(n: int) -> list[float]:
    """Prize share by place for an n-team bracket: 1st 40%, 2nd 20%, semis 20%, then the rest."""
    groups = [(1, 0.40), (1, 0.20), (2, 0.20), (4, 0.12), (8, 0.08)]
    out: list[float] = []
    for size, part in groups:
        if len(out) + size > n:
            break
        out += [part / size] * size
    total = sum(out)
    return [x / total for x in out]


def calendar(regions=REGIONS) -> dict[int, list[Tournament]]:
    """A season for 100-150 clubs: elite S/A events for the top 16, pro events for the top 32,
    regional leagues for everyone outside the elite, open online cups for ranks 33+."""
    cal: dict[int, list[Tournament]] = {}

    def add(week: int, t: Tournament) -> None:
        cal.setdefault(week, []).append(t)

    for w, name in ((4, "Зимняя лига"), (20, "Весенняя лига"), (40, "Осенняя лига")):
        for r in regions:
            add(w, Tournament(f"{name} {r}", "B", 120_000, _dist(8), min_rank_invite=17, region=r, lan=False))
    for w, name in ((8, "Pro Series I"), (30, "Pro Series II")):
        add(w, Tournament(name, "A", 300_000, _dist(8), max_rank_invite=32, lan=True, travel_cost=20_000))
    for w, name in ((10, "Open Cup I"), (28, "Open Cup II"), (50, "Open Cup III")):
        add(w, Tournament(name, "C", 60_000, _dist(8), min_rank_invite=33, lan=False))
    add(14, Tournament("Spring Masters", "A", 500_000, _dist(8), max_rank_invite=16, lan=True, travel_cost=30_000))
    add(24, Tournament("Major", "S", 1_250_000, _dist(16), max_rank_invite=16, lan=True, major=True,
                       sticker_revenue=8_000_000, travel_cost=40_000))
    add(36, Tournament("Autumn Masters", "A", 500_000, _dist(8), max_rank_invite=16, lan=True, travel_cost=30_000))
    add(46, Tournament("World Final", "S", 1_000_000, _dist(8), max_rank_invite=8, lan=True, travel_cost=40_000))
    return cal


def _contracts(club: Club, players, rng: random.Random, start_week: int = 0) -> None:
    lo, hi = economy.TIERS[club.tier]["salary"]
    for p in players:
        sal = rng.uniform(lo, hi)
        club.contracts[p.name] = Contract(p.name, sal, end_week=start_week + rng.randint(30, 150),
                                          buyout=economy.buyout_for(sal, 100))
        p.joined_week = start_week - rng.randint(0, 150)


def make_club(name: str, tier: str, region: str, rank: int, rating_points: float, rng: random.Random,
              nick, start_week: int = 0, level: float | None = None) -> Club:
    """One club with a five-man roster, contracts and two sponsors."""
    level = TIER_LEVEL[tier] + rng.uniform(-3, 3) if level is None else level
    _, hi = economy.TIERS[tier]["salary"]
    b_lo, b_hi = economy.TIERS[tier]["budget"]
    club = Club(name, tier=tier, region=region, cash=rng.uniform(b_lo, (b_lo + b_hi) / 2) / 2,
                brand=max(5.0, min(95.0, TIER_BRAND[tier] + rng.uniform(-8, 8))),
                fans=int(TIER_FANS[tier] * rng.uniform(0.6, 1.5)), rank=rank,
                rating_points=rating_points, staff_month=hi * 2,
                coach_quality=max(20.0, min(90.0, rng.gauss(30 + level / 2, 8))),
                scout_quality=max(20.0, min(90.0, rng.gauss(30 + level / 2, 8))))
    countries = REGIONS[region][1]
    for role in ROLES:
        p = make_player(nick(), level, rng, role)
        p.country = rng.choice(countries)
        p.potential = roll_potential(p.overall(), p.age, rng)
        club.roster.append(p)
    _contracts(club, club.roster, rng, start_week)
    club.sponsors = new_sponsors(club, rng, start_week, economy.TIERS[tier]["sponsors"][0])
    return club


def generate(seed: int = 1, n_clubs: int = 120, director: str = "cassandra"):
    """Build clubs, relation graph, calendar and a full Systems bundle. Returns
    (clubs, graph, calendar, systems, home_club_name)."""
    if not 8 <= n_clubs <= 400:
        raise ValueError("n_clubs should be 8..400")
    rng = random.Random(seed)
    graph = RelationGraph()
    examples = concept_examples()
    nick = Nicknames(rng, reserved=examples)
    names = _names(rng, n_clubs)
    region_list = list(REGIONS)
    weights = [REGIONS[r][0] for r in region_list]

    tiers: list[str] = []
    for tier, share in TIER_SHARE:
        k = n_clubs - len(tiers) if tier == "tier3" else max(1, round(n_clubs * share))
        tiers += [tier] * k
    clubs: list[Club] = []
    home = None
    for i, (name, tier) in enumerate(zip(names, tiers)):
        region = rng.choices(region_list, weights)[0] if i else "EU"
        club = make_club(name, tier, region, i + 1, (n_clubs - i) * 10.0, rng, nick)
        roster = club.roster
        if home is None and tier == "tier1":   # the concept's trio
            home = club
            club.region = "EU"
            for q in roster[:3]:
                club.contracts.pop(q.name, None)
            roster[0], roster[1], roster[2] = examples["north"], examples["sable"], examples["vanta"]
            graph.set_pair("vanta", "sable", irritation=40, role_rivalry=50)
            _contracts(club, roster[:3], rng)
        clubs.append(club)

    free_agents = [make_player(nick(), rng.uniform(46, 64), rng, ROLES[i % 5]) for i in range(n_clubs // 3)]
    for p in free_agents:
        p.potential = roll_potential(p.overall(), p.age, rng)
    systems = Systems(
        stories=StoryEngine(director=Director(director)),
        market=Market(free_agents=free_agents),
        owners={c.name: _owner(c, rng) for c in clubs},
        rivalries=Rivalries(), meta=Meta(), chronicle=Chronicle(), legacy=Legacy(),
        secrets=Secrets(), careers=Careers(), talents_per_season=max(6, n_clubs // 3),
    )
    return clubs, graph, calendar(), systems, home.name


# Yearly owner money by tier: below the super tier almost every org runs at a loss and lives on
# its investors (see notes/ekonomika-igry.md). A money-focused owner pays less.
OWNER_SUBSIDY = {"super": (0, 0), "tier1": (600_000, 1_500_000), "tier2": (100_000, 250_000), "tier3": (50_000, 110_000)}


def _owner(club: Club, rng: random.Random) -> Owner:
    o = Owner(f"Владелец {club.name}", patience=rng.uniform(20, 80), ambition=rng.uniform(30, 90),
              money_focus=rng.uniform(20, 80))
    lo, hi = OWNER_SUBSIDY[club.tier]
    o.subsidy_year = rng.uniform(lo, hi) * (1.2 - o.money_focus / 100)
    return o


SPONSOR_BRANDS = {"hardware": "Kernel", "energy": "Bolt", "telecom": "Linkr", "bank": "Vault Bank",
                  "auto": "Motive", "crypto": "Chainz", "betting": "LuckyBet",
                  "luxury": "Aurum Watches"}


def new_sponsors(club: Club, rng: random.Random, week: int, base: float) -> list[Sponsor]:
    """Two deals for a year: a safe one and a riskier one; bigger brands get more."""
    safe = rng.choice(["hardware", "energy", "telecom", "bank", "auto"])
    risky = rng.choice(["hardware", "energy", "crypto", "betting", "telecom", "luxury"])
    scale = 0.6 + club.brand / 100
    return [Sponsor(SPONSOR_BRANDS[safe], safe, base * 0.5 * scale, week + 52),
            Sponsor(SPONSOR_BRANDS[risky], risky, base * 0.5 * scale * economy.SPONSOR_CATEGORIES[risky]["mul"] / 1.5,
                    week + 52, kpi_max_rank=max(1, club.rank // 2), kpi_bonus=base * 0.1)]
