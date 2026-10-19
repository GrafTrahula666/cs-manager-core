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
VERSION = 3
# Version history: 1 = before the emergent world engine; 2 = sysm.emergent (facts, minds, press);
# 3 = leagues (Тир 1-3 and the rest), HACEIT and HLTW.
SUPPORTED = (1, 2, 3)


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
    return game


def _to_leagues(game) -> None:
    """2 -> 3: leagues by the current ranking and the league calendar from the next week on;
    the season table starts empty."""
    from . import circuit, worldgen
    circuit.assign(game.clubs)
    game.calendar = worldgen.calendar()


def save(game, path: str) -> int:
    data = dumps(game)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def load(path: str):
    with open(path, "rb") as f:
        return loads(f.read())
