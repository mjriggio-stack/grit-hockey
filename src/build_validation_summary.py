#!/usr/bin/env python3
"""
build_validation_summary.py — regenerate v3_validation_summary.txt from the
current per_60 CSVs.

This script computes the four validation tables that v3_validation_summary.txt
contains, sourced from `grit_per_60_v3_{season}.csv` (RS) and
`grit_per_60_v3_{season}_playoffs.csv` (PO) files. It is the canonical source
of truth for all numbers cited in README.md and v3_methodology.md — those
documents should pull their figures directly from this output.

Sections produced:
    1. Year-over-year repeatability (consecutive-pair r on grit_z_blend)
    2. Per-pool YoY breakdown (C/L/R/D) for each pair
    3. CWD pool sizes per season
    4. Playoff vs RS rate inflation — composite + per-event
    5. Multi-gap YoY decay (1yr, 2yr, 3yr, 4yr means)

The 2020-21 (tag 2021) season is excluded from YoY computations because it
was the COVID bubble; pairs that would bridge that gap are skipped.

Reads:
    grit_per_60_v3_{season}.csv             for every season in --seasons
    grit_per_60_v3_{season}_playoffs.csv    same

Writes:
    v3_validation_summary.txt  in --output-dir.

Usage:
    python build_validation_summary.py \\
        --data-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\Grit\\Version 3\\data" \\
        --output-dir "C:\\Users\\mjrig\\OneDrive\\Documents\\GitHub\\grit-hockey"
"""

import argparse
import datetime as dt
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd


DEFAULT_SEASONS = [2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025, 2026]
COVID_GAP_YEAR = 2021  # missing season tag — bridges with both s<=2020 and s>=2022


def season_label(s: int) -> str:
    return f"{s-1}-{str(s)[-2:]}"


def find_input_csv(data_dir: Path, season_tag: str) -> Path | None:
    fname = f"grit_per_60_v3_{season_tag}.csv"
    for p in [data_dir / season_tag / fname, data_dir / fname]:
        if p.exists():
            return p
    return None


def derive_pool_cwd(p: str) -> str:
    p = str(p).upper().strip()
    if p == "C": return "C"
    if p in ("L", "R", "LW", "RW", "W"): return "W"
    if p == "D": return "D"
    return "?"


def derive_pool_lr(p: str) -> str:
    """For per-pool diagnostics, keep L and R separate so we can see if one
    wing is more stable than the other."""
    p = str(p).upper().strip()
    if p in ("C", "L", "R", "D"): return p
    if p == "LW": return "L"
    if p == "RW": return "R"
    return "?"


def bridges_covid(s1: int, s2: int) -> bool:
    lo, hi = min(s1, s2), max(s1, s2)
    return lo <= 2020 and hi >= 2022


# ============================================================================
# Section computers
# ============================================================================

def section_yoy(dfs: dict[int, pd.DataFrame]) -> str:
    """Section 1: consecutive-pair YoY on grit_z_blend (1-year gap pairs only)."""
    out = []
    out.append("=" * 80)
    out.append("1. YEAR-OVER-YEAR REPEATABILITY (regular season, grit_z_blend)")
    out.append("=" * 80)
    out.append("")
    out.append(f'{"Pair":<20}{"n":>8}{"v3 r":>10}')
    out.append("-" * 40)

    seasons = sorted(dfs.keys())
    rs = []
    for i in range(len(seasons) - 1):
        s1, s2 = seasons[i], seasons[i + 1]
        if bridges_covid(s1, s2):
            label = f"{season_label(s1)} <-> {season_label(s2)}"
            out.append(f'{label:<20}{"--":>8}{"COVID gap":>10}')
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
        r = m["z1"].corr(m["z2"])
        rs.append(r)
        label = f"{season_label(s1)} <-> {season_label(s2)}"
        out.append(f'{label:<20}{len(m):>8}{r:>+10.4f}')

    if rs:
        out.append("-" * 40)
        out.append(f'{"Mean":<20}{"":>8}{sum(rs)/len(rs):>+10.4f}')
        out.append(f'{"Min":<20}{"":>8}{min(rs):>+10.4f}')
        out.append(f'{"Max":<20}{"":>8}{max(rs):>+10.4f}')
    out.append("")
    out.append("Public benchmarks for context:")
    out.append("  Corsi/Fenwick repeatability ~ r = 0.6 - 0.7")
    out.append("  Points-per-60 repeatability ~ r = 0.5 - 0.6")
    out.append("")
    return "\n".join(out)


