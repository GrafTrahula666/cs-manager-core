"""The club base (LIVING CLUB, stage 3-4): nine facilities with levels 0-5.

Building and upgrading cost real money through Club.book (item "construction"), take build weeks, and
afterwards charge monthly upkeep (item "facilities"). Requirements come from data/facilities.json.
Effects are shown with their status (EFFECT_STATUS, default `planned` = not active) until later stages wire them in; nothing
here changes a win probability. The old Club.facilities dict (bootcamp/academy/studio) is untouched.
"""
from __future__ import annotations

from . import livingdata
from .economy import WEEKS_PER_MONTH

MAX_PARALLEL = 2             # at most two construction projects at once
OWNER_APPROVAL_MIN = 50      # hypothesis: the owner approves big projects while confidence is at least this

EFFECT_RU = {
    "training.quality": "качество тренировок", "fatigue.risk": "риск усталости", "academy.slots": "места в академии",
    "academy.potential_read": "точность оценки потенциала", "streaming.income": "доход от стримов", "streaming.slots": "места для стримеров",
    "stress.relief": "снятие стресса", "recovery.rate": "скорость восстановления", "analysis.demo_depth": "глубина разбора демо",
    "analysis.slots": "аналитики одновременно", "fans.growth": "рост фанатов", "injury.risk_cut": "меньше травм", "hire.pool_size": "кандидатов в выборке",
}


# Status of each facility effect key (planned -> wired -> tested -> calibrated). Nothing is wired yet, so none of
# them may be shown as an active bonus. Flip a key here in the PR that really connects it.
EFFECT_STATUS: dict[str, str] = {
    # wired in staff.py: the analytics centre speeds up the analyst's dossier on a rival club (information only)
    "analysis.demo_depth": "wired", "analysis.slots": "wired",
}


def effect_status(key: str) -> str:
    return EFFECT_STATUS.get(key, "planned")


def fac_data() -> dict:
    return {f["id"]: f for f in livingdata.load("facilities")["facilities"]}


class Base:
    def __init__(self) -> None:
        self.levels: dict[str, int] = {fid: f["start_level"] for fid, f in fac_data().items()}
        self.projects: dict[str, dict] = {}     # id -> {"to": level, "done": absolute week, "cost": paid}
        self.history: list[str] = []

    def level(self, fid: str) -> int:
        return self.levels.get(fid, 0)

    def total_levels(self) -> int:
        return sum(self.levels.values())

    def upkeep_of(self, fid: str, lv: int) -> float:
        """Monthly upkeep of a level. The rooms a club starts with are already inside the old staff budget, so a
        start level costs nothing extra: only what was built beyond it is charged (no hidden price rise at day one)."""
        f = fac_data()[fid]
        if not lv:
            return 0.0
        free = f["levels"][f["start_level"] - 1]["upkeep_month"] if f["start_level"] else 0.0
        return max(0.0, f["levels"][lv - 1]["upkeep_month"] - free)

    def upkeep_month(self) -> float:
        return sum(self.upkeep_of(fid, lv) for fid, lv in self.levels.items() if fid in fac_data())

    # ---- requirements ----
    def check(self, game, fid: str) -> dict:
        """Everything about the next level of one facility: price, weeks, each requirement with its state."""
        f = fac_data()[fid]
        cur = self.level(fid)
        if fid in self.projects:
            return {"can": False, "why": "уже строится", "next": None}
        if cur >= 5:
            return {"can": False, "why": "максимальный уровень", "next": None}
        lv = f["levels"][cur]
        req = lv["requires"]
        club = game.club
        rows = []

        def add(text, ok, soft=False):
            rows.append({"text": text, "ok": ok, "soft": soft})
        add(f"деньги {int(lv['cost']):,}".replace(",", " "), club.cash >= lv["cost"])
        if req.get("club_reputation"):
            add(f"бренд клуба {req['club_reputation']}+", club.brand >= req["club_reputation"])
        if req.get("fans"):
            add(f"фанатов {req['fans']:,}".replace(",", " "), club.fans >= req["fans"])
        if req.get("titles_a_or_higher"):
            n = self.big_titles(game)
            add(f"титулов турниров A/S: {req['titles_a_or_higher']} (у вас {n})", n >= req["titles_a_or_higher"])
        if req.get("owner_approval"):
            add(f"одобрение владельца (доверие {OWNER_APPROVAL_MIN}+)", game.desk.owner.confidence >= OWNER_APPROVAL_MIN)
        if req.get("staff_role_min_skill"):
            add("профильный специалист в штате: проверка появится вместе с рынком штата", True, soft=True)
        add(f"параллельных строек не больше {MAX_PARALLEL}", len(self.projects) < MAX_PARALLEL)
        ok = all(r["ok"] for r in rows)
        return {"can": ok, "why": "" if ok else next(r["text"] for r in rows if not r["ok"]),
                "next": {"level": cur + 1, "cost": lv["cost"], "weeks": lv["build_weeks"], "upkeep_month": self.upkeep_of(fid, cur + 1) - self.upkeep_of(fid, cur),
                         "effects": [{"key": k, "label": EFFECT_RU.get(k, k), "value": v, "active": livingdata.is_active(effect_status(k))} for k, v in lv["effects"].items()],
                         "events": lv["events"], "req": rows}}

    def big_titles(self, game) -> int:
        ch = game.sysm.chronicle
        if ch is None:
            return 0
        n = 0
        for title in ch.titles.get(game.club_name, []):
            if game._tier_of(title.rsplit(" (сезон", 1)[0]) in ("S", "A"):
                n += 1
        return n

    # ---- actions ----
    def start(self, game, fid: str) -> str:
        if fid not in fac_data():
            raise ValueError("нет такого здания")
        c = self.check(game, fid)
        if not c["can"]:
            raise ValueError(f"нельзя начать стройку: {c['why']}")
        nx = c["next"]
        game.club.book(game.week, "construction", -nx["cost"], f"{fac_data()[fid]['name']} до уровня {nx['level']}")
        self.projects[fid] = {"to": nx["level"], "done": game.week + nx["weeks"], "cost": nx["cost"]}
        return f"{fac_data()[fid]['name']}: стройка уровня {nx['level']} начата, готово через {nx['weeks']} нед."

    # ---- the weekly tick (called from Game.advance) ----
    def week(self, game) -> list[str]:
        out = []
        d = fac_data()
        for fid, lv in self.levels.items():
            up = self.upkeep_of(fid, lv)
            if up:
                game.club.book(game.week, "facilities", -up / WEEKS_PER_MONTH, f"{d[fid]['name']} ур. {lv}")
        for fid, p in list(self.projects.items()):
            if game.week >= p["done"]:
                self.levels[fid] = p["to"]
                del self.projects[fid]
                names = livingdata.load("facilities")["level_names"]
                line = f"клуб: {d[fid]['name']} достигла уровня {p['to']} ({names[p['to']]})"
                self.history.append(f"сезон {game.season}: {line}")
                out.append(line)
                if game.living is not None:
                    out += game._grant("infra_project", f"{fid}:{p['to']}")
        return out
