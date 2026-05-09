#!/usr/bin/env python3
"""
load_grit_to_sql.py — Load all GRIT v3 CSVs into SQL Server.

Populates:
  - players          (from all per_60 files)
  - player_season_toi (from toi CSVs — currently only 2025 exists)
  - grit_scores      (from per_60, 5v5, and pk files)
  - grit_spatial     (from spatial files)
  - grit_monthly     (from monthly files)

Does NOT populate raw_plays — that requires re-scraping.

Usage:
    pip install pandas pyodbc sqlalchemy

    python load_grit_to_sql.py --data-dir "C:\\path\\to\\your\\csv\\folder"

    # Dry run (validate files only, no DB writes):
    python load_grit_to_sql.py --data-dir "C:\\path\\to\\your\\csv\\folder" --dry-run
"""

import argparse
import glob
import os
import re
import sys

import pandas as pd
from sqlalchemy import create_engine, text


# ============================================================================
# Config
# ============================================================================

SERVER   = "localhost"
DATABASE = "GRIT"
DRIVER   = "ODBC Driver 17 for SQL Server"

# File patterns and their season/playoffs metadata
# Each tuple: (glob_pattern, season_from_filename, is_playoffs)
PER60_PATTERN    = "grit_per_60_v3_{tag}.csv"
V5V5_PATTERN     = "grit_5v5_v3_{tag}.csv"
PK_PATTERN       = "grit_pk_v3_{tag}.csv"
SPATIAL_PATTERN  = "grit_spatial_v3_{tag}.csv"
MONTHLY_PATTERN  = "grit_monthly_v3_{tag}.csv"
TOI_PATTERN      = "toi_{season}_scraped.csv"


def get_engine():
    conn_str = (
        f"mssql+pyodbc://@{SERVER}/{DATABASE}"
        f"?driver={DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
        f"&TrustServerCertificate=yes"
    )
    return create_engine(conn_str, fast_executemany=True)


def parse_tag(filename):
    """
    Extract (season, is_playoffs) from a filename tag like:
      grit_per_60_v3_2026.csv        -> (2026, False)
      grit_per_60_v3_2026_playoffs.csv -> (2026, True)
    """
    stem = os.path.basename(filename).replace(".csv", "")
    m = re.search(r'_(\d{4})(_playoffs)?$', stem)
    if not m:
        return None, None
    season     = int(m.group(1))
    is_playoffs = m.group(2) is not None
    return season, is_playoffs


def load_players(engine, all_per60_files, dry_run):
    """Upsert player identity from all per_60 files."""
    print("\n--- Loading players ---")
    frames = []
    for f in all_per60_files:
        df = pd.read_csv(f, usecols=["player_id", "name", "position"])
        frames.append(df)

    players = pd.concat(frames).drop_duplicates(subset="player_id")
    players = players.rename(columns={"player_id": "player_id", "name": "name", "position": "position"})
    print(f"  {len(players)} unique players found")

    if dry_run:
        print("  [DRY RUN] Skipping write")
        return

    with engine.begin() as conn:
        for _, row in players.iterrows():
            conn.execute(text("""
                IF NOT EXISTS (SELECT 1 FROM players WHERE player_id = :pid)
                    INSERT INTO players (player_id, name, position)
                    VALUES (:pid, :name, :pos)
                ELSE
                    UPDATE players SET name = :name, position = :pos
                    WHERE player_id = :pid
            """), {"pid": int(row.player_id), "name": row["name"], "pos": row.position})

    print(f"  Done.")


