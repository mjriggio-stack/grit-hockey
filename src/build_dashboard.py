#!/usr/bin/env python3
"""
build_dashboard.py — generate grit_dashboard_v3_{season}.html from a v3 per_60 CSV.

Handles BOTH regular season and playoffs via --season arg, mirroring the
build_player_cards.py pattern. The same script that produces
grit_dashboard_v3_2026.html with `--season 2026` produces
grit_dashboard_v3_2026_playoffs.html with `--season 2026_playoffs`.

Reads:
    grit_per_60_v3_{season}.csv     (in --data-dir or its season subfolder)

Writes:
    grit_dashboard_v3_{season}.html (in --output-dir)

The HTML embeds the per-player rows inline as `const EMBEDDED = [...]`. No
external fetches at runtime. The "Upload CSV" affordance is preserved so a
user can drop in a different season's CSV without touching disk.

Layout matches the existing grit_dashboard_v3.html exactly:
    - Header: title + V3 badge + position toggle (ALL/C/W/D) + Export/Share/Upload
    - Status row + 4 meta cards (Players, C/W/D split, Avg Grit/60, League Leader)
    - Two-panel grid: Leaderboard table (left) + ATOI vs Grit/60 scatter (right)

CSS palette (--bg #0d1117, --orange #f9a03f, C #58a6ff, W #3fb950, D #f85149).

Usage:
    python build_dashboard.py --season 2026 \\
        --data-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3\\data" \\
        --output-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\GitHub\\grit-hockey"

    python build_dashboard.py --season 2026_playoffs \\
        --data-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3\\data" \\
        --output-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\GitHub\\grit-hockey"

Season tag convention follows build_v3.py / build_player_cards.py:
    2026          -> 2025-26 Regular Season
    2026_playoffs -> 2025-26 Playoffs
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


# ============================================================================
# Columns embedded into the HTML. Anything the leaderboard, scatter, meta row,
# or Export-CSV button needs must be in this list. Raw event columns are
# preserved so Export CSV from the dashboard yields the same shape as the
# source per_60 CSV.
# ============================================================================

EMBED_COLS = [
    "player_id", "name", "position", "team",
    "games_played", "toi_min", "weighted_total",
    "raw_grit_per_60", "grit_per_game",
    "grit_z_pos", "grit_z_vol", "grit_z_blend",
    "raw_blocked_shots", "raw_blocked_shots_hd", "raw_blocked_shots_non_hd",
    "raw_crease_goals", "raw_dz_faceoff_wins", "raw_fighting_majors",
    "raw_giveaways_dz", "raw_giveaways_nz", "raw_giveaways_oz",
    "raw_hits_taken", "raw_hits_thrown",
    "raw_penalties_drawn", "raw_physical_minors_taken",
    "raw_takeaways_high_danger", "raw_takeaways_other",
]


def derive_pool(position: str) -> str:
    """C/W/D pooling — matches build_v3.py.

    Centers in their own pool. L/R wingers pooled together. D unchanged.
    """
    pos = (position or "").strip().upper()
    if pos == "C":
        return "C"
    if pos in ("L", "R", "LW", "RW", "W"):
        return "W"
    if pos == "D":
        return "D"
    # Fallback: anything weird gets dropped from the pool toggle but stays
    # visible under "ALL". Use the raw position string as the pool tag.
    return pos or "?"


def season_title(season_tag: str) -> str:
    """2026 -> '2025-26 Regular Season'.  2026_playoffs -> '2025-26 Playoffs'."""
    is_playoffs = season_tag.endswith("_playoffs")
    year_part = season_tag.replace("_playoffs", "")
    try:
        end_year = int(year_part)
    except ValueError:
        return season_tag  # Fallback: just show the raw tag
    start_year = end_year - 1
    label = "Playoffs" if is_playoffs else "Regular Season"
    return f"{start_year}-{str(end_year)[-2:]} {label}"


def find_input_csv(data_dir: Path, season_tag: str) -> Path:
    """Look for grit_per_60_v3_{season}.csv in:
       1. data_dir/{season}/grit_per_60_v3_{season}.csv  (build_v3.py layout)
       2. data_dir/grit_per_60_v3_{season}.csv           (flat layout)
    """
    fname = f"grit_per_60_v3_{season_tag}.csv"
    candidates = [data_dir / season_tag / fname, data_dir / fname]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Could not find {fname} in either {candidates[0]} or {candidates[1]}"
    )


def build_records(csv_path: Path) -> list[dict]:
    """Read the per_60 CSV, restrict to embed cols, add pool + atoi_min."""
    df = pd.read_csv(csv_path)

    missing = [c for c in EMBED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input CSV missing required columns: {missing}\n"
            f"Columns present: {list(df.columns)}"
        )

    df = df[EMBED_COLS].copy()

    # Pool for the position toggle — derived once here so the JS doesn't have to.
    df["pool"] = df["position"].apply(derive_pool)

    # ATOI in minutes, rounded to 2dp. NaN-safe.
    df["atoi_min"] = (
        df.apply(
            lambda r: round(r["toi_min"] / r["games_played"], 2)
            if pd.notna(r["games_played"]) and r["games_played"] > 0
            else 0.0,
            axis=1,
        )
    )

    # Sort by Z desc — initial paint is sorted, the JS re-sorts on filter change.
    df = df.sort_values("grit_z_blend", ascending=False, kind="stable")

    # Replace NaN with None so JSON serialization yields `null`, not `NaN`.
    df = df.where(pd.notna(df), None)

    return df.to_dict(orient="records")


# ============================================================================
# HTML template. The {DATA_JSON}, {TITLE_LONG}, {SEASON_TAG} tokens are the
# only thing that changes between RS and playoffs. CSS + JS are byte-identical
# across runs.
# ============================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>GRIT v3 Dashboard · __TITLE_SHORT__</title>
<style>
  :root {
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
    --c-col: #58a6ff;
    --w-col: #3fb950;
    --d-col: #f85149;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg); color: var(--text);
    padding: 20px; min-height: 100vh;
  }
  .header {
    border-bottom: 1px solid var(--border);
    padding-bottom: 16px; margin-bottom: 20px;
    display: flex; justify-content: space-between;
    align-items: flex-end; flex-wrap: wrap; gap: 12px;
  }
  h1 { font-size: 22px; font-weight: 600; letter-spacing: -0.3px; display:flex; align-items:center; gap:8px; }
  h1 .sub { color: var(--text-dim); font-weight: 400; font-size: 14px; }
  .v3badge {
    background: var(--orange); color: #0d1117;
    font-size: 11px; font-weight: 700;
    padding: 2px 7px; border-radius: 3px; letter-spacing: 1px;
  }
  .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .btn {
    color: white; padding: 7px 14px; border: none;
    border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
  }
  .btn-upload { background: var(--accent); }
  .btn-upload:hover { background: #d0422f; }
  .btn-export { background: var(--panel); border: 1px solid var(--border); color: var(--text-dim); }
  .btn-export:hover { color: var(--text); border-color: var(--accent-2); }
  .btn-share { background: var(--panel); border: 1px solid var(--border); color: var(--text-dim); }
  .btn-share:hover { color: var(--text); border-color: var(--orange); }
  input[type="file"] { display: none; }
  .toggle-group {
    display: flex; background: var(--panel);
    border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
  }
  .toggle-btn {
    background: transparent; color: var(--text-dim);
    border: none; padding: 7px 14px; cursor: pointer;
    font-size: 13px; transition: all 0.15s;
  }
  .toggle-btn:hover { color: var(--text); }
  .toggle-btn.active { background: var(--panel-2); color: var(--text); }
  .status {
    color: var(--text-dim); font-size: 13px;
    padding: 6px 12px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 6px;
  }
  .meta-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }
  .meta-card {
    background: var(--panel); border: 1px solid var(--border);
    padding: 12px 14px; border-radius: 6px;
  }
  .meta-label {
    color: var(--text-dim); font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
  }
  .meta-value { font-size: 20px; font-weight: 600; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
  .panel {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }
  .panel-title {
    font-size: 14px; font-weight: 600; color: var(--text);
    margin-bottom: 12px; display: flex;
    justify-content: space-between; align-items: center;
  }
  .panel-title .hint { color: var(--text-dim); font-weight: 400; font-size: 11px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left; padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    color: var(--text-dim); font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.4px;
    font-size: 11px; cursor: pointer; user-select: none;
  }
  th:hover { color: var(--text); }
  th.sorted { color: var(--accent); }
  td { padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
  tr:hover td { background: rgba(255,255,255,0.02); }
  tr.selected td { background: rgba(248,81,73,0.08); }
  .pos-badge {
    display: inline-block; padding: 1px 6px; border-radius: 3px;
    font-size: 10px; font-weight: 600; text-transform: uppercase;
  }
  .pos-C { background: rgba(88,166,255,0.2); color: var(--c-col); }
  .pos-W { background: rgba(63,185,80,0.2); color: var(--w-col); }
  .pos-D { background: rgba(248,81,73,0.2); color: var(--d-col); }
  .rank { color: var(--text-dim); font-variant-numeric: tabular-nums; }
  .z-score { font-weight: 600; font-variant-numeric: tabular-nums; }
  .z-pos { color: var(--good); }
  .z-neg { color: var(--text-dim); }
  .num { font-variant-numeric: tabular-nums; text-align: right; }
  .table-wrap { max-height: 620px; overflow-y: auto; }
  .table-wrap::-webkit-scrollbar { width: 8px; }
  .table-wrap::-webkit-scrollbar-track { background: var(--panel); }
  .table-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  #scatter-container { height: 560px; position: relative; }
  .empty { text-align: center; padding: 60px 20px; color: var(--text-dim); }
  .empty h2 { font-size: 16px; margin-bottom: 8px; color: var(--text); }
  .empty p { font-size: 13px; max-width: 400px; margin: 0 auto; line-height: 1.5; }
  .legend { display: flex; gap: 14px; font-size: 12px; color: var(--text-dim); }
  .legend-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 4px; vertical-align: middle;
  }
  .search-input {
    background: var(--panel-2); border: 1px solid var(--border);
    color: var(--text); padding: 6px 10px; border-radius: 4px;
    font-size: 12px; width: 160px;
  }
  .search-input:focus { outline: none; border-color: var(--accent-2); }
  #toast {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    background: #1c232d; border: 1px solid var(--orange);
    color: var(--text); padding: 10px 20px; border-radius: 6px;
    font-size: 13px; display: none; z-index: 100;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
</style>
</head>
<body>

<div class="header">
  <h1>GRIT <span class="v3badge">v3</span> <span class="sub">__TITLE_LONG__</span></h1>
  <div class="controls">
    <input type="text" id="search" class="search-input" placeholder="Search player..." />
    <div class="toggle-group">
      <button class="toggle-btn active" data-pos="ALL">All</button>
      <button class="toggle-btn" data-pos="C">C</button>
      <button class="toggle-btn" data-pos="W">W</button>
      <button class="toggle-btn" data-pos="D">D</button>
    </div>
    <button class="btn btn-export" id="btn-export">⬇ Export CSV</button>
    <button class="btn btn-share" id="btn-share">🔗 Share Player</button>
    <label class="btn btn-upload">
      Upload CSV
      <input type="file" id="file-input" accept=".csv" />
    </label>
  </div>
</div>

<div id="status" class="status" style="margin-bottom: 20px;">
  Data loaded · __TITLE_LONG__ · v3
</div>

<div id="meta" class="meta-row"></div>

<div id="main">
  <div class="grid">
    <div class="panel">
      <div class="panel-title">
        Leaderboard
        <span class="hint">Click column to sort · Click row to highlight</span>
      </div>
      <div class="table-wrap">
        <table id="leaderboard">
          <thead>
            <tr>
              <th data-col="rank">#</th>
              <th data-col="name">Player</th>
              <th data-col="position">Pos</th>
              <th data-col="team">Team</th>
              <th data-col="games_played" class="num">GP</th>
              <th data-col="atoi_min" class="num">ATOI</th>
              <th data-col="raw_grit_per_60" class="num">Grit/60</th>
              <th data-col="grit_z_blend" class="num sorted">Z</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">
        ATOI vs Grit/60
        <div class="legend">
          <span><span class="legend-dot" style="background:var(--c-col)"></span>C</span>
          <span><span class="legend-dot" style="background:var(--w-col)"></span>W</span>
          <span><span class="legend-dot" style="background:var(--d-col)"></span>D</span>
        </div>
      </div>
      <div id="scatter-container">
        <svg id="scatter" width="100%" height="100%"></svg>
        <div id="scatter-tooltip" style="position:absolute;display:none;pointer-events:none;background:#161b22;border:1px solid #30363d;padding:8px 10px;border-radius:4px;font-size:12px;color:#e6edf3;z-index:10;"></div>
      </div>
    </div>
  </div>
</div>

<div id="empty" class="empty" style="display:none;">
  <h2>No data loaded</h2>
  <p>Upload a <code>grit_per_60_v3_YYYY.csv</code> file to load a different season.</p>
</div>

<div id="toast"></div>

<script>
const SEASON_TAG = "__SEASON_TAG__";
const EMBEDDED = __DATA_JSON__;

let players = [];
let filteredPlayers = [];
let positionFilter = "ALL";
let searchTerm = "";
let sortCol = "grit_z_blend";
let sortDir = "desc";
let selectedPlayerId = null;

// Pool fallback for CSVs uploaded at runtime that lack a derived pool col.
function derivePool(position) {
  const p = String(position || "").trim().toUpperCase();
  if (p === "C") return "C";
  if (p === "L" || p === "R" || p === "LW" || p === "RW" || p === "W") return "W";
  if (p === "D") return "D";
  return p || "?";
}

function loadData(rows) {
  players = rows
    .filter(r => r && r.name)
    .map(r => ({
      ...r,
      pool: r.pool || derivePool(r.position),
      atoi_min: (r.atoi_min !== undefined && r.atoi_min !== null && r.atoi_min !== "")
        ? +r.atoi_min
        : ((r.games_played > 0) ? +(r.toi_min / r.games_played).toFixed(2) : 0),
    }));

  document.getElementById("empty").style.display = "none";
  document.getElementById("main").style.display = "block";
  document.getElementById("meta").style.display = "grid";
  document.getElementById("status").textContent =
    `${players.length} qualifying players loaded`;
  renderMeta();
  applyFiltersAndRender();
}

function renderMeta() {
  const cs = players.filter(p => p.pool === "C").length;
  const ws = players.filter(p => p.pool === "W").length;
  const ds = players.filter(p => p.pool === "D").length;
  const avgGrit = players.length
    ? players.reduce((s, p) => s + (p.raw_grit_per_60 || 0), 0) / players.length
    : 0;
  const maxZ = players.length
    ? Math.max(...players.map(p => p.grit_z_blend || -Infinity))
    : 0;
  const topPlayer = players.find(p => p.grit_z_blend === maxZ);
  document.getElementById("meta").innerHTML = `
    <div class="meta-card"><div class="meta-label">Players</div><div class="meta-value">${players.length}</div></div>
    <div class="meta-card"><div class="meta-label">C / W / D</div><div class="meta-value" style="font-size:17px">${cs} / ${ws} / ${ds}</div></div>
    <div class="meta-card"><div class="meta-label">League Avg Grit/60</div><div class="meta-value">${avgGrit.toFixed(2)}</div></div>
    <div class="meta-card"><div class="meta-label">League Leader</div><div class="meta-value" style="font-size:15px">${topPlayer ? escapeHtml(topPlayer.name) : "—"}</div></div>
  `;
}

document.querySelectorAll(".toggle-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    positionFilter = btn.dataset.pos;
    applyFiltersAndRender();
  });
});

document.getElementById("search").addEventListener("input", e => {
  searchTerm = e.target.value.toLowerCase().trim();
  applyFiltersAndRender();
});

document.querySelectorAll("#leaderboard th").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.col;
    if (col === "rank") return;
    if (sortCol === col) {
      sortDir = sortDir === "desc" ? "asc" : "desc";
    } else {
      sortCol = col;
      sortDir = (col === "name" || col === "position" || col === "team") ? "asc" : "desc";
    }
    applyFiltersAndRender();
  });
});

function applyFiltersAndRender() {
  filteredPlayers = players.filter(p => {
    if (positionFilter !== "ALL" && p.pool !== positionFilter) return false;
    if (searchTerm && !p.name.toLowerCase().includes(searchTerm)) return false;
    return true;
  });
  filteredPlayers.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (av === undefined || av === null) av = (typeof bv === "string") ? "" : -Infinity;
    if (bv === undefined || bv === null) bv = (typeof av === "string") ? "" : -Infinity;
    if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortDir === "asc" ? (av - bv) : (bv - av);
  });
  renderTable();
  renderScatter();
}

function renderTable() {
  const tbody = document.querySelector("#leaderboard tbody");
  tbody.innerHTML = "";
  document.querySelectorAll("#leaderboard th").forEach(th => {
    th.classList.toggle("sorted", th.dataset.col === sortCol);
  });
  filteredPlayers.forEach((p, i) => {
    const tr = document.createElement("tr");
    if (p.player_id === selectedPlayerId) tr.classList.add("selected");
    tr.dataset.playerId = p.player_id;
    tr.innerHTML = `
      <td class="rank">${i + 1}</td>
      <td>${escapeHtml(p.name)}</td>
      <td><span class="pos-badge pos-${p.pool}">${escapeHtml(p.position || "")}</span></td>
      <td>${escapeHtml(p.team || "")}</td>
      <td class="num">${p.games_played || 0}</td>
      <td class="num">${(p.atoi_min || 0).toFixed(1)}</td>
      <td class="num">${(p.raw_grit_per_60 || 0).toFixed(2)}</td>
      <td class="num z-score ${(p.grit_z_blend || 0) >= 0 ? 'z-pos' : 'z-neg'}">${(p.grit_z_blend || 0).toFixed(2)}</td>
    `;
    tr.addEventListener("click", () => {
      selectedPlayerId = (selectedPlayerId === p.player_id) ? null : p.player_id;
      renderTable();
      renderScatter();
    });
    tbody.appendChild(tr);
  });
}

const POOL_RGB = {
  "C": "88,166,255",
  "W": "63,185,80",
  "D": "248,81,73",
};

function el(tag, attrs) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

function renderScatter() {
  const svg = document.getElementById("scatter");
  const tooltip = document.getElementById("scatter-tooltip");
  const container = document.getElementById("scatter-container");
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const W = container.clientWidth, H = container.clientHeight;
  const PAD = { t: 20, r: 20, b: 50, l: 60 };
  const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const data = filteredPlayers.map(p => ({
    x: p.atoi_min, y: p.raw_grit_per_60,
    name: p.name, id: p.player_id,
    z: p.grit_z_blend, pool: p.pool,
    toi: p.toi_min, gp: p.games_played, team: p.team
  })).filter(d => isFinite(d.x) && isFinite(d.y));
  if (!data.length) return;

  const xs = data.map(d => d.x), ys = data.map(d => d.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xPad = (xMax - xMin) * 0.05 || 1;
  const yPad = (yMax - yMin) * 0.05 || 1;
  const x0 = xMin - xPad, x1 = xMax + xPad;
  const y0 = yMin - yPad, y1 = yMax + yPad;
  const scaleX = v => PAD.l + ((v - x0) / (x1 - x0)) * plotW;
  const scaleY = v => PAD.t + plotH - ((v - y0) / (y1 - y0)) * plotH;

  // Axis lines
  svg.appendChild(el("line", {
    x1: PAD.l, y1: PAD.t + plotH, x2: PAD.l + plotW, y2: PAD.t + plotH,
    stroke: "#30363d", "stroke-width": 1
  }));
  svg.appendChild(el("line", {
    x1: PAD.l, y1: PAD.t, x2: PAD.l, y2: PAD.t + plotH,
    stroke: "#30363d", "stroke-width": 1
  }));

  // Tick marks + labels
  const xTicks = 5, yTicks = 5;
  for (let i = 0; i <= xTicks; i++) {
    const v = x0 + (x1 - x0) * (i / xTicks);
    const xPx = scaleX(v);
    svg.appendChild(el("line", {
      x1: xPx, y1: PAD.t + plotH, x2: xPx, y2: PAD.t + plotH + 4,
      stroke: "#30363d"
    }));
    const t = el("text", {
      x: xPx, y: PAD.t + plotH + 18, "text-anchor": "middle",
      fill: "#8b949e", "font-size": 11
    });
    t.textContent = v.toFixed(1);
    svg.appendChild(t);
  }
  for (let i = 0; i <= yTicks; i++) {
    const v = y0 + (y1 - y0) * (i / yTicks);
    const yPx = scaleY(v);
    svg.appendChild(el("line", {
      x1: PAD.l - 4, y1: yPx, x2: PAD.l, y2: yPx, stroke: "#30363d"
    }));
    const t = el("text", {
      x: PAD.l - 8, y: yPx + 4, "text-anchor": "end",
      fill: "#8b949e", "font-size": 11
    });
    t.textContent = v.toFixed(0);
    svg.appendChild(t);
  }

  // Axis labels
  const xLabel = el("text", {
    x: PAD.l + plotW / 2, y: H - 12, "text-anchor": "middle",
    fill: "#8b949e", "font-size": 12
  });
  xLabel.textContent = "ATOI (min)";
  svg.appendChild(xLabel);

  const yLabel = el("text", {
    x: 18, y: PAD.t + plotH / 2,
    "text-anchor": "middle", fill: "#8b949e", "font-size": 12,
    transform: `rotate(-90 18 ${PAD.t + plotH / 2})`
  });
  yLabel.textContent = "Grit/60";
  svg.appendChild(yLabel);

  // Points
  data.forEach(d => {
    const isSelected = (d.id === selectedPlayerId);
    const rgb = POOL_RGB[d.pool] || "139,148,158";
    const base = `rgba(${rgb},`;
    const fill = isSelected ? "#ffdf5d" : base + "0.55)";
    const stroke = isSelected ? "#ffffff" : base + "0.9)";
    const r = isSelected ? 7 : 4;
    const c = el("circle", {
      cx: scaleX(d.x), cy: scaleY(d.y), r,
      fill, stroke, "stroke-width": isSelected ? 2 : 1, style: "cursor:pointer"
    });
    c.addEventListener("mouseenter", () => {
      c.setAttribute("r", isSelected ? 9 : 7);
      tooltip.style.display = "block";
      tooltip.innerHTML = `<strong>${escapeHtml(d.name)}</strong> · ${escapeHtml(d.team || "")}<br>` +
        `${d.gp} GP · ATOI: ${d.x.toFixed(1)} min<br>` +
        `Grit/60: ${d.y.toFixed(2)} · Z: ${(d.z || 0).toFixed(2)}`;
    });
    c.addEventListener("mousemove", evt => {
      const rect = container.getBoundingClientRect();
      tooltip.style.left = (evt.clientX - rect.left + 12) + "px";
      tooltip.style.top  = (evt.clientY - rect.top  + 12) + "px";
    });
    c.addEventListener("mouseleave", () => { c.setAttribute("r", r); tooltip.style.display = "none"; });
    c.addEventListener("click", () => {
      selectedPlayerId = (selectedPlayerId === d.id) ? null : d.id;
      renderTable(); renderScatter();
    });
    svg.appendChild(c);
  });
}

// ── Export CSV ──
document.getElementById("btn-export").addEventListener("click", () => {
  if (!filteredPlayers.length) { showToast("No data to export."); return; }
  const cols = ["name","position","team","games_played","atoi_min","toi_min",
    "raw_grit_per_60","grit_per_game","grit_z_pos","grit_z_vol","grit_z_blend",
    "raw_hits_thrown","raw_hits_taken","raw_blocked_shots","raw_blocked_shots_hd",
    "raw_blocked_shots_non_hd","raw_crease_goals","raw_dz_faceoff_wins",
    "raw_fighting_majors","raw_penalties_drawn","raw_physical_minors_taken",
    "raw_takeaways_high_danger","raw_takeaways_other",
    "raw_giveaways_dz","raw_giveaways_nz","raw_giveaways_oz"];
  const header = cols.join(",");
  const rows = filteredPlayers.map(p =>
    cols.map(c => {
      const v = p[c];
      if (v === null || v === undefined) return "";
      if (typeof v === "string" && v.includes(",")) return `"${v}"`;
      return v;
    }).join(",")
  );
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], {type:"text/csv"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const posTag = positionFilter === "ALL" ? "all" : positionFilter.toLowerCase();
  a.download = `grit_v3_${SEASON_TAG}_${posTag}.csv`;
  a.click();
  showToast("CSV exported.");
});

// ── Share selected player ──
document.getElementById("btn-share").addEventListener("click", () => {
  if (!selectedPlayerId) { showToast("Click a player first, then share."); return; }
  const p = players.find(pl => pl.player_id === selectedPlayerId);
  if (!p) return;
  const sign = (p.grit_z_blend || 0) >= 0 ? "+" : "";
  const text = `${p.name} (${p.position} · ${p.team}) — GRIT v3 Z: ${sign}${(p.grit_z_blend||0).toFixed(2)} | Grit/60: ${(p.raw_grit_per_60||0).toFixed(2)} | ${p.games_played} GP`;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => showToast("Copied to clipboard."));
  } else {
    showToast("Clipboard not available in this browser.");
  }
});

// ── Upload override ──
document.getElementById("file-input").addEventListener("change", e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      const rows = parseCSV(ev.target.result);
      loadData(rows);
    } catch(err) {
      document.getElementById("status").textContent = "Parse error: " + err.message;
    }
  };
  reader.readAsText(file);
});

function parseCSV(text) {
  text = text.replace(/\r\n/g,"\n").replace(/\r/g,"\n");
  const rows = []; let i = 0, n = text.length;
  while (i < n) {
    const row = []; let field = "", inQuote = false;
    while (i < n) {
      const c = text[i];
      if (inQuote) {
        if (c === '"') { if (text[i+1]==='"'){field+='"';i+=2;continue;} inQuote=false;i++;continue; }
        field += c; i++;
      } else {
        if (c==='"'){inQuote=true;i++;continue;}
        if (c===","){row.push(field);field="";i++;continue;}
        if (c==="\n"){i++;break;}
        field+=c;i++;
      }
    }
    row.push(field);
    if (!(row.length===1&&row[0]==="")) rows.push(row);
  }
  const headers = rows.shift() || [];
  return rows.map(r => {
    const obj = {};
    headers.forEach((h,idx) => {
      let v = r[idx] ?? "";
      if (v !== "" && /^-?\d+(\.\d+)?$/.test(v)) v = parseFloat(v);
      obj[h] = v;
    });
    return obj;
  });
}

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.style.display = "block";
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.display = "none"; }, 2500);
}

function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// Boot with embedded data
loadData(EMBEDDED);

// Re-render scatter on resize so it tracks panel width changes.
let _resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(renderScatter, 120);
});
</script>
</body>
</html>
"""


