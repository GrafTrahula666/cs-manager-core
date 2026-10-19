"""Contracts that end: extension talks, leaving on a free, and a journal of every decision.

Before this module a contract's end week only stopped the salary: the player stayed in the roster
and played for free forever (by season 3, ~78% of rostered players in a 120-club world). Now:

    active --(RENEWAL_WINDOW weeks before the end)--> talks
    talks  --club wants him and he agrees--> a new Contract (renewed)
    talks  --club does not want him, or he says no--> leaving
    leaving --the club may still sell him, cheaper as the end nears--> sold
    leaving --end week passes--> free agent (a free transfer)

The manager's club gets the talks in the news and decides with api.renew / api.release; if he
does nothing, the assistant decides MANAGER_DEADLINE weeks before the end, as with other inbox
items. Every step goes to market.journal with the rule and the reasons that decided it.

The numbers here (window, terms, raises) are game hypotheses, not industry norms: real contract
terms are mostly private and depend on the governing law.
"""
from __future__ import annotations

import random

from . import economy
from .decisions import contract_acceptance
from .economy import Club, Contract

RENEWAL_WINDOW = 8       # weeks before the end when extension talks start
MANAGER_DEADLINE = 2     # the assistant decides for the manager this many weeks before the end
TERMS = (52, 78, 104)    # length of a new deal in weeks
JOURNAL_KEEP = 600


def note(market, week: int, club: str, player: str, kind: str, rule: str, reasons=()) -> dict:
    """One line of the contract journal; also counts the outcome in market.stats."""
    entry = {"week": week, "club": club, "player": player, "kind": kind, "rule": rule, "reasons": list(reasons)}
    market.journal.append(entry)
    if len(market.journal) > JOURNAL_KEEP:
        del market.journal[:len(market.journal) - JOURNAL_KEEP]
    market.stats[kind] += 1
    return entry


def make(market, player: str, salary: float, week: int, weeks: int, buyout_weeks: int = 104) -> Contract:
    market.next_contract_id += 1
    return Contract(player, salary, end_week=week + weeks, buyout=economy.buyout_for(salary, buyout_weeks),
                    start_week=week, contract_id=market.next_contract_id)


def release(club: Club, p, market, week: int, why: str, payout_months: float = 0.0) -> None:
    """The player leaves the club with no new club: to the free-agent pool, nobody vanishes."""
    k = club.contracts.pop(p.name, None)
    if k is not None and payout_months:
        club.book(week, "release", -k.salary_month * payout_months, p.name)
    club.roster.remove(p)
    club.former.append(p)
    p.former_clubs.add(club.name)
    p.flags.add("free_agent")
    p.flags.discard("transfer_requested")
    p.__dict__["free_since"] = week
    if p not in market.free_agents:
        market.free_agents.append(p)
    p.history.append(f"week {week}: ушёл из {club.name} ({why})")


def staying(club: Club) -> int:
    """Players who will still be here next season: a club replaces a leaver before he goes."""
    return sum(1 for p in club.roster if (k := club.contracts.get(p.name)) is None or k.status != "leaving")


def offer_salary(club: Club, p) -> float:
    from .market import TIER_SALARY_CAP, expected_salary
    return min(expected_salary(p), TIER_SALARY_CAP[club.tier])


def club_wants(club: Club, p, week: int) -> tuple[bool, str]:
    """Would the club extend him? A plain rule a manager could explain to the press."""
    lineup = club.lineup()
    if len(club.roster) <= 5 and p.age < 33:
        return True, "без него в составе меньше пяти"
    if p not in lineup:
        return False, "запасной: клуб не продлевает"
    if "transfer_requested" in p.flags:
        best = sorted(club.roster, key=lambda q: -q.overall())[:2]
        if p not in best:
            return False, "сам просил трансфер, а клуб не держится за него"
    salary = offer_salary(club, p)
    if salary * 6 > max(0.0, club.cash):
        return False, f"нет денег на полгода его зарплаты ({salary:,.0f}/мес)"
    return True, "игрок основы"


def offer(market, club: Club, p, salary: float, weeks: int, week: int, rng: random.Random, by: str) -> tuple[bool, str]:
    """Put an extension to the player; he decides. Returns (signed, line for the news)."""
    from .market import expected_salary
    old = club.contracts[p.name]
    new = make(market, p.name, salary, old.end_week, weeks)
    new.start_week = week
    v = contract_acceptance(p, new, expected_salary(p), club, staying=True)
    if not v.decide(rng.random()):
        old.status = "leaving"
        note(market, week, club.name, p.name, "renewal_refused", f"{by}: игрок отказал", v.reasons[:3])
        return False, f"{p.name} не стал продлевать контракт с {club.name}: " + "; ".join(v.reasons[:2])
    new.prize_share_player, new.win_bonus = old.prize_share_player, old.win_bonus
    club.contracts[p.name] = new
    p.history.append(f"week {week}: продлил контракт с {club.name} до недели {new.end_week}")
    note(market, week, club.name, p.name, "renewed", f"{by}: продлили на {weeks} нед.", v.reasons[:2])
    return True, f"{club.name} продлил контракт {p.name} ({salary:,.0f}/мес, до недели {new.end_week})"


