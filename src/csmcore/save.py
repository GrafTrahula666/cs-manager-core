"""Save and load a whole game: world, systems, random streams and the manager's desk.

The file is a gzip'd pickle with a small header, so a loaded game continues exactly as the
original would have (same matches, same events). Pickle is only for your own saves: never load
a save file from someone you do not trust.
"""
from __future__ import annotations

import gzip
import io
import pickle

MAGIC = b"CSMSAVE"
VERSION = 5
# Version history: 1 = before the emergent world engine; 2 = sysm.emergent (facts, minds, press);
# 3 = leagues (Тир 1-3 and the rest), HACEIT and HLTW; 4 = contracts that end, the hiring journal,
# the roster-core rule for invites; 5 = salaries and prices follow the world's level scale.
SUPPORTED = (1, 2, 3, 4, 5)
WORLD_LEVEL_AT_START = 70.0   # see _to_world_scale


def dumps(game) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        pickle.dump(game, f, protocol=pickle.HIGHEST_PROTOCOL)
    return MAGIC + bytes([VERSION]) + buf.getvalue()


def loads(data: bytes):
    if not data.startswith(MAGIC):
        raise ValueError("это не сохранение CS MENEDGER")
    version = data[len(MAGIC)]
    if version not in SUPPORTED:
        raise ValueError(f"сохранение версии {version}, игра понимает {', '.join(map(str, SUPPORTED))}")
    with gzip.GzipFile(fileobj=io.BytesIO(data[len(MAGIC) + 1:])) as f:
        game = pickle.load(f)
    return migrate(game, version)


def migrate(game, version: int):
    """Bring an older save up to date without losing anything it had.

    1 -> 2: the world gets an emergent engine. Nothing happened in it before the save, so the
    engine starts with empty memories and looks at the world from the next week on (its first
    look only records who plays where, it does not invent transfers)."""
    if version < 2 and getattr(game.sysm, "emergent", None) is None:
        from .emergent import EmergentWorld
        regions = tuple(sorted({c.region for c in game.clubs}))
        game.sysm.emergent = EmergentWorld(game.seed, regions)
    if version < 3:
        _to_leagues(game)
    if version < 4:
        _to_contracts(game)
    if version < 5:
        _to_world_scale(game)
    return game


def _to_world_scale(game) -> None:
    """4 -> 5: salaries and prices follow the world's level (Market.level_shift). An old save does
    not know the level its world started at; generated worlds start with the best sixth of
    players at ~70 (seeds 1-20 of the 120-club lab world), so that is taken as the start."""
    from .market import world_level
    m = game.sysm.market
    if m is not None:
        m.__dict__.setdefault("level_ref", min(WORLD_LEVEL_AT_START, world_level(game.clubs)))
        m.__dict__.setdefault("level_shift", 0.0)
        m.rescale(game.clubs)


def _to_contracts(game) -> None:
    """3 -> 4: contracts start to end. In an old save many have already run out while the player
    stayed for free; letting all of them go in one week would empty half the world, so each gets
    a few more months (4-52 weeks, from the save's seed) and normal talks from then on."""
    import random
    from collections import Counter
    m = game.sysm.market
    if m is not None:
        m.__dict__.setdefault("journal", [])
        m.__dict__.setdefault("stats", Counter())
        m.__dict__.setdefault("next_contract_id", 0)
        m.__dict__.setdefault("short_since", {})
    rng = random.Random(game.seed * 7919 + game.week)
    for c in game.clubs:
        for p in sorted(c.roster, key=lambda q: q.name):
            k = c.contracts.get(p.name)
            if k is None:
                continue
            if k.end_week < game.week + 4:
                k.end_week = game.week + rng.randint(4, 52)
            if m is not None and not k.contract_id:
                m.next_contract_id += 1
                k.contract_id = m.next_contract_id
    if game.run is not None and not hasattr(game.run, "invites"):
        game.run.invites = {}


def _to_leagues(game) -> None:
    """2 -> 3: leagues by the current ranking and the league calendar from the next week on;
    the season table starts empty."""
    from . import circuit, worldgen
    from .haceit import Haceit
    from .hltw import Hltw
    circuit.assign(game.clubs)
    game.calendar = worldgen.calendar()
    game.sysm.haceit, game.sysm.hltw = Haceit(game.seed), Hltw()


def save(game, path: str) -> int:
    data = dumps(game)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def load(path: str):
    with open(path, "rb") as f:
        return loads(f.read())
