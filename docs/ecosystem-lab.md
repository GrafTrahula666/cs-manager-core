# Ecosystem Laboratory — 100 worlds × 10 seasons on Money P1

## Scope and base

- Branch: `analysis/ecosystem-100x10-p1`, based on the exact Money P1
  development branch at commit `43d39c97ceb929ffb9ef16ec2086a660aaa25291`.
- This adds **only diagnostic files**, separate from the Claude implementation.
- Does not modify `src/csmcore/`, saves, data, match engine, AI decisions,
  revenues or transfer rules. No merges are performed.
- `AuditGame` subclasses the existing lab observer. Only read-only observations
  are made before original season rollover and after game.advance().
  No extra calls to the game's random generators.

## What is measured

The report contains a separate row for each seed and completed season:
- Player membership changes: direct club-to-club transitions, arrivals from
  outside a roster, exits from rosters, unique teams visited per player (3+ and 5+).
  Actual market journal events are counted separately, because direct roster
  changes and paid transactions are **not** the same thing.
- Transfers, free signings, academy players, renewals, refusals, expirations,
  and other contract events from the game's `Market.journal`.
- Completed club tenure spells in weeks, and separate *right-censored*
  current tenures. No claim of accurate real-life career lengths.
- Bankruptcies and other team removals at the end of a season. The removed-club
  metric includes nonbankruptcy world replacements and must not be presented
  as a bankruptcy count.
- All money postings grouped by item and tier, per-season revenue/expense
  totals, salaries, sponsorship, merch, content, prizes and transfers.
- Median club fan growth and the trajectory of cash by seed, season and tier.
  Associations are **not** causal proof. A follow-up intervention/ablation
  is needed to attribute money growth to fans.
- Opening/closing cash reconciliation: booked money vs actual cash change.
  Offseason entries already booked before opening are subtracted correctly.
- Standard correctness warnings from `world_sim_lab.snapshot` (separate from
  balance questions); 0 alerts cannot prove balanced behavior.

## Running

Full one-process run (expensive):
```bash
python scripts/ecosystem_lab.py --worlds 100 --seasons 10 --clubs 120 --seed-start 1 --director cassandra --output out/ecosystem
```

Test smoke:
```bash
python -m pytest -q tests/test_ecosystem_lab.py
python scripts/ecosystem_lab.py --worlds 1 --seasons 1 --clubs 24 --output out/ecosystem-smoke
```

Checkpoints: one atomic `world-000NNN.json` per world. Repeating the
same command reuses existing checkpoints after verifying seed, season count
and club count. For a *new code version*, **use a new output directory**:
checkpoint reuse must not be mistaken for validating a new commit.

The GitHub Actions workflow on this analysis branch runs regression tests
and a small live smoke first, then 10 isolated matrix jobs, each with 10
worlds (100 worlds total). A final aggregator downloads the 100 per-world
files, rejects duplicate seeds and inconsistent shapes and produces:

- `ecosystem_seasons.csv` — all 1,000 world-season observations.
- `ecosystem_trends.csv` — averages by season; not just season 10.
- `ecosystem_summary.json` — trends, income/expense by item and tier,
  integrity signal and explicit methodological limitations.
- `world-*.json` — traceable per-seed seasonal evidence.

Each shard uploads an artifact; a failed job is not a completed experiment.
A final artifact is uploaded only after all shards finish successfully.

## Interpretation and thresholds

Do **not** assign arbitrary “realistic” numbers to transfer volume or
bankruptcies. This initial experiment describes the game's baseline P1.
Investigate especially:

1. Number of players who visit 3 or 5 different clubs over ten seasons.
2. Whether completed-tenure distribution is excessively short, keeping
   censoring separate.
3. Whether transfers and salaries are affordable across tiers.
4. Tier-1 closures vs superteam substitutions or investor rebrands.
5. Cash growth by fan growth, revenue item, season and tier.
6. Whether the academy pipeline replaces retirements without overwhelming
   the professional free-agent market.

P1 remains a draft until independently validated. Do not merge this analysis
PR until the owner explicitly approves its results.
