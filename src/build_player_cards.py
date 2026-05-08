#!/usr/bin/env python3
"""
build_player_cards.py — generate player_cards_v3.html and its sidecar JSON
from SQL (preferred) or v3 CSVs (fallback).

Mirrors the conventions of build_v3.py:
  - SQL Server first, with --no-sql for CSV fallback
  - argparse for season tag / output dir
  - Reads from the same GRIT database build_v3.py writes to

Outputs (two files):
  1. player_cards_v3.html       — thin shell, ~50 KB. Includes the styles, the
                                  card render JS, and a small inline manifest
                                  (header fields only) so filter/sort/initial
                                  paint work without waiting on the fetch.
  2. player_cards_v3_data.json  — sidecar, ~600 KB. Per-player pos_events,
                                  neg_events, pre-binned spatial triples, and
                                  monthly trend points. Fetched once on page
                                  load; cards pull from it lazily.

Why split: the previous single-file player_cards_v3.html was 1.18 MB because
the entire data payload (including raw spatial coordinates) was embedded in a
1.16 MB inline <script>. That bloated context costs in any session that
referenced the file. The split keeps the *visual* output identical but moves
the heavy data outside the HTML, where it doesn't cost anything when the
HTML is read for inspection.

Usage:
    # From SQL (default):
    python build_player_cards.py --season 2025 --output-dir viz/

    # From CSVs (fallback if SQL is offline):
    python build_player_cards.py --season 2025 --output-dir viz/ --no-sql \
        --data-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3\\data"

The "season" argument follows build_v3.py's start-year convention:
  2025 = 2024-25 season (regular season + 2025 playoffs joined automatically)
  2026 = 2025-26 season (etc.)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd


# ============================================================================
# SQL connection (mirrors build_v3.py)
# ============================================================================

SQL_SERVER   = "localhost"
SQL_DATABASE = "GRIT"
SQL_DRIVER   = "ODBC Driver 17 for SQL Server"


def get_sql_engine():
    from sqlalchemy import create_engine
    conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/{SQL_DATABASE}"
        f"?driver={SQL_DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
        f"&TrustServerCertificate=yes"
    )
    return create_engine(conn_str, fast_executemany=True)


# ============================================================================
# Event labels and weights — must match build_v3.py V3_WEIGHTS
# ============================================================================

# Display order matches the existing card layout (positives first, by weight).
# Labels match what the existing player_cards_v3.html shows.
POS_EVENTS = [
    ("Crease goals",     "raw_crease_goals",         10.0),
    ("Penalties drawn",  "raw_penalties_drawn",       5.5),
    ("Phys minors taken","raw_physical_minors_taken", 5.5),
    ("HD blocks",        "raw_blocked_shots_hd",      4.0),
    ("HD takeaways",     "raw_takeaways_high_danger", 3.5),
    ("Fights",           "raw_fighting_majors",       3.5),
    ("Hits thrown",      "raw_hits_thrown",           3.0),
    ("Non-HD blocks",    "raw_blocked_shots_non_hd",  3.0),
    ("DZ faceoff wins",  "raw_dz_faceoff_wins",       2.0),
    ("Other takeaways",  "raw_takeaways_other",       2.0),
    ("Hits taken",       "raw_hits_taken",            1.5),
    ("Close shots",      "raw_close_shots",           1.5),   # NEW v3.1
]

# Negative events (anti-grit table). OZ giveaways excluded — weight is 0.0 in v3.
NEG_EVENTS = [
    ("DZ giveaways", "raw_giveaways_dz", -2.5),
    ("NZ giveaways", "raw_giveaways_nz", -1.5),
]


# ============================================================================
# Spatial pre-binning
# ============================================================================
#
# The card renderer expects an array of [gx, gy, count] triples, where:
#   - gx is an integer 0..39 indicating column (full rink, 40 columns, 5ft each)
#   - gy is an integer 0..16 indicating row (17 rows top-to-bottom)
#   - count is the number of events that landed in that cell
#
# build_v3.py normalises x so the attacking direction is positive. So:
#   - gx 0..19  = defensive zone (player's own half)
#   - gx 20..39 = offensive zone
# y is in NHL coordinates (-42.5 to +42.5).
#
# 40 cols × 17 rows = 680 cells. At 5ft × 5ft, this is the same resolution as
# HockeyViz / MoneyPuck heatmaps.

SPATIAL_X_HALF = 100.0  # rink runs -100..+100 in NHL coordinates
SPATIAL_Y_HALF = 42.5
N_COLS = 40   # full-rink width: 5 ft per column, 20 cols per zone half
N_ROWS = 17


def bin_spatial(rows):
    """
    rows: iterable of (x, y) pairs in NHL coordinates after attacking-direction
          normalization in build_v3.py. After the home/away fix:
            x < 0 = defensive zone for that player
            x > 0 = offensive zone for that player
    Returns: list of [gx, gy, count] for cells with count > 0.

    gx ranges 0..N_COLS-1 across the full rink (-100..+100).
    gy ranges 0..N_ROWS-1 across full y (-42.5..+42.5).
    """
    counts = {}
    for x, y in rows:
        if x is None or y is None:
            continue
        # Map x in [-100, 100] to [0, N_COLS-1]
        gx = int(min(N_COLS - 1, max(0, (x + SPATIAL_X_HALF) / (2 * SPATIAL_X_HALF) * N_COLS)))
        # Map y in [-42.5, 42.5] to [0, N_ROWS-1]
        gy = int(min(N_ROWS - 1, max(0, (y + SPATIAL_Y_HALF) / (2 * SPATIAL_Y_HALF) * N_ROWS)))
        key = (gx, gy)
        counts[key] = counts.get(key, 0) + 1
    return [[gx, gy, c] for (gx, gy), c in counts.items()]


# ============================================================================
# Data loaders — SQL and CSV both produce the same DataFrames
# ============================================================================

def load_from_sql(engine, season):
    """Load all the frames we need for one season from SQL."""
    from sqlalchemy import text

    print(f"Loading data from SQL for season {season}...")

    # grit_scores — three rows per player (all / 5v5 / pk) for regular season,
    # plus one row at strength='all' for playoffs.
    #
    # Note: build_v3.py writes name/position/team into grit_scores along with the
    # raw event columns. We pull from grit_scores only — joining to `players`
    # would duplicate name/position/team and break downstream pandas operations.
    df_scores = pd.read_sql(
        text("""
            SELECT *
            FROM grit_scores
            WHERE season = :season
        """),
        engine, params={"season": season},
    )
    print(f"  grit_scores: {len(df_scores)} rows")

    # Defensive: if any duplicate column names slipped in, keep first occurrence
    df_scores = df_scores.loc[:, ~df_scores.columns.duplicated()]

    df_monthly = pd.read_sql(
        text("""
            SELECT player_id, month, raw_grit_per_game
            FROM grit_monthly
            WHERE season = :season AND is_playoffs = 0
            ORDER BY player_id, month
        """),
        engine, params={"season": season},
    )
    print(f"  grit_monthly: {len(df_monthly)} rows")

    df_spatial = pd.read_sql(
        text("""
            SELECT player_id, x, y
            FROM grit_spatial
            WHERE season = :season AND is_playoffs = 0
        """),
        engine, params={"season": season},
    )
    print(f"  grit_spatial: {len(df_spatial)} events")

    return df_scores, df_monthly, df_spatial


def load_from_csv(data_dir, season):
    """Load the same frames from the v3 CSVs as a fallback."""
    print(f"Loading data from CSVs in {data_dir} for season {season}...")

    season_dir = Path(data_dir) / str(season)
    playoffs_dir = Path(data_dir) / f"{season}_playoffs"

    # Reg-season per_60, 5v5, pk
    f_all  = season_dir / f"grit_per_60_v3_{season}.csv"
    f_5v5  = season_dir / f"grit_5v5_v3_{season}.csv"
    f_pk   = season_dir / f"grit_pk_v3_{season}.csv"
    f_po   = playoffs_dir / f"grit_per_60_v3_{season}_playoffs.csv"
    f_mon  = season_dir / f"grit_monthly_v3_{season}.csv"
    f_spat = season_dir / f"grit_spatial_v3_{season}.csv"

    # Fall back to flat layout if season-subdir doesn't exist (project layout)
    if not f_all.exists():
        flat = Path(data_dir)
        f_all  = flat / f"grit_per_60_v3_{season}.csv"
        f_5v5  = flat / f"grit_5v5_v3_{season}.csv"
        f_pk   = flat / f"grit_pk_v3_{season}.csv"
        f_po   = flat / f"grit_per_60_v3_{season}_playoffs.csv"
        f_mon  = flat / f"grit_monthly_v3_{season}.csv"
        f_spat = flat / f"grit_spatial_v3_{season}.csv"

    def _read(p, strength=None):
        if not p.exists():
            print(f"  MISSING: {p.name}")
            return pd.DataFrame()
        df = pd.read_csv(p)
        if strength is not None:
            df["strength"] = strength
            df["is_playoffs"] = 0
        df["season"] = season
        return df

    df_all = _read(f_all,  "all")
    df_5v5 = _read(f_5v5,  "5v5")
    df_pk  = _read(f_pk,   "pk")
    df_po  = _read(f_po,   "all")
    if not df_po.empty:
        df_po["is_playoffs"] = 1

    # Concatenate to mimic the SQL grit_scores shape
    df_scores = pd.concat([df_all, df_5v5, df_pk, df_po], ignore_index=True)
    print(f"  grit_scores: {len(df_scores)} rows")

    df_monthly = _read(f_mon)
    if not df_monthly.empty:
        df_monthly = df_monthly[["player_id", "month", "raw_grit_per_game"]]
    print(f"  grit_monthly: {len(df_monthly)} rows")

    df_spatial = _read(f_spat)
    if not df_spatial.empty:
        df_spatial = df_spatial[["player_id", "x", "y"]]
    print(f"  grit_spatial: {len(df_spatial)} events")

    return df_scores, df_monthly, df_spatial


# ============================================================================
# Card data assembly
# ============================================================================

def assign_pool(pos):
    if pos == "D":
        return "D"
    if pos == "C":
        return "C"
    return "W"  # L, R, F


def build_player_records(df_scores, df_monthly, df_spatial):
    """Produce two parallel structures — manifest (small) and details (large)."""

    # Split scores by strength + is_playoffs
    scores_all = df_scores[(df_scores["strength"] == "all") & (df_scores["is_playoffs"] == 0)].copy()
    scores_5v5 = df_scores[(df_scores["strength"] == "5v5") & (df_scores["is_playoffs"] == 0)].copy()
    scores_pk  = df_scores[(df_scores["strength"] == "pk")  & (df_scores["is_playoffs"] == 0)].copy()
    scores_po  = df_scores[(df_scores["strength"] == "all") & (df_scores["is_playoffs"] == 1)].copy()

    # Index helpers
    by_pid_5v5 = scores_5v5.set_index("player_id")
    by_pid_pk  = scores_pk.set_index("player_id")
    by_pid_po  = scores_po.set_index("player_id")

    # League rank for the all-strengths blend
    scores_all = scores_all.sort_values("grit_z_blend", ascending=False).reset_index(drop=True)
    scores_all["rk_lg"] = scores_all.index + 1

    # Per-pool ranks
    scores_all["pool"] = scores_all["position"].map(assign_pool)
    pool_sizes = scores_all.groupby("pool").size().to_dict()
    scores_all["rk_pos"] = (
        scores_all.groupby("pool")["grit_z_blend"]
        .rank(ascending=False, method="min").astype(int)
    )
    scores_all["rk_pos_total"] = scores_all["pool"].map(pool_sizes)
    scores_all["pctile_pos"] = (
        100.0 * (scores_all["rk_pos_total"] - scores_all["rk_pos"] + 1)
        / scores_all["rk_pos_total"]
    ).round().astype(int)

    # Monthly: pivot to per-player list of {m, v}
    monthly_by_pid = {}
    if not df_monthly.empty:
        for pid, grp in df_monthly.sort_values("month").groupby("player_id"):
            monthly_by_pid[int(pid)] = [
                {"m": str(m), "v": float(round(v, 3))}
                for m, v in zip(grp["month"], grp["raw_grit_per_game"])
                if pd.notna(v)
            ]

    # Spatial: bin per player
    spatial_by_pid = {}
    if not df_spatial.empty:
        for pid, grp in df_spatial.groupby("player_id"):
            binned = bin_spatial(zip(grp["x"], grp["y"]))
            if binned:
                spatial_by_pid[int(pid)] = binned

    manifest = []   # what the HTML embeds inline
    details  = {}   # what the sidecar JSON holds, keyed by player_id (string)

    for _, row in scores_all.iterrows():
        pid  = int(row["player_id"])
        pos  = row["position"] if pd.notna(row["position"]) else "?"
        pool = row["pool"]

        # Header / manifest fields
        atoi = (row["toi_min"] / row["games_played"]) if row["games_played"] else 0.0

        manifest.append({
            "player_id":    pid,
            "name":         row["name"] if pd.notna(row["name"]) else "",
            "pos":          pos,
            "pool":         pool,
            "team":         row["team"] if pd.notna(row["team"]) else "",
            "gp":           int(row["games_played"]),
            "atoi":         round(float(atoi), 1),
            "gritz":        round(float(row["grit_z_blend"]), 4),
            "rk_lg":        int(row["rk_lg"]),
            "rk_pos":       int(row["rk_pos"]),
            "rk_pos_total": int(row["rk_pos_total"]),
            "pctile_pos":   int(row["pctile_pos"]),
        })

        # Detail fields — events, splits, playoffs, monthly, spatial
        pos_events = []
        for label, col, weight in POS_EVENTS:
            v = int(row.get(col, 0) or 0)
            if v:
                pos_events.append({"l": label, "v": v, "w": round(v * weight, 1)})
        # Sort by absolute contribution descending — matches existing card visual
        pos_events.sort(key=lambda e: -e["w"])

        neg_events = []
        for label, col, weight in NEG_EVENTS:
            v = int(row.get(col, 0) or 0)
            if v:
                neg_events.append({"l": label, "v": v, "w": round(v * weight, 1)})
        neg_events.sort(key=lambda e: e["w"])  # most negative first

        # 5v5 / PK splits
        z_5v5  = float(by_pid_5v5.loc[pid, "grit_z_blend"]) if pid in by_pid_5v5.index else None
        toi_5v5 = float(by_pid_5v5.loc[pid, "toi_min"])     if pid in by_pid_5v5.index else 0.0
        z_pk   = float(by_pid_pk.loc[pid,  "grit_z_blend"]) if pid in by_pid_pk.index  else None
        toi_pk  = float(by_pid_pk.loc[pid,  "toi_min"])     if pid in by_pid_pk.index  else 0.0

        # Playoffs
        if pid in by_pid_po.index:
            po_z   = float(by_pid_po.loc[pid, "grit_z_blend"])
            po_gp  = int(by_pid_po.loc[pid, "games_played"])
            po_toi = float(by_pid_po.loc[pid, "toi_min"])
        else:
            po_z = None
            po_gp = 0
            po_toi = 0.0

        details[str(pid)] = {
            "pos_events": pos_events,
            "neg_events": neg_events,
            "z_5v5":  None if z_5v5  is None else round(z_5v5, 4),
            "toi_5v5": round(toi_5v5, 1),
            "z_pk":   None if z_pk   is None else round(z_pk, 4),
            "toi_pk":  round(toi_pk, 1),
            "po_z":   None if po_z is None else round(po_z, 4),
            "po_gp":  po_gp,
            "po_toi": round(po_toi, 1),
            "monthly": monthly_by_pid.get(pid, []),
            "spatial": spatial_by_pid.get(pid, []),
        }

    return manifest, details


# ============================================================================
# HTML emission
# ============================================================================

# Distinct teams for the dropdown — derived from manifest at build time so
# this never goes stale (e.g. UTA after relocation).
def teams_from_manifest(manifest):
    return sorted({p["team"] for p in manifest if p["team"]})


def render_html(manifest, season_label, sidecar_filename):
    """
    Render the thin shell. Stylesheet and card-build JS are identical to the
    legacy player_cards_v3.html (visually). The differences are:
      - PLAYERS array contains only the manifest (no pos_events/spatial/monthly)
      - on DOMContentLoaded we fetch sidecar JSON, then merge each player's
        details into its manifest record before render() runs.
    """
    teams = teams_from_manifest(manifest)
    team_options = "".join(f'<option value="{t}">{t}</option>' for t in teams)
    manifest_json = json.dumps(manifest, separators=(",", ":"))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GRIT v3 Player Cards · {season_label}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;}}
body{{margin:0;padding:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;}}
header{{position:sticky;top:0;z-index:20;background:#0d1117;border-bottom:1px solid #21262d;padding:10px 14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;}}
header h1{{font-size:18px;font-weight:700;margin:0;color:#cadcfc;letter-spacing:1px;}}
.meta{{color:#8b949e;font-size:12px;margin-left:2px;}}
.v3badge{{background:#f9a03f;color:#0d1117;font-size:10px;font-weight:700;padding:2px 6px;border-radius:3px;letter-spacing:1px;}}
header input,header select{{background:#161b22;color:#e6edf3;border:1px solid #30363d;padding:6px 10px;border-radius:4px;font-size:13px;font-family:inherit;}}
header input{{flex:1 1 140px;}}
header select{{flex:0 1 auto;}}
header input:focus,header select:focus{{outline:1px solid #f9a03f;}}
.count{{color:#8b949e;font-size:12px;margin-left:auto;}}
.loading{{padding:40px 20px;text-align:center;color:#8b949e;font-size:13px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px;padding:14px;}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:8px;overflow:hidden;}}
.card-header{{padding:14px 16px 12px;border-bottom:1px solid #21262d;display:flex;gap:10px;align-items:flex-start;}}
.card-rank{{background:#0d1117;color:#f9a03f;font-weight:700;font-size:13px;padding:4px 8px;border-radius:4px;border:1px solid #21262d;min-width:36px;text-align:center;flex-shrink:0;}}
.card-name{{font-size:17px;font-weight:700;line-height:1.2;margin-bottom:2px;}}
.card-meta{{color:#8b949e;font-size:11px;}}
.card-z{{margin-left:auto;text-align:right;flex-shrink:0;}}
.card-z .num{{font-family:'Impact','Arial Black',sans-serif;font-size:26px;line-height:1;}}
.card-z .num.pos{{color:#f9a03f;}}
.card-z .num.neg{{color:#8b949e;}}
.card-z .lbl{{font-size:9px;color:#8b949e;letter-spacing:1px;margin-top:2px;}}
.card-z .pctile{{font-size:9px;color:#f9a03f;margin-top:2px;font-weight:600;}}
.card-body{{padding:12px 14px;}}
.section-label{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#f9a03f;margin:0 0 5px 0;}}
.events-table{{width:100%;border-collapse:collapse;font-size:11px;margin-bottom:8px;}}
.events-table td{{padding:2px 0;color:#8b949e;}}
.events-table td.ev{{color:#cadcfc;}}
.events-table td.num{{text-align:right;font-variant-numeric:tabular-nums;color:#e6edf3;font-weight:600;}}
.events-table td.wt{{text-align:right;font-size:10px;color:#8b949e;width:38px;}}
.events-table tr.neg td{{color:#555;}}
.events-table tr.neg td.num{{color:#777;}}
.splits{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0;}}
.split{{background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:6px 8px;}}
.split .lbl{{color:#8b949e;text-transform:uppercase;letter-spacing:1px;font-size:9px;}}
.split .v{{font-weight:700;font-size:13px;margin-top:1px;}}
.split .v.pos{{color:#f9a03f;}}
.split .v.neg{{color:#58a6ff;}}
.split .t{{color:#8b949e;font-size:9px;margin-top:1px;}}
.po-strip{{margin:8px 0;padding:7px 10px;background:#0d1117;border:1px solid rgba(249,160,63,0.3);border-radius:4px;display:flex;align-items:center;gap:10px;}}
.po-strip .po-lbl{{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#f9a03f;font-weight:700;}}
.po-strip .po-z{{font-family:'Impact','Arial Black',sans-serif;font-size:18px;}}
.po-strip .po-z.pos{{color:#f9a03f;}}
.po-strip .po-z.neg{{color:#58a6ff;}}
.po-strip .po-info{{margin-left:auto;text-align:right;font-size:10px;color:#8b949e;}}
.sparkline-wrap{{margin:8px 0;}}
.sparkline-wrap svg{{display:block;width:100%;height:44px;}}
.heatmap-wrap{{margin:8px 0;}}
.heatmap-wrap svg{{display:block;width:100%;border-radius:4px;}}
</style>
</head>
<body>
<header>
  <h1>GRIT</h1>
  <span class="v3badge">v3</span>
  <span class="meta">player cards · {season_label}</span>
  <input id="search" type="text" placeholder="Search name..." autocomplete="off">
  <select id="team-filter">
    <option value="">All teams</option>
    {team_options}
  </select>
  <select id="pos-filter">
    <option value="">All positions</option>
    <option value="C">C</option>
    <option value="W">W (L/R)</option>
    <option value="D">D</option>
  </select>
  <select id="sort">
    <option value="grit-desc">GRIT-Z ↓</option>
    <option value="grit-asc">GRIT-Z ↑</option>
    <option value="name">Name</option>
    <option value="team">Team</option>
  </select>
  <span class="count" id="count"></span>
</header>
<div id="status" class="loading">Loading player details…</div>
<div class="grid" id="grid"></div>

<script>
// ----------------------------------------------------------------------------
// Inline manifest — small, ~120 KB. Provides headers for instant filter/sort.
// Detail data (events, splits, playoffs, monthly, spatial) loads from sidecar.
// ----------------------------------------------------------------------------
const PLAYERS = {manifest_json};
const SIDECAR = "{sidecar_filename}";

function esc(s){{return String(s).replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));}}
function ord(n){{const v=n%100;if(v>=11&&v<=13)return"th";switch(n%10){{case 1:return"st";case 2:return"nd";case 3:return"rd";default:return"th";}}}}

function heatColor(t){{
  let r,g,b,a;
  if(t<0.5){{const s=t/0.5;r=Math.round(74+s*(255-74));g=Math.round(144+s*(255-144));b=Math.round(217+s*(255-217));}}
  else {{const s=(t-0.5)/0.5;r=255;g=Math.round(255-s*(255-74));b=Math.round(255-s*(255-74));}}
  a=(0.15+t*0.85).toFixed(2);
  return `rgba(${{r}},${{g}},${{b}},${{a}})`;
}}

function buildHeatmap(spatial){{
  if(!spatial||!spatial.length) return "";
  // Rink is 200ft x 85ft. SVG is 400 x 170 (10 SVG units per ft horizontally,
  // ~2 per ft vertically — close enough; visual aspect ratio is correct).
  const W=400, H=170;
  const N_COLS=40, N_ROWS=17;
  const CW=W/N_COLS, CH=H/N_ROWS;
  const maxVal=Math.max(...spatial.map(d=>d[2]));
  if(!maxVal) return "";

  // NHL coordinate -> SVG coordinate helpers (rink runs -100..+100, -42.5..+42.5)
  const sx = nx => (nx + 100) * (W / 200);
  const sy = ny => (ny + 42.5) * (H / 85);

  // Lines
  const goalLineL = sx(-89), goalLineR = sx(89);
  const blueLeft  = sx(-25), blueRight = sx(25);
  const centerX   = sx(0);

  // Faceoff dots (NHL coords)
  // End zones: (±69, ±22). Neutral zone: (±20, ±22). Center: (0, 0).
  const dot = (xN, yN, c="#e8474a") =>
    `<circle cx="${{sx(xN).toFixed(1)}}" cy="${{sy(yN).toFixed(1)}}" r="2.5" fill="${{c}}"/>`;
  const endZoneCircle = (xN, yN) =>
    // 15ft radius circle around end-zone faceoff dots
    `<circle cx="${{sx(xN).toFixed(1)}}" cy="${{sy(yN).toFixed(1)}}" r="${{(15*W/200).toFixed(1)}}" fill="none" stroke="#e8474a" stroke-width="1"/>`;
  const centerCircle =
    // 15ft radius circle around center ice (with blue stroke per NHL standard)
    `<circle cx="${{centerX.toFixed(1)}}" cy="${{(H/2).toFixed(1)}}" r="${{(15*W/200).toFixed(1)}}" fill="none" stroke="#4a90d9" stroke-width="1"/>`;

  // Goal creases — semicircle facing inward from each goal line (6ft radius)
  const creaseR = (6 * W / 200);
  const creaseL = `<path d="M ${{goalLineL.toFixed(1)}},${{(H/2-creaseR).toFixed(1)}} A ${{creaseR.toFixed(1)}},${{creaseR.toFixed(1)}} 0 0,1 ${{goalLineL.toFixed(1)}},${{(H/2+creaseR).toFixed(1)}}" fill="#aac8e8" fill-opacity="0.4" stroke="#e8474a" stroke-width="0.8"/>`;
  const creaseR_ = `<path d="M ${{goalLineR.toFixed(1)}},${{(H/2-creaseR).toFixed(1)}} A ${{creaseR.toFixed(1)}},${{creaseR.toFixed(1)}} 0 0,0 ${{goalLineR.toFixed(1)}},${{(H/2+creaseR).toFixed(1)}}" fill="#aac8e8" fill-opacity="0.4" stroke="#e8474a" stroke-width="0.8"/>`;

  // Heatmap cells — gx 0..39 spans -100..+100 in x, gy 0..16 spans -42.5..+42.5 in y
  const cells=spatial.map(([gx,gy,cnt])=>{{
    const t=cnt/maxVal;
    const x=(gx*CW).toFixed(1);
    const y=(gy*CH).toFixed(1);
    return `<rect x="${{x}}" y="${{y}}" width="${{CW.toFixed(1)}}" height="${{CH.toFixed(1)}}" fill="${{heatColor(t)}}"/>`;
  }}).join("");

  const cornerR = (28 * W / 200);  // ~28ft corner radius

  return `<div class="heatmap-wrap">
  <p class="section-label">Event Heatmap · DZ ← → OZ</p>
  <svg viewBox="0 0 ${{W}} ${{H}}" xmlns="http://www.w3.org/2000/svg" style="width:100%;border-radius:4px;">
    <rect x="1" y="1" width="${{W-2}}" height="${{H-2}}" rx="${{cornerR.toFixed(1)}}" ry="${{cornerR.toFixed(1)}}" fill="white" stroke="#c8d8e8" stroke-width="1.5"/>
    <clipPath id="rc"><rect x="1" y="1" width="${{W-2}}" height="${{H-2}}" rx="${{cornerR.toFixed(1)}}" ry="${{cornerR.toFixed(1)}}"/></clipPath>
    <g clip-path="url(#rc)">${{cells}}</g>
    <!-- Center red line -->
    <line x1="${{centerX.toFixed(1)}}" y1="1" x2="${{centerX.toFixed(1)}}" y2="${{H-1}}" stroke="#e8474a" stroke-width="2" clip-path="url(#rc)"/>
    <!-- Blue lines -->
    <line x1="${{blueLeft.toFixed(1)}}" y1="1" x2="${{blueLeft.toFixed(1)}}" y2="${{H-1}}" stroke="#4a90d9" stroke-width="2.5" clip-path="url(#rc)"/>
    <line x1="${{blueRight.toFixed(1)}}" y1="1" x2="${{blueRight.toFixed(1)}}" y2="${{H-1}}" stroke="#4a90d9" stroke-width="2.5" clip-path="url(#rc)"/>
    <!-- Goal lines -->
    <line x1="${{goalLineL.toFixed(1)}}" y1="${{(cornerR/2).toFixed(1)}}" x2="${{goalLineL.toFixed(1)}}" y2="${{(H-cornerR/2).toFixed(1)}}" stroke="#e8474a" stroke-width="1" clip-path="url(#rc)"/>
    <line x1="${{goalLineR.toFixed(1)}}" y1="${{(cornerR/2).toFixed(1)}}" x2="${{goalLineR.toFixed(1)}}" y2="${{(H-cornerR/2).toFixed(1)}}" stroke="#e8474a" stroke-width="1" clip-path="url(#rc)"/>
    <!-- Goal creases -->
    ${{creaseL}}
    ${{creaseR_}}
    <!-- End-zone faceoff circles + dots -->
    ${{endZoneCircle(-69,-22)}}
    ${{endZoneCircle(-69, 22)}}
    ${{endZoneCircle( 69,-22)}}
    ${{endZoneCircle( 69, 22)}}
    ${{dot(-69,-22)}}
    ${{dot(-69, 22)}}
    ${{dot( 69,-22)}}
    ${{dot( 69, 22)}}
    <!-- Neutral-zone faceoff dots -->
    ${{dot(-20,-22)}}
    ${{dot(-20, 22)}}
    ${{dot( 20,-22)}}
    ${{dot( 20, 22)}}
    <!-- Center circle + center dot -->
    ${{centerCircle}}
    <circle cx="${{centerX.toFixed(1)}}" cy="${{(H/2).toFixed(1)}}" r="2" fill="#4a90d9"/>
    <!-- Outline on top to mask cells past corner radius -->
    <rect x="1" y="1" width="${{W-2}}" height="${{H-2}}" rx="${{cornerR.toFixed(1)}}" ry="${{cornerR.toFixed(1)}}" fill="none" stroke="#c8d8e8" stroke-width="1.5"/>
  </svg></div>`;
}}

function buildSparkline(monthly){{
  if(!monthly||monthly.length<2) return "";
  const vals=monthly.map(m=>m.v);
  const mn=Math.min(...vals), mx=Math.max(...vals), range=mx-mn||1;
  const W=300,H=44,PAD=3;
  const pts=vals.map((v,i)=>{{
    const x=PAD+(i/(vals.length-1))*(W-PAD*2);
    const y=H-PAD-((v-mn)/range)*(H-PAD*2);
    return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
  }});
  const avg=vals.reduce((a,b)=>a+b,0)/vals.length;
  const ay=(H-PAD-((avg-mn)/range)*(H-PAD*2)).toFixed(1);
  const dots=vals.map((v,i)=>{{
    const x=PAD+(i/(vals.length-1))*(W-PAD*2);
    const y=H-PAD-((v-mn)/range)*(H-PAD*2);
    return `<circle cx="${{x.toFixed(1)}}" cy="${{y.toFixed(1)}}" r="2.5" fill="#f9a03f"/>`;
  }}).join("");
  return `<div class="sparkline-wrap">
  <p class="section-label">Monthly Grit/Game</p>
  <svg viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none">
    <line x1="${{PAD}}" y1="${{ay}}" x2="${{W-PAD}}" y2="${{ay}}" stroke="#30363d" stroke-width="0.5" stroke-dasharray="3,2"/>
    <polyline points="${{pts.join(' ')}}" fill="none" stroke="#f9a03f" stroke-width="1.5" stroke-linejoin="round"/>
    ${{dots}}
  </svg>
  <div style="display:flex;justify-content:space-between;font-size:9px;color:#555;margin-top:1px;">
    <span>${{monthly[0].m.slice(5)}}</span><span>${{monthly[monthly.length-1].m.slice(5)}}</span>
  </div></div>`;
}}

function buildCard(p){{
  const zClass=p.gritz>=0?"pos":"neg";
  const zStr=(p.gritz>=0?"+":"")+p.gritz.toFixed(2);
  const d=p._d||{{}};
  const posEvents=d.pos_events||[];
  const negEvents=d.neg_events||[];
  const posRows=posEvents.map(e=>`<tr><td class="ev">${{esc(e.l)}}</td><td class="num">${{e.v}}</td><td class="wt">${{e.w>0?"+":""}}${{e.w}}</td></tr>`).join("");
  const negRows=negEvents.map(e=>`<tr class="neg"><td class="ev">${{esc(e.l)}}</td><td class="num">${{e.v}}</td><td class="wt">${{e.w}}</td></tr>`).join("");
  const fmt5=(z,t)=>z!==null&&z!==undefined?`<div class="v ${{z>=0?"pos":"neg"}}">${{(z>=0?"+":"")+z.toFixed(2)}}</div><div class="t">${{t.toFixed(0)}} min</div>`:`<div class="v" style="color:#555">—</div>`;
  const splits=`<div class="splits">
    <div class="split"><div class="lbl">5-on-5</div>${{fmt5(d.z_5v5,d.toi_5v5||0)}}</div>
    <div class="split"><div class="lbl">Penalty kill</div>${{fmt5(d.z_pk,d.toi_pk||0)}}</div>
  </div>`;
  let poHTML="";
  if(d.po_z!==null&&d.po_z!==undefined){{
    const pc=d.po_z>=0?"pos":"neg";
    poHTML=`<div class="po-strip">
      <div class="po-lbl">🏒 Playoffs</div>
      <div class="po-z ${{pc}}">${{(d.po_z>=0?"+":"")+d.po_z.toFixed(2)}}</div>
      <div class="po-info">${{d.po_gp}} GP · ${{d.po_toi.toFixed(0)}} min</div>
    </div>`;
  }}
  return`<div class="card" data-name="${{esc(p.name.toLowerCase())}}" data-team="${{esc(p.team)}}" data-pos="${{esc(p.pool)}}" data-gritz="${{p.gritz}}">
    <div class="card-header">
      <div class="card-rank">#${{p.rk_lg}}</div>
      <div>
        <div class="card-name">${{esc(p.name)}}</div>
        <div class="card-meta">${{esc(p.pos)}} · ${{esc(p.team)}} · ${{p.gp}} GP · ${{p.atoi}} ATOI · #${{p.rk_pos}}/${{p.rk_pos_total}} ${{p.pool}}</div>
      </div>
      <div class="card-z">
        <div class="num ${{zClass}}">${{zStr}}</div>
        <div class="lbl">GRIT-Z v3</div>
        <div class="pctile">${{p.pctile_pos}}${{ord(p.pctile_pos)}} pct (${{p.pool}})</div>
      </div>
    </div>
    <div class="card-body">
      <p class="section-label">Positive events</p>
      <table class="events-table">${{posRows||"<tr><td>none</td></tr>"}}</table>
      ${{negRows?`<p class="section-label" style="margin-top:8px">Anti-grit</p><table class="events-table">${{negRows}}</table>`:""}}
      ${{splits}}${{poHTML}}
      ${{buildSparkline(d.monthly||[])}}
      ${{buildHeatmap(d.spatial||[])}}
    </div>
  </div>`;
}}

const grid=document.getElementById("grid");
const status=document.getElementById("status");
const searchEl=document.getElementById("search");
const teamF=document.getElementById("team-filter");
const posF=document.getElementById("pos-filter");
const sortS=document.getElementById("sort");
const countEl=document.getElementById("count");

function getFiltered(){{
  const q=searchEl.value.toLowerCase().trim();
  const tf=teamF.value, pf=posF.value;
  return PLAYERS.filter(p=>{{
    if(q&&!p.name.toLowerCase().includes(q))return false;
    if(tf&&p.team!==tf)return false;
    if(pf&&p.pool!==pf)return false;
    return true;
  }});
}}
function getSorted(list){{
  const s=sortS.value, r=list.slice();
  if(s==="grit-desc")r.sort((a,b)=>b.gritz-a.gritz);
  else if(s==="grit-asc")r.sort((a,b)=>a.gritz-b.gritz);
  else if(s==="name")r.sort((a,b)=>a.name.localeCompare(b.name));
  else if(s==="team")r.sort((a,b)=>(a.team||"").localeCompare(b.team||"")||(b.gritz-a.gritz));
  return r;
}}

let rendered=0;
const PAGE=25;
function render(){{
  const list=getSorted(getFiltered());
  countEl.textContent=list.length+" players";
  grid.innerHTML="";rendered=0;
  window.__list=list;
  appendMore();
}}
function appendMore(){{
  const slice=window.__list.slice(rendered,rendered+PAGE);
  if(!slice.length)return;
  grid.insertAdjacentHTML("beforeend",slice.map(buildCard).join(""));
  rendered+=slice.length;
}}
window.addEventListener("scroll",()=>{{
  if(window.innerHeight+window.scrollY>=document.body.offsetHeight-1000&&rendered<(window.__list||[]).length)
    appendMore();
}});

// Bind filters before fetch — search/sort work even if sidecar fails to load.
searchEl.addEventListener("input",render);
teamF.addEventListener("change",render);
posF.addEventListener("change",render);
sortS.addEventListener("change",render);

// Fetch sidecar, merge, then render.
fetch(SIDECAR).then(r=>{{
  if(!r.ok) throw new Error("HTTP "+r.status);
  return r.json();
}}).then(details=>{{
  for(const p of PLAYERS){{
    p._d = details[String(p.player_id)] || {{}};
  }}
  status.style.display="none";
  render();
}}).catch(err=>{{
  status.textContent = "Could not load "+SIDECAR+" ("+err.message+"). Cards will show headers only.";
  status.style.color = "#e8474a";
  // Render with empty details so at least the headers show.
  for(const p of PLAYERS) p._d = {{}};
  render();
}});
</script>
</body>
</html>'''


# ============================================================================
# Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True,
                    help="Start-year season tag (e.g. 2026 = 2025-26)")
    ap.add_argument("--output-dir", default=".",
                    help="Where to write the .html and .json files")
    ap.add_argument("--no-sql", action="store_true",
                    help="Skip SQL — load from CSVs instead")
    ap.add_argument("--data-dir",
                    help="Required with --no-sql. Folder containing v3 CSVs.")
    ap.add_argument("--season-label",
                    help="Display label, e.g. '2025-26'. Defaults from --season.")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    season_label = args.season_label or f"{args.season - 1}-{str(args.season)[-2:]}"

    # Load
    if args.no_sql:
        if not args.data_dir:
            print("ERROR: --no-sql requires --data-dir", file=sys.stderr)
            sys.exit(1)
        df_scores, df_monthly, df_spatial = load_from_csv(args.data_dir, args.season)
    else:
        try:
            engine = get_sql_engine()
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("SQL connection: OK")
            df_scores, df_monthly, df_spatial = load_from_sql(engine, args.season)
        except Exception as e:
            print(f"SQL connection failed: {e}")
            if args.data_dir:
                print("Falling back to CSVs...")
                df_scores, df_monthly, df_spatial = load_from_csv(args.data_dir, args.season)
            else:
                print("No --data-dir provided; cannot fall back. Exiting.", file=sys.stderr)
                sys.exit(1)

    if df_scores.empty:
        print(f"ERROR: no rows for season {args.season}. Nothing to build.", file=sys.stderr)
        sys.exit(1)

    # Build records
    print("\nAssembling player records...")
    manifest, details = build_player_records(df_scores, df_monthly, df_spatial)
    print(f"  {len(manifest)} players in manifest")
    print(f"  {len(details)} player detail records")

    # Write sidecar JSON
    sidecar_name = f"player_cards_v3_{args.season}_data.json"
    sidecar_path = out_dir / sidecar_name
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(details, f, separators=(",", ":"))
    sidecar_kb = sidecar_path.stat().st_size / 1024
    print(f"\nWrote sidecar JSON: {sidecar_path} ({sidecar_kb:.0f} KB)")

    # Write HTML
    html = render_html(manifest, season_label, sidecar_name)
    html_name = f"player_cards_v3_{args.season}.html"
    html_path = out_dir / html_name
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    html_kb = html_path.stat().st_size / 1024
    print(f"Wrote HTML:         {html_path} ({html_kb:.0f} KB)")

    print("\nDone.")
    print(f"Open in a browser: {html_path.resolve()}")
    print("(The HTML expects the JSON next to it. Both must travel together.)")


if __name__ == "__main__":
    main()
