"""No-regression checks for the *observational* ecosystem laboratory."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ecosystem_lab import AuditGame, run_world, summarize
from scripts.world_sim_lab import ObservedGame


def fingerprint(g):
    return (
        g.week,
        [(c.name, c.cash, c.debt, c.fans, c.rank,
          tuple((p.name, p.age, p.overall()) for p in c.roster))
         for c in g.clubs],
        sorted(g.sysm.market.stats.items()),
        len(g.sysm.market.free_agents),
        g.rng.getstate(),
        g.run.rng.getstate(),
    )


def test_observer_does_not_change_game_state_or_rng():
    baseline = ObservedGame.new(seed=9, n_clubs=24)
    lab = AuditGame.new(seed=9, n_clubs=24)
    assert fingerprint(baseline) == fingerprint(lab)
    for week in range(1, 5):
        baseline.advance()
        lab.advance()
        lab.observe_week(week, 1)
        assert fingerprint(baseline) == fingerprint(lab)


def test_money_reconciliation_handles_offseason_bookings():
    g = AuditGame.new(seed=3, n_clubs=24)
    # Booked BEFORE opening comparison: turnover operations should not
    # cause a false reconciliation alert in the next season.
    c = g.clubs[0]
    c.book(0, "initial_offset", 123.0, "prior to measurement")
    g.audit_open[id(c)] = (c.cash, c.fans, sum(c.money_season.values()))
    for week in range(1, 53):
        g.advance()
        g.observe_week(week, 1)
    assert len(g.audit_closed) == 1
    assert g.audit_closed[0]["reconciliation_failures"] == 0


@pytest.mark.slow
def test_real_one_season_has_lifecycle_and_money_outputs():
    world = run_world(4, 1, 24, "cassandra")
    assert len(world["rows"]) == 1
    row = world["rows"][0]
    assert row["metrics"]["clubs"] == 24
    assert row["metrics"]["finance_reconciliation_failures"] == 0
    assert isinstance(row["money_by_item"], dict)
    assert "salaries" in row["money_by_item"]
    assert row["metrics"]["completed_tenure_weeks_median"] >= 0
    assert row["metrics"]["paid_transfer_events"] >= 0


def test_aggregation_requires_unique_seeds(tmp_path: Path):
    w = {"schema": 1, "seed": 1, "seasons": 1, "clubs": 24,
         "rows": [{"metrics": {"seed": 1, "season": 1,
                               "finance_reconciliation_failures": 0,
                               "alerts": "", "cash_median": 100},
                   "money_by_item": {"salaries": -10},
                   "tier_money": {"tier3": {"salaries": -10}}}]}
    p = tmp_path / "world-000001.json"
    p.write_text(json.dumps(w), encoding="utf-8")
    report = summarize([p], tmp_path, expected_worlds=1)
    assert report["worlds"] == 1
    assert report["integrity"] == "NO_RECORDED_ALERTS"
    assert (tmp_path / "ecosystem_trends.csv").exists()
    assert (tmp_path / "ecosystem_summary.json").exists()
    q = tmp_path / "world-000002.json"
    q.write_text(json.dumps(w), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate seed"):
        summarize([p, q], tmp_path, expected_worlds=2)
