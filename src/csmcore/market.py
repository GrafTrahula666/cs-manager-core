"""A living transfer market: AI clubs buy listed players and free agents, sell unhappy ones,
and send offers for the manager's players. Every deal still has to pass the player's own
decision (decisions.contract_acceptance), so personality shapes the market.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

from . import contracts, economy
from .decisions import contract_acceptance
from .economy import Club, Contract, LevelScale, scaled_level
from .player import Player

TIER_SALARY_CAP = {t: v["salary"][1] for t, v in economy.TIERS.items()}
ROSTER_MAX = 6          # AI clubs keep five and a substitute; the weakest extra is released
ASK_DROP_MONTH = 0.06   # a free agent asks 6% less for every month without a club...
ASK_FLOOR = 0.45        # ...down to 45% of what he thinks he is worth


# What a player expects per month at his level (on the world's starting scale). Anchors: the median
# level of each tier's rosters in a new 120-club world (51, 60, 69, 74) and the mean salary that
# world pays that tier (economy.TIERS ranges: 1250, 4000, 45000, 85000). Between anchors the
# salary is exponential in level; above the last one it grows slower, so the best of the world
# reach the superteam cap (130k) around 81. Not calibrated on real salaries: it keeps a player's
# expectations consistent with what the clubs of the world pay.
SALARY_CURVE = ((51.0, 1_250.0), (60.0, 4_000.0), (69.0, 45_000.0), (74.0, 85_000.0))
SALARY_TOP_SLOPE = 1 / 17   # log-salary per level above the last anchor


def _curve_log(level: float) -> float:
    pts = SALARY_CURVE
    if level >= pts[-1][0]:
        return math.log(pts[-1][1]) + (level - pts[-1][0]) * SALARY_TOP_SLOPE
    i = next(j for j in range(len(pts) - 1) if level < pts[j + 1][0])   # below the first anchor: its slope
    (a, x), (b, y) = pts[i], pts[i + 1]
    return math.log(x) + (level - a) * (math.log(y) - math.log(x)) / (b - a)


def level_for_salary(salary: float) -> float:
    """The inverse of the curve, without hype: the level that expects `salary`."""
    lo, hi = 0.0, 100.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _curve_log(mid) < math.log(salary) else (lo, mid)
    return (lo + hi) / 2


def expected_salary(p: Player, scale: LevelScale | None = None) -> float:
    """What a player thinks he is worth per month (SALARY_CURVE). With the market's `scale` the
    level is his place in the world (economy.LevelScale): when everybody gets better, pay stays."""
    hype = p.mod("fan_gain")[1]
    return math.exp(_curve_log(scaled_level(p, scale))) * (0.85 + 0.15 * hype)


def world_quantiles(clubs: list[Club]) -> list[float]:
    return economy.level_quantiles([p.overall() for c in clubs for p in c.roster])


def free_weeks(p: Player, week: int) -> float:
    """Weeks without a club. A teenager who never had one wants his first pro contract more
    than a big name: he counts as half a year without a team from the start."""
    since = p.__dict__.get("free_since")
    weeks = 0.0 if since is None else max(0, week - since)
    if since is not None and not p.former_clubs and p.age <= 19:
        weeks = max(weeks, 24.0)
    return weeks


def asking(p: Player, week: int, scale: LevelScale | None = None) -> float:
    """What a free agent settles for: months without a team lower his demands."""
    since = p.__dict__.get("free_since")
    if since is None:
        return expected_salary(p, scale)
    months = max(0, week - since) / 4
    return expected_salary(p, scale) * max(ASK_FLOOR, 1 - ASK_DROP_MONTH * months)


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
    journal: list[dict] = field(default_factory=list)   # contract and hiring decisions with their reasons
    stats: Counter = field(default_factory=Counter)      # outcome -> count, for the lab and the UI
    next_contract_id: int = 0
    short_since: dict[str, int] = field(default_factory=dict)   # club -> first week it had fewer than five
    level_ref: list[float] | None = None   # world_quantiles() when the market first looked at the world
    level_scale: LevelScale | None = None  # today's quantiles against level_ref: see expected_salary

    def rescale(self, clubs: list[Club]) -> LevelScale:
        now = world_quantiles(clubs)
        if self.level_ref is None:
            self.level_ref = now
        self.level_scale = LevelScale(self.level_ref, now)
        return self.level_scale

    def listed(self, clubs: list[Club], week: int = 0) -> list[tuple[Player, Club | None]]:
        out: list[tuple[Player, Club | None]] = [(p, None) for p in self.free_agents]
        for p in self.free_agents:
            p.__dict__.setdefault("free_since", week)
        for c in clubs:
            for p in c.roster:
                if "legend_contract" in p.flags:
                    continue
                k = c.contracts.get(p.name)
                if "transfer_requested" in p.flags or (k is not None and k.status == "leaving"):
                    out.append((p, c))
            for p in c.former:
                if "free_agent" in p.flags and p not in self.free_agents:
                    self.free_agents.append(p)
                    p.__dict__.setdefault("free_since", week)
                    out.append((p, None))
        return out

    def _need(self, club: Club) -> float:
        lineup = [p for p in club.roster if "benched" not in p.flags]
        if len(lineup) < 5 or contracts.staying(club) < 5:
            return 0.0  # any decent player helps
        return min(p.overall() for p in lineup)

    def week(self, clubs: list[Club], week: int, rng: random.Random, manager_club: str | None = None) -> list[str]:
        """AI clubs act every 4 weeks, at most one deal each; a club without five players looks
        every week and goes first. Clubs over ROSTER_MAX release their weakest bench player."""
        window = week % 4 == 0
        self.rescale(clubs)
        notes = self._trim_rosters(clubs, week, manager_club) if window else []
        short = [c for c in clubs if contracts.staying(c) < 5 and c.name != manager_club]
        for name in [n for n in self.short_since if n not in {c.name for c in short}]:
            del self.short_since[name]
        for c in short:
            self.short_since.setdefault(c.name, week)
        if not window and not short:
            return notes
        pool = self.listed(clubs, week)
        buyers = sorted(clubs if window else short, key=lambda c: (contracts.staying(c) >= 5, c.rank))
        buyers = [(b, extra) for b in buyers for extra in range(3 if contracts.staying(b) < 5 else 1)]
        for buyer, extra in buyers:   # a short club gets three tries: a refusal is not the end
            if buyer.name == manager_club or (buyer.cash < 0 and contracts.staying(buyer) >= 5):
                continue
            if extra and contracts.staying(buyer) >= 5:
                continue
            if contracts.staying(buyer) >= ROSTER_MAX:
                continue
            need = self._need(buyer)
            best = None
            why: Counter = Counter()   # why each candidate was passed over, for a short club's diagnosis
            for p, seller in pool:
                if seller is buyer:
                    continue
                if p.overall() < need + 2:
                    why["not_better"] += 1
                    continue
                if week - self.refused.get((p.name, buyer.name), -999) < 26:
                    why["refused_recently"] += 1
                    continue  # he said no recently
                ask = asking(p, week, self.level_scale) if seller is None else expected_salary(p, self.level_scale)
                if ask > TIER_SALARY_CAP[buyer.tier] * 1.1:
                    why["wage_gap"] += 1
                    continue  # cannot pay what he wants: do not waste an offer
                salary = min(ask * rng.uniform(0.9, 1.15), TIER_SALARY_CAP[buyer.tier])
                fee = 0.0 if seller is None else contracts.sale_fee(seller, p, week, self.level_scale)
                if fee + salary * (6 if contracts.staying(buyer) >= 5 else 2) > buyer.cash:
                    why["cash"] += 1
                    continue  # a club short of players signs on two months of wages
                guess = contract_acceptance(p, Contract(p.name, salary, week + 52, 0.0), ask, buyer,
                                            seller, relocation=bool(seller), free_weeks=free_weeks(p, week))
                if guess.p < 0.25:
                    why["expected_refusal"] += 1
                    continue  # scouts know he would say no (ambition, loyalty, home)
                gain = p.overall() - need
                if best is None or gain > best[0]:
                    best = (gain, p, seller, fee, salary)
            if not best:
                if contracts.staying(buyer) < 5 and not extra:
                    reasons = [f"{k}: {n}" for k, n in why.most_common(3)] or ["market_empty: на рынке никого"]
                    contracts.note(self, week, buyer.name, "", "hire_failed",
                                   f"остаются {contracts.staying(buyer)} из {len(buyer.roster)}, подходящего кандидата нет", reasons)
                    self.stats.update({f"hire_failed:{k}": n for k, n in why.items()})
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
        for c in short:   # still short after its tries and for weeks: the academy
            if len(c.roster) < 5 and week - self.short_since.get(c.name, week) >= contracts.ACADEMY_AFTER:
                notes.append(contracts.academy_signing(c, clubs, self, week, rng))
                if len(c.roster) >= 5:
                    self.short_since.pop(c.name, None)
        self.log += [f"week {week}: {n}" for n in notes]
        return notes

    def _trim_rosters(self, clubs: list[Club], week: int, manager_club: str | None) -> list[str]:
        notes = []
        for c in clubs:
            if c.name == manager_club or contracts.staying(c) <= ROSTER_MAX:
                continue
            lineup = c.lineup()
            spare = [p for p in c.roster if p not in lineup and "legend_contract" not in p.flags
                     and (c.contracts.get(p.name) is None or c.contracts[p.name].status != "leaving")]
            if not spare:
                continue
            p = min(spare, key=lambda q: q.overall())
            contracts.release(c, p, self, week, f"в составе было {len(c.roster)} игроков", payout_months=3)
            contracts.note(self, week, c.name, p.name, "released", f"в составе больше {ROSTER_MAX}", [])
            notes.append(f"{c.name} отпустил {p.name}: в составе лишний игрок")
        return notes

    def complete(self, o: Offer, week: int, rng: random.Random) -> str:
        """Seller agreed (or free agent); now the player decides."""
        p = o.player
        contract = contracts.make(self, p.name, o.salary, week, rng.choice(contracts.TERMS))
        v = contract_acceptance(p, contract, asking(p, week, self.level_scale) if o.seller is None else expected_salary(p, self.level_scale), o.buyer, o.seller,
                                free_weeks=free_weeks(p, week) if o.seller is None else 0.0,
                                relocation=bool(o.seller and o.seller.name != o.buyer.name))
        if not v.decide(rng.random()):
            o.status = "refused"
            self.refused[(p.name, o.buyer.name)] = week
            contracts.note(self, week, o.buyer.name, p.name, "signing_refused", "игрок отказал", v.reasons[:3])
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
            contracts.note(self, week, o.buyer.name, p.name, "signed_free", f"{o.salary:,.0f}/мес", v.reasons[:2])
            return f"{o.buyer.name} подписал свободного агента {p.name} ({o.salary:,.0f}/мес)"
        economy.transfer(o.buyer, o.seller, p, o.fee, contract, week)
        contracts.note(self, week, o.buyer.name, p.name, "transferred", f"из {o.seller.name} за {o.fee:,.0f}", v.reasons[:2])
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
