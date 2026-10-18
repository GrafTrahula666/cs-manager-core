"""Facts: what really happened, when, with whom, why, who knows and who believes something else.

A fact is the unit of the world's memory. Everything the emergent engine does is recorded as a
fact, and so is everything it notices in the older systems (a transfer, a title, an open
conflict from world.py, a storylet). Facts point at the facts that caused them, so any event
can be traced back through a causal graph to the circumstances that started it.

Knowledge is part of the fact: `knowers` maps a holder (a person, "club:<name>" for a club's
staff and manager, "press:<id>" for a journalist) to how they learned it. `misbelief` maps a
holder to the distorted version they believe (a different culprit, an exaggeration).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Facts at or above this salience are history: they are never pruned, and neither are the
# facts that caused them (up to PROTECT_DEPTH levels up).
HISTORIC = 35.0
PROTECT_DEPTH = 6
# Everything else is forgotten by the world after this many weeks (people keep their own
# memories in minds.py, which have their own limits).
KEEP_WEEKS = 52
PUBLIC = "*"


@dataclass
class Fact:
    id: int
    week: int
    season: int
    kind: str
    actor: str | None = None
    target: str | None = None
    third: str | None = None
    club: str | None = None
    data: dict = field(default_factory=dict)
    # person -> {resource: delta}: who won or lost what (status, attention, pride, belonging,
    # harmony, career, trust). Appraisal reads impacts, not the kind, so new kinds need no rules.
    impacts: dict[str, dict[str, float]] = field(default_factory=dict)
    causes: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    depth: int = 0
    salience: float = 5.0
    visibility: str = "internal"      # private | internal | public
    text: str = ""
    knowers: dict[str, tuple[int, str]] = field(default_factory=dict)   # holder -> (week, how)
    misbelief: dict[str, dict] = field(default_factory=dict)            # holder -> changed fields
    about: int | None = None          # articles and rumours report another fact

    def people(self) -> list[str]:
        return [x for x in (self.actor, self.target, self.third) if x and ":" not in x]

    def known_by(self, holder: str) -> bool:
        return PUBLIC in self.knowers or holder in self.knowers

    def believed(self, holder: str) -> dict:
        """The version of the fact this holder believes: actor/target/text may differ from truth."""
        base = {"actor": self.actor, "target": self.target, "third": self.third, "text": self.text}
        return {**base, **self.misbelief.get(holder, {})}


@dataclass
class FactLog:
    facts: dict[int, Fact] = field(default_factory=dict)
    next_id: int = 1
    by_person: dict[str, list[int]] = field(default_factory=dict)
    protected: set[int] = field(default_factory=set)
    pruned: int = 0

    def add(self, week: int, season: int, kind: str, *, actor=None, target=None, third=None, club=None,
            data=None, impacts=None, causes=(), reasons=(), salience: float = 5.0,
            visibility: str = "internal", text: str = "", about: int | None = None,
            max_depth: int | None = None) -> Fact:
        causes = sorted({c for c in causes if c in self.facts})
        if max_depth is not None:
            # links deeper than the cap stay background: the chain cannot grow past it
            causes = [c for c in causes if self.facts[c].depth < max_depth]
        depth = 1 + max((self.facts[c].depth for c in causes), default=-1)
        f = Fact(self.next_id, week, season, kind, actor, target, third, club, dict(data or {}),
                 {k: dict(v) for k, v in (impacts or {}).items()}, causes, list(reasons)[:6], depth,
                 salience, visibility, text, about=about)
        self.facts[f.id] = f
        self.next_id += 1
        for p in f.people():
            self.by_person.setdefault(p, []).append(f.id)
        if visibility == "public":
            f.knowers[PUBLIC] = (week, "публично")
        if salience >= HISTORIC:
            self._protect(f.id, PROTECT_DEPTH)
        return f

    def get(self, fid: int) -> Fact | None:
        return self.facts.get(fid)

    def learn(self, holder: str, fid: int, week: int, how: str, claim: dict | None = None) -> bool:
        """Holder learns a fact (or a distorted version of it). Returns True if it is news to them."""
        f = self.facts.get(fid)
        if f is None or f.known_by(holder):
            if f is not None and claim is None and holder in f.misbelief and PUBLIC not in f.knowers:
                del f.misbelief[holder]   # the true version from a trusted source corrects a rumour
            return False
        f.knowers[holder] = (week, how)
        if claim:
            f.misbelief[holder] = dict(claim)
        return True

    def of_person(self, name: str, kinds=None) -> list[Fact]:
        out = [self.facts[i] for i in self.by_person.get(name, []) if i in self.facts]
        return [f for f in out if kinds is None or f.kind in kinds]

    def recent(self, since_week: int) -> list[Fact]:
        out = []
        for fid in range(self.next_id - 1, 0, -1):
            f = self.facts.get(fid)
            if f is None:
                continue
            if f.week < since_week:
                break
            out.append(f)
        return out[::-1]

    def _protect(self, fid: int, depth: int) -> None:
        stack = [(fid, depth)]
        while stack:
            i, d = stack.pop()
            if i in self.protected or i not in self.facts:
                continue
            self.protected.add(i)
            if d > 0:
                stack += [(c, d - 1) for c in self.facts[i].causes]

    def prune(self, now_week: int) -> int:
        """Forget old, unimportant facts. Causes that point at a forgotten fact stay as ids and
        render as "(забыто)" in the causal graph."""
        old = [i for i, f in self.facts.items()
               if f.week < now_week - KEEP_WEEKS and i not in self.protected and f.salience < HISTORIC]
        for i in old:
            f = self.facts.pop(i)
            for p in f.people():
                ids = self.by_person.get(p)
                if ids:
                    try:
                        ids.remove(i)
                    except ValueError:
                        pass
                    if not ids:
                        del self.by_person[p]
            # A fact that outlived its week no longer needs a full knower list: holders matter
            # for spreading news, and old news does not spread.
        for f in self.facts.values():
            if f.week < now_week - KEEP_WEEKS and len(f.knowers) > 1 and PUBLIC not in f.knowers:
                keep = {k: v for k, v in f.knowers.items() if k.startswith("club:") or k in f.people()}
                f.knowers = keep
                f.misbelief = {k: v for k, v in f.misbelief.items() if k in keep}
        self.pruned += len(old)
        return len(old)

    # ---- causal graph ----
    def tree(self, fid: int, depth: int = 6, seen: set | None = None) -> dict:
        """Nested causes of a fact, for the "почему?" view. A fact that already appeared in the
        tree is shown once more as a reference ("ref": True) without its causes."""
        seen = set() if seen is None else seen
        f = self.facts.get(fid)
        if f is None:
            return {"id": fid, "text": "(забыто)", "causes": [], "reasons": []}
        node = {"id": f.id, "week": f.week, "season": f.season, "kind": f.kind, "text": f.text,
                "reasons": list(f.reasons), "causes": []}
        if fid in seen:
            node["ref"], node["reasons"] = True, []
            return node
        seen.add(fid)
        if depth > 0:
            node["causes"] = [self.tree(c, depth - 1, seen) for c in f.causes]
        return node

    def ancestors(self, fid: int, limit: int = 50) -> list[int]:
        out, stack, seen = [], [fid], set()
        while stack and len(out) < limit:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            out.append(i)
            f = self.facts.get(i)
            if f is not None:
                stack += f.causes
        return out

    def chain_depth(self, fid: int) -> int:
        f = self.facts.get(fid)
        return f.depth if f else 0
