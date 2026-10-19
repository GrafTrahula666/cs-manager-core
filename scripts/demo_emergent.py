"""Play a world for a few seasons and print the three richest causal chains nobody scripted:
each as a tree (effect at the top, causes below, with the reasons the person had), a Mermaid
graph, and who believes something false along the way.

    python scripts/demo_emergent.py --seed 3 --seasons 3 --out stories.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csmcore.emergent.history import chains, mermaid, render_tree  # noqa: E402
from csmcore.game import Game  # noqa: E402

ENDINGS = ("ask_to_leave", "article", "beat_former_club", "transfer", "reconcile", "public_jab", "leak",
           "freeze_out", "mediate", "side_with", "manager_decision", "retrospective")


def story_score(ew, f) -> float:
    anc = [ew.facts.get(i) for i in ew.facts.ancestors(f.id)]
    anc = [a for a in anc if a is not None] + [f]
    people = {p for a in anc for p in (a.actor, a.target, a.third) if p and ":" not in p}
    kinds = {a.kind for a in anc}
    acts = sum(1 for a in anc if a.data.get("action"))
    false = sum(1 for a in anc if a.misbelief)
    return f.depth + 0.6 * len(people) + 0.8 * len(kinds) + 0.3 * acts + 2 * false


def pick(ew, n=3):
    cands = [f for f in chains(ew, 4) if f.kind in ENDINGS]
    cands.sort(key=lambda f: (-story_score(ew, f), f.id))
    out, used, clubs = [], set(), set()
    for f in cands:
        anc = set(ew.facts.ancestors(f.id)) | {f.id}
        if anc & used or (f.club and f.club in clubs):
            continue            # three different stories, not three endings of one
        out.append(f)
        used |= anc
        clubs.add(f.club)
        if len(out) == n:
            break
    return out


def beliefs(ew, fid) -> list[str]:
    lines = []
    for i in sorted(set(ew.facts.ancestors(fid)) | {fid}):
        f = ew.facts.get(i)
        if f is None:
            continue
        for who, claim in sorted(f.misbelief.items()):
            lines.append(f"- {who} считает, что [{i}] сделал {claim.get('actor')}, а на самом деле {f.actor}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--seasons", type=int, default=3)
    ap.add_argument("--clubs", type=int, default=120)
    ap.add_argument("--out")
    a = ap.parse_args()
    g = Game.new(seed=a.seed, n_clubs=a.clubs)
    for _ in range(52 * a.seasons):
        g.advance()
    ew = g.sysm.emergent
    parts = [f"# Три истории мира (seed {a.seed}, {a.seasons} сезона, {a.clubs} клубов)\n",
             "Ни одна цепочка не задана сценарием: каждое звено — либо событие существующих систем "
             "(матчи, трансферы, сторилеты), либо действие из типизированного меню, выбранное человеком "
             "по его эмоциям, памяти и характеру. Под каждым действием — причины, которые у него были.\n"]
    for n, f in enumerate(pick(ew), 1):
        parts.append(f"## История {n}: {f.text}\n")
        parts.append(f"Клуб: {f.club or '—'}; глубина цепочки {f.depth}.\n")
        parts.append("```\n" + render_tree(ew.why(f.id, 7)) + "\n```\n")
        b = beliefs(ew, f.id)
        if b:
            parts.append("Ложные убеждения в этой цепочке:\n\n" + "\n".join(b) + "\n")
        parts.append("```mermaid\n" + mermaid(ew, f.id, 7) + "\n```\n")
    text = "\n".join(parts)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
