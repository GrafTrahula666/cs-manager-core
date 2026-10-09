"""One playable game: the world, the human manager's club and the week-by-week clock.

    g = Game.new(seed=7)              # 120-club world, manager takes the concept trio's club
    news = g.advance()                # one week; returns what the manager should see
    g.desk.talk("calm")               # everything the manager does goes through ManagerDesk
    save.save(g, "career.sav"); g = save.load("career.sav")

The game never blocks on the manager: unanswered life events and transfer offers are settled by
the assistant after PATIENCE_WEEKS, as in Football Manager when you ignore your inbox.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import economy, worldgen
from .economy import Club
from .manager import ManagerDesk
from .season import SeasonRun, Systems, season_begin, season_finish, season_week

PATIENCE_WEEKS = 2
LEDGER_KEEP_WEEKS = 104   # older ledger lines are dropped so saves stay small


@dataclass
class WeekNews:
    week: int
    season: int
    lines: list[str] = field(default_factory=list)


class Game:
    def __init__(self, seed: int, clubs: list[Club], graph, calendar, systems: Systems, club_name: str,
                 manager_name: str = "Вы") -> None:
        self.seed, self.clubs, self.graph, self.calendar, self.sysm = seed, clubs, graph, calendar, systems
        self.club_name = club_name
        self.season = 1
        self.rng = random.Random(seed + 5)
        systems.manager_club = club_name
        self.desk = ManagerDesk(self.club, clubs, graph, self.rng, systems.market, systems.stories,
                                systems.secrets, (systems.owners or {}).get(club_name), systems.rivalries)
        systems.promises = {club_name: self.desk.promises}
        self.history: list[WeekNews] = []
        self.run: SeasonRun = season_begin(clubs, self._season_seed(), systems, 1, 0)
        self.manager_name = manager_name
        if systems.careers is not None:   # the human gets the job instead of an AI coach
            m = systems.careers.managers.get(club_name)
            if m is not None:
                m.name, m.reputation = manager_name, 30.0
        self._seen = self._counts()

    # ---- construction ----
    @classmethod
    def new(cls, seed: int = 1, n_clubs: int = 120, club: str | None = None, director: str = "cassandra",
            manager_name: str = "Вы") -> "Game":
        clubs, graph, cal, sysm, home = worldgen.generate(seed, n_clubs, director)
        return cls(seed, clubs, graph, cal, sysm, club or home, manager_name)

    # ---- lookups ----
    @property
    def club(self) -> Club:
        return next(c for c in self.clubs if c.name == self.club_name)

    @property
    def week(self) -> int:
        """Absolute week (1 = first week of season 1)."""
        return self.run.start_week + self.run.wk

    def find_player(self, name: str):
        for c in self.clubs:
            for p in c.roster:
                if p.name == name:
                    return p, c
        if self.sysm.market:
            for p in self.sysm.market.free_agents:
                if p.name == name:
                    return p, None
        return None, None

    def next_events(self, n: int = 3) -> list[tuple[int, str, bool]]:
        """Upcoming tournaments: (season week, name, is my club invited)."""
        out = []
        for wk in sorted(self.calendar):
            if wk <= self.run.wk:
                continue
            ts = self.calendar[wk] if isinstance(self.calendar[wk], list) else [self.calendar[wk]]
            for t in ts:
                if t.region is None or t.region == self.club.region:
                    out.append((wk, t.name, t.invited(self.club)))
        return out[:n]

    # ---- the clock ----
    def _season_seed(self) -> int:
        return self.seed * 1000 + self.season

    def _counts(self) -> tuple[int, int, int, int]:
        log = self.run.log
        return (len(log.results), len(log.stories), len(log.management), len(self.sysm.chronicle.entries) if self.sysm.chronicle else 0)

    def advance(self) -> WeekNews:
        """Play one week. Returns the news that concern the manager plus world headlines."""
        self._assistant_decides()
        plans = {self.club_name: self.desk.plan}
        season_week(self.run, self.clubs, self.graph, self.calendar, self.sysm, plans)
        news = WeekNews(self.week, self.season, self._collect())
        self.desk.plan = type(self.desk.plan)()   # plans last one week
        if self.run.wk >= economy.WEEKS_PER_YEAR:
            season_finish(self.run, self.clubs, self.sysm)
            news.lines += self._new_season()
        self._trim()
        self._seen = self._counts()
        self.history.append(news)
        self.history = self.history[-60:]
        return news

    def _collect(self) -> list[str]:
        r0, s0, m0, c0 = self._seen
        log, me = self.run.log, self.club_name
        out = [f"матч: {r.split(': ', 1)[-1]} ({r.split(' R')[0].split(' ', 2)[-1]})"
               for r in log.results[r0:] if me in r]
        for f in log.stories[s0:]:
            if f.club.name == me:
                tail = " — ждёт вашего решения" if f in (self.sysm.stories.pending if self.sysm.stories else []) else \
                    (f": {'; '.join(f.outcome[:2])}" if f.outcome else "")
                out.append(f"история: {f.title}{tail}")
        out += [f"клуб: {m}" for m in log.management[m0:] if me in m]
        if self.sysm.chronicle:
            out += [f"клуб: {e.text}" for e in self.sysm.chronicle.entries[c0:]
                    if e.kind in ("title", "rivalry") and me in e.text]
            out += [f"мир: {e.text}" for e in self.sysm.chronicle.entries[c0:]
                    if e.kind in ("title", "patch", "board") and me not in e.text
                    and ("лига" not in e.text or self.club.region in e.text)][:6]
        return out

    def _trim(self) -> None:
        """The week's news are already collected: drop raw logs so saves stay small."""
        log = self.run.log
        log.events.clear(), log.results.clear(), log.stories.clear(), log.management.clear()
        for holder in (self.sysm.market, self.sysm.secrets, self.sysm.careers):
            if holder is not None and len(holder.log) > 200:
                holder.log = holder.log[-200:]
        for o in (self.sysm.owners or {}).values():
            o.log = o.log[-50:]
        director = self.sysm.stories.director if self.sysm.stories else None
        if director is not None and director._randy:
            director._randy = {k: v for k, v in director._randy.items() if k[1] >= self.week}
        if self.week % 13 == 0:
            for c in self.clubs:   # AI clubs only need the recent months for their decisions
                keep = LEDGER_KEEP_WEEKS if c.name == self.club_name else 13
                c.ledger = [x for x in c.ledger if x.week > self.week - keep]
            riv = self.sysm.rivalries
            if riv is not None:
                riv.duels = {k: v for k, v in riv.duels.items() if v >= 6 or k[0] in riv.titles or k[1] in riv.nemesis}
                for r in riv.clubs.values():
                    r.memories = r.memories[-6:]

    def _assistant_decides(self) -> None:
        st, mk = self.sysm.stories, self.sysm.market
        if st:
            for f in list(st.pending):
                if self.week - f.week >= PATIENCE_WEEKS:
                    st.resolve(f, st.ai_choice(f, self.graph, self.rng), self.graph, self.rng)
                    f.outcome.insert(0, "решил ассистент")
        if mk:
            for o in list(mk.offers):
                if self.week - o.week >= PATIENCE_WEEKS:
                    mk.answer(o, False, self.week, self.rng)

    def _new_season(self) -> list[str]:
        """Season rollover: ranking points decay, expired sponsors are replaced, owners set new
        targets, old ledger lines are trimmed."""
        lines = [f"Сезон {self.season} завершён. {self.club_name}: место {self.club.rank}"]
        self.season += 1
        start = self.run.start_week + self.run.wk
        rng = random.Random(self._season_seed() + 77)
        for c in self.clubs:
            c.rating_points *= 0.5
            c.sponsors = [s for s in c.sponsors if s.end_week > start]
            if len(c.sponsors) < 2:
                c.sponsors += worldgen.new_sponsors(c, rng, start, economy.TIERS[c.tier]["sponsors"][0])[len(c.sponsors):]
            if self.sysm.owners and c.name in self.sysm.owners:
                self.sysm.owners[c.name].objectives = []
        if self.sysm.stories:
            self.sysm.stories.last_fired = {k: w for k, w in self.sysm.stories.last_fired.items() if w > start - 104}
        lines += self._world_changes(start, rng)
        self.run = season_begin(self.clubs, self._season_seed(), self.sysm, self.season, start)
        owner = self.desk.owner
        if owner and owner.objectives:
            lines.append("Цели владельца: " + "; ".join(o.text for o in owner.objectives))
        return lines

    def _world_changes(self, week: int, rng: random.Random) -> list[str]:
        """Closures, investor rebrands, the superteam, wonderkids: see worldlife.py."""
        from . import worldlife
        from .season import rerank
        names = {p.name for c in self.clubs for p in c.roster + c.former}
        if self.sysm.market:
            names |= {p.name for p in self.sysm.market.free_agents}
        if self.sysm.legacy:
            names |= {r.player.name for r in self.sysm.legacy.retired}
        nick = worldgen.Nicknames(rng, reserved=names)
        notes = worldlife.close_bankrupt(self.clubs, self.sysm, week, rng, nick, self.club_name)
        notes += worldlife.investor_rebrand(self.clubs, self.sysm, week, rng, self.club_name)
        notes += worldlife.superteam(self.clubs, self.sysm, self.season, week, rng, nick, self.club_name)
        rerank(self.clubs)
        if self.sysm.legacy:
            fresh = sorted(self.sysm.legacy.born[-self.sysm.talents_per_season:], key=lambda q: -q.potential)
            for p in [q for q in fresh if q.potential >= 84][:2]:   # only the real wonderkids make the news
                notes.append(f"Появился вундеркинд {p.name} ({p.age} лет, {p.role}): скауты в восторге")
        if self.sysm.chronicle:
            for n in notes:
                self.sysm.chronicle.add(self.season, week, "board", n)
        return [f"мир: {n}" for n in notes]

    # ---- manager career ----
    @property
    def sacked(self) -> bool:
        """The owner fired you: the club now has another manager."""
        m = self.sysm.careers.managers.get(self.club_name) if self.sysm.careers else None
        return m is not None and m.name != self.manager_name

    def me(self):
        """Your Manager record (reputation, titles, history), employed or not."""
        careers = self.sysm.careers
        if careers is None:
            return None
        return next((m for m in list(careers.managers.values()) + careers.pool if m.name == self.manager_name), None)

    def job_offers(self) -> list[Club]:
        """After a sacking: clubs whose prestige fits your reputation (their AI coach makes way)."""
        from .manager import TIER_PRESTIGE
        m = self.me()
        rep = m.reputation if m else 20.0
        fits = [c for c in self.clubs if c.name != self.club_name and rep <= TIER_PRESTIGE[c.tier] + c.brand / 5 + 10]
        return sorted(fits, key=lambda c: c.rank)[:5]

    def take_job(self, club_name: str) -> str:
        careers, m = self.sysm.careers, self.me()
        club = next(c for c in self.clubs if c.name == club_name)
        old = careers.managers.pop(club_name, None)
        if old is not None:
            old.club = None
            careers.pool.append(old)
        if m in careers.pool:
            careers.pool.remove(m)
        m.club = club_name
        m.history.append(f"week {self.week}: возглавил {club_name}")
        careers.managers[club_name] = m
        self.club_name = self.sysm.manager_club = club_name
        owner = (self.sysm.owners or {}).get(club_name)
        if owner:
            owner.fired, owner.confidence = False, 55.0
            owner.set_objectives(club)
        self.desk = ManagerDesk(club, self.clubs, self.graph, self.rng, self.sysm.market, self.sysm.stories,
                                self.sysm.secrets, owner, self.sysm.rivalries)
        self.sysm.promises = {club_name: self.desk.promises}
        return f"Вы возглавили {club_name} ({club.tier}, место {club.rank})"
