#!/usr/bin/env python3
"""
scrape_v3.py — download NHL PBP cache and TOI data for a given season.

Run this before build_v3.py. It produces:
  - A directory of per-game JSON files (one per game)
  - A toi_{season_tag}.csv file with EV/PP/SH splits for all skaters

Usage:
    # Regular season 2025-26:
    python scrape_v3.py --season 2025 --output-dir C:\\grit\\cache\\2025

    # Regular season 2022-23:
    python scrape_v3.py --season 2022 --output-dir C:\\grit\\cache\\2022

    # Playoffs 2025:
    python scrape_v3.py --season 2025 --output-dir C:\\grit\\cache\\2025_playoffs --playoffs

    # Resume an interrupted scrape (skips already-downloaded files):
    python scrape_v3.py --season 2025 --output-dir C:\\grit\\cache\\2025

Season tag conventions (match build_v3.py):
    2020 = 2019-20 season
    2021 = 2020-21 season (COVID bubble — short season, use with caution)
    2022 = 2021-22 season
    2023 = 2022-23 season
    2024 = 2023-24 season
    2025 = 2024-25 season
    2026 = 2025-26 season  (or pass --season 2025 with custom --season-tag 2025)

Season start/end dates are looked up automatically from the NHL schedule API.
"""

import argparse
import csv
import json
import os
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Known regular season start/end dates (inclusive).
# End date is the last day regular season games are scheduled.
# If a season isn't listed, the script will attempt to infer it from the API.
RS_DATES = {
    2010: (date(2009, 10,  1), date(2010,  4,  11)),
    2011: (date(2010, 10,  7), date(2011,  4,  10)),
    2012: (date(2011, 10,  6), date(2012,  4,   7)),
    2013: (date(2012, 10,  4), date(2013,  4,  27)),  # lockout-shortened
    2014: (date(2013, 10,  1), date(2014,  4,  13)),
    2015: (date(2014, 10,  8), date(2015,  4,  11)),
    2016: (date(2015, 10,  7), date(2016,  4,   9)),
    2017: (date(2016, 10, 12), date(2017,  4,   9)),
    2018: (date(2017, 10,  4), date(2018,  4,   8)),
    2019: (date(2018, 10,  3), date(2019,  4,   6)),
    2020: (date(2019, 10,  2), date(2020,  3,  11)),  # paused Mar 12 (COVID)
    2021: (date(2021,  1, 13), date(2021,  5,  19)),  # COVID bubble (56 games)
    2022: (date(2021, 10, 12), date(2022,  4,  29)),
    2023: (date(2022, 10, 11), date(2023,  4,  13)),
    2024: (date(2023, 10, 10), date(2024,  4,  18)),
    2025: (date(2024, 10,  8), date(2025,  4,  18)),
    2026: (date(2025, 10,  8), date(2026,  4,  18)),
}

# NHL season ID format: YYYYYYYY (start year concatenated with end year)
def season_id(season_tag):
    start_yr = int(season_tag) - 1
    end_yr   = int(season_tag)
    return f"{start_yr}{end_yr}"


def fetch(url, retries=3, delay=0.5):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise e


def get_schedule_dates(season_tag):
    """Return (start_date, end_date) for a regular season."""
    tag = int(season_tag)
    if tag in RS_DATES:
        return RS_DATES[tag]
    # Fallback: try to infer from API
    sid = season_id(season_tag)
    url = f"https://api.nhle.com/stats/rest/en/season?cayenneExp=id={sid}"
    try:
        data = fetch(url)
        if data.get("data"):
            row = data["data"][0]
            s = row.get("startDate", "")[:10]
            e = row.get("regularSeasonEndDate", row.get("endDate", ""))[:10]
            if s and e:
                return date.fromisoformat(s), date.fromisoformat(e)
    except Exception:
        pass
    raise ValueError(
        f"Unknown season tag {season_tag}. Add it to RS_DATES in scrape_v3.py."
    )


