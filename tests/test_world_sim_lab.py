"""Regression and contract checks for the read-only world simulation lab."""
import csv
import json

import pytest

from scripts import world_sim_lab as lab
from csmcore.game import Game


def test_percentile_and_empty_average():
    assert lab.percentile([], .5) == 0
    assert lab.percentile([1, 3, 9], .5) == 3
    assert lab.percentile([1, 3, 9], .25) == 2
    assert lab.average([]) == 0


def test_snapshot_does_not_advance_rng_or_change_world():
    game = lab.ObservedGame.new(seed=7, n_clubs=24)
    before = [(c.name, c.cash, c.rank, [p.name for p in c.roster])
              for c in game.clubs]
    rng_before = game.rng.getstate()
    a, tiers, errors, warnings = lab.snapshot(game)
    b, _, _, _ = lab.snapshot(game)
    after = [(c.name, c.cash, c.rank, [p.name for p in c.roster])
             for c in game.clubs]
    assert a == b and a["clubs"] == 24
    assert sum(v["clubs"] for v in tiers.values()) == 24
    assert before == after and game.rng.getstate() == rng_before
    assert not errors
    assert isinstance(warnings, list)


def test_observed_game_preserves_original_weekly_results():
    original = Game.new(seed=19, n_clubs=24)
    observed = lab.ObservedGame.new(seed=19, n_clubs=24)
    for _ in range(3):
        a, b = original.advance(), observed.advance()
        assert a.lines == b.lines
        assert [(c.name, c.rank, c.cash) for c in original.clubs] == [
            (c.name, c.rank, c.cash) for c in observed.clubs
        ]
    assert observed.lab_series >= 0


def test_report_resume_and_csv(tmp_path, monkeypatch):
    calls = []

    def fake_run_world(seed, seasons, clubs, director):
        calls.append(seed)
        return {
            "schema": lab.SCHEMA, "seed": seed,
            "rows": [{
                "seed": seed, "season": season,
                "metrics": {"clubs": clubs, "bankrupt_clubs": seed - 1},
                "by_tier": {"super": {"clubs": clubs}},
                "alerts": [], "warnings": [],
            } for season in range(1, seasons + 1)],
            "story_counts": {"example_event": 2}, "world_event_counts": {},
        }

    monkeypatch.setattr(lab, "run_world", fake_run_world)
    out = tmp_path / "lab"
    args = ["--worlds", "2", "--seasons", "2", "--clubs", "24",
            "--output", str(out)]
    assert lab.main(args) == 0
    assert calls == [1, 2]
    assert lab.main(args + ["--resume"]) == 0
    assert calls == [1, 2]  # no rerun
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["completed_world_seasons"] == 4
    assert summary["observed_story_types"] == 1
    assert summary["mean_by_season"]["1"]["bankrupt_clubs"] == .5
    with (out / "season_metrics.csv").open(newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 4
    with (out / "tier_metrics.csv").open(newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 4
    with pytest.raises(SystemExit, match="manifest differs"):
        lab.main(args + ["--resume", "--clubs", "30"])
    with pytest.raises(SystemExit, match="already initialized"):
        lab.main(args)


def test_fail_on_alerts(tmp_path, monkeypatch):
    def warning_world(seed, seasons, clubs, director):
        return {
            "schema": lab.SCHEMA, "seed": seed,
            "rows": [{
                "seed": seed, "season": 1, "metrics": {"clubs": clubs},
                "by_tier": {"tier3": {"clubs": clubs}},
                "alerts": ["duplicate_ranking"], "warnings": [],
            }],
            "story_counts": {}, "world_event_counts": {},
        }

    monkeypatch.setattr(lab, "run_world", warning_world)
    assert lab.main(["--worlds", "1", "--seasons", "1",
                     "--output", str(tmp_path / "lab"),
                     "--fail-on-alerts"]) == 2


@pytest.mark.slow
def test_one_real_season_smoke():
    """Runs only when explicitly selected; the full default would be 1000 seasons."""
    world = lab.run_world(seed=3, seasons=1, clubs=24, director="cassandra")
    row = world["rows"][0]
    assert row["season"] == 1 and row["metrics"]["clubs"] == 24
    assert row["metrics"]["story_events_this_season"] >= 0
    assert row["metrics"]["match_series_this_season"] >= 0
    assert row["metrics"]["titles_total"] >= 0
    assert len(world["story_counts"]) > 0