def section_yoy_by_pool(dfs: dict[int, pd.DataFrame]) -> str:
    """Section 2: per-pool YoY (C, L, R, D separately) for each consecutive pair."""
    out = []
    out.append("=" * 80)
    out.append("2. YOY BY POSITION POOL (consecutive pairs)")
    out.append("=" * 80)
    out.append("")

    seasons = sorted(dfs.keys())
    for i in range(len(seasons) - 1):
        s1, s2 = seasons[i], seasons[i + 1]
        if bridges_covid(s1, s2):
            continue

        a = dfs[s1][["player_id", "position", "grit_z_blend"]].rename(
            columns={"position": "pos1", "grit_z_blend": "z1"}
        )
        b = dfs[s2][["player_id", "position", "grit_z_blend"]].rename(
            columns={"position": "pos2", "grit_z_blend": "z2"}
        )
        m = a.merge(b, on="player_id")
        m["pool"] = m["pos2"].apply(derive_pool_lr)

        overall_r = m["z1"].corr(m["z2"])
        out.append(f"{season_label(s1)} -> {season_label(s2)}:")
        out.append(f'  Overall:  n={len(m):>4}  r={overall_r:+.4f}')
        for pool in ["C", "L", "R", "D"]:
            sub = m[m["pool"] == pool]
            if len(sub) < 2:
                continue
            r = sub["z1"].corr(sub["z2"])
            out.append(f'    {pool}:  n={len(sub):>4}  r={r:+.4f}')
        out.append("")
    return "\n".join(out)


def section_pool_sizes(dfs: dict[int, pd.DataFrame]) -> str:
    """Section 3: CWD pool sizes per season."""
    out = []
    out.append("=" * 80)
    out.append("3. POOL SIZES UNDER CWD POOLING")
    out.append("=" * 80)
    out.append("")
    out.append(f'{"Season":<12}{"C":>6}{"W":>6}{"D":>6}{"Total":>8}')
    out.append("-" * 38)
    for s in sorted(dfs.keys()):
        df = dfs[s].copy()
        df["pool"] = df["position"].apply(derive_pool_cwd)
        counts = df["pool"].value_counts().to_dict()
        out.append(
            f'{season_label(s):<12}'
            f'{counts.get("C", 0):>6}'
            f'{counts.get("W", 0):>6}'
            f'{counts.get("D", 0):>6}'
            f'{len(df):>8}'
        )
    out.append("")
    return "\n".join(out)


def section_playoff_inflation(rs_dfs: dict[int, pd.DataFrame],
                               po_dfs: dict[int, pd.DataFrame]) -> str:
    """Section 4: playoff vs RS rate inflation (composite + per-event)."""
    out = []
    out.append("=" * 80)
    out.append("4. PLAYOFF vs REGULAR SEASON RATE INFLATION")
    out.append("=" * 80)
    out.append("")

    pairs = sorted(set(rs_dfs.keys()) & set(po_dfs.keys()))
    if not pairs:
        out.append("No paired RS/PO seasons available.")
        out.append("")
        return "\n".join(out)

    out.append("Composite weighted rate per60 (raw_grit_per_60):")
    out.append(f'{"Season":<12}{"RS rate":>10}{"PO rate":>10}{"Ratio":>8}')
    out.append("-" * 40)
    composite_ratios = []
    for s in pairs:
        rs = rs_dfs[s]
        po = po_dfs[s]
        rs_rate = rs["weighted_total"].sum() / rs["toi_min"].sum() * 60
        po_rate = po["weighted_total"].sum() / po["toi_min"].sum() * 60
        ratio = po_rate / rs_rate
        composite_ratios.append(ratio)
        out.append(f'{season_label(s):<12}{rs_rate:>10.2f}{po_rate:>10.2f}{ratio:>7.2f}x')
    out.append("-" * 40)
    out.append(
        f'{"Mean":<12}{"":>10}{"":>10}'
        f'{sum(composite_ratios)/len(composite_ratios):>7.2f}x'
    )
    out.append(f'{"Range":<12}{"":>10}{"":>10}'
               f'{min(composite_ratios):>5.2f}x - {max(composite_ratios):.2f}x')
    out.append("")

    # Per-event inflation
    events = [
        "raw_hits_thrown", "raw_hits_taken",
        "raw_blocked_shots", "raw_blocked_shots_hd",
        "raw_takeaways_high_danger", "raw_takeaways_other",
        "raw_dz_faceoff_wins",
        "raw_crease_goals", "raw_penalties_drawn",
        "raw_physical_minors_taken", "raw_fighting_majors",
        "raw_giveaways_dz", "raw_giveaways_nz", "raw_giveaways_oz",
    ]

    out.append("Per-event rate ratio (PO / RS) by season:")
    header = f'{"Event":<32}'
    for s in pairs:
        header += f'{season_label(s):>9}'
    header += f'{"Mean":>9}'
    out.append(header)
    out.append("-" * len(header))

    for e in events:
        row = f'{e:<32}'
        ratios_for_event = []
        for s in pairs:
            rs = rs_dfs[s]
            po = po_dfs[s]
            if e not in rs.columns or e not in po.columns:
                row += f'{"--":>9}'
                continue
            rs_rate = rs[e].sum() / rs["toi_min"].sum() * 60
            po_rate = po[e].sum() / po["toi_min"].sum() * 60
            if rs_rate <= 0:
                row += f'{"--":>9}'
                continue
            r = po_rate / rs_rate
            ratios_for_event.append(r)
            row += f'{r:>7.2f}x '[-9:]
        if ratios_for_event:
            mean_r = sum(ratios_for_event) / len(ratios_for_event)
            row += f'{mean_r:>7.2f}x '[-9:]
        out.append(row)
    out.append("")
    return "\n".join(out)


