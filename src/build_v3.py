#!/usr/bin/env python3
"""
build_v3.py — produce v3-formatted GRIT files from PBP cache and TOI data.

v3 = v2.1 baseline + weight changes + pooling change.
Builds on v2.1 (which itself fixed bugs and realigned spatial methodology).

Changes from v2.1:
  Weight changes:
    1. crease_goals: 7.5 → 10.0 (top-tier weight; rewards going to the net)
    2. fighting_majors: 5.5 → 3.5 (mid-tier; reduces regression-inflation issue
       documented in methodology §7.7 — fights are individually stable so
       regression coefficients overweight them)
    3. hits_thrown: 2.5 → 3.0 (highest YoY repeatability r=0.92 of any GRIT
       event; high-volume role signal worth strengthening)
    4. giveaways_oz: -1.0 → 0.0 (don't penalize OZ possession risk; offensive
       creativity shouldn't carry a structural penalty)

  Pooling change:
    5. F/D -> C/W/D (centers split from wings; D unchanged)
       Recognizes that center responsibilities (DZ faceoffs, two-way play) are
       structurally different from wings, and ranking them in the same pool
       creates apples-to-oranges comparisons.

UNCHANGED from v2.1:
  - HD spatial definitions (12-ft circle for crease goals, slot rectangle for HD
    takeaways and HD blocks)
  - Block subdivision (HD weighted +4.0, non-HD weighted +3.0)
  - Phys minor list (documented six only)
  - PK strength filter (generous SH)
  - Bug fixes for the three inverted columns from v2 PK
  - 0.7 rate / 0.3 volume blend ratio
  - TOI floors

UNCHANGED from v2:
  - Penalties drawn weight (5.5)
  - Physical minors weight (5.5)
  - HD takeaways weight (3.5)
  - DZ faceoff wins weight (2.0)
  - Other takeaways weight (2.0)
  - Hits taken weight (1.5)
  - NZ giveaways weight (-1.5)
  - DZ giveaways weight (-2.5)

NEW in this version:
  - Outputs grit_monthly_v3_{tag}.csv  -- per-player per-month weighted_total,
    approx_toi_min, and raw_grit_per_60. Used by player cards for sparklines.
  - Outputs grit_spatial_v3_{tag}.csv  -- per-player event coordinate list
    (x, y, event_type) for all GRIT-counted spatial events. Used by player
    cards for heatmap SVGs. All-strengths only; giveaways excluded per
    heatmap convention.

Usage:
    python build_v3.py \\
        --pbp-cache /home/user/pbp_cache_2025 \\
        --toi /home/user/toi_data/toi_2025.csv \\
        --output-dir versions/v3/outputs/2025 \\
        --season-tag 2025

    # Playoffs (lower TOI floors, monthly less meaningful so skip it):
    python build_v3.py \\
        --pbp-cache /home/user/pbp_cache_2025_playoffs \\
        --toi /home/user/toi_data/toi_2025_playoffs.csv \\
        --output-dir versions/v3/outputs/2025_playoffs \\
        --season-tag 2025_playoffs \\
        --playoffs --no-monthly
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import pandas as pd


# ============================================================================
# v3 weights and definitions
# ============================================================================

V3_WEIGHTS = {
    "raw_crease_goals":         10.0,   # CHANGED v3: 7.5 -> 10.0 (top tier)
    "raw_penalties_drawn":       5.5,
    "raw_fighting_majors":       3.5,   # CHANGED v3: 5.5 -> 3.5 (mid tier)
    "raw_physical_minors_taken": 5.5,
    "raw_takeaways_high_danger": 3.5,
    "raw_blocked_shots_hd":      4.0,   # v2.1 baseline preserved
    "raw_blocked_shots_non_hd":  3.0,   # v2.1 baseline preserved
    "raw_hits_thrown":           3.0,   # CHANGED v3: 2.5 -> 3.0 (highest YoY r)
    "raw_dz_faceoff_wins":       2.0,
    "raw_takeaways_other":       2.0,
    "raw_hits_taken":            1.5,
    "raw_giveaways_oz":          0.0,   # CHANGED v3: -1.0 -> 0.0
    "raw_giveaways_nz":         -1.5,
    "raw_giveaways_dz":         -2.5,
}

# Strength state codes
EV_5V5 = {"1551"}

# v3 phys minor list: documented six only (no slashing, no high-sticking)
PHYS_MINOR_KEYS = {"roughing", "charging", "boarding", "cross-checking",
                   "elbowing", "interference"}


def is_hd_takeaway(x, y):
    """HD takeaway = slot rectangle |x|>=70 AND |y|<=18."""
    if x is None or y is None:
        return False
    return abs(x) >= 70 and abs(y) <= 18


def is_hd_block(x, y):
    """HD block = slot rectangle |x|>=70 AND |y|<=18."""
    if x is None or y is None:
        return False
    return abs(x) >= 70 and abs(y) <= 18


def is_crease_goal(x, y):
    """Crease goal = within 12-ft Euclidean of net."""
    if x is None or y is None:
        return False
    return ((89 - abs(x))**2 + y**2) <= 144


# ============================================================================
# Strength classification
# ============================================================================

def classify_strength(sc, side, mode):
    """Return True if this event counts under the given mode for this player."""
    if mode == "all_strengths":
        return True
    if not sc or len(sc) != 4 or side is None:
        return False
    if mode == "five_v_five":
        return sc in EV_5V5
    if mode == "pk":
        try:
            a = int(sc[1]); h = int(sc[2])
        except (ValueError, IndexError):
            return False
        if side == "away":
            return a < h
        elif side == "home":
            return h < a
    return False


# ============================================================================
# Event extraction
# ============================================================================

def process_game(data, agg, identity, mode,
                 monthly_agg=None, game_month=None, spatial_agg=None):
    """
    Walk one game's plays, accumulate events.

    monthly_agg: dict keyed by (player_id, "YYYY-MM") -> {"weighted_total": float}
                 Only populated on the all_strengths pass.
    spatial_agg: dict keyed by player_id -> list of (x, y, event_label)
                 All-strengths, no TOI floor, giveaways excluded.
    """
    home_id   = data.get("homeTeam", {}).get("id")
    away_id   = data.get("awayTeam", {}).get("id")
    home_abbr = data.get("homeTeam", {}).get("abbrev")
    away_abbr = data.get("awayTeam", {}).get("abbrev")
    if not home_id or not away_id:
        return

    side = {}
    for spot in data.get("rosterSpots", []):
        pid = spot.get("playerId")
        tid = spot.get("teamId")
        if pid:
            side[pid] = "home" if tid == home_id else "away"
            fn = spot.get("firstName", {}).get("default", "")
            ln = spot.get("lastName", {}).get("default", "")
            identity[pid] = {
                "name": f"{fn} {ln}".strip(),
                "position": spot.get("positionCode", "?"),
                "team_abbr": home_abbr if tid == home_id else away_abbr,
            }

    for p in data.get("plays", []):
        sc = p.get("situationCode")
        ev = p.get("typeDescKey")
        d  = p.get("details", {}) or {}
        x  = d.get("xCoord")
        y  = d.get("yCoord")

        def credit(player_id, field, weight=None):
            if not player_id:
                return
            if classify_strength(sc, side.get(player_id), mode):
                agg[player_id][field] += 1
                if monthly_agg is not None and game_month and weight is not None:
                    monthly_agg[(player_id, game_month)]["weighted_total"] += weight

        def record_spatial(player_id, label):
            """Store normalised (x, y, label) — attacking direction always positive-x."""
            if spatial_agg is None or not player_id:
                return
            if x is None or y is None:
                return
            nx = abs(x)
            ny = y if x >= 0 else -y
            spatial_agg[player_id].append((nx, ny, label))

        if ev == "hit":
            hitter = d.get("hittingPlayerId")
            hittee = d.get("hitteePlayerId")
            credit(hitter, "raw_hits_thrown", weight=V3_WEIGHTS["raw_hits_thrown"])
            credit(hittee, "raw_hits_taken",  weight=V3_WEIGHTS["raw_hits_taken"])
            record_spatial(hitter, "hit_thrown")
            record_spatial(hittee, "hit_taken")

        elif ev == "blocked-shot":
            blocker = d.get("blockingPlayerId")
            credit(blocker, "raw_blocked_shots")  # legacy sum, not separately weighted
            if is_hd_block(x, y):
                credit(blocker, "raw_blocked_shots_hd",     weight=V3_WEIGHTS["raw_blocked_shots_hd"])
                record_spatial(blocker, "block_hd")
            else:
                credit(blocker, "raw_blocked_shots_non_hd", weight=V3_WEIGHTS["raw_blocked_shots_non_hd"])
                record_spatial(blocker, "block_non_hd")

        elif ev == "takeaway":
            taker = d.get("playerId")
            if is_hd_takeaway(x, y):
                credit(taker, "raw_takeaways_high_danger", weight=V3_WEIGHTS["raw_takeaways_high_danger"])
                record_spatial(taker, "takeaway_hd")
            else:
                credit(taker, "raw_takeaways_other", weight=V3_WEIGHTS["raw_takeaways_other"])
                record_spatial(taker, "takeaway_other")

        elif ev == "giveaway":
            # Giveaways excluded from spatial (heatmap convention)
            giver = d.get("playerId")
            zc = d.get("zoneCode")
            if zc == "O":
                credit(giver, "raw_giveaways_oz", weight=V3_WEIGHTS["raw_giveaways_oz"])
            elif zc == "D":
                credit(giver, "raw_giveaways_dz", weight=V3_WEIGHTS["raw_giveaways_dz"])
            elif zc == "N":
                credit(giver, "raw_giveaways_nz", weight=V3_WEIGHTS["raw_giveaways_nz"])

        elif ev == "faceoff":
            if d.get("zoneCode") == "D":
                winner = d.get("winningPlayerId")
                credit(winner, "raw_dz_faceoff_wins", weight=V3_WEIGHTS["raw_dz_faceoff_wins"])
                record_spatial(winner, "dz_faceoff_win")

        elif ev == "penalty":
            committer = d.get("committedByPlayerId")
            drawn_by  = d.get("drawnByPlayerId")
            desc      = (d.get("descKey") or "").lower()
            duration  = d.get("duration", 0)
            is_fight      = desc == "fighting" or duration == 5
            is_phys_minor = duration == 2 and desc in PHYS_MINOR_KEYS
            if is_fight:
                credit(committer, "raw_fighting_majors",      weight=V3_WEIGHTS["raw_fighting_majors"])
            if is_phys_minor:
                credit(committer, "raw_physical_minors_taken", weight=V3_WEIGHTS["raw_physical_minors_taken"])
            if drawn_by and not is_fight:
                credit(drawn_by, "raw_penalties_drawn",       weight=V3_WEIGHTS["raw_penalties_drawn"])

        elif ev == "goal":
            scorer = d.get("scoringPlayerId")
            if scorer and is_crease_goal(x, y):
                credit(scorer, "raw_crease_goals", weight=V3_WEIGHTS["raw_crease_goals"])
                record_spatial(scorer, "crease_goal")


# ============================================================================
# DataFrame builders
# ============================================================================

def zscore(series):
    s  = series.astype(float)
    sd = s.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


V2_1_COLUMNS = [
    "player_id", "name", "position", "team", "games_played", "toi_min",
    "weighted_total", "raw_grit_per_60", "grit_per_game",
    "grit_z_pos", "grit_z_vol", "grit_z_blend",
    "raw_blocked_shots", "raw_blocked_shots_hd", "raw_blocked_shots_non_hd",
    "raw_crease_goals", "raw_dz_faceoff_wins",
    "raw_fighting_majors", "raw_giveaways_dz", "raw_giveaways_nz",
    "raw_giveaways_oz", "raw_hits_taken", "raw_hits_thrown",
    "raw_penalties_drawn", "raw_physical_minors_taken",
    "raw_takeaways_high_danger", "raw_takeaways_other",
]


def build_dataframe(agg, identity, toi_map, gp_map, mode):
    """Build a v3 DataFrame: aggregate events, weight, z-score by C/W/D pool."""
    rows = []
    for pid, events in agg.items():
        ident = identity.get(pid, {})
        toi   = toi_map.get(pid, 0.0)
        if toi <= 0:
            continue
        row = {
            "player_id":   pid,
            "name":        ident.get("name", ""),
            "position":    ident.get("position", "?"),
            "team":        ident.get("team_abbr", ""),
            "games_played": gp_map.get(pid, 0),
            "toi_min":     round(toi, 1),
        }
        for c in V3_WEIGHTS.keys():
            row[c] = events.get(c, 0)
        row["raw_blocked_shots"] = (events.get("raw_blocked_shots_hd", 0)
                                    + events.get("raw_blocked_shots_non_hd", 0))
        rows.append(row)

    df = pd.DataFrame(rows)

    floors = {
        "all_strengths":  600, "five_v_five":   400, "pk":          30,
        "playoffs_all":    25, "playoffs_5v5":   15, "playoffs_pk":   5,
    }
    df = df[df["toi_min"] >= floors.get(mode, 0)].copy()

    df["weighted_total"] = 0.0
    for c, w in V3_WEIGHTS.items():
        if c in df.columns:
            df["weighted_total"] += df[c].fillna(0) * w

    df["raw_grit_per_60"] = df["weighted_total"] / df["toi_min"] * 60.0
    df["grit_per_game"]   = df["weighted_total"] / df["games_played"].replace(0, pd.NA)

    def assign_pool(pos):
        if pos == "D": return "D"
        if pos == "C": return "C"
        return "W"
    df["pool"]        = df["position"].apply(assign_pool)
    df["grit_z_pos"]  = df.groupby("pool")["raw_grit_per_60"].transform(zscore)
    df["grit_z_vol"]  = df.groupby("pool")["grit_per_game"].transform(zscore)
    df["grit_z_blend"] = 0.7 * df["grit_z_pos"] + 0.3 * df["grit_z_vol"]

    return df[V2_1_COLUMNS]


def build_monthly(monthly_agg, identity, toi_df):
    """
    Build per-player per-month summary for sparklines.

    Monthly TOI isn't in the PBP cache, so we approximate it by prorating
    season TOI by each month's share of the season weighted_total.
    Shape of the sparkline is accurate; absolute per-60 values are approximate.

    Output columns:
        player_id, name, position, team, month, weighted_total,
        approx_toi_min, raw_grit_per_60
    """
    season_wt = defaultdict(float)
    for (pid, month), vals in monthly_agg.items():
        season_wt[pid] += vals["weighted_total"]

    toi_total = dict(zip(toi_df["player_id"], toi_df["total_toi_min"]))

    rows = []
    for (pid, month), vals in monthly_agg.items():
        wt           = vals["weighted_total"]
        season_total = season_wt.get(pid, 0)
        toi_season   = toi_total.get(pid, 0)
        if season_total > 0 and toi_season > 0:
            approx_toi = toi_season * (wt / season_total)
        else:
            approx_toi = 0.0
        per60 = (wt / approx_toi * 60.0) if approx_toi > 0 else 0.0
        ident = identity.get(pid, {})
        rows.append({
            "player_id":      pid,
            "name":           ident.get("name", ""),
            "position":       ident.get("position", "?"),
            "team":           ident.get("team_abbr", ""),
            "month":          month,
            "weighted_total": round(wt, 2),
            "approx_toi_min": round(approx_toi, 1),
            "raw_grit_per_60": round(per60, 4),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["player_id", "month"]).reset_index(drop=True)


def build_spatial(spatial_agg, identity):
    """
    Build per-player event coordinate list for heatmaps.
    Coordinates are normalised so the attacking direction is always positive-x.

    Output columns:
        player_id, name, position, team, x, y, event_type
    """
    rows = []
    for pid, events in spatial_agg.items():
        ident = identity.get(pid, {})
        for (x, y, label) in events:
            rows.append({
                "player_id": pid,
                "name":      ident.get("name", ""),
                "position":  ident.get("position", "?"),
                "team":      ident.get("team_abbr", ""),
                "x":         x,
                "y":         y,
                "event_type": label,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["player_id", "event_type"]).reset_index(drop=True)


def game_date_from_file(fn, data):
    """
    Try to extract YYYY-MM from a game cache file.
    Checks filename first (YYYY-MM-DD prefix), then JSON gameDate / startTimeUTC.
    Returns None if neither works.
    """
    stem = Path(fn).stem
    for part in stem.replace("_", "-").split("-"):
        pass  # just parse below
    # Check for ISO date in filename: YYYY-MM-DD anywhere
    import re
    m = re.search(r'(\d{4})-(\d{2})-\d{2}', stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    # Fall back to JSON fields
    for field in ("gameDate", "startTimeUTC", "easternUTCOffset"):
        val = data.get(field, "")
        if val and len(val) >= 7 and val[4] == "-":
            return val[:7]
    return None


# ============================================================================
# Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbp-cache",   required=True,
                    help="Directory of per-game JSON files")
    ap.add_argument("--toi",         required=True,
                    help="CSV: player_id, total_toi_min, ev_toi_min, sh_toi_min, games_played")
    ap.add_argument("--output-dir",  required=True)
    ap.add_argument("--season-tag",  required=True,
                    help="e.g. 2025 or 2025_playoffs")
    ap.add_argument("--playoffs",    action="store_true",
                    help="Use playoff TOI floors")
    ap.add_argument("--no-monthly",  action="store_true",
                    help="Skip monthly output")
    ap.add_argument("--no-spatial",  action="store_true",
                    help="Skip spatial output")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(os.listdir(args.pbp_cache))
    print(f"\nReading {len(files)} game files from {args.pbp_cache}")

    agg_all = defaultdict(lambda: defaultdict(int))
    agg_5v5 = defaultdict(lambda: defaultdict(int))
    agg_pk  = defaultdict(lambda: defaultdict(int))
    identity = {}

    monthly_agg = defaultdict(lambda: {"weighted_total": 0.0}) if not args.no_monthly else None
    spatial_agg = defaultdict(list) if not args.no_spatial else None

    for fn in files:
        fpath = os.path.join(args.pbp_cache, fn)
        with open(fpath) as f:
            data = json.load(f)

        game_month = game_date_from_file(fn, data) if not args.no_monthly else None

        process_game(data, agg_all, identity, "all_strengths",
                     monthly_agg=monthly_agg, game_month=game_month,
                     spatial_agg=spatial_agg)
        process_game(data, agg_5v5, identity, "five_v_five")
        process_game(data, agg_pk,  identity, "pk")

    toi_df    = pd.read_csv(args.toi)
    toi_total = dict(zip(toi_df["player_id"], toi_df["total_toi_min"]))
    toi_5v5   = dict(zip(toi_df["player_id"], toi_df["ev_toi_min"]))
    toi_pk    = dict(zip(toi_df["player_id"], toi_df["sh_toi_min"]))
    gp        = dict(zip(toi_df["player_id"], toi_df["games_played"]))

    if args.playoffs:
        modes = {"all_strengths": "playoffs_all", "five_v_five": "playoffs_5v5", "pk": "playoffs_pk"}
    else:
        modes = {"all_strengths": "all_strengths", "five_v_five": "five_v_five", "pk": "pk"}

    print(f"\nBuilding all-strengths file...")
    df_all = build_dataframe(agg_all, identity, toi_total, gp, modes["all_strengths"])
    out_all = out_dir / f"grit_per_60_v3_{args.season_tag}.csv"
    df_all.to_csv(out_all, index=False)
    print(f"  Wrote {len(df_all)} rows to {out_all}")

    print(f"\nBuilding 5v5 file...")
    df_5v5 = build_dataframe(agg_5v5, identity, toi_5v5, gp, modes["five_v_five"])
    out_5v5 = out_dir / f"grit_5v5_v3_{args.season_tag}.csv"
    df_5v5.to_csv(out_5v5, index=False)
    print(f"  Wrote {len(df_5v5)} rows to {out_5v5}")

    print(f"\nBuilding PK file...")
    df_pk = build_dataframe(agg_pk, identity, toi_pk, gp, modes["pk"])
    out_pk = out_dir / f"grit_pk_v3_{args.season_tag}.csv"
    df_pk.to_csv(out_pk, index=False)
    print(f"  Wrote {len(df_pk)} rows to {out_pk}")

    if not args.no_monthly:
        print(f"\nBuilding monthly file...")
        df_monthly = build_monthly(monthly_agg, identity, toi_df)
        out_monthly = out_dir / f"grit_monthly_v3_{args.season_tag}.csv"
        df_monthly.to_csv(out_monthly, index=False)
        print(f"  Wrote {len(df_monthly)} rows to {out_monthly}")

    if not args.no_spatial:
        print(f"\nBuilding spatial file...")
        df_spatial = build_spatial(spatial_agg, identity)
        out_spatial = out_dir / f"grit_spatial_v3_{args.season_tag}.csv"
        df_spatial.to_csv(out_spatial, index=False)
        print(f"  Wrote {len(df_spatial)} rows to {out_spatial}")

    print(f"\nDone. Outputs in: {out_dir}")


if __name__ == "__main__":
    main()
