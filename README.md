# cs-manager-core

Simulation core for an esports manager game: a tactical-FPS match engine calibrated on real match data.
Python library plus a browser prototype (`web/`). Design comes from the "Simulated Esports World" concept.

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
- `src/csmcore/secrets.py` – CK3-style secrets, discovery, hooks and leaks
- `src/csmcore/manager.py` – manager careers (reputation, sackings, hiring) and `ManagerDesk`, the one API for UI
- `src/csmcore/season.py` – season loop: weeks, ranking-based invites, tournaments; stepwise via `SeasonRun`
- `src/csmcore/worldgen.py` – procedural 100–150 club world: regions, tiers, rosters, sponsors, big-world calendar
- `src/csmcore/game.py` – one playable career: week clock, news, assistant, season rollover, sacking and new jobs
- `src/csmcore/save.py` – save/load the whole game (gzip pickle, exact continuation)
- `src/csmcore/api.py` – JSON-friendly facade for UIs
- `web/index.html` + `scripts/build_web.py` – browser prototype running the core in Pyodide
- `src/csmcore/engine.py` – seeded duel -> round -> map engine (pistol/eco, pressure, chemistry)
- `scripts/demo_season.py` – one season of an 8-club world, prints money, results, events
- `src/csmcore/emergent/` – Emergent World Engine: facts with knowers and false beliefs, minds, typed actions, causal graph (`docs/emergent-world.md`)
- `src/csmcore/circuit.py`, `haceit.py`, `hltw.py` – leagues Тир 1–3 and the rest with promotion and relegation; HACEIT (Elo, HPL, lower leagues, Major qualifier); HLTW (media ranking, player rating, MVP, Top 20) (`docs/leagues-and-media.md`)
- `src/csmcore/contracts.py` – contracts that end: extension talks, free transfers, a journal of every contract and hiring decision with its reasons, the academy fallback; the roster-core rule for invites is in `season.py` (`docs/contracts.md`, research vs. code: `docs/research-matrix.md`)
- `src/csmcore/matchstats.py`, `src/csmcore/demo_records.py` – the same match metrics for simulated maps and parsed demos
- `scripts/demo_analysis.py` – local CS2 demos -> round records (needs `pip install -e ".[data]"`; not yet run on a real demo)
- `scripts/compare_sim_real.py` – simulation vs. demo records, side by side (`docs/match-engine-plan.md`)
- `scripts/soak_world.py` – many seasons of the whole world: time, memory, save size, invariants
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
python scripts/build_web.py path/to/pyodide/package  # then serve web/dist and open index.html
```
