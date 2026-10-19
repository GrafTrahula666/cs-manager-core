"""The world's historical memory: careers, legends and retrospectives assembled from facts.

Nothing here is invented after the fact. A retrospective is a selection of facts that really
happened to a person (a debut, a breakout game, a title, a falling-out, a transfer and its
causes, a win over the old club), ordered and joined into prose. Each paragraph keeps the ids
of the facts it was built from, so the "почему?" view can open the causal graph behind it.
"""
from __future__ import annotations

from .facts import Fact

CONFLICT = {"public_jab", "open_conflict", "private_confront", "freeze_out", "side_with", "complain",
            "ask_to_leave", "transfer_request", "leak", "article"}


def career(ew, name: str) -> list[Fact]:
    return ew.history_of(name)


def score(ew, name: str) -> float:
    """How much history a person has: sum of the salience of facts about him."""
    return sum(f.salience for f in ew.facts.of_person(name))


def legends(ew, n: int = 5, min_score: float = 120.0) -> list[tuple[str, float]]:
    out = [(name, score(ew, name)) for name in sorted(ew.facts.by_person)]
    return sorted([x for x in out if x[1] >= min_score], key=lambda x: (-x[1], x[0]))[:n]


def _season(f: Fact) -> str:
    return f"в сезоне {f.season}"


def arc(ew, name: str) -> dict[str, list[Fact]]:
    fs = career(ew, name)
    mgr_against = [f for f in fs if f.kind == "manager_decision" and any(
        d < 0 for d in f.impacts.get(name, {}).values())]
    return {
        "origin": [f for f in fs if f.kind in ("debut", "signed")][:1],
        "rise": [f for f in fs if f.kind in ("standout", "became_star")][:3],
        "titles": [f for f in fs if f.kind == "title"],
        "conflict": [f for f in fs if f.kind in CONFLICT and (f.actor == name or f.target == name)][:4] + mgr_against[:2],
        "moves": [f for f in fs if f.kind in ("transfer", "released")],
        "revenge": [f for f in fs if f.kind == "beat_former_club"],
        "end": [f for f in fs if f.kind == "retired"],
    }


def retrospective(ew, name: str, now_season: int, journalist: str | None = None) -> dict:
    a = arc(ew, name)
    paras: list[tuple[str, list[int]]] = []
    if a["origin"]:
        f = a["origin"][0]
        paras.append((f"Всё началось {_season(f)}: {f.text}.", [f.id]))
    if a["rise"]:
        txt = " Потом ".join(x.text for x in a["rise"][:2])
        paras.append((f"О нём заговорили, когда {txt[0].lower() + txt[1:]}.", [x.id for x in a["rise"][:2]]))
    if a["titles"]:
        names = ", ".join(sorted({x.data.get("tournament", "?") for x in a["titles"]}))
        paras.append((f"Трофеи: {len(a['titles'])} ({names}).", [x.id for x in a["titles"][:4]]))
    if a["conflict"]:
        bits = "; ".join(x.text for x in a["conflict"][:3])
        paras.append((f"Но в раздевалке было неспокойно: {bits}.", [x.id for x in a["conflict"][:3]]))
    for mv in a["moves"][:3]:
        why = [ew.facts.get(c) for c in mv.causes]
        why = [w.text for w in why if w is not None and w.text][:2]
        tail = f" Причины: {'; '.join(why)}." if why else ""
        paras.append((f"{mv.text[0].upper() + mv.text[1:]} {_season(mv)}.{tail}", [mv.id] + mv.causes[:2]))
    for rv in a["revenge"][:2]:
        paras.append((f"И вот {_season(rv)} {rv.text}.", [rv.id]))
    if a["end"]:
        paras.append((a["end"][0].text + ".", [a["end"][0].id]))
    has = {k for k, v in a.items() if v}
    if {"revenge", "moves"} <= has and "conflict" in has:
        head = f"{name}: ссора, уход и реванш"
    elif "revenge" in has:
        head = f"{name} против бывших"
    elif {"rise", "titles"} <= has:
        head = f"Как {name} стал легендой"
    elif "conflict" in has and "moves" in has:
        head = f"Почему {name} ушёл"
    else:
        head = f"История {name}"
    years = now_season - (a["origin"][0].season if a["origin"] else min((f.season for f in career(ew, name)), default=now_season))
    lead = f"{journalist or 'Редакция'} вспоминает {years} {'год' if years == 1 else 'года' if 2 <= years <= 4 else 'лет'} истории." \
        if years > 0 else ""
    out = {"player": name, "headline": head, "lead": lead,
           "paragraphs": [p for p, _ in paras], "sources": [ids for _, ids in paras]}
    if ew.narrator is not None:
        out["text"] = ew.narrator.article(out, [ew.facts.get(i) for ids in out["sources"] for i in ids if ew.facts.get(i)])
    return out


def publish_retrospective(ew, ctx) -> str | None:
    """At a season start a journalist writes about the richest career nobody covered yet."""
    done = {ew.facts.get(i).target for i in ew.retrospectives if ew.facts.get(i)}
    for name, sc in legends(ew, 20, 150.0):
        if name in done:
            continue
        a = arc(ew, name)
        if sum(bool(v) for v in a.values()) < 3:
            continue
        j = max(ew.journalists, key=lambda x: (x.credibility, x.name))
        r = retrospective(ew, name, ctx.season, j.name)
        ids = [i for ids in r["sources"] for i in ids][:10]
        f = ew.emit(ctx, "retrospective", actor=j.id, target=name, causes=ids, salience=36, visibility="public",
                    engine_made=False, data={"headline": r["headline"]},
                    text=f"{j.name}, большой материал: «{r['headline']}»")
        ew.retrospectives.append(f.id)
        return f.text
    return None


# ---------- causal graph views ----------
def render_tree(node: dict, indent: int = 0) -> str:
    pad = "  " * indent
    head = f"{pad}{'└─ ' if indent else ''}[{node['id']}] " + (f"С{node['season']} Н{(node['week'] - 1) % 52 + 1}: " if "week" in node else "") + node["text"] + (" (см. выше)" if node.get("ref") else "")
    lines = [head]
    for r in node.get("reasons", [])[:3]:
        lines.append(f"{pad}   · {r}")
    for c in node.get("causes", []):
        lines.append(render_tree(c, indent + 1))
    return "\n".join(lines)


def mermaid(ew, fid: int, depth: int = 6) -> str:
    """Mermaid flowchart of a fact's causes (cause --> effect)."""
    lines = ["flowchart TD"]
    seen = set()

    def label(f):
        return f"{f.kind}: {f.text}".replace('"', "'")[:70]

    def walk(i, d):
        f = ew.facts.get(i)
        if f is None or i in seen:
            return
        seen.add(i)
        lines.append(f'  F{i}["{label(f)}"]')
        if d <= 0:
            return
        for c in f.causes:
            if ew.facts.get(c) is not None:
                walk(c, d - 1)
                lines.append(f"  F{c} --> F{i}")
    walk(fid, depth)
    return "\n".join(lines)


def chains(ew, min_depth: int = 3, kinds=None) -> list[Fact]:
    """Facts at the end of long causal chains, deepest first (for demos and tests)."""
    out = [f for f in ew.facts.facts.values() if f.depth >= min_depth and (kinds is None or f.kind in kinds)]
    return sorted(out, key=lambda f: (-f.depth, f.id))
