"""build_eyp_career_html.py — generate the EYP career table and scatter HTMLs.

Reads:
  - data/eyp_career_v31.csv          (career pivot, 797 forwards, quad history)
  - per-season query of SQL          (for scatter: season pts + grit_z + quadrant)

Writes:
  - data/eyp_career_v31.html         (sortable table, all 797, color-coded quads)
  - data/eyp_career_scatter_v31.html (scatter w/ season dropdown, default 2026)

Both files are standalone (self-contained HTML+JS, no external assets).
Style: white ice background, dark text, BLUE/GREEN/RED/GRAY quadrant colors.

Usage:
    python build_eyp_career_html.py
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from grit_version import GRIT_VERSION
from eyp_common import (
    GP_FLOOR, FORWARD_POSITIONS, GRIT_CUTOFF,
    season_points_threshold, assign_quadrant,
)


SQL_SERVER   = "localhost"
SQL_DATABASE = "GRIT"
SQL_DRIVER   = "ODBC Driver 17 for SQL Server"

DEFAULT_DATA_DIR = Path(
    r"C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\data"
)
DEFAULT_OUTPUT_DIR = Path(
    r"C:\Users\mjrig\OneDrive\Documents\GitHub\grit-hockey\viz"
)

ALL_RS_SEASONS = [2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025, 2026]
DEFAULT_SEASON = 2026

GP_FLOOR          = 40                    # mirrors eyp_common
FORWARD_POSITIONS = ["C", "L", "R"]       # mirrors eyp_common
GRIT_CUTOFF       = 0.0                    # mirrors eyp_common
# Classification (points bar + assign_quadrant) comes from eyp_common, imported
# above — the single source of truth shared with build_eyp.py.

# Quadrant colors. Solid dots, mid-tone — readable on white.
QUAD_COLORS = {
    "BLUE":  "#2563eb",
    "GREEN": "#16a34a",
    "RED":   "#dc2626",
    "GRAY":  "#6b7280",
}


def get_engine():
    from sqlalchemy import create_engine
    return create_engine(
        f"mssql+pyodbc://@{SQL_SERVER}/{SQL_DATABASE}"
        f"?driver={SQL_DRIVER.replace(' ', '+')}"
        f"&trusted_connection=yes"
    )


def load_season_qualifiers(engine, season_tag):
    """Per-season qualifying forwards with points, grit_z, quadrant, team, age.

    Matches build_eyp.py's logic exactly: forwards only, GP >= 40, grit_scores
    + skater_scoring inner join, quadrant by absolute pts bar (41, prorated). Adds an `age`
    column from players.birth_year (age = season_end_year - birth_year).
    Missing birth_year → age = None (excluded from age <= 25 highlight).
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        grit = pd.read_sql(
            text("""
                SELECT player_id, name, position, team, grit_z_blend
                FROM grit_scores
                WHERE season = :s AND is_playoffs = 0 AND strength = 'all'
            """),
            conn, params={"s": season_tag},
        )
        scoring = pd.read_sql(
            text("""
                SELECT player_id, games_played, points
                FROM skater_scoring
                WHERE season = :s
            """),
            conn, params={"s": season_tag},
        )
        ages = pd.read_sql(
            text("SELECT player_id, birth_year FROM players"),
            conn,
        )

    if grit.empty or scoring.empty:
        return pd.DataFrame()

    grit_fwd = grit[grit["position"].isin(FORWARD_POSITIONS)].copy()
    df = grit_fwd.merge(scoring, on="player_id", how="inner")
    df = df[df["games_played"] >= GP_FLOOR].copy()
    if df.empty:
        return pd.DataFrame()

    df = df.merge(ages, on="player_id", how="left")
    df["age"] = int(season_tag) - df["birth_year"]

    pts_threshold = season_points_threshold(season_tag)
    df["quadrant"] = df.apply(
        lambda r: assign_quadrant(r["grit_z_blend"], r["points"], pts_threshold),
        axis=1,
    )
    df["season"] = int(season_tag)
    df["pts_threshold"] = pts_threshold
    return df[["season", "player_id", "name", "position", "team",
               "games_played", "points", "grit_z_blend",
               "pts_threshold", "quadrant", "age"]]


# =============================================================================
# Table HTML
# =============================================================================

