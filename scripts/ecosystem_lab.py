#!/usr/bin/env python3
"""Observational 100-world ecosystem laboratory (no game-rule changes).

Tracks player/club lifecycles, actual market decisions and season-close cash
flows. No game RNG draws; all state reads are side-effect-free.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from csmcore.economy import WEEKS_PER_YEAR
from world_sim_lab import ObservedGame, atomic_json, snapshot


def median(xs):
    return round(statistics.median(xs), 3) if xs else 0.0


def mean(xs):
    return round(statistics.fmean(xs), 3) if xs else 0.0


class AuditGame(ObservedGame):
    """Only observes; does not replace or suppress any existing game action."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.audit_open = {id(c): (c.cash, c.fans, sum(c.money_season.values())) for c in self.clubs}
        self.audit_closed = []
        self.audit_market_cursor = len(self.sysm.market.journal)
        self.audit_market_events = []
        self.audit_membership = {p.name: id(c) for c in self.clubs for p in c.roster}
        self.audit_started = {p.name: 0 for c in self.clubs for p in c.roster}
        self.audit_clubs_visited = defaultdict(set)
        for c in self.clubs:
            for p in c.roster:
                self.audit_clubs_visited[p.name].add(id(c))
        self.audit_completed_spells = []
        self.audit_direct_moves = Counter()
        self.audit_from_free = Counter()
        self.audit_to_free = Counter()

    def _new_season(self):
        # Called by Game exactly when 52 weeks have elapsed and *before*
        # close_money_season(), bankruptcies, rebrands and team replacement.
        before = list(self.clubs)
        clubs = []
        items = Counter()
        tier_items = defaultdict(Counter)
        residuals = []
        fan_growth = []
        for club in before:
            money = dict(getattr(club, "money_season", {}))
            items.update(money)
            tier_items[club.tier].update(money)
            opened_cash, opened_fans, already_booked = self.audit_open.get(id(club), (None, None, 0.0))
            if opened_cash is not None:
                residuals.append(club.cash - opened_cash - (sum(money.values()) - already_booked))
            if opened_fans and opened_fans > 0:
                fan_growth.append(club.fans / opened_fans - 1)
            clubs.append({
                "name": club.name, "tier": club.tier, "cash": club.cash,
                "fans": club.fans, "rank": club.rank, "roster": len(club.roster),
                "bankrupt": bool(club.bankrupt),
            })
        notes = super()._new_season()
        survivors = {id(c) for c in self.clubs}
        removed = Counter(c.tier for c in before if id(c) not in survivors)
        closures = sum("закрылся после банкротства" in line for line in notes)
        self.audit_closed.append({
            "clubs": clubs,
            "money": dict(sorted(items.items())),
            "tier_money": {k: dict(sorted(v.items())) for k, v in sorted(tier_items.items())},
            "reconciliation_max_abs": round(max((abs(v) for v in residuals), default=0), 5),
            "reconciliation_failures": sum(abs(v) > 0.01 for v in residuals),
            "fan_growth_median": median(fan_growth),
            "fan_growth_mean": mean(fan_growth),
            "removed_by_tier": dict(sorted(removed.items())),
            "bankruptcy_closure_messages": closures,
            "rollover_messages": [s for s in notes if
                "закрылся" in s or "инвестор купил" in s or "исчез" in s],
        })
        # Transactions in the rollover belong to next season, so record opening
        # cash *after* the real game's offseason actions.
        self.audit_open = {id(c): (c.cash, c.fans, sum(c.money_season.values())) for c in self.clubs}
        return notes

    def observe_week(self, absolute_week: int, season: int):
        market = self.sysm.market
        journal = market.journal
        self.audit_market_events.extend(journal[self.audit_market_cursor:])
        self.audit_market_cursor = len(journal)

        current = {p.name: id(c) for c in self.clubs for p in c.roster}
        for name in set(self.audit_membership) | set(current):
            prev = self.audit_membership.get(name)
            now = current.get(name)
            if prev == now:
                continue
            if prev is not None:
                self.audit_completed_spells.append(absolute_week -
                                                    self.audit_started.get(name, 0))
                self.audit_started.pop(name, None)
            if now is not None:
                self.audit_started[name] = absolute_week
                self.audit_clubs_visited[name].add(now)
            if prev is not None and now is not None:
                self.audit_direct_moves[season] += 1
            elif prev is None and now is not None:
                self.audit_from_free[season] += 1
            elif prev is not None and now is None:
                self.audit_to_free[season] += 1
        self.audit_membership = current


