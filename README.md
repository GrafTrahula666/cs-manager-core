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
```