def build_table_html(career_df, output_path):
    """Sortable table of 797 forwards with color-coded quad cells."""
    # Quad columns we'll render. Skip 2021 (always None) for compactness.
    quad_seasons = [s for s in ALL_RS_SEASONS]
    quad_cols = [f"quad_{s}" for s in quad_seasons]

    front_cols = [
        ("player_id", "ID"),
        ("name", "Name"),
        ("position", "Pos"),
        ("birth_year", "Born"),
        ("n_qualifying_seasons", "n"),
        ("blue_count", "B"),
        ("green_count", "G"),
        ("red_count", "R"),
        ("gray_count", "Gr"),
        ("blue_streak", "Bstreak"),
        ("blue_streak_current", "Bcurr"),
        ("ever_btog", "B→G"),
        ("most_recent_quad", "Recent"),
        ("most_recent_season", "Rsn"),
    ]

    # Convert dataframe to list-of-dicts for JS rendering. We embed as JSON.
    cols_to_export = [c for c, _ in front_cols] + quad_cols
    safe_df = career_df[cols_to_export].copy()
    # Booleans → strings for cleaner JSON
    safe_df["ever_btog"] = safe_df["ever_btog"].map(lambda v: "Y" if v else "")
    # NaN → None → JSON null
    safe_df = safe_df.astype(object).where(pd.notna(safe_df), None)
    data_json = safe_df.to_dict(orient="records")

    header_meta = [{"key": k, "label": l} for k, l in front_cols]
    header_meta += [{"key": f"quad_{s}", "label": f"'{str(s)[2:]}"} for s in quad_seasons]

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EYP Career · {GRIT_VERSION}</title>
<style>
  :root {{
    --bg: #0d1117;
    --panel: #161b22;
    --panel-2: #1c232d;
    --border: #30363d;
    --text: #e6edf3;
    --text-dim: #8b949e;
    --accent: #f85149;
    --accent-2: #58a6ff;
    --orange: #f9a03f;
    --row-alt: #161b22;
    --row-hover: #1c232d;
    --header-bg: #1c232d;
    --blue: {QUAD_COLORS['BLUE']};
    --green: {QUAD_COLORS['GREEN']};
    --red: {QUAD_COLORS['RED']};
    --gray: {QUAD_COLORS['GRAY']};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 20px; min-height: 100vh;
    font-size: 13px;
  }}
  .header {{
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px; margin-bottom: 20px;
    display: flex; justify-content: space-between;
    align-items: flex-end; flex-wrap: wrap; gap: 12px;
  }}
  h1 {{ font-size: 22px; font-weight: 600; letter-spacing: -0.3px; display:flex; align-items:center; gap:8px; }}
  h1 .sub {{ color: var(--text-dim); font-weight: 400; font-size: 14px; }}
  .v3badge {{
    background: var(--orange); color: #0d1117;
    font-size: 11px; font-weight: 700;
    padding: 2px 7px; border-radius: 3px; letter-spacing: 1px;
  }}
  .subtitle {{ color: var(--text-dim); font-size: 12px; margin-bottom: 16px; }}
  .controls {{
    margin-bottom: 12px; display: flex; gap: 16px; align-items: center;
  }}
  input[type=text] {{
    padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px;
    font-size: 13px; background: var(--panel); color: var(--text);
    width: 220px;
  }}
  input[type=text]::placeholder {{ color: var(--text-dim); }}
  .count {{ color: var(--text-dim); }}
  .table-wrap {{
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; overflow-x: auto;
  }}
  table {{
    border-collapse: collapse; font-size: 12px;
    background: var(--panel); width: 100%;
  }}
  th, td {{
    padding: 6px 8px; border-bottom: 1px solid var(--border);
    text-align: right; white-space: nowrap;
  }}
  th {{
    position: sticky; top: 0;
    background: var(--header-bg); cursor: pointer; user-select: none;
    text-align: right; color: var(--text-dim);
    text-transform: uppercase; letter-spacing: 0.4px;
    font-weight: 500;
  }}
  th:hover {{ color: var(--text); }}
  th.sort-asc::after  {{ content: " ▲"; color: var(--orange); }}
  th.sort-desc::after {{ content: " ▼"; color: var(--orange); }}
  td.name, th.name {{ text-align: left; min-width: 160px; }}
  tr:nth-child(even) td {{ background: var(--row-alt); }}
  tr:hover td {{ background: var(--row-hover); }}
  td.quad {{
    text-align: center; min-width: 32px; font-size: 11px;
    font-weight: 600; color: white;
  }}
  td.quad-BLUE  {{ background: var(--blue); }}
  td.quad-GREEN {{ background: var(--green); }}
  td.quad-RED   {{ background: var(--red); }}
  td.quad-GRAY  {{ background: var(--gray); }}
  td.quad-empty {{ background: transparent; color: var(--text-dim); opacity: 0.4; }}
  td.btog-yes {{ color: var(--orange); font-weight: 600; }}
</style>
</head>
<body>

<div class="header">
  <h1>EYP Career Pivot <span class="v3badge">{GRIT_VERSION.upper()}</span><span class="sub">Earning Your Points</span></h1>
</div>
<p class="subtitle">
  797 forwards qualified in at least one season (2015-16 → 2025-26, ex. 2020-21 COVID).
  Forwards only, GP ≥ {GP_FLOOR}. Click any column header to sort.
</p>

<div class="controls">
  <input id="filter" type="text" placeholder="Filter by name…">
  <span class="count" id="count"></span>
</div>

<div class="table-wrap">
<table id="t">
  <thead><tr id="headers"></tr></thead>
  <tbody id="body"></tbody>
</table>
</div>

<script>
const DATA = {json.dumps(data_json, default=str)};
const HEADERS = {json.dumps(header_meta)};
const QUAD_SEASONS = {json.dumps([f'quad_{s}' for s in quad_seasons])};

let sortKey = "blue_streak_current";
let sortDir = -1;  // -1 desc, 1 asc

const headerRow = document.getElementById("headers");
HEADERS.forEach(h => {{
  const th = document.createElement("th");
  th.textContent = h.label;
  th.dataset.key = h.key;
  if (h.key === "name") th.classList.add("name");
  th.addEventListener("click", () => {{
    if (sortKey === h.key) sortDir = -sortDir;
    else {{ sortKey = h.key; sortDir = -1; }}
    render();
  }});
  headerRow.appendChild(th);
}});

