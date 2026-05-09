#!/usr/bin/env python3
"""
build_yoy_stability.py — generate grit_yoy_stability.html from all available
v3 per_60 CSVs.

Computes the year-over-year correlation of grit_z_blend between every valid
pair of regular seasons in --data-dir. A pair is "valid" if it does not bridge
the 2020-21 COVID-bubble season, which is intentionally excluded from the GRIT
project per the FAQ ("shortened format and abnormal competitive conditions").

Output structure:
    - Headline: 4 stat cards (n pairs, mean r overall, mean r at 1yr gap,
                              mean r at 2yr gap)
    - Pair matrix: upper-triangular grid, season x season, cells colored by r.
                   Hover any cell for the underlying n. Skipped/COVID cells
                   shown as gray with "—".
    - Decay panel: r vs gap-years scatter, one dot per pair, colored by gap
                   bucket. Trend visible at a glance.
    - Pair table: all valid pairs sorted by r descending. Low-n pairs (defined
                  as bottom 10% by shared-player count) flagged visually.

Reads:
    grit_per_60_v3_{season}.csv  for every season in DEFAULT_SEASONS or as
    discovered in --data-dir.

Writes:
    grit_yoy_stability.html  in --output-dir.

Usage:
    python build_yoy_stability.py \\
        --data-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3\\data" \\
        --output-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\GitHub\\grit-hockey"

    # To restrict the season set (e.g., exclude pre-2018 if methodology
    # changed):
    python build_yoy_stability.py \\
        --data-dir ... --output-dir ... \\
        --seasons 2018 2019 2020 2022 2023 2024 2025 2026
"""

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Path anchoring. Script assumed to live at:
#     C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\source\build_yoy_stability.py
# DEFAULT_DATA_DIR   = Version 3\data\
# DEFAULT_OUTPUT_DIR = grit-hockey repo root (for validation HTMLs)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
WORKING_DIR = SCRIPT_DIR.parent
GRIT_DIR = WORKING_DIR.parent
ONE_DRIVE_DOCS = GRIT_DIR.parent
DEFAULT_DATA_DIR = WORKING_DIR / "data"
DEFAULT_OUTPUT_DIR = ONE_DRIVE_DOCS / "GitHub" / "grit-hockey"


# Default season set — matches what build_v3.py has produced.
# 2021 (= 2020-21 COVID bubble) intentionally absent; 2020-21 was the
# shortened-format season excluded from the project.
DEFAULT_SEASONS = [2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025, 2026]

# Visible season label mapping. Convention: season tag = end-year of the season.
# 2026 = 2025-26.
def season_label(s: int) -> str:
    return f"{s-1}-{str(s)[-2:]}"


def bridges_covid(s1: int, s2: int) -> bool:
    """A pair bridges the COVID gap if it spans across the missing 2020-21 season.

    The 2020-21 season has tag 2021 (which is intentionally absent from our
    files). Any pair where one season is <= 2020 and the other is >= 2022
    therefore implicitly spans the missing year.
    """
    lo, hi = min(s1, s2), max(s1, s2)
    return lo <= 2020 and hi >= 2022


def find_input_csv(data_dir: Path, season: int) -> Path:
    fname = f"grit_per_60_v3_{season}.csv"
    candidates = [data_dir / str(season) / fname, data_dir / fname]
    for c in candidates:
        if c.exists():
            return c
    return None


def compute_pair_matrix(dfs: dict[int, pd.DataFrame]) -> dict:
    """Return { 'pairs': [...], 'seasons': [...], 'matrix': {(s1,s2): r}, ... }."""
    seasons = sorted(dfs.keys())
    pairs = []
    for s1, s2 in combinations(seasons, 2):
        if bridges_covid(s1, s2):
            pairs.append({
                "s1": s1, "s2": s2, "gap": s2 - s1,
                "r": None, "n": 0, "status": "covid_skip",
            })
            continue
        m = (
            dfs[s1][["player_id", "grit_z_blend"]]
            .rename(columns={"grit_z_blend": "z1"})
            .merge(
                dfs[s2][["player_id", "grit_z_blend"]]
                .rename(columns={"grit_z_blend": "z2"}),
                on="player_id",
            )
        )
        if len(m) < 2:
            pairs.append({
                "s1": s1, "s2": s2, "gap": s2 - s1,
                "r": None, "n": len(m), "status": "insufficient",
            })
            continue
        r = float(m["z1"].corr(m["z2"]))
        pairs.append({
            "s1": s1, "s2": s2, "gap": s2 - s1,
            "r": r, "n": int(len(m)), "status": "ok",
        })
    return {"seasons": seasons, "pairs": pairs}


