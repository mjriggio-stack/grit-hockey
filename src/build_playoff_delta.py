#!/usr/bin/env python3
"""
build_playoff_delta.py — generate grit_playoff_delta.html showing per-player
RS-to-playoff rate inflation, with a season picker covering every season
that has both regular-season and playoff per_60 CSVs available.

Replaces the three one-off files:
    grit_playoff_delta_2324.html
    grit_playoff_delta_2425.html
    grit_playoff_delta_2526.html

The new file is a single HTML with a dropdown to switch between any season
that has a complete RS+PO pair. Currently auto-discovers all seasons in
--data-dir; defaults to the standard set if not specified.

Inflation = playoff Grit/60 / regular-season Grit/60. A value of 1.50 means
the player produced GRIT events at 1.5x their regular-season rate during the
playoffs. League-wide mean typically lands in the 1.25-1.50 range.

Output structure per season:
    - Headline meta cards: # players, mean inflation, median, top inflator
    - Inflation distribution histogram with mean/median markers
    - Player table: name, pos, team, RS GP, PO GP, RS Grit/60, PO Grit/60,
                    Inflation ratio (the headline column, sortable)
    - Team rollup: average inflation per team, sortable

Filtering: minimum 3 playoff GP (matches the per_60 qualification floor).

Reads:
    grit_per_60_v3_{season}.csv             (RS)
    grit_per_60_v3_{season}_playoffs.csv    (playoffs)

Writes:
    grit_playoff_delta.html  in --output-dir.

Usage:
    python build_playoff_delta.py \\
        --data-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3\\data" \\
        --output-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\GitHub\\grit-hockey"

    # Restrict to a specific season list:
    python build_playoff_delta.py \\
        --data-dir ... --output-dir ... --seasons 2024 2025 2026
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from grit_version import GRIT_VERSION


# ---------------------------------------------------------------------------
# Path anchoring. Script assumed to live at:
#     C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\source\build_playoff_delta.py
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
WORKING_DIR = SCRIPT_DIR.parent
GRIT_DIR = WORKING_DIR.parent
ONE_DRIVE_DOCS = GRIT_DIR.parent
DEFAULT_DATA_DIR = WORKING_DIR / "data"
DEFAULT_OUTPUT_DIR = ONE_DRIVE_DOCS / "GitHub" / "grit-hockey"


DEFAULT_SEASONS = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025, 2026]
MIN_PO_GP = 3  # matches the per_60 qualification floor


def season_label(s: int) -> str:
    return f"{s-1}-{str(s)[-2:]}"


def find_input_csv(data_dir: Path, season_tag: str) -> Path | None:
    """Find grit_per_60_v3_{season_tag}.csv with the build_v3.py layout."""
    fname = f"grit_per_60_v3_{season_tag}.csv"
    for p in [data_dir / season_tag / fname, data_dir / fname]:
        if p.exists():
            return p
    return None


def compute_season_pair(rs_path: Path, po_path: Path) -> dict:
    """Compute per-player inflation for one RS/PO season pair."""
    rs = pd.read_csv(rs_path)
    po = pd.read_csv(po_path)

    rs_cols = ["player_id", "name", "position", "team",
               "games_played", "toi_min", "raw_grit_per_60", "grit_z_blend"]
    po_cols = ["player_id", "team", "games_played", "toi_min",
               "raw_grit_per_60", "grit_z_blend"]
    missing = [c for c in rs_cols if c not in rs.columns]
    if missing:
        raise ValueError(f"RS file missing columns: {missing}")
    missing = [c for c in po_cols if c not in po.columns]
    if missing:
        raise ValueError(f"PO file missing columns: {missing}")

    m = rs[rs_cols].rename(columns={
        "games_played": "gp_rs",
        "toi_min": "toi_rs",
        "raw_grit_per_60": "g60_rs",
        "grit_z_blend": "z_rs",
    }).merge(
        po[po_cols].rename(columns={
            "team": "team_po",
            "games_played": "gp_po",
            "toi_min": "toi_po",
            "raw_grit_per_60": "g60_po",
            "grit_z_blend": "z_po",
        }),
        on="player_id",
    )

    # Filter to playoff-qualified players
    m = m[m["gp_po"] >= MIN_PO_GP].copy()

    # Avoid divide-by-zero on the rate ratio
    m = m[m["g60_rs"] > 0].copy()

    m["inflation"] = m["g60_po"] / m["g60_rs"]
    m["delta_g60"] = m["g60_po"] - m["g60_rs"]
    m["z_delta"] = m["z_po"] - m["z_rs"]

    # Use playoff team where present (handles trade-deadline moves)
    m["team_display"] = m["team_po"].fillna(m["team"])

    # Round numerics for embedding (smaller payload, no precision loss for display)
    for c in ["g60_rs", "g60_po", "z_rs", "z_po", "inflation", "delta_g60",
              "z_delta", "toi_rs", "toi_po"]:
        m[c] = m[c].round(4)

    # NaN-safe → JSON null
    m = m.where(pd.notna(m), None)

    return {
        "players": m[[
            "player_id", "name", "position", "team_display",
            "gp_rs", "toi_rs", "g60_rs", "z_rs",
            "gp_po", "toi_po", "g60_po", "z_po",
            "inflation", "delta_g60", "z_delta",
        ]].rename(columns={"team_display": "team"}).to_dict(orient="records"),
    }


def compute_summary(players: list[dict]) -> dict:
    """League-wide and team-level summary stats for one season."""
    if not players:
        return {"n": 0}

    df = pd.DataFrame(players)

    inf = df["inflation"]

    # Top inflator and top deflator
    top_idx = inf.idxmax()
    bot_idx = inf.idxmin()
    top_player = {
        "name": df.loc[top_idx, "name"],
        "team": df.loc[top_idx, "team"],
        "inflation": float(inf.loc[top_idx]),
    }
    bot_player = {
        "name": df.loc[bot_idx, "name"],
        "team": df.loc[bot_idx, "team"],
        "inflation": float(inf.loc[bot_idx]),
    }

    # Team rollup: weighted by playoff TOI so a 25-min defenseman counts more
    # than a 6-min fourth-liner. Drops teams with no players in this season.
    team_rows = []
    for team, sub in df.groupby("team"):
        toi_total = sub["toi_po"].sum()
        if toi_total <= 0:
            continue
        weighted_inf = (sub["inflation"] * sub["toi_po"]).sum() / toi_total
        team_rows.append({
            "team": team,
            "n_players": int(len(sub)),
            "mean_inflation": round(float(sub["inflation"].mean()), 4),
            "weighted_inflation": round(float(weighted_inf), 4),
            "median_inflation": round(float(sub["inflation"].median()), 4),
            "total_po_toi": round(float(toi_total), 1),
        })
    team_rows.sort(key=lambda r: r["weighted_inflation"], reverse=True)

    # Distribution bins for the histogram (0.5x-step buckets)
    bin_edges = [round(0.0 + 0.10 * i, 2) for i in range(31)]  # 0.0 to 3.0
    counts = [0] * (len(bin_edges) - 1)
    for v in inf:
        if v is None:
            continue
        for i in range(len(bin_edges) - 1):
            if bin_edges[i] <= v < bin_edges[i + 1]:
                counts[i] += 1
                break
        else:
            if v >= bin_edges[-1]:
                counts[-1] += 1  # overflow into top bucket

    return {
        "n": int(len(df)),
        "mean_inflation": round(float(inf.mean()), 4),
        "median_inflation": round(float(inf.median()), 4),
        "p10_inflation": round(float(inf.quantile(0.10)), 4),
        "p90_inflation": round(float(inf.quantile(0.90)), 4),
        "weighted_mean_inflation": round(
            float((df["inflation"] * df["toi_po"]).sum() / df["toi_po"].sum()), 4
        ),
        "top_inflator": top_player,
        "top_deflator": bot_player,
        "team_rollup": team_rows,
        "histogram": {"edges": bin_edges, "counts": counts},
    }


# ============================================================================
# HTML template
# ============================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>GRIT __VERSION__ · Playoff Rate Inflation</title>
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
  h1 { font-size: 22px; font-weight: 600; letter-spacing: -0.3px;
       display: flex; align-items: center; gap: 8px; }
  h1 .sub { color: var(--text-dim); font-weight: 400; font-size: 14px; }
  .v3badge {
    background: var(--orange); color: #0d1117;
    font-size: 11px; font-weight: 700;
    padding: 2px 7px; border-radius: 3px; letter-spacing: 1px;
  }
  .lede {
    color: var(--text-dim); font-size: 13px; line-height: 1.6;
    max-width: 900px; margin-top: 10px;
  }
  .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .season-select, .search-input {
    background: var(--panel-2); border: 1px solid var(--border);
    color: var(--text); padding: 7px 12px; border-radius: 6px;
    font-size: 13px;
  }
  .season-select { min-width: 140px; }
  .search-input { width: 180px; }
  .season-select:focus, .search-input:focus {
    outline: none; border-color: var(--accent-2);
  }
  .meta-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }
  .meta-card {
    background: var(--panel); border: 1px solid var(--border);
    padding: 12px 14px; border-radius: 6px;
  }
  .meta-label {
    color: var(--text-dim); font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
  }
  .meta-value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .meta-sub { color: var(--text-dim); font-size: 11px; margin-top: 2px; }

  .grid-2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 20px; margin-bottom: 24px; }
  @media (max-width: 1100px) { .grid-2 { grid-template-columns: 1fr; } }
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

  /* Tables */
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
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .table-wrap { max-height: 600px; overflow-y: auto; }
  .table-wrap::-webkit-scrollbar { width: 8px; }
  .table-wrap::-webkit-scrollbar-track { background: var(--panel); }
  .table-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  .pos-badge {
    display: inline-block; padding: 1px 6px; border-radius: 3px;
    font-size: 10px; font-weight: 600; text-transform: uppercase;
  }
  .pos-C { background: rgba(88,166,255,0.2); color: var(--c-col); }
  .pos-W { background: rgba(63,185,80,0.2); color: var(--w-col); }
  .pos-D { background: rgba(248,81,73,0.2); color: var(--d-col); }
  .pos-L, .pos-R { background: rgba(63,185,80,0.2); color: var(--w-col); }

  .inflation-strong { color: var(--good); font-weight: 600; }
  .inflation-mod    { color: var(--text); font-weight: 500; }
  .inflation-low    { color: var(--warn); }
  .inflation-neg    { color: var(--accent); }

  /* Histogram */
  #hist-container { height: 280px; position: relative; }

  .footnote {
    color: var(--text-dim); font-size: 11px; line-height: 1.6;
    margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border);
  }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>GRIT <span class="v3badge">__VERSION__</span> <span class="sub" id="season-sub">Playoff Rate Inflation</span></h1>
    <div class="lede">
      Inflation = playoff Grit/60 ÷ regular-season Grit/60. <strong>1.50</strong>
      means the player produced GRIT events at 1.5× their regular-season rate
      during the playoffs. Includes only players with ≥__MIN_GP__ playoff games.
    </div>
  </div>
  <div class="controls">
    <select class="season-select" id="season-select"></select>
    <input type="text" class="search-input" id="search" placeholder="Search player or team..." />
  </div>
</div>

<div id="meta" class="meta-row"></div>

<div class="grid-2">
  <div class="panel">
    <div class="panel-title">
      Inflation Distribution
      <span class="hint">League-wide histogram, 0.10 buckets</span>
    </div>
    <div id="hist-container">
      <svg id="hist-svg" width="100%" height="100%"></svg>
    </div>
  </div>

  <div class="panel">
    <div class="panel-title">
      Team Rollup
      <span class="hint">TOI-weighted mean inflation</span>
    </div>
    <div class="table-wrap">
      <table id="team-table">
        <thead>
          <tr>
            <th data-col="team">Team</th>
            <th data-col="n_players" class="num">Players</th>
            <th data-col="weighted_inflation" class="num sorted">W. Mean</th>
            <th data-col="mean_inflation" class="num">Mean</th>
            <th data-col="total_po_toi" class="num">PO TOI</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<div class="panel">
  <div class="panel-title">
    Player Inflation Table
    <span class="hint">Click column to sort</span>
  </div>
  <div class="table-wrap">
    <table id="players-table">
      <thead>
        <tr>
          <th data-col="name">Player</th>
          <th data-col="position">Pos</th>
          <th data-col="team">Team</th>
          <th data-col="gp_rs" class="num">RS GP</th>
          <th data-col="g60_rs" class="num">RS Grit/60</th>
          <th data-col="gp_po" class="num">PO GP</th>
          <th data-col="g60_po" class="num">PO Grit/60</th>
          <th data-col="inflation" class="num sorted">Inflation</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
  <div class="footnote">
    <strong>Reading the numbers.</strong> League-wide playoff inflation has averaged 1.26–1.49× across the
    nine-season window in this dataset, varying year to year. Hits and physical minors typically inflate
    most (often above 2×), reflecting playoff intensity; fighting majors usually <em>deflate</em>
    (around 0.5×) because designated fighters are healthy-scratched in the postseason. Individual
    player inflation reflects role change as much as effort: a depth player promoted up the lineup
    in playoffs will inflate by virtue of higher leverage minutes, not necessarily harder play.
  </div>
</div>

<script>
const SEASONS_DATA = __SEASONS_JSON__;
const MIN_GP = __MIN_GP__;

let currentSeason = null;
let searchTerm = "";
let playerSortCol = "inflation";
let playerSortDir = "desc";
let teamSortCol = "weighted_inflation";
let teamSortDir = "desc";

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function seasonLabel(s) {
  // Tag like "2026" -> "2024-25 Playoffs"... wait, no:
  //   2026 = 2025-26 season. Playoff that runs after the 2025-26 RS = "2025-26 Playoffs".
  const n = parseInt(s, 10);
  return (n - 1) + "-" + String(n).slice(-2) + " Playoffs";
}

function inflationClass(v) {
  if (v == null) return "";
  if (v >= 1.5) return "inflation-strong";
  if (v >= 1.2) return "inflation-mod";
  if (v >= 1.0) return "inflation-low";
  return "inflation-neg";
}

function posClass(p) {
  const x = String(p || "").toUpperCase();
  if (x === "C" || x === "W" || x === "D") return "pos-" + x;
  if (x === "L" || x === "R") return "pos-" + x;
  return "";
}

// ── Season picker ──
function buildSeasonPicker() {
  const sel = document.getElementById("season-select");
  // Most recent first
  const tags = Object.keys(SEASONS_DATA).sort().reverse();
  tags.forEach(t => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = seasonLabel(t);
    sel.appendChild(opt);
  });
  if (tags.length) {
    currentSeason = tags[0];
    sel.value = currentSeason;
  }
  sel.addEventListener("change", e => {
    currentSeason = e.target.value;
    renderAll();
  });
}

// ── Meta cards ──
function renderMeta() {
  const s = SEASONS_DATA[currentSeason];
  if (!s) return;
  const sm = s.summary;
  const card = (lbl, val, sub) => `<div class="meta-card">
    <div class="meta-label">${lbl}</div>
    <div class="meta-value">${val}</div>
    <div class="meta-sub">${sub || ""}</div>
  </div>`;
  document.getElementById("meta").innerHTML =
    card("Players", sm.n, `≥${MIN_GP} PO GP`) +
    card("Mean Inflation", sm.mean_inflation.toFixed(3) + "×",
         `Weighted: ${sm.weighted_mean_inflation.toFixed(3)}×`) +
    card("Median Inflation", sm.median_inflation.toFixed(3) + "×",
         `P10–P90: ${sm.p10_inflation.toFixed(2)}–${sm.p90_inflation.toFixed(2)}`) +
    card("Top Inflator", escapeHtml(sm.top_inflator.name),
         `${escapeHtml(sm.top_inflator.team)} · ${sm.top_inflator.inflation.toFixed(2)}×`);
  document.getElementById("season-sub").textContent =
    seasonLabel(currentSeason) + " · Rate Inflation";
}

// ── Histogram ──
function renderHistogram() {
  const s = SEASONS_DATA[currentSeason];
  if (!s) return;
  const svg = document.getElementById("hist-svg");
  const container = document.getElementById("hist-container");
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const W = container.clientWidth, H = container.clientHeight;
  const PAD = { t: 16, r: 16, b: 36, l: 36 };
  const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const ns = (tag, attrs) => {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  const edges = s.summary.histogram.edges;
  const counts = s.summary.histogram.counts;
  const xMin = edges[0], xMax = edges[edges.length - 1];
  const yMax = Math.max(...counts) || 1;

  const sx = v => PAD.l + ((v - xMin) / (xMax - xMin)) * plotW;
  const sy = v => PAD.t + plotH - (v / yMax) * plotH;

  // Bars
  for (let i = 0; i < counts.length; i++) {
    const c = counts[i];
    if (c === 0) continue;
    const x = sx(edges[i]);
    const w = sx(edges[i + 1]) - x - 1;
    const y = sy(c);
    const h = PAD.t + plotH - y;
    const center = (edges[i] + edges[i + 1]) / 2;
    const fill = center >= 1.5 ? "#3fb950"
               : center >= 1.0 ? "#58a6ff"
               : "#f85149";
    svg.appendChild(ns("rect", {
      x, y, width: w, height: h,
      fill, "fill-opacity": 0.65, stroke: fill, "stroke-width": 0.8
    }));
  }

  // Mean & median markers
  const drawMarker = (val, color, label) => {
    if (val < xMin || val > xMax) return;
    const x = sx(val);
    svg.appendChild(ns("line", {
      x1: x, y1: PAD.t, x2: x, y2: PAD.t + plotH,
      stroke: color, "stroke-width": 1.5, "stroke-dasharray": "4,3"
    }));
    const t = ns("text", {
      x: x + 4, y: PAD.t + 12, fill: color, "font-size": 11
    });
    t.textContent = label + " " + val.toFixed(2);
    svg.appendChild(t);
  };
  drawMarker(s.summary.mean_inflation, "#f9a03f", "mean");
  drawMarker(s.summary.median_inflation, "#e6edf3", "med");
  drawMarker(1.0, "#8b949e", "1.0");

  // X axis with ticks at 0.5 increments
  svg.appendChild(ns("line", {
    x1: PAD.l, y1: PAD.t + plotH, x2: PAD.l + plotW, y2: PAD.t + plotH,
    stroke: "#30363d"
  }));
  for (let v = 0.0; v <= xMax + 0.001; v += 0.5) {
    const x = sx(v);
    svg.appendChild(ns("line", {
      x1: x, y1: PAD.t + plotH, x2: x, y2: PAD.t + plotH + 4,
      stroke: "#30363d"
    }));
    const t = ns("text", {
      x, y: PAD.t + plotH + 18, "text-anchor": "middle",
      fill: "#8b949e", "font-size": 11
    });
    t.textContent = v.toFixed(1) + "×";
    svg.appendChild(t);
  }

  // Y axis label
  const yL = ns("text", {
    x: 8, y: PAD.t + plotH / 2,
    "text-anchor": "middle", fill: "#8b949e", "font-size": 11,
    transform: `rotate(-90 8 ${PAD.t + plotH / 2})`
  });
  yL.textContent = "Players";
  svg.appendChild(yL);
}

// ── Player table ──
function renderPlayers() {
  const s = SEASONS_DATA[currentSeason];
  if (!s) return;
  const tbody = document.querySelector("#players-table tbody");
  tbody.innerHTML = "";
  document.querySelectorAll("#players-table th").forEach(th => {
    th.classList.toggle("sorted", th.dataset.col === playerSortCol);
  });

  const q = searchTerm.toLowerCase().trim();
  let rows = s.players.filter(p => {
    if (!q) return true;
    return (p.name || "").toLowerCase().includes(q) ||
           (p.team || "").toLowerCase().includes(q);
  });

  rows.sort((a, b) => {
    let av = a[playerSortCol], bv = b[playerSortCol];
    if (av == null) av = (typeof bv === "string") ? "" : -Infinity;
    if (bv == null) bv = (typeof av === "string") ? "" : -Infinity;
    if (typeof av === "string") {
      return playerSortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return playerSortDir === "asc" ? (av - bv) : (bv - av);
  });

  rows.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.name)}</td>
      <td><span class="pos-badge ${posClass(p.position)}">${escapeHtml(p.position || "")}</span></td>
      <td>${escapeHtml(p.team || "")}</td>
      <td class="num">${p.gp_rs || 0}</td>
      <td class="num">${(p.g60_rs || 0).toFixed(2)}</td>
      <td class="num">${p.gp_po || 0}</td>
      <td class="num">${(p.g60_po || 0).toFixed(2)}</td>
      <td class="num ${inflationClass(p.inflation)}">${(p.inflation || 0).toFixed(2)}×</td>
    `;
    tbody.appendChild(tr);
  });
}

// ── Team table ──
function renderTeams() {
  const s = SEASONS_DATA[currentSeason];
  if (!s) return;
  const tbody = document.querySelector("#team-table tbody");
  tbody.innerHTML = "";
  document.querySelectorAll("#team-table th").forEach(th => {
    th.classList.toggle("sorted", th.dataset.col === teamSortCol);
  });

  let rows = s.summary.team_rollup.slice();
  rows.sort((a, b) => {
    let av = a[teamSortCol], bv = b[teamSortCol];
    if (typeof av === "string") {
      return teamSortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return teamSortDir === "asc" ? (av - bv) : (bv - av);
  });

  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(r.team)}</td>
      <td class="num">${r.n_players}</td>
      <td class="num ${inflationClass(r.weighted_inflation)}">${r.weighted_inflation.toFixed(3)}×</td>
      <td class="num">${r.mean_inflation.toFixed(3)}×</td>
      <td class="num">${r.total_po_toi.toFixed(0)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAll() {
  renderMeta();
  renderHistogram();
  renderPlayers();
  renderTeams();
}

// ── Sort handlers ──
document.querySelectorAll("#players-table th").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.col;
    if (playerSortCol === col) {
      playerSortDir = playerSortDir === "desc" ? "asc" : "desc";
    } else {
      playerSortCol = col;
      playerSortDir = (col === "name" || col === "position" || col === "team") ? "asc" : "desc";
    }
    renderPlayers();
  });
});

document.querySelectorAll("#team-table th").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.col;
    if (teamSortCol === col) {
      teamSortDir = teamSortDir === "desc" ? "asc" : "desc";
    } else {
      teamSortCol = col;
      teamSortDir = (col === "team") ? "asc" : "desc";
    }
    renderTeams();
  });
});

// ── Search ──
document.getElementById("search").addEventListener("input", e => {
  searchTerm = e.target.value;
  renderPlayers();
});

// ── Resize ──
let _resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(renderHistogram, 120);
});

// ── Boot ──
buildSeasonPicker();
renderAll();
</script>
</body>
</html>
"""


