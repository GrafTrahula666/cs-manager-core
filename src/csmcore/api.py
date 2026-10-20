"""JSON-friendly facade over Game + ManagerDesk for user interfaces (the browser prototype
runs this module in Pyodide; a CLI or a server can call it the same way).

Every function returns plain dicts/lists/str, never core objects.
"""
from __future__ import annotations

import base64

from . import circuit, contracts as contracts_mod, economy, save as save_mod
from .game import Game
from .market import asking, expected_salary
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
        "situations": len(g.situations()),
        "objective_status": [{"text": o.text, "score": round(owner._score(o, c), 2)} for o in owner.objectives] if owner else [],
        "zone": _zone(g),
        "division": circuit.name(c.division), "division_place": circuit.standings(g.clubs, c.division).index(c) + 1,
        "season_points": round(c.season_points), "hltw_rank": g.sysm.hltw.place(c.name) if g.sysm.hltw else None,
    }


def _zone(g: Game) -> str:
    """'up' / 'down' when the club sits in a promotion / relegation place of its league now."""
    k = g.club.division
    rows = circuit.standings(g.clubs, k)
    i = rows.index(g.club) + 1
    up = circuit.SWAPS.get(k - 1, 0) if k > 1 else 0
    down = circuit.SWAPS.get(k, 0) if k < 4 else 0
    return "up" if i <= up else "down" if down and i > len(rows) - down else ""


def _hints(club, effects: list[dict]) -> dict:
    """What an option does to the club, read from its effects: sure numbers and 'maybe' flags."""
    from .storylets import TIER_CASH
    h = {"cash": 0, "fans_pct": 0, "brand": 0, "morale": 0, "risky": False}
    for e in effects:
        if "chance" in e or "follow" in e or "follow_random" in e or "sponsor_leaves" in e or "release" in e \
                or "add_trait" in e or "secret" in e or "flag" in e:
            h["risky"] = True
        if "chance" in e:
            continue
        if "cash" in e:
            h["cash"] += e["cash"]
        elif "cash_scaled" in e:
            h["cash"] += e["cash_scaled"] * TIER_CASH.get(club.tier, 1.0)
        elif "fans_pct" in e:
            h["fans_pct"] += e["fans_pct"]
        elif "brand" in e:
            h["brand"] += e["brand"]
        elif "team_morale" in e:
            h["morale"] += e["team_morale"]
        elif e.get("state") == "morale" and e.get("who") != "b":
            h["morale"] += e["add"] / 5
    h["cash"] = _money(h["cash"])
    return h


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
            "contract_status": k.status if k else None,
            "value": _money(economy.market_value(p)), "lineup": p.name in lineup,
            "benched": "benched" in p.flags, "wants_out": "transfer_requested" in p.flags,
            "fame": round(p.fame), "history": p.history[-4:], **_haceit_card(p.name),
        })
    return out


def _haceit_card(name: str) -> dict:
    hc = _g().sysm.haceit
    card = hc.card(name) if hc else {}
    return {"elo": card.get("elo"), "level": card.get("level"), "hpl": card.get("hpl", False)}


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
    hl = g.sysm.hltw
    return [{"rank": c.rank, "club": c.name, "tier": c.tier, "region": c.region, "points": round(c.rating_points),
             "division": circuit.name(c.division), "hltw": hl.place(c.name) if hl else None,
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
               "text": f.text, "options": f.options, "why": f.why[:4], "week": f.week,
               "hints": [_hints(g.club, o.get("effects", [])) for o in st.events[f.event_id].get("options", [])],
               "left": max(0, 2 - (g.week - f.week))}
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
    for p, seller in g.sysm.market.listed(g.clubs, g.week):
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
                    "ovr_range": [round(lo), round(hi)], "salary_wish": _money(asking(p, g.week) if seller is None else expected_salary(p)),
                    "fee": _money(ask), "known": round(g.desk.scouting.knowledge.get(p.name, 0)),
                    "potential": rep.potential, "traits": [lib[t].name for t in rep.traits if t in lib],
                    **_haceit_card(p.name)})
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
    k = c.contracts.get(name)
    payout = k.salary_month * 3 if k else 0
    contracts_mod.release(c, p, g.sysm.market, g.week, "менеджер отпустил", payout_months=3 if k else 0)
    contracts_mod.note(g.sysm.market, g.week, c.name, name, "released", "решение менеджера")
    return f"{name} отпущен, компенсация {payout:,.0f}"


