"""The world changes between seasons: orgs die, new ones appear, legends come and go.

* A club that ended the season bankrupt closes. Its players become free agents, and a new
  tier-3 org takes its slot in the same region.
* Sometimes an investor buys a small club, renames it and pours money in (tier-3 -> tier-2).
* Very rarely, after something special happened (a dynasty winning 4+ titles in a season, a
  95+ player, a fixed match in the world), a mysterious superteam appears: five players at
  97-99. It crushes everyone for three seasons and then disappears without a word.
"""
from __future__ import annotations

import random

from . import economy
from .board import Owner
from .economy import Club
from .generate import make_player
from .worldgen import NAME_A, NAME_B, REGIONS, ROLES, _contracts, _owner, make_club

SUPERTEAM_NAMES = ["Project Omega", "The Syndicate", "Aurora Prime", "Null Division", "Black Monolith", "Zero Hour"]
SUPERTEAM_SEASONS = 3
SUPERTEAM_BASE = 0.04       # per season, from season 3
SUPERTEAM_TRIGGERED = 0.30  # after a special event


def _new_name(rng: random.Random, taken: set[str]) -> str:
    for _ in range(500):
        nm = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
        if nm not in taken:
            return nm
    return f"Club {len(taken) + 1}"


def _free(club: Club, market, week: int) -> None:
    for p in club.roster:
        p.former_clubs.add(club.name)
        p.flags.add("free_agent")
        p.flags.discard("benched")
        p.history.append(f"week {week}: {club.name} закрылся, стал свободным агентом")
        if market is not None:
            market.free_agents.append(p)


MAX_CLOSURES = 2   # per season; the other broke clubs get one more year from their owner


def close_bankrupt(clubs: list[Club], sysm, week: int, rng: random.Random, nick, keep: str) -> list[str]:
    notes, taken = [], {c.name for c in clubs}
    broke = [i for i, c in enumerate(clubs)
             if c.name != keep and (c.bankrupt or c.cash < -economy.TIERS[c.tier]["budget"][0])]
    broke.sort(key=lambda i: clubs[i].cash)
    for n, i in enumerate(broke):
        c = clubs[i]
        owner = sysm.owners.get(c.name) if sysm.owners is not None else None
        if n >= MAX_CLOSURES or (owner is not None and rng.random() < owner.ambition / 200):
            c.cash = economy.TIERS[c.tier]["budget"][0] * 0.1   # the owner pays the debts, once more
            c.weeks_negative = 0
            continue
        _free(c, sysm.market, week)
        new = make_club(_new_name(rng, taken), "tier3", c.region, len(clubs), 0.0, rng, nick, start_week=week)
        taken.add(new.name)
        clubs[i] = new
        if sysm.owners is not None:
            sysm.owners.pop(c.name, None)
            sysm.owners[new.name] = _owner(new, rng)
        if sysm.careers is not None:
            m = sysm.careers.managers.pop(c.name, None)
            if m is not None:
                m.club = None
                sysm.careers.pool.append(m)
        notes.append(f"{c.name} закрылся после банкротства, игроки ушли в свободные агенты. "
                     f"В регионе {c.region} появился новый клуб {new.name}")
    return notes


def investor_rebrand(clubs: list[Club], sysm, week: int, rng: random.Random, keep: str) -> list[str]:
    if rng.random() > 0.5:
        return []
    small = [c for c in clubs if c.tier == "tier3" and c.name != keep and c.cash > 0]
    if not small:
        return []
    c = rng.choice(small)
    old = c.name
    c.name = _new_name(rng, {x.name for x in clubs})
    c.tier = "tier2"
    c.cash += rng.uniform(500_000, 1_500_000)
    c.brand = min(100.0, c.brand + 10)
    c.staff_month = economy.TIERS["tier2"]["salary"][1] * 2
    for p in c.roster:
        p.history.append(f"week {week}: клуб {old} купил инвестор и переименовал в {c.name}")
    if sysm.owners is not None:
        o = sysm.owners.pop(old, None) or _owner(c, rng)
        o.name, o.ambition = f"Инвестор {c.name}", max(o.ambition, 75.0)
        o.subsidy_year *= 2
        o.objectives = []
        sysm.owners[c.name] = o
    if sysm.careers is not None and old in sysm.careers.managers:
        m = sysm.careers.managers.pop(old)
        m.club = c.name
        sysm.careers.managers[c.name] = m
    return [f"Инвестор купил {old} и переименовал в {c.name}: деньги, амбиции и tier-2"]