function render() {{
  const filter = document.getElementById("filter").value.toLowerCase();
  let rows = DATA.filter(r => !filter ||
    (r.name || "").toLowerCase().includes(filter));

  rows.sort((a, b) => {{
    let av = a[sortKey], bv = b[sortKey];
    // Null/empty go to the end regardless of direction
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
    return String(av).localeCompare(String(bv)) * sortDir;
  }});

  document.getElementById("count").textContent =
    rows.length + " of " + DATA.length + " forwards";

  // Update header indicators
  document.querySelectorAll("th").forEach(th => {{
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.key === sortKey) {{
      th.classList.add(sortDir === 1 ? "sort-asc" : "sort-desc");
    }}
  }});

  const body = document.getElementById("body");
  body.innerHTML = "";
  rows.forEach(r => {{
    const tr = document.createElement("tr");
    HEADERS.forEach(h => {{
      const td = document.createElement("td");
      const v = r[h.key];
      if (QUAD_SEASONS.indexOf(h.key) !== -1) {{
        // Quadrant cell
        if (v == null || v === "") {{
          td.classList.add("quad", "quad-empty");
          td.textContent = "·";
        }} else {{
          td.classList.add("quad", "quad-" + v);
          td.textContent = v[0];
        }}
      }} else {{
        if (h.key === "name") td.classList.add("name");
        if (h.key === "ever_btog" && v === "Y") td.classList.add("btog-yes");
        td.textContent = v == null ? "" : v;
      }}
      tr.appendChild(td);
    }});
    body.appendChild(tr);
  }});
}}

document.getElementById("filter").addEventListener("input", render);
render();
</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    print(f"  wrote {output_path}  ({len(career_df)} rows, {len(quad_cols)} quad cols)")


# =============================================================================
# Scatter HTML
# =============================================================================

def build_scatter_html(season_data, output_path):
    """Scatter w/ season dropdown.

    AXES: X = grit_z_blend, Y = points. So:
      Top-left    (lo grit, hi pts) = RED   — McDavid territory
      Top-right   (hi grit, hi pts) = GREEN
      Bottom-left (lo grit, lo pts) = GRAY
      Bottom-right(hi grit, lo pts) = BLUE  — EYP archetype

    GRIT-palette theme (matches build_dashboard.py). Dots colored by selected
    season's quadrant. Top-N auto-pinned (default 20, slider-configurable).
    Pinned players render their full multi-season trajectory: dots across all
    qualifying seasons, connected by a faint line in chronological order.
    """
    # Build BOTH the per-season qualifier dict (for current rendering) AND
    # a per-player history dict (for trajectory mode). The history dict maps
    # player_id -> sorted list of [season, grit_z, points, quadrant] entries.
    by_season = {}
    by_player = {}  # player_id -> [{season, points, grit_z_blend, quadrant, team}, ...]

    for s, rows in season_data.items():
        out_rows = []
        for r in rows:
            row = {
                "player_id":    int(r["player_id"]),
                "name":         r["name"],
                "team":         r["team"],
                "position":     r["position"],
                "points":       int(r["points"]),
                "grit_z_blend": float(r["grit_z_blend"]),
                "pts_threshold": float(r["pts_threshold"]),
                "quadrant":     r["quadrant"],
                "age":          (None if pd.isna(r.get("age")) else int(r["age"])),
            }
            out_rows.append(row)
            # accumulate trajectory history
            pid = row["player_id"]
            if pid not in by_player:
                by_player[pid] = {"name": row["name"], "seasons": []}
            by_player[pid]["seasons"].append({
                "season":       int(s),
                "team":         row["team"],
                "points":       row["points"],
                "grit_z_blend": row["grit_z_blend"],
                "quadrant":     row["quadrant"],
            })
        by_season[str(s)] = out_rows

    # Sort each player's season history chronologically
    for pid in by_player:
        by_player[pid]["seasons"].sort(key=lambda d: d["season"])

    default_str = str(DEFAULT_SEASON)
    seasons_list = sorted(by_season.keys(), reverse=True)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EYP Scatter · {GRIT_VERSION}</title>
