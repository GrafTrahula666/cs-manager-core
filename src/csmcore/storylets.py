"""Life-event engine in the Crusader Kings style ("storylets").

An event is data (data/events.json), not a script:
    who        "player" (one subject a), "pair" (a and teammate b) or "club"
    when       conditions on the world: stats, state, personality, traits, flags, relations, club
    weight     base weekly chance + multipliers ("if" condition -> "mul"), like CK3 mean-time-to-happen
    options    choices; the manager picks for their club, AI clubs pick by personality-weighted odds
    effects    change state, relations, money, fans, flags, traits; schedule a follow-up event (chains)

Nothing about a particular story is hard-coded: a story is a chain of events whose conditions
became true because of earlier events and of the slow drift in world.py.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from .economy import Club
from .player import Player
from .relations import RelationGraph

MAX_EVENTS_PER_SUBJECT_WEEK = 1
# After any story a person gets a breather: other events are rarer for a few weeks, so one
# player does not collect a clip, a visa problem and a breakup in one month.
STORY_REST_WEEKS = 6
# Weekly dilemmas ("deck" cards) for the manager: chance of a card in a week with no open card.
DECK_CHANCE = 0.55
DECK_COOLDOWN_WEEKS = 30
# cash_scaled amounts are written for a tier-1 club and scaled to the club's size
TIER_CASH = {"tier3": 0.08, "tier2": 0.3, "tier1": 1.0, "super": 2.0}
STORY_REST_MUL = 0.35


@dataclass
class Fired:
    """An event that happened. `choice` is None until the manager (or AI) picks an option."""
    event_id: str
    week: int
    club: Club
    a: Player | None
    b: Player | None
    title: str
    text: str
    options: list[str]
    why: list[str]
    choice: int | None = None
    outcome: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def library() -> dict[str, dict]:
    raw = json.loads(resources.files("csmcore.data").joinpath("events.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in raw["events"]}


# ---------- conditions ----------

def _cmp(value: float, cond: dict) -> bool:
    return ("lt" not in cond or value < cond["lt"]) and ("gt" not in cond or value > cond["gt"])


def check(cond: dict, club: Club, a: Player | None, b: Player | None, graph: RelationGraph) -> bool:
    if "any" in cond:
        return any(check(c, club, a, b, graph) for c in cond["any"])
    if "not" in cond:
        return not check(cond["not"], club, a, b, graph)
    p = b if cond.get("who") == "b" else a
    if "stat" in cond:
        return p is not None and _cmp(p.stat(cond["stat"]), cond)
    if "state" in cond:
        return p is not None and _cmp(p.s(cond["state"]), cond)
    if "personality" in cond:
        return p is not None and _cmp(p.p(cond["personality"]), cond)
    if "fame" in cond:
        return p is not None and _cmp(p.fame, cond)
    if "age" in cond:
        return p is not None and _cmp(p.age, cond)
    if "trait" in cond:
        return p is not None and cond["trait"] in p.traits
    if "role" in cond:
        return p is not None and p.role == cond["role"]
    if "flag" in cond:
        return p is not None and cond["flag"] in p.flags
    if "no_flag" in cond:
        return p is None or cond["no_flag"] not in p.flags
    if "club_flag" in cond:
        return cond["club_flag"] in club.flags
    if "no_club_flag" in cond:
        return cond["no_club_flag"] not in club.flags
    if "rel" in cond:
        return a is not None and b is not None and _cmp(getattr(graph.get(a.name, b.name), cond["rel"]), cond)
    if "club" in cond:
        return _cmp(float(getattr(club, cond["club"])), cond)
    if "sponsor" in cond:
        return any(s.category == cond["sponsor"] for s in club.sponsors)
    raise ValueError(f"unknown condition {cond}")


def describe(cond: dict) -> str:
    """Short human-readable reason for the 'why' log."""
    if "any" in cond:
        return " или ".join(describe(c) for c in cond["any"])
    if "not" in cond:
        return "не " + describe(cond["not"])
    key = next(k for k in cond if k not in ("lt", "gt", "who"))
    bound = (f" < {cond['lt']}" if "lt" in cond else "") + (f" > {cond['gt']}" if "gt" in cond else "")
    who = "(b) " if cond.get("who") == "b" else ""
    val = f"={cond[key]}" if cond[key] not in ("", True) else ""
    return f"{who}{key}{val}{bound}"


# ---------- effects ----------

def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def apply_effects(effects: list[dict], f: Fired, graph: RelationGraph, rng: random.Random,
                  queue: list[tuple[int, str, Club, str | None, str | None]], secrets=None) -> list[str]:
    out = []
    club = f.club
    for e in effects:
        p = f.b if e.get("who") == "b" else f.a
        if "chance" in e and rng.random() >= e["chance"]:
            continue
        if "state" in e and p:
            p.state[e["state"]] = _clamp(p.s(e["state"]) + e["add"])
            out.append(f"{p.name}: {e['state']} {e['add']:+}")
        elif "stat" in e and p:
            p.stats[e["stat"]] = _clamp(p.stats.get(e["stat"], 50) + e["add"])
            out.append(f"{p.name}: {e['stat']} {e['add']:+}")
        elif "personality" in e and p:
            p.personality[e["personality"]] = _clamp(p.p(e["personality"]) + e["add"])
        elif "rel" in e and f.a and f.b:
            graph.nudge(f.a.name, f.b.name, e["rel"], e["add"])
            if e.get("both", True):
                graph.nudge(f.b.name, f.a.name, e["rel"], e["add"])
            out.append(f"{f.a.name}↔{f.b.name}: {e['rel']} {e['add']:+}")
        elif "team_morale" in e:
            for q in club.roster:
                q.state["morale"] = _clamp(q.s("morale") + e["team_morale"])
            out.append(f"мораль команды {e['team_morale']:+}")
        elif "cash_scaled" in e:
            amount = e["cash_scaled"] * TIER_CASH.get(club.tier, 1.0)
            club.book(f.week, "events", amount, f.title)
            out.append(f"касса {amount:+,.0f}")
        elif "act" in e:
            from .character import act
            who = [p] if e.get("on") == "a" and p else club.lineup() if e.get("on") == "lineup" else list(club.roster)
            out += act([q for q in who if q in club.roster], e["act"], f.week, e.get("scale", 1.0))
        elif "state_team" in e:
            for q in club.roster:
                q.state[e["state_team"]] = _clamp(q.s(e["state_team"]) + e["add"])
            out.append(f"команда: {e['state_team']} {e['add']:+}")
        elif "unclub_flag" in e:
            club.flags.discard(e["unclub_flag"])
        elif "cash" in e:
            club.book(f.week, "events", e["cash"], f.title)
            out.append(f"касса {e['cash']:+,.0f}")
        elif "fans_pct" in e:
            club.fans = max(0, int(club.fans * (1 + e["fans_pct"] / 100)))
            out.append(f"фанаты {e['fans_pct']:+}%")
        elif "brand" in e:
            club.brand = _clamp(club.brand + e["brand"])
            out.append(f"бренд {e['brand']:+}")
        elif "sponsor_leaves" in e:
            gone = [s for s in club.sponsors if s.category in e["sponsor_leaves"] or e["sponsor_leaves"] == "any"]
            if gone:
                club.sponsors.remove(gone[0])
                out.append(f"спонсор {gone[0].name} разорвал контракт")
        elif "flag" in e and p:
            p.flags.add(e["flag"])
        elif "unflag" in e and p:
            p.flags.discard(e["unflag"])
        elif "club_flag" in e:
            club.flags.add(e["club_flag"])
        elif "add_trait" in e and p and e["add_trait"] not in p.traits:
            p.traits.append(e["add_trait"])
            out.append(f"{p.name} получил черту {e['add_trait']}")
        elif "bench" in e and p:
            p.flags.add("benched")
            out.append(f"{p.name} отстранён от состава")
        elif "release" in e and p and p in club.roster:
            club.roster.remove(p)
            club.contracts.pop(p.name, None)
            club.former.append(p)
            p.former_clubs.add(club.name)
            p.flags.add("free_agent")
            out.append(f"{p.name} покинул клуб")
        elif "secret" in e and p and secrets is not None:
            sec = secrets.add(p, e["secret"], f.week)
            if e.get("known_by_club"):
                sec.known_by.add(club.name)
            out.append(f"у {p.name} появился секрет")
        elif "follow_random" in e:
            ids, odds = zip(*e["follow_random"])
            pick = rng.choices(ids, weights=odds)[0]
            queue.append((f.week + e.get("in_weeks", 1), pick, club,
                          f.a.name if f.a else None, f.b.name if f.b else None))
        elif "follow" in e:
            queue.append((f.week + e.get("in_weeks", 1), e["follow"], club,
                          f.a.name if f.a else None, f.b.name if f.b else None))
        if "history" in e and p:
            p.history.append(f"week {f.week}: " + e["history"].format(a=f.a.name if f.a else "", b=f.b.name if f.b else "", club=club.name))
    return out


# ---------- engine ----------

class StoryEngine:
    def __init__(self, events: dict[str, dict] | None = None, director=None) -> None:
        self.events = events or library()
        self.director = director  # optional director.Director: shapes the drama per club
        self.secrets = None       # optional secrets.Secrets: events can leave secrets behind
        self.queue: list[tuple[int, str, Club, str | None, str | None]] = []  # scheduled follow-ups
        self.last_fired: dict[tuple[str, str], int] = {}  # (event, subject) -> week
        self.pending: list[Fired] = []  # waiting for the manager's choice

    def _weight(self, ev: dict, club, a, b, graph, week: int = 0) -> tuple[float, list[str]]:
        w = ev.get("base", 0.01)
        why = []
        if self.director is not None:
            m = self.director.multiplier(club, ev.get("tone", "neutral"), week)
            if abs(m - 1) > 0.05:
                w *= m
                why.append(f"режиссёр ({self.director.mode}) ×{m:.2f}")
        for m in ev.get("weight", []):
            if check(m["if"], club, a, b, graph):
                w *= m["mul"]
                why.append(f"{describe(m['if'])} ×{m['mul']}")
        if a is not None and week - getattr(self, "last_any", {}).get(a.name, -10_000) < STORY_REST_WEEKS:
            w *= STORY_REST_MUL
            why.append(f"недавно уже была история ×{STORY_REST_MUL}")
        if ev.get("scandal") and a is not None:
            m = a.mod("scandal_risk")[1]
            if m != 1.0:
                w *= m
                why.append(f"склонность к скандалам ×{m:g}")
        return min(w, 0.9), why

    def _eligible(self, ev: dict, week: int, club, a, b, graph) -> bool:
        key = (ev["id"], a.name if a else club.name)
        if ev.get("once") and key in self.last_fired:
            return False
        if week - self.last_fired.get(key, -10_000) < ev.get("cooldown", 26):
            return False
        return all(check(c, club, a, b, graph) for c in ev.get("when", []))

    def _fire(self, ev: dict, week: int, club, a, b, why: list[str]) -> Fired:
        fmt = {"a": a.name if a else "", "b": b.name if b else "", "club": club.name}
        self.last_fired[(ev["id"], a.name if a else club.name)] = week
        if a is not None:
            self.__dict__.setdefault("last_any", {})[a.name] = week   # older saves lack the field
        return Fired(ev["id"], week, club, a, b, ev["title"].format(**fmt), ev["text"].format(**fmt),
                     [o["label"].format(**fmt) for o in ev.get("options", [])], why)

    def week(self, clubs: list[Club], graph: RelationGraph, week: int, rng: random.Random,
             manager_club: str | None = None) -> list[Fired]:
        """Roll events for everyone. AI clubs resolve at once; the manager's club waits in `pending`."""
        fired: list[Fired] = []
        by_name = {c.name: c for c in clubs}
        due = [q for q in self.queue if q[0] <= week]
        self.queue = [q for q in self.queue if q[0] > week]
        for _, eid, club, an, bn in due:
            if club.name not in by_name:
                continue
            people = {p.name: p for p in club.roster} | {p.name: p for p in getattr(club, "former", [])}
            a, b = people.get(an), people.get(bn)
            ev = self.events[eid]
            if all(check(c, club, a, b, graph) for c in ev.get("when", [])):
                fired.append(self._fire(ev, week, club, a, b, ["продолжение цепочки"]))

        for club in clubs:
            busy: dict[str, int] = {}
            for ev in self.events.values():
                if ev.get("chain_only") or ev.get("deck"):
                    continue
                subjects: list[tuple[Player | None, Player | None]]
                if ev["who"] == "club":
                    subjects = [(None, None)]
                elif ev["who"] == "player":
                    subjects = [(p, None) for p in club.roster]
                else:
                    subjects = [(p, q) for p in club.roster for q in club.roster if p is not q]
                for a, b in subjects:
                    if a and busy.get(a.name, 0) >= MAX_EVENTS_PER_SUBJECT_WEEK:
                        continue
                    if not self._eligible(ev, week, club, a, b, graph):
                        continue
                    w, why = self._weight(ev, club, a, b, graph, week)
                    if rng.random() < w:
                        why = [describe(c) for c in ev.get("when", [])] + why
                        fired.append(self._fire(ev, week, club, a, b, why))
                        if a:
                            busy[a.name] = busy.get(a.name, 0) + 1
        if manager_club in by_name:
            card = self._deck_card(by_name[manager_club], graph, week, rng)
            if card is not None:
                fired.append(card)
        if self.director is not None:
            for c in clubs:
                self.director.observe(c, week)
            for f in fired:
                if self.events[f.event_id].get("tone") == "bad":
                    self.director.hurt(f.club, week, 10.0)
        for f in fired:
            if f.club.name == manager_club and f.options:
                self.pending.append(f)
            else:
                self.resolve(f, self.ai_choice(f, graph, rng), graph, rng)
        return fired

    def _deck_card(self, club: Club, graph: RelationGraph, week: int, rng: random.Random) -> Fired | None:
        """At most one open dilemma at a time, so quiet weeks still ask the manager something."""
        if any(self.events[f.event_id].get("deck") for f in self.pending) or rng.random() >= DECK_CHANCE:
            return None
        cards, weights, subjects = [], [], []
        for ev in self.events.values():
            if not ev.get("deck"):
                continue
            people = [None] if ev["who"] == "club" else [p for p in club.roster]
            ok = [a for a in people if week - self.last_fired.get((ev["id"], a.name if a else club.name), -10_000)
                  >= ev.get("cooldown", DECK_COOLDOWN_WEEKS) and all(check(c, club, a, None, graph) for c in ev.get("when", []))]
            if ok:
                cards.append(ev)
                weights.append(ev.get("deck_weight", 1.0))
                subjects.append(ok)
        if not cards:
            return None
        i = rng.choices(range(len(cards)), weights=weights)[0]
        a = rng.choice(subjects[i])
        # a card is the same for every subject: cool it down for the whole club too
        for q in [None] + list(club.roster):
            self.last_fired[(cards[i]["id"], q.name if q else club.name)] = week
        return self._fire(cards[i], week, club, a, None, ["выбор недели"])

    def ai_choice(self, f: Fired, graph: RelationGraph, rng: random.Random) -> int | None:
        opts = self.events[f.event_id].get("options", [])
        if not opts:
            return None
        weights = []
        for o in opts:
            w = o.get("ai", 1.0)
            for m in o.get("ai_weight", []):
                if check(m["if"], f.club, f.a, f.b, graph):
                    w *= m["mul"]
            weights.append(w)
        return rng.choices(range(len(opts)), weights=weights)[0]

    def resolve(self, f: Fired, choice: int | None, graph: RelationGraph, rng: random.Random) -> Fired:
        ev = self.events[f.event_id]
        f.outcome += apply_effects(ev.get("effects", []), f, graph, rng, self.queue, self.secrets)
        if choice is not None and ev.get("options"):
            f.choice = choice
            f.outcome += apply_effects(ev["options"][choice].get("effects", []), f, graph, rng, self.queue, self.secrets)
        if f in self.pending:
            self.pending.remove(f)
        return f