def render_html(seasons_data: dict) -> str:
    html = HTML_TEMPLATE
    html = html.replace("__SEASONS_JSON__", json.dumps(seasons_data, separators=(",", ":"), ensure_ascii=False))
    html = html.replace("__MIN_GP__", str(MIN_PO_GP))
    html = html.replace("__VERSION__", GRIT_VERSION)
    return html


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help=f"Root data dir (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Where to write grit_playoff_delta.html (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--seasons", nargs="*", type=int, default=None,
                        help="Season tags to include (default: auto-discover from DEFAULT_SEASONS)")
    args = parser.parse_args()

    print(f"Data dir:   {args.data_dir}")
    print(f"Output dir: {args.output_dir}")
    print()

    if not args.data_dir.exists():
        print(f"ERROR: --data-dir does not exist: {args.data_dir}", file=sys.stderr)
        sys.exit(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidates = args.seasons if args.seasons else DEFAULT_SEASONS

    seasons_data = {}
    for s in candidates:
        rs_path = find_input_csv(args.data_dir, str(s))
        po_path = find_input_csv(args.data_dir, f"{s}_playoffs")
        if rs_path is None or po_path is None:
            print(f"  {s}: skipping (RS={'found' if rs_path else 'missing'}, "
                  f"PO={'found' if po_path else 'missing'})")
            continue

        try:
            pair = compute_season_pair(rs_path, po_path)
        except Exception as e:
            print(f"  {s}: ERROR computing pair: {e}", file=sys.stderr)
            continue

        if not pair["players"]:
            print(f"  {s}: no qualifying players (≥{MIN_PO_GP} PO GP)")
            continue

        summary = compute_summary(pair["players"])
        seasons_data[str(s)] = {"players": pair["players"], "summary": summary}
        print(f"  {s}: {summary['n']:3d} players  "
              f"mean={summary['mean_inflation']:.3f}×  "
              f"median={summary['median_inflation']:.3f}×  "
              f"top: {summary['top_inflator']['name']} ({summary['top_inflator']['inflation']:.2f}×)")

    if not seasons_data:
        print("ERROR: no valid season pairs found", file=sys.stderr)
        sys.exit(1)

    print(f"\nGenerated {len(seasons_data)} season(s) of data")
    html = render_html(seasons_data)

    out = args.output_dir / "grit_playoff_delta.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
