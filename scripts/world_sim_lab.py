#!/usr/bin/env python3
"""Read-only, seeded multi-world balance diagnostics for CS Manager.

Runs the existing Game unchanged. Each completed world is an atomic checkpoint.
This is a *measurement* tool, not an alternate simulation or balancing patch.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from csmcore.economy import WEEKS_PER_YEAR
from csmcore.game import Game

SCHEMA = 1
TIERS = ("super", "tier1", "tier2", "tier3")


class ObservedGame(Game):
    """Collect existing log entries immediately before Game discards them.

    No RNG is consumed, core state is not modified, and the original lifecycle
    methods still perform their normal work (including season rollover).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lab_stories: Counter[str] = Counter()
        self.lab_world_events: Counter[str] = Counter()
        self.lab_series = 0
        self.lab_management_notes = 0

    def _observe(self):
        log = self.run.log
        self.lab_stories.update(f.event_id for f in log.stories)
        self.lab_world_events.update(e.kind for e in log.events)
        self.lab_series += len(log.results)
        self.lab_management_notes += len(log.management)

    def _trim(self):
        self._observe()
        super()._trim()

    def _new_season(self):
        # Game switches to a new SeasonRun before calling _trim at week 52.
        self._observe()
        return super()._new_season()


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    pos = (len(values) - 1) * p
    low, high = math.floor(pos), math.ceil(pos)
    return values[low] + (values[high] - values[low]) * (pos - low)


def average(values):
    return statistics.fmean(values) if values else 0.0


def _round(value):
    return round(float(value), 3)


def tier_metrics(clubs):
    cash = [c.cash for c in clubs]
    debt = [c.debt for c in clubs]
    return {
        "clubs": len(clubs),
        "cash_median": _round(statistics.median(cash)) if cash else 0,
        "cash_p10": _round(percentile(cash, .1)),
        "cash_p90": _round(percentile(cash, .9)),
        "negative_cash_clubs": sum(c.cash < 0 for c in clubs),
        "bankrupt_clubs": sum(c.bankrupt for c in clubs),
        "debt_clubs": sum(c.debt > 0 for c in clubs),
        "total_debt": _round(sum(debt)),
        "understaffed_clubs": sum(len(c.roster) < 5 for c in clubs),
    }


def snapshot(game):
    """Snapshot public world state; do not mutate or call random methods."""
    clubs = game.clubs
    players = [p for c in clubs for p in c.roster]
    by_tier = {t: tier_metrics([c for c in clubs if c.tier == t]) for t in TIERS}
    overall = tier_metrics(clubs)
    morale = [p.s("morale") for p in players]
    stress = [p.s("stress") for p in players]
    fatigue = [p.s("fatigue") for p in players]
    manager_system = game.sysm.careers
    managers = list(manager_system.managers.values()) + manager_system.pool if manager_system else []
    chronicle = game.sysm.chronicle
    retired = game.sysm.legacy.retired if game.sysm.legacy else []
    market = game.sysm.market
    metrics = {
        **overall,
        "players": len(players),
        "avg_morale": _round(average(morale)),
        "avg_stress": _round(average(stress)),
        "avg_fatigue": _round(average(fatigue)),
        "transfer_requests": sum("transfer_requested" in p.flags for p in players),
        "star_players": sum("star" in p.flags for p in players),
        "free_agents": len(market.free_agents) if market else 0,
        "retirements_total": len(retired),
        "sackings_total": sum(m.sackings for m in managers),
        "titles_total": sum(len(v) for v in chronicle.titles.values()) if chronicle else 0,
        "active_rivalries": sum(r.score >= 40 for r in game.sysm.rivalries.clubs.values())
        if game.sysm.rivalries else 0,
        "story_events_total": sum(game.lab_stories.values()),
        "world_events_total": sum(game.lab_world_events.values()),
        "match_series_total": game.lab_series,
        "management_notes_total": game.lab_management_notes,
    }
    alerts = set()
    if not clubs:
        alerts.add("no_clubs")
    ranks = [c.rank for c in clubs]
    if len(set(ranks)) != len(ranks):
        alerts.add("duplicate_ranking")
    names = [p.name for p in players]
    if len(set(names)) != len(names):
        alerts.add("duplicate_roster_player_name")
    for c in clubs:
        if not all(math.isfinite(x) for x in (c.cash, c.debt, c.rating_points)):
            alerts.add("non_finite_club_finances_or_rank_points")
        if c.debt < 0:
            alerts.add("negative_debt")
    for values in (morale, stress, fatigue):
        if any(not math.isfinite(v) or v < 0 or v > 100 for v in values):
            alerts.add("invalid_player_state")
    # Heuristic balance warnings, NOT correctness violations.
    warnings = set()
    if clubs and metrics["bankrupt_clubs"] / len(clubs) > .30:
        warnings.add("over_30pct_bankrupt")
    if metrics["avg_stress"] > 85:
        warnings.add("very_high_average_stress")
    if metrics["avg_fatigue"] > 90:
        warnings.add("very_high_average_fatigue")
    return metrics, by_tier, sorted(alerts), sorted(warnings)


