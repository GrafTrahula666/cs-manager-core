# cs-manager-core

Simulation core for an esports manager game: a tactical-FPS match engine calibrated on real match data.
Headless Python library, no UI. Design comes from the "Simulated Esports World" concept.

## Layout
- `src/csmcore/player.py` – the 20 base stats and a placeholder duel-skill formula
- `src/csmcore/engine.py` – seeded duel -> round -> map engine with a readable event log
- `scripts/parse_demo.py` – demo -> compact table (untested skeleton, needs `pip install -e ".[data]"`)
- `tests/` – determinism and sanity tests (`pytest`)

## Status
Early scaffold. All weights are placeholders. Next steps:
1. Find a legal demo source and parse a first batch.
2. Fit duel probabilities (weapon, economy, numbers advantage) from the parsed tables.
3. Add economy and round phases, then compare simulated vs. real stats (KD, ADR, favourite win rate).

## Run
```
pip install -e ".[dev]"
pytest
```
