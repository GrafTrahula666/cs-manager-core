"""What the manager sees and what the manager can do about it.

The manager never sees hidden values. A situation shows the version of events the club
believes (which can be wrong), how the club learned it (the assistant noticed, a player told
you, an article), and the risks the staff can foresee, phrased as the assistant's estimates.

Every option is a trade-off with consequences that arrive later through people's memories:
back one side and the other remembers; mediate and you spend a week of training on talks and
may fail; discipline and the dressing room gets quieter but trusts you less; ignore it and it
may fade, or fester. AI clubs face the same situations and pick by their own manager's habits.
"""
from __future__ import annotations

import math
import random

from .sim import MAX_OPEN_SITUATIONS, SITUATION_COOLDOWN, Situation

CONFLICT_KINDS = {"public_jab", "open_conflict", "private_confront", "freeze_out", "side_with"}
AXES_RU = {"criticism": "обидчив", "ego": "самолюбив", "conflict": "вспыльчив", "loyalty": "предан клубу",
           "media": "любит камеры", "social_need": "дорожит атмосферой"}


def estimate(p, axis: str) -> float:
    """The assistant's estimate of a hidden axis: fixed per person, closer for your own players."""
    noise = random.Random(f"est:{p.name}:{axis}").gauss(0, 18 * (1 - 0.7))
    return max(0.0, min(100.0, p.p(axis) + noise))


def _risk(p, axis: str, high: bool = True) -> str | None:
    v = estimate(p, axis)
    if high and v >= 65:
        return f"{p.name} {AXES_RU[axis]} (оценка ассистента)"
    return None


def _parties(f, holder: str) -> tuple[str | None, str | None]:
    b = f.believed(holder)
    if f.kind == "side_with":
        return f.third, b["target"]
    return b["actor"], b["target"]


def make_situation(ew, ctx, club_name: str, f) -> Situation | None:
    """Turn a fact that reached a club's staff into a decision for its manager (or none)."""
    holder = f"club:{club_name}"
    if f.kind in CONFLICT_KINDS and not (f.kind == "private_confront" and f.data.get("ok")):
        kind = "conflict"
    elif f.kind == "complain":
        kind = "complaint"
    elif f.kind == "article" and f.club == club_name and f.about is not None:
        kind = "leak"
    else:
        return None
    a, b = _parties(f, holder) if kind != "leak" else (f.target, None)
    club = next((c for c in ctx.clubs if c.name == club_name), None)
    if club is None:
        return None
    roster = {p.name for p in club.roster}
    if a not in roster or (b is not None and b not in roster):
        return None
    key = f"{club_name}|{'|'.join(sorted(x for x in (a, b) if x))}|{kind}"
    if ew.pair_situation.get(key, -100) > ctx.week - SITUATION_COOLDOWN:
        return None
    if ew.open_situation(club_name, a, b) is not None:
        return None
    if sum(1 for s in ew.situations if s.club == club_name and s.choice is None) >= MAX_OPEN_SITUATIONS:
        return None
    ew.pair_situation[key] = ctx.week
    how = (f.knowers.get(holder) or f.knowers.get("*", (ctx.week, "из новостей")))[1]
    seen = f.believed(holder)
    text = seen["text"] or f.text
    pa, pb = ew.player(ctx, a), ew.player(ctx, b)
    opts = options(kind, pa, pb, club)
    s = Situation(ew.next_situation, ctx.week, club_name, kind, f.id, a, b, text, how, opts)
    ew.next_situation += 1
    ew.situations.append(s)
    return s


def options(kind: str, a, b, club) -> list[dict]:
    def risks(*xs):
        return [r for r in xs if r]
    if kind in ("conflict", "complaint"):
        return [
            {"key": "back_a", "label": f"Поддержать {a.name}",
             "risks": risks(_risk(b, "criticism"), _risk(b, "ego")) + [f"{b.name} запомнит, что вы были против него"]},
            {"key": "back_b", "label": f"Поддержать {b.name}",
             "risks": risks(_risk(a, "criticism"), _risk(a, "conflict")) + [f"{a.name} может пойти со своей обидой в прессу или к выходу"]},
            {"key": "mediate", "label": "Поговорить с обоими лично",
             "risks": ["неделя тренировок пройдёт хуже: вы заняты разговорами", "может не получиться, тогда оба будут недовольны вами"]
             + risks(_risk(a, "ego"), _risk(b, "ego"))},
            {"key": "discipline", "label": "Штраф обоим и тишина в раздевалке",
             "risks": ["оба будут меньше вам доверять", "ссоры на время затихнут", "владелец любит порядок"]},
            {"key": "ignore", "label": "Не вмешиваться",
             "risks": ["может само сойти на нет, а может разрастись"] +
             ([f"{a.name} ждёт от вас ответа" ] if kind == "complaint" else [])},
        ]
    return [
        {"key": "deny", "label": "Опровергнуть публично",
         "risks": ["в раздевалке знают правду: доверие к вам упадёт у тех, кто ценит честность"]},
        {"key": "admit", "label": "Признать и пообещать разобраться",
         "risks": ["бренд клуба немного пострадает", f"{a.name} окажется под ударом"]},
        {"key": "hunt", "label": "Искать, кто слил",
         "risks": ["атмосфера подозрений, доверие всех немного падает", "можно обвинить не того"]},
        {"key": "ignore", "label": "Промолчать", "risks": ["история может обрасти слухами"]},
    ]