def run_world(seed: int, seasons: int, clubs: int, director: str):
    game = AuditGame.new(seed=seed, n_clubs=clubs, director=director)
    rows = []
    previous_journal = 0
    for season in range(1, seasons + 1):
        for wk in range(1, WEEKS_PER_YEAR + 1):
            game.advance()
            game.observe_week((season - 1) * WEEKS_PER_YEAR + wk, season)
        finance = game.audit_closed[-1]
        state, tiers, alerts, warnings = snapshot(game)
        events = game.audit_market_events[previous_journal:]
        previous_journal = len(game.audit_market_events)
        kinds = Counter(e.get("kind", "unknown") for e in events)
        money = finance["money"]
        clubs_closed = finance["bankruptcy_closure_messages"]
        revenue = sum(v for v in money.values() if v > 0)
        expenses = -sum(v for v in money.values() if v < 0)
        remaining_spells = [
            season * WEEKS_PER_YEAR - game.audit_started[name]
            for name in game.audit_membership if name in game.audit_started
        ]
        fields = {
            "seed": seed, "season": season,
            "clubs": state["clubs"], "players": state["players"],
            "free_agents": state["free_agents"],
            "understaffed": state["understaffed_clubs"],
            "cash_median": state["cash_median"], "cash_p90": state["cash_p90"],
            "negative_cash": state["negative_cash_clubs"],
            "total_debt": state["total_debt"],
            "transfer_requests": state["transfer_requests"],
            "paid_transfer_events": kinds["transferred"],
            "free_signings": kinds["signed_free"],
            "renewals": kinds["renewed"], "renewal_refusals": kinds["renewal_refused"],
            "contracts_expired": kinds["expired_left"],
            "not_offered": kinds["not_offered"],
            "signing_refusals": kinds["signing_refused"],
            "academy_signings": kinds["academy_signed"] + kinds["academy_signing"],
            "direct_roster_moves": game.audit_direct_moves[season],
            "roster_entries_from_nonclub": game.audit_from_free[season],
            "roster_exits_to_nonclub": game.audit_to_free[season],
            "bankruptcy_closures": clubs_closed,
            "removed_club_objects": sum(finance["removed_by_tier"].values()),
            "tier1_removed_objects": finance["removed_by_tier"].get("tier1", 0),
            "finance_reconciliation_failures": finance["reconciliation_failures"],
            "finance_reconciliation_max_abs": finance["reconciliation_max_abs"],
            "fan_growth_median": finance["fan_growth_median"],
            "fan_growth_mean": finance["fan_growth_mean"],
            "revenue": round(revenue, 2), "expenses": round(expenses, 2),
            "salaries_paid": round(-money.get("salaries", 0.0), 2),
            "sponsors_income": round(money.get("sponsors", 0.0), 2),
            "merch_income": round(money.get("merch", 0.0), 2),
            "content_income": round(money.get("content", 0.0), 2),
            "prize_income": round(money.get("prizes", 0.0), 2),
            "transfer_in_spend": round(-money.get("transfers_in", 0.0), 2),
            "transfer_out_income": round(money.get("transfers_out", 0.0), 2),
            "completed_tenure_weeks_median": median(game.audit_completed_spells),
            "current_tenure_weeks_median_censored": median(remaining_spells),
            "players_with_3plus_clubs_cumulative": sum(
                len(v) >= 3 for v in game.audit_clubs_visited.values()),
            "players_with_5plus_clubs_cumulative": sum(
                len(v) >= 5 for v in game.audit_clubs_visited.values()),
            "retirements_total": state["retirements_total"],
            "alerts": "|".join(sorted(alerts)), "warnings": "|".join(sorted(warnings)),
        }
        rows.append({"metrics": fields, "money_by_item": money,
                     "tier_money": finance["tier_money"],
                     "removed_by_tier": finance["removed_by_tier"],
                     "market_decisions": dict(sorted(kinds.items())),
                     "rollover_messages": finance["rollover_messages"]})
    # End-of-observation spans are right censored, not completed spells.
    return {"schema": 1, "seed": seed, "seasons": seasons, "clubs": clubs,
            "rows": rows, "completed_roster_spell_count": len(game.audit_completed_spells),
            "completed_roster_spell_weeks_median": median(game.audit_completed_spells),
            "player_club_counts": dict(Counter(
                len(v) for v in game.audit_clubs_visited.values()))}


def write_csv(path: Path, data: list[dict]):
    if not data:
        return
    fields = list(data[0])
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fields)
        w.writeheader()
        w.writerows(data)


