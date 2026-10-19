"""Universal typed actions. A story is never scripted: people pick one of these when their
emotions, goals, memories and the situation make it worth more than doing nothing.

Each action has
    candidates  who it could be aimed at, from what the actor feels and knows
    available   can the actor really do it (same club, a journalist in reach, not already asked ...)
    utility     how much it is worth to this person now, with the reasons
    execute     the real changes to the world, recorded as a fact with impacts and causes

`tone` is "neg" for actions that hurt someone (they draw on the club's drama budget), "pos" for
help and repair, "self" for things done to oneself.
"""
from __future__ import annotations

import math

NEG, POS, SELF = "neg", "pos", "self"


def _p(p, k):
    return p.p(k) / 100


class Action:
    name = ""
    label = ""
    tone = SELF
    public = False        # needs a media opportunity (press day, match week)
    cooldown = 8          # weeks before the same person does this to the same target again

    def candidates(self, ew, ctx, a, club, mind):
        return []

    def available(self, ew, ctx, a, club, t, x) -> bool:
        return True

    def utility(self, ew, ctx, a, club, mind, t, x) -> tuple[float, list[str]]:
        return 0.0, []

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        raise NotImplementedError


def _mates(club, a):
    return [q for q in club.roster if q is not a]


def _felt_targets(mind, kinds, min_v=8.0):
    out = []
    for key in sorted(mind.emotions):
        k, _, who = key.partition("|")
        if k in kinds and who and ":" not in who and mind.emotions[key] >= min_v:
            out.append(who)
    return sorted(set(out))


def _grievance(mind, t):
    return mind.emotion("anger", t) + 0.8 * mind.emotion("envy", t) + 0.8 * mind.emotion("threat", t)


class PublicJab(Action):
    name, label, tone, public = "public_jab", "публично задел", NEG, True

    def candidates(self, ew, ctx, a, club, mind):
        # anyone he feels strongly about: a teammate or someone in another club (a former mate)
        return [(t, None) for t in _felt_targets(mind, ("anger", "envy", "threat"), 12) if ew.player(ctx, t)]

    def available(self, ew, ctx, a, club, t, x):
        return ew.player(ctx, t) is not None

    def utility(self, ew, ctx, a, club, mind, t, x):
        g = _grievance(mind, t)
        rel = ctx.graph.get(a.name, t).friendship / 100
        drive = g / 26 * (0.3 + _p(a, "conflict")) * (0.4 + _p(a, "media"))
        status = 0.5 * mind.goals.get("status", 0) if mind.emotion("envy", t) + mind.emotion("threat", t) > 10 else 0.0
        fear = (1 - _p(a, "risk")) * 0.5 * a.s("coach_trust") / 100
        u = drive + status - fear - rel * 0.9 - a.stat("teamwork") / 250
        why = [f"обида/зависть к {t}: {g:.0f}", f"конфликтность {a.p('conflict'):.0f}", f"медийность {a.p('media'):.0f}"]
        if status:
            why.append(f"хочет быть главным (эго {a.p('ego'):.0f})")
        return u, why

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        tp = ew.player(ctx, t)
        sens = tp.p("criticism") / 50
        ew.st(tp, "morale", -5 * sens), ew.st(tp, "confidence", -3)
        ew.rel(ctx, t, a.name, "resentment", 12), ew.rel(ctx, t, a.name, "irritation", 10)
        ew.fame(a, 1.0 * _p(a, "media"))
        imp = {t: {"pride": -8 * sens, "status": -4}, a.name: {"attention": 3}}
        if ew.club_name(ctx, t) == club.name:
            imp[f"club:{club.name}"] = {"harmony": -5}
        return ew.emit(ctx, "public_jab", actor=a.name, target=t, club=club.name, impacts=imp, causes=causes,
                       reasons=reasons, salience=14 + a.fame / 10, visibility="public",
                       text=f"{a.name} публично задел {t}")