def run_world(seed, seasons, clubs, director):
    """Advance the real simulation by 52 weeks per season, with no interventions."""
    game = ObservedGame.new(seed=seed, n_clubs=clubs, director=director)
    original_club_names = {c.name for c in game.clubs}
    rows = []
    previous = Counter()
    totals = ("story_events", "world_events", "match_series", "management_notes")
    for season in range(1, seasons + 1):
        for _ in range(WEEKS_PER_YEAR):
            game.advance()
        metrics, tiers, alerts, warnings = snapshot(game)
        counters = Counter({
            "story_events": metrics["story_events_total"],
            "world_events": metrics["world_events_total"],
            "match_series": metrics["match_series_total"],
            "management_notes": metrics["management_notes_total"],
        })
        for key in totals:
            metrics[key + "_this_season"] = counters[key] - previous[key]
        previous = counters
        current_names = {c.name for c in game.clubs}
        metrics["original_clubs_lost"] = len(original_club_names - current_names)
        metrics["new_clubs_present"] = len(current_names - original_club_names)
        rows.append({"seed": seed, "season": season, "metrics": metrics,
                     "by_tier": tiers, "alerts": alerts, "warnings": warnings})
    return {"schema": SCHEMA, "seed": seed, "rows": rows,
            "story_counts": dict(sorted(game.lab_stories.items())),
            "world_event_counts": dict(sorted(game.lab_world_events.items()))}


def atomic_json(path, data):
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def export_csv(path, rows, tiers=False):
    if tiers:
        data = [{"seed": r["seed"], "season": r["season"], "tier": tier, **metrics}
                for r in rows for tier, metrics in r["by_tier"].items()]
    else:
        data = [{"seed": r["seed"], "season": r["season"], **r["metrics"],
                 "alerts": "|".join(r["alerts"]), "warnings": "|".join(r["warnings"])}
                for r in rows]
    if not data:
        return
    fields = list(data[0])
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def summarize(worlds, config):
    rows = [row for w in worlds for row in w["rows"]]
    by_season = defaultdict(list)
    alerts, warnings, stories = Counter(), Counter(), Counter()
    for row in rows:
        by_season[row["season"]].append(row["metrics"])
        alerts.update(row["alerts"])
        warnings.update(row["warnings"])
    for world in worlds:
        stories.update(world["story_counts"])
    trends = {}
    for season, items in sorted(by_season.items()):
        keys = items[0]
        trends[str(season)] = {
            k: _round(average([r[k] for r in items]))
            for k in keys if isinstance(items[0][k], (int, float))
        }
    catalog = set()
    for world in worlds:
        catalog.update(world["story_counts"])
    return {"schema": SCHEMA, "config": config, "completed_worlds": len(worlds),
            "completed_world_seasons": len(rows), "mean_by_season": trends,
            "alert_season_counts": dict(sorted(alerts.items())),
            "warning_season_counts": dict(sorted(warnings.items())),
            "observed_story_types": len(catalog),
            "story_frequency_top_20": stories.most_common(20),
            "note": "Aggregated season-end snapshots. Cumulative counters and per-season "
                    "deltas have different meanings; warnings are heuristic, not proven bugs."}


def positive_int(s):
    x = int(s)
    if x < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return x


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worlds", type=positive_int, default=100)
    p.add_argument("--seasons", type=positive_int, default=10)
    p.add_argument("--clubs", type=positive_int, default=120)
    p.add_argument("--seed-start", type=positive_int, default=1)
    p.add_argument("--director", choices=("cassandra", "phoebe", "randy"),
                   default="cassandra")
    p.add_argument("--output", type=Path, default=Path("world-lab-output"))
    p.add_argument("--resume", action="store_true",
                   help="Reuse verified completed-world checkpoints")
    p.add_argument("--fail-on-alerts", action="store_true",
                   help="Return exit code 2 if correctness alerts were observed")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = {"worlds": args.worlds, "seasons": args.seasons, "clubs": args.clubs,
              "seed_start": args.seed_start, "director": args.director, "schema": SCHEMA}
    output = args.output
    manifest = output / "manifest.json"
    output.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        with manifest.open(encoding="utf-8") as f:
            existing = json.load(f)
        if existing != config:
            raise SystemExit("Output manifest differs: use a new --output directory")
        if not args.resume:
            raise SystemExit("Output already initialized: pass --resume to continue")
    else:
        if list(output.iterdir()):
            raise SystemExit("Output directory is nonempty and has no manifest")
        atomic_json(manifest, config)

    worlds = []
    for i in range(args.worlds):
        seed = args.seed_start + i
        path = output / f"world-{seed:06d}.json"
        if path.exists():
            if not args.resume:
                raise SystemExit(f"Checkpoint already exists: {path}")
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if (data.get("schema") != SCHEMA or data.get("seed") != seed
                    or len(data.get("rows", [])) != args.seasons):
                raise SystemExit(f"Incompatible checkpoint: {path}")
            print(f"[{i + 1}/{args.worlds}] seed={seed}: checkpoint", flush=True)
        else:
            data = run_world(seed, args.seasons, args.clubs, args.director)
            atomic_json(path, data)
            print(f"[{i + 1}/{args.worlds}] seed={seed}: {args.seasons} seasons complete",
                  flush=True)
        worlds.append(data)

    rows = [r for w in worlds for r in w["rows"]]
    export_csv(output / "season_metrics.csv", rows)
    export_csv(output / "tier_metrics.csv", rows, tiers=True)
    summary = summarize(worlds, config)
    atomic_json(output / "summary.json", summary)
    print(f"Results: {output / 'summary.json'}")
    print(f"Observed story types: {summary['observed_story_types']}; "
          f"alert-season count: {sum(summary['alert_season_counts'].values())}")
    return 2 if args.fail_on_alerts and summary["alert_season_counts"] else 0


if __name__ == "__main__":
    sys.exit(main())
