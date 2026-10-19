# World Simulation Laboratory

A **diagnostic-only** harness for the existing CS Manager world. No modifications to
match probabilities, club finances, character logic or AI decisions.

## Default experiment: 100 worlds × 10 seasons

From the repository root, with Python >=3.10:

    python -m pip install -e ".[dev]"
    python scripts/world_sim_lab.py --worlds 100 --seasons 10 --clubs 120 \
        --seed-start 1 --director cassandra --output world-lab-output

Each world uses a different deterministic seed, starting at 1. The harness calls
the existing Game 52 times per season. It does **not** substitute its own season
logic or steer the manager: unanswered decisions follow the game's existing
assistant policy. Runs with large worlds and many tournaments can be expensive;
budget CPU time and disk space before starting the complete experiment.

Quick operational smoke test:

    python scripts/world_sim_lab.py --worlds 1 --seasons 1 --clubs 24 \
        --output world-lab-smoke

To continue after an interruption, repeat the **exact** original arguments and
add --resume. Each world is checkpointed with atomic JSON replacement; a
checkpoint is written only after all requested seasons for that world have
finished. An incomplete world is rerun from the same seed. The tool refuses
an incompatible manifest or incomplete checkpoint instead of silently mixing
data from different simulation configurations.

Run tests:

    python -m pytest tests/test_world_sim_lab.py -m "not slow" -q
    python -m pytest tests/test_world_sim_lab.py -q

The second command includes a full (one-world, one-season) core integration
smoke test; the first limits the suite to fast tests.

## Output

- manifest.json: experiment configuration, seeds and schema
- world-000001.json, etc.: one completed world per file, with per-season
  world snapshots, tier snapshots and actual observed story-event counts
- season_metrics.csv: one row per seed and season
- tier_metrics.csv: one row per seed, season and tier
- summary.json: means across completed worlds by season, recurring alerts,
  balance warnings and top twenty story event IDs

The default experiment produces 1,000 season rows and 4,000 tier rows
(assuming all four tiers are represented). These are **measurements**, not a
claim that all 1,000 seasons have been executed or validated.

## Metrics and interpretation

Per-season snapshot: surviving clubs, players, roster shortages, club finances
(cash distribution, debt, negative-cash and bankrupt clubs), average morale,
stress and fatigue, transfer requests, stars, free agents, retirements, firings,
titles, rivalries and cumulative event counts.

Fields ending in _this_season denote the delta between two season boundaries;
fields ending in _total denote the cumulative observation for that world.
original_clubs_lost and new_clubs_present compare current club names with
initial names; a rebrand is counted as a name change, not necessarily a closure.

For event counts the harness uses a small **read-only subclass** of Game that
observes the already generated per-week logs just before the game clears them.
It also observes the final week's log before Game switches to the next season.
This preserves the original game's RNG consumption and state transitions.

**Balance warnings** are inspection thresholds, not proven defects:
more than 30% bankrupt clubs, average stress above 85, or average fatigue above
90. **Correctness alerts** flag duplicated ranking positions or roster player
names, nonfinite finances, negative debts and out-of-range player states.
Use --fail-on-alerts for a nonzero exit code (2) if any alert is found.

Interpretation caveats:

1. A single seed is not a statistical conclusion; compare distributions across
   seeds, tiers and seasons.
2. The real match engine and economy still use provisional weights, so the
   simulation is not independently calibrated against professional CS2 data.
3. Consequences seen in the last-week season snapshot may already include the
   game's standard season rollover, rebrands and club replacements.
4. Each world is independent; there is no real-world historical calibration and
   no LLM-generated events introduced by the laboratory.
5. The probe is intentionally tied to the current Game log lifecycle. If that
   lifecycle changes, the observer parity regression test must be rerun.

## Development policy

Do not commit generated world-lab-output/ or world-lab-smoke/ data.
Keep diagnostic changes in a separate branch and open a Draft PR against the
existing feature branch, not directly into main while the core is still draft.
