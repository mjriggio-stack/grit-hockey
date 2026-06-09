"""scrape_players.py — pull player bio/age data from NHL /player/{id}/landing.

For each distinct player_id in skater_scoring (or a passed list), calls
api-web.nhle.com/v1/player/{id}/landing and writes:
  - CSV at data_dir/players_v3.csv (full bio set, all-time roster)
  - Rows in SQL table 'players' (one row per player_id)

The players table is a static reference: one row per player across all
seasons. Re-runs are idempotent — existing players are skipped by default,
re-fetched with --refresh.

Use case: feeds the EYP framework's age filter (age <= 25), where:
    age = season_end_year - birth_year

That's the rough integer age agreed for v3.1 EYP. birth_date is also stored
as a string so we can switch to exact-age computation later without a
re-scrape.

Pattern mirrors scrape_scoring.py — same SQL connection settings, same
DELETE-then-INSERT strategy, same CSV-first/--no-sql contract.

Usage:
    # Default: scrape every player_id in skater_scoring that's not already
    # in the players table.
    python scrape_players.py

    # Force re-scrape of every player (overwrites stale rows)
    python scrape_players.py --refresh

    # Scrape a specific list of player_ids (comma-separated)
    python scrape_players.py --player-ids 8478402,8477934

    # CSV only, skip SQL
    python scrape_players.py --no-sql

    # Use a custom data dir for CSV output
    python scrape_players.py --output-dir /tmp/grit_data
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd


# =============================================================================
# Config
# =============================================================================

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

SQL_SERVER   = "localhost"
SQL_DATABASE = "GRIT"
SQL_DRIVER   = "ODBC Driver 17 for SQL Server"

DEFAULT_DATA_DIR = Path(
    r"C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\data"
)

API_LANDING = "https://api-web.nhle.com/v1/player/{pid}/landing"


# =============================================================================
# API fetch
# =============================================================================

def fetch_player(pid: int, timeout: int = 30) -> dict | None:
    """Fetch one player's landing JSON. Returns None on 404 or network error."""
    url = API_LANDING.format(pid=pid)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  HTTP {e.code} for player_id={pid}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  fetch failed for player_id={pid}: {e}", file=sys.stderr)
        return None


def extract_bio(pid: int, data: dict) -> dict:
    """Pull the bio fields we care about from a /player/{id}/landing payload.

    Field names checked against api-web.nhle.com behavior. Every field is
    extracted defensively — if the API renames or drops a field, the row
    still inserts with None for that column rather than crashing.

    Names like firstName/lastName are localized objects ({'default': 'Connor'});
    we pull .default and fall back to whatever's there.

    The 'draftDetails' subobject (when present) has 'year', 'round',
    'pickInRound', 'overallPick', 'teamAbbrev'. Undrafted players have
    no draftDetails key.
    """
    def loc(v):
        """Unwrap a localized {'default': 'X', 'fr': 'X'} object."""
        if isinstance(v, dict):
            return v.get("default") or next(iter(v.values()), None)
        return v

    first_name = loc(data.get("firstName"))
    last_name  = loc(data.get("lastName"))
    full_name = (
        f"{first_name} {last_name}".strip()
        if first_name or last_name
        else None
    )

    birth_date_str = data.get("birthDate")  # e.g., "1997-01-13"
    birth_year = None
    if birth_date_str and len(birth_date_str) >= 4:
        try:
            birth_year = int(birth_date_str[:4])
        except (ValueError, TypeError):
            birth_year = None

    draft = data.get("draftDetails") or {}

    return {
        "player_id":           pid,
        "full_name":           full_name,
        "first_name":          first_name,
        "last_name":           last_name,
        "birth_date_str":      birth_date_str,
        "birth_year":          birth_year,
        "birth_city":          loc(data.get("birthCity")),
        "birth_state_province": loc(data.get("birthStateProvince")),
        "birth_country":       data.get("birthCountry"),
        "position_code":       data.get("position"),
        "shoots_catches":      data.get("shootsCatches"),
        "height_in_inches":    data.get("heightInInches"),
        "weight_in_pounds":    data.get("weightInPounds"),
        "current_team_abbrev": data.get("currentTeamAbbrev"),
        "is_active":           data.get("isActive"),
        "draft_year":          draft.get("year"),
        "draft_round":         draft.get("round"),
        "draft_pick_in_round": draft.get("pickInRound"),
        "draft_overall_pick":  draft.get("overallPick"),
        "draft_team_abbrev":   draft.get("teamAbbrev"),
    }