def summarize(paths, output: Path, expected_worlds: int | None = None):
    datasets = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(paths)]
    seeds = [v["seed"] for v in datasets]
    if len(set(seeds)) != len(seeds):
        raise ValueError("Duplicate seed in merged artifacts")
    if expected_worlds is not None and len(seeds) != expected_worlds:
        raise ValueError(f"Expected {expected_worlds} worlds, found {len(seeds)}")
    shapes = {(v["seasons"], v["clubs"], len(v["rows"])) for v in datasets}
    if len(shapes) != 1:
        raise ValueError(f"Inconsistent experiment dimensions: {shapes}")
    rows = [r["metrics"] for v in datasets for r in v["rows"]]
    write_csv(output / "ecosystem_seasons.csv", rows)
    seasons = sorted({r["season"] for r in rows})
    means = []
    for season in seasons:
        subset = [r for r in rows if r["season"] == season]
        numeric = [k for k, v in subset[0].items() if
                   isinstance(v, (int, float)) and k not in ("seed", "season")]
        means.append({"season": season, "worlds": len(subset), **{
            k: mean([r[k] for r in subset]) for k in numeric}})
    write_csv(output / "ecosystem_trends.csv", means)
    by_item = defaultdict(lambda: defaultdict(float))
    by_tier = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for v in datasets:
        for i, row in enumerate(v["rows"], 1):
            for k, amount in row["money_by_item"].items():
                by_item[i][k] += amount
            for tier, money in row["tier_money"].items():
                for k, amount in money.items():
                    by_tier[i][tier][k] += amount
    if any(r["finance_reconciliation_failures"] for r in rows):
        integrity = "FAIL"
    elif any(r["alerts"] for r in rows):
        integrity = "ALERT"
    else:
        integrity = "NO_RECORDED_ALERTS"
    report = {
        "schema": 1, "worlds": len(datasets), "seasons_per_world": len(seasons),
        "completed_world_seasons": len(rows), "seed_min": min(seeds) if seeds else None,
        "seed_max": max(seeds) if seeds else None,
        "integrity": integrity,
        "season_averages": means,
        "money_by_item_mean_by_season": {
            str(s): {k: round(v / len(datasets), 2) for k, v in sorted(x.items())}
            for s, x in sorted(by_item.items())},
        "tier_money_mean_by_season": {
            str(s): {tier: {k: round(v / len(datasets), 2) for k, v in sorted(x.items())}
                     for tier, x in sorted(tiers.items())}
            for s, tiers in sorted(by_tier.items())},
        "limitations": [
            "Synthetic CS Manager simulations, not real esports calibration.",
            "Market events are counted by the game's contract journal; direct roster moves are independent state observations.",
            "Team IDs track roster spells through rebrands, but disappearing teams include world replacement and superteam events.",
            "Completed tenure medians exclude still-active spells; current tenure is right-censored.",
            "Money item totals cover clubs present just before season rollover; transfers between clubs appear on both ledgers.",
            "No causal attribution: rising fan counts and cash may correlate without fan churn being the sole explanation.",
            "The human-managed club follows existing assistant decisions; no interventions added.",
        ],
    }
    atomic_json(output / "ecosystem_summary.json", report)
    print(json.dumps({"worlds": report["worlds"], "seasons": len(rows),
                      "integrity": integrity, "last_season": means[-1] if means else None},
                     ensure_ascii=False, indent=2), flush=True)
    return report


def positive(s):
    n = int(s)
    if n < 1:
        raise argparse.ArgumentTypeError("positive integer required")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worlds", type=positive, default=100)
    ap.add_argument("--seasons", type=positive, default=10)
    ap.add_argument("--clubs", type=positive, default=120)
    ap.add_argument("--seed-start", type=positive, default=1)
    ap.add_argument("--director", choices=("cassandra", "phoebe", "randy"),
                    default="cassandra")
    ap.add_argument("--output", type=Path, default=Path("ecosystem-out"))
    ap.add_argument("--aggregate-only", action="store_true")
    args = ap.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.aggregate_only:
        for seed in range(args.seed_start, args.seed_start + args.worlds):
            path = args.output / f"world-{seed:06d}.json"
            if path.exists():
                world = json.loads(path.read_text(encoding="utf-8"))
                if (world.get("seed"), world.get("seasons"), world.get("clubs")) != (
                        seed, args.seasons, args.clubs):
                    raise SystemExit(f"Incompatible checkpoint: {path}")
            else:
                world = run_world(seed, args.seasons, args.clubs, args.director)
                atomic_json(path, world)
            print(f"seed {seed}: {args.seasons} seasons complete", flush=True)
    paths = list(args.output.glob("world-*.json"))
    summarize(paths, args.output, expected_worlds=args.worlds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
