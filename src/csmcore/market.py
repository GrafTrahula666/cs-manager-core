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


def expected_salary(p: Player) -> float:
    """What a player thinks he is worth per month: exponential in level, like real salaries
    (tier-3 ~$1k, solid tier-1 ~$20-40k, superstar ~$100k+)."""
    hype = p.mod("fan_gain")[1]
    return 600 * math.exp((p.overall() - 45) / 7.5) * (0.85 + 0.15 * hype)


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

    def listed(self, clubs: list[Club]) -> list[tuple[Player, Club | None]]:
        out: list[tuple[Player, Club | None]] = [(p, None) for p in self.free_agents]
        for c in clubs:
            for p in c.roster:
                if "transfer_requested" in p.flags:
                    out.append((p, c))
            for p in c.former:
                if "free_agent" in p.flags and p not in self.free_agents:
                    self.free_agents.append(p)
                    out.append((p, None))
        return out

    def _need(self, club: Club) -> float:
        lineup = [p for p in club.roster if "benched" not in p.flags]
        if len(lineup) < 5:
            return 0.0  # any decent player helps
        return min(p.overall() for p in lineup)

    def week(self, clubs: list[Club], week: int, rng: random.Random, manager_club: str | None = None) -> list[str]:
        """AI clubs act every 4 weeks, at most one deal each."""
        if week % 4:
            return []
        notes = []
        pool = self.listed(clubs)
        for buyer in sorted(clubs, key=lambda c: c.rank):
            if buyer.name == manager_club or buyer.cash < 0:
                continue
            need = self._need(buyer)
            best = None
            for p, seller in pool:
                if seller is buyer or p.overall() < need + 2:
                    continue
                if week - self.refused.get((p.name, buyer.name), -999) < 26:
                    continue  # he said no recently
                salary = min(expected_salary(p) * rng.uniform(0.9, 1.15), TIER_SALARY_CAP[buyer.tier])
                fee = 0.0 if seller is None else market_value(p) * (1.3 if seller.contracts.get(p.name) else 1.0)
                if fee + salary * 6 > buyer.cash:
                    continue
                gain = p.overall() - need
                if best is None or gain > best[0]:
                    best = (gain, p, seller, fee, salary)
            if not best:
                continue
            _, p, seller, fee, salary = best
            offer = Offer(week, buyer, seller, p, fee, salary)
            if seller is not None and seller.name == manager_club:
                self.offers.append(offer)
                notes.append(f"{buyer.name} предлагает {fee:,.0f} за {p.name}: ждёт решения менеджера")
                pool = [(q, s) for q, s in pool if q is not p]   # one bid per player per window
                continue
            note = self.complete(offer, week, rng)
            notes.append(note)
            pool = [(q, s) for q, s in pool if q is not p]
        self.log += [f"week {week}: {n}" for n in notes]
        return notes

    def complete(self, o: Offer, week: int, rng: random.Random) -> str:
        """Seller agreed (or free agent); now the player decides."""
        p = o.player
        contract = Contract(p.name, o.salary, end_week=week + rng.choice([52, 78, 104]),
                            buyout=economy.buyout_for(o.salary, 104))
        v = contract_acceptance(p, contract, expected_salary(p), o.buyer, o.seller,
                                relocation=bool(o.seller and o.seller.name != o.buyer.name))
        if not v.decide(rng.random()):
            o.status = "refused"
            self.refused[(p.name, o.buyer.name)] = week
            return f"{p.name} отказал {o.buyer.name}: " + "; ".join(v.reasons[:2])
        o.status = "done"
        p.flags.discard("transfer_requested")
        p.flags.discard("free_agent")
        p.joined_week = week
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
            o.player.state["morale"] = max(0.0, o.player.s("morale") - 10 * o.player.p("ambition") / 50)
            return f"Предложение {o.buyer.name} за {o.player.name} отклонено"
        return self.complete(o, week, rng)