def get_playoff_game_ids(season_tag):
    """
    Return dict of {game_id: date_str} for all playoff games in a season.
    Playoff game IDs use gameType=3.
    """
    sid = season_id(season_tag)
    # Playoffs typically run April through June
    start_yr = int(season_tag) - 1
    p_start = date(int(season_tag), 4, 1)
    p_end   = date(int(season_tag), 7, 15)

    game_ids = {}
    d = p_start
    while d <= p_end:
        url = f"https://api-web.nhle.com/v1/schedule/{d.strftime('%Y-%m-%d')}"
        try:
            data = fetch(url)
            for week in data.get("gameWeek", []):
                for g in week.get("games", []):
                    if g.get("gameType") == 3:
                        game_ids[g["id"]] = week["date"]
        except Exception as e:
            print(f"  Schedule error {d}: {e}")
        d += timedelta(days=7)
        time.sleep(0.1)
    return game_ids


def get_rs_game_ids(season_tag):
    """Return dict of {game_id: date_str} for all regular season games."""
    start, end = get_schedule_dates(season_tag)
    game_ids = {}
    d = start
    while d <= end:
        url = f"https://api-web.nhle.com/v1/schedule/{d.strftime('%Y-%m-%d')}"
        try:
            data = fetch(url)
            for week in data.get("gameWeek", []):
                for g in week.get("games", []):
                    if g.get("gameType") == 2:
                        game_ids[g["id"]] = week["date"]
        except Exception as e:
            print(f"  Schedule error {d}: {e}")
        d += timedelta(days=7)
        time.sleep(0.1)
    return game_ids