def load_grit_scores(engine, data_dir, dry_run):
    """Load all per_60, 5v5, and pk files into grit_scores."""
    print("\n--- Loading grit_scores ---")

    patterns = [
        ("grit_per_60_v3_*.csv", "all"),
        ("grit_5v5_v3_*.csv",    "5v5"),
        ("grit_pk_v3_*.csv",     "pk"),
    ]

    total = 0
    for pattern, strength in patterns:
        files = sorted(glob.glob(os.path.join(data_dir, "**", pattern), recursive=True))
        print(f"  {strength}: {len(files)} files")

        for f in files:
            season, is_playoffs = parse_tag(f)
            if season is None:
                print(f"    SKIP (can't parse tag): {f}")
                continue

            df = pd.read_csv(f)
            df["season"]      = season
            df["is_playoffs"] = int(is_playoffs)
            df["strength"]    = strength

            # Rename columns to match schema
            df = df.rename(columns={"toi_min": "toi_min"})

            # Ensure all expected columns exist
            score_cols = [
                "player_id", "season", "is_playoffs", "strength",
                "games_played", "toi_min", "weighted_total",
                "raw_grit_per_60", "grit_per_game",
                "grit_z_pos", "grit_z_vol", "grit_z_blend",
                "raw_blocked_shots", "raw_blocked_shots_hd", "raw_blocked_shots_non_hd",
                "raw_crease_goals", "raw_dz_faceoff_wins", "raw_fighting_majors",
                "raw_giveaways_dz", "raw_giveaways_nz", "raw_giveaways_oz",
                "raw_hits_taken", "raw_hits_thrown", "raw_penalties_drawn",
                "raw_physical_minors_taken", "raw_takeaways_high_danger", "raw_takeaways_other",
            ]
            for col in score_cols:
                if col not in df.columns:
                    df[col] = 0

            df = df[score_cols]

            tag = f"{season}{'_playoffs' if is_playoffs else ''}"
            print(f"    {tag} ({strength}): {len(df)} rows", end="")

            if not dry_run:
                # Delete existing rows for this season/playoffs/strength then insert
                with engine.begin() as conn:
                    conn.execute(text("""
                        DELETE FROM grit_scores
                        WHERE season = :s AND is_playoffs = :p AND strength = :st
                    """), {"s": season, "p": int(is_playoffs), "st": strength})

                df.to_sql("grit_scores", engine, if_exists="append", index=False, method="multi", chunksize=75)
                total += len(df)
                print(" ✓")
            else:
                print(" [DRY RUN]")

    print(f"  Total rows loaded: {total}")


def load_spatial(engine, data_dir, dry_run):
    """Load all spatial files into grit_spatial."""
    print("\n--- Loading grit_spatial ---")

    files = sorted(glob.glob(os.path.join(data_dir, "**", "grit_spatial_v3_*.csv"), recursive=True))
    print(f"  {len(files)} files found")

    total = 0
    for f in files:
        season, is_playoffs = parse_tag(f)
        if season is None:
            print(f"  SKIP: {f}")
            continue

        df = pd.read_csv(f, usecols=["player_id", "x", "y", "event_type"])
        df["season"]      = season
        df["is_playoffs"] = int(is_playoffs)

        tag = f"{season}{'_playoffs' if is_playoffs else ''}"
        print(f"  {tag}: {len(df)} rows", end="")

        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM grit_spatial
                    WHERE season = :s AND is_playoffs = :p
                """), {"s": season, "p": int(is_playoffs)})

            df = df[["player_id", "season", "is_playoffs", "x", "y", "event_type"]]
            df.to_sql("grit_spatial", engine, if_exists="append", index=False, method="multi", chunksize=200)
            total += len(df)
            print(" ✓")
        else:
            print(" [DRY RUN]")

    print(f"  Total rows loaded: {total}")


def load_monthly(engine, data_dir, dry_run):
    """Load all monthly files into grit_monthly."""
    print("\n--- Loading grit_monthly ---")

    files = sorted(glob.glob(os.path.join(data_dir, "**", "grit_monthly_v3_*.csv"), recursive=True))
    print(f"  {len(files)} files found")

    total = 0
    for f in files:
        season, is_playoffs = parse_tag(f)
        if season is None:
            print(f"  SKIP: {f}")
            continue

        df = pd.read_csv(f, usecols=["player_id", "month", "weighted_total", "approx_toi_min", "raw_grit_per_60"])
        df["season"]      = season
        df["is_playoffs"] = int(is_playoffs)

        tag = f"{season}{'_playoffs' if is_playoffs else ''}"
        print(f"  {tag}: {len(df)} rows", end="")

        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM grit_monthly
                    WHERE season = :s AND is_playoffs = :p
                """), {"s": season, "p": int(is_playoffs)})

            df = df[["player_id", "season", "is_playoffs", "month", "weighted_total", "approx_toi_min", "raw_grit_per_60"]]
            df.to_sql("grit_monthly", engine, if_exists="append", index=False, method="multi", chunksize=200)
            total += len(df)
            print(" ✓")
        else:
            print(" [DRY RUN]")

    print(f"  Total rows loaded: {total}")