<style>
  :root {{
    --bg: #0d1117;
    --panel: #161b22;
    --panel-2: #1c232d;
    --border: #30363d;
    --text: #e6edf3;
    --text-dim: #8b949e;
    --accent: #f85149;
    --accent-2: #58a6ff;
    --good: #3fb950;
    --warn: #d29922;
    --orange: #f9a03f;
    --blue: {QUAD_COLORS['BLUE']};
    --green: {QUAD_COLORS['GREEN']};
    --red: {QUAD_COLORS['RED']};
    --gray: {QUAD_COLORS['GRAY']};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 20px; min-height: 100vh;
    font-size: 13px;
  }}
  .header {{
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px; margin-bottom: 20px;
    display: flex; justify-content: space-between;
    align-items: flex-end; flex-wrap: wrap; gap: 12px;
  }}
  h1 {{ font-size: 22px; font-weight: 600; letter-spacing: -0.3px; display:flex; align-items:center; gap:8px; }}
  h1 .sub {{ color: var(--text-dim); font-weight: 400; font-size: 14px; }}
  .v3badge {{
    background: var(--orange); color: #0d1117;
    font-size: 11px; font-weight: 700;
    padding: 2px 7px; border-radius: 3px; letter-spacing: 1px;
  }}
  .subtitle {{ color: var(--text-dim); font-size: 12px; margin-bottom: 16px; }}
  .controls {{
    margin-bottom: 16px; display: flex; gap: 16px; align-items: center;
    flex-wrap: wrap;
  }}
  .controls label {{
    display: inline-flex; align-items: center; gap: 6px;
    color: var(--text-dim); font-size: 12px;
  }}
  select, input[type=text] {{
    padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px;
    font-size: 13px; background: var(--panel); color: var(--text);
  }}
  input[type="checkbox"] {{ accent-color: var(--orange); }}
  .btn-png {{
    background: var(--panel); border: 1px solid var(--border);
    color: var(--text-dim); padding: 6px 12px; border-radius: 4px;
    cursor: pointer; font-size: 12px;
  }}
  .btn-png:hover {{ color: var(--text); border-color: var(--orange); }}
  .compare-arrow {{
    fill: none; stroke: var(--orange);
    stroke-width: 1; opacity: 0.55;
    marker-end: url(#arrowhead);
    pointer-events: none;
  }}
  .compare-dot {{
    fill-opacity: 0.30; stroke: none;
    pointer-events: none;
  }}
  .age-ring {{
    fill: none; stroke: var(--orange);
    stroke-width: 1.5;
    pointer-events: none;
  }}
  input[type=range] {{
    accent-color: var(--orange);
    width: 110px;
  }}
  #topnVal {{
    color: var(--orange); font-weight: 600;
    min-width: 22px; text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  .legend {{
    display: flex; gap: 12px; font-size: 12px; color: var(--text-dim);
    flex-wrap: wrap;
  }}
  .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .legend .swatch {{
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  }}
  #plot-wrap {{
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px;
  }}
  #plot {{
    background: var(--bg);
    border-radius: 4px;
    display: block;
  }}
  .axis-label {{
    fill: var(--text); font-size: 12px; font-weight: 500;
  }}
  .axis-tick text {{ fill: var(--text-dim); font-size: 11px; }}
  .quad-label {{
    fill: var(--text); font-size: 12px; font-weight: 600; opacity: 0.65;
  }}
  .pin {{ pointer-events: none; }}
  .pin-bg {{
    fill: #000; stroke: var(--orange); stroke-width: 1;
    rx: 3; ry: 3;
  }}
  .pin-text {{ fill: white; font-size: 11px; font-weight: 500; }}
  .med-label {{
    fill: var(--text); font-size: 10px; font-weight: 600;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }}
  .traj-line {{
    fill: none; stroke: var(--orange);
    stroke-width: 1.5; stroke-dasharray: 3,2; opacity: 0.7;
    pointer-events: none;
  }}
  .traj-dot {{ pointer-events: none; }}
  #tooltip {{
    position: absolute; pointer-events: none; visibility: hidden;
    background: #000; color: white;
    padding: 6px 8px; border-radius: 4px;
    font-size: 12px; white-space: nowrap;
    transform: translate(8px, -50%);
    border: 1px solid var(--orange);
  }}
</style>
</head>
<body>

<div class="header">
  <h1>EYP Scatter <span class="v3badge">{GRIT_VERSION.upper()}</span><span class="sub">Earning Your Points</span></h1>
</div>
<p class="subtitle">
  grit_z_blend (x) vs season points (y). Forwards only, GP ≥ {GP_FLOOR}.
  Quadrants split by grit_z = 0 (vertical) and the absolute pts bar (horizontal).
  Pinned players show their full season-by-season trajectory.
</p>

<div class="controls">
  <label>Season:
    <select id="season">
      {''.join(f'<option value="{s}"{" selected" if s == default_str else ""}>{s}</option>' for s in seasons_list)}
    </select>
  </label>
  <label>Compare:
    <select id="compare">
      <option value="">(none)</option>
      {''.join(f'<option value="{s}">{s}</option>' for s in seasons_list)}
    </select>
  </label>
  <label>Pos:
    <input type="checkbox" id="posC" checked> <span style="color:var(--text);margin-right:6px">C</span>
    <input type="checkbox" id="posW" checked> <span style="color:var(--text)">W</span>
  </label>
  <label>Team:
    <select id="team"><option value="">All teams</option></select>
  </label>
  <label>
    <input type="checkbox" id="ageHi"> <span style="color:var(--text)">Age ≤25</span>
  </label>
  <label>Search:
    <input id="search" type="text" placeholder="Player name…">
  </label>
  <button id="pngBtn" class="btn-png">Save PNG</button>
</div>

<div class="controls" style="margin-top:-8px;">
  <span class="legend" id="legend"></span>
  <span class="legend"><span id="count"></span></span>
</div>

<div id="plot-wrap">
  <svg id="plot" width="900" height="600"></svg>
</div>
<div id="tooltip"></div>

<script>
const DATA = {json.dumps(by_season)};
const TRAJ = {json.dumps(by_player)};
const QUAD_COLORS = {json.dumps(QUAD_COLORS)};

const W = 900, H = 600;
const M = {{ top: 30, right: 30, bottom: 50, left: 60 }};
const PW = W - M.left - M.right;
const PH = H - M.top - M.bottom;

