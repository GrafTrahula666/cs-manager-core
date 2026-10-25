"""Leagues: the world's clubs split into Тир 1, Тир 2, Тир 3 and the rest.

The league is fixed for a season and decides invites (see worldgen.calendar):
    Тир 1      16 clubs: direct invites to the Masters, the Major and the World Final
    Тир 2      16 clubs: Pro Series, HACEIT leagues, the HACEIT Major qualifier (2 places at the Major)
    Тир 3      32 clubs: HACEIT leagues and open cups
    Остальные  the rest: HACEIT leagues and open cups

Every tournament gives season points (the same formula as the ranking, without decay). At the
end of the season the bottom of each league goes down and the top of the one below goes up.
The official ranking (club.rank, VRS-like) still seeds brackets and drives sponsor KPIs.
"""
from __future__ import annotations

from .economy import Club

NAMES = {1: "Тир 1", 2: "Тир 2", 3: "Тир 3", 4: "Остальные"}
SIZES = {1: 16, 2: 16, 3: 32}       # division 4 takes the rest
SWAPS = {1: 4, 2: 4, 3: 8}          # clubs that swap between division k and k + 1 each season


def name(division: int) -> str:
    return NAMES.get(division, NAMES[4])


def _sizes(n: int) -> list[int]:
    out, left = [], n
    for k in (1, 2, 3):
        out.append(min(SIZES[k], left))
        left -= out[-1]
    return out + [left]


def _fill(order: list[Club]) -> None:
    i = 0
    for k, size in enumerate(_sizes(len(order)), 1):
        for c in order[i:i + size]:
            c.division = k
        i += size


def assign(clubs: list[Club]) -> None:
    """A new world: leagues by ranking."""
    _fill(sorted(clubs, key=lambda c: c.rank))


def standings(clubs: list[Club], division: int) -> list[Club]:
    """The league table: season points, then ranking."""
    return sorted((c for c in clubs if c.division == division), key=lambda c: (-c.season_points, c.rank))


def regional_candidates(clubs: list[Club], per_region: int = 2) -> list[Club]:
    """Two highest season scorers from each region of division 3.

    Candidates compete internationally for the four promotion slots. Small generated worlds
    may have fewer than two clubs in a particular region, so vacant berths stay vacant.
    """
    regions = sorted({c.region for c in clubs})
    result: list[Club] = []
    for region in regions:
        pool = sorted((c for c in clubs if c.division == 3 and c.region == region),
                      key=lambda c: (-c.season_points, c.rank))
        result.extend(pool[:per_region])
    return sorted(result, key=lambda c: (-c.season_points, c.rank))


def season_end(clubs: list[Club], promoted_from_qualifier: list[str] | None = None) -> list[str]:
    """Promotion and relegation by the season tables, then a fresh table for everyone."""
    tables = {k: standings(clubs, k) for k in (1, 2, 3, 4)}
    moves: list[tuple[Club, int]] = []
    lines = []
    for k in (1, 2, 3):
        n = min(SWAPS[k], len(tables[k]) // 2, len(tables[k + 1]))
        if n <= 0:
            continue
        down, up = tables[k][-n:], tables[k + 1][:n]
        if k == 2 and promoted_from_qualifier is not None:
            names = set(promoted_from_qualifier)
            winners = [c for c in tables[3] if c.name in names]
            # If an unusually small seed has fewer qualifiers, retain open promotion slots.
            up = winners[:n] + [c for c in tables[3] if c.name not in names][:max(0, n-len(winners))]
        moves += [(c, k + 1) for c in down] + [(c, k) for c in up]
        lines.append(f"{name(k)}: вылетели {', '.join(c.name for c in down)}; "
                     f"поднялись: {', '.join(c.name for c in up)}")
    for c, k in moves:
        c.division = k
    for c in clubs:
        c.season_points = 0.0
        c.flags = {f for f in c.flags if not f.startswith("qual:")}
    return lines


def rebalance(clubs: list[Club]) -> None:
    """Keep the league sizes after clubs close or appear: a new club starts at the bottom (a
    superteam buys a Тир 1 place), the best of the league below fills a free place."""
    def key(c: Club):
        top = any(f.startswith("superteam_until:") for f in c.flags)
        return (1 if top else c.division, c.rank)
    _fill(sorted(clubs, key=key))
