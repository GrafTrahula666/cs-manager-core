"""The manager as a character, and one API for everything the manager can do.

Career (FM / CK3): every club has a manager with a reputation. Titles and beating the owner's
expectations raise it; getting sacked lowers it. Sacked managers enter a job pool; clubs that
fire someone hire the best available they can attract. The player's own manager lives the same
life: a sacking is not game over, it is the next chapter at a smaller club.

ManagerDesk is the single entry point a UI would call. Each method changes the world through the
existing systems and returns a readable outcome line.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import economy, promises as promises_mod
from .board import Owner
from .economy import Club
from .market import Market, expected_salary
from .player import Player
from .relations import RelationGraph
from .scouting import Scouting
from .secrets import Secrets
from .storylets import Fired, StoryEngine
from .talks import press_conference, team_talk
from .world import WeekPlan

TIER_PRESTIGE = {"tier3": 15, "tier2": 35, "tier1": 65, "super": 85}


@dataclass
class Manager:
    name: str
    reputation: float = 30.0
    club: str | None = None
    history: list[str] = field(default_factory=list)
    titles: int = 0
    sackings: int = 0

    def season_review(self, club: Club, owner: Owner | None, titles_won: int, season: int) -> None:
        delta = 4 * titles_won
        if owner is not None:
            delta += (owner.confidence - 50) / 10
        self.titles += titles_won
        self.reputation = max(0.0, min(100.0, self.reputation + delta))
        self.history.append(f"сезон {season}: {club.name}, место {club.rank}, титулов {titles_won}, репутация {self.reputation:.0f}")


@dataclass
class Careers:
    managers: dict[str, Manager] = field(default_factory=dict)   # club -> manager
    pool: list[Manager] = field(default_factory=list)             # unemployed
    log: list[str] = field(default_factory=list)

    def sack(self, club: Club, week: int) -> Manager | None:
        m = self.managers.pop(club.name, None)
        if m is None:
            return None
        m.sackings += 1
        m.reputation = max(0.0, m.reputation - 8)
        m.history.append(f"week {week}: уволен из {club.name}")
        m.club = None
        self.pool.append(m)
        self.log.append(f"week {week}: {m.name} уволен из {club.name}")
        return m

    def hire(self, club: Club, week: int, rng: random.Random) -> Manager:
        """Best reputation that still fits the club's prestige; unknown coach if nobody fits.
        A club never re-hires a manager it sacked."""
        prestige = TIER_PRESTIGE[club.tier] + club.brand / 5
        fits = [m for m in self.pool if m.reputation <= prestige + 10
                and not any(f"уволен из {club.name}" in h for h in m.history)]
        if fits:
            m = max(fits, key=lambda x: x.reputation)
            self.pool.remove(m)
        else:
            m = Manager(f"coach{rng.randrange(10_000)}", reputation=max(5.0, prestige - 20))
        m.club = club.name
        m.history.append(f"week {week}: возглавил {club.name}")
        self.managers[club.name] = m
        self.log.append(f"week {week}: {m.name} (репутация {m.reputation:.0f}) возглавил {club.name}")
        return m

    def job_offers(self, m: Manager, clubs: list[Club]) -> list[Club]:
        """Clubs without a manager that would take this one."""
        return [c for c in clubs if c.name not in self.managers
                and m.reputation <= TIER_PRESTIGE[c.tier] + c.brand / 5 + 10]


class ManagerDesk:
    """Everything the human manager can do, in one place."""

    def __init__(self, club: Club, clubs: list[Club], graph: RelationGraph, rng: random.Random,
                 market: Market | None = None, stories: StoryEngine | None = None,
                 secrets: Secrets | None = None, owner: Owner | None = None, rivals=None) -> None:
        self.club, self.clubs, self.graph, self.rng = club, clubs, graph, rng
        self.market, self.stories, self.secrets, self.owner, self.rivals = market, stories, secrets, owner, rivals
        self.scouting = Scouting(club)
        self.promises: list[promises_mod.Promise] = []
        self.plan = WeekPlan()

    # --- inbox ---
    def inbox(self) -> list[str]:
        items = []
        if self.stories:
            items += [f"событие: {f.title} → варианты: {', '.join(f.options)}" for f in self.stories.pending]
        if self.market:
            items += [f"предложение: {o.buyer.name} хочет {o.player.name} за {o.fee:,.0f}" for o in self.market.offers]
        if self.owner:
            items += [f"владелец: доверие {self.owner.confidence:.0f}"]
        return items

    # --- people ---
    def answer_event(self, f: Fired, option: int) -> list[str]:
        return self.stories.resolve(f, option, self.graph, self.rng).outcome

    def promise(self, p: Player, kind: str, deadline: int, week: int, value: float = 0.0) -> str:
        self.promises.append(promises_mod.make(p, kind, deadline, week, value))
        return f"Пообещал {p.name}: {kind} до недели {deadline}"

    def talk(self, tone: str, favourite: bool | None = None) -> list[str]:
        return [f"{r.player}: {r.text}" for r in team_talk(self.club, tone, favourite)]

    def press(self, question: str, answer: str, player: Player | None = None, opponent: Club | None = None) -> list[str]:
        return press_conference(self.club, question, answer, player, self.rivals, opponent, self.owner)

    def use_hook(self, p: Player, action: str, week: int) -> str:
        return self.secrets.use_hook(self.club, p, action, self.graph, week)

    # --- week ---
    def set_week(self, **kw) -> WeekPlan:
        self.plan = WeekPlan(**kw)
        return self.plan

    def scout(self, p: Player, weeks: float = 1.0):
        self.scouting.observe(p, weeks)
        return self.scouting.report(p)

    # --- market ---
    def sign_free_agent(self, p: Player, salary: float, week: int) -> str:
        from .market import Offer
        return self.market.complete(Offer(week, self.club, None, p, 0.0, salary), week, self.rng)

    def bid(self, p: Player, seller: Club, fee: float, salary: float, week: int) -> str:
        """AI seller accepts at or above 90% of market value (or the buyout); then the player decides."""
        from .market import Offer
        c = seller.contracts.get(p.name)
        ask = min(economy.market_value(p) * 0.9, c.buyout if c else float("inf"))
        if fee < ask:
            return f"{seller.name} отклонил {fee:,.0f} за {p.name} (хотят от {ask:,.0f})"
        return self.market.complete(Offer(week, self.club, seller, p, fee, salary), week, self.rng)

    def answer_offer(self, index: int, accept: bool, week: int) -> str:
        return self.market.answer(self.market.offers[index], accept, week, self.rng)

    def expected_salary(self, p: Player) -> float:
        return expected_salary(p)

    # --- money ---
    def loan(self, amount: float, week: int) -> str:
        economy.take_loan(self.club, amount, week)
        return f"Кредит {amount:,.0f} под {self.club.debt_rate_year:.0%}"

    def investor(self, amount: float, share: float, week: int) -> str:
        economy.take_investment(self.club, amount, share, week)
        return f"Инвестор купил {share:.0%} за {amount:,.0f}"

    def build(self, facility: str, week: int, cost: float = 150_000) -> str:
        lvl = self.club.facilities.get(facility, 0) + 1
        self.club.book(week, "build", -cost * lvl, f"{facility} ур.{lvl}")
        self.club.facilities[facility] = lvl
        return f"Построили {facility} уровня {lvl} за {cost * lvl:,.0f}"
