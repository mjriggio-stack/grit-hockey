"""build_eyp_career.py — multi-season EYP pivot AND career aggregate.

For every forward who qualified in any of the 10 RS seasons (2015-16 → 2025-26,
excluding 2020-21 COVID), produce TWO output files:

Output 1: data/eyp_career_v31.csv (pivot / quadrant history)
  - Per-season quadrant (quad_2016, quad_2017, ..., quad_2026)
      Values: 'BLUE' | 'GREEN' | 'RED' | 'GRAY' | None
      None = didn't qualify that season (GP < 40, wasn't a forward, or missing
      from grit_scores ∩ skater_scoring intersection).
  - Quadrant tallies (blue_count, green_count, red_count, gray_count)
  - blue_streak: longest run of consecutive BLUE seasons (gap-aware — the
    2021 COVID year always breaks streaks since we don't know what
    happened that season)
  - blue_streak_current: length of an ongoing BLUE run ending in the player's
    most recent qualifying season. 0 if the most recent season wasn't BLUE.
  - ever_btog: True if the player ever went BLUE in season N then GREEN in
    season N+1 (consecutive seasons only — does NOT count transitions across
    the COVID gap)
  - most_recent_quad: quadrant in the player's most recent qualifying season
  - most_recent_season: the season tag (e.g. "2026") of that most recent qual

Output 2: data/eyp_career_aggregate_v31.csv (mean stats for scatter viz)
  - mean_grit_z   — equal-weight mean of grit_z_blend across qualifying seasons
  - mean_pts      — equal-weight mean of season points
  - mean_pts_gap  — equal-weight mean of season points gap (bar minus pts)
  - mean_age_at_qualification — mean age across seasons player qualified
  - n_qualifying_seasons — trust-this-mean signal (a +0.8 mean from 8 seasons
    is very different from +0.8 from 1)

Reads from SQL: grit_scores, skater_scoring, players. Reproduces the same
forward + GP ≥ 40 filter as build_eyp.py per season, then pivots & aggregates.

Usage:
    python build_eyp_career.py
    python build_eyp_career.py --data-dir /custom/path
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from grit_version import GRIT_VERSION
from eyp_common import (
    GP_FLOOR, FORWARD_POSITIONS, GRIT_CUTOFF,
    FULL_SEASON_THRESHOLD, SHORTENED_SEASON_THRESHOLDS,
    season_points_threshold, assign_quadrant,
)


SQL_SERVER   = "localhost"
SQL_DATABASE = "GRIT"
SQL_DRIVER   = "ODBC Driver 17 for SQL Server"

DEFAULT_DATA_DIR = Path(
    r"C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\data"
)

# Full RS season range. 2021 (2020-21 COVID) is intentionally absent.
# When iterating per-season we only hit these; for the wide pivot we include
# quad_2021 as a column that's always None (transparency about the gap).
ALL_RS_SEASONS    = [2016, 2017, 2018, 2019, 2020,        2022, 2023, 2024, 2025, 2026]
COVID_SEASON      = 2021
PIVOT_SEASON_SPAN = list(range(2016, 2027))  # 2016..2026 inclusive, 11 columns

GP_FLOOR          = 40                                # mirrors eyp_common
FORWARD_POSITIONS = ["C", "L", "R"]                   # mirrors eyp_common
GRIT_CUTOFF       = 0.0                               # mirrors eyp_common
#
# The classification definitions (points bar + assign_quadrant) come from
# eyp_common, imported above — the single source of truth shared with
# build_eyp.py. The three lines above are restated for readability only.


def get_engine():
    from sqlalchemy import create_engine
    conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/{SQL_DATABASE}"
        f"?driver={SQL_DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
    )
    return create_engine(conn_str)


def build_one_season(engine, season_tag: str) -> pd.DataFrame:
    """Replicate build_eyp.py's per-season classification.

    Returns df with columns: player_id, season (int), quadrant, grit_z_blend,
    points, pts_gap. The extra metric columns are needed for the career
    aggregate (mean_grit_z, mean_pts, mean_pts_gap).

    Empty df if no data for the season.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        grit = pd.read_sql(
            text("""
                SELECT player_id, position, grit_z_blend
                FROM grit_scores
                WHERE season = :s AND is_playoffs = 0 AND strength = 'all'
            """),
            conn, params={"s": season_tag},
        )
        scoring = pd.read_sql(
            text("""
                SELECT player_id, position, games_played, points
                FROM skater_scoring
                WHERE season = :s
            """),
            conn, params={"s": season_tag},
        )

    empty_cols = ["player_id", "season", "quadrant",
                  "grit_z_blend", "points", "pts_gap"]
    if grit.empty or scoring.empty:
        return pd.DataFrame(columns=empty_cols)

    grit_fwd = grit[grit["position"].isin(FORWARD_POSITIONS)].copy()
    scoring_fwd = scoring[
        scoring["position"].isin(FORWARD_POSITIONS) &
        (scoring["games_played"] >= GP_FLOOR)
    ].copy()

    df = grit_fwd.merge(
        scoring_fwd[["player_id", "points"]],
        on="player_id", how="inner", suffixes=("", "_s"),
    )
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    pts_threshold = season_points_threshold(season_tag)
    df["pts_gap"] = pts_threshold - df["points"]    # positive = below the bar (BLUE side)
    df["quadrant"] = df.apply(
        lambda r: assign_quadrant(r["grit_z_blend"], r["points"], pts_threshold),
        axis=1,
    )
    df["season"] = int(season_tag)

    return df[["player_id", "season", "quadrant",
               "grit_z_blend", "points", "pts_gap"]]


