#!/usr/bin/env python3
"""
load_close_shots.py — load close-range shot counts into SQL Server.

Reads every close_shot_test_{season}.csv file in --input-dir and updates the
existing grit_scores table to include each player's raw_close_shots count.

This is a v3.1-prep loader. Once v3.1 ships, build_v3.py will populate this
column natively during the build pass and this script becomes obsolete.
Until then, it lets us get the close-shot data into SQL alongside everything
else without waiting for the v3.1 rebuild cycle.

Schema change required (run once before this script):
    ALTER TABLE grit_scores ADD raw_close_shots INT NOT NULL DEFAULT 0;

The script uses the same connection pattern as build_v3.py:
    Trusted Windows authentication, ODBC Driver 17, SQL Server localhost,
    database = GRIT.

Usage:
    python load_close_shots.py \\
        --input-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3"

What it does, per CSV:
    1. Parse season tag from filename (close_shot_test_{tag}.csv)
    2. Resolve season tag to (season, is_playoffs) — the existing convention:
         tag '2026'          -> season=2026, is_playoffs=0
         tag '2026_playoffs' -> season=2026, is_playoffs=1
    3. UPDATE grit_scores SET raw_close_shots = ?
       WHERE season = ? AND is_playoffs = ? AND strength = 'all'
       AND player_id = ?
       — keyed batch update; only touches rows that exist
    4. Report match count vs CSV row count for sanity check
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


# Mirrors build_v3.py
SQL_SERVER   = "localhost"
SQL_DATABASE = "GRIT"
SQL_DRIVER   = "ODBC Driver 17 for SQL Server"


# ---------------------------------------------------------------------------
# Path anchoring. The loader assumes it lives at:
#     C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\source\load_close_shots.py
# DEFAULT_INPUT_DIR resolves to one level up: Version 3\
# Override with --input-dir if running from a non-standard location.
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = SCRIPT_DIR.parent  # Version 3\


def get_sql_engine():
    """Same pattern as build_v3.py — trusted Windows auth."""
    from sqlalchemy import create_engine
    conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/{SQL_DATABASE}"
        f"?driver={SQL_DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
        f"&TrustServerCertificate=yes"
    )
    return create_engine(conn_str, fast_executemany=True)


def parse_season_tag(filename: str) -> tuple[int, int] | None:
    """
    'close_shot_test_2026.csv'          -> (2026, 0)
    'close_shot_test_2026_playoffs.csv' -> (2026, 1)
    """
    m = re.match(r"close_shot_test_(\d{4})(_playoffs)?\.csv$", filename)
    if not m:
        return None
    season = int(m.group(1))
    is_playoffs = 1 if m.group(2) else 0
    return (season, is_playoffs)


def ensure_column_exists(engine):
    """
    Verify raw_close_shots column exists on grit_scores. If not, fail loudly
    with the ALTER TABLE statement to run.
    """
    from sqlalchemy import text
    check_sql = text("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'grit_scores' AND COLUMN_NAME = 'raw_close_shots'
    """)
    with engine.connect() as conn:
        n = conn.execute(check_sql).scalar()
    if n == 0:
        print("ERROR: grit_scores.raw_close_shots column does not exist.", file=sys.stderr)
        print("       Run this in SSMS first:", file=sys.stderr)
        print("       ALTER TABLE grit_scores ADD raw_close_shots INT NOT NULL DEFAULT 0;",
              file=sys.stderr)
        sys.exit(1)


def load_one_file(engine, csv_path: Path) -> dict:
    """Load close-shot counts from one CSV into grit_scores."""
    season_info = parse_season_tag(csv_path.name)
    if season_info is None:
        return {"file": csv_path.name, "status": "skipped", "reason": "filename pattern mismatch"}
    season, is_playoffs = season_info

    df = pd.read_csv(csv_path)
    if "player_id" not in df.columns or "raw_close_shots" not in df.columns:
        return {
            "file": csv_path.name, "status": "error",
            "reason": f"missing required columns; have: {list(df.columns)}"
        }

    # Keep only the keys we need
    df = df[["player_id", "raw_close_shots"]].copy()
    df["season"] = season
    df["is_playoffs"] = is_playoffs

    # Use a parameterized UPDATE in a single transaction
    from sqlalchemy import text
    update_sql = text("""
        UPDATE grit_scores
        SET raw_close_shots = :rcs
        WHERE season = :season
          AND is_playoffs = :ip
          AND strength = 'all'
          AND player_id = :pid
    """)

    matched_rows = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            result = conn.execute(update_sql, {
                "rcs": int(row["raw_close_shots"]),
                "season": season,
                "ip": is_playoffs,
                "pid": int(row["player_id"]),
            })
            # rowcount tells us how many rows the WHERE matched
            if result.rowcount > 0:
                matched_rows += result.rowcount

    return {
        "file": csv_path.name,
        "status": "ok",
        "season": season,
        "is_playoffs": is_playoffs,
        "csv_rows": len(df),
        "matched_rows": matched_rows,
        "unmatched": len(df) - matched_rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
                        help=f"Directory containing close_shot_test_*.csv files "
                             f"(default: {DEFAULT_INPUT_DIR})")
    args = parser.parse_args()

    print(f"Input directory: {args.input_dir}")
    if args.input_dir == DEFAULT_INPUT_DIR:
        print("  (using default — pass --input-dir to override)")
    print()

    if not args.input_dir.exists():
        print(f"ERROR: --input-dir does not exist: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(args.input_dir.glob("close_shot_test_*.csv"))
    if not files:
        print(f"ERROR: no close_shot_test_*.csv files in {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} close-shot CSVs:")
    for f in files:
        print(f"  {f.name}")
    print()

    engine = get_sql_engine()

    # Confirm schema
    print("Verifying grit_scores.raw_close_shots column exists...")
    ensure_column_exists(engine)
    print("  OK.")
    print()

    # Load each file
    print("Loading close-shot counts into grit_scores...")
    print(f"{'Season':<10}{'Type':<10}{'CSV rows':>10}{'Matched':>10}{'Unmatched':>11}{'Status':>10}")
    print("-" * 61)
    total_csv = 0
    total_matched = 0
    for f in files:
        result = load_one_file(engine, f)
        if result["status"] != "ok":
            print(f"  SKIP {f.name}: {result.get('reason','')}")
            continue
        type_str = "Playoffs" if result["is_playoffs"] else "RS"
        print(f"{result['season']:<10}{type_str:<10}"
              f"{result['csv_rows']:>10}{result['matched_rows']:>10}"
              f"{result['unmatched']:>11}{'OK':>10}")
        total_csv += result["csv_rows"]
        total_matched += result["matched_rows"]

    print("-" * 61)
    print(f"{'TOTAL':<20}{total_csv:>10}{total_matched:>10}"
          f"{total_csv - total_matched:>11}")
    print()
    if total_csv != total_matched:
        print(f"NOTE: {total_csv - total_matched} CSV rows did not find a matching row in")
        print(f"      grit_scores. This typically means a player qualified for the close-shot")
        print(f"      test (any close shots) but didn't qualify for the per_60 file (TOI floor).")
        print(f"      That's expected. The per_60 floor is the gating qualification.")


if __name__ == "__main__":
    main()
