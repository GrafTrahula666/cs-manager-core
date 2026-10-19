"""JSON-friendly facade over Game + ManagerDesk for user interfaces (the browser prototype
runs this module in Pyodide; a CLI or a server can call it the same way).

Every function returns plain dicts/lists/str, never core objects.
"""
from __future__ import annotations

import base64

from . import economy, save as save_mod
from .game import Game
from .market import expected_salary
from .talks import PRESS, TONES
from .traits import library

G: Game | None = None

TONE_RU = {"calm": "спокойно", "encourage": "подбодрить", "demand": "потребовать", "aggressive": "жёстко",
           "praise": "похвалить", "criticize": "покритиковать"}
FACILITIES = {"bootcamp": "буткемп", "academy": "академия", "studio": "студия контента"}


def _g() -> Game:
    if G is None:
        raise RuntimeError("игра не начата")
    return G


def new_game(seed: int = 1, n_clubs: int = 120, director: str = "cassandra") -> dict:
    global G
    G = Game.new(seed=seed, n_clubs=n_clubs, director=director)
    return state()


def _money(x: float) -> int:
    return int(round(x))


def state() -> dict:
    g = _g()
    c = g.club
    owner = g.desk.owner
    m = g.me()
    st = g.sysm.stories
    return {
        "club": c.name, "tier": c.tier, "region": c.region, "rank": c.rank, "season": g.season,
        "week": g.run.wk, "abs_week": g.week, "cash": _money(c.cash), "debt": _money(c.debt), "brand": round(c.brand),
        "fans": c.fans, "owner_confidence": round(owner.confidence) if owner else None,
        "objectives": [o.text for o in owner.objectives] if owner else [],
        "next_events": [{"week": w, "name": n, "invited": i} for w, n, i in g.next_events(4)],
        "pending_events": len(st.pending) if st else 0,
        "offers": len(g.sysm.market.offers) if g.sysm.market else 0,
        "manager": {"name": g.manager_name, "reputation": round(m.reputation) if m else None,
                    "titles": m.titles if m else 0},
        "sacked": g.sacked, "patch": g.sysm.meta.patch["name"] if g.sysm.meta else "",
        "facilities": {FACILITIES[k]: v for k, v in c.facilities.items() if k in FACILITIES},
    }


def roster() -> list[dict]:
    g = _g()
    c, lib = g.club, library()
    lineup = {p.name for p in c.lineup()}
    out = []
    for p in sorted(c.roster, key=lambda p: (p.name not in lineup, -p.overall())):
        k = c.contracts.get(p.name)
        out.append({
            "name": p.name, "role": p.role, "age": p.age, "country": p.country, "ovr": round(p.overall(), 1),
            "form": round(p.s("form")), "morale": round(p.s("morale")), "stress": round(p.s("stress")),
            "fatigue": round(p.s("fatigue")), "role_satisfaction": round(p.s("role_satisfaction")),
            "traits": [{"id": t, "name": lib[t].name, "rarity": lib[t].rarity} for t in p.traits
                       if t in lib and not lib[t].hidden_until],
            "star": "star" in p.flags, "stats": _season_stats(p),
            "salary": _money(k.salary_month) if k else 0, "contract_end": k.end_week if k else None,
            "value": _money(economy.market_value(p)), "lineup": p.name in lineup,
            "benched": "benched" in p.flags, "wants_out": "transfer_requested" in p.flags,
            "fame": round(p.fame), "history": p.history[-4:],
        })
    return out


def _season_stats(p) -> dict:
    st = p.__dict__.get("season_stats") or p.__dict__.get("last_season_stats")
    if not st or not st["rounds"]:
        return {}
    return {"maps": st["maps"], "kd": round(st["kills"] / max(1, st["deaths"]), 2),
            "kpr": round(st["kills"] / st["rounds"], 2)}


RARITY_RU = {"common": "обычная", "rare": "редкая", "special": "особая", "acquired": "приобретённая"}


def trait(tid: str) -> dict:
    """Everything about one trait for its card: what it gives, what it costs, what stresses it."""
    from .character import ACTIONS, RARITY_MUL
    t = library()[tid]
    mul = RARITY_MUL.get(t.rarity, 1.0)
    return {"id": t.id, "name": t.name, "rarity": t.rarity, "rarity_ru": RARITY_RU.get(t.rarity, t.rarity),
            "family": t.family, "desc": t.desc, "cons": t.cons,
            "stress_on": [f"{ACTIONS[a]} (+{v * mul:.0f})" for a, v in t.stress_on],
            "relief_on": [f"{ACTIONS[a]} (−{v:.0f})" for a, v in t.relief_on]}