const svg = document.getElementById("plot");
const tooltip = document.getElementById("tooltip");
const seasonEl = document.getElementById("season");
const searchEl = document.getElementById("search");
const countEl = document.getElementById("count");
const legendEl = document.getElementById("legend");

// State for active player + filter controls
let activeIdx = null;       // index into FILTERED currentRows
let currentRows = [];       // post-filter rows for the primary season
let compareRows = [];       // post-filter rows for the compare season (or [])
let xScale, yScale;
let pinsLayer = null;

// Filter / compare / age UI refs
const posCEl = document.getElementById("posC");
const posWEl = document.getElementById("posW");
const teamEl = document.getElementById("team");
const ageHiEl = document.getElementById("ageHi");
const compareEl = document.getElementById("compare");
const pngBtnEl = document.getElementById("pngBtn");

// Build the team dropdown from all data
const TEAMS = new Set();
Object.values(DATA).forEach(arr => arr.forEach(r => TEAMS.add(r.team)));
Array.from(TEAMS).sort().forEach(t => {{
  const opt = document.createElement("option");
  opt.value = t; opt.textContent = t;
  teamEl.appendChild(opt);
}});

function applyFilters(rows) {{
  const wantC = posCEl.checked;
  const wantW = posWEl.checked;
  const team = teamEl.value;
  return rows.filter(r => {{
    // Position: C / W (W = L + R)
    const isC = r.position === "C";
    const isW = r.position === "L" || r.position === "R";
    if (!((isC && wantC) || (isW && wantW))) return false;
    if (team && r.team !== team) return false;
    return true;
  }});
}}

function buildLegend(rows) {{
  const counts = {{ RED: 0, GREEN: 0, GRAY: 0, BLUE: 0 }};
  rows.forEach(r => {{ counts[r.quadrant] = (counts[r.quadrant] || 0) + 1; }});
  legendEl.innerHTML =
    `<span><span class="swatch" style="background:${{QUAD_COLORS.RED}}"></span>Low grit / High points (n=${{counts.RED}})</span>` +
    `<span><span class="swatch" style="background:${{QUAD_COLORS.GREEN}}"></span>High grit / High points (n=${{counts.GREEN}})</span>` +
    `<span><span class="swatch" style="background:${{QUAD_COLORS.GRAY}}"></span>Low grit / Low points (n=${{counts.GRAY}})</span>` +
    `<span><span class="swatch" style="background:${{QUAD_COLORS.BLUE}}"></span>High grit / Low points (n=${{counts.BLUE}})</span>`;
  return counts;
}}

function drawTrajectory(playerId) {{
  if (!pinsLayer) return;
  const hist = TRAJ[playerId];
  if (!hist || hist.seasons.length === 0) return;

  let pathD = "";
  hist.seasons.forEach((sn, idx) => {{
    const cx = xScale(sn.grit_z_blend);
    const cy = yScale(sn.points);
    pathD += (idx === 0 ? `M ${{cx}} ${{cy}}` : ` L ${{cx}} ${{cy}}`);
  }});
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", pathD);
  path.setAttribute("class", "traj-line");
  pinsLayer.appendChild(path);

  hist.seasons.forEach(sn => {{
    const color = QUAD_COLORS[sn.quadrant] || "#888";
    const cx = xScale(sn.grit_z_blend);
    const cy = yScale(sn.points);
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "traj-dot");
    g.innerHTML =
      `<circle cx="${{cx}}" cy="${{cy}}" r="3" fill="${{color}}" stroke="var(--orange)" stroke-width="1"/>` +
      `<text x="${{cx + 5}}" y="${{cy - 5}}" font-size="9" fill="var(--orange)" font-weight="600">'${{String(sn.season).slice(2)}}</text>`;
    pinsLayer.appendChild(g);
  }});
}}

function drawActive() {{
  if (!pinsLayer) return;
  pinsLayer.innerHTML = "";
  if (activeIdx === null) return;
  const r = currentRows[activeIdx];
  if (!r) return;

  drawTrajectory(r.player_id);

  const cx = xScale(r.grit_z_blend), cy = yScale(r.points);
  const label = `${{r.name}} (${{r.team}})`;
  const w = label.length * 6.5 + 12;
  const h = 18;
  const flipX = cx + w + 10 > M.left + PW;
  const bx = flipX ? cx - w - 8 : cx + 8;
  const by = cy - h - 6;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("pin");
  g.innerHTML =
    `<rect class="pin-bg" x="${{bx}}" y="${{by}}" width="${{w}}" height="${{h}}"/>` +
    `<text class="pin-text" x="${{bx + w / 2}}" y="${{by + 12}}" text-anchor="middle">${{label}}</text>` +
    `<circle cx="${{cx}}" cy="${{cy}}" r="6" fill="none" stroke="var(--orange)" stroke-width="1.5"/>`;
  pinsLayer.appendChild(g);
}}

