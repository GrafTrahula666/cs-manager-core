"""Named club staff (LIVING CLUB stage B, LC-018/019/021): a person with an ID, a market, a contract,
a workplace and one real result.

Vertical slice: a tactical analyst is found on the staff market, hired on a contract, assigned to the
analytics centre and, every week, studies the players of a chosen rival club. The result is the manager's
own scouting knowledge of those players (ranges that shrink), so the effect is the information the manager
sees, never a win probability. Other phase-1 roles can be hired and paid but have no effect yet (shown so).

Money: every salary is a `Club.book` line (item "staff_named"). The old aggregate `staff_month` stays as the
general-staff baseline and is not touched, so nothing is paid twice. The staff world has its own random
generator: it never draws from the world's, so match results do not depend on it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import livingdata
from .economy import WEEKS_PER_MONTH

WORLD_SIZE = 420                            # specialists alive in the world at the start (hypothesis)
EMPLOYED_SHARE = 0.45                       # share working for AI clubs at the start; they are not hirable until the contract ends
ROLE_WEIGHT = {"head_coach": 3, "assistant_coach": 4, "tactical_analyst": 5, "psychologist": 4, "scout": 5, "head_hunter": 2,
               "sports_director": 2, "academy_head": 2, "youth_coach": 3, "media_manager": 3, "streaming_specialist": 3,
               "physio": 3, "finance_director": 2, "commercial_director": 2}
WIRED_ROLES = {"tactical_analyst"}          # roles whose work changes something in the game today
POACH_WEEKS = 4                             # every 4th week AI clubs sign a few free specialists
POACH_COUNT = 6
SEASON_INTAKE = 25                          # new young specialists a season; those over RETIRE_AGE retire
RETIRE_AGE = 62
COUNTRIES = ["RU", "UA", "KZ", "BY", "PL", "SE", "DK", "FR", "DE", "BR", "US", "CN", "FI", "CZ", "ES"]
# Personality traits of staff. `analysis` is the only wired effect today (the analyst's dossier speed); the rest are shown but do nothing yet.
TRAITS = {
    "methodical": ("Методичный", "аккуратно ведёт досье", "медленно принимает решения", 0.10),
    "perfectionist": ("Дотошный", "ничего не пропускает", "требует больше времени и денег", 0.15),
    "innovator": ("Новатор", "предлагает нестандартные ходы", "не любит рутину", 0.05),
    "old_school": ("Старой школы", "авторитет у ветеранов", "не доверяет новым методам", -0.05),
    "lazy": ("Лентяй", "не требует многого", "тянет со сроками", -0.10),
    "mentor": ("Наставник по натуре", "молодёжь тянется к нему", "мало внимания взрослым", 0.0),
    "loyal": ("Верный", "не уйдёт к конкурентам", "тяжело расстаётся с командой", 0.0),
    "careerist": ("Карьерист", "тянет результат", "уйдёт за лучшим предложением", 0.0),
    "charismatic": ("Харизматичный", "заряжает людей", "любит быть на виду", 0.0),
    "volatile": ("Вспыльчивый", "честно говорит, что думает", "конфликтует с игроками", 0.0),
    "calm": ("Невозмутимый", "держит спокойствие в кризис", "реагирует с задержкой", 0.0),
    "thrifty": ("Бережливый", "экономит бюджет", "скупится на нужное", 0.0),
}
TIER_PAY = {"super": 1.3, "tier1": 1.0, "tier2": 0.7, "tier3": 0.45}
MONTHS = (6, 12, 24)
ACCEPT_RATIO = 0.95                         # offers below this share of the expectation are refused
FIRE_SHARE = 0.5                            # releasing early costs this share of the remaining salary
FIRST = ["Ян", "Марк", "Лео", "Нико", "Артём", "Тимур", "Сэм", "Влад", "Эрик", "Дэн", "Ким", "Ося", "Макс", "Рич", "Олле", "Ильяс"]
LAST = ["Ковач", "Бергман", "Мартинес", "Орлов", "Лундгрен", "Фишер", "Сато", "Новак", "Ким", "Дюран", "Хоффман", "Левин", "Альмейда", "Росс"]


def roles() -> dict:
    return {r["id"]: r for r in livingdata.load("staff_roles")["roles"]}


@dataclass
class Staffer:
    id: str
    name: str
    role: str
    skill: int                 # 20-95, the main number
    age: int
    loyalty: int               # 0-100: hint of how he reacts to a renewal offer
    expectation: float         # monthly salary he asks, already scaled by the club's tier
    listed_week: int = 0
    country: str = "RU"
    traits: list[str] = field(default_factory=list)
    experience: int = 0        # years in the job
    history: list[str] = field(default_factory=list)   # earlier clubs
    employer: str | None = None    # an AI club he works for: not hirable until employed_until
    employed_until: int = 0
    club: str | None = None
    salary: float = 0.0        # monthly, under contract
    start_week: int = 0
    end_week: int = 0
    workplace: str | None = None        # facility id he is assigned to
    log: list[str] = field(default_factory=list)


class StaffWorld:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(f"staff:{seed}")
        self.members: dict[str, Staffer] = {}
        self.counter = 0
        self.target: str | None = None          # club the analyst is studying
        self.log: list[str] = []

    # ---- the world of people ----
    def _make(self, role: str, week: int, tier: str, young: bool = False) -> Staffer:
        r = self.rng
        self.counter += 1
        age = r.randint(22, 28) if young else max(23, min(62, int(r.gauss(40, 9))))
        skill = max(20, min(95, int(r.gauss(48 + (0 if young else (age - 30) * 0.5), 15))))
        base = roles()[role]["salary_tier1"]
        ask = round(base * (0.5 + skill / 100) * TIER_PAY.get(tier, 1.0) / 50) * 50
        m = Staffer(f"S{self.counter:04d}", f"{r.choice(FIRST)} {r.choice(LAST)}", role, skill, age, r.randint(20, 90), float(ask), listed_week=week)
        m.country = r.choice(COUNTRIES)
        m.traits = r.sample(sorted(TRAITS), 2)
        m.experience = max(0, age - 22 - r.randint(0, 6)) if not young else r.randint(0, 3)
        return m

    def seed_market(self, game) -> None:
        r = self.rng
        pool = [role for role, w in ROLE_WEIGHT.items() for _ in range(w)]
        ai = [c.name for c in game.clubs if c.name != game.club_name]
        for _ in range(WORLD_SIZE):
            m = self._make(r.choice(pool), game.week, game.club.tier)
            for c in r.sample(ai, min(len(ai), r.randint(1 if m.experience >= 3 else 0, 3))):
                m.history.append(f"{c} ({r.randint(1, max(1, m.experience or 1))} г.)")
            if ai and r.random() < EMPLOYED_SHARE:
                m.employer, m.employed_until = r.choice(ai), game.week + r.randint(8, 150)
            self.members[m.id] = m

    def free(self) -> list[Staffer]:
        return [m for m in self.members.values() if m.club is None and m.employer is None]

    def candidates(self) -> list[Staffer]:
        return sorted(self.free(), key=lambda m: (list(roles()).index(m.role), -m.skill))

    def search(self, role: str | None = None, q: str = "", min_skill: int = 0, min_age: int = 0, max_age: int = 99,
               trait: str | None = None, country: str | None = None, free_only: bool = True, sort: str = "skill") -> list[Staffer]:
        q = q.strip().lower()
        out = [m for m in self.members.values() if m.club is None
               and (not free_only or m.employer is None) and (not role or m.role == role) and m.skill >= min_skill
               and min_age <= m.age <= max_age and (not trait or trait in m.traits) and (not country or m.country == country)
               and (not q or q in m.name.lower())]
        key = {"skill": lambda m: (-m.skill, m.id), "age": lambda m: (m.age, m.id), "price": lambda m: (m.expectation, m.id),
               "experience": lambda m: (-m.experience, m.id)}.get(sort, lambda m: (-m.skill, m.id))
        return sorted(out, key=key)

    def mine(self, game) -> list[Staffer]:
        return sorted((m for m in self.members.values() if m.club == game.club_name), key=lambda m: m.id)

    # ---- actions ----
    def hire(self, game, sid: str, salary: float | None = None, months: int = 12) -> str:
        m = self.members.get(sid)
        if m is None or m.club is not None:
            raise ValueError("этого специалиста нет на рынке")
        if m.employer is not None:
            raise ValueError(f"{m.name} работает в клубе {m.employer} до недели {m.employed_until}")
        if months not in MONTHS:
            raise ValueError("договор на 6, 12 или 24 месяца")
        salary = m.expectation if salary is None else float(salary)
        if salary < m.expectation * ACCEPT_RATIO:
            raise ValueError(f"{m.name} отказался: просит около {int(m.expectation)} в месяц")
        m.club, m.salary, m.start_week = game.club_name, salary, game.week
        m.end_week = game.week + round(months * WEEKS_PER_MONTH)
        m.log.append(f"неделя {game.week}: нанят на {months} мес., {int(salary)} в месяц")
        return f"{m.name} нанят ({roles()[m.role]['name']}), договор до недели {m.end_week}"

    def assign(self, game, sid: str) -> str:
        m = self.members.get(sid)
        if m is None or m.club != game.club_name:
            raise ValueError("это не ваш сотрудник")
        place = roles()[m.role]["workplace"]
        # the office role's workplace id in staff_roles.json is "office"; the facility is "headhunting_office"
        fid = {"office": "headhunting_office"}.get(place, place)
        if game.base.level(fid) < 1:
            raise ValueError("нужно здание: " + next(f["name"] for f in livingdata.load("facilities")["facilities"] if f["id"] == fid))
        used = sum(1 for x in self.mine(game) if x.workplace == fid and x.id != sid)
        if used >= self.capacity(game, fid):
            raise ValueError("все рабочие места заняты")
        m.workplace = fid
        m.log.append(f"неделя {game.week}: назначен в «{fid}»")
        return f"{m.name} назначен на рабочее место"

    def release(self, game, sid: str) -> str:
        m = self.members.get(sid)
        if m is None or m.club != game.club_name:
            raise ValueError("это не ваш сотрудник")
        left = max(0, m.end_week - game.week)
        fee = round(m.salary * left / WEEKS_PER_MONTH * FIRE_SHARE)
        if fee:
            game.club.book(game.week, "staff_named", -fee, f"выходное пособие: {m.name}")
        m.club, m.workplace, m.salary = None, None, 0.0
        m.listed_week = game.week
        m.log.append(f"неделя {game.week}: уволен, пособие {fee}")
        return f"{m.name} уволен, выплачено {fee}"

    def set_target(self, game, club: str | None) -> str:
        if club is not None and not any(c.name == club for c in game.clubs):
            raise ValueError("нет такого клуба")
        self.target = club
        return f"Аналитик изучает: {club}" if club else "Цель анализа снята"

    def capacity(self, game, fid: str) -> int:
        lvl = game.base.level(fid)
        if fid == "analytics_center":
            from .base import fac_data
            return sum(int(e) for l in fac_data()[fid]["levels"][:lvl] for k, e in l["effects"].items() if k == "analysis.slots")
        return 1 if lvl else 0

    # ---- the weekly tick ----
    def week(self, game) -> list[str]:
        out: list[str] = []
        for m in self.mine(game):
            game.club.book(game.week, "staff_named", -m.salary / WEEKS_PER_MONTH, f"{m.name} ({roles()[m.role]['name']})")
            if game.week >= m.end_week:
                m.club, m.workplace, m.salary, m.listed_week = None, None, 0.0, game.week
                m.log.append(f"неделя {game.week}: договор истёк, ушёл на рынок")
                out.append(f"клуб: у {m.name} истёк договор, он ушёл на рынок")
            elif m.end_week - game.week == 8:
                out.append(f"клуб: договор {m.name} истекает через 8 недель: продлите (наймите заново) или он уйдёт")
        out += self._world_turn(game)
        out += self._analyst_work(game)
        return out

    def _world_turn(self, game) -> list[str]:
        """Contracts at AI clubs run out, AI clubs sign free people, every season people age, retire and new ones appear."""
        r = self.rng
        for m in self.members.values():
            if m.employer is not None and game.week >= m.employed_until:
                m.history.append(f"{m.employer}, до недели {m.employed_until}")
                m.employer, m.listed_week = None, game.week
        if game.week and game.week % POACH_WEEKS == 0:
            ai = [c.name for c in game.clubs if c.name != game.club_name]
            free = sorted(self.free(), key=lambda m: m.id)
            for m in r.sample(free, min(len(free), POACH_COUNT)):
                m.employer, m.employed_until = r.choice(ai), game.week + r.randint(26, 130)
        if game.week and game.week % 52 == 0:
            for sid, m in list(self.members.items()):
                m.age += 1
                m.experience += 1
                if m.age > RETIRE_AGE and m.club is None and m.employer is None:
                    del self.members[sid]
            pool = [role for role, w in ROLE_WEIGHT.items() for _ in range(w)]
            for _ in range(SEASON_INTAKE):
                m = self._make(r.choice(pool), game.week, game.club.tier, young=True)
                self.members[m.id] = m
        return []

    def analyst_power(self, game, m: Staffer) -> float:
        """Learning speed multiplier for the dossier: his skill and the analytics centre's analysis depth (wired effects)."""
        from .base import fac_data
        lvl = game.base.level("analytics_center")
        depth = sum(e for l in fac_data()["analytics_center"]["levels"][:lvl] for k, e in l["effects"].items() if k == "analysis.demo_depth")
        return (0.4 + m.skill / 100) * (1 + depth) * (1 + sum(TRAITS[t][3] for t in m.traits if t in TRAITS))   # personality: the one wired trait effect

    def _analyst_work(self, game) -> list[str]:
        if not self.target:
            return []
        club = next((c for c in game.clubs if c.name == self.target), None)
        analysts = [m for m in self.mine(game) if m.role == "tactical_analyst" and m.workplace == "analytics_center"
                    and game.base.level("analytics_center") >= 1][: max(1, self.capacity(game, "analytics_center"))]
        if club is None or not analysts:
            return []
        weeks = sum(self.analyst_power(game, m) for m in analysts)
        before = self.knowledge(game, club)
        for p in club.lineup():
            game.desk.scouting.observe(p, weeks, "scout")
        after = self.knowledge(game, club)
        if int(after // 25) > int(before // 25):
            return [f"клуб: аналитик {analysts[0].name} собрал досье на {club.name}: изучено {round(after)}%"]
        return []

    def knowledge(self, game, club) -> float:
        k = [game.desk.scouting.knowledge.get(p.name, 0.0) for p in club.lineup()]
        return sum(k) / len(k) if k else 0.0
