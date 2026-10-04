# cs-manager-core

Simulation core for an esports manager game: a tactical-FPS match engine calibrated on real match data.
Headless Python library, no UI. Design comes from the "Simulated Esports World" concept.

Design overview (RU): [docs/core-design.md](docs/core-design.md).

## Layout
- `src/csmcore/player.py` – the six layers: 20 base stats, 10 hidden personality axes, Gold Traits, dynamic state, history
- `src/csmcore/traits.py` + `data/traits.json` – data-driven Gold Traits (trigger/condition/modifier)
- `src/csmcore/relations.py` – social graph, team chemistry, tilt contagion
- `src/csmcore/economy.py` – club money flows, contracts, sponsors, tournaments, stickers, transfers
- `src/csmcore/decisions.py` – personality-driven decisions (contract acceptance, transfer request, conflict)
- `src/csmcore/world.py` – weekly world tick with emergent events and their causes
- `src/csmcore/storylets.py` + `data/events.json` – Crusader-Kings-style life events: conditions, weights, choices, chains
- `src/csmcore/development.py` – FM-style potential and monthly growth/decline
- `src/csmcore/scouting.py` – stat ranges and trait/personality reveal by knowledge
- `src/csmcore/promises.py` – promises to players, kept or broken
- `src/csmcore/squad.py` – dressing-room hierarchy, cliques, leader mood spread
- `src/csmcore/board.py` – owner objectives, confidence, sacking, next budget
- `src/csmcore/market.py` – AI transfer market, free agents, offers to the manager
- `src/csmcore/director.py` – RimWorld-style drama director (cassandra / phoebe / randy)
- `src/csmcore/rivalry.py` – club rivalries, player nemeses, nicknames (Nemesis-system style)
- `src/csmcore/chronicle.py` – world history, titles, Hall of Fame, headlines
- `src/csmcore/meta.py` – patches, role meta, map pool, map familiarity, Bo3 veto
- `src/csmcore/talks.py` – team talks and press conferences
- `src/csmcore/legacy.py` – retirements, second careers, new talents inheriting legends' traits
- `src/csmcore/season.py` – season loop: weeks, ranking-based invites, tournaments
- `src/csmcore/engine.py` – seeded duel -> round -> map engine (pistol/eco, pressure, chemistry)
- `scripts/demo_season.py` – one season of an 8-club world, prints money, results, events
- `scripts/parse_demo.py` – demo -> compact table (untested skeleton, needs `pip install -e ".[data]"`)
- `tests/` – determinism and sanity tests (`pytest`)

## Status
Early scaffold. All weights are placeholders. Next steps:
1. Find a legal demo source and parse a first batch.
2. Fit duel probabilities (weapon, economy, numbers advantage) from the parsed tables.
3. Add round phases, then compare simulated vs. real stats (KD, ADR, favourite win rate).
4. Manager actions API, AI clubs, player development, scouting uncertainty (see docs/core-design.md).

## Run
```
pip install -e ".[dev]"
pytest
python scripts/demo_season.py 1
cd scripts && python demo_world.py 2 3 cassandra   # several seasons, every system on
```
