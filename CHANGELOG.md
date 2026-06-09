# Changelog

All notable changes to GRIT (Gritty Role Impact Total).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions before v3.1 are documented retroactively; only v3.1 and forward have authoritative release dates.

---

## [v3.2] — in progress

### Changed

- **EYP points axis: per-season median → absolute 41-point bar.** The original quadrant split put the points axis at each season's median, which mechanically forces a ~50/50 split above and below and makes any "players cross the line" finding partly an artifact of the split itself. v3.2 replaces it with a fixed bar of 41 points (0.5 pts/game over 82) for full seasons, pro-rated for shortened seasons (the 71-game 2019-20 uses 35.5). "High scoring" is now a real, stable population (~40% of qualifying forwards) instead of half the field by construction. All EYP outputs regenerated on the bar.

- **Single classifier (`eyp_common.py`).** The quadrant logic (the bar, the pro-ration, `assign_quadrant`) was duplicated across `build_eyp.py`, `build_eyp_career.py`, and `build_eyp_career_html.py` — three copies that had already drifted (the 41-bar decision lived in docs but not code). Extracted to `eyp_common.py` as the single source of truth, imported by all three. A change to the bar is now one edit. (A cleaner refactor — making `build_eyp.py` the only thing that classifies and having the career builder read its CSVs — is tabled for v3.3.)

- **Watchlist age gate: 25 → 27.** Set by btog sustain analysis on the bar: transitions made at age ≤ 27 hold ~78% of the time, dropping to ~54% at 28-30 and ~50% at 31-33.

### Added

- **EYP (Earning Your Points) framework** — quadrant analysis layered on top of v3.1 GRIT scores. Classifies qualifying forwards (GP ≥ 40, C/W) into four quadrants by GRIT-Z (split at 0) vs the absolute points bar:
  - GREEN (hi grit, at/above bar), RED (lo grit, at/above bar), BLUE (hi grit, below bar), GRAY (lo grit, below bar)
  - Watchlist: the BLUE quadrant
  - Headline filter: BLUE + age ≤ 27 + within 5 points of the bar

- **`scrape_players.py`** — new script; scrapes NHL player bio data (birth year) into `players` SQL table (2,103 rows, 4 NULL orphans).

- **`build_eyp.py`** — `--headline-filter` mode, age column, configurable age/gap cutoffs; classification imported from `eyp_common`.

- **`build_eyp_career.py`** — new; multi-season pivot across 800 forwards × 25 columns, Blue→Green transition tracking; classification imported from `eyp_common`.

- **`build_eyp_career_html.py`** — new; sortable career table + interactive scatter with single-player trajectory mode, position/team filters, compare-with arrows, age ≤ 27 ring, PNG export; classification imported from `eyp_common`.

- **`v3_methodology.md` §14** — full EYP writeup on the absolute bar, including the Blue-to-Green analysis and the corrected framing below.

### Findings (Blue-to-Green analysis, on the absolute bar)

- **GRIT does not predict the breakout, and EYP is a population screen, not a forecast.** Blue-season GRIT-Z is *lower* for forwards who cross to GREEN than for those who stay (0.67 vs 0.99, p = 0.0012; OR ~0.66/SD). Proximity to the bar and age are the actual predictors. The negative control settles it: low-grit GRAY forwards reach the bar at ~28% vs ~13% for high-grit BLUE forwards, so a below-bar forward is roughly twice as likely to start scoring if their grit is *low*. This is consistent with GRIT's design orthogonality to scoring; it screens the contested-puck population rather than forecasting production.

- **Transition counts and magnitude.** 70 transitions / 63 players (exclusive, literal consecutive years) or 79 / 69 (inclusive, accepting the 2020→2022 COVID-gap pair). Raw points jump averages ~+17 and is 100% positive, but that is forced by the definition (crossing the bar from below); pace-adjusted, the honest magnitude is ~+13 per-82 (exclusive) to ~+14.5 (inclusive). Sustain rate ~68% overall, ~78% at age ≤ 27.

### Fixed