def section_multi_gap(dfs: dict[int, pd.DataFrame]) -> str:
    """Section 5: multi-gap YoY decay (1yr, 2yr, 3yr, 4yr means)."""
    out = []
    out.append("=" * 80)
    out.append("5. MULTI-GAP YOY DECAY (grit_z_blend)")
    out.append("=" * 80)
    out.append("")

    seasons = sorted(dfs.keys())
    by_gap = {}  # gap_years -> list of r values
    by_gap_n = {}  # gap_years -> list of n values

    for s1, s2 in combinations(seasons, 2):
        if bridges_covid(s1, s2):
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
            continue
        r = m["z1"].corr(m["z2"])
        gap = s2 - s1
        by_gap.setdefault(gap, []).append(r)
        by_gap_n.setdefault(gap, []).append(len(m))

    out.append(f'{"Gap":<10}{"# pairs":>10}{"Mean r":>12}{"Min":>10}{"Max":>10}')
    out.append("-" * 52)
    for gap in sorted(by_gap.keys()):
        rs = by_gap[gap]
        out.append(
            f'{gap}-year{"":<4}'
            f'{len(rs):>10}'
            f'{sum(rs)/len(rs):>+12.4f}'
            f'{min(rs):>+10.4f}'
            f'{max(rs):>+10.4f}'
        )
    out.append("")
    out.append("Interpretation: r decays as the gap widens but appears to plateau")
    out.append("after gap=2-3 years, suggesting GRIT identifies a stable player")
    out.append("archetype rather than year-specific role context.")
    out.append("")
    return "\n".join(out)


def build_summary(rs_dfs: dict[int, pd.DataFrame],
                  po_dfs: dict[int, pd.DataFrame]) -> str:
    today = dt.date.today().isoformat()
    seasons_str = ", ".join(season_label(s) for s in sorted(rs_dfs.keys()))

    sections = []
    sections.append("=" * 80)
    sections.append("V3 VALIDATION SUMMARY")
    sections.append("=" * 80)
    sections.append("")
    sections.append(f"Generated:        {today}")
    sections.append(f"RS seasons:       {seasons_str}")
    sections.append(f"PO seasons:       {len(po_dfs)} ({', '.join(season_label(s) for s in sorted(po_dfs.keys()))})")
    sections.append(f"COVID exclusion:  2020-21 (tag 2021) intentionally absent")
    sections.append("")
    sections.append("Source: grit_per_60_v3_*.csv files in --data-dir.")
    sections.append("Regenerate with: python build_validation_summary.py --data-dir ... --output-dir ...")
    sections.append("")
    sections.append("")

    sections.append(section_yoy(rs_dfs))
    sections.append(section_yoy_by_pool(rs_dfs))
    sections.append(section_pool_sizes(rs_dfs))
    sections.append(section_playoff_inflation(rs_dfs, po_dfs))
    sections.append(section_multi_gap(rs_dfs))

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seasons", nargs="*", type=int, default=None)
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"ERROR: --data-dir does not exist: {args.data_dir}", file=sys.stderr)
        sys.exit(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidates = args.seasons if args.seasons else DEFAULT_SEASONS

    rs_dfs, po_dfs = {}, {}
    for s in candidates:
        rs_path = find_input_csv(args.data_dir, str(s))
        po_path = find_input_csv(args.data_dir, f"{s}_playoffs")
        if rs_path is not None:
            rs_dfs[s] = pd.read_csv(rs_path)
        if po_path is not None:
            po_dfs[s] = pd.read_csv(po_path)
        rs_status = "found" if s in rs_dfs else "missing"
        po_status = "found" if s in po_dfs else "missing"
        print(f"  {s}: RS={rs_status}  PO={po_status}")

    if len(rs_dfs) < 2:
        print("ERROR: need at least 2 RS seasons to compute validation", file=sys.stderr)
        sys.exit(1)

    print()
    print(f"Loaded {len(rs_dfs)} RS seasons + {len(po_dfs)} PO seasons")

    summary = build_summary(rs_dfs, po_dfs)

    out_path = args.output_dir / "v3_validation_summary.txt"
    out_path.write_text(summary, encoding="utf-8")
    print(f"Wrote {out_path}  ({out_path.stat().st_size / 1024:.1f} KB)")
    print()
    print("First 60 lines of output:")
    print("-" * 80)
    for line in summary.split("\n")[:60]:
        print(line)


if __name__ == "__main__":
    main()