def summary_stats(pairs: list[dict]) -> dict:
    valid = [p for p in pairs if p["status"] == "ok"]
    if not valid:
        return {"n_pairs": 0}

    rs = [p["r"] for p in valid]
    ns = [p["n"] for p in valid]

    # By-gap means
    by_gap = {}
    for p in valid:
        by_gap.setdefault(p["gap"], []).append(p["r"])
    by_gap_mean = {g: sum(v) / len(v) for g, v in by_gap.items()}
    by_gap_count = {g: len(v) for g, v in by_gap.items()}

    # N-weighted mean (more honest summary)
    n_weighted = sum(p["r"] * p["n"] for p in valid) / sum(ns)

    # Low-n threshold: 25th percentile of n
    sorted_n = sorted(ns)
    p25 = sorted_n[int(len(sorted_n) * 0.25)] if sorted_n else 0

    return {
        "n_pairs": len(valid),
        "mean_r": sum(rs) / len(rs),
        "n_weighted_mean_r": n_weighted,
        "min_r": min(rs),
        "max_r": max(rs),
        "by_gap_mean": by_gap_mean,
        "by_gap_count": by_gap_count,
        "low_n_threshold": p25,
    }


# ============================================================================
# HTML template
# ============================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>GRIT v3.1 · Year-Over-Year Stability</title>
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
  }
  h1 { font-size: 22px; font-weight: 600; letter-spacing: -0.3px;
       display:flex; align-items:center; gap:8px; }
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

  .grid-2 { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
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

  /* Pair matrix */
  table.matrix {
    border-collapse: separate; border-spacing: 2px;
    font-size: 12px; font-variant-numeric: tabular-nums;
  }
  table.matrix th {
    color: var(--text-dim); padding: 4px 6px;
    text-align: center; font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.4px; font-size: 10px;
  }
  table.matrix td.row-label {
    color: var(--text-dim); padding: 4px 8px 4px 0;
    text-align: right; font-size: 11px;
  }
  table.matrix td.cell {
    width: 56px; height: 30px; text-align: center;
    border-radius: 3px; cursor: default; font-weight: 500;
    color: var(--text); position: relative;
  }
  table.matrix td.cell.empty { background: transparent; }
  table.matrix td.cell.skip {
    background: rgba(139,148,158,0.12); color: var(--text-dim);
    font-style: italic;
  }
  table.matrix td.cell.lown {
    outline: 1px dashed var(--warn); outline-offset: -2px;
  }
  /* Color scale: r>=0.85 strong green, 0.80-0.85 muted, 0.75-0.80 amber, <0.75 red */
  td.cell.r-strong { background: rgba(63,185,80,0.55); }
  td.cell.r-good   { background: rgba(63,185,80,0.30); }
  td.cell.r-okay   { background: rgba(210,153,34,0.35); }
  td.cell.r-weak   { background: rgba(248,81,73,0.35); }

  /* Decay scatter */
  #decay-container { height: 380px; position: relative; }
  #decay-tooltip {
    position: absolute; display: none; pointer-events: none;
    background: #161b22; border: 1px solid #30363d;
    padding: 8px 10px; border-radius: 4px;
    font-size: 12px; color: #e6edf3; z-index: 10;
  }

  /* Pair table */
  table.pairs { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.pairs th {
    text-align: left; padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    color: var(--text-dim); font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.4px; font-size: 11px;
    cursor: pointer; user-select: none;
  }
  table.pairs th:hover { color: var(--text); }
  table.pairs th.sorted { color: var(--accent); }
  table.pairs td { padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
  table.pairs tr:hover td { background: rgba(255,255,255,0.02); }
  table.pairs td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .gap-pill {
    display: inline-block; padding: 1px 6px; border-radius: 3px;
    font-size: 10px; font-weight: 600;
  }
  .gap-1 { background: rgba(63,185,80,0.20); color: var(--good); }
  .gap-2 { background: rgba(88,166,255,0.20); color: var(--accent-2); }
  .gap-3 { background: rgba(210,153,34,0.20); color: var(--warn); }
  .gap-4 { background: rgba(248,81,73,0.20); color: var(--accent); }
  .lown-flag { color: var(--warn); font-size: 10px; margin-left: 4px; }

  .legend-row { display: flex; gap: 20px; margin-top: 12px; flex-wrap: wrap;
                font-size: 11px; color: var(--text-dim); }
  .legend-swatch {
    display: inline-block; width: 12px; height: 12px;
    border-radius: 2px; margin-right: 5px; vertical-align: middle;
  }
  .footnote {
    color: var(--text-dim); font-size: 11px; line-height: 1.6;
    margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border);
  }
</style>
</head>
<body>

<div class="header">
  <h1>GRIT <span class="v3badge">v3.1</span> <span class="sub">Year-Over-Year Stability</span></h1>
  <div class="lede">
    Correlation of player <code>grit_z_blend</code> across season pairs. Each
    valid pair takes the players who appeared in both seasons and computes the
    Pearson correlation of their GRIT-Z values. The 2020-21 season is excluded
    from the project, so any pair spanning that gap is omitted.
  </div>
</div>

<div id="meta" class="meta-row"></div>

<div class="grid-2">
  <div class="panel">
    <div class="panel-title">
      Pair Matrix
      <span class="hint">Hover a cell for shared-player count</span>
    </div>
    <div id="matrix-host" style="overflow-x:auto"></div>
    <div class="legend-row">
      <span><span class="legend-swatch" style="background:rgba(63,185,80,0.55)"></span>r ≥ 0.85</span>
      <span><span class="legend-swatch" style="background:rgba(63,185,80,0.30)"></span>0.80 – 0.85</span>
      <span><span class="legend-swatch" style="background:rgba(210,153,34,0.35)"></span>0.75 – 0.80</span>
      <span><span class="legend-swatch" style="background:rgba(248,81,73,0.35)"></span>&lt; 0.75</span>
      <span><span class="legend-swatch" style="background:rgba(139,148,158,0.12); border:1px solid var(--border)"></span>COVID gap (excluded)</span>
      <span><span class="legend-swatch" style="background:transparent; outline:1px dashed var(--warn)"></span>Low shared-n (bottom 25%)</span>
    </div>
  </div>

  <div class="panel">
    <div class="panel-title">
      Decay vs Season Gap
      <span class="hint">r drops as gap widens</span>
    </div>
    <div id="decay-container">
      <svg id="decay-svg" width="100%" height="100%"></svg>
      <div id="decay-tooltip"></div>
    </div>
    <div class="legend-row">
      <span><span class="legend-swatch" style="background:#3fb950"></span>1-year gap</span>
      <span><span class="legend-swatch" style="background:#58a6ff"></span>2-year gap</span>
      <span><span class="legend-swatch" style="background:#d29922"></span>3-year gap</span>
      <span><span class="legend-swatch" style="background:#f85149"></span>4-year gap</span>
    </div>
  </div>
</div>

<div class="panel">
  <div class="panel-title">
    All Valid Pairs
    <span class="hint">Click column to sort</span>
  </div>
  <div style="overflow-x:auto">
    <table class="pairs" id="pairs-table">
      <thead>
        <tr>
          <th data-col="s1">From</th>
          <th data-col="s2">To</th>
          <th data-col="gap" class="num">Gap</th>
          <th data-col="r" class="num sorted">r</th>
          <th data-col="n" class="num">Shared n</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
  <div class="footnote">
    <strong>Reading the numbers.</strong> The consecutive-pair (1-year-gap) mean is the comparable
    figure to public benchmarks: Corsi/Fenwick land around 0.6–0.7, points-per-60 around 0.5–0.6.
    GRIT's consecutive-year r being substantially higher reflects that contested-puck activity is
    more rooted in role and play-style than in scoring outcomes, which absorb shooting-percentage
    noise. Decay across multi-year gaps is a feature, not a flaw — the same player at age 24 and
    age 28 shouldn't necessarily play the same way, and the metric should reflect that.
  </div>
</div>

<script>
const PAIRS = __PAIRS_JSON__;
const SEASONS = __SEASONS_JSON__;
const SUMMARY = __SUMMARY_JSON__;

function seasonLabel(s) { return (s-1) + "-" + String(s).slice(-2); }
function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function colorClass(r) {
  if (r === null) return "skip";
  if (r >= 0.85) return "r-strong";
  if (r >= 0.80) return "r-good";
  if (r >= 0.75) return "r-okay";
  return "r-weak";
}

// ── Meta cards ──
function renderMeta() {
  const byGap = SUMMARY.by_gap_mean || {};
  const card = (lbl, val, sub) => `<div class="meta-card">
    <div class="meta-label">${lbl}</div>
    <div class="meta-value">${val}</div>
    <div class="meta-sub">${sub || ""}</div>
  </div>`;
  const valid = SUMMARY.n_pairs || 0;
  const meanR = (SUMMARY.mean_r != null) ? SUMMARY.mean_r.toFixed(3) : "—";
  const wMeanR = (SUMMARY.n_weighted_mean_r != null) ? SUMMARY.n_weighted_mean_r.toFixed(3) : "—";
  const g1 = byGap[1] != null ? byGap[1].toFixed(3) : "—";
  const g2 = byGap[2] != null ? byGap[2].toFixed(3) : "—";
  document.getElementById("meta").innerHTML =
    card("Valid Pairs", valid, "non-COVID-bridging") +
    card("Mean r (all pairs)", meanR, "unweighted") +
    card("Mean r (1-yr gap)", g1, `${SUMMARY.by_gap_count?.[1] || 0} pairs`) +
    card("Mean r (2-yr gap)", g2, `${SUMMARY.by_gap_count?.[2] || 0} pairs`);
}

// ── Pair matrix ──
function renderMatrix() {
  const host = document.getElementById("matrix-host");
  const lookup = {};
  PAIRS.forEach(p => { lookup[p.s1 + "x" + p.s2] = p; });

  let html = '<table class="matrix"><thead><tr><th></th>';
  for (let i = 1; i < SEASONS.length; i++) {
    html += `<th>${seasonLabel(SEASONS[i])}</th>`;
  }
  html += "</tr></thead><tbody>";

  for (let i = 0; i < SEASONS.length - 1; i++) {
    html += `<tr><td class="row-label">${seasonLabel(SEASONS[i])}</td>`;
    for (let j = 1; j < SEASONS.length; j++) {
      if (j <= i) {
        html += '<td class="cell empty"></td>';
        continue;
      }
      const p = lookup[SEASONS[i] + "x" + SEASONS[j]];
      if (!p || p.status === "covid_skip") {
        html += `<td class="cell skip" title="Spans 2020-21 (excluded)">—</td>`;
        continue;
      }
      if (p.status !== "ok" || p.r === null) {
        html += `<td class="cell skip" title="Insufficient overlap (n=${p.n})">·</td>`;
        continue;
      }
      const isLow = p.n <= SUMMARY.low_n_threshold;
      const cls = colorClass(p.r) + (isLow ? " lown" : "");
      const tip = `${seasonLabel(p.s1)} → ${seasonLabel(p.s2)} | r=${p.r.toFixed(3)} | n=${p.n}` +
                  (isLow ? " (low-n flag)" : "");
      html += `<td class="cell ${cls}" title="${tip}">${p.r.toFixed(2)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  host.innerHTML = html;
}

// ── Decay scatter ──
const GAP_COLOR = { 1: "#3fb950", 2: "#58a6ff", 3: "#d29922", 4: "#f85149", 5: "#f85149" };

function renderDecay() {
  const svg = document.getElementById("decay-svg");
  const container = document.getElementById("decay-container");
  const tooltip = document.getElementById("decay-tooltip");
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const W = container.clientWidth, H = container.clientHeight;
  const PAD = { t: 16, r: 16, b: 44, l: 50 };
  const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const data = PAIRS.filter(p => p.status === "ok" && p.r !== null);
  if (!data.length) return;

  const gaps = data.map(d => d.gap);
  const xMin = Math.min(...gaps) - 0.5;
  const xMax = Math.max(...gaps) + 0.5;
  const yMin = Math.min(0.7, Math.min(...data.map(d => d.r)) - 0.02);
  const yMax = Math.max(0.92, Math.max(...data.map(d => d.r)) + 0.02);

  const sx = v => PAD.l + ((v - xMin) / (xMax - xMin)) * plotW;
  const sy = v => PAD.t + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

  const ns = (tag, attrs) => {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  // Axes
  svg.appendChild(ns("line", {
    x1: PAD.l, y1: PAD.t + plotH, x2: PAD.l + plotW, y2: PAD.t + plotH,
    stroke: "#30363d"
  }));
  svg.appendChild(ns("line", {
    x1: PAD.l, y1: PAD.t, x2: PAD.l, y2: PAD.t + plotH,
    stroke: "#30363d"
  }));

  // X ticks (integer gap values)
  const gapSet = [...new Set(gaps)].sort((a,b)=>a-b);
  gapSet.forEach(g => {
    svg.appendChild(ns("line", {
      x1: sx(g), y1: PAD.t + plotH, x2: sx(g), y2: PAD.t + plotH + 4,
      stroke: "#30363d"
    }));
    const t = ns("text", {
      x: sx(g), y: PAD.t + plotH + 18, "text-anchor": "middle",
      fill: "#8b949e", "font-size": 11
    });
    t.textContent = g + "yr";
    svg.appendChild(t);
  });

  // Y ticks — fixed at 0.70, 0.75, 0.80, 0.85, 0.90 if in range
  [0.70, 0.75, 0.80, 0.85, 0.90].forEach(v => {
    if (v < yMin - 0.001 || v > yMax + 0.001) return;
    svg.appendChild(ns("line", {
      x1: PAD.l - 4, y1: sy(v), x2: PAD.l + plotW, y2: sy(v),
      stroke: "#30363d", "stroke-dasharray": v === 0.85 ? "" : "2,3",
      opacity: v === 0.85 ? 0.6 : 0.3
    }));
    const t = ns("text", {
      x: PAD.l - 8, y: sy(v) + 4, "text-anchor": "end",
      fill: "#8b949e", "font-size": 11
    });
    t.textContent = v.toFixed(2);
    svg.appendChild(t);
  });

  // Axis labels
  const xL = ns("text", {
    x: PAD.l + plotW / 2, y: H - 8, "text-anchor": "middle",
    fill: "#8b949e", "font-size": 12
  });
  xL.textContent = "Season gap";
  svg.appendChild(xL);

  const yL = ns("text", {
    x: 14, y: PAD.t + plotH / 2,
    "text-anchor": "middle", fill: "#8b949e", "font-size": 12,
    transform: `rotate(-90 14 ${PAD.t + plotH / 2})`
  });
  yL.textContent = "Pearson r";
  svg.appendChild(yL);

  // Mean-by-gap line (connect the means)
  const byGap = SUMMARY.by_gap_mean || {};
  const meanPoints = Object.keys(byGap).map(g => ({
    x: parseInt(g, 10), y: byGap[g]
  })).sort((a, b) => a.x - b.x);
  if (meanPoints.length > 1) {
    let path = "";
    meanPoints.forEach((p, i) => {
      path += (i === 0 ? "M" : "L") + sx(p.x) + "," + sy(p.y) + " ";
    });
    svg.appendChild(ns("path", {
      d: path, stroke: "#f9a03f", "stroke-width": 2,
      fill: "none", opacity: 0.6
    }));
    meanPoints.forEach(p => {
      svg.appendChild(ns("circle", {
        cx: sx(p.x), cy: sy(p.y), r: 4,
        fill: "#f9a03f", stroke: "#0d1117", "stroke-width": 1.5
      }));
    });
  }

  // Individual pair points (jittered horizontally so they don't overlap)
  data.forEach((d, i) => {
    const sameGap = data.filter(x => x.gap === d.gap);
    const idx = sameGap.indexOf(d);
    const jitter = (idx - (sameGap.length - 1) / 2) * 0.08;
    const cx = sx(d.gap + jitter);
    const cy = sy(d.r);
    const color = GAP_COLOR[d.gap] || "#8b949e";
    const c = ns("circle", {
      cx, cy, r: 5,
      fill: color, "fill-opacity": 0.55,
      stroke: color, "stroke-width": 1.5,
      style: "cursor:pointer"
    });
    c.addEventListener("mouseenter", () => {
      c.setAttribute("r", 7);
      tooltip.style.display = "block";
      tooltip.innerHTML =
        `<strong>${seasonLabel(d.s1)} → ${seasonLabel(d.s2)}</strong><br>` +
        `r = ${d.r.toFixed(3)} · n = ${d.n}<br>` +
        `Gap: ${d.gap} year${d.gap > 1 ? "s" : ""}`;
    });
    c.addEventListener("mousemove", evt => {
      const rect = container.getBoundingClientRect();
      tooltip.style.left = (evt.clientX - rect.left + 12) + "px";
      tooltip.style.top  = (evt.clientY - rect.top  + 12) + "px";
    });
    c.addEventListener("mouseleave", () => {
      c.setAttribute("r", 5);
      tooltip.style.display = "none";
    });
    svg.appendChild(c);
  });
}

// ── Pair table ──
let sortCol = "r", sortDir = "desc";

function renderPairsTable() {
  const tbody = document.querySelector("#pairs-table tbody");
  tbody.innerHTML = "";
  document.querySelectorAll("#pairs-table th").forEach(th => {
    th.classList.toggle("sorted", th.dataset.col === sortCol);
  });
  const valid = PAIRS.filter(p => p.status === "ok" && p.r !== null);
  valid.sort((a, b) => {
    const av = a[sortCol], bv = b[sortCol];
    return sortDir === "asc" ? (av - bv) : (bv - av);
  });
  valid.forEach(p => {
    const isLow = p.n <= SUMMARY.low_n_threshold;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${seasonLabel(p.s1)}</td>
      <td>${seasonLabel(p.s2)}</td>
      <td class="num"><span class="gap-pill gap-${Math.min(p.gap, 4)}">${p.gap}yr</span></td>
      <td class="num">${p.r.toFixed(3)}</td>
      <td class="num">${p.n}${isLow ? '<span class="lown-flag">low-n</span>' : ''}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.querySelectorAll("#pairs-table th").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.col;
    if (sortCol === col) sortDir = (sortDir === "desc" ? "asc" : "desc");
    else { sortCol = col; sortDir = (col === "s1" || col === "s2") ? "asc" : "desc"; }
    renderPairsTable();
  });
});

// ── Boot ──
renderMeta();
renderMatrix();
renderDecay();
renderPairsTable();

let _resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(renderDecay, 120);
});
</script>
</body>
</html>
"""


def render_html(seasons: list[int], pairs: list[dict], summary: dict) -> str:
    html = HTML_TEMPLATE
    html = html.replace("__PAIRS_JSON__", json.dumps(pairs, separators=(",", ":")))
    html = html.replace("__SEASONS_JSON__", json.dumps(seasons, separators=(",", ":")))
    html = html.replace("__SUMMARY_JSON__", json.dumps(summary, separators=(",", ":")))
    return html


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help=f"Root data dir (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Where to write grit_yoy_stability.html (default: {DEFAULT_OUTPUT_DIR})")
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

    season_candidates = args.seasons if args.seasons else DEFAULT_SEASONS

    dfs = {}
    for s in season_candidates:
        path = find_input_csv(args.data_dir, s)
        if path is None:
            print(f"  {s}: no per_60 CSV found, skipping")
            continue
        df = pd.read_csv(path)
        if "player_id" not in df.columns or "grit_z_blend" not in df.columns:
            print(f"  {s}: missing required columns, skipping ({path})")
            continue
        dfs[s] = df
        print(f"  {s}: {len(df):4d} players  ({path.name})")

    if len(dfs) < 2:
        print("ERROR: need at least 2 seasons to compute YoY pairs", file=sys.stderr)
        sys.exit(1)

    seasons = sorted(dfs.keys())
    print(f"\nLoaded {len(seasons)} seasons: {seasons}\n")

    matrix = compute_pair_matrix(dfs)
    pairs = matrix["pairs"]
    summary = summary_stats(pairs)

    # Console summary
    valid = [p for p in pairs if p["status"] == "ok"]
    skipped = [p for p in pairs if p["status"] != "ok"]
    print(f"Computed {len(pairs)} pairs total: {len(valid)} valid, {len(skipped)} skipped")

    if summary.get("n_pairs"):
        print(f"  Mean r:            {summary['mean_r']:.4f}")
        print(f"  N-weighted mean r: {summary['n_weighted_mean_r']:.4f}")
        print(f"  Range:             [{summary['min_r']:.4f}, {summary['max_r']:.4f}]")
        print(f"  Low-n threshold:   {summary['low_n_threshold']} (bottom 25%)")
        print(f"  By gap:")
        for g in sorted(summary["by_gap_mean"].keys()):
            print(f"    {g}yr: mean={summary['by_gap_mean'][g]:.4f}  "
                  f"(n_pairs={summary['by_gap_count'][g]})")

    html = render_html(seasons, pairs, summary)
    out = args.output_dir / "grit_yoy_stability.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nWrote {out}  ({out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