- **`scrape_scoring.py` duplicate-row bug** — NHL `/skater/summary` and `/skater/faceoffwins` endpoints return identical duplicate `(playerId, teamAbbrevs)` rows for many players. The non-deduplicated left merge fanned out summary rows; the downstream `groupby` sum then inflated every counting stat by 2× or 3×. Example: Hamilton 22-23 showed GP=246, points=222 instead of GP=82, points=74.

  Fix: both endpoints are now deduplicated on `(playerId, teamAbbrevs)` + counting stats before the merge. Identical-row dupes collapse to 1 row; genuine traded-player splits (different `teamAbbrevs`) are preserved.

  All 10 RS seasons re-scraped clean. Four players with GP > 82 (Barrie 85, Hathaway 84, Eller 84, Johnson 83) are confirmed legitimate trade-deadline overages, not artifacts. 800 qualifying forwards after the fix (was 797). `ever_btog` is 63 players on the absolute bar (exclusive definition).

### 2025-26 headline watchlist

Cuylle (NYR, age 24, gap=3) · Podkolzin (EDM, age 25, gap=4) · Krebs (BUF, age 25, gap=2) · Neighbours (STL, age 24, gap=5) · Poehling (ANA, age 27, gap=5) · Tolvanen (SEA, age 27, gap=5)

Gap is points below the 41-point bar. List is best read by gap/age, not GRIT-Z, given GRIT does not predict crossing.

---

## [v3.1] — 2026-05-09

The v3.1 release adds one weighted component to v3 and is otherwise identical. v3.1 ↔ v3 correlation is ~0.997 across all validation seasons; the rank order is essentially preserved.

### Added

- **`raw_close_shots`** — new event type: any shot attempt (shot-on-goal, missed-shot, or goal) within 12 feet of the net, weighted at +1.5. Spatial test is `(89 − |x|)² + y² ≤ 144` (identical to crease goals). Goals stack: a crease goal earns both the +10.0 finishing credit and the +1.5 attempt credit, for a combined +11.5.
- **`v3_methodology.md` §13** — new "Changes from v3" section parallel to the existing v3 history narrative.
- **CHANGELOG.md** — this file.

### Changed

- **Component count: 14 → 15.**
- **YoY mean r: 0.876 → 0.873** across 8 consecutive-year pairs (within consecutive-pair noise, range 0.858–0.885).
- **Playoff inflation mean: 1.34× → 1.32×** across 9 paired seasons.
- **All build scripts** updated to handle the new component:
  - `build_v3.py` — extends goal handler, adds shot-on-goal and missed-shot handlers
  - `build_player_cards.py` — POS_EVENTS list updated
  - `build_dashboard.py` — EMBED_COLS updated
  - `build_validation_summary.py` — adds `raw_close_shots` row to per-event PO/RS table; updates labels (V3 → V3.1, "v3 r" → "v3.1 r")
  - `build_yoy_stability.py`, `build_playoff_delta.py` — HTML titles updated to v3.1
- **Validation defaults**: `build_yoy_stability.py`, `build_playoff_delta.py`, `build_validation_summary.py` now default `--output-dir` to repo root rather than `viz/` or `validation/` subdirs.
- **README**: full v3.1 rewrite with regenerated validation tables, close-shot row in per-event PO/RS, v3.1 prose leading.
- **GRIT_v3_FAQ.md**: new "What changed in v3.1?" and "Why are close shots a separate event from crease goals?" Q&As at the top; updated YoY tables and event-count references throughout.
- **v3_methodology.md**: §1 weights table drops v2 column and adds v3.1 column with close-shots row; §10 validation summary fully regenerated; §11 "Honest framing" rewritten for v3.1 framing (refinement, not replacement).

### Highlights

- **Power-forward archetype recovery**: Tavares, JVR, Kreider, Lee, B. Tkachuk now properly surface in top-30 movers across all validation seasons (2018-19, 2023-24, 2025-26). v3 understated this archetype because their value was concentrated in close-range attempts, not finished crease goals.
- **Empirical orthogonality**: close-shots vs hits-thrown correlation is r ≈ +0.12 — close shots are not redundant with the existing physical-engagement weights. The component captures a distinct dimension.
- **Close shots PO/RS = 0.96×** (range 0.82–1.08 across 9 paired seasons): close-range attempts dip slightly in the playoffs, consistent with the existing crease-goals 0.86× finding (getting clean looks from the dangerous area is harder against playoff defending).

### Considered and rejected

- **+3.0 weight for close shots** — tested first; dropped v3.1 ↔ v3 correlation to ~0.988 and tilted the metric too aggressively toward close-range scorers. +1.5 holds correlation at ~0.997 while still surfacing the missing power-forward archetype.

### Deferred