def contracts() -> list[dict]:
    """The manager's contracts: who is in extension talks and who leaves on a free."""
    g = _g()
    out = []
    for p in sorted(g.club.roster, key=lambda q: g.club.contracts[q.name].end_week if q.name in g.club.contracts else 1 << 30):
        k = g.club.contracts.get(p.name)
        if k is None:
            continue
        out.append({"name": p.name, "salary": _money(k.salary_month), "end_week": k.end_week,
                    "weeks_left": k.end_week - g.week, "status": k.status, "id": k.contract_id,
                    "expected": _money(expected_salary(p)), "offer": _money(contracts_mod.offer_salary(g.club, p))})
    return out


def renew(name: str, salary: float, weeks: int = 104) -> str:
    """Offer an extension; the player decides as with any contract."""
    g = _g()
    c = g.club
    p = next((q for q in c.roster if q.name == name), None)
    k = c.contracts.get(name)
    if p is None or k is None:
        return "нет такого игрока"
    if k.end_week - g.week > contracts_mod.RENEWAL_WINDOW * 3:
        return f"рано: контракт до недели {k.end_week}"
    if k.status == "leaving" and g.week - g.sysm.market.refused.get((name, c.name), -999) < 4:
        return f"{name} только что отказал, вернитесь позже"
    ok, line = contracts_mod.offer(g.sysm.market, c, p, float(salary), int(weeks), g.week, g.desk.rng, "менеджер")
    if not ok:
        g.sysm.market.refused[(name, c.name)] = g.week
    return line


def hiring(n: int = 40) -> dict:
    """Why clubs did or did not complete their rosters: the contract and hiring journal."""
    m = _g().sysm.market
    return {"journal": m.journal[-n:][::-1], "stats": dict(m.stats.most_common())}


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
        if g.sacked or (g.sysm.stories and g.sysm.stories.pending) or (g.sysm.market and g.sysm.market.offers) \
                or g.situations():
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


# ---------- the emergent world: what the manager knows and why things happened ----------
SITUATION_RU = {"conflict": "конфликт", "complaint": "жалоба", "leak": "утечка в прессу"}


def _ew():
    ew = getattr(_g().sysm, "emergent", None)
    if ew is None:
        raise RuntimeError("в этом мире нет причинного движка")
    return ew


def situations() -> list[dict]:
    """Open situations first, then the last few resolved ones."""
    g = _g()
    items = sorted(g.situations(open_only=False), key=lambda s: (s.choice is not None, -s.week))[:8]
    return [{"id": s.id, "week": (s.week - 1) % economy.WEEKS_PER_YEAR + 1, "kind": SITUATION_RU.get(s.kind, s.kind),
             "text": s.text, "how": s.how, "fact": s.fact, "open": s.choice is None,
             "options": s.options, "choice": s.choice, "outcome": s.outcome, "by": s.by} for s in items]


def answer_situation(sid: int, key: str) -> list[str]:
    return _g().answer_situation(sid, key)


def reports(n: int = 20) -> list[dict]:
    """What reached your staff, and how. The club's version can be wrong; the UI cannot tell."""
    g = _g()
    rs = _ew().reports.get(g.club_name, [])[-n:]
    return [{"week": (r.week - 1) % economy.WEEKS_PER_YEAR + 1, "text": r.text, "how": r.how, "fact": r.fact}
            for r in reversed(rs)]


def world_feed(n: int = 20, min_salience: float = 12.0) -> list[dict]:
    """Public news of the whole world: what anyone could read."""
    ew = _ew()
    out = []
    for f in reversed(list(ew.facts.facts.values())):
        if f.visibility == "public" and f.salience >= min_salience and f.kind not in ("series",):
            out.append({"fact": f.id, "season": f.season, "week": (f.week - 1) % economy.WEEKS_PER_YEAR + 1,
                        "kind": f.kind, "text": f.text})
            if len(out) >= n:
                break
    return out