function render(season) {{
  // Apply filters to the primary season's data
  const rawRows = DATA[season] || [];
  currentRows = applyFilters(rawRows);

  // Compare season (if any) — also filtered
  const compareSeason = compareEl.value;
  if (compareSeason && compareSeason !== season) {{
    compareRows = applyFilters(DATA[compareSeason] || []);
  }} else {{
    compareRows = [];
  }}

  if (currentRows.length === 0) {{
    svg.innerHTML = '<text x="450" y="300" text-anchor="middle" fill="#888">no data (try adjusting filters)</text>';
    countEl.textContent = "0 forwards";
    legendEl.innerHTML = "";
    return;
  }}

  const compareSuffix = compareRows.length > 0
    ? ` · vs ${{compareSeason}} (n=${{compareRows.length}})`
    : "";
  countEl.textContent = currentRows.length + " qualifying forwards" + compareSuffix;
  buildLegend(currentRows);

  // AXES: x = grit_z_blend, y = points
  // Use COMBINED ranges across primary + compare for stable scales
  const allRows = currentRows.concat(compareRows);
  const gzs = allRows.map(r => r.grit_z_blend);
  const pts = allRows.map(r => r.points);
  const gzMin = Math.min(...gzs), gzMax = Math.max(...gzs);
  const ptsMin = Math.min(...pts), ptsMax = Math.max(...pts);
  const gzPad = (gzMax - gzMin) * 0.05;
  const ptsPad = (ptsMax - ptsMin) * 0.05;
  const xMin = gzMin - gzPad, xMax = gzMax + gzPad;
  const yMin = ptsMin - ptsPad, yMax = ptsMax + ptsPad;
  const ptsBar = currentRows[0].pts_threshold;

  xScale = v => M.left + (v - xMin) / (xMax - xMin) * PW;
  yScale = v => M.top + PH - (v - yMin) / (yMax - yMin) * PH;
  const x = xScale, y = yScale;

  const counts = {{ RED: 0, GREEN: 0, GRAY: 0, BLUE: 0 }};
  currentRows.forEach(r => {{ counts[r.quadrant] = (counts[r.quadrant] || 0) + 1; }});

  const xZero = x(0);
  const yMed = y(ptsBar);

  let svgInner = "";

  // Arrow marker defs for compare arrows
  svgInner += `<defs>
    <marker id="arrowhead" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="${{getComputedStyle(document.documentElement).getPropertyValue('--orange').trim()}}" />
    </marker>
  </defs>`;

  // Background tints
  svgInner += `<rect x="${{M.left}}" y="${{M.top}}" width="${{xZero - M.left}}" height="${{yMed - M.top}}" fill="${{QUAD_COLORS.RED}}" opacity="0.08"/>`;
  svgInner += `<rect x="${{xZero}}" y="${{M.top}}" width="${{M.left + PW - xZero}}" height="${{yMed - M.top}}" fill="${{QUAD_COLORS.GREEN}}" opacity="0.08"/>`;
  svgInner += `<rect x="${{M.left}}" y="${{yMed}}" width="${{xZero - M.left}}" height="${{M.top + PH - yMed}}" fill="${{QUAD_COLORS.GRAY}}" opacity="0.08"/>`;
  svgInner += `<rect x="${{xZero}}" y="${{yMed}}" width="${{M.left + PW - xZero}}" height="${{M.top + PH - yMed}}" fill="${{QUAD_COLORS.BLUE}}" opacity="0.08"/>`;

  // Split lines
  svgInner += `<line x1="${{xZero}}" y1="${{M.top}}" x2="${{xZero}}" y2="${{M.top + PH}}" stroke="#7a8ca8" stroke-dasharray="4,3" stroke-width="1.2"/>`;
  svgInner += `<line x1="${{M.left}}" y1="${{yMed}}" x2="${{M.left + PW}}" y2="${{yMed}}" stroke="#7a8ca8" stroke-dasharray="4,3" stroke-width="1.2"/>`;

  // Median annotations
  svgInner += `<rect x="${{xZero - 28}}" y="${{M.top + PH - 22}}" width="56" height="16" fill="#0d1117" stroke="#7a8ca8" stroke-width="0.5" rx="2"/>`;
  svgInner += `<text class="med-label" x="${{xZero}}" y="${{M.top + PH - 10}}" text-anchor="middle">grit_z=0</text>`;
  const medText = `pts bar ${{ptsBar.toFixed(0)}}`;
  svgInner += `<rect x="${{M.left + 4}}" y="${{yMed - 8}}" width="68" height="16" fill="#0d1117" stroke="#7a8ca8" stroke-width="0.5" rx="2"/>`;
  svgInner += `<text class="med-label" x="${{M.left + 38}}" y="${{yMed + 4}}" text-anchor="middle">${{medText}}</text>`;

  // Quadrant labels with counts
  svgInner += `<text class="quad-label" x="${{M.left + 8}}" y="${{M.top + 16}}">Low grit · High points · n=${{counts.RED}}</text>`;
  svgInner += `<text class="quad-label" x="${{M.left + PW - 8}}" y="${{M.top + 16}}" text-anchor="end">High grit · High points · n=${{counts.GREEN}}</text>`;
  svgInner += `<text class="quad-label" x="${{M.left + 8}}" y="${{M.top + PH - 8}}">Low grit · Low points · n=${{counts.GRAY}}</text>`;
  svgInner += `<text class="quad-label" x="${{M.left + PW - 8}}" y="${{M.top + PH - 8}}" text-anchor="end">High grit · Low points · n=${{counts.BLUE}}</text>`;

  // Axis ticks
  const xTickStep = (xMax - xMin) > 4 ? 1.0 : 0.5;
  for (let v = Math.ceil(xMin / xTickStep) * xTickStep; v <= xMax; v += xTickStep) {{
    const xp = x(v);
    svgInner += `<line x1="${{xp}}" y1="${{M.top + PH}}" x2="${{xp}}" y2="${{M.top + PH + 4}}" stroke="#b0c0d4"/>`;
    svgInner += `<text class="axis-tick" x="${{xp}}" y="${{M.top + PH + 18}}" text-anchor="middle">${{v.toFixed(1)}}</text>`;
  }}
  const yTickStep = (yMax - yMin) > 80 ? 20 : 10;
  for (let v = Math.ceil(yMin / yTickStep) * yTickStep; v <= yMax; v += yTickStep) {{
    const yp = y(v);
    svgInner += `<line x1="${{M.left - 4}}" y1="${{yp}}" x2="${{M.left}}" y2="${{yp}}" stroke="#b0c0d4"/>`;
    svgInner += `<text class="axis-tick" x="${{M.left - 6}}" y="${{yp + 3}}" text-anchor="end">${{v}}</text>`;
  }}

  // Axis labels
  svgInner += `<text class="axis-label" x="${{M.left + PW / 2}}" y="${{H - 12}}" text-anchor="middle">grit_z_blend</text>`;
  svgInner += `<text class="axis-label" x="${{16}}" y="${{M.top + PH / 2}}" text-anchor="middle" transform="rotate(-90 16 ${{M.top + PH / 2}})">Points</text>`;

  // COMPARE SEASON DOTS + QUADRANT-CHANGE ARROWS
  // Compare dots are ghostly (30% opacity) and not interactive.
  // Arrows only for players whose quadrant changed between the two seasons.
  if (compareRows.length > 0) {{
    // Build lookup from compareRows so we can find each player by id
    const compareByPid = new Map(compareRows.map(r => [r.player_id, r]));

    // Compare dots first (under primary dots)
    compareRows.forEach(r => {{
      const color = QUAD_COLORS[r.quadrant] || "#888";
      svgInner += `<circle class="compare-dot" cx="${{x(r.grit_z_blend)}}" cy="${{y(r.points)}}" r="4" fill="${{color}}"/>`;
    }});

    // Quadrant-change arrows (FROM compare-season position TO primary-season position)
    currentRows.forEach(r => {{
      const c = compareByPid.get(r.player_id);
      if (!c) return;
      if (c.quadrant === r.quadrant) return;  // only changed-quadrant arrows
      const x1 = x(c.grit_z_blend), y1 = y(c.points);
      const x2 = x(r.grit_z_blend),  y2 = y(r.points);
      // Shrink the arrow target a bit so the head doesn't sit under the primary dot
      const dx = x2 - x1, dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const shrink = 6;
      const ex = x2 - (dx / len) * shrink;
      const ey = y2 - (dy / len) * shrink;
      svgInner += `<line class="compare-arrow" x1="${{x1}}" y1="${{y1}}" x2="${{ex}}" y2="${{ey}}"/>`;
    }});
  }}

  // PRIMARY DOTS
  currentRows.forEach((r, i) => {{
    const color = QUAD_COLORS[r.quadrant] || "#888";
    svgInner += `<circle class="dot" cx="${{x(r.grit_z_blend)}}" cy="${{y(r.points)}}" r="4" fill="${{color}}" fill-opacity="0.78" data-idx="${{i}}"/>`;
  }});

  // AGE <= 25 ORANGE RINGS (drawn over dots, non-interactive)
  if (ageHiEl.checked) {{
    currentRows.forEach(r => {{
      if (r.age == null || r.age > 25) return;
      svgInner += `<circle class="age-ring" cx="${{x(r.grit_z_blend)}}" cy="${{y(r.points)}}" r="6.5"/>`;
    }});
  }}

  // Pinned-labels layer (populated after innerHTML set)
  svgInner += `<g id="pins"></g>`;

  svg.innerHTML = svgInner;
  pinsLayer = document.getElementById("pins");

  // Reset trajectory state on each (re)render
  activeIdx = null;
  drawActive();

  svg.querySelectorAll(".dot").forEach(dot => {{
    dot.addEventListener("mouseenter", e => {{
      const r = currentRows[parseInt(e.target.dataset.idx)];
      const ageStr = r.age != null ? `age ${{r.age}}` : "age ?";
      tooltip.innerHTML =
        `<strong>${{r.name}}</strong> (${{r.team}} · ${{r.position}} · ${{ageStr}})<br>` +
        `pts=${{r.points}} · grit_z=${{r.grit_z_blend.toFixed(2)}} · ${{r.quadrant}}<br>` +
        `<em style="opacity:0.7">click to see career trajectory</em>`;
      tooltip.style.visibility = "visible";
    }});
    dot.addEventListener("mousemove", e => {{
      tooltip.style.left = (e.pageX) + "px";
      tooltip.style.top = (e.pageY) + "px";
    }});
    dot.addEventListener("mouseleave", () => {{
      tooltip.style.visibility = "hidden";
    }});
    dot.addEventListener("click", e => {{
      e.stopPropagation();
      const i = parseInt(e.target.dataset.idx);
      activeIdx = (activeIdx === i) ? null : i;
      drawActive();
    }});
  }});

  svg.addEventListener("click", e => {{
    if (!e.target.classList.contains("dot")) {{
      activeIdx = null;
      drawActive();
    }}
  }});
}}