def _left(s: Situation, club, a, b) -> bool:
    """A player of the situation retired or moved on while it waited for an answer."""
    gone = lambda p: p is None or p not in club.roster   # noqa: E731
    return gone(a) or (s.kind != "leak" and gone(b))


def ai_resolve(ew, ctx, s: Situation) -> list[str]:
    """An AI manager decides by his habits: back the more influential player, sometimes mediate."""
    from ..squad import influence
    club = next(c for c in ctx.clubs if c.name == s.club)
    careers = getattr(ctx.sysm, "careers", None)
    rep = careers.managers[club.name].reputation if careers and club.name in careers.managers else 40.0
    keys = [o["key"] for o in s.options]
    if _left(s, club, ew.player(ctx, s.a), ew.player(ctx, s.b)):   # someone left while it waited
        return resolve(ew, ctx, s, "ignore", by="ai")
    a, b = ew.player(ctx, s.a), ew.player(ctx, s.b)
    w = []
    for k in keys:
        if k == "back_a":
            w.append(1.0 + influence(a, club, ctx.week) / 60)
        elif k == "back_b":
            w.append(1.0 + influence(b, club, ctx.week) / 60)
        elif k == "mediate":
            w.append(0.6 + rep / 50)
        elif k in ("discipline", "deny"):
            w.append(1.0)
        else:
            w.append(1.2)
    pick = ctx.rng.choices(keys, weights=w)[0]
    return resolve(ew, ctx, s, pick, by="ai")