# =============================================================================
# Player ID sources
# =============================================================================

def get_pids_from_skater_scoring(engine) -> list[int]:
    """Return every distinct player_id in skater_scoring (RS + playoffs)."""
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT DISTINCT player_id FROM skater_scoring "
            "WHERE player_id IS NOT NULL ORDER BY player_id"
        ))
        return [int(row[0]) for row in result]


def get_existing_pids(engine) -> set[int]:
    """Return player_ids that already have birth_year populated.

    'Already in the table' isn't a strong enough signal — the existing
    players table has 1329 stub rows without birth_year. We want to skip
    only player_ids that actually have a birth_year, so the first full
    run after the schema change will re-fetch them all (to backfill
    birth_year) but subsequent runs will be incremental.
    """
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT player_id FROM players WHERE birth_year IS NOT NULL"
            ))
            return {int(row[0]) for row in result}
    except Exception as e:
        # Table doesn't exist yet or birth_year column missing — fine
        print(f"  (players table not yet fully populated: {e})")
        return set()


# =============================================================================
# Disk write
# =============================================================================

def write_csv(df: pd.DataFrame, data_dir: Path) -> Path:
    """Write the full players dataframe to data_dir/players_v3.csv.

    This is a single all-time file (not per-season). Each run rewrites it
    in full from the union of new fetches + existing SQL rows (if any).
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "players_v3.csv"
    df.to_csv(out_path, index=False)
    print(f"  wrote {out_path}  ({len(df)} rows)")
    return out_path


# =============================================================================
# SQL write
# =============================================================================

def get_sql_engine():
    try:
        from sqlalchemy import create_engine
    except ImportError:
        raise ImportError("sqlalchemy not installed. Run: pip install sqlalchemy pyodbc")

    conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/{SQL_DATABASE}"
        f"?driver={SQL_DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
    )
    return create_engine(conn_str, fast_executemany=True)


def ensure_players_table(engine) -> None:
    """Make sure the players table exists and has the columns we need.

    The existing players table has just (player_id, name, position). We need
    to add birth_year to it for the EYP age filter. This function:

      1. CREATEs the players table if it doesn't exist (with the minimal
         4-column schema we actually use: player_id, name, position, birth_year).
      2. ALTERs it to add birth_year if the column is missing (handles the
         existing stub table from earlier sessions).

    We deliberately do NOT add 17 other bio fields to SQL — those go to the
    CSV only. The SQL table stays flat: just what EYP needs.
    """
    from sqlalchemy import text

    create_sql = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='players' AND xtype='U')
    CREATE TABLE players (
        player_id  INT          NOT NULL PRIMARY KEY,
        name       NVARCHAR(120) NULL,
        position   VARCHAR(4)   NULL,
        birth_year INT          NULL
    )
    """

    add_birth_year_sql = """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'players' AND COLUMN_NAME = 'birth_year'
    )
    ALTER TABLE players ADD birth_year INT NULL
    """

    with engine.begin() as conn:
        conn.execute(text(create_sql))
        conn.execute(text(add_birth_year_sql))