// Search: set activeIdx to the FIRST match. Single-trajectory mode means
// only one player is "active" — search replaces whoever was active before.
function handleSearch() {{
  const q = searchEl.value.trim().toLowerCase();
  if (q.length < 2) return;
  for (let i = 0; i < currentRows.length; i++) {{
    if (currentRows[i].name.toLowerCase().includes(q)) {{
      activeIdx = i;
      drawActive();
      return;
    }}
  }}
  // No match — leave existing active player alone
}}

searchEl.addEventListener("keydown", e => {{
  if (e.key === "Enter") handleSearch();
}});
searchEl.addEventListener("input", () => {{
  if (searchEl.value.trim().length >= 3) handleSearch();
}});

// Re-render when any filter/compare/age control changes
[posCEl, posWEl, teamEl, ageHiEl, compareEl].forEach(el => {{
  el.addEventListener("change", () => render(seasonEl.value));
}});

seasonEl.addEventListener("change", () => {{
  searchEl.value = "";
  render(seasonEl.value);
}});

// PNG export: serialize the SVG, draw onto a canvas, trigger download
pngBtnEl.addEventListener("click", () => {{
  const svgEl = document.getElementById("plot");
  const xml = new XMLSerializer().serializeToString(svgEl);
  // Inline CSS so the exported PNG uses our colors
  const style = `
    <style>
      .axis-label {{ fill: #e6edf3; font-size: 12px; font-weight: 500; font-family: sans-serif; }}
      .axis-tick text {{ fill: #8b949e; font-size: 11px; font-family: sans-serif; }}
      .quad-label {{ fill: #e6edf3; font-size: 12px; font-weight: 600; opacity: 0.65; font-family: sans-serif; }}
      .med-label {{ fill: #e6edf3; font-size: 10px; font-weight: 600; font-family: monospace; }}
      .pin-text {{ fill: white; font-size: 11px; font-weight: 500; font-family: sans-serif; }}
      .pin-bg {{ fill: #000; stroke: #f9a03f; stroke-width: 1; }}
      .traj-line {{ fill: none; stroke: #f9a03f; stroke-width: 1.5; stroke-dasharray: 3,2; opacity: 0.7; }}
      .compare-arrow {{ fill: none; stroke: #f9a03f; stroke-width: 1; opacity: 0.55; }}
      .compare-dot {{ fill-opacity: 0.30; }}
      .age-ring {{ fill: none; stroke: #f9a03f; stroke-width: 1.5; }}
    </style>
  `;
  // Wrap with explicit svg namespace + background rect
  const w = svgEl.getAttribute("width");
  const h = svgEl.getAttribute("height");
  const wrapped = `<svg xmlns="http://www.w3.org/2000/svg" width="${{w}}" height="${{h}}">
    ${{style}}
    <rect width="100%" height="100%" fill="#0d1117"/>
    ${{xml.replace(/^<svg[^>]*>/, "").replace(/<\\/svg>$/, "")}}
  </svg>`;

  const img = new Image();
  img.onload = () => {{
    const canvas = document.createElement("canvas");
    canvas.width = parseInt(w, 10) * 2;   // 2x for retina
    canvas.height = parseInt(h, 10) * 2;
    const ctx = canvas.getContext("2d");
    ctx.scale(2, 2);
    ctx.drawImage(img, 0, 0);
    canvas.toBlob(blob => {{
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const season = seasonEl.value;
      const cmp = compareEl.value ? `_vs_${{compareEl.value}}` : "";
      a.href = url;
      a.download = `eyp_scatter_${{season}}${{cmp}}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }}, "image/png");
  }};
  const blob = new Blob([wrapped], {{ type: "image/svg+xml" }});
  img.src = URL.createObjectURL(blob);
}});

render(seasonEl.value);
</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    print(f"  wrote {output_path}  ({sum(len(v) for v in season_data.values())} total qualifier-seasons)")


# =============================================================================
# Main
# =============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                    help=f"Where the CSV inputs live (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                    help=f"Where to write HTML outputs (default: {DEFAULT_OUTPUT_DIR})")
    args = ap.parse_args()

    # 1. Load career pivot CSV (already built by build_eyp_career.py)
    career_path = args.data_dir / "eyp_career_v31.csv"
    if not career_path.exists():
        print(f"ERROR: {career_path} not found. Run build_eyp_career.py first.",
              file=sys.stderr)
        sys.exit(1)
    career_df = pd.read_csv(career_path)
    print(f"Loaded {career_path}  ({len(career_df)} rows)")

    # 2. Pull per-season qualifiers from SQL for the scatter
    engine = get_engine()
    print("Loading per-season qualifier data...")
    season_data = {}
    for s in ALL_RS_SEASONS:
        df = load_season_qualifiers(engine, str(s))
        if df.empty:
            print(f"  [{s}] no data")
            continue
        season_data[s] = df.to_dict(orient="records")
        print(f"  [{s}] {len(df)} qualifiers")

    # 3. Build both HTMLs to the viz output dir
    args.output_dir.mkdir(parents=True, exist_ok=True)
    table_path = args.output_dir / "eyp_career_v31.html"
    scatter_path = args.output_dir / "eyp_career_scatter_v31.html"
    build_table_html(career_df, table_path)
    build_scatter_html(season_data, scatter_path)
    print("\nDone.")


if __name__ == "__main__":
    main()
