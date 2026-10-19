"""Several seasons with every system on: drama director, rivalries, patches and map pool,
market, owners, development, retirements and new talents, chronicle and Hall of Fame.

    python scripts/demo_world.py [seed] [seasons] [director: cassandra|phoebe|randy]
"""
from __future__ import annotations

import random
import sys

from demo_season import ROLES, build_world

from csmcore.board import Owner
from csmcore.chronicle import Chronicle
from csmcore.director import Director
from csmcore.economy import Sponsor
from csmcore.generate import make_player
from csmcore.legacy import Legacy
from csmcore.manager import Careers
from csmcore.secrets import Secrets
from csmcore.market import Market
from csmcore.meta import Meta
from csmcore.rivalry import Rivalries
from csmcore.season import Systems, run_season
from csmcore.storylets import StoryEngine
from csmcore.talks import team_talk


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    seasons = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    mode = sys.argv[3] if len(sys.argv) > 3 else "cassandra"
    rng = random.Random(seed + 7)
    clubs, graph, calendar = build_world(seed)
    director = Director(mode)
    sysm = Systems(
        stories=StoryEngine(director=director),
        market=Market(free_agents=[make_player(f"fa{i}", rng.uniform(50, 66), rng, ROLES[i % 5]) for i in range(10)]),
        owners={c.name: Owner(f"owner{c.name}", patience=rng.uniform(20, 80), ambition=rng.uniform(30, 90),
                              money_focus=rng.uniform(20, 80)) for c in clubs},
        rivalries=Rivalries(), meta=Meta(), chronicle=Chronicle(), legacy=Legacy(),
        secrets=Secrets(), careers=Careers(),
    )
    everyone = {p.name: p for c in clubs for p in c.roster}
    for s in range(1, seasons + 1):
        start = (s - 1) * 52
        for c in clubs:
            c.rating_points *= 0.5
            c.sponsors = [Sponsor(f"{c.name} HW", "hardware", sp, start + 52) for sp in [max(50_000, c.brand * 20_000)]]
            sysm.owners[c.name].objectives = []
        run_season(clubs, graph, calendar, seed * 100 + s, systems=sysm, season=s, start_week=start)
        for c in clubs:
            everyone.update({p.name: p for p in c.roster})

    ch = sysm.chronicle
    print(f"Режиссёр: {mode}. Сезонов: {seasons}. Записей в летописи: {len(ch.entries)}\n")
    print("Титулы клубов:")
    for club, t in sorted(ch.titles.items(), key=lambda kv: -len(kv[1])):
        print(f"  {club}: {len(t)} — {', '.join(t[-3:])}")
    print("\nЛетопись (последние 18 записей без титулов):")
    for h in ch.headlines(18, kinds=("final", "transfer", "story", "rivalry", "retirement", "patch", "board")):
        print("  " + h)
    print("\nСамые горячие соперничества:")
    top = sorted(sysm.rivalries.clubs.items(), key=lambda kv: -kv[1].score)[:3]
    for pair, r in top:
        a, b = sorted(pair)
        print(f"  {a} vs {b}: {r.score:.0f}/100, встреч {r.meetings}, счёт {r.wins}")
    if sysm.rivalries.nemesis:
        print("  Немезиды: " + ", ".join(f"{k}→{v}" for v, k in list(sysm.rivalries.nemesis.items())[:4]))
    if sysm.rivalries.titles:
        print("  Прозвища: " + ", ".join(f"{p} «{t}»" for p, t in sysm.rivalries.titles.items()))
    retired = [r.player for r in sysm.legacy.retired]
    print("\nЗал славы:")
    for name, score in ch.hall_of_fame(list(everyone.values()) + retired, min_score=30)[:6]:
        print(f"  {name}: {score}")
    print(f"\nЗавершили карьеру: {len(retired)}, новых талантов: {len(sysm.legacy.born)}")
    for r in sysm.legacy.retired[:5]:
        print(f"  {r.player.name} ({r.player.age}) → {r.second_career}" + (f" в {r.club}" if r.club else ""))
    heirs = [p for p in sysm.legacy.born if any("легенды" in h for h in p.history)]
    for p in heirs[:2]:
        print(f"  талант {p.name}: {p.history[-1]}")
    sec = sysm.secrets
    print(f"\nСекреты: всего {len(sec.items)}, раскрыто {sum(s.exposed for s in sec.items)}")
    for s in sec.items[:4]:
        print(f"  {s.player}: {s.kind}, знают {sorted(s.known_by)[:4]}" + (" — ВСПЛЫЛ" if s.exposed else ""))
    print("\nМенеджеры:")
    for club, m in sorted(sysm.careers.managers.items()):
        print(f"  {club}: {m.name}, репутация {m.reputation:.0f}, титулов {m.titles}, увольнений {m.sackings}")
    for m in sysm.careers.pool[:3]:
        print(f"  без работы: {m.name}, репутация {m.reputation:.0f}, {m.history[-1]}")
    print("\nРазговор перед финалом (Club2, тон «требовательный», фаворит):")
    for r in team_talk(clubs[1], "demand", favourite=True):
        print(f"  {r.player}: {r.text} (мораль {r.delta_morale:+})")


if __name__ == "__main__":
    main()
