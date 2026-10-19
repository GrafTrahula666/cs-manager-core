"""A living transfer market: AI clubs buy listed players and free agents, sell unhappy ones,
and send offers for the manager's players. Every deal still has to pass the player's own
decision (decisions.contract_acceptance), so personality shapes the market.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import economy
from .decisions import contract_acceptance
from .economy import Club, Contract, market_value
from .player import Player

TIER_SALARY_CAP = {t: v["salary"][1] for t, v in economy.TIERS.items()}
ROSTER_MAX = 6          # AI clubs keep five and a substitute; the weakest extra is released
ASK_DROP_MONTH = 0.06   # a free agent asks 6% less for every month without a club...
ASK_FLOOR = 0.45        # ...down to 45% of what he thinks he is worth


def expected_salary(p: Player) -> float:
    """What a player thinks he is worth per month: exponential in level, like real salaries
    (tier-3 ~$1k, solid tier-1 ~$20-40k, superstar ~$100k+)."""
    hype = p.mod("fan_gain")[1]
    return 600 * math.exp((p.overall() - 45) / 7.5) * (0.85 + 0.15 * hype)


def free_weeks(p: Player, week: int) -> float:
    """Weeks without a club. A teenager who never had one wants his first pro contract more
    than a big name: he counts as half a year without a team from the start."""
    since = p.__dict__.get("free_since")
    weeks = 0.0 if since is None else max(0, week - since)
    if since is not None and not p.former_clubs and p.age <= 19:
        weeks = max(weeks, 24.0)
    return weeks


def asking(p: Player, week: int) -> float:
    """What a free agent settles for: months without a team lower his demands."""
    since = p.__dict__.get("free_since")
    if since is None:
        return expected_salary(p)
    months = max(0, week - since) / 4
    return expected_salary(p) * max(ASK_FLOOR, 1 - ASK_DROP_MONTH * months)


@dataclass
class Offer:
    week: int
    buyer: Club
    seller: Club | None
    player: Player
    fee: float
    salary: float
    status: str = "open"


@dataclass
class Market:
    free_agents: list[Player] = field(default_factory=list)
    offers: list[Offer] = field(default_factory=list)    # offers waiting for the manager
    log: list[str] = field(default_factory=list)
    refused: dict[tuple[str, str], int] = field(default_factory=dict)  # (player, club) -> week

    def listed(self, clubs: list[Club], week: int = 0) -> list[tuple[Player, Club | None]]:
        out: list[tuple[Player, Club | None]] = [(p, None) for p in self.free_agents]
        for p in self.free_agents:
            p.__dict__.setdefault("free_since", week)
        for c in clubs:
            for p in c.roster:
                if "transfer_requested" in p.flags and "legend_contract" not in p.flags:
                    out.append((p, c))
            for p in c.former:
                if "free_agent" in p.flags and p not in self.free_agents:
                    self.free_agents.append(p)
                    p.__dict__.setdefault("free_since", week)
                    out.append((p, None))
        return out

    def _need(self, club: Club) -> float:
        lineup = [p for p in club.roster if "benched" not in p.flags]
        if len(lineup) < 5:
            return 0.0  # any decent player helps
        return min(p.overall() for p in lineup)

    def week(self, clubs: list[Club], week: int, rng: random.Random, manager_club: str | None = None) -> list[str]:
        """AI clubs act every 4 weeks, at most one deal each; a club without five players looks
        every week and goes first. Clubs over ROSTER_MAX release their weakest bench player."""
        window = week % 4 == 0
        notes = self._trim_rosters(clubs, week, manager_club) if window else []
        short = [c for c in clubs if len(c.roster) < 5 and c.name != manager_club]
        if not window and not short:
            return notes
        pool = self.listed(clubs, week)
        buyers = sorted(clubs if window else short, key=lambda c: (len(c.roster) >= 5, c.rank))
        buyers = [(b, extra) for b in buyers for extra in range(3 if len(b.roster) < 5 else 1)]
        for buyer, extra in buyers:   # a short club gets three tries: a refusal is not the end
            if buyer.name == manager_club or (buyer.cash < 0 and len(buyer.roster) >= 5):
                continue
            if extra and len(buyer.roster) >= 5:
                continue
            if len(buyer.roster) >= ROSTER_MAX:
                continue
            need = self._need(buyer)
            best = None
            for p, seller in pool:
                if seller is buyer or p.overall() < need + 2:
                    continue
                if week - self.refused.get((p.name, buyer.name), -999) < 26:
                    continue  # he said no recently
                ask = asking(p, week) if seller is None else expected_salary(p)
                if ask > TIER_SALARY_CAP[buyer.tier] * 1.1:
                    continue  # cannot pay what he wants: do not waste an offer
                salary = min(ask * rng.uniform(0.9, 1.15), TIER_SALARY_CAP[buyer.tier])
                fee = 0.0 if seller is None else market_value(p) * (1.3 if seller.contracts.get(p.name) else 1.0)
                if fee + salary * (6 if len(buyer.roster) >= 5 else 2) > buyer.cash:
                    continue  # a club short of players signs on two months of wages
                guess = contract_acceptance(p, Contract(p.name, salary, week + 52, 0.0), ask, buyer,
                                            seller, relocation=bool(seller), free_weeks=free_weeks(p, week))
                if guess.p < 0.25:
                    continue  # scouts know he would say no (ambition, loyalty, home)
                gain = p.overall() - need
                if best is None or gain > best[0]:
                    best = (gain, p, seller, fee, salary)
            if not best:
                continue
            _, p, seller, fee, salary = best
            offer = Offer(week, buyer, seller, p, fee, salary)
            if seller is not None and seller.name == manager_club:
                if week - self.refused.get((p.name, "<manager>"), -999) < 12:
                    continue  # the manager just said no for him: the market waits a few months
                self.refused[(p.name, "<manager>")] = week
                self.offers.append(offer)
                notes.append(f"{buyer.name} предлагает {fee:,.0f} за {p.name}: ждёт решения менеджера")
                pool = [(q, s) for q, s in pool if q is not p]   # one bid per player per window
                continue
            note = self.complete(offer, week, rng)
            notes.append(note)
            pool = [(q, s) for q, s in pool if q is not p]
        self.log += [f"week {week}: {n}" for n in notes]
        return notes

    def _trim_rosters(self, clubs: list[Club], week: int, manager_club: str | None) -> list[str]:
        notes = []
        for c in clubs:
            if c.name == manager_club or len(c.roster) <= ROSTER_MAX:
                continue
            lineup = c.lineup()
            spare = [p for p in c.roster if p not in lineup and "legend_contract" not in p.flags]
            if not spare:
                continue
            p = min(spare, key=lambda q: q.overall())
            k = c.contracts.pop(p.name, None)
            if k is not None:
                c.book(week, "release", -3 * k.salary_month, p.name)
            c.roster.remove(p)
            c.former.append(p)
            p.former_clubs.add(c.name)
            p.flags.add("free_agent")
            p.flags.discard("transfer_requested")
            p.__dict__["free_since"] = week
            self.free_agents.append(p)
            p.history.append(f"week {week}: {c.name} отпустил его, в составе было {len(c.roster) + 1} игроков")
            notes.append(f"{c.name} отпустил {p.name}: в составе лишний игрок")
        return notes

    def complete(self, o: Offer, week: int, rng: random.Random) -> str:
        """Seller agreed (or free agent); now the player decides."""
        p = o.player
        contract = Contract(p.name, o.salary, end_week=week + rng.choice([52, 78, 104]),
                            buyout=economy.buyout_for(o.salary, 104))
        v = contract_acceptance(p, contract, asking(p, week) if o.seller is None else expected_salary(p), o.buyer, o.seller,
                                free_weeks=free_weeks(p, week) if o.seller is None else 0.0,
                                relocation=bool(o.seller and o.seller.name != o.buyer.name))
        if not v.decide(rng.random()):
            o.status = "refused"
            self.refused[(p.name, o.buyer.name)] = week
            return f"{p.name} отказал {o.buyer.name}: " + "; ".join(v.reasons[:2])
        o.status = "done"
        p.flags.discard("transfer_requested")
        p.flags.discard("free_agent")
        p.joined_week = week
        p.__dict__.pop("free_since", None)
        if o.seller is None:
            if p in self.free_agents:
                self.free_agents.remove(p)
            o.buyer.roster.append(p)
            o.buyer.contracts[p.name] = contract
            p.history.append(f"week {week}: свободный агент подписал {o.buyer.name}")
            return f"{o.buyer.name} подписал свободного агента {p.name} ({o.salary:,.0f}/мес)"
        economy.transfer(o.buyer, o.seller, p, o.fee, contract, week)
        return f"{p.name}: {o.seller.name} → {o.buyer.name} за {o.fee:,.0f} ({o.salary:,.0f}/мес)"

    def answer(self, o: Offer, accept: bool, week: int, rng: random.Random) -> str:
        """Manager's answer to an offer for one of their players."""
        self.offers.remove(o)
        if not accept:
            o.status = "rejected"
            self.refused[(o.player.name, o.buyer.name)] = week   # this buyer will not ask again soon
            o.player.state["morale"] = max(0.0, o.player.s("morale") - 10 * o.player.p("ambition") / 50)
            return f"Предложение {o.buyer.name} за {o.player.name} отклонено"
        return self.complete(o, week, rng)