def write_sql(rows: list[dict], engine, refresh: bool) -> dict:
    """Upsert player bios into the 4-column players table.

    The table has just (player_id, name, position, birth_year). The 17 other
    bio fields we fetched go to the CSV only — not stored in SQL because EYP
    doesn't need them.

    Behavior:
      - For player_ids already in the table: UPDATE name, position, birth_year
        (so we backfill birth_year on the existing 1329 stub rows).
      - For player_ids not in the table: INSERT (player_id, name, position,
        birth_year).
      - With --refresh: same as default, since we're upserting either way.
        The flag affects which player_ids we fetch (see main), not the SQL.

    Returns dict of counts for the run summary.
    """
    from sqlalchemy import text

    if not rows:
        return {"updated": 0, "inserted": 0}

    df = pd.DataFrame(rows)

    # Map our rich dataframe down to the 4 SQL columns.
    # full_name -> name (existing table's column name)
    # position_code -> position (existing table's column name)
    sql_df = pd.DataFrame({
        "player_id":  df["player_id"].astype(int),
        "name":       df["full_name"],
        "position":   df["position_code"],
        "birth_year": df["birth_year"],
    })

    # Find which player_ids are already in the table — those get UPDATEd, the
    # rest get INSERTed. One round-trip via a temp staging table would be
    # tidier but for ~800 rows the explicit split is fine and easier to read.
    with engine.connect() as conn:
        existing = pd.read_sql(
            text("SELECT player_id FROM players"),
            conn,
        )
    existing_pids = set(existing["player_id"].astype(int).tolist())

    update_df = sql_df[sql_df["player_id"].isin(existing_pids)].copy()
    insert_df = sql_df[~sql_df["player_id"].isin(existing_pids)].copy()

    # UPDATE path: row-by-row UPDATE. For ~1300 rows this takes a couple
    # of seconds — fine for a one-time scrape. If it ever needs to scale,
    # switch to a staging-table + MERGE.
    updated = 0
    if len(update_df) > 0:
        update_sql = text("""
            UPDATE players
            SET name       = :name,
                position   = :position,
                birth_year = :birth_year
            WHERE player_id = :player_id
        """)
        with engine.begin() as conn:
            for _, row in update_df.iterrows():
                # SQL Server doesn't accept numpy types as parameters cleanly
                # under all driver versions; coerce nullable ints to Python.
                by = row["birth_year"]
                params = {
                    "player_id":  int(row["player_id"]),
                    "name":       (None if pd.isna(row["name"]) else str(row["name"])),
                    "position":   (None if pd.isna(row["position"]) else str(row["position"])),
                    "birth_year": (None if pd.isna(by) else int(by)),
                }
                result = conn.execute(update_sql, params)
                if result.rowcount and result.rowcount > 0:
                    updated += result.rowcount
        print(f"  SQL: updated {updated} existing rows (backfilled birth_year)")

    # INSERT path: bulk insert via pandas. 4 columns × 200 chunksize = 800
    # parameters — comfortably under SQL Server's 2100 limit.
    inserted = 0
    if len(insert_df) > 0:
        # Coerce nullable int birth_year to Python int / None for the driver
        insert_df["birth_year"] = insert_df["birth_year"].apply(
            lambda v: None if pd.isna(v) else int(v)
        )
        insert_df.to_sql(
            "players",
            engine,
            if_exists="append",
            index=False,
            chunksize=200,
            method=None,
        )
        inserted = len(insert_df)
        print(f"  SQL: inserted {inserted} new rows")

    return {"updated": updated, "inserted": inserted}


# =============================================================================
# Main scrape loop
# =============================================================================