def load_toi(engine, data_dirs, dry_run):
    """Load TOI files into player_season_toi."""
    print("\n--- Loading player_season_toi ---")

    files = []
    for d in data_dirs:
        files += glob.glob(os.path.join(d, "**", "toi_*.csv"), recursive=True)
    files = sorted(set(files))
    print(f"  {len(files)} files found")

    total = 0
    for f in files:
        # Handle both toi_2026.csv and toi_2025_scraped.csv
        m = re.search(r'toi_(\d{4})(_playoffs)?(_scraped)?\.csv', os.path.basename(f))
        if not m:
            print(f"  SKIP: {f}")
            continue
        season      = int(m.group(1))
        is_playoffs = m.group(2) is not None

        df = pd.read_csv(f)
        df["season"]      = season
        df["is_playoffs"] = int(is_playoffs)
        df = df.rename(columns={
            "total_toi_min": "total_toi_min",
            "ev_toi_min":    "ev_toi_min",
            "sh_toi_min":    "sh_toi_min",
            "pp_toi_min":    "pp_toi_min",
        })

        tag = f"{season}{'_playoffs' if is_playoffs else ''}"
        print(f"  {tag}: {len(df)} rows", end="")

        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM player_season_toi
                    WHERE season = :s AND is_playoffs = :p
                """), {"s": season, "p": int(is_playoffs)})

            df = df[["player_id", "season", "is_playoffs", "team", "games_played",
                     "total_toi_min", "ev_toi_min", "sh_toi_min", "pp_toi_min"]]
            df.to_sql("player_season_toi", engine, if_exists="append", index=False, method="multi", chunksize=75)
            total += len(df)
            print(" ✓")
        else:
            print(" [DRY RUN]")

    print(f"  Total rows loaded: {total}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True,
                    help="Folder containing all GRIT CSVs")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate files without writing to DB")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"ERROR: --data-dir not found: {args.data_dir}")
        sys.exit(1)

    print(f"\nGRIT CSV -> SQL Loader")
    print(f"Data dir : {args.data_dir}")
    print(f"Database : {SERVER}/{DATABASE}")
    print(f"Dry run  : {args.dry_run}")

    engine = get_engine()

    # Test connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("\nDB connection: OK")
    except Exception as e:
        print(f"\nERROR connecting to SQL Server: {e}")
        print("Make sure pyodbc and 'ODBC Driver 17 for SQL Server' are installed.")
        sys.exit(1)

    # Collect all per_60 files for player extraction
    all_per60 = sorted(glob.glob(os.path.join(args.data_dir, "**", "grit_per_60_v3_*.csv"), recursive=True))
    if not all_per60:
        print(f"ERROR: No grit_per_60_v3_*.csv files found in {args.data_dir}")
        sys.exit(1)

    load_players(engine, all_per60, args.dry_run)
    load_grit_scores(engine, args.data_dir, args.dry_run)
    load_monthly(engine, args.data_dir, args.dry_run)
    load_spatial(engine, args.data_dir, args.dry_run)
    toi_dirs = [
        args.data_dir,
        r"C:\Users\mjrig\OneDrive\Documents\Grit\cache",
        r"C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\cache",
        r"C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\archive",
    ]
    load_toi(engine, toi_dirs, args.dry_run)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