def _special_happened(clubs: list[Club], sysm, season: int) -> str | None:
    ch = sysm.chronicle
    if ch is not None:
        gone = {n for n in SUPERTEAM_NAMES}
        for club, titles in ch.titles.items():
            if club in gone:
                continue
            if sum(f"(сезон {season})" in t for t in titles) >= 4:
                return f"династия {club}"
    for c in clubs:
        if "fixed_match" in c.flags:
            return "договорной матч"
        for p in c.roster:
            if p.overall() >= 95:
                return f"феномен {p.name}"
    return None


def superteam(clubs: list[Club], sysm, season: int, week: int, rng: random.Random, nick, keep: str) -> list[str]:
    notes = []
    for i, c in enumerate(list(clubs)):    # the old one leaves when its time is up
        until = next((int(f.split(":")[1]) for f in c.flags if f.startswith("superteam_until:")), None)
        if until is not None and season > until:
            for p in c.roster:
                p.history.append(f"week {week}: {c.name} исчез, легенда ушла в тень")
            new = make_club(_new_name(rng, {x.name for x in clubs}), "tier3", c.region, len(clubs), 0.0, rng, nick,
                            start_week=week)
            clubs[i] = new
            if sysm.owners is not None:
                sysm.owners.pop(c.name, None)
                sysm.owners[new.name] = _owner(new, rng)
            if sysm.careers is not None:
                sysm.careers.managers.pop(c.name, None)
            notes.append(f"{c.name} исчез так же внезапно, как появился. Его игроков больше никто не видел")
    if notes:
        sysm.__dict__["superteam_gone"] = season
    if season < 3 or any(f.startswith("superteam_until:") for c in clubs for f in c.flags):
        return notes
    if season - sysm.__dict__.get("superteam_gone", -99) < 3:   # the world gets a few normal seasons first
        return notes
    why = _special_happened(clubs, sysm, season - 1)
    if rng.random() >= max(SUPERTEAM_BASE, SUPERTEAM_TRIGGERED if why else 0.0):
        return notes
    taken = {c.name for c in clubs}
    name = next((n for n in SUPERTEAM_NAMES if n not in taken), _new_name(rng, taken))
    region = rng.choice(list(REGIONS))
    club = Club(name, tier="super", region=region, cash=40_000_000, brand=70.0, fans=1_000_000, rank=1,
                rating_points=max(c.rating_points for c in clubs) + 500, staff_month=300_000,
                coach_quality=95.0, scout_quality=95.0)
    club.flags.add(f"superteam_until:{season + SUPERTEAM_SEASONS - 1}")
    for role in ROLES:
        p = make_player(nick(), 99, rng, role, age=rng.randint(21, 25))
        p.country = rng.choice(REGIONS[region][1])
        p.potential = 100.0
        p.personality["loyalty"] = 100.0
        p.personality["ambition"] = 30.0
        p.flags.update({"star", "legend_contract"})   # nobody can buy them
        p.fame = 40.0
        club.roster.append(p)
    _contracts(club, club.roster, rng, week)
    worst = max((c for c in clubs if c.name != keep), key=lambda c: c.rank)
    clubs[clubs.index(worst)] = club
    _free(worst, sysm.market, week)
    if sysm.owners is not None:
        sysm.owners.pop(worst.name, None)
        o = Owner(f"Неизвестный владелец {name}", patience=100, ambition=100, money_focus=0)
        o.subsidy_year = 10_000_000
        sysm.owners[name] = o
    if sysm.careers is not None:
        sysm.careers.managers.pop(worst.name, None)
    reason = f" (после того как случилось: {why})" if why else ""
    notes.append(f"Из ниоткуда появился {name}{reason}: пятеро игроков уровня 95–98. "
                 f"Никто не знает, кто за ними стоит. {worst.name} уступил им место")
    return notes
