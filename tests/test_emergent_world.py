"""The emergent engine inside the real game: saves, migration, determinism, long runs."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from csmcore import api, save
from csmcore.emergent.invariants import engine as engine_inv, social as social_inv
from csmcore.game import Game

ROOT = Path(__file__).resolve().parents[1]


def digest(g) -> str:
    ew = g.sysm.emergent
    rows = [(f.id, f.week, f.kind, f.actor, f.target, f.third, round(f.salience, 3), tuple(f.causes))
            for f in ew.facts.facts.values()]
    minds = sorted((n, sorted((k, round(v, 3)) for k, v in m.emotions.items())) for n, m in ew.minds.minds.items())
    return hashlib.sha256(repr((rows, minds)).encode()).hexdigest()


def test_save_load_continues_identically_with_the_engine():
    g = Game.new(seed=11, n_clubs=40)
    for _ in range(15):
        g.advance()
    g2 = save.loads(save.dumps(g))
    assert digest(g2) == digest(g)
    for _ in range(15):
        g.advance(), g2.advance()
    assert digest(g2) == digest(g)
    assert g.sysm.emergent.facts.next_id > 100


def test_a_version_1_save_gets_an_engine_and_keeps_playing():
    g = Game.new(seed=5, n_clubs=40)
    for _ in range(5):
        g.advance()
    g.sysm.emergent = None
    del g.sysm.__dict__["emergent"]        # exactly what an old pickle looks like
    raw = save.dumps(g)
    old = raw[:len(save.MAGIC)] + bytes([1]) + raw[len(save.MAGIC) + 1:]
    g2 = save.loads(old)
    ew = g2.sysm.emergent
    assert ew is not None and not ew.facts.facts
    for _ in range(8):
        g2.advance()
    # the first look only records who plays where: no flood of invented signings
    assert sum(1 for f in ew.facts.facts.values() if f.kind in ("signed", "debut", "transfer")) < 20
    assert ew.facts.next_id > 20 and not engine_inv(ew)


SCRIPT = """
import sys, hashlib
sys.path.insert(0, {src!r}); sys.path.insert(0, {tests!r})
from test_emergent_world import digest
from csmcore.game import Game
g = Game.new(seed=21, n_clubs=24)
for _ in range(14):
    g.advance()
print(digest(g))
"""


def test_same_seed_same_world_in_another_process():
    code = SCRIPT.format(src=str(ROOT / "src"), tests=str(ROOT / "tests"))
    outs = []
    for hs in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        outs.append(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                   check=True).stdout.strip())
    assert outs[0] == outs[1] and len(outs[0]) == 64


def test_two_seasons_on_two_seeds_keep_every_invariant():
    for seed in (1, 2):
        g = Game.new(seed=seed, n_clubs=24)
        for _ in range(104):
            g.advance()
        ew = g.sysm.emergent
        assert not social_inv(g.clubs, g.graph), social_inv(g.clubs, g.graph)[:5]
        assert not engine_inv(ew), engine_inv(ew)[:5]
        assert len(ew.facts.facts) < 5000                 # pruning keeps the store flat
        people = sum(len(c.roster) for c in g.clubs) + len(g.sysm.market.free_agents)
        assert len(ew.minds.minds) <= people + 200
        kinds = {f.kind for f in ew.facts.facts.values()}
        assert {"standout", "title", "transfer"} <= kinds


def test_api_shows_what_the_club_knows():
    api.new_game(seed=3, n_clubs=40)
    for _ in range(26):
        api.advance(1)
        for s in api.situations():
            if s["open"]:
                api.answer_situation(s["id"], s["options"][0]["key"])
    st = api.state()
    assert "situations" in st
    feed = api.world_feed(10)
    assert feed and all({"fact", "text", "kind"} <= set(x) for x in feed)
    tree = api.why(feed[0]["fact"])
    assert tree["id"] == feed[0]["fact"] and "reasons" in tree
    assert not tree["reasons"]                      # hidden numbers stay hidden from the manager
    assert api.why(feed[0]["fact"], god=True)["text"]
    for r in api.reports(5):
        assert r["how"]
    data = api.save_b64()
    api.load_b64(data)
    assert api.state()["club"] == st["club"]
