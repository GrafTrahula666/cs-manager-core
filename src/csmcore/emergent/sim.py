"""The Emergent World Engine: one weekly pass that turns circumstances into decisions and
decisions into new circumstances.

    observe     notice what the older systems did (transfers, titles, conflicts, storylets,
                stars, exposed secrets, standout games) and record it as facts with causes
    press       journalists publish what they were told or dug up, sometimes getting it wrong
    spread      people tell friends, the assistant notices, the manager is told
    appraise    everyone who learned something new feels something about it (appraisal.py)
    decide      people with something on their mind weigh the universal actions (actions.py)
                against doing nothing; emotions add noise, so people sometimes misjudge
    act         the chosen actions change the world and become facts for next week
    manage      facts that reach a club's staff become situations for its manager
    forget      emotions fade, memories weaken, old unimportant facts are pruned

Natural limits keep the world from snowballing into a conflict generator: one deliberate act per
person a week, cooldowns per act and target, a drama budget per club, crisis fatigue (a team that
has fought a lot is tired of it and leans toward repair), and a hard cap on causal chain depth.

Randomness comes from its own stream per week (seeded by the world seed and the week), so
adding this engine never reshuffles matches, and a loaded game continues identically.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import actions as A
from .appraisal import appraise
from .facts import HISTORIC, PUBLIC, FactLog
from .minds import Intention, Minds, goals_for

REST_UTILITY = 0.8          # doing nothing is always an option
MAX_CHAIN_DEPTH = 9         # facts this deep in a chain no longer make anyone act
DEPTH_DAMP = 0.88           # every link makes the next harmful act less likely
NEG_PER_WEEK = 1            # drama budget per club: one harmful act a week,
NEG_PER_WINDOW = 3          # three in NEG_WINDOW weeks,
NEG_WINDOW = 6
NEG_PER_TARGET = 2          # and nobody takes more than two hits in that window
ACTOR_NEG_REST = 3          # weeks a person needs before another harmful act
COOLDOWN = 8                # weeks before the same act at the same person
CRISIS_TENSION = 16.0       # above this a club is tired of fighting
AROUSAL = 12.0              # emotion needed to start weighing actions
FACTS_PER_CLUB_WEEK = 6     # hard safety cap for engine-made facts
SITUATION_COOLDOWN = 6
MAX_OPEN_SITUATIONS = 2
REPORTS_KEEP = 40
ASSISTANT_KNOWLEDGE = 0.7

JOURNALIST_NAMES = ["Марк Ветров", "Ольга Лис", "Daniel Brook", "Ирина Сокол", "Lukas Hahn", "Ana Ribeiro",
                    "Тимур Кеш", "Sofia Marin", "Kenji Arai", "Вера Гром", "Jonas Berg", "Lea Moreau"]


@dataclass
class Journalist:
    id: str
    name: str
    region: str
    accuracy: float       # 0..100: how often a story is told right
    sensation: float      # 0..100: how hard they dig and how loud they print
    credibility: float = 50.0
    tips: list[int] = field(default_factory=list)
    published: list[int] = field(default_factory=list)


@dataclass
class Report:
    week: int
    fact: int
    text: str
    how: str
    believed: bool = True     # False when the club's version differs from what really happened


@dataclass
class Situation:
    id: int
    week: int
    club: str
    kind: str                 # conflict | complaint | leak
    fact: int
    a: str | None
    b: str | None
    text: str
    how: str
    options: list[dict]
    choice: str | None = None
    outcome: list[str] = field(default_factory=list)
    by: str = ""


@dataclass
class WeekCtx:
    """Per-week view of the world; never saved."""
    clubs: list
    graph: object
    week: int
    season: int
    rng: random.Random
    sysm: object = None
    manager_club: str | None = None
    index: dict = field(default_factory=dict)        # name -> (Player, Club | None)
    played: set = field(default_factory=set)         # clubs with a match this week
    events: list = field(default_factory=list)       # world.Event
    stories: list = field(default_factory=list)      # storylets.Fired


class EmergentWorld:
    def __init__(self, seed: int, regions=("EU", "CIS", "NA", "SA", "ASIA", "OCE")) -> None:
        self.seed = seed
        self.facts = FactLog()
        self.minds = Minds()
        rng = random.Random(f"emergent-init:{seed}")
        names = list(JOURNALIST_NAMES)
        rng.shuffle(names)
        self.journalists: list[Journalist] = []
        for i, region in enumerate(sorted(regions)):
            for k in range(2):
                n = names[(2 * i + k) % len(names)]
                self.journalists.append(Journalist(f"press:{2 * i + k}", n, region,
                                                   rng.uniform(45, 95), rng.uniform(20, 90)))
        self.situations: list[Situation] = []
        self.next_situation = 1
        self.reports: dict[str, list[Report]] = {}
        self.prov: dict[str, list[int]] = {}
        self._pend: list[str] = []
        self.where: dict[str, str | None] = {}        # person -> club name last week
        self.stars: set[str] = set()
        self.exposed: set[tuple] = set()
        self.retired_seen = 0
        self.kills: dict[str, int] = {}
        self.harmony_log: dict[str, list[tuple[int, float]]] = {}
        self.neg_log: dict[str, list[int]] = {}
        self.pair_situation: dict[str, int] = {}
        self.order_until: dict[str, int] = {}          # club -> week: discipline deters drama
        self.learned: list[tuple[str, int]] = []       # (holder, fact) learned this week
        self.made_this_week: dict[str, int] = {}
        self.counts: dict[str, int] = {}               # fact kind -> total, for the soak tests
        self.retrospectives: list[int] = []
        self.capped = 0
        self.narrator = None                           # optional narrate.Narrator for texts
        self.ctx: WeekCtx | None = None                # open week, never saved between weeks

    # ================= helpers used by actions =================
    def player(self, ctx: WeekCtx, name: str | None):
        if not name:
            return None
        hit = ctx.index.get(name)
        return hit[0] if hit else None

    def club_name(self, ctx: WeekCtx, name: str) -> str | None:
        hit = ctx.index.get(name)
        return hit[1].name if hit and hit[1] is not None else None

    def manager_id(self, ctx: WeekCtx, club) -> str:
        careers = getattr(ctx.sysm, "careers", None)
        m = careers.managers.get(club.name) if careers is not None else None
        return f"mgr:{m.name}" if m is not None else f"mgr:{club.name}"

    def st(self, p, key: str, delta: float) -> None:
        p.state[key] = max(0.0, min(100.0, p.s(key) + delta))
        self._pend.append(f"s|{p.name}|{key}")

    def rel(self, ctx: WeekCtx, a: str, b: str, dim: str, delta: float) -> None:
        ctx.graph.nudge(a, b, dim, delta)
        self._pend.append(f"r|{a}|{b}|{dim}")

    def fame(self, p, delta: float) -> None:
        p.fame = max(0.0, p.fame + delta)

    def tension(self, club: str) -> float:
        return sum(-d for _, d in self.harmony_log.get(club, []) if d < 0)

    def journalists_in(self, region: str) -> list[Journalist]:
        return [j for j in self.journalists if j.region == region]

    def pick_journalist(self, region: str, rng: random.Random) -> Journalist:
        js = self.journalists_in(region) or self.journalists
        return max(js, key=lambda j: j.sensation + rng.random() * 30)

    def leakable(self, actor: str, target: str, club: str, week: int):
        """A recent internal fact that makes `target` look bad and that `actor` knows."""
        best = None
        for fid in reversed(self.facts.by_person.get(target, [])[-12:]):
            f = self.facts.get(fid)
            if f is None or f.week < week - 8 or f.club != club or f.visibility == "public" or f.kind == "leak":
                continue
            if not f.known_by(actor) or f.actor != target:
                continue
            if any(d < 0 for imp in f.impacts.values() for d in imp.values()):
                if best is None or f.salience > best.salience:
                    best = f
        return best

    def prov_causes(self, keys) -> list[int]:
        out = []
        for k in keys:
            out += [i for i in self.prov.get(k, []) if i in self.facts.facts]
        return sorted(set(out))[-4:]

    def open_situation(self, club: str, a: str | None, b: str | None) -> Situation | None:
        for s in self.situations:
            if s.club == club and s.choice is None and {s.a, s.b} & {a, b} and (b is None or {s.a, s.b} == {a, b}):
                return s
        return None

    # ================= facts =================
    def emit(self, ctx: WeekCtx, kind: str, *, witnesses=(), engine_made: bool = True, **kw):
        f = self.facts.add(ctx.week, ctx.season, kind, max_depth=MAX_CHAIN_DEPTH if engine_made else None, **kw)
        for key in self._pend:
            lst = self.prov.setdefault(key, [])
            lst.append(f.id)
            del lst[:-3]
        self._pend = []
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if engine_made and f.club:
            self.made_this_week[f.club] = self.made_this_week.get(f.club, 0) + 1
        for who, imp in f.impacts.items():
            if who.startswith("club:") and imp.get("harmony"):
                self.harmony_log.setdefault(who[5:], []).append((ctx.week, imp["harmony"]))
        holders = set(f.people()) | set(witnesses)
        for h in sorted(holders):
            if self.facts.learn(h, f.id, ctx.week, "был там" if h in f.people() else "видел сам"):
                self.learned.append((h, f.id))
        if f.visibility == "public":
            for h in sorted(self._public_observers(ctx, f)):
                self.learned.append((h, f.id))
        if self.narrator is not None and not f.text:
            f.text = self.narrator.describe(f)
        return f

    def _public_observers(self, ctx: WeekCtx, f) -> set[str]:
        out = set(f.people())
        clubs = {self.club_name(ctx, p) for p in f.people()} | ({f.club} if f.club else set())
        for c in ctx.clubs:
            if c.name in clubs:
                out |= {q.name for q in c.roster}
                out.add(f"club:{c.name}")
        return out

    # ================= the weekly pass =================
    def begin(self, clubs, graph, week: int, season: int, sysm=None, manager_club: str | None = None,
              open_week: bool = True) -> WeekCtx:
        """Open a week: the context lives until week() closes it (matches report into it).
        With open_week=False it is a context for one manager decision between weeks."""
        seed = f"emergent:{self.seed}:{week}" + ("" if open_week else f":desk:{self.facts.next_id}")
        ctx = WeekCtx(clubs, graph, week, season, random.Random(seed), sysm, manager_club)
        self._index(ctx)
        if open_week:
            self.ctx = ctx
        return ctx

    def week(self, ctx: WeekCtx) -> list[str]:
        self.made_this_week = {}
        self._index(ctx)
        if self.narrator is not None and hasattr(self.narrator, "known"):
            self.narrator.known |= set(ctx.index)
        notes: list[str] = []
        self.observe(ctx)
        self.press(ctx)
        self.spread(ctx)
        self.appraise_all(ctx)
        if ctx.week % 4 == 0:
            self.refresh_goals(ctx)
        acts = self.decide_and_act(ctx)
        self.appraise_all(ctx)     # people react this week to what they saw happen
        notes += self.manage(ctx)
        self.forget(ctx)
        if acts:
            notes += [f.text for f in acts]
        self.ctx = None
        return notes

    def _index(self, ctx: WeekCtx) -> None:
        idx = {}
        market = getattr(ctx.sysm, "market", None)
        if market is not None:
            for p in market.free_agents:
                idx[p.name] = (p, None)
        for c in ctx.clubs:
            for p in c.roster:
                idx[p.name] = (p, c)
        ctx.index = idx

    # ---------- observe the older systems ----------
    def observe(self, ctx: WeekCtx) -> None:
        week, season = ctx.week, ctx.season
        clubs_now = {c.name: c for c in ctx.clubs}
        now = {p.name: c.name for c in ctx.clubs for p in c.roster}
        legacy = getattr(ctx.sysm, "legacy", None)
        retired = {r.player.name for r in legacy.retired[self.retired_seen:]} if legacy else set()
        if legacy:
            for r in legacy.retired[self.retired_seen:]:
                p = r.player
                sal = min(80.0, 6 + p.fame * 0.6 + len(self.facts.of_person(p.name, ("title",))) * 6)
                titles = [f.id for f in self.facts.of_person(p.name, ("title",))][-3:]
                self.emit(ctx, "retired", actor=p.name, club=self.where.get(p.name), causes=titles,
                          reasons=[f"возраст {p.age}", f"слава {p.fame:.0f}"], salience=sal, visibility="public",
                          engine_made=False, text=f"{p.name} завершил карьеру ({p.age} лет), дальше: {r.second_career}")
            self.retired_seen = len(legacy.retired)
        if not getattr(self, "_primed", False):   # first look at the world: nothing "happened" yet
            self.where, self._primed = now, True
            self.stars = {p.name for c in ctx.clubs for p in c.roster if "star" in p.flags}
        renamed = self._renames(clubs_now, now)
        for name in sorted(set(self.where) | set(now)):
            c0, c1 = self.where.get(name), now.get(name)
            if c0 == c1 or name in retired:
                continue
            if c0 is not None and renamed.get(c0) == c1:
                continue
            hit = ctx.index.get(name)
            if hit is None and c1 is None:
                continue
            p = hit[0] if hit else None
            if p is None:
                continue
            if c1 is None:
                gone = c0 not in clubs_now
                self.emit(ctx, "released", actor=name, club=c0, salience=4 + p.fame / 6, engine_made=False,
                          causes=self._why_left(ctx, p, c0), visibility="public",
                          text=f"{name} покинул {c0}" + (" после закрытия клуба" if gone else ""))
                continue
            if c0 is None:
                first = not self.facts.of_person(name, ("signed", "transfer", "debut"))
                kind = "debut" if first and p.age <= 20 else "signed"
                self.emit(ctx, kind, actor=name, target=f"club:{c1}", club=c1, visibility="public",
                          salience=3 + p.fame / 6, engine_made=False, impacts={name: {"career": 3}},
                          text=(f"{name} ({p.age}) дебютирует в профессиональном составе {c1}" if kind == "debut"
                                else f"{name} подписал контракт с {c1}"))
                continue
            ovr = p.overall()
            sal = min(85.0, 8 + p.fame * 0.6 + max(0.0, ovr - 72) * 2)
            causes = self._why_left(ctx, p, c0)
            f = self.emit(ctx, "transfer", actor=name, target=f"club:{c1}", third=None, club=c1,
                          data={"from": c0, "to": c1}, impacts={name: {"career": 4}, f"club:{c0}": {"harmony": -1}},
                          causes=causes, reasons=[f"уровень {ovr:.0f}", f"слава {p.fame:.0f}"],
                          salience=sal, visibility="public", engine_made=False,
                          text=f"{name} перешёл из {c0} в {c1}")
            mind = self.minds.of(name)
            bitter = sum(-m.valence * m.strength / 100 for m in mind.grudges(-20)
                         if m.about in {q for q, cl in self.where.items() if cl == c0} or m.about.startswith("mgr:"))
            mind.remember(f.id, f"club:{c0}", "left", -min(100.0, bitter) if bitter > 15 else 15.0, week)
            if bitter > 25:
                mind.goals[f"beat|{c0}"] = round(min(1.0, bitter / 80), 3)
        self.where = now

        for c in ctx.clubs:
            for p in c.roster:
                if "star" in p.flags and p.name not in self.stars:
                    self.stars.add(p.name)
                    young = p.age <= 21
                    self.emit(ctx, "became_star", actor=p.name, club=c.name, visibility="public", engine_made=False,
                              impacts={p.name: {"status": 10, "attention": 8}}, salience=30 + (10 if young else 0),
                              causes=[x.id for x in self.facts.of_person(p.name, ("standout", "title"))][-2:],
                              reasons=[f"уровень {p.overall():.1f}", f"возраст {p.age}"],
                              text=f"★ {p.name} ({p.age}) стал звездой {c.name}")
                elif "star" not in p.flags and p.name in self.stars:
                    self.stars.discard(p.name)
        secrets = getattr(ctx.sysm, "secrets", None)
        if secrets is not None:
            for s in secrets.items:
                key = (s.player, s.kind, s.week)
                if s.exposed and key not in self.exposed:
                    self.exposed.add(key)
                    hit = ctx.index.get(s.player)
                    club = hit[1].name if hit and hit[1] else None
                    self.emit(ctx, "secret_exposed", actor=s.player, club=club, visibility="public", engine_made=False,
                              impacts={s.player: {"pride": -10, "status": -6}, **({f"club:{club}": {"harmony": -4}} if club else {})},
                              salience=12 + 8 * s.severity, text=f"Всплыл секрет {s.player}: {s.kind}")
            if len(self.exposed) > 400:
                self.exposed = set(sorted(self.exposed, key=lambda k: k[2])[-200:])
        for e in ctx.events:
            self._observe_event(ctx, e)
        for fired in ctx.stories:
            self._observe_story(ctx, fired)

    def _renames(self, clubs_now: dict, now: dict) -> dict:
        """Old club name -> new name when an investor renamed a club (the roster moved as a block)."""
        gone = {c for c in set(self.where.values()) if c and c not in clubs_now}
        out = {}
        for old in sorted(gone):
            members = [n for n, c in self.where.items() if c == old]
            dest = [now.get(n) for n in members if now.get(n)]
            if dest and len(dest) >= max(3, len(members) * 0.6):
                best = max(set(dest), key=dest.count)
                if dest.count(best) >= len(members) * 0.6:
                    out[old] = best
        return out

    def _why_left(self, ctx: WeekCtx, p, old: str | None) -> list[int]:
        reqs = [f.id for f in self.facts.of_person(p.name, ("ask_to_leave", "transfer_request"))
                if f.week >= ctx.week - 60][-1:]
        mind = self.minds.of(p.name)
        grudges = [m.fact for m in mind.grudges(-25)][:2]
        return reqs + grudges

    def _observe_event(self, ctx: WeekCtx, e) -> None:
        if e.kind == "conflict" and len(e.who) == 2:
            a, b = e.who
            club = self.club_name(ctx, a)
            causes = self.prov_causes([f"r|{a}|{b}|irritation", f"r|{a}|{b}|resentment", f"r|{b}|{a}|resentment"])
            m = self.minds.of(a)
            causes += m.causes_of("anger", b) + m.causes_of("envy", b) + m.causes_of("threat", b)
            hit = ctx.index.get(a)
            self.emit(ctx, "open_conflict", actor=a, target=b, club=club, causes=causes[-5:], reasons=e.causes[:4],
                      impacts={b: {"pride": -5}, **({f"club:{club}": {"harmony": -5}} if club else {})},
                      salience=10, engine_made=False, text=e.text,
                      witnesses=[q.name for q in hit[1].roster] if hit and hit[1] else ())
        elif e.kind == "transfer_request" and e.who:
            a = e.who[0]
            club = self.club_name(ctx, a)
            causes = self.prov_causes([f"s|{a}|role_satisfaction", f"s|{a}|morale", f"s|{a}|coach_trust"])
            causes += [m.fact for m in self.minds.of(a).grudges(-25)][:2]
            hit = ctx.index.get(a)
            self.emit(ctx, "transfer_request", actor=a, club=club, causes=causes, reasons=e.causes[:4],
                      impacts={f"club:{club}": {"harmony": -2}} if club else {}, salience=10, engine_made=False,
                      text=e.text, witnesses=([f"club:{club}"] + [q.name for q in hit[1].roster]) if hit and hit[1] else ())
        elif e.kind == "bankruptcy":
            self.emit(ctx, "bankruptcy", actor=f"club:{e.who[0]}", club=e.who[0], salience=40, visibility="public",
                      engine_made=False, reasons=e.causes[:3], text=e.text)

    def _observe_story(self, ctx: WeekCtx, fired) -> None:
        stories = getattr(ctx.sysm, "stories", None)
        ev = stories.events.get(fired.event_id, {}) if stories is not None else {}
        a, b = fired.a.name if fired.a else None, fired.b.name if fired.b else None
        keys = []
        for c in ev.get("when", []):
            who = b if c.get("who") == "b" else a
            if who and "state" in c:
                keys.append(f"s|{who}|{c['state']}")
            if a and b and "rel" in c:
                keys.append(f"r|{a}|{b}|{c['rel']}")
        causes = self.prov_causes(keys)
        if a and "продолжение цепочки" in fired.why:
            prev = [f.id for f in self.facts.of_person(a, ("story",)) if f.week >= ctx.week - 30]
            causes += prev[-1:]
        tone = ev.get("tone", "neutral")
        club = fired.club.name
        effects = list(ev.get("effects", []))
        if fired.choice is not None and ev.get("options"):
            effects += ev["options"][fired.choice].get("effects", [])
        imp = story_impacts(effects, a, b, club)
        self.emit(ctx, "story", actor=a, target=b, club=club, data={"event": fired.event_id, "tone": tone},
                  causes=causes, reasons=list(fired.why[:4]), impacts=imp, engine_made=False,
                  salience=8 if ev.get("chain_only") else 4, witnesses=[q.name for q in fired.club.roster],
                  text=fired.title)

    # ---------- matches (called from season.run_tournament) ----------
    def on_series(self, ctx: WeekCtx, t, stage: str, a, b, winner, score: str) -> None:
        ctx.played |= {a.name, b.name}
        loser = b if winner is a else a
        standouts = []
        for club in (a, b):
            line = club.lineup()
            deltas = {}
            for p in line:
                st = p.__dict__.get("season_stats")
                k = st["kills"] if st else 0
                before = self.kills.get(p.name)
                # season stats reset each season; a newcomer's count may come from his old club
                deltas[p.name] = 0 if before is None else k if k < before else k - before
                self.kills[p.name] = k
            avg = sum(deltas.values()) / max(1, len(deltas))
            best = max(line, key=lambda p: (deltas[p.name], p.name))
            if deltas[best.name] >= max(14, 1.3 * avg):
                standouts.append((club, best, deltas[best.name], avg))
        major = bool(getattr(t, "major", False))
        decisive = stage in ("semi", "final")
        sf = None
        if decisive:
            sf = self.emit(ctx, "series", actor=f"club:{winner.name}", target=f"club:{loser.name}", club=winner.name,
                           data={"tournament": t.name, "stage": stage, "score": score, "major": major},
                           salience=(28 if major else 16) if stage == "final" else 6, visibility="public",
                           engine_made=False, text=f"{t.name}, {'финал' if stage == 'final' else 'полуфинал'}: {score}")
        for club, p, k, avg in standouts:
            attention = 2 + (5 if stage == "final" else 2 if decisive else 0) + (3 if major else 0)
            if p.age <= 20 and p.fame < 15:
                attention *= 1.6      # nobody expected the kid
            self.fame(p, attention / 3)
            self.emit(ctx, "standout", actor=p.name, club=club.name, causes=[sf.id] if sf else [],
                      data={"tournament": t.name, "kills": k, "stage": stage},
                      impacts={p.name: {"status": attention * 0.8, "attention": attention}},
                      reasons=[f"{k} убийств при среднем по команде {avg:.0f}", f"возраст {p.age}, слава до матча {p.fame:.0f}"],
                      salience=4 + attention * 1.5, visibility="public", engine_made=False,
                      text=f"{p.name} ({p.age}) разнёс {('финал ' if stage == 'final' else '')}{t.name}: {k} убийств")
        if decisive:
            for p in winner.lineup():
                if loser.name not in p.former_clubs:
                    continue
                mind = self.minds.of(p.name)
                left = [f.id for f in self.facts.of_person(p.name, ("transfer", "released"))
                        if (f.data.get("from") == loser.name or f.club == loser.name)]
                bitter = mind.goals.pop(f"beat|{loser.name}", 0.0) if stage == "final" else mind.goals.get(f"beat|{loser.name}", 0.0)
                sal = (45 if major else 30) if stage == "final" else 12
                self.emit(ctx, "beat_former_club", actor=p.name, target=f"club:{loser.name}", club=winner.name,
                          causes=([sf.id] if sf else []) + left[-1:] + [m.fact for m in mind.grudges(-25)][:1],
                          impacts={p.name: {"pride": 6 + 10 * bitter}}, salience=sal + 15 * bitter, visibility="public",
                          data={"tournament": t.name, "stage": stage, "bitter": bitter}, engine_made=False,
                          reasons=[f"ушёл из {loser.name}"] + (["личные счёты"] if bitter else []),
                          text=f"{p.name} обыграл свой бывший клуб {loser.name} в {t.name}" +
                               (" и взял реванш" if bitter else ""))

    def on_title(self, ctx: WeekCtx, t, club) -> None:
        major = bool(getattr(t, "major", False))
        final = [f.id for f in self.facts.recent(ctx.week) if f.kind == "series" and f.club == club.name][-1:]
        stand = [f.id for f in self.facts.recent(ctx.week) if f.kind == "standout" and f.club == club.name][-2:]
        imp = {p.name: {"status": 5, "pride": 5} for p in club.lineup()}
        imp[f"club:{club.name}"] = {"harmony": 5}
        self.emit(ctx, "title", actor=f"club:{club.name}", club=club.name, causes=final + stand, impacts=imp,
                  data={"tournament": t.name, "major": major, "lineup": [p.name for p in club.lineup()]},
                  salience=60 if major else 36, visibility="public", engine_made=False,
                  text=f"{club.name} выигрывает {t.name}")
        # people() covers actor/target/third only: index the lineup for their careers
        f = self.facts.get(self.facts.next_id - 1)
        for p in club.lineup():
            self.facts.by_person.setdefault(p.name, []).append(f.id)

    # ---------- press ----------
    def press(self, ctx: WeekCtx) -> None:
        tension_clubs = {}
        for c in ctx.clubs:
            t = self.tension(c.name)
            if t >= 10:
                tension_clubs.setdefault(c.region, []).append((t, c))
        for j in self.journalists:
            if ctx.rng.random() < j.sensation / 500 and tension_clubs.get(j.region):
                _, club = max(tension_clubs[j.region], key=lambda x: (x[0], x[1].name))
                pool = [f for f in self.facts.recent(ctx.week - 8) if f.club == club.name and f.visibility == "internal"
                        and f.salience >= 6 and not f.known_by(j.id) and _harmful(f)]
                if pool:
                    f = ctx.rng.choice(pool)
                    self.facts.learn(j.id, f.id, ctx.week, "расследование")
                    j.tips.append(f.id)
            tips = [self.facts.get(i) for i in j.tips if self.facts.get(i) is not None and i not in j.published
                    and _harmful(self.facts.get(i))]
            j.tips = [f.id for f in tips]
            if not tips:
                continue
            f = max(tips, key=lambda x: (x.salience, x.id))
            self._publish(ctx, j, f)

    def _publish(self, ctx: WeekCtx, j: Journalist, f) -> None:
        j.published.append(f.id)
        del j.published[:-30]
        j.tips.remove(f.id)
        club = next((c for c in ctx.clubs if c.name == f.club), None)
        claim = None
        culprit = f.actor
        if club is not None and ctx.rng.random() < (100 - j.accuracy) / 150:
            others = sorted(q.name for q in club.roster if q.name not in f.people())
            if others and f.actor and ":" not in f.actor:
                culprit = ctx.rng.choice(others)
                claim = {"actor": culprit, "text": f.text.replace(f.actor, culprit, 1)}
        leak = [x.id for x in self.facts.recent(ctx.week - 8) if x.kind == "leak" and x.data.get("about") == f.id]
        imp = {}
        if culprit and ":" not in culprit:
            imp[culprit] = {"status": -3, "pride": -4}
        if club is not None:
            imp[f"club:{club.name}"] = {"harmony": -3}
        text = (claim or {}).get("text", f.text)
        art = self.emit(ctx, "article", actor=j.id, target=culprit, club=f.club, about=f.id, causes=[f.id] + leak,
                        impacts=imp, salience=10 + f.salience / 2, visibility="public", engine_made=False,
                        reasons=[f"журналист {j.name}: точность {j.accuracy:.0f}, тяга к сенсациям {j.sensation:.0f}"],
                        data={"journalist": j.name, "distorted": claim is not None},
                        text=f"{j.name}: «{text}»")
        if club is not None:
            for h in sorted([q.name for q in club.roster] + [f"club:{club.name}"]):
                if self.facts.learn(h, f.id, ctx.week, f"статья {j.name}", claim):
                    self.learned.append((h, f.id))
        j.credibility += -4 if claim else 1
        return art

    # ---------- spreading information ----------
    def spread(self, ctx: WeekCtx) -> None:
        g = ctx.graph
        for f in self.facts.recent(ctx.week - 6):
            if f.visibility == "public" or f.salience < 4 or f.kind == "leak":
                continue
            club = next((c for c in ctx.clubs if c.name == f.club), None)
            holders = sorted(h for h in f.knowers if ":" not in h)
            for h in holders:
                hp = self.player(ctx, h)
                if hp is None:
                    continue
                hc = ctx.index[h][1]
                pool = [q for q in (hc.roster if hc else []) if not f.known_by(q.name)]
                for q in pool:
                    fr = g.get(h, q.name).friendship
                    p_tell = 0.15 * (0.4 + hp.p("social_need") / 100) * min(1.0, fr / 55) * min(1.0, f.salience / 10)
                    if ctx.rng.random() >= p_tell:
                        continue
                    claim = f.misbelief.get(h)
                    if claim is None and h == f.actor and f.target and ":" not in f.target and \
                            any(d < 0 for d in f.impacts.get(f.target, {}).values()) and ctx.rng.random() < hp.p("ego") / 200:
                        # the culprit tells his own version: the other one started it
                        claim = {"actor": f.target, "target": h, "text": f"{f.target} первым начал с {h} (со слов {h})"}
                    if self.facts.learn(q.name, f.id, ctx.week, f"рассказал {h}", claim):
                        self.learned.append((q.name, f.id))
                    elif claim is None and q.name in f.misbelief:
                        pass
                # the staff and the manager
                if club is not None and hc is club and not f.known_by(f"club:{club.name}"):
                    if hp.s("coach_trust") > 65 and ctx.rng.random() < 0.25:
                        if self.facts.learn(f"club:{club.name}", f.id, ctx.week, f"{h} рассказал вам", f.misbelief.get(h)):
                            self.learned.append((f"club:{club.name}", f.id))
            if club is not None and f.visibility == "internal" and not f.known_by(f"club:{club.name}"):
                if ctx.rng.random() < 0.15 + club.coach_quality / 300:
                    if self.facts.learn(f"club:{club.name}", f.id, ctx.week, "ассистент заметил"):
                        self.learned.append((f"club:{club.name}", f.id))

    # ---------- feelings ----------
    def appraise_all(self, ctx: WeekCtx) -> None:
        todo, self.learned = self.learned, []
        self._club_news = getattr(self, "_club_news", [])
        for holder, fid in todo:
            f = self.facts.get(fid)
            if f is None:
                continue
            if holder.startswith("club:"):
                self._club_news.append((holder[5:], fid))
                continue
            p = self.player(ctx, holder)
            if p is None:
                continue
            appraise(self, ctx, p, self.minds.of(holder), f)

    def refresh_goals(self, ctx: WeekCtx) -> None:
        for c in ctx.clubs:
            ranked = sorted(c.roster, key=lambda q: -q.fame)
            for i, p in enumerate(ranked, 1):
                m = self.minds.of(p.name)
                dyn = {k: v for k, v in m.goals.items() if "|" in k}
                m.goals = {**goals_for(p, c, i, len(ranked)), **dyn}

    # ---------- decisions ----------
    def _budget_ok(self, ctx: WeekCtx, club, target: str | None = None) -> bool:
        log = [x for x in self.neg_log.get(club.name, []) if _w(x) > ctx.week - NEG_WINDOW]
        self.neg_log[club.name] = log
        cap_w, cap_m = NEG_PER_WEEK, NEG_PER_WINDOW
        if self.order_until.get(club.name, -1) >= ctx.week:
            cap_w, cap_m = 1, 1
        if target is not None and sum(1 for x in log if isinstance(x, tuple) and x[1] == target) >= NEG_PER_TARGET:
            return False
        return sum(1 for x in log if _w(x) == ctx.week) < cap_w and len(log) < cap_m

    def decide_and_act(self, ctx: WeekCtx) -> list:
        done = []
        for club in ctx.clubs:
            if self.made_this_week.get(club.name, 0) >= FACTS_PER_CLUB_WEEK:
                self.capped += 1
                continue
            crisis = self.tension(club.name) >= CRISIS_TENSION
            for a in sorted(club.roster, key=lambda q: q.name):
                mind = self.minds.peek(a.name)
                if mind is None or mind.last_action >= ctx.week:
                    continue
                if mind.intention is not None:
                    f = self._pursue(ctx, a, club, mind)
                    if f is not None:
                        done.append(f)
                        continue
                k, _, v = mind.strongest()
                ambient = ctx.rng.random() < 0.1
                if v < AROUSAL and not ambient:
                    continue
                choice = self._choose(ctx, a, club, mind, crisis)
                if choice is None:
                    continue
                act, t, x, u, why, causes = choice
                if act.public and not self._opportunity(ctx, club):
                    if mind.intention is None:   # wait for a press day; meanwhile life goes on
                        mind.intention = Intention(act.name, t, x, causes, ctx.week, u)
                    continue
                f = self._do(ctx, a, club, mind, act, t, x, why, causes)
                if f is not None:
                    done.append(f)
        return done

    def _opportunity(self, ctx: WeekCtx, club) -> bool:
        return club.name in ctx.played or ctx.rng.random() < 0.3

    def _choose(self, ctx: WeekCtx, a, club, mind, crisis: bool):
        """Two steps, so a long menu of weak options does not add up to an urge: first, is the
        best option worth more than doing nothing (a soft threshold); then which option, picked
        by softmax, so an upset or stressed person sometimes does not pick the best one."""
        temp = 0.12 + a.s("stress") / 400 + mind.strongest()[2] / 500
        opts = []
        for act in A.ALL:
            if act.tone == A.NEG and (not self._budget_ok(ctx, club) or mind.cooldowns.get("neg", -1) > ctx.week):
                continue
            for t, x in act.candidates(self, ctx, a, club, mind):
                if t == a.name or x == a.name:
                    continue
                if t and ":" not in t and self.player(ctx, t) is None:
                    continue    # feelings outlive people: the one they are about has retired
                if act.tone == A.NEG and not self._budget_ok(ctx, club, t):
                    continue
                if mind.cooldowns.get(f"{act.name}|{t}", -1) > ctx.week:
                    continue
                if not act.available(self, ctx, a, club, t, x):
                    continue
                u, why = act.utility(self, ctx, a, club, mind, t, x)
                causes = self._motive(mind, t, x, act)
                depth = max((self.facts.chain_depth(c) for c in causes), default=0)
                if depth >= MAX_CHAIN_DEPTH:
                    continue
                if act.tone == A.NEG:
                    u *= DEPTH_DAMP ** depth
                    if crisis:
                        u *= 0.35
                elif act.tone == A.POS and crisis:
                    u += 0.4
                opts.append((u, act, t, x, why, causes))
        if not opts:
            return None
        best = max(o[0] for o in opts)
        if ctx.rng.random() >= 1 / (1 + math.exp(-(best - REST_UTILITY) / temp)):
            return None
        weights = [math.exp((o[0] - best) / temp) for o in opts]
        u, act, t, x, why, causes = opts[ctx.rng.choices(range(len(opts)), weights=weights)[0]]
        return act, t, x, u, why, causes

    def _motive(self, mind, t, x, act=None) -> list[int]:
        """The facts behind the feelings that drive this act: the edges of the causal graph."""
        kinds = MOTIVES.get(act.name if act else "", ("anger", "envy", "threat", "gratitude"))
        causes = []
        for who in (t, x):
            if not who:
                continue
            for k in kinds:
                causes += mind.causes_of(k, who)
            if act is None or act.tone == A.NEG or act.name == "reconcile":
                causes += [m.fact for m in mind.memories_about(who) if m.valence <= -20][-2:]
        if act is not None and act.name in ("mediate", "reconcile"):
            for key in sorted(mind.emotion_causes):
                if key.startswith("distress|club:"):
                    causes += mind.emotion_causes[key][-2:]
        return sorted(set(causes))[-5:]

    def _do(self, ctx: WeekCtx, a, club, mind, act, t, x, why, causes):
        mind.last_action = ctx.week
        mind.cooldowns[f"{act.name}|{t}"] = ctx.week + COOLDOWN
        if len(mind.cooldowns) > 12:
            mind.cooldowns = {k: w for k, w in mind.cooldowns.items() if w > ctx.week}
        if act.tone == A.NEG:
            self.neg_log.setdefault(club.name, []).append((ctx.week, t))
            mind.cooldowns["neg"] = ctx.week + ACTOR_NEG_REST
            for k in ("anger", "envy", "threat"):   # letting it out vents some of the feeling
                key = f"{k}|{t or ''}"
                if key in mind.emotions:
                    mind.emotions[key] *= 0.7
        self._pend = []
        f = act.execute(self, ctx, a, club, t, x, causes, why)
        f.data["action"] = act.name
        return f

    def _pursue(self, ctx: WeekCtx, a, club, mind):
        it = mind.intention
        act = A.BY_NAME[it.action]
        still = it.target is None or self.player(ctx, it.target) is not None
        u, why = act.utility(self, ctx, a, club, mind, it.target, it.third) if still else (0.0, [])
        if not still or u < REST_UTILITY * 0.8 or ctx.week - it.formed > 6:
            mind.intention = None
            self.emit(ctx, "changed_mind", actor=a.name, target=it.target, club=club.name, causes=it.causes,
                      salience=3, visibility="private",
                      reasons=[f"желание остыло (ценность {u:.2f} при пороге {REST_UTILITY * 0.8:.2f})"],
                      text=f"{a.name} собирался: {act.label}" + (f" ({it.target})" if it.target else "") + ", но передумал")
            return None
        if act.public and not self._opportunity(ctx, club):
            return None
        mind.intention = None
        if max((self.facts.chain_depth(c) for c in it.causes), default=0) >= MAX_CHAIN_DEPTH:
            return None
        if act.tone == A.NEG and not self._budget_ok(ctx, club, it.target):
            return None
        return self._do(ctx, a, club, mind, act, it.target, it.third, why + ["задумал это заранее"], it.causes)

    # ---------- manager situations ----------
    def manage(self, ctx: WeekCtx) -> list[str]:
        from .manager_view import make_situation, ai_resolve
        notes = []
        news, self._club_news = getattr(self, "_club_news", []), []
        for club_name, fid in news:
            f = self.facts.get(fid)
            if f is None:
                continue
            if club_name == ctx.manager_club and f.salience >= 5 and f.kind not in ("series", "standout", "title", "manager_decision"):
                week, how = f.knowers.get(f"club:{club_name}") or f.knowers.get(PUBLIC, (ctx.week, "из новостей"))
                b = f.believed(f"club:{club_name}")
                lst = self.reports.setdefault(club_name, [])
                lst.append(Report(ctx.week, fid, b["text"] or f.text, how, believed=not f.misbelief.get(f"club:{club_name}")))
                del lst[:-REPORTS_KEEP]
            s = make_situation(self, ctx, club_name, f)
            if s is None:
                continue
            if club_name != ctx.manager_club:
                notes += ai_resolve(self, ctx, s)
        return notes

    # ---------- forgetting ----------
    def forget(self, ctx: WeekCtx) -> None:
        cut = ctx.week - 8
        for c in list(self.harmony_log):
            self.harmony_log[c] = [(w, d) for w, d in self.harmony_log[c] if w > cut]
            if not self.harmony_log[c]:
                del self.harmony_log[c]
        alive = set(ctx.index)
        for name in sorted(self.minds.minds):
            m = self.minds.minds[name]
            m.decay()
            if name not in alive and not m.memories:
                del self.minds.minds[name]
        if ctx.week % 13 == 0:
            self.facts.prune(ctx.week)
            live = self.facts.facts
            self.prov = {k: [i for i in v if i in live] for k, v in self.prov.items()}
            self.prov = {k: v for k, v in self.prov.items() if v}
            self.kills = {k: v for k, v in self.kills.items() if k in alive}
            self.situations = [s for s in self.situations if s.choice is None or s.week > ctx.week - 26]
            self.pair_situation = {k: w for k, w in self.pair_situation.items() if w > ctx.week - SITUATION_COOLDOWN}
            for m in self.minds.minds.values():
                m.memories = [x for x in m.memories if x.fact in live or abs(x.valence) >= 30]
                m.emotion_causes = {k: [i for i in v if i in live] for k, v in m.emotion_causes.items()}

    # ---------- views ----------
    def history_of(self, name: str) -> list:
        return sorted(self.facts.of_person(name), key=lambda f: (f.week, f.id))

    def why(self, fid: int, depth: int = 6) -> dict:
        return self.facts.tree(fid, depth)


NEG_DIMS = ("irritation", "role_rivalry", "resentment", "fear")


def story_impacts(effects: list[dict], a: str | None, b: str | None, club: str) -> dict:
    """Read a storylet's effects as impacts, so appraisal needs no rules per event."""
    imp: dict[str, dict[str, float]] = {}

    def add(who, res, v):
        if who and v:
            d = imp.setdefault(who, {})
            d[res] = round(d.get(res, 0.0) + v, 2)
    for e in effects:
        who = b if e.get("who") == "b" else a
        k = e.get("add", 0)
        if "state" in e:
            if e["state"] in ("morale", "confidence", "role_satisfaction", "coach_trust"):
                add(who, "pride", k / 2)
            elif e["state"] == "stress":
                add(who, "pride", -k / 3)
        elif "rel" in e and a and b:
            v = (-k if e["rel"] in NEG_DIMS else k) / 2
            add(b, "belonging", v)
            if e.get("both", True):
                add(a, "belonging", v)
        elif "team_morale" in e:
            add(f"club:{club}", "harmony", e["team_morale"] / 2)
        elif "bench" in e:
            add(who, "status", -6)
        elif "add_trait" in e or "release" in e:
            add(who, "career", -3 if "release" in e else 0)
    return {k: v for k, v in imp.items() if any(v.values())}


MOTIVES = {
    "public_jab": ("anger", "envy", "threat"), "private_confront": ("anger", "threat"),
    "freeze_out": ("envy", "threat", "anger"), "outwork": ("envy", "threat"), "mentor": ("gratitude",),
    "praise_publicly": ("gratitude",), "mediate": (), "side_with": ("anger",), "reconcile": (),
    "complain": ("anger", "envy", "threat"), "seek_spotlight": ("envy",), "ask_to_leave": (),
    "leak": ("anger",),
}


def _harmful(f) -> bool:
    """Something the press can sell: somebody lost something because of somebody."""
    return any(d < 0 for imp in f.impacts.values() for d in imp.values())


def _w(x) -> int:
    return x[0] if isinstance(x, tuple) else x


def _gumbel(rng: random.Random) -> float:
    u = min(max(rng.random(), 1e-9), 1 - 1e-9)
    return -math.log(-math.log(u))