def ai_decide(market, club: Club, p, week: int, rng: random.Random, by: str = "ai") -> str:
    wants, why = club_wants(club, p, week)
    if not wants:
        club.contracts[p.name].status = "leaving"
        note(market, week, club.name, p.name, "not_offered", f"{by}: {why}")
        return f"{club.name} не продлевает контракт {p.name}: {why}"
    return offer(market, club, p, offer_salary(club, p), rng.choice(TERMS), week, rng, by)[1]


def week(clubs: list[Club], market, week: int, rng: random.Random, manager_club: str | None = None) -> list[str]:
    """Expiries and extension talks for every club, once a week."""
    out: list[str] = []
    for club in clubs:
        mine = club.name == manager_club
        for p in sorted(club.roster, key=lambda q: q.name):
            c = club.contracts.get(p.name)
            if c is None or "legend_contract" in p.flags:
                continue
            if not c.contract_id:
                market.next_contract_id += 1
                c.contract_id = market.next_contract_id
            left = c.end_week - week
            if left < 0:
                release(club, p, market, week, "контракт закончился")
                note(market, week, club.name, p.name, "expired_left", "контракт закончился, ушёл свободным агентом")
                out.append(f"{p.name} ушёл из {club.name} свободным агентом: контракт закончился")
            elif left <= RENEWAL_WINDOW and c.status == "active":
                c.status = "talks"
                if mine:
                    out.append(f"{club.name}: контракт {p.name} заканчивается через {left} нед. — продлить или отпустить")
                else:
                    out.append(ai_decide(market, club, p, week, rng))
            elif mine and c.status == "talks" and left <= MANAGER_DEADLINE:
                out.append(f"{club.name}: решил ассистент: " + ai_decide(market, club, p, week, rng, by="assistant"))
    return out


def sale_fee(seller: Club, p, week: int) -> float:
    """A player who will leave on a free is worth less every week (cf. the m0NESY sale, H02)."""
    from .economy import market_value
    c = seller.contracts.get(p.name)
    if c is None:
        return market_value(p)
    if c.status == "leaving":
        return market_value(p) * max(0.1, min(1.0, (c.end_week - week) / 52))
    return market_value(p) * 1.3


ACADEMY_AFTER = 2   # weeks a club stays short with nobody it can afford before it promotes a junior


def academy_signing(club: Club, clubs: list[Club], market, week: int, rng: random.Random) -> str:
    """The fallback when the market has nobody a short club can pay or persuade: a junior from its
    own academy or the local scene, at a level the club's wage cap can hold (research p.47, P0)."""
    import math

    from .development import roll_potential
    from .generate import make_player
    from .market import TIER_SALARY_CAP, expected_salary
    from .worldgen import REGIONS, ROLES, Nicknames
    cap = TIER_SALARY_CAP[club.tier]
    affordable = 45 + 7.5 * math.log(cap * 0.8 / 600)          # inverse of market.expected_salary
    real = [p.overall() for p in club.roster]
    level = min(affordable, (sum(real) / len(real) - 4) if real else affordable)
    taken = {p.name for c in clubs for p in c.roster + c.former} | {p.name for p in market.free_agents}
    have = {p.role for p in club.roster}
    role = next((r for r in ROLES if r not in have), rng.choice(ROLES))
    p = make_player(Nicknames(rng, reserved=taken)(), level, rng, role, age=rng.randint(17, 19))
    p.country = rng.choice(REGIONS.get(club.region, REGIONS["EU"])[1])
    p.potential = roll_potential(p.overall(), p.age, rng)
    salary = min(expected_salary(p), cap)
    club.roster.append(p)
    club.contracts[p.name] = make(market, p.name, salary, week, 52)
    p.joined_week = week
    p.history.append(f"week {week}: первый контракт с {club.name} (из академии)")
    note(market, week, club.name, p.name, "academy", f"рынок не дал игрока {ACADEMY_AFTER} нед.",
         [f"уровень {p.overall():.0f}", f"{salary:,.0f}/мес"])
    return f"{club.name} подписал игрока из академии: {p.name} ({p.age}, {role})"