def traits_all() -> list[dict]:
    order = {"special": 0, "rare": 1, "common": 2, "acquired": 3}
    return sorted((trait(t) for t in library()), key=lambda x: (order.get(x["rarity"], 9), x["family"], x["name"]))


def table(limit: int = 30, region: str | None = None) -> list[dict]:
    g = _g()
    rows = sorted((c for c in g.clubs if region is None or c.region == region), key=lambda c: c.rank)[:limit]
    titles = g.sysm.chronicle.titles if g.sysm.chronicle else {}
    return [{"rank": c.rank, "club": c.name, "tier": c.tier, "region": c.region, "points": round(c.rating_points),
             "titles": len(titles.get(c.name, [])), "me": c.name == g.club_name,
             "superteam": any(f.startswith("superteam_until:") for f in c.flags),
             "stars": sum("star" in p.flags for p in c.roster),
             "ovr": round(sum(p.overall() for p in c.lineup()) / 5, 1)} for c in rows]


def finances() -> dict:
    g = _g()
    c = g.club
    month = c.balance(g.week - 4)
    season = c.balance(g.run.start_week + 1)
    return {
        "cash": _money(c.cash), "debt": _money(c.debt),
        "month": {k: _money(v) for k, v in sorted(month.items(), key=lambda kv: kv[1])},
        "season": {k: _money(v) for k, v in sorted(season.items(), key=lambda kv: kv[1])},
        "sponsors": [{"name": s.name, "category": s.category, "annual": _money(s.annual), "until": s.end_week,
                      "kpi_rank": s.kpi_max_rank} for s in c.sponsors],
        "wages_month": _money(sum(k.salary_month for k in c.contracts.values())),
        "staff_month": _money(c.staff_month),
    }


def inbox() -> dict:
    g = _g()
    st, mk = g.sysm.stories, g.sysm.market
    events = [{"i": i, "id": f.event_id, "deck": bool(st.events[f.event_id].get("deck")), "title": f.title,
               "text": f.text, "options": f.options, "why": f.why[:4], "week": f.week}
              for i, f in enumerate(st.pending if st else [])]
    offers = [{"i": i, "buyer": o.buyer.name, "player": o.player.name, "fee": _money(o.fee), "salary": _money(o.salary)}
              for i, o in enumerate(mk.offers if mk else [])]
    return {"events": events, "offers": offers}


def answer_event(i: int, option: int) -> list[str]:
    g = _g()
    return g.desk.answer_event(g.sysm.stories.pending[i], option)


def answer_offer(i: int, accept: bool) -> str:
    g = _g()
    return g.desk.answer_offer(i, accept, g.week)


def market(limit: int = 40) -> list[dict]:
    """Free agents and players who asked to leave, seen through your scouts (ranges, not truth)."""
    g = _g()
    out, lib = [], library()
    for p, seller in g.sysm.market.listed(g.clubs):
        if seller is g.club:
            continue
        rep = g.desk.scouting.report(p)
        mid = sum(a + b for a, b in rep.stats.values()) / 2 / len(rep.stats)
        half = sum(b - a for a, b in rep.stats.values()) / 2 / len(rep.stats) / 2.2   # 20 stats average out
        lo, hi = max(0.0, mid - half), min(100.0, mid + half)
        k = seller.contracts.get(p.name) if seller else None
        ask = 0 if seller is None else min(economy.market_value(p) * 0.9, k.buyout if k else float("inf"))
        out.append({"name": p.name, "role": p.role, "age": p.age, "club": seller.name if seller else None,
                    "star": "star" in p.flags,
                    "ovr_range": [round(lo), round(hi)], "salary_wish": _money(expected_salary(p)),
                    "fee": _money(ask), "known": round(g.desk.scouting.knowledge.get(p.name, 0)),
                    "potential": rep.potential, "traits": [lib[t].name for t in rep.traits if t in lib]})
    return sorted(out, key=lambda r: -sum(r["ovr_range"]))[:limit]   # by the scouts' estimate, not truth


def scout(name: str) -> dict:
    g = _g()
    p, _ = g.find_player(name)
    rep = g.desk.scout(p, 4.0)
    lib = library()
    return {"name": name, "known": round(g.desk.scouting.knowledge.get(name, 0)), "stats": rep.stats,
            "traits": [lib[t].name for t in rep.traits if t in lib], "personality": rep.personality,
            "potential": rep.potential}


