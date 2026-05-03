# GRIT v3

**GRIT (Gritty Role Impact Total)** is a position-adjusted, weighted composite metric measuring physical and contested-puck contribution for NHL skaters. Built and maintained by Matthew Riggio of the [Echoes from the Arena](https://www.youtube.com/@EchoesfromtheArena) podcast.

---

## What GRIT measures

GRIT counts what happens when players battle for pucks. Hits thrown and taken, blocked shots, takeaways, crease goals, defensive-zone faceoff wins, penalties drawn, physical minors, fights, and giveaways, each weighted by its estimated value. Each event is weighted by its estimated contribution, rates are normalized per 60 minutes of ice time, and z-scores are computed within position pools so centers are compared against centers, wings against wings, and defensemen against defensemen.

One thing worth saying up front: **GRIT is not a grinder metric.** The name implies it, but the math doesn't back it up. A 5'10" winger who draws 25 penalties and scores 12 crease goals scores well on GRIT. So does a top-six center who throws 200 hits while putting up 60 points. The metric doesn't care about role or archetype. It counts contested-puck contribution honestly, which means the leaderboard looks different from what you'd expect if you filtered purely by reputation.

Vincent Trocheck (NYR) is a consistent top-15 center on this metric. Ryan Hartman (MIN) ranks in the top 25 among wings despite throwing fewer hits than almost everyone else on that list. Peyton Krebs (BUF), listed at 184 lbs and playing top-line minutes, ranks inside the top 25 among NHL centers. None of them fit the traditional "grit guy" archetype. All of them show up because they compete in contested areas at an elite rate.

---

## Season coverage

**Regular seasons:** 2015-16 through 2025-26, skipping 2020-21.

**Playoffs:** 2015-16 through 2025-26, skipping 2020-21.

The 2019-20 season is included with a caution note. The COVID bubble produced a non-standard schedule with no home/away context and compressed games, which affects some event rates. Year-over-year comparisons involving 2020 should be interpreted carefully.

The 2020-21 season is excluded entirely. The 56-game format and unusual schedule make it an outlier that would distort multi-season analysis.

---

## Why it holds up

GRIT z-scores are more stable year-over-year than forward points across every season pair in this dataset. The average Pearson r between consecutive seasons is 0.877 for GRIT z versus 0.809 for forward points. That gap holds in every single season pair going back to 2015-16.

This matters because stability is one of the best tests of whether a metric is measuring something real about a player versus capturing noise. GRIT passes that test more consistently than scoring does.

---

## Files

### Per-player data

| File | Description |
|------|-------------|
| `grit_per_60_v3_{year}.csv` | All-strengths per-60, z-scores by position pool |
| `grit_5v5_v3_{year}.csv` | 5v5 only (situationCode 1551) |
| `grit_pk_v3_{year}.csv` | Penalty kill only |
| `grit_monthly_v3_{year}.csv` | Monthly GRIT rate breakdown |
| `grit_per_60_v3_{year}_playoffs.csv` | Playoff all-strengths per-60 |
| `grit_5v5_v3_{year}_playoffs.csv` | Playoff 5v5 |
| `grit_pk_v3_{year}_playoffs.csv` | Playoff PK |
| `grit_monthly_v3_{year}_playoffs.csv` | Playoff monthly breakdown |

Year tags follow NHL convention: `2026` = 2025-26 season.

Note: the 2020 and 2022 season folders do not include monthly files. Monthly breakdowns were not collected for those seasons and cannot be reconstructed from the available data.

### Career and team data

| File | Description |
|------|-------------|
| `grit_career_v3.csv` | Career totals and z-scores, all skaters with 3+ seasons |
| `grit_team_rollup_v3_allseasons.csv` | Team-level GRIT aggregates, all seasons |

### Key columns

| Column | Description |
|--------|-------------|
| `grit_z_blend` | Primary z-score: 70% positional rate z, 30% volumetric z |
| `grit_z_pos` | Positional rate z-score (within C, W, or D pool) |
| `grit_z_vol` | Volumetric z-score (total weighted events) |
| `raw_grit_per_60` | Weighted event total per 60 minutes, before z-scoring |
| `grit_per_game` | Weighted event total per game |
| `raw_blocked_shots_hd` | Blocked shots from the slot rectangle |
| `raw_blocked_shots_non_hd` | Blocked shots outside the slot |
| `raw_crease_goals` | Goals scored within 12 feet of the net |
| `raw_takeaways_high_danger` | Takeaways from the slot rectangle |

Full column documentation is in `GRIT_v3_Methodology.pdf`.

---

## Dashboards

Open any of the HTML files in a browser. No installation required.

| File | Description |
|------|-------------|
| `grit_dashboard_v3_2026.html` | 2025-26 regular season leaderboard |
| `grit_dashboard_v3_2026_playoffs.html` | 2025-26 playoffs leaderboard |
| `grit_playoff_delta_2526.html` | Playoff GRIT elevation, 2025-26 |
| `grit_playoff_delta_2425.html` | Playoff GRIT elevation, 2024-25 |
| `grit_playoff_delta_2324.html` | Playoff GRIT elevation, 2023-24 |
| `grit_yoy_stability.html` | Year-over-year stability, GRIT z vs points |

The regular season and playoff dashboards have a CSV upload button. When new data is available, drop in the corresponding `grit_per_60_v3_{year}.csv` file to refresh without rebuilding the page.

The playoff delta dashboards show raw GRIT/60 change between a player's regular season and playoff performance, normalized so the baseline playoff intensity increase washes out. What remains is who actually elevated relative to their peers.

---

## Methodology

Full methodology is in `GRIT_v3_Methodology.pdf`. The short version:

- 14 weighted event types, each assigned a weight reflecting its estimated contested-puck value
- Rates normalized per 60 minutes of ice time
- Z-scores computed within position pools: C vs C, W vs W, D vs D
- Blended z-score: 70% rate-based, 30% volume-based
- TOI floors applied to exclude small-sample outliers

Changes from v2 and v2.1, including three confirmed bug fixes in the penalty kill file, are documented in `CHANGELOG.md`.

---

## What is coming in v3.1

Targeting release before the end of May 2026.

- Earning Your Points forward visualization: a career and single-season quadrant view showing which forwards are producing points relative to their physical contribution
- Earning Your Points career scatter: all eligible forwards plotted by career average GRIT z and career average points
- Team GRIT identity over time
- Playoff success analysis

---

## Credit and use

Built by Matthew Riggio. If you use GRIT data or methodology in your work, please credit GRIT v3 by Matthew Riggio and link back to this repository.

Questions, feedback, and corrections are welcome. Email is mjriggio@gmail.com  Find the podcast at [Echoes from the Arena](https://www.youtube.com/@EchoesfromtheArena).

