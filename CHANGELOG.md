# Changelog

All notable changes to GRIT (Gritty Role Impact Total).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions before v3.1 are documented retroactively; only v3.1 and forward have authoritative release dates.

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