def sign(name: str, salary: float) -> str:
    g = _g()
    p, seller = g.find_player(name)
    if p is None:
        return "игрок не найден"
    if seller is None:
        return g.desk.sign_free_agent(p, salary, g.week)
    return "этот игрок под контрактом: сделайте предложение клубу"


def bid(name: str, fee: float, salary: float) -> str:
    g = _g()
    p, seller = g.find_player(name)
    if p is None or seller is None:
        return "игрок не найден или свободен"
    if g.club.cash < fee:
        return "не хватает денег"
    return g.desk.bid(p, seller, fee, salary, g.week)


def release(name: str) -> str:
    g = _g()
    c = g.club
    p = next((q for q in c.roster if q.name == name), None)
    if p is None:
        return "нет такого игрока"
    k = c.contracts.pop(name, None)
    payout = k.salary_month * 3 if k else 0
    c.book(g.week, "release", -payout, name)
    c.roster.remove(p)
    c.former.append(p)
    p.former_clubs.add(c.name)
    p.flags.add("free_agent")
    g.sysm.market.free_agents.append(p)
    return f"{name} отпущен, компенсация {payout:,.0f}"


def toggle_bench(name: str) -> str:
    g = _g()
    p = next((q for q in g.club.roster if q.name == name), None)
    if p is None:
        return "нет такого игрока"
    if "benched" in p.flags:
        p.flags.discard("benched")
        return f"{name} возвращён в состав"
    p.flags.add("benched")
    return f"{name} отправлен в запас"


def talk(tone: str) -> list[str]:
    if tone not in TONES:
        raise ValueError(tone)
    return _g().desk.talk(tone)


def press_options() -> dict:
    return {q: list(a) for q, a in PRESS.items()}


def press(question: str, answer: str, player: str | None = None) -> list[str]:
    g = _g()
    p = next((q for q in g.club.roster if q.name == player), None) if player else None
    if p is None and question in ("about_player_form", "about_transfer_rumours"):
        p = max(g.club.roster, key=lambda q: q.fame)
    return g.desk.press(question, answer, p)


def plan(practice_hours: float = 30, rest_days: int = 1, bootcamp: bool = False, commercial_days: int = 0) -> dict:
    g = _g()
    g.desk.set_week(practice_hours=practice_hours, rest_days=rest_days, bootcamp=bootcamp,
                    commercial_days=commercial_days)
    return {"practice_hours": practice_hours, "rest_days": rest_days, "bootcamp": bootcamp,
            "commercial_days": commercial_days}


def build(facility: str) -> str:
    g = _g()
    return g.desk.build(facility, g.week)


def loan(amount: float) -> str:
    g = _g()
    return g.desk.loan(amount, g.week)


def advance(weeks: int = 1) -> list[dict]:
    """Play weeks; stops early when the manager has something to decide or got sacked."""
    g = _g()
    out = []
    for _ in range(weeks):
        n = g.advance()
        out.append({"season": n.season, "week": (n.week - 1) % economy.WEEKS_PER_YEAR + 1, "lines": n.lines})
        if g.sacked or (g.sysm.stories and g.sysm.stories.pending) or (g.sysm.market and g.sysm.market.offers):
            break
    return out


def chronicle(n: int = 30) -> list[str]:
    ch = _g().sysm.chronicle
    return list(reversed(ch.headlines(n, kinds=("title", "transfer", "story", "rivalry", "retirement", "patch", "board"))))


def rivalries(n: int = 8) -> list[dict]:
    g = _g()
    riv = g.sysm.rivalries
    top = sorted(riv.clubs.items(), key=lambda kv: -kv[1].score)[:n]
    return [{"clubs": sorted(pair), "score": round(r.score), "meetings": r.meetings, "wins": r.wins,
             "memories": [m.text for m in r.memories[-2:]]} for pair, r in top]


def jobs() -> list[dict]:
    return [{"club": c.name, "tier": c.tier, "rank": c.rank, "region": c.region} for c in _g().job_offers()]


def take_job(club: str) -> str:
    return _g().take_job(club)


def save_b64() -> str:
    return base64.b64encode(save_mod.dumps(_g())).decode()


def load_b64(data: str) -> dict:
    global G
    G = save_mod.loads(base64.b64decode(data))
    return state()


def meta_info() -> dict:
    return {"tones": {t: TONE_RU[t] for t in TONES}, "facilities": FACILITIES, "press": press_options()}