def resolve(ew, ctx, s: Situation, key: str, by: str = "manager") -> list[str]:
    """Apply a manager's choice: real changes now, and a fact people will remember."""
    club = next(c for c in ctx.clubs if c.name == s.club)
    mgr = ew.manager_id(ctx, club)
    a, b = ew.player(ctx, s.a), ew.player(ctx, s.b)
    out: list[str] = []
    s.choice, s.by = key, by
    imp: dict = {}
    text = ""
    data = {"situation": s.id, "choice": key}
    if _left(s, club, a, b):
        s.outcome = ["участник уже не в клубе, ситуация закрыта"]
        return s.outcome
    if key in ("back_a", "back_b"):
        win, lose = (a, b) if key == "back_a" else (b, a)
        ew.st(win, "coach_trust", 8), ew.st(lose, "coach_trust", -10), ew.st(lose, "morale", -5)
        ew.rel(ctx, lose.name, win.name, "resentment", 6)
        if s.kind == "complaint" and win is a:
            ew.st(a, "role_satisfaction", 10)
        imp = {win.name: {"trust": 8, "pride": 3}, lose.name: {"trust": -10, "pride": -6}}
        text = f"Менеджер {club.name} поддержал {win.name} в споре с {lose.name}"
    elif key == "mediate":
        careers = getattr(ctx.sysm, "careers", None)
        rep = careers.managers[club.name].reputation if careers and club.name in careers.managers else 40.0
        g = ctx.graph
        heat = (g.get(a.name, b.name).resentment + g.get(b.name, a.name).resentment) / 2
        z = rep / 60 + (200 - a.p("conflict") - b.p("conflict")) / 200 - (a.p("ego") + b.p("ego")) / 250 - heat / 60 - 0.3
        p_ok = 1 / (1 + math.exp(-3 * z))
        ok = ctx.rng.random() < p_ok
        for q in club.roster:
            ew.st(q, "form", -2)     # a week of talks instead of coaching
        if ok:
            for u, v in ((a.name, b.name), (b.name, a.name)):
                ew.rel(ctx, u, v, "irritation", -14), ew.rel(ctx, u, v, "resentment", -12)
            ew.st(a, "coach_trust", 4), ew.st(b, "coach_trust", 4)
            imp = {a.name: {"trust": 4, "belonging": 3}, b.name: {"trust": 4, "belonging": 3}, f"club:{club.name}": {"harmony": 5}}
            text = f"Менеджер {club.name} лично помирил {a.name} и {b.name}"
        else:
            ew.st(a, "coach_trust", -3), ew.st(b, "coach_trust", -3)
            ew.rel(ctx, a.name, b.name, "irritation", 3)
            imp = {a.name: {"trust": -3}, b.name: {"trust": -3}}
            text = f"Менеджер {club.name} пытался помирить {a.name} и {b.name}, разговор ничего не дал"
        data["ok"] = ok
        out.append(f"шанс был {p_ok:.0%}: {'получилось' if ok else 'не получилось'}; тренировки недели хуже (форма −2)")
    elif key == "discipline":
        for q in (a, b):
            ew.st(q, "coach_trust", -6)
            club.book(ctx.week, "fines", 2_000, f"штраф {q.name}")
        for u, v in ((a.name, b.name), (b.name, a.name)):
            ew.rel(ctx, u, v, "irritation", -10)
        ew.order_until[club.name] = ctx.week + 8
        owners = getattr(ctx.sysm, "owners", None) or {}
        if club.name in owners:
            owners[club.name].confidence = min(100.0, owners[club.name].confidence + 2)
        imp = {a.name: {"trust": -6, "pride": -2}, b.name: {"trust": -6, "pride": -2}}
        text = f"Менеджер {club.name} оштрафовал {a.name} и {b.name}"
        out.append("в раздевалке на два месяца тише")
    elif key == "ignore":
        if s.kind == "complaint":
            ew.st(a, "coach_trust", -4)
            imp = {a.name: {"trust": -4}}
        text = f"Менеджер {club.name} не стал вмешиваться ({s.text})"
    elif key == "deny":
        insiders = [q for q in club.roster if ew.facts.get(s.fact) and ew.facts.get(s.fact).known_by(q.name)]
        for q in insiders:
            if q.p("loyalty") < 60:
                ew.st(q, "coach_trust", -3)
        imp = {q.name: {"trust": -3} for q in insiders if q.p("loyalty") < 60}
        text = f"Менеджер {club.name} публично опроверг слухи"
    elif key == "admit":
        club.brand = max(0.0, club.brand - 2)
        for q in club.roster:
            if q is not a:
                ew.st(q, "coach_trust", 2)
        imp = {a.name: {"pride": -4}}
        text = f"Менеджер {club.name} признал проблему в команде"
    elif key == "hunt":
        orig = ew.facts.get(s.fact)
        art = next((f for f in ew.facts.recent(s.week - 1) if f.kind == "article" and f.about == s.fact), None)
        leaks = [f for f in ew.facts.recent(s.week - 10) if f.kind == "leak" and f.data.get("about") == s.fact]
        true = leaks[-1].actor if leaks else None
        for q in club.roster:
            ew.st(q, "coach_trust", -2)
        found = true if true and ctx.rng.random() < 0.4 + club.scout_quality / 200 else None
        if found is None:
            pool = sorted((q for q in club.roster if q.name != true and (orig is None or q.name not in orig.people())),
                          key=lambda q: (q.s("coach_trust") - q.p("media"), q.name))
            accused = pool[0].name if pool else None
        else:
            accused = found
        if accused is None:
            text = f"Менеджер {club.name} искал источник утечки, но ничего не нашёл"
        else:
            ap = ew.player(ctx, accused)
            ew.st(ap, "coach_trust", -12), ew.st(ap, "morale", -6)
            imp = {accused: {"trust": -12, "pride": -8}}
            wrong = accused != true
            text = f"Менеджер {club.name} решил, что утечка от {accused}"
            data.update({"accused": accused, "wrong": wrong})
            if leaks:
                # the club now holds a belief about the leak: true or false
                ew.facts.learn(f"club:{club.name}", leaks[-1].id, ctx.week, "внутреннее расследование",
                               None if not wrong else {"actor": accused, "text": f"{accused} слил информацию прессе"})
            out.append("нашли настоящего источника" if not wrong else "под подозрение попал невиновный")
        del art
    f = ew.emit(ctx, "manager_decision", actor=mgr, target=s.a, third=s.b, club=club.name, impacts=imp,
                causes=[s.fact], reasons=[f"ситуация: {s.text}", f"решение: {key}" + (" (ассистент)" if by == "assistant" else "")],
                salience=8, witnesses=[q.name for q in club.roster] + [f"club:{club.name}"], text=text, data=data)
    s.outcome = [text] + out
    return s.outcome