class PrivateConfront(Action):
    name, label, tone = "private_confront", "высказал в лицо", NEG

    def candidates(self, ew, ctx, a, club, mind):
        mates = {q.name for q in _mates(club, a)}
        return [(t, None) for t in _felt_targets(mind, ("anger", "threat")) if t in mates]

    def utility(self, ew, ctx, a, club, mind, t, x):
        g = mind.emotion("anger", t) + 0.5 * mind.emotion("threat", t)
        rel = ctx.graph.get(a.name, t).friendship / 100
        u = g / 28 * (0.3 + _p(a, "conflict")) * (1.1 - 0.5 * _p(a, "media")) - 0.4 * rel - 0.2
        return u, [f"злость на {t}: {g:.0f}", f"конфликтность {a.p('conflict'):.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        tp = ew.player(ctx, t)
        # Talking it out can work: a good communicator and a thick-skinned target settle it.
        p_ok = 1 / (1 + math.exp(-((a.stat("communication") - tp.p("criticism")) / 15 - a.p("conflict") / 60 + 0.3)))
        ok = ctx.rng.random() < p_ok
        mind = ew.minds.of(a.name)
        if ok:
            mind.emotions.pop(f"anger|{t}", None)
            ew.rel(ctx, a.name, t, "irritation", -12), ew.rel(ctx, t, a.name, "irritation", -6)
            ew.rel(ctx, t, a.name, "respect", 5)
            imp, text = {t: {"pride": -2}}, f"{a.name} высказал {t} всё в лицо, и они разобрались"
        else:
            ew.rel(ctx, a.name, t, "resentment", 8), ew.rel(ctx, t, a.name, "resentment", 8)
            ew.rel(ctx, t, a.name, "irritation", 10)
            imp = {t: {"pride": -5}, f"club:{club.name}": {"harmony": -3}}
            text = f"{a.name} высказал {t} претензии, разговор перешёл в ссору"
        return ew.emit(ctx, "private_confront", actor=a.name, target=t, club=club.name, impacts=imp,
                       causes=causes, reasons=reasons + [f"разговор {'удался' if ok else 'не удался'} (шанс {p_ok:.0%})"],
                       salience=6 if ok else 10, witnesses=[t], text=text, data={"ok": ok})


class FreezeOut(Action):
    name, label, tone = "freeze_out", "перестал общаться", NEG

    def candidates(self, ew, ctx, a, club, mind):
        mates = {q.name for q in _mates(club, a)}
        return [(t, None) for t in _felt_targets(mind, ("envy", "anger", "threat")) if t in mates]

    def utility(self, ew, ctx, a, club, mind, t, x):
        g = mind.emotion("envy", t) + 0.8 * mind.emotion("threat", t) + 0.6 * mind.emotion("anger", t)
        u = g / 32 * (1.2 - _p(a, "social_need")) * (0.5 + _p(a, "ego")) \
            * (0.5 + 0.5 * _p(a, "conflict") + 0.5 * (1 - a.stat("teamwork") / 100)) - a.stat("teamwork") / 200
        return u, [f"зависть/злость к {t}: {g:.0f}", f"эго {a.p('ego'):.0f}", f"общительность {a.p('social_need'):.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        tp = ew.player(ctx, t)
        ew.rel(ctx, a.name, t, "friendship", -10), ew.rel(ctx, t, a.name, "friendship", -6)
        ew.rel(ctx, a.name, t, "irritation", 4)
        ew.st(tp, "morale", -3 * (0.5 + _p(tp, "social_need")))
        return ew.emit(ctx, "freeze_out", actor=a.name, target=t, club=club.name, causes=causes, reasons=reasons,
                       impacts={t: {"belonging": -6}, f"club:{club.name}": {"harmony": -3}}, salience=7,
                       witnesses=[q.name for q in club.roster], text=f"{a.name} демонстративно перестал общаться с {t}")


class Outwork(Action):
    """The healthy answer to a threat: train harder and win the place back on the server."""
    name, label, tone = "outwork", "взялся за работу", SELF

    def candidates(self, ew, ctx, a, club, mind):
        return [(t, None) for t in _felt_targets(mind, ("envy", "threat"))] or \
            ([(None, None)] if mind.goals.get("growth", 0) > 0.5 and ctx.rng.random() < 0.05 else [])

    def available(self, ew, ctx, a, club, t, x):
        return a.s("fatigue") < 75

    def utility(self, ew, ctx, a, club, mind, t, x):
        g = (mind.emotion("envy", t) + mind.emotion("threat", t)) if t else 10.0
        drive = g / 45 * (a.stat("discipline") / 100 + _p(a, "ambition")) / 1.2 * (1.1 - 0.5 * _p(a, "conflict"))
        u = drive + 0.4 * mind.goals.get("growth", 0) - a.s("fatigue") / 150
        return u, [f"угроза месту{' от ' + t if t else ''}: {g:.0f}", f"дисциплина {a.stat('discipline'):.0f}",
                   f"амбиции {a.p('ambition'):.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        ew.st(a, "fatigue", 6), ew.st(a, "motivation", 5), ew.st(a, "form", 3)
        mind = ew.minds.of(a.name)
        for k in ("envy", "threat"):
            key = f"{k}|{t or ''}"
            if key in mind.emotions:
                mind.emotions[key] *= 0.5
        gain = ""
        if ctx.rng.random() < 0.35 + a.stat("learning_speed") / 300:
            stat = "game_sense" if a.role in ("igl", "support") else "aim"
            a.stats[stat] = min(100.0, a.stats.get(stat, 50.0) + 0.6)
            gain = f", {stat} +0.6"
        return ew.emit(ctx, "outwork", actor=a.name, target=t, club=club.name, causes=causes, reasons=reasons,
                       impacts={a.name: {"career": 3}}, salience=4, witnesses=[q.name for q in club.roster],
                       text=f"{a.name} остаётся после тренировок" + (f", чтобы не уступить место {t}" if t else "") + gain)


class Mentor(Action):
    name, label, tone = "mentor", "взял под крыло", POS

    def candidates(self, ew, ctx, a, club, mind):
        if a.age < 23 or ctx.rng.random() > 0.04 + mind.goals.get("harmony", 0) * 0.06:
            return []
        return [(q.name, None) for q in _mates(club, a) if q.age <= 21 and a.age >= q.age + 3]

    def utility(self, ew, ctx, a, club, mind, t, x):
        tp = ew.player(ctx, t)
        fr = ctx.graph.get(a.name, t).friendship / 100
        envy = mind.emotion("envy", t) + mind.emotion("threat", t)
        u = (0.6 * (a.stat("leadership") + a.stat("teamwork")) / 100 * (1.1 - 0.7 * _p(a, "ego"))
             + 0.5 * fr + mind.emotion("gratitude", t) / 30 - envy / 18 + 0.2 * (tp.potential - tp.overall()) / 10)
        return u, [f"лидерство {a.stat('leadership'):.0f}", f"эго {a.p('ego'):.0f}", f"{t} молод ({tp.age})"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        tp = ew.player(ctx, t)
        for d in ("friendship", "trust"):
            ew.rel(ctx, a.name, t, d, 6), ew.rel(ctx, t, a.name, d, 7)
        ew.rel(ctx, t, a.name, "leader_loyalty", 6)
        stat = "utility_iq" if ctx.rng.random() < 0.5 else "game_sense"
        tp.stats[stat] = min(100.0, tp.stats.get(stat, 50.0) + 0.5)
        ew.st(tp, "confidence", 4)
        return ew.emit(ctx, "mentor", actor=a.name, target=t, club=club.name, causes=causes, reasons=reasons,
                       impacts={t: {"career": 4, "belonging": 3}, a.name: {"status": 1}}, salience=6,
                       witnesses=[q.name for q in club.roster], text=f"{a.name} взял под крыло молодого {t} ({stat} +0.5)")


class PraisePublicly(Action):
    name, label, tone, public = "praise_publicly", "публично похвалил", POS, True
    cooldown = 26         # praise answered by praise every two months reads as a loop, not a friendship

    def candidates(self, ew, ctx, a, club, mind):
        return [(t, None) for t in _felt_targets(mind, ("gratitude",), 10)]

    def utility(self, ew, ctx, a, club, mind, t, x):
        fr = ctx.graph.get(a.name, t).friendship / 100
        u = mind.emotion("gratitude", t) / 25 + 0.5 * fr * (0.4 + _p(a, "media")) - _grievance(mind, t) / 20
        return u, [f"благодарность {t}: {mind.emotion('gratitude', t):.0f}", f"дружба {fr * 100:.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        tp = ew.player(ctx, t)
        ew.st(tp, "confidence", 5), ew.st(tp, "morale", 3)
        ew.rel(ctx, t, a.name, "friendship", 5), ew.rel(ctx, t, a.name, "respect", 4)
        ew.minds.of(a.name).emotions.pop(f"gratitude|{t}", None)
        return ew.emit(ctx, "praise_publicly", actor=a.name, target=t, club=club.name, causes=causes, reasons=reasons,
                       impacts={t: {"status": 3, "pride": 4}}, salience=7, visibility="public",
                       text=f"{a.name} в интервью: «{t} — лучшее, что случилось с командой»")


def _conflict_pairs(ew, ctx, club, a, min_score=28.0):
    """Pairs of teammates in an open quarrel the actor knows about (by edges and recent facts)."""
    names = [q.name for q in club.roster if q is not a]
    out = []
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            r1, r2 = ctx.graph.get(x, y), ctx.graph.get(y, x)
            heat = max(r1.irritation + r1.resentment, r2.irritation + r2.resentment)
            if heat >= min_score:
                out.append((x, y, heat))
    return out


class Mediate(Action):
    name, label, tone = "mediate", "помирил", POS

    def candidates(self, ew, ctx, a, club, mind):
        if mind.emotion("distress", f"club:{club.name}") < 6 and mind.goals.get("harmony", 0) < 0.45:
            return []
        return [(x, y) for x, y, _ in _conflict_pairs(ew, ctx, club, a)]

    def utility(self, ew, ctx, a, club, mind, t, x):
        g = ctx.graph
        like_t, like_x = g.get(a.name, t).score() / 100, g.get(a.name, x).score() / 100
        heat = max(g.get(t, x).resentment + g.get(t, x).irritation, g.get(x, t).resentment + g.get(x, t).irritation)
        u = (mind.emotion("distress", f"club:{club.name}") / 20 + mind.goals.get("harmony", 0)) * \
            (0.3 + a.stat("leadership") / 100) + heat / 120 - abs(like_t - like_x) * 1.5 - 0.3
        return u, [f"переживает за команду ({mind.emotion('distress', f'club:{club.name}'):.0f})",
                   f"лидерство {a.stat('leadership'):.0f}", f"накал между {t} и {x}: {heat:.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        g = ctx.graph
        tp, xp = ew.player(ctx, t), ew.player(ctx, x)
        heat = (g.get(t, x).resentment + g.get(x, t).resentment) / 2
        z = (a.stat("leadership") + a.stat("communication")) / 100 - (tp.p("conflict") + xp.p("conflict") + tp.p("ego") + xp.p("ego")) / 400 \
            + (g.get(t, a.name).respect + g.get(x, a.name).respect) / 200 - heat / 80 - 0.4
        p_ok = 1 / (1 + math.exp(-3 * z))
        ok = ctx.rng.random() < p_ok
        if ok:
            for u, v in ((t, x), (x, t)):
                ew.rel(ctx, u, v, "irritation", -15), ew.rel(ctx, u, v, "resentment", -10)
                ew.rel(ctx, u, a.name, "respect", 6)
            imp = {f"club:{club.name}": {"harmony": 6}, t: {"belonging": 2}, x: {"belonging": 2}, a.name: {"status": 2}}
            text = f"{a.name} помирил {t} и {x}"
        else:
            worse = t if g.get(t, a.name).score() < g.get(x, a.name).score() else x
            ew.rel(ctx, worse, a.name, "irritation", 8)
            imp = {f"club:{club.name}": {"harmony": -1}}
            text = f"{a.name} пытался помирить {t} и {x}, но {worse} не стал слушать"
        return ew.emit(ctx, "mediate", actor=a.name, target=t, third=x, club=club.name, impacts=imp, causes=causes,
                       reasons=reasons + [f"шанс примирения {p_ok:.0%}"], salience=9 if ok else 6,
                       witnesses=[q.name for q in club.roster], text=text, data={"ok": ok})


class SideWith(Action):
    name, label, tone = "side_with", "встал на сторону", NEG

    def candidates(self, ew, ctx, a, club, mind):
        out = []
        for x, y, _ in _conflict_pairs(ew, ctx, club, a, 30.0):
            out += [(x, y), (y, x)]   # (who he backs, against whom)
        return out

    def utility(self, ew, ctx, a, club, mind, t, x):
        g = ctx.graph
        diff = (g.get(a.name, t).friendship - g.get(a.name, x).friendship) / 100 + (mind.opinion(t) - mind.opinion(x)) / 150
        u = diff * 1.6 + mind.emotion("anger", x) / 25 + 0.3 * _p(a, "conflict") - 0.6 * mind.goals.get("harmony", 0) - 0.25
        return u, [f"дружит с {t} больше, чем с {x} ({diff * 100:+.0f})", f"злость на {x}: {mind.emotion('anger', x):.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        ew.rel(ctx, a.name, t, "friendship", 6), ew.rel(ctx, t, a.name, "friendship", 6)
        ew.rel(ctx, x, a.name, "resentment", 8), ew.rel(ctx, a.name, x, "irritation", 6)
        return ew.emit(ctx, "side_with", actor=a.name, target=x, third=t, club=club.name, causes=causes, reasons=reasons,
                       impacts={t: {"belonging": 4}, x: {"belonging": -5, "pride": -2}, f"club:{club.name}": {"harmony": -3}},
                       salience=8, witnesses=[q.name for q in club.roster],
                       text=f"{a.name} встал на сторону {t} в конфликте с {x}")


class Reconcile(Action):
    name, label, tone = "reconcile", "пошёл на примирение", POS
    cooldown = 20

    def candidates(self, ew, ctx, a, club, mind):
        mates = {q.name for q in _mates(club, a)}
        out = {m.about for m in mind.memories if m.valence <= -15 and m.about in mates}
        out |= {q for q in mates if ctx.graph.get(a.name, q).resentment >= 22 or ctx.graph.get(q, a.name).resentment >= 22}
        return [(t, None) for t in sorted(out)]

    def utility(self, ew, ctx, a, club, mind, t, x):
        crisis = ew.tension(club.name) / 30
        u = (0.5 * (_p(a, "loyalty") + _p(a, "social_need")) + 0.7 * mind.goals.get("harmony", 0) + 0.4 * crisis
             - 0.7 * _p(a, "ego") - mind.emotion("anger", t) / 25 - 0.25)
        return u, [f"лояльность {a.p('loyalty'):.0f}", f"эго {a.p('ego'):.0f}", f"злость на {t}: {mind.emotion('anger', t):.0f}"] + \
            ([f"команда устала от ссор (напряжение {ew.tension(club.name):.0f})"] if crisis > 0.3 else [])

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        tp = ew.player(ctx, t)
        tm = ew.minds.of(t)
        forgive = (100 - tp.p("conflict") + tp.p("loyalty") - 0.6 * tp.p("ego")) / 100 - tm.emotion("anger", a.name) / 60 \
            + tm.opinion(a.name) / 200
        ok = ctx.rng.random() < 1 / (1 + math.exp(-3 * (forgive - 0.45)))
        if ok:
            for u, v in ((a.name, t), (t, a.name)):
                ew.rel(ctx, u, v, "resentment", -15), ew.rel(ctx, u, v, "irritation", -12), ew.rel(ctx, u, v, "friendship", 5)
            tm.emotions.pop(f"anger|{a.name}", None)
            for m, other in ((ew.minds.of(a.name), t), (tm, a.name)):    # forgiven, not forgotten
                for mem in m.memories:
                    if mem.about == other and mem.valence < 0:
                        mem.valence *= 0.4
            imp = {f"club:{club.name}": {"harmony": 4}, t: {"belonging": 3, "pride": 2}, a.name: {"belonging": 3}}
            text = f"{a.name} и {t} помирились"
        else:
            imp = {a.name: {"pride": -3}}
            text = f"{a.name} протянул руку {t}, но тот отказался мириться"
        return ew.emit(ctx, "reconcile", actor=a.name, target=t, club=club.name, impacts=imp, causes=causes,
                       reasons=reasons + [f"готовность {t} простить {forgive:.2f}"], salience=10 if ok else 6,
                       witnesses=[q.name for q in club.roster], text=text, data={"ok": ok})


class Complain(Action):
    """Take it to management instead of settling it yourself: the manager gets a situation."""
    name, label, tone = "complain", "пожаловался руководству", NEG

    def candidates(self, ew, ctx, a, club, mind):
        mates = {q.name for q in _mates(club, a)}
        return [(t, None) for t in _felt_targets(mind, ("anger", "envy", "threat"), 10) if t in mates]

    def available(self, ew, ctx, a, club, t, x):
        return ew.open_situation(club.name, a.name, t) is None

    def utility(self, ew, ctx, a, club, mind, t, x):
        trust = a.s("coach_trust") / 100
        mgr = ew.manager_id(ctx, club)
        burnt = mind.opinion(mgr) < -20
        u = _grievance(mind, t) / 30 * trust * (1.1 - 0.5 * _p(a, "conflict")) + \
            (0.5 if a.s("role_satisfaction") < 45 else 0.0) - (1.5 if burnt else 0.0) - 0.15
        why = [f"обида на {t}: {_grievance(mind, t):.0f}", f"доверие тренеру {a.s('coach_trust'):.0f}"]
        if burnt:
            why.append("руководство уже было против него")
        return u, why

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        f = ew.emit(ctx, "complain", actor=a.name, target=t, club=club.name, causes=causes, reasons=reasons,
                    impacts={t: {"status": -1}}, salience=8, witnesses=[f"club:{club.name}"],
                    text=f"{a.name} пришёл к руководству с претензиями к {t}")
        return f


class SeekSpotlight(Action):
    name, label, tone, public = "seek_spotlight", "пошёл в медиа", SELF, True

    def candidates(self, ew, ctx, a, club, mind):
        if a.p("media") < 55:
            return []
        rival = _felt_targets(mind, ("envy",), 12)
        return [(None, rival[0] if rival else None)] if rival or ctx.rng.random() < 0.04 else []

    def utility(self, ew, ctx, a, club, mind, t, x):
        envy = mind.emotion("envy", x) if x else 0.0
        u = 0.8 * mind.goals.get("attention", 0) + envy / 30 * _p(a, "media") + 0.3 * mind.goals.get("status", 0) - 0.3
        return u, [f"медийность {a.p('media'):.0f}"] + ([f"не хочет уступать внимание {x}"] if x else [])

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        ew.fame(a, 2.0 * _p(a, "media") + 0.5)
        ew.st(a, "fatigue", 2)
        return ew.emit(ctx, "seek_spotlight", actor=a.name, club=club.name, causes=causes, reasons=reasons,
                       impacts={a.name: {"attention": 4, "status": 2}}, salience=6, visibility="public",
                       text=f"{a.name} всю неделю стримит и раздаёт интервью")


class AskToLeave(Action):
    """Grudges, not only role unhappiness (that path lives in world.py), can push a player out."""
    name, label, tone = "ask_to_leave", "попросил трансфер", NEG

    def candidates(self, ew, ctx, a, club, mind):
        if "transfer_requested" in a.flags:
            return []
        mates = {q.name for q in club.roster} | {ew.manager_id(ctx, club)}
        bad = sum(-m.valence * m.strength / 100 for m in mind.grudges(-20) if m.about in mates)
        return [(None, None)] if bad >= 30 else []

    def utility(self, ew, ctx, a, club, mind, t, x):
        mates = {q.name for q in club.roster} | {ew.manager_id(ctx, club)}
        g = mind.grudges(-20)
        bad = sum(-m.valence * m.strength / 100 for m in g if m.about in mates)
        u = bad / 60 + (0.4 if a.s("role_satisfaction") < 40 else 0) - 0.9 * _p(a, "loyalty") \
            - 0.5 * mind.goals.get("stability", 0) - 0.2
        who = sorted({m.about for m in g if m.about in mates})[:3]
        return u, [f"накопленные обиды ({bad:.0f}) на: {', '.join(who)}", f"лояльность {a.p('loyalty'):.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        a.flags.add("transfer_requested")
        mind = ew.minds.of(a.name)
        mates = {q.name for q in club.roster} | {ew.manager_id(ctx, club)}
        causes = list(causes) + [m.fact for m in mind.grudges(-20) if m.about in mates][:3]
        return ew.emit(ctx, "ask_to_leave", actor=a.name, club=club.name, causes=causes, reasons=reasons,
                       impacts={f"club:{club.name}": {"harmony": -3}, a.name: {"career": 2}}, salience=12 + a.fame / 5,
                       witnesses=[f"club:{club.name}"] + [q.name for q in club.roster],
                       text=f"{a.name} попросил выставить его на трансфер: в клубе ему больше не рады")


class LeakToPress(Action):
    name, label, tone = "leak", "слил прессе", NEG

    def candidates(self, ew, ctx, a, club, mind):
        if a.p("media") < 40 or not ew.journalists_in(club.region):
            return []
        out = []
        for t in _felt_targets(mind, ("anger",), 14):
            f = ew.leakable(a.name, t, club.name, ctx.week)
            if f is not None:
                out.append((t, str(f.id)))
        return out

    def utility(self, ew, ctx, a, club, mind, t, x):
        mgr = ew.manager_id(ctx, club)
        u = mind.emotion("anger", t) / 20 * _p(a, "media") * (1.2 - _p(a, "loyalty")) \
            + (0.4 if mind.opinion(mgr) < -20 else 0.0) - (1 - _p(a, "risk")) * 0.4 - 0.1
        return u, [f"злость на {t}: {mind.emotion('anger', t):.0f}", f"лояльность {a.p('loyalty'):.0f}",
                   f"склонность к риску {a.p('risk'):.0f}"]

    def execute(self, ew, ctx, a, club, t, x, causes, reasons):
        fid = int(x)
        j = ew.pick_journalist(club.region, ctx.rng)
        f = ew.emit(ctx, "leak", actor=a.name, target=t, club=club.name, causes=list(causes) + [fid], reasons=reasons,
                    salience=5, visibility="private", witnesses=[j.id],
                    text=f"{a.name} анонимно рассказал журналисту {j.name} о том, что происходит в {club.name}",
                    data={"journalist": j.id, "about": fid})
        ew.facts.learn(j.id, fid, ctx.week, f"источник в {club.name}")
        j.tips.append(fid)
        return f


ALL = [PublicJab(), PrivateConfront(), FreezeOut(), Outwork(), Mentor(), PraisePublicly(), Mediate(), SideWith(),
       Reconcile(), Complain(), SeekSpotlight(), AskToLeave(), LeakToPress()]
BY_NAME = {a.name: a for a in ALL}
