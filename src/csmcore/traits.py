"""Gold Traits (concept layer 3): data-driven rule modifiers loaded from data/traits.json.

A trait never stores a scripted story. It is a list of effects:
    target  what it changes: "stat:<name>", "duel", or a named hook ("fan_gain", "travel_stress", ...)
    op      "add" or "mul"
    when    optional context conditions, matched against the event context dict
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources


@dataclass(frozen=True)
class Effect:
    target: str
    op: str
    value: float
    when: dict = field(default_factory=dict)

    def applies(self, ctx: dict | None) -> bool:
        ctx = ctx or {}
        return all(ctx.get(k) == v for k, v in self.when.items())


@dataclass(frozen=True)
class Trait:
    id: str
    name: str
    family: str
    desc: str
    effects: tuple[Effect, ...]
    incompatible: tuple[str, ...] = ()
    hidden_until: str | None = None


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(resources.files("csmcore.data").joinpath("traits.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def library() -> dict[str, Trait]:
    out = {}
    for t in _raw()["traits"]:
        effects = tuple(Effect(e["target"], e["op"], float(e["value"]), e.get("when", {})) for e in t["effects"])
        out[t["id"]] = Trait(t["id"], t["name"], t["family"], t["desc"], effects,
                             tuple(t.get("incompatible", ())), t.get("hidden_until"))
    return out


def modifier(trait_ids: list[str], target: str, ctx: dict | None = None) -> tuple[float, float]:
    """Sum of 'add' effects and product of 'mul' effects for one target in one context."""
    add, mul = 0.0, 1.0
    lib = library()
    for tid in trait_ids:
        for e in lib[tid].effects:
            if e.target == target and e.applies(ctx):
                if e.op == "add":
                    add += e.value
                else:
                    mul *= e.value
    return add, mul


def roll_traits(rng: random.Random, weights: dict[str, float] | None = None) -> list[str]:
    """Pick 1-3 traits with the 70/27/3 distribution, skipping incompatible pairs.
    `weights` lets archetype/role/region bias the pick (non-uniform RNG, as in the concept)."""
    dist = _raw()["distribution"]
    count = rng.choices([int(k) for k in dist], weights=list(dist.values()))[0]
    lib = library()
    pool = list(lib)
    w = [(weights or {}).get(t, 1.0) for t in pool]
    picked: list[str] = []
    while len(picked) < count:
        tid = rng.choices(pool, weights=w)[0]
        if tid in picked or any(tid in lib[p].incompatible or p in lib[tid].incompatible for p in picked):
            continue
        picked.append(tid)
    return picked
