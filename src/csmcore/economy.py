"""Club economy: money flows, contracts, sponsors, tournaments, transfers.

All numbers are anchored to public esports data (see docs/core-design.md and
notes/ekonomika-igry.md in the project) and are placeholders for balancing.
Time unit: one week. Currency: USD-like game dollars.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .player import Player

WEEKS_PER_YEAR = 52
WEEKS_PER_MONTH = 52 / 12

# Club tiers, anchored to real ranges: tier-2/3 salaries $1-5k/month, tier-1 $5-80k,
# superstars ~$100-130k; Astralis 2021 revenue $11M.
TIERS = {
    "tier3": {"budget": (100_000, 400_000), "salary": (500, 2_000), "sponsors": (20_000, 100_000)},
    "tier2": {"budget": (400_000, 2_000_000), "salary": (2_000, 6_000), "sponsors": (100_000, 800_000)},
    "tier1": {"budget": (3_000_000, 15_000_000), "salary": (10_000, 80_000), "sponsors": (2_000_000, 8_000_000)},
    "super": {"budget": (15_000_000, 60_000_000), "salary": (40_000, 130_000), "sponsors": (8_000_000, 25_000_000)},
}

# Sponsor categories: base annual value multiplier and fan reputation effect per year.
# Betting/casino pays the most and costs reputation with part of the fanbase.
SPONSOR_CATEGORIES = {
    "hardware": {"mul": 1.0, "rep": 0.0},
    "energy": {"mul": 1.1, "rep": 0.0},
    "telecom": {"mul": 1.2, "rep": 0.0},
    "bank": {"mul": 1.3, "rep": 0.0},
    "auto": {"mul": 1.4, "rep": 0.0},
    "crypto": {"mul": 1.8, "rep": -2.0},
    "betting": {"mul": 2.5, "rep": -4.0},
}

# Major sticker royalties after the 2025-26 reform: share of token revenue by final place,
# champion 2.85% down to ~0.72%; team share split 50/50 with players.
STICKER_ROYALTY_TOP, STICKER_ROYALTY_BOTTOM = 0.0285, 0.0072


@dataclass
class Contract:
    player: str
    salary_month: float
    end_week: int
    buyout: float
    prize_share_player: float = 0.8  # players keep 80% of prize money by default
    signing_bonus: float = 0.0
    win_bonus: float = 0.0  # paid per tournament win


@dataclass
class Sponsor:
    name: str
    category: str
    annual: float
    end_week: int
    kpi_max_rank: int | None = None   # bonus if club ranked at or above this
    kpi_bonus: float = 0.0
    exclusive: bool = False


@dataclass
class LedgerLine:
    week: int
    item: str
    amount: float
    why: str = ""


@dataclass
class Club:
    name: str
    tier: str = "tier2"
    cash: float = 500_000.0
    debt: float = 0.0
    debt_rate_year: float = 0.12
    brand: float = 40.0      # 0-100
    fans: int = 50_000
    rank: int = 50           # world ranking position (VRS-like)
    rating_points: float = 0.0
    roster: list[Player] = field(default_factory=list)
    contracts: dict[str, Contract] = field(default_factory=dict)
    sponsors: list[Sponsor] = field(default_factory=list)
    staff_month: float = 15_000.0
    facilities: dict[str, int] = field(default_factory=dict)  # "bootcamp","academy","studio" -> level
    investor_share: float = 0.0
    ledger: list[LedgerLine] = field(default_factory=list)
    weeks_negative: int = 0

    def book(self, week: int, item: str, amount: float, why: str = "") -> None:
        self.cash += amount
        self.ledger.append(LedgerLine(week, item, round(amount, 2), why))

    def balance(self, since_week: int = 0) -> dict[str, float]:
        out: dict[str, float] = {}
        for line in self.ledger:
            if line.week >= since_week:
                out[line.item] = out.get(line.item, 0.0) + line.amount
        return out

    @property
    def bankrupt(self) -> bool:
        return self.weeks_negative >= 13


# Facility upkeep per month by level; benefits are read by the world tick.
FACILITY_UPKEEP = {"bootcamp": 8_000, "academy": 12_000, "studio": 6_000}


def merch_week(club: Club) -> float:
    """Merch + tickets: fans x conversion(brand) x average spend, spread over the year."""
    conversion = 0.01 + 0.04 * club.brand / 100
    return club.fans * conversion * 35.0 / WEEKS_PER_YEAR


def content_week(club: Club) -> float:
    """Streams/content: grows with fans, media-type players and a studio."""
    studio = 1.0 + 0.5 * club.facilities.get("studio", 0)
    stars = sum(p.mod("fan_gain")[1] for p in club.roster) / max(1, len(club.roster))
    return club.fans * 0.15 * studio * stars / WEEKS_PER_YEAR


def weekly_finances(club: Club, week: int) -> None:
    """One week of money flows. Every line goes to the ledger with a reason."""
    for p in club.roster:
        c = club.contracts.get(p.name)
        if c and week <= c.end_week:
            club.book(week, "salaries", -c.salary_month / WEEKS_PER_MONTH, p.name)
    club.book(week, "staff", -club.staff_month / WEEKS_PER_MONTH)
    for fac, lvl in club.facilities.items():
        if lvl:
            club.book(week, "facilities", -FACILITY_UPKEEP[fac] * lvl / WEEKS_PER_MONTH, fac)
    for s in list(club.sponsors):
        if week > s.end_week:
            club.sponsors.remove(s)
            continue
        club.book(week, "sponsors", s.annual / WEEKS_PER_YEAR, s.name)
        club.fans = max(0, int(club.fans * (1 + SPONSOR_CATEGORIES[s.category]["rep"] / 100 / WEEKS_PER_YEAR)))
    club.book(week, "merch", merch_week(club))
    club.book(week, "content", content_week(club))
    if club.debt:
        club.book(week, "interest", -club.debt * club.debt_rate_year / WEEKS_PER_YEAR)
    club.weeks_negative = club.weeks_negative + 1 if club.cash < 0 else 0


def sponsor_offer(club: Club, category: str, base: float | None = None) -> float:
    """Annual value a sponsor of this category offers the club."""
    lo, hi = TIERS[club.tier]["sponsors"]
    base = base if base is not None else math.sqrt(lo * hi) / 3
    rank_mul = 1.0 + max(0, 30 - club.rank) / 30           # top-30 clubs worth up to 2x
    star_mul = max([p.mod("sponsor_value")[1] for p in club.roster] or [1.0])
    return base * SPONSOR_CATEGORIES[category]["mul"] * (0.5 + club.brand / 50) * rank_mul * star_mul


def sponsor_kpi_check(club: Club, week: int) -> list[str]:
    """End-of-season style check: pay KPI bonuses or explain why not."""
    notes = []
    for s in club.sponsors:
        if s.kpi_max_rank is None:
            continue
        if club.rank <= s.kpi_max_rank:
            club.book(week, "sponsor_bonus", s.kpi_bonus, s.name)
            notes.append(f"{s.name}: KPI выполнен (место {club.rank} ≤ {s.kpi_max_rank}), бонус {s.kpi_bonus:,.0f}")
        else:
            notes.append(f"{s.name}: KPI провален (место {club.rank} > {s.kpi_max_rank}), бонуса нет")
    return notes


@dataclass
class Tournament:
    name: str
    tier: str                 # "S", "A", "B", "C"
    prize_pool: float
    distribution: list[float]  # share by place, 1st first
    max_rank_invite: int = 999  # VRS-like: invites go by ranking only
    lan: bool = True
    major: bool = False
    travel_cost: float = 0.0
    sticker_revenue: float = 0.0  # total token revenue if major

    def invited(self, club: Club) -> bool:
        return club.rank <= self.max_rank_invite


def award(club: Club, t: Tournament, place: int, week: int, field_size: int) -> float:
    """Pay prize money and, for a major, sticker royalties. Returns what the club itself kept."""
    kept = 0.0
    if t.travel_cost:
        club.book(week, "travel", -t.travel_cost, t.name)
    if place <= len(t.distribution):
        prize = t.prize_pool * t.distribution[place - 1]
        share = sum(club.contracts[p.name].prize_share_player for p in club.roster
                    if p.name in club.contracts) / max(1, len(club.roster))
        to_players = prize * share
        for p in club.roster:
            p.earnings += to_players / max(1, len(club.roster))
        club.book(week, "prizes", prize - to_players, f"{t.name} #{place}")
        kept += prize - to_players
        if place == 1:
            for p in club.roster:
                c = club.contracts.get(p.name)
                if c and c.win_bonus:
                    club.book(week, "win_bonuses", -c.win_bonus, p.name)
    if t.major and t.sticker_revenue:
        frac = (place - 1) / max(1, field_size - 1)
        royalty = STICKER_ROYALTY_TOP + (STICKER_ROYALTY_BOTTOM - STICKER_ROYALTY_TOP) * frac
        team_take = t.sticker_revenue * royalty
        for p in club.roster:
            p.earnings += team_take / 2 / max(1, len(club.roster))
        club.book(week, "stickers", team_take / 2, f"{t.name} royalty {royalty:.2%}")
        kept += team_take / 2
    club.fans += int(1500 * max(0, 9 - place) * (2 if t.tier == "S" else 1))
    return kept


def market_value(p: Player) -> float:
    """Transfer value. Peaks at 19-24, scales steeply with level and hype (fan_gain traits)."""
    level = p.overall()
    age_mul = 1.0 if 19 <= p.age <= 24 else max(0.3, 1 - 0.12 * abs(p.age - (19 if p.age < 19 else 24)))
    form_mul = 0.8 + 0.4 * p.s("form") / 100
    hype = p.mod("fan_gain")[1]
    return 2_000 * math.exp((level - 40) / 7.5) * age_mul * form_mul * (0.8 + 0.2 * hype)


def buyout_for(salary_month: float, weeks_left: int, mult: float = 2.0) -> float:
    """Real-world rule of thumb: buyout ~1.5-3 annual salaries, scaled by remaining term."""
    years_left = max(0.25, weeks_left / WEEKS_PER_YEAR)
    return salary_month * 12 * mult * min(1.5, years_left)


def transfer(buyer: Club, seller: Club, player: Player, fee: float, new: Contract, week: int,
             agent_pct: float = 0.05) -> None:
    buyer.book(week, "transfers_in", -fee, f"{player.name} из {seller.name}")
    buyer.book(week, "agents", -fee * agent_pct, player.name)
    if new.signing_bonus:
        buyer.book(week, "signing_bonus", -new.signing_bonus, player.name)
    seller.book(week, "transfers_out", fee, f"{player.name} в {buyer.name}")
    seller.roster.remove(player)
    seller.contracts.pop(player.name, None)
    buyer.roster.append(player)
    buyer.contracts[player.name] = new
    player.history.append(f"week {week}: {seller.name} -> {buyer.name} за {fee:,.0f}")


def take_investment(club: Club, amount: float, share: float, week: int) -> None:
    club.investor_share += share
    club.book(week, "investment", amount, f"{share:.0%} доли")


def take_loan(club: Club, amount: float, week: int, rate_year: float = 0.12) -> None:
    club.debt += amount
    club.debt_rate_year = rate_year
    club.book(week, "loan", amount)