def scrape_pbp(game_ids, cache_dir, delay=0.12):
    """
    Download play-by-play JSON for each game ID into cache_dir.
    Skips files that already exist (safe to resume).
    Returns (downloaded, skipped, errors).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    already = set(os.listdir(cache_dir))

    downloaded = skipped = 0
    errors = []

    for gid, date_str in sorted(game_ids.items()):
        fname = f"{date_str}_{gid}.json"
        if fname in already:
            skipped += 1
            continue
        url = f"https://api-web.nhle.com/v1/gamecenter/{gid}/play-by-play"
        try:
            data = fetch(url)
            with open(cache_dir / fname, "w") as f:
                json.dump(data, f)
            downloaded += 1
        except Exception as e:
            errors.append((gid, str(e)))
        time.sleep(delay)

        if (downloaded + skipped) % 100 == 0:
            total = len(game_ids)
            done  = downloaded + skipped
            print(f"  {done}/{total} games ({downloaded} new, {skipped} cached, {len(errors)} errors)")

    return downloaded, skipped, errors


def scrape_toi(season_tag, out_path, playoffs=False):
    """
    Download season-level TOI splits for all skaters and write to CSV.
    """
    sid      = season_id(season_tag)
    game_type = 3 if playoffs else 2
    base_url = (
        f"https://api.nhle.com/stats/rest/en/skater/timeonice"
        f"?limit=1&start=0&sort=timeOnIce"
        f"&cayenneExp=seasonId={sid}%20and%20gameTypeId={game_type}"
    )
    total = fetch(base_url)["total"]
    print(f"  Fetching TOI for {total} skaters...")

    all_rows = []
    start = 0
    while start < total:
        url = (
            f"https://api.nhle.com/stats/rest/en/skater/timeonice"
            f"?limit=100&start={start}&sort=timeOnIce"
            f"&cayenneExp=seasonId={sid}%20and%20gameTypeId={game_type}"
        )
        data = fetch(url)
        all_rows.extend(data["data"])
        start += 100
        time.sleep(0.1)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "player_id", "name", "position", "team",
            "games_played", "total_toi_min",
            "ev_toi_min", "sh_toi_min", "pp_toi_min",
        ])
        for r in all_rows:
            w.writerow([
                r["playerId"],
                r["skaterFullName"],
                r["positionCode"],
                r["teamAbbrevs"],
                r["gamesPlayed"],
                round(r["timeOnIce"]    / 60, 2),
                round(r["evTimeOnIce"]  / 60, 2),
                round(r["shTimeOnIce"]  / 60, 2),
                round(r["ppTimeOnIce"]  / 60, 2),
            ])

    print(f"  TOI written to {out_path}")
    return len(all_rows)


def main():
    ap = argparse.ArgumentParser(
        description="Scrape NHL PBP cache and TOI for GRIT v3 build."
    )
    ap.add_argument(
        "--season", required=True,
        help="Season end year, e.g. 2025 for the 2024-25 season"
    )
    ap.add_argument(
        "--output-dir", required=True,
        help="Directory to write PBP cache and TOI CSV"
    )
    ap.add_argument(
        "--playoffs", action="store_true",
        help="Scrape playoff games instead of regular season"
    )
    ap.add_argument(
        "--pbp-only", action="store_true",
        help="Skip TOI scrape (useful if TOI already downloaded)"
    )
    ap.add_argument(
        "--toi-only", action="store_true",
        help="Skip PBP scrape (useful if PBP cache already complete)"
    )
    ap.add_argument(
        "--delay", type=float, default=0.12,
        help="Seconds between API requests (default 0.12)"
    )
    args = ap.parse_args()

    out_dir  = Path(args.output_dir)
    pbp_dir  = out_dir / "pbp"
    toi_path = out_dir / f"toi_{args.season}{'_playoffs' if args.playoffs else ''}.csv"

    out_dir.mkdir(parents=True, exist_ok=True)

    label = "playoffs" if args.playoffs else "regular season"
    print(f"\nGRIT v3 scraper — {args.season} {label}")
    print(f"Output directory: {out_dir}\n")

    # ── Game IDs ──────────────────────────────────────────────────────────────
    if not args.toi_only:
        print(f"Fetching {label} schedule for season {args.season}...")
        if args.playoffs:
            game_ids = get_playoff_game_ids(args.season)
        else:
            game_ids = get_rs_game_ids(args.season)
        print(f"  Found {len(game_ids)} games\n")

        # Save game ID manifest for reference
        manifest_path = out_dir / f"game_ids_{args.season}{'_playoffs' if args.playoffs else ''}.json"
        with open(manifest_path, "w") as f:
            json.dump({str(k): v for k, v in game_ids.items()}, f)

        # ── PBP cache ──────────────────────────────────────────────────────────
        print(f"Downloading PBP cache to {pbp_dir}...")
        downloaded, skipped, errors = scrape_pbp(game_ids, pbp_dir, delay=args.delay)
        total_cached = len(list(pbp_dir.iterdir()))
        print(f"\n  PBP complete: {total_cached} files cached")
        print(f"  ({downloaded} new, {skipped} already existed, {len(errors)} errors)")
        if errors:
            print(f"  Errors: {errors[:5]}{'...' if len(errors) > 5 else ''}")

    # ── TOI ───────────────────────────────────────────────────────────────────
    if not args.pbp_only:
        print(f"\nDownloading TOI data...")
        n = scrape_toi(args.season, toi_path, playoffs=args.playoffs)
        print(f"  {n} skaters written")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\nDone. Files in {out_dir}:")
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            size_kb = p.stat().st_size // 1024
            print(f"  {p.relative_to(out_dir)} ({size_kb} KB)")

    print(f"""
Next step — run build_v3.py:

    python build_v3.py \\
        --pbp-cache "{pbp_dir}" \\
        --toi "{toi_path}" \\
        --output-dir /path/to/outputs/{args.season}{'_playoffs' if args.playoffs else ''} \\
        --season-tag {args.season}{'_playoffs' if args.playoffs else ''}{'\\' + chr(10) + '        --playoffs' if args.playoffs else ''}
""")


if __name__ == "__main__":
    main()