def render_html(records: list[dict], season_tag: str) -> str:
    title_long = season_title(season_tag)
    # Short title for the <title> tag — strip "Regular Season" but keep "Playoffs"
    # so browser tab text is "2025-26" or "2025-26 Playoffs".
    if title_long.endswith(" Regular Season"):
        title_short = title_long.replace(" Regular Season", "")
    else:
        title_short = title_long

    # Use json.dumps directly. The HTML template uses __TOKENS__ (not braces) so
    # JSON containing { } characters won't interfere with str.replace.
    data_json = json.dumps(records, separators=(",", ":"), ensure_ascii=False)

    html = HTML_TEMPLATE
    html = html.replace("__TITLE_LONG__", title_long)
    html = html.replace("__TITLE_SHORT__", title_short)
    html = html.replace("__SEASON_TAG__", season_tag)
    html = html.replace("__DATA_JSON__", data_json)
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season", required=True,
                        help="Season tag, e.g. 2026 or 2026_playoffs")
    parser.add_argument("--data-dir", required=True, type=Path,
                        help="Root data directory (will look in data-dir/{season}/ first, then data-dir/)")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Where to write grit_dashboard_v3_{season}.html")
    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = args.output_dir
    season = args.season

    if not data_dir.exists():
        print(f"ERROR: --data-dir does not exist: {data_dir}", file=sys.stderr)
        sys.exit(1)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = find_input_csv(data_dir, season)
    print(f"Reading {csv_path}")
    records = build_records(csv_path)
    print(f"  {len(records)} qualifying players")

    if records:
        top = records[0]
        print(f"  #1 by Z: {top['name']} ({top['position']} · {top['team']}) "
              f"Z={top['grit_z_blend']:.3f} Grit/60={top['raw_grit_per_60']:.2f}")

    html = render_html(records, season)

    out_path = output_dir / f"grit_dashboard_v3_{season}.html"
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