- **Renaming `raw_close_shots` to `raw_crease_shots`** for naming consistency with `raw_crease_goals`. Both events use the identical 12-ft Euclidean spatial test but carry different prefixes. Backward-compatible naming is preserved in v3.1; rename will land in v4.
- **EYP (Earning Your Points) framework** — quadrant analysis of GRIT-Z vs scoring rate, watchlist tracking. Re-runs under v3.1 thresholds tabled for v3.2.
- **Blue→Green trajectory analysis** — re-run under v3.1 thresholds. v3 finding (36 transitions in 5 seasons, mean +18.1 pts increase) needs revalidation; tabled for v3.2.
- **AllThreeZones tracked-data components** — DZ Puck Retrievals, Forecheck Recoveries, Exit Disruptions identified as viable additions; tabled for v3.2.
- **Cache and repo cleanup** — completed during the v3.1 publish but separate from the metric change. Repo `data/` purged (~165 MB of stale CSVs), PBP cache consolidated under `Version 3/cache/`, validation HTMLs aligned to repo root.

---

## [v3.0] — 2026-05-03

The v3 release tightened weights, changed pooling structure, and produced the first clean validation framework. Tagged as `v3.0` before the v3.1 development began.

### Changed (from v2.1)

Weight changes:

- **Crease-area goals**: +7.5 → **+10.0**. Top-tier weight; doorstep scoring elevated to highest-leverage scoring activity.
- **Fighting majors**: +5.5 → **+3.5**. Mid-tier; v2.1 robustness check showed regression-derived weight was inflated ~3× the design weight due to fighting's unusually high individual stability.
- **Hits thrown**: +2.5 → **+3.0**. Reflects highest YoY repeatability among GRIT events (r ≈ 0.92).
- **OZ giveaways**: −1.0 → **0.0**. Removed penalty; an OZ giveaway often reflects attempting a high-danger play, the same activity GRIT rewards positively.

Pooling change:

- **F/D → C/W/D**. Centers split from wings; defense unchanged. The argument: a winger structurally cannot win a defensive-zone faceoff. CWD pooling makes the comparison fair (each pool contains players who can plausibly produce the same set of events). The cost is reduced pool sizes (~370 → ~180-200), which mechanically reduces YoY stability by ~2-3 points of correlation.

### Added

- **First end-to-end validation framework** with `build_validation_summary.py`, `build_yoy_stability.py`, and `build_playoff_delta.py`.
- **SQL Server backend**: `grit_scores`, `grit_monthly`, `grit_spatial` tables; bulk loader scripts.
- **Player card sidecar JSON** — split monolith HTML into thin shell + sidecar JSON.
- **Coordinate bug fix in `build_v3.py`**: home/away spatial branches were copy-paste identical (away attacking direction wrongly set to `home_def` instead of opposite). Fixed; spatial x range now correctly spans −99 to +99.

### Highlights

- **YoY mean r = 0.876** across 8 consecutive-year pairs.
- **Pool sizes balanced under CWD** (25-26 example: C=187, W=187, D=204).
- **Playoff inflation mean = 1.34×** across 9 paired seasons.

---

## [v2.1] — pre-v3

Bug fixes and methodology realignment from v2. No fundamental design changes.

### Fixed

- **Three v2 PK strength-inversion bugs**:
  - `raw_blocked_shots` — was counting PP blocks; now correctly counts PK blocks
  - `raw_hits_taken` — was counting PP hits taken; now correctly counts PK hits taken
  - `raw_penalties_drawn` — was counting PP penalty draws; now correctly counts PK draws

  Pattern: v2 inverted strength state for "recipient" events while correctly classifying "actor" events. Likely cause was separate join logic between actor and recipient event roles.

### Changed

- **HD spatial definitions standardized**: 12-ft circle for crease goals, slot rectangle (`|x| ≥ 70` AND `|y| ≤ 18`) for both HD takeaways AND HD blocks.
- **Block subdivision introduced**: HD blocks +4.0, non-HD blocks +3.0 (v2 used a single combined +3.0).
- **Physical minor list documented and frozen**: roughing, charging, boarding, cross-checking, elbowing, interference. Slashing, high-sticking, tripping, hooking, holding explicitly excluded.

---

## [v2] — pre-v2.1

Initial weighted composite. Established the core thesis (contested-puck contribution as a measurable dimension) and the fourteen-component framework. F/D pooling. Subsequent bug discoveries and methodology refinement led directly to v2.1.

---

## [v1] — original

Concept exploration. Counted physical and contested events; not yet a weighted composite metric. Superseded by v2.

---
