"""Protect on-disk saves without changing the serialized game format."""

import gzip

import pytest

from csmcore import save
from csmcore.game import Game


def test_atomic_save_failure_keeps_previous_snapshot(tmp_path, monkeypatch):
    game = Game.new(seed=21, n_clubs=24)
    path = tmp_path / "career.sav"
    save.save(game, str(path))
    original = path.read_bytes()
    game.advance()

    def fail_replace(source, destination):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(save.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated rename failure"):
        save.save(game, str(path))

    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]  # no orphaned temporary save


def test_atomic_save_can_replace_and_reload(tmp_path):
    game = Game.new(seed=22, n_clubs=24)
    path = tmp_path / "career.sav"
    save.save(game, str(path))
    old_bytes = path.read_bytes()
    game.advance()

    written = save.save(game, str(path))
    assert written == len(path.read_bytes())
    assert path.read_bytes() != old_bytes
    assert save.load(str(path)).week == game.week
    assert list(tmp_path.iterdir()) == [path]


def test_truncated_header_raises_clear_error():
    with pytest.raises(ValueError, match="номер версии"):
        save.loads(save.MAGIC)


def test_corrupted_gzip_checksum_does_not_load():
    game = Game.new(seed=23, n_clubs=24)
    corrupted = bytearray(save.dumps(game))
    corrupted[-8] ^= 0x01  # first byte of gzip CRC32 footer
    with pytest.raises(gzip.BadGzipFile):
        save.loads(bytes(corrupted))