def scrape_player_list(pids: list[int], delay: float, dump_first_raw: bool = True) -> list[dict]:
    """Fetch every player_id and return list of bio dicts.

    On the first successful fetch, dumps the raw JSON to stdout so the
    operator can eyeball field names and confirm the extract_bio mapping
    is right. Disable with dump_first_raw=False.
    """
    rows = []
    misses = 0
    dumped = False

    for i, pid in enumerate(pids, 1):
        data = fetch_player(pid)
        if data is None:
            misses += 1
            continue

        if dump_first_raw and not dumped:
            print("\n  === raw /player/{id}/landing keys (first success) ===")
            print(f"  player_id: {pid}")
            print(f"  top-level keys: {sorted(data.keys())}")
            print("  sample fields we extract:")
            for k in ("firstName", "lastName", "birthDate", "birthCountry",
                      "position", "shootsCatches", "heightInInches",
                      "weightInPounds", "currentTeamAbbrev", "isActive",
                      "draftDetails"):
                v = data.get(k)
                if isinstance(v, dict):
                    print(f"    {k}: {v}")
                else:
                    print(f"    {k}: {v!r}")
            print("  ====================================================\n")
            dumped = True

        rows.append(extract_bio(pid, data))

        if i % 50 == 0:
            print(f"  fetched {i}/{len(pids)} ({misses} misses)")

        time.sleep(delay)

    print(f"  done: {len(rows)} bios, {misses} misses out of {len(pids)} requests")
    return rows


# =============================================================================
# Main
# =============================================================================

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--player-ids", type=str,
                    help="Comma-separated list of player_ids to scrape "
                         "(overrides the default skater_scoring scan).")
    ap.add_argument("--refresh", action="store_true",
                    help="Re-scrape every player (default skips players "
                         "already in the table).")
    ap.add_argument("--no-sql", action="store_true",
                    help="Skip SQL writes — CSV only.")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_DATA_DIR,
                    help=f"Where to write CSV (default: {DEFAULT_DATA_DIR}).")
    ap.add_argument("--delay", type=float, default=0.15,
                    help="Seconds between API requests (default 0.15).")
    args = ap.parse_args()

    # Resolve which player_ids we're going to fetch
    engine = None
    if not args.no_sql:
        engine = get_sql_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        print("SQL connection OK.")
        ensure_players_table(engine)

    if args.player_ids:
        pids = [int(s.strip()) for s in args.player_ids.split(",") if s.strip()]
        print(f"Scraping {len(pids)} player_id(s) from --player-ids argument")
    else:
        if engine is None:
            print("ERROR: --no-sql requires --player-ids (need a source of player_ids)",
                  file=sys.stderr)
            sys.exit(1)
        all_pids = get_pids_from_skater_scoring(engine)
        print(f"Found {len(all_pids)} distinct player_ids in skater_scoring")

        if args.refresh:
            pids = all_pids
            print(f"  --refresh mode: scraping all {len(pids)}")
        else:
            existing = get_existing_pids(engine)
            print(f"  {len(existing)} already have birth_year populated — will skip")
            pids = [p for p in all_pids if p not in existing]
            print(f"  scraping {len(pids)} player_id(s)")

    if not pids:
        print("Nothing to scrape. Exiting.")
        return

    print(f"\nFetching with delay={args.delay}s between calls...")
    rows = scrape_player_list(pids, args.delay)

    if not rows:
        print("No successful fetches. Nothing to write.")
        return

    if engine is not None:
        result = write_sql(rows, engine, refresh=args.refresh)
        print(f"  SQL summary: {result['updated']} updated, {result['inserted']} inserted")

    # CSV: rich bio data, all 20 columns. SQL stores only 4 of these.
    # Union this batch with any existing CSV so the file is a running
    # snapshot. Last-write-wins on player_id collisions.
    new_df = pd.DataFrame(rows)
    csv_path = args.output_dir / "players_v3.csv"
    if csv_path.exists():
        try:
            old_df = pd.read_csv(csv_path)
            # Drop rows in old_df that we have fresh data for, then concat
            old_df = old_df[~old_df["player_id"].isin(new_df["player_id"])]
            full_df = pd.concat([old_df, new_df], ignore_index=True)
            print(f"  CSV: merged with existing {csv_path.name} "
                  f"({len(old_df)} kept + {len(new_df)} new = {len(full_df)} total)")
        except Exception as e:
            print(f"  CSV: couldn't merge with existing ({e}); writing fresh")
            full_df = new_df
    else:
        full_df = new_df

    write_csv(full_df, args.output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