def why(fid: int, god: bool = False, depth: int = 6) -> dict:
    """Causal tree of a fact as your club sees it: facts you do not know stay hidden and the
    hidden numbers behind people's choices are shown only in god mode (for debugging and demos)."""
    g, ew = _g(), _ew()
    holder = f"club:{g.club_name}"

    def mask(node):
        f = ew.facts.get(node["id"])
        known = god or f is None or f.known_by(holder)
        if not known:
            return {"id": node["id"], "text": "что-то, о чём вы не знаете", "causes": [], "reasons": [], "hidden": True}
        out = dict(node)
        if f is not None and not god:
            seen = f.believed(holder)
            out["text"] = seen["text"] or out["text"]
            out["how"] = f.knowers.get(holder, f.knowers.get("*", (0, "")))[1]
            out["reasons"] = []
        out["causes"] = [mask(c) for c in node.get("causes", [])]
        return out
    return mask(ew.why(fid, depth))


def legends(n: int = 8) -> list[dict]:
    from .emergent.history import legends as top
    return [{"name": name, "score": round(sc)} for name, sc in top(_ew(), n, 60.0)]


def retrospective(name: str) -> dict:
    from .emergent.history import retrospective as retro
    g = _g()
    r = retro(_ew(), name, g.season)
    r["sources"] = [list(x) for x in r["sources"]]
    return r


def person(name: str) -> dict:
    """A word with one of your players: what he says, not what he hides."""
    from .emergent.narrate import Narrator
    g, ew = _g(), _ew()
    p = next((q for q in g.club.roster if q.name == name), None)
    if p is None:
        return {"name": name, "says": "Это не ваш игрок."}
    narr = ew.narrator or Narrator()
    return {"name": name, "says": narr.dialogue(p, ew.minds.of(name))}


# ---- leagues, HACEIT and HLTW ----
def leagues(division: int | None = None) -> dict:
    """A league table: season points decide who goes up and who goes down at the end."""
    g = _g()
    k = division or g.club.division
    rows = circuit.standings(g.clubs, k)
    up = circuit.SWAPS.get(k - 1, 0) if k > 1 else 0
    down = circuit.SWAPS.get(k, 0) if k < 4 else 0
    out = []
    for i, c in enumerate(rows, 1):
        zone = "up" if i <= up else "down" if down and i > len(rows) - down else ""
        out.append({"place": i, "club": c.name, "region": c.region, "points": round(c.season_points),
                    "rank": c.rank, "me": c.name == g.club_name, "zone": zone})
    return {"division": k, "name": circuit.name(k), "names": circuit.NAMES, "rows": out,
            "invites": [t.name for ts in g.calendar.values() for t in (ts if isinstance(ts, list) else [ts])
                        if t.divisions and k in t.divisions and t.region in (None, g.club.region)]}


def hltw(n: int = 30) -> dict:
    """HLTW: its own ranking (beside the official one), MVPs and the Top 20 of past seasons."""
    g = _g()
    hl = g.sysm.hltw
    if hl is None:
        return {"ranking": [], "mvps": [], "top20": {}}
    by = {c.name: c for c in g.clubs}
    return {"ranking": [{"place": i, "club": name, "points": round(hl.points[name]), "official": by[name].rank,
                         "division": circuit.name(by[name].division), "me": name == g.club_name}
                        for i, name in enumerate(hl.ranking[:n], 1)],
            "mvps": list(reversed(hl.mvps[-12:])), "top20": {str(k): v for k, v in hl.top20.items()}}


def haceit(n: int = 25) -> dict:
    """HACEIT: the Elo ladder, HPL and where your players stand."""
    from .haceit import level
    g = _g()
    hc = g.sysm.haceit
    if hc is None:
        return {"ladder": [], "mine": [], "hpl": 0}
    club_of = {p.name: c.name for c in g.clubs for p in c.roster}
    ages = {p.name: p.age for c in g.clubs for p in c.roster}
    if g.sysm.market:
        ages.update({p.name: p.age for p in g.sysm.market.free_agents})
    ladder = [{"place": i, "player": name, "elo": round(e), "level": level(e), "club": club_of.get(name),
               "age": ages.get(name), "hpl": name in hc.hpl} for i, (name, e) in enumerate(hc.ladder(n), 1)]
    mine = [{"player": p.name, **hc.card(p.name)} for p in g.club.roster if p.name in hc.elo]
    return {"ladder": ladder, "mine": mine, "hpl": len(hc.hpl)}