def load_player_identity(engine, player_ids: list[int]) -> pd.DataFrame:
    """Pull name, position, birth_year for the player_ids we have history for.

    Uses the `players` table built by scrape_players.py. Missing rows get
    NaN — recorded for transparency, not used in computations.
    """
    if not player_ids:
        return pd.DataFrame(columns=["player_id", "name", "position", "birth_year"])

    from sqlalchemy import text
    # IN clause needs chunking under SQL Server's 2100-param limit
    out = []
    CHUNK = 1000
    with engine.connect() as conn:
        for i in range(0, len(player_ids), CHUNK):
            batch = player_ids[i:i + CHUNK]
            placeholders = ",".join(f":p{j}" for j in range(len(batch)))
            params = {f"p{j}": int(pid) for j, pid in enumerate(batch)}
            chunk_df = pd.read_sql(
                text(
                    f"SELECT player_id, name, position, birth_year "
                    f"FROM players WHERE player_id IN ({placeholders})"
                ),
                conn, params=params,
            )
            out.append(chunk_df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def compute_blue_streak_longest(quads: list, seasons: list) -> int:
    """Longest consecutive-season BLUE run.

    quads and seasons are parallel lists of (quadrant, season) sorted by season.
    Gaps in season sequence (anything > 1 year apart) break a streak — this
    handles the 2020 → 2022 COVID gap correctly.

    Returns 0 if no BLUE seasons exist.
    """
    if not quads:
        return 0

    longest = 0
    current = 0
    last_season = None
    for q, s in zip(quads, seasons):
        is_consecutive = (last_season is not None and s == last_season + 1)
        if q == "BLUE":
            current = current + 1 if is_consecutive else 1
            longest = max(longest, current)
        else:
            current = 0
        last_season = s
    return longest


def compute_blue_streak_current(quads: list, seasons: list) -> int:
    """Length of an ONGOING BLUE run ending at the most recent qualifying season.

    Same gap-awareness as longest. Returns 0 if the most recent season isn't
    BLUE.
    """
    if not quads:
        return 0
    # Walk backwards from the end while quad == 'BLUE' AND seasons are consecutive
    streak = 0
    expected_season = seasons[-1]
    for q, s in zip(reversed(quads), reversed(seasons)):
        if s != expected_season:
            break  # gap encountered, ongoing streak ends
        if q != "BLUE":
            break
        streak += 1
        expected_season = s - 1
    return streak


def compute_ever_btog(quads: list, seasons: list) -> bool:
    """True if the player ever went BLUE in season N then GREEN in season N+1.

    Only counts CONSECUTIVE-season transitions. A player BLUE in 2020 and
    GREEN in 2022 does NOT count (the COVID gap interrupts the inference).
    """
    if len(quads) < 2:
        return False
    for i in range(len(quads) - 1):
        if (seasons[i + 1] == seasons[i] + 1
                and quads[i] == "BLUE"
                and quads[i + 1] == "GREEN"):
            return True
    return False


def build_career_aggregate(long_df: pd.DataFrame, identity: pd.DataFrame,
                            season_end_year_col: str = "season") -> pd.DataFrame:
    """Compute per-player career aggregate metrics.

    Equal-weight mean across qualifying seasons:
      mean_grit_z   — mean of grit_z_blend
      mean_pts      — mean of season points (raw, NOT GP-normalized)
      mean_pts_gap  — mean of pts_gap (positive = below the bar)
      mean_age_at_qualification — mean age in seasons where they qualified

    Includes n_qualifying_seasons as the trust-this-mean signal — a +0.8 mean
    from 8 seasons reads very differently than +0.8 from 1.

    long_df must have: player_id, season, grit_z_blend, points, pts_gap
    identity must have: player_id, birth_year (used for per-season age)
    """
    # Join birth_year onto long_df so we can compute per-season age
    df = long_df.merge(
        identity[["player_id", "birth_year"]],
        on="player_id", how="left",
    )
    df["age_in_season"] = df[season_end_year_col] - df["birth_year"]

    grouped = df.groupby("player_id")
    agg = grouped.agg(
        n_qualifying_seasons=("season", "count"),
        mean_grit_z=("grit_z_blend", "mean"),
        mean_pts=("points", "mean"),
        mean_pts_gap=("pts_gap", "mean"),
        mean_age_at_qualification=("age_in_season", "mean"),
    ).reset_index()

    return agg


def build_career_pivot(engine):
    """Main driver: build the wide multi-season EYP pivot AND the aggregate.

    Returns: (pivot_df, aggregate_df). Both are keyed on player_id.
    """

    # 1. Run per-season classification for each non-COVID RS season.
    long_rows = []
    for season in ALL_RS_SEASONS:
        df = build_one_season(engine, str(season))
        if df.empty:
            print(f"  [{season}] no data, skipped")
            continue
        long_rows.append(df)
        print(f"  [{season}] {len(df)} qualifying forwards")

    if not long_rows:
        print("No data loaded across any season. Exiting.")
        return pd.DataFrame(), pd.DataFrame()

    long_df = pd.concat(long_rows, ignore_index=True)
    print(f"\nLong table: {len(long_df)} player-season rows across "
          f"{len(long_rows)} seasons")

    # 2. Wide pivot: one column per season, value = quadrant. Players who
    # didn't qualify in a given season get NaN/None for that column.
    wide = long_df.pivot(index="player_id", columns="season", values="quadrant")
    # Ensure all PIVOT_SEASON_SPAN years are present as columns (including the
    # COVID year, which will be all None).
    for s in PIVOT_SEASON_SPAN:
        if s not in wide.columns:
            wide[s] = None
    # Order columns by season and rename to quad_YYYY
    wide = wide.reindex(columns=sorted(PIVOT_SEASON_SPAN))
    wide.columns = [f"quad_{s}" for s in wide.columns]
    wide = wide.reset_index()

    # 3. Per-player computed columns: streaks, B→G, counts, most recent.
    # Build a per-player long view to make these computations easy.
    long_sorted = long_df.sort_values(["player_id", "season"]).copy()
    grouped = long_sorted.groupby("player_id")

    per_player = []
    for pid, group in grouped:
        quads = group["quadrant"].tolist()
        seasons = group["season"].tolist()
        per_player.append({
            "player_id":            pid,
            "n_qualifying_seasons": len(group),
            "blue_count":           sum(1 for q in quads if q == "BLUE"),
            "green_count":          sum(1 for q in quads if q == "GREEN"),
            "red_count":            sum(1 for q in quads if q == "RED"),
            "gray_count":           sum(1 for q in quads if q == "GRAY"),
            "blue_streak":          compute_blue_streak_longest(quads, seasons),
            "blue_streak_current":  compute_blue_streak_current(quads, seasons),
            "ever_btog":            compute_ever_btog(quads, seasons),
            "most_recent_quad":     quads[-1],
            "most_recent_season":   seasons[-1],
        })
    per_player_df = pd.DataFrame(per_player)

    # 4. Identity join: pull name, position, birth_year from players table.
    pids = wide["player_id"].tolist()
    identity = load_player_identity(engine, pids)

    # 5. Career aggregate (mean grit_z, mean pts, mean pts_gap, mean age).
    aggregate = build_career_aggregate(long_df, identity)
    # Order aggregate columns and join identity for readability
    aggregate = aggregate.merge(identity, on="player_id", how="left")
    agg_front = [
        "player_id", "name", "position", "birth_year",
        "n_qualifying_seasons",
        "mean_grit_z", "mean_pts", "mean_pts_gap", "mean_age_at_qualification",
    ]
    aggregate = aggregate[[c for c in agg_front if c in aggregate.columns]]
    # Sort: highest mean_grit_z first (interesting cases at top)
    aggregate = aggregate.sort_values(
        ["mean_grit_z", "n_qualifying_seasons"],
        ascending=[False, False],
    ).reset_index(drop=True)

    # 6. Merge pivot pieces.
    out = wide.merge(per_player_df, on="player_id", how="left")
    out = out.merge(identity, on="player_id", how="left")

    # Column ordering for readability: identity first, then summary stats,
    # then per-season columns in chronological order at the right.
    quad_cols = [f"quad_{s}" for s in sorted(PIVOT_SEASON_SPAN)]
    front_cols = [
        "player_id", "name", "position", "birth_year",
        "n_qualifying_seasons",
        "blue_count", "green_count", "red_count", "gray_count",
        "blue_streak", "blue_streak_current", "ever_btog",
        "most_recent_quad", "most_recent_season",
    ]
    out = out[[c for c in front_cols if c in out.columns] + quad_cols]

    # 7. Sort: most-recent BLUE players first, then by blue_streak desc, then
    # by name. Puts the EYP-watchlist-relevant rows at the top of the CSV.
    out["_sort_recent_blue"] = (out["most_recent_quad"] == "BLUE").astype(int)
    out = out.sort_values(
        ["_sort_recent_blue", "blue_streak", "blue_streak_current", "name"],
        ascending=[False, False, False, True],
    ).drop(columns=["_sort_recent_blue"]).reset_index(drop=True)

    return out, aggregate


def print_summary(df: pd.DataFrame, agg: pd.DataFrame) -> None:
    """Quick console summary of the career pivot AND career aggregate."""
    n = len(df)
    print(f"\n{'=' * 76}")
    print(f"  EYP career pivot · {GRIT_VERSION}")
    print(f"  {n} forwards qualified in at least one season (2016-26, ex-2021)")
    print(f"{'=' * 76}")

    # How many qualified in each number of seasons?
    seasons_count = df["n_qualifying_seasons"].value_counts().sort_index()
    print("\n  Qualifying seasons distribution:")
    for k, v in seasons_count.items():
        print(f"    {k:>2} season(s): {v:>4} players")

    # B→G transition headliners
    btog = df[df["ever_btog"]].sort_values(
        ["blue_streak", "blue_count"], ascending=[False, False]
    )
    print(f"\n  ever_btog (BLUE→GREEN transitions, consecutive seasons): "
          f"{len(btog)} players")
    if len(btog) > 0:
        print("  Top 15 (by blue_streak desc, then blue_count desc):")
        for _, r in btog.head(15).iterrows():
            print(f"    {r['name']:<24} "
                  f"blue_streak={r['blue_streak']:>1} "
                  f"current={r['blue_streak_current']:>1} "
                  f"counts: B={r['blue_count']} G={r['green_count']} "
                  f"R={r['red_count']} Gr={r['gray_count']}")

    # Active BLUE streaks
    active_blue = df[df["blue_streak_current"] > 0].sort_values(
        "blue_streak_current", ascending=False,
    )
    print(f"\n  Players with an active BLUE streak (most recent quad = BLUE): "
          f"{len(active_blue)}")
    if len(active_blue) > 0:
        print("  Top 15 by blue_streak_current:")
        for _, r in active_blue.head(15).iterrows():
            print(f"    {r['name']:<24} "
                  f"current={r['blue_streak_current']:>1} "
                  f"longest={r['blue_streak']:>1} "
                  f"ever_btog={r['ever_btog']}")

    # Career aggregate: top mean_grit_z with reasonable sample size
    print(f"\n{'=' * 76}")
    print(f"  EYP career aggregate (equal-weight mean across qualifying seasons)")
    print(f"{'=' * 76}")
    qualified = agg[agg["n_qualifying_seasons"] >= 3]
    print(f"\n  Top 15 by mean_grit_z (filtered to n_qualifying_seasons >= 3):")
    for _, r in qualified.head(15).iterrows():
        age = r["mean_age_at_qualification"]
        print(f"    {r['name']:<24} "
              f"n={int(r['n_qualifying_seasons']):>2} "
              f"mean_gz={r['mean_grit_z']:+.2f}  "
              f"mean_pts={r['mean_pts']:>5.1f}  "
              f"mean_gap={r['mean_pts_gap']:+.1f}  "
              f"mean_age={age:.1f}")
    print()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                    help=f"Where to write output CSVs (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--no-summary", action="store_true",
                    help="Skip the console summary at the end")
    args = ap.parse_args()

    engine = get_engine()
    print(f"Data dir: {args.data_dir}")
    print(f"Seasons:  {ALL_RS_SEASONS} (COVID {COVID_SEASON} excluded)")
    print(f"GP floor: {GP_FLOOR}, GRIT cutoff: {GRIT_CUTOFF}\n")

    df, agg = build_career_pivot(engine)
    if df.empty:
        print("No data — exiting.", file=sys.stderr)
        sys.exit(1)

    args.data_dir.mkdir(parents=True, exist_ok=True)
    pivot_path = args.data_dir / "eyp_career_v31.csv"
    agg_path = args.data_dir / "eyp_career_aggregate_v31.csv"
    df.to_csv(pivot_path, index=False)
    agg.to_csv(agg_path, index=False)
    print(f"\nWrote {pivot_path}  ({len(df)} rows × {len(df.columns)} cols)")
    print(f"Wrote {agg_path}    ({len(agg)} rows × {len(agg.columns)} cols)")

    if not args.no_summary:
        print_summary(df, agg)


if __name__ == "__main__":
    main()
