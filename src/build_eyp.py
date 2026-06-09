"""build_eyp.py — generate EYP (Earning Your Points) quadrant analysis.

Reads:
  - grit_scores SQL table (or grit_per_60_v3_{season}.csv fallback)
  - skater_scoring SQL table
  - players SQL table (for birth_year → age — used by headline filter)

Joins by player_id within season, classifies forwards into quadrants:

  RED   (lo grit, hi pts) | GREEN  (hi grit, hi pts)  ← at/above the points bar
  ----------------------- + -------------------------
  GRAY  (lo grit, lo pts) | BLUE   (hi grit, lo pts)  ← below the points bar
                          ^ grit_z >= 0

Points axis is an ABSOLUTE bar, not the per-season median. The bar is 41
points (0.5 pts/game over 82) for full seasons, pro-rated for shortened
seasons (2019-20, tag 2020, ran ~71 games → 0.5 * 71 = 35.5). Using an
absolute bar avoids the median split's mechanical ~50/50 symmetry.

Outputs (v3.1 naming):
  data/{season}/eyp_v31_{season}.csv          — all qualifying forwards
  data/eyp_watchlist_v31_{season}.csv         — BLUE forwards only
  data/eyp_headline_v31_{season}.csv          — narrow watchlist:
                                                age ≤ MAX_AGE, pts_gap ≤ MAX_GAP
                                                (only when --headline-filter)

Age math: age = int(season_tag) - birth_year. Player born 2000 in season 2026
is 26. This is the end-of-season integer age agreed for v3.1 EYP. Players
missing from the players table (birth_year IS NULL) get age = NaN and are
EXCLUDED from the headline filter, but remain in the watchlist.

Usage:
    python build_eyp.py --season 2026
    python build_eyp.py --season 2025 --season 2026
    python build_eyp.py --all-seasons
    python build_eyp.py --season 2026 --headline-filter
    python build_eyp.py --season 2026 --headline-filter \\
        --headline-max-age 24 --headline-max-pts-gap 5
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

ALL_RS_SEASONS = [2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025, 2026]

GP_FLOOR = 40                             # minimum games played for EYP eligibility
FORWARD_POSITIONS = ["C", "L", "R"]       # EYP scope
GRIT_CUTOFF = 0.0                         # grit_z_blend >= 0 → "high grit"
#
# NOTE: the four lines above are re-stated for readability but the values that
# MATTER come from eyp_common (imported above) — that's the single source of
# truth. The points bar (FULL_SEASON_THRESHOLD / SHORTENED_SEASON_THRESHOLDS /
# season_points_threshold) and assign_quadrant also live in eyp_common.

# Headline (narrow watchlist) defaults. Override on the CLI.
# pts_gap is now distance BELOW the points bar (bar - points), so a small
# positive gap means BLUE-but-close-to-the-bar — the proximity signal that
# empirically predicts crossing the bar. The age cap targets young
# deployment-limited forwards. NOTE: the gap-cutoff names that were tuned
# under the old median split (Greig/Sourdif/Minten at gap=1, etc.) were
# median-era and need re-validation against the absolute bar before being
# quoted again.
HEADLINE_MAX_AGE     = 27                 # age <= this (revised from 25: sustain rate
                                          # decays past 27; sweet spot is age <= 27 with
                                          # a prior BLUE streak)
HEADLINE_MAX_PTS_GAP = 5.0                # within this many points of the bar


def get_engine():
    from sqlalchemy import create_engine
    conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/{SQL_DATABASE}"
        f"?driver={SQL_DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
    )
    return create_engine(conn_str)


def load_grit(engine, season_tag: str) -> pd.DataFrame:
    """Load GRIT data for one RS season from SQL grit_scores table.

    grit_scores uses (season, is_playoffs) as the season key, not a combined
    string like skater_scoring's '2026_playoffs'. We filter is_playoffs=0 here
    since EYP is RS-only.
    """
    from sqlalchemy import text
    q = text("""
        SELECT player_id, name, position, team, games_played,
               grit_z_blend, raw_grit_per_60, grit_per_game
        FROM grit_scores
        WHERE season = :s AND is_playoffs = 0 AND strength = 'all'
    """)
    with engine.connect() as conn:
        df = pd.read_sql(q, conn, params={"s": season_tag})
    return df


def load_scoring(engine, season_tag: str) -> pd.DataFrame:
    """Load scoring data for one RS season from SQL skater_scoring table."""
    from sqlalchemy import text
    q = text("""
        SELECT player_id, name, position, team, games_played,
               goals, assists, points
        FROM skater_scoring
        WHERE season = :s
    """)
    with engine.connect() as conn:
        df = pd.read_sql(q, conn, params={"s": season_tag})
    return df


def load_player_ages(engine, season_tag: str) -> pd.DataFrame:
    """Load (player_id, birth_year, age) for all players.

    age = int(season_tag) - birth_year. This is the player's age at the end
    of the season, integer-rounded. Players with birth_year IS NULL get
    age = NaN; they're left in the watchlist but get excluded from the
    headline filter.
    """
    from sqlalchemy import text
    q = text("SELECT player_id, birth_year FROM players")
    with engine.connect() as conn:
        df = pd.read_sql(q, conn)

    season_end_year = int(season_tag)
    # Use Float so NaN propagates cleanly for missing birth_years
    df["age"] = season_end_year - df["birth_year"]
    return df


def build_season_eyp(engine, season_tag: str) -> pd.DataFrame:
    """For one season, produce the per-forward EYP dataframe with quadrant column."""
    grit = load_grit(engine, season_tag)
    scoring = load_scoring(engine, season_tag)
    ages = load_player_ages(engine, season_tag)

    if grit.empty or scoring.empty:
        print(f"  [{season_tag}] no data — skipping")
        return pd.DataFrame()

    # Filter to forwards only and apply GP floor.
    # Use scoring's gp (more authoritative — reflects actual API gp).
    grit_fwd = grit[grit["position"].isin(FORWARD_POSITIONS)].copy()
    scoring_fwd = scoring[
        scoring["position"].isin(FORWARD_POSITIONS) &
        (scoring["games_played"] >= GP_FLOOR)
    ].copy()

    # Inner join: must appear in both datasets (qualifier in GRIT pool AND meets GP floor)
    df = grit_fwd.merge(
        scoring_fwd[["player_id", "goals", "assists", "points"]],
        on="player_id",
        how="inner",
        suffixes=("", "_score"),
    )

    if df.empty:
        print(f"  [{season_tag}] no overlap between GRIT and scoring after filters")
        return pd.DataFrame()

    # Left-join age info. Players missing from players table get age=NaN.
    df = df.merge(
        ages[["player_id", "birth_year", "age"]],
        on="player_id",
        how="left",
    )

    # Diagnostic: how many forwards have missing age?
    n_missing_age = df["age"].isna().sum()
    if n_missing_age > 0:
        print(f"  [{season_tag}] {n_missing_age} forwards have missing birth_year — "
              f"excluded from headline filter only")

    # Absolute points bar for this season (41, or pro-rated for short seasons)
    pts_threshold = season_points_threshold(season_tag)

    df["pts_threshold"] = pts_threshold
    df["pts_gap"] = pts_threshold - df["points"]    # positive = below the bar (BLUE side)
    df["quadrant"] = df.apply(
        lambda r: assign_quadrant(r["grit_z_blend"], r["points"], pts_threshold),
        axis=1,
    )
    df["season"] = season_tag

    return df.sort_values("grit_z_blend", ascending=False).reset_index(drop=True)


def write_per_season(df: pd.DataFrame, season_tag: str, data_dir: Path) -> Path:
    """Per-season output: all qualifying forwards with quadrant + age."""
    out_dir = data_dir / season_tag
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eyp_v31_{season_tag}.csv"
    cols_order = [
        "season", "player_id", "name", "position", "team",
        "games_played", "grit_z_blend", "raw_grit_per_60",
        "goals", "assists", "points",
        "pts_threshold", "pts_gap", "quadrant",
        "birth_year", "age",
    ]
    df[[c for c in cols_order if c in df.columns]].to_csv(out_path, index=False)
    print(f"  wrote {out_path}  ({len(df)} forwards)")
    return out_path


def write_watchlist(df: pd.DataFrame, season_tag: str, data_dir: Path) -> Path:
    """BLUE-quadrant forwards only, sorted by grit_z descending. All ages."""
    blue = df[df["quadrant"] == "BLUE"].sort_values("grit_z_blend", ascending=False)
    out_path = data_dir / f"eyp_watchlist_v31_{season_tag}.csv"
    cols = [
        "season", "player_id", "name", "position", "team", "games_played",
        "grit_z_blend", "points", "goals", "assists",
        "pts_threshold", "pts_gap",
        "birth_year", "age",
    ]
    blue[[c for c in cols if c in blue.columns]].to_csv(out_path, index=False)
    print(f"  wrote {out_path}  ({len(blue)} BLUE forwards)")
    return out_path


def write_headline(df: pd.DataFrame, season_tag: str, data_dir: Path,
                   max_age: float, max_pts_gap: float) -> Path:
    """Narrow watchlist for headline reporting.

    Filter: BLUE quadrant AND age ≤ max_age AND pts_gap ≤ max_pts_gap.
    Players with missing age (no birth_year) are EXCLUDED — the age cap
    requires us to know the age, and we don't infer.

    pts_gap is 'bar - player_pts' so a small positive gap
    means the player is BLUE-but-close-to-the-bar, the EYP archetype.
    """
    headline = df[
        (df["quadrant"] == "BLUE")
        & (df["age"].notna())
        & (df["age"] <= max_age)
        & (df["pts_gap"] <= max_pts_gap)
    ].sort_values("grit_z_blend", ascending=False).copy()

    out_path = data_dir / f"eyp_headline_v31_{season_tag}.csv"
    cols = [
        "season", "player_id", "name", "position", "team", "games_played",
        "grit_z_blend", "points", "goals", "assists",
        "pts_threshold", "pts_gap",
        "birth_year", "age",
    ]
    headline[[c for c in cols if c in headline.columns]].to_csv(out_path, index=False)
    print(f"  wrote {out_path}  ({len(headline)} headline candidates, "
          f"age ≤ {max_age:g}, pts_gap ≤ {max_pts_gap:g})")
    return out_path


def quadrant_grid(df: pd.DataFrame, season_tag: str,
                  show_headline: bool = False,
                  max_age: float = HEADLINE_MAX_AGE,
                  max_pts_gap: float = HEADLINE_MAX_PTS_GAP) -> str:
    """Return a text grid showing quadrant counts and exemplar players.

    When show_headline=True, appends a HEADLINE section listing the narrow
    filter results (age + pts_gap cutoffs applied to BLUE).
    """
    if df.empty:
        return f"[{season_tag}] no data"

    pts_threshold = df["pts_threshold"].iloc[0]
    n = len(df)

    counts = df["quadrant"].value_counts().to_dict()
    n_red   = counts.get("RED", 0)
    n_green = counts.get("GREEN", 0)
    n_gray  = counts.get("GRAY", 0)
    n_blue  = counts.get("BLUE", 0)

    # Top 5 by grit_z within each quadrant for exemplars
    def top_in(q, n=5):
        sub = df[df["quadrant"] == q].sort_values("grit_z_blend", ascending=False).head(n)
        return [f"{r['name']} ({r['team']}, gz={r['grit_z_blend']:.2f}, pts={r['points']})" for _, r in sub.iterrows()]

    lines = []
    lines.append(f"\n{'=' * 76}")
    lines.append(f"  EYP {GRIT_VERSION} · {season_tag}  (forwards only, GP ≥ {GP_FLOOR})")
    lines.append(f"  N = {n} forwards · pts bar = {pts_threshold:.1f}")
    lines.append(f"{'=' * 76}")
    lines.append("")
    lines.append(f"  {'RED  (lo grit, hi pts)':<36}  {'GREEN  (hi grit, hi pts)':<36}")
    lines.append(f"  {'n=' + str(n_red):<36}  {'n=' + str(n_green):<36}")
    for i in range(5):
        l = top_in("RED")[i]   if i < len(top_in("RED"))   else ""
        r = top_in("GREEN")[i] if i < len(top_in("GREEN")) else ""
        lines.append(f"  {l:<36}  {r:<36}")
    lines.append("  " + "-" * 36 + "  " + "-" * 36)
    lines.append(f"  {'GRAY (lo grit, lo pts)':<36}  {'BLUE   (hi grit, lo pts)':<36}")
    lines.append(f"  {'n=' + str(n_gray):<36}  {'n=' + str(n_blue):<36}")
    for i in range(5):
        l = top_in("GRAY")[i] if i < len(top_in("GRAY")) else ""
        r = top_in("BLUE")[i] if i < len(top_in("BLUE")) else ""
        lines.append(f"  {l:<36}  {r:<36}")
    lines.append("")

    if show_headline:
        headline = df[
            (df["quadrant"] == "BLUE")
            & (df["age"].notna())
            & (df["age"] <= max_age)
            & (df["pts_gap"] <= max_pts_gap)
        ].sort_values("grit_z_blend", ascending=False)

        lines.append(f"  {'-' * 76}")
        lines.append(f"  HEADLINE (age ≤ {max_age:g}, pts_gap ≤ {max_pts_gap:g}) — "
                     f"n = {len(headline)}")
        lines.append(f"  {'-' * 76}")
        for _, r in headline.iterrows():
            age_str = f"{int(r['age'])}" if pd.notna(r["age"]) else "?"
            lines.append(
                f"    {r['name']:<22} {r['team']:<4} age={age_str:<3} "
                f"gz={r['grit_z_blend']:+.2f}  pts={int(r['points']):<3} "
                f"gap={r['pts_gap']:+.1f}"
            )
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=str, action="append",
                    help="Season tag (end year), repeatable: --season 2025 --season 2026")
    ap.add_argument("--all-seasons", action="store_true",
                    help="Process all 10 RS seasons in ALL_RS_SEASONS")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                    help=f"Where to write outputs (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--no-grid", action="store_true",
                    help="Suppress the text quadrant grid output")
    ap.add_argument("--headline-filter", action="store_true",
                    help="Also write eyp_headline_v31_{season}.csv with narrow "
                         "filter (age <= max-age, pts_gap <= max-pts-gap)")
    ap.add_argument("--headline-max-age", type=float, default=HEADLINE_MAX_AGE,
                    help=f"Max age for headline filter (default {HEADLINE_MAX_AGE})")
    ap.add_argument("--headline-max-pts-gap", type=float, default=HEADLINE_MAX_PTS_GAP,
                    help=f"Max pts_gap for headline filter (default {HEADLINE_MAX_PTS_GAP})")
    args = ap.parse_args()

    if not args.season and not args.all_seasons:
        ap.error("Pass --season YYYY (repeatable) or --all-seasons")

    seasons = [str(s) for s in ALL_RS_SEASONS] if args.all_seasons else args.season

    engine = get_engine()
    print(f"Data dir: {args.data_dir}")
    print(f"Seasons:  {seasons}")
    print(f"GP floor: {GP_FLOOR}, GRIT cutoff: {GRIT_CUTOFF}")
    if args.headline_filter:
        print(f"Headline: age ≤ {args.headline_max_age:g}, "
              f"pts_gap ≤ {args.headline_max_pts_gap:g}")

    grids = []
    for s in seasons:
        print(f"\n[{s}] processing…")
        df = build_season_eyp(engine, s)
        if df.empty:
            continue
        write_per_season(df, s, args.data_dir)
        write_watchlist(df, s, args.data_dir)
        if args.headline_filter:
            write_headline(df, s, args.data_dir,
                           args.headline_max_age, args.headline_max_pts_gap)
        if not args.no_grid:
            grids.append(quadrant_grid(
                df, s,
                show_headline=args.headline_filter,
                max_age=args.headline_max_age,
                max_pts_gap=args.headline_max_pts_gap,
            ))

    if grids:
        for g in grids:
            print(g)


if __name__ == "__main__":
    main()
