"""Run one season of a small fictional world and print money, results and emergent events.

    python scripts/demo_season.py [seed]
"""
from __future__ import annotations

import random
import sys

from csmcore import economy
from csmcore.economy import Club, Contract, Sponsor, Tournament
from csmcore.generate import concept_examples, make_player
from csmcore.relations import RelationGraph
from csmcore.season import run_season

ROLES = ["igl", "awp", "entry", "rifler", "support"]


def build_world(seed: int):
    rng = random.Random(seed)
    graph = RelationGraph()
    clubs = []
    tiers = ["super", "tier1", "tier1", "tier1", "tier2", "tier2", "tier2", "tier3"]
    for i, tier in enumerate(tiers):
        level = {"super": 72, "tier1": 66, "tier2": 58, "tier3": 50}[tier]
        lo, hi = economy.TIERS[tier]["salary"]
        club = Club(f"Club{i + 1}", tier=tier, cash=economy.TIERS[tier]["budget"][0] / 2,
                    brand={"super": 80, "tier1": 60, "tier2": 40, "tier3": 20}[tier],
                    fans={"super": 2_000_000, "tier1": 600_000, "tier2": 120_000, "tier3": 20_000}[tier],
                    rank=i + 1, rating_points=100 - i * 10, staff_month=hi * 2)
        roster = [make_player(f"c{i + 1}p{j}", level, rng, ROLES[j]) for j in range(5)]
        if i == 1:  # the concept's example trio plays for Club2
            ex = concept_examples()
            roster[0], roster[1], roster[2] = ex["north"], ex["sable"], ex["vanta"]
            graph.set_pair("vanta", "sable", irritation=40, role_rivalry=50)
        for p in roster:
            sal = rng.uniform(lo, hi)
            club.contracts[p.name] = Contract(p.name, sal, end_week=rng.randint(30, 150),
                                              buyout=economy.buyout_for(sal, 100))
        club.roster = roster
        mid = economy.TIERS[tier]["sponsors"][0]
        club.sponsors = [Sponsor("HW Corp", "hardware", mid * 0.4, 52),
                         Sponsor("BetX" if i % 2 else "BankY", "betting" if i % 2 else "bank", mid * 0.6, 52,
                                 kpi_max_rank=4, kpi_bonus=mid * 0.1)]
        clubs.append(club)
    calendar = {
        6: Tournament("Online Cup", "C", 50_000, [0.5, 0.25, 0.125, 0.125], max_rank_invite=8, lan=False),
        14: Tournament("Spring Masters", "A", 400_000, [0.4, 0.2, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05], lan=True,
                       travel_cost=30_000),
        24: Tournament("Major", "S", 1_250_000, [0.4, 0.14, 0.07, 0.07, 0.04, 0.04, 0.04, 0.04], lan=True,
                       major=True, sticker_revenue=8_000_000, travel_cost=40_000),
        36: Tournament("Autumn League", "B", 150_000, [0.4, 0.2, 0.1, 0.1], max_rank_invite=4, lan=False),
        46: Tournament("World Final", "S", 1_000_000, [0.5, 0.2, 0.15, 0.15], max_rank_invite=4, lan=True,
                       travel_cost=40_000),
    }
    return clubs, graph, calendar


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    clubs, graph, calendar = build_world(seed)
    log = run_season(clubs, graph, calendar, seed)
    for line in log.results[-8:]:
        print(line)
    print("\nFinal ranking and money:")
    for c in sorted(clubs, key=lambda c: c.rank):
        bal = c.balance()
        top = ", ".join(f"{k} {v / 1000:+,.0f}k" for k, v in sorted(bal.items(), key=lambda kv: -abs(kv[1]))[:4])
        print(f"#{c.rank} {c.name:7} {c.tier:6} cash {c.cash / 1000:9,.0f}k  fans {c.fans:>9,}  | {top}")
    print(f"\n{len(log.events)} emergent events. First five with causes:")
    for e in log.events[:5]:
        print(f"week {e.week}: {e.text}\n   why: {'; '.join(e.causes)}")


if __name__ == "__main__":
    main()
