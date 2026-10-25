"""Founder-only onboarding. Reuses one existing tier-3 world slot and the normal market.

AI club simulation and the legacy manager career remain unchanged for old saves/tests.
New founder saves own their club permanently; no world-size increase or free players.
"""
from __future__ import annotations

from . import contracts, worldgen
from .market import asking

CAPITAL = 120_000
REGIONS = tuple(worldgen.REGIONS)


def bootstrap(clubs, systems, club_name: str, region: str, capital: int = CAPITAL) -> tuple[str, list[str]]:
    name = " ".join(club_name.split())
    if not 3 <= len(name) <= 40:
        raise ValueError("название клуба должно содержать 3–40 символов")
    if region not in REGIONS:
        raise ValueError("неизвестный регион клуба")
    if any(c.name.casefold() == name.casefold() for c in clubs):
        raise ValueError("клуб с таким названием уже существует")
    # Preserve the original 120-club ecosystem, including seeded AI rosters and rankings.
    available = [c for c in clubs if c.division == 3 and c.tier == "tier3"]
    if not available:
        available = [c for c in clubs if c.division == 3]
    if not available:
        raise ValueError("в этом мире пока нет третьего дивизиона")
    home = next((c for c in reversed(available) if c.region == region), available[-1])
    old_name = home.name
    # Three starters are real contracted players, the other two enter the common free-agent market.
    for p in home.roster[3:]:
        home.contracts.pop(p.name, None)
        p.flags.add("free_agent")
        p.__dict__["free_since"] = 0
        systems.market.free_agents.append(p)
    home.roster = home.roster[:3]
    home.name, home.region, home.tier = name, region, "tier3"
    home.brand, home.fans = 12.0, 1_500
    home.cash = 0.0
    home.book(0, "founder_capital", capital, "Капитал основателя клуба")
    owner = systems.owners.pop(old_name)
    owner.name = "Совет директоров"
    owner.founder_mode = True
    owner.confidence = 65.0
    owner.subsidy_year = 0.0  # no imaginary external owner financing a 100%-owned club
    systems.owners[name] = owner
    # Offer affordable, actual free agents; preserve unused candidates in the world.
    options = [p for p in systems.market.free_agents if asking(p, 0) <= capital / 12]
    options.sort(key=lambda p: (p.role not in ("rifler", "support"), asking(p, 0), p.name))
    return name, [p.name for p in options[:8]]


def candidates(game) -> list[dict]:
    if not getattr(game, "founder_mode", False) or game.week > 0:
        return []
    m = game.sysm.market
    return [
        {"name": p.name, "role": p.role, "age": p.age, "overall": round(p.overall(), 1),
         "salary": round(asking(p, game.week)), "country": p.country}
        for name in game.starter_candidates for p in m.free_agents if p.name == name
    ]


def sign(game, player_name: str) -> str:
    if not getattr(game, "founder_mode", False) or game.week != 0:
        raise ValueError("стартовый набор доступен только перед первой неделей")
    if len(game.club.roster) >= 5:
        raise ValueError("стартовая пятёрка уже собрана")
    if player_name not in game.starter_candidates:
        raise ValueError("кандидат не прошёл стартовый отбор")
    market = game.sysm.market
    p = next((q for q in market.free_agents if q.name == player_name), None)
    if p is None:
        raise ValueError("кандидат уже подписал другой контракт")
    salary = asking(p, game.week)
    if salary * 6 > game.club.cash:
        raise ValueError("не хватает резерва на шесть месяцев зарплаты")
    c = contracts.make(market, p.name, salary, game.week, 52)
    market.free_agents.remove(p)
    p.flags.discard("free_agent")
    p.__dict__.pop("free_since", None)
    p.joined_week = game.week
    p.history.append(f"week {game.week}: стартовый контракт с {game.club.name}")
    game.club.roster.append(p)
    game.club.contracts[p.name] = c
    contracts.note(market, game.week, game.club.name, p.name, "signed_free",
                   "предварительно согласованный стартовый контракт", [f"{salary:,.0f}/мес"])
    return f"{p.name} подписан на сезон: {salary:,.0f}/мес. В составе {len(game.club.roster)}/5."
