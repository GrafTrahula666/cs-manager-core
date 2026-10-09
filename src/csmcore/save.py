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
VERSION = 1


def dumps(game) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        pickle.dump(game, f, protocol=pickle.HIGHEST_PROTOCOL)
    return MAGIC + bytes([VERSION]) + buf.getvalue()


def loads(data: bytes):
    if not data.startswith(MAGIC):
        raise ValueError("это не сохранение CS MENEDGER")
    version = data[len(MAGIC)]
    if version != VERSION:
        raise ValueError(f"сохранение версии {version}, игра понимает {VERSION}")
    with gzip.GzipFile(fileobj=io.BytesIO(data[len(MAGIC) + 1:])) as f:
        return pickle.load(f)


def save(game, path: str) -> int:
    data = dumps(game)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def load(path: str):
    with open(path, "rb") as f:
        return loads(f.read())
