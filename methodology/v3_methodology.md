# GRIT v3.1 — Methodology Specification

This document specifies GRIT v3.1 in full. v3.1 builds on v3, which itself built on v2.1 (which fixed bugs and realigned spatial methodology in v2). See `v3_deliverable/methodology/` reference and v2.1 deliverable for the full lineage.

## 0. What GRIT measures (and what it doesn't)

GRIT measures **contested-puck contribution**. It's a positionally-agnostic, archetype-agnostic count of the events that happen when a player is competing for or against a puck in a contested area: hits thrown and taken, blocked shots, takeaways and giveaways, defensive-zone faceoff wins, penalties drawn, physical minors, fights, crease-area goals, and (new in v3.1) close-range shot attempts.

Critically, GRIT is **not** a measure of toughness, body size, role designation, or "grinding." Those concepts are how mainstream hockey commentary describes some of the players who tend to score well on GRIT, but they are descriptions of *archetype*, not of what the metric actually counts.

### What this means in practice

A 6'4" fourth-line center who blocks shots and throws 250 hits will score well on GRIT. So will a 5'10" top-line winger who draws 25 penalties and scores 12 crease goals. So will a top-six center who throws 200 hits while putting up 60 points. The metric doesn't distinguish between them based on role; it counts the contested events each of them produced.

Three concrete cases from the 25-26 leaderboard worth keeping in mind:

- **Peyton Krebs** (BUF, listed at 184 lb) — top-line winger and physical agitator, top-25 among NHL centers in v3 despite small stature and skilled-line deployment. Krebs throws hits, draws penalties, goes to the net, and wins faceoffs. The metric doesn't care that he's not a typical 4C grinder.
- **Vincent Trocheck** (NYR) — skilled 2C and 60+ point scorer, top-15 among NHL centers. His reputation as a finesse player undersells the physical engagement his event count reveals (193 hits, 18 penalties drawn).
- **Ryan Hartman** (MIN) — top-line agitator/scorer with low hit volume but 15 crease goals and 29 penalties drawn. Top-25 among NHL wings despite throwing fewer hits than essentially everyone else on that list. His contested-puck contribution comes from net-front scoring and penalty-drawing, not physical engagement.

If a reader's intuition says "Hartman shouldn't be on a grit list, he's not a grinder" — that's the reader applying an archetype filter the metric doesn't apply. v3.1 is identifying contested-puck contribution honestly. The metric and the archetype are different things, and that's a feature: it means GRIT can pick up a Krebs or a Trocheck or a Hartman when the archetype filter would miss them.

### Implication for naming and presentation

The acronym "GRIT" (Gritty Role Impact Total) is itself slightly misleading because it primes readers to expect a toughness metric. The honest product is a contested-puck contribution metric. Anywhere v3.1 outputs are presented publicly — podcasts, dashboards, written analysis — the framing should be "contested-puck contribution" first, not "grit." This is especially important when explaining unintuitive results.

## 1. Weights

| Event | v2.1 | v3 | v3.1 |
|---|---:|---:|---:|
| Crease-area goals | +7.5 | +10.0 | +10.0 |
| Penalties drawn | +5.5 | +5.5 | +5.5 |
| Fighting majors | +5.5 | +3.5 | +3.5 |
| Physical minors taken | +5.5 | +5.5 | +5.5 |
| HD takeaways | +3.5 | +3.5 | +3.5 |
| HD blocks | +4.0 | +4.0 | +4.0 |
| Non-HD blocks | +3.0 | +3.0 | +3.0 |
| Hits thrown | +2.5 | +3.0 | +3.0 |
| DZ faceoff wins | +2.0 | +2.0 | +2.0 |
| Other takeaways | +2.0 | +2.0 | +2.0 |
| **Close-range shots** | — | — | **+1.5** |
| Hits taken | +1.5 | +1.5 | +1.5 |
| OZ giveaways | −1.0 | 0.0 | 0.0 |
| NZ giveaways | −1.5 | −1.5 | −1.5 |
| DZ giveaways | −2.5 | −2.5 | −2.5 |

### v3 weight change rationale (unchanged in v3.1)

**Crease goals 7.5 → 10.0:** Top-tier weight. Players who score from the doorstep — tipping rebounds, jamming pucks past the goalie, going to the net through traffic — embody the GRIT thesis. v3 elevated this to the highest-leverage scoring activity.

**Fighting 5.5 → 3.5:** Mid-tier. The methodology document's §7.7 (regression robustness check) showed that fighting has unusually high individual stability year-over-year, which means regression-derived weights inflated it (~3× the design weight). Bringing fighting down to 3.5 prevents v3 from over-rewarding designated fighters who occupy a niche role on a small subset of teams.

**Hits thrown 2.5 → 3.0:** Hits thrown has the highest YoY repeatability of any GRIT event (r ≈ 0.92 in v2 historical analysis). It's also the most common positive GRIT event by volume. Aligning weight with stability is defensible.

**OZ giveaways −1.0 → 0.0:** Offensive-zone giveaways aren't comparable to DZ or NZ giveaways. They often reflect attempting a play in a dangerous area — the same thing GRIT rewards on the positive side via crease goals and HD takeaways. Penalizing them creates an internal contradiction (rewarding the attempt and punishing the failure of the same activity). NZ and DZ giveaways remain weighted negatively because puck-management failures in those zones genuinely cost teams.

### v3.1 weight change rationale

**Close-range shots: new event at +1.5.** Any shot attempt (shot-on-goal, missed-shot, or goal) whose location satisfies the same 12-ft Euclidean test used for crease goals: `(89 − |x|)² + y² ≤ 144`.

The case for inclusion: the GRIT thesis rewards willingness to enter dangerous areas. A defender who blocks a shot gets credit regardless of whether the shot would have gone in; by the same logic, a forward who crashes the net and gets a shot off deserves credit regardless of whether it goes in. v3 only credited the make (crease goal at +10.0); v3.1 also credits the attempt (close shot at +1.5).

The two events stack by design. A crease goal earns both the +10.0 finishing credit and the +1.5 attempt credit, for a combined +11.5. This is intentional, not double-counting in a problematic sense — close-shots and crease-goals are conceptually different events (effort/exposure vs finishing in dangerous areas), and a player who does both is contributing on both axes.

The case for +1.5 specifically: a +3.0 weight was tested first and rejected. At +3.0, v3.1 ↔ v3 correlation dropped to ~0.988 across validation seasons, and the metric tilted too aggressively toward close-range scorers — doubling credit for a play type that already gets weighted highly via crease goals. At +1.5, correlation with v3 holds at ~0.997 across all 3 validation seasons (2018-19, 2023-24, 2025-26), the persistent power-forward archetype (Tavares, JVR, Kreider, Lee, B. Tkachuk) cleanly surfaces in top-30 movers in every validation season, and the existing v3 leaderboard structure stays intact.

The component is empirically separate from hits thrown despite both being labeled "physical engagement events" by some readers. Close-shots vs hits-thrown correlation is only r ≈ +0.12 across the dataset — they capture different player behaviors. The decision to include close-shots was made on theoretical grounds (the "willingness to enter dangerous places" argument), not on empirical clustering.

## 2. Spatial definitions (inherited from v2.1, extended in v3.1)

**Crease-area goals:** A goal qualifies if its location satisfies `(89 − |x|)² + y² ≤ 144` (within 12 feet of the net, Euclidean). This is a circle around the goalmouth — captures going-to-the-net scoring, excludes wraparounds and bad-angle goals from below the goal line.

**Close-range shots (new in v3.1):** Same 12-ft Euclidean test as crease goals. Any shot-on-goal, missed-shot, or goal whose location is within 12 feet of the net qualifies. Goals are counted in BOTH `raw_crease_goals` and `raw_close_shots` by design (see §1 v3.1 rationale).

**HD takeaway zone:** A takeaway qualifies as high-danger if `|x| ≥ 70` AND `|y| ≤ 18`. This is the slot rectangle (~19 ft deep, 36 ft wide). Captures both goalmouth strips AND high-slot takeaways during a setup.

**HD block zone:** Same slot rectangle as HD takeaways: `|x| ≥ 70` AND `|y| ≤ 18`. Non-HD blocks are everywhere else.

## 3. Physical minors penalty list (inherited from v2.1)

A 2-minute minor counts toward `raw_physical_minors_taken` only if its NHL `descKey` is one of:

- roughing
- charging
- boarding
- cross-checking
- elbowing
- interference

Slashing, high-sticking, tripping, hooking, holding are NOT included — these are stickwork or skating-deficit penalties, not physical engagement.

## 4. Strength-state filtering (inherited from v2.1)

- **All-strengths file** (`grit_per_60_v3_YYYY.csv`): no strength filter
- **5v5 file** (`grit_5v5_v3_YYYY.csv`): situation code `1551` only
- **PK file** (`grit_pk_v3_YYYY.csv`): generous SH (team has fewer skaters than opponent, regardless of goalie state)

## 5. Bug fixes from v2 (inherited from v2.1)

Three columns in v2's `grit_pk.csv` had inverted strength state — they counted events while the player was on the **power play** instead of the penalty kill. v3 corrected all three:

- `raw_blocked_shots` — was counting PP blocks; now correctly counts PK blocks
- `raw_hits_taken` — was counting PP hits taken; now correctly counts PK hits taken
- `raw_penalties_drawn` — was counting PP penalty draws; now correctly counts PK draws

The pattern: v2 inverted strength state for "recipient" events (player as blocker, hit recipient, penalty drawer) while correctly classifying "actor" events (player as hitter, takeaway taker, faceoff winner, giveaway committer, scorer). Likely cause was separate join logic between actor and recipient event roles.

## 6. Pooling (CHANGED in v3, unchanged in v3.1)

**v3.1 uses C/W/D pooling.** Z-scores are computed within each pool:

- **C** (centers): position code `C`
- **W** (wings): position code `L` or `R`
- **D** (defense): position code `D`

This replaces v2 and v2.1's F/D pooling, where forwards (C+L+R) all competed in one pool against defensemen separately.

### Why CWD

A winger structurally cannot win a defensive-zone faceoff. Penalizing them in a pool that includes DZ-faceoff specialists isn't measuring contested-puck contribution; it's measuring "how center-like is this player." CWD pooling makes the comparison fair: each pool contains players who can plausibly produce the same set of events.

The cost is reduced pool sizes (~370 → ~180-200), which mechanically increases z-score noise. Earlier validation against pre-coordinate-fix data showed v3 YoY repeatability about 2-3 points lower than v2's. The current v3.1 mean is r = 0.873 across 8 consecutive-year pairs (see README §Validation); v2 has not been re-tabulated against post-fix data, so the precise gap to v2 is not currently known. The qualitative trade-off — slightly lower stability in exchange for positional fairness — stands regardless.

## 7. Computation pipeline

Same as v2.1 with one component added:

1. **Weighted aggregation:** sum `count_event × weight_event` across the 15 weighted components in v3.1 (16 with block subdivision counted separately, but `raw_blocked_shots` is the sum and is not separately weighted). v3 had 14; v3.1 adds `raw_close_shots`.
2. **Rate normalization:** `weighted_total ÷ toi_min × 60` for per-60 rate.
3. **Volume normalization:** `weighted_total ÷ games_played` for per-game volume.
4. **C/W/D pool z-scoring:** within each pool, compute z-score on rate (`grit_z_pos`) and volume (`grit_z_vol`) separately.
5. **Blend:** `grit_z_blend = 0.7 × grit_z_pos + 0.3 × grit_z_vol`

## 8. TOI floors

Same as v2.1:

| File | Floor |
|---|---|
| RS all-strengths | 600 minutes |
| RS 5v5 | 400 minutes |
| RS PK | 30 minutes |
| Playoff all-strengths | 25 minutes |
| Playoff 5v5 | 15 minutes |
| Playoff PK | 5 minutes |

## 9. Output column structure

v3.1 adds `raw_close_shots` to the column list. All other columns unchanged from v3:

```
player_id, name, position, team, games_played, toi_min,
weighted_total, raw_grit_per_60, grit_per_game,
grit_z_pos, grit_z_vol, grit_z_blend,
raw_blocked_shots, raw_blocked_shots_hd, raw_blocked_shots_non_hd,
raw_close_shots, raw_crease_goals, raw_dz_faceoff_wins,
raw_fighting_majors, raw_giveaways_dz, raw_giveaways_nz,
raw_giveaways_oz, raw_hits_taken, raw_hits_thrown,
raw_penalties_drawn, raw_physical_minors_taken,
raw_takeaways_high_danger, raw_takeaways_other
```

`raw_blocked_shots` is preserved as the sum (HD + non-HD) for backward compatibility.

## 10. Validation summary

Numbers below are regenerated programmatically from the per_60 CSVs by `build_validation_summary.py`. The full breakdown lives in `v3_validation_summary.txt` at the repo root and is rebuilt every time underlying data changes. See README §Validation for the per-pair tables; this section gives the rolled-up summary.

**YoY repeatability:** v3.1 mean r = 0.873 across 8 consecutive-year pairs spanning 2015-16 through 2025-26 (excluding the 2020-21 COVID season). Range 0.858–0.885. Sits well above public benchmarks (Corsi/Fenwick ~0.6–0.7, Points/60 ~0.5–0.6). v3 was 0.876 across the same pairs; the 0.003 drop from adding the close-shot component is within consecutive-pair variance.

**YoY decay across multi-season gaps:** 1-year mean r = 0.873, 2-year = 0.821, 3-year = 0.783, 4-year = 0.777. Plateaus after 2-3 years — consistent with a metric capturing stable player archetype rather than year-specific role context.

**Pool sizes under CWD (25-26):** C = 187, W = 187, D = 204. Balanced. Pool sizes hold roughly steady across the dataset (C and D both 180-210; W ranges 150-190 with some growth over time).

**Playoff vs RS rate inflation:** Mean composite ratio 1.32× across 9 paired seasons, range 1.26×–1.43×. Hits ~1.63× (thrown) and 1.58× (taken). Physical minors ~1.67×. Fighting ~0.48× (the most robust signature — fighting halves in playoffs every year). Crease goals ~0.86× (slightly below RS — net-front scoring is harder against playoff goaltending). Close-range shot attempts ~0.96× (also below RS — getting clean looks from the dangerous area is harder against playoff defending, even before the finishing question). The aggregate ratio is meaningfully variable year to year and should not be characterized as "stable" in the strong sense; the most recent two seasons (2024-25 and 2025-26) sit visibly higher than 2015-2019.

**Per-pool YoY (24-25 → 25-26):** C r = 0.865, L r = 0.890, R r = 0.909, D r = 0.867. The wing pools cluster more tightly than centers and defense, likely because the role-type range within wings is narrower.

## 11. Honest framing

**v3.1 is a refinement of v3, not a replacement.** Adding the close-shot component preserves v3's structure (same pooling, same other weights, same spatial definitions, same TOI floors) and adds one component that captures a behavior the v3 metric was missing. v3.1 ↔ v3 correlation is ~0.997, meaning the rank order is essentially preserved. v3.1 is preferred over v3 because:

1. The close-shot component directly captures the "willingness to enter dangerous areas" half of the GRIT thesis that v3 only captured for finished goals.
2. The persistent power-forward archetype (Tavares, JVR, Kreider, Lee, B. Tkachuk) properly surfaces in v3.1 where it was understated in v3.
3. No regressions: YoY stability is within noise of v3 (0.873 vs 0.876), playoff inflation is within noise (1.32× vs 1.34×), and the pooling/weight changes that made v3 conceptually coherent are preserved.

The trade for v3.1 over v3 is genuinely small. For users who want the v3 numbers exactly, they remain available in tagged commits.

The v3 → v2 comparison stands: v3 is more conceptually coherent than v2, with bug fixes, spatial methodology coherence, positional fairness, and defensible weight choices. Earlier validation against pre-coordinate-fix data suggested v3 was about 2-3 points lower in YoY repeatability than v2; v2 has not been re-tabulated against post-fix data, so the current gap is unknown.

## 12. What v3.1 does NOT include

The following are intentionally out of scope:

- **TOI floor adjustments.** Low-TOI rate noise on PK is a known issue; v3.1 keeps v2's 30-min floor for backward consistency.
- **Component-level z-scoring before weighting.** v3.1 weights raw counts directly. An alternative approach (z-score each component within pool first, then sum the z-scores) would change the metric's behavior; not adopted.
- **Position deployment context.** A center playing 22 minutes vs a center playing 12 minutes are compared at the rate level (per-60). The 0.3-volume blend partially addresses this; full deployment-controlling normalization is not v3.1 scope.
- **Multi-season aggregates.** v3.1 produces single-season files. Career or multi-season GRIT is computed downstream by the consumer.
- **Naming consistency between `raw_close_shots` and `raw_crease_goals`.** Both events use the identical 12-ft Euclidean spatial test, but they carry different prefixes (`close_` vs `crease_`). This is a cosmetic inconsistency that will be cleaned up in v4 (likely by renaming `raw_close_shots` to `raw_crease_shots`). Backward-compatible aliases in the CSV columns and SQL schema are preserved in v3.1 to avoid breaking downstream consumers.

## 13. Changes from v3

A summary of what changed and what didn't, for users moving from v3 to v3.1.

### What's new

**One component added:** `raw_close_shots` at +1.5 weight. See §1 (v3.1 rationale), §2 (spatial definition), and §10 (validation impact) for full detail.

### What stayed the same

Everything else. v3.1 inherits unchanged:

- All v3 weight choices (crease goals 10.0, fighting 3.5, hits thrown 3.0, OZ giveaways 0.0)
- C/W/D pooling
- HD spatial definitions (12-ft circle for crease goals, slot rectangle for HD takeaways AND HD blocks)
- Block subdivision (HD blocks +4.0, non-HD blocks +3.0)
- Physical minor list (six penalty types)
- PK strength filter (generous SH)
- 0.7 rate / 0.3 volume blend ratio
- TOI floors (RS 600/400/30; playoffs 25/15/5)
- Output column structure (one column added; nothing removed or renamed)

### What v3.1 ↔ v3 correlation looks like

Across the 3 validation seasons (2018-19 RS, 2023-24 RS, 2025-26 RS), v3.1 grit_z_blend correlates with v3 grit_z_blend at r ≈ 0.997. The metric reorders some players — the "movers" are heavily concentrated in the power-forward archetype that gets close-shot credit it didn't have under v3 — but the leaderboard structure is preserved.

### What weight was rejected

A +3.0 weight for close-range shots was tested before settling on +1.5. At +3.0, v3.1 ↔ v3 correlation dropped to ~0.988, and the metric tilted aggressively toward close-range scorers. The +1.5 weight was chosen as the lightest weight at which the close-shot component meaningfully surfaces the missing power-forward archetype while keeping v3.1 structurally aligned with v3.

### Which other components were considered for v3.1

Three AllThreeZones tracked-data items were evaluated and deferred:

- **DZ Puck Retrievals** — viable for v3.2, requires AllThreeZones data ingestion path
- **Forecheck Recoveries** — viable for v3.2, same data path
- **Exit Disruptions** — viable for v3.2, same data path

Three were considered and ruled out:

- **Forecheck Offense** — off-thesis (offensive zone success isn't the same as contested-puck contribution)
- **Botched Retrievals** — high double-count risk with existing DZ giveaways
- **Passing data** — too noisy at the granularity needed for GRIT pooling

## 14. The EYP (Earning Your Points) framework

EYP is an analytical layer on top of the per-season GRIT outputs. It is not part of the GRIT metric. It is a way of reading the metric to ask one question: among forwards who contribute contested-puck value but are not scoring, what happens to them, and does GRIT tell you which ones break out.

### Quadrant definition

For qualifying forwards (GP >= 40, positions C/L/R) in a season, EYP splits on two axes:

- Vertical: GRIT-Z (grit_z_blend) at 0. At or above 0 is "high grit."
- Horizontal: an ABSOLUTE points bar, not the per-season median. The bar is 41 points (0.5 pts/game over 82) for full seasons, pro-rated for shortened seasons (2019-20, tag 2020, ran 71 games, so 0.5 * 71 = 35.5).

That gives four quadrants:

- GREEN (hi grit, at/above bar): contributing contested-puck value and scoring.
- RED (lo grit, at/above bar): scoring without the contested-puck profile.
- BLUE (hi grit, below bar): contested-puck value without the scoring. The watchlist quadrant.
- GRAY (lo grit, below bar): below both.

The points axis was originally the per-season median. That was wrong. A median split mechanically forces roughly 50/50 above and below, which guarantees symmetric crossing rates and makes any "players cross the line" finding partly an artifact of the split itself. The absolute bar fixes a real scoring level (41 points), so "high scoring" is a genuine minority population (about 40 percent of qualifying forwards), and crossing the bar means something fixed rather than something relative to that year's field. All figures below are on the absolute bar.

The classification logic (the bar, the pro-ration, and assign_quadrant) lives in eyp_common.py as the single source of truth, imported by build_eyp.py, build_eyp_career.py, and build_eyp_career_html.py so the three cannot drift.

### The Blue-to-Green question

The original EYP thesis was that BLUE forwards are undervalued breakouts waiting to happen, and that GRIT identifies them. The Blue-to-Green (btog) analysis tested that and forced a correction to the thesis.

A btog transition is a forward who is BLUE in one season and GREEN in the next qualifying season. There is one definitional fork, and the project reports both:

- Exclusive (literal consecutive years): the 2020 to 2022 pair does NOT count, because the unobserved 2020-21 COVID season sits between them and you cannot attribute a clean year-over-year jump across a season you never measured. This is what compute_ever_btog in build_eyp_career.py does. 70 transitions across 63 players.
- Inclusive (treat 2020 and 2022 as a player's consecutive qualifying seasons): the 9 COVID-gap crossings count. 79 transitions across 69 players.

**Points delta when a transition happens.**

| | Exclusive (70 tr / 63 pl) | Inclusive (79 tr / 69 pl) |
| --- | --- | --- |
| Raw delta, mean / median | +17.0 / +16 | +18.4 / +17 |
| Raw, percent positive | 100% | 100% |
| Per-82 delta, mean / median | +13.2 / +11.3 | +14.5 / +12.6 |
| Per-82, percent positive | 91.4% | 92.4% |

The raw figure is impressive and almost entirely an artifact. BLUE is below the bar and GREEN is at or above it, so a btog transition is by construction a player crossing the bar from below. The points had to go up. The 100-percent-positive figure is forced by the selection rule, not evidence about grit, and should be reported as such. Pace-adjusting to per-82 is the honest magnitude: about +13 to +14.5 points depending on definition. The inclusive number runs hotter because the 9 COVID-gap crossings cross the short 2020 season (about 62 games for those players) into a full 2022, and that games-played gap inflates the raw jump. The exclusive +13.2 per-82 is the conservative figure to lead with.

### The finding that matters: GRIT does not predict the jump

The delta analysis only describes transitions that happened. The real question is the base rate, and whether blue-season GRIT forecasts who crosses.

**Base rate.** Of BLUE forwards with a qualifying next season, only about 13 percent reach the bar the following year (13.2% exclusive, 13.8% inclusive). The dominant outcome for a BLUE forward is to stay BLUE. The watchlist quadrant is mostly a holding pattern.

**Does blue-season GRIT forecast the jump? No, and on the absolute bar it is a mild negative signal.** Forwards who crossed had LOWER blue-season grit-z than those who stayed (0.67 vs 0.99 exclusive, p = 0.0012; 0.65 vs 0.99 inclusive, p = 0.0002). In a logistic model the grit-z coefficient is below 1 per SD (odds ratio about 0.66). What forecasts the jump is proximity to the bar (a BLUE forward close to 41 points is far likelier to cross than one 20 below) and age. Grit adds nothing on top of those, and if anything cuts against the jump. That matches hockey sense: the purest grinders are grinders, not scorers-in-waiting.

**The control confirms it.** Running the same crossing test on GRAY forwards (low grit, below the bar) is the low-grit analog. Low-grit below-bar forwards reach the bar at about 28 percent (27.7% exclusive, 28.0% inclusive), more than double the BLUE rate of 13 percent. A below-bar forward is MORE likely to start scoring if their grit is low, not high. The proximity mechanism is identical in both pools, so the crossing is regression toward the bar, grit-independent, and high grit is associated with a lower chance of an offensive breakout.

### Corrected framing of EYP

The thesis "high GRIT identifies undervalued forwards about to break out offensively" is not supported. Grit is not the active ingredient, and a filter using only age and points-proximity, with no grit term, would find the same transitions. What survives:

- GRIT is the population screen, not the breakout predictor. The BLUE quadrant defines which contested-puck forwards are worth looking at at all. It does not rank them by breakout likelihood.
- Within that population, age and proximity to the bar do the predicting. The headline watchlist filter (young, close to the bar) is a legitimate screen for likelier breakouts, but the lift comes from age and proximity, not grit.

This is not a problem for GRIT. GRIT was never built to forecast scoring, and Section 0 already states that orthogonality to traditional production is a feature. The btog test confirms grit is orthogonal to scoring trajectory as well, which is consistent with the metric measuring something traditional stats miss rather than a leading indicator of them. The metric's validation rests where it always did: year-over-year repeatability, the team-balance thesis, and bottom-six role evaluation.

Reporting the grit-z result explicitly is the point of this section. Anyone evaluating the watchlist will run this exact test. Publishing it first, including the negative-control comparison against GRAY, is what makes the framework credible rather than something that collapses on first inspection.

### Reproducibility

All figures regenerate from the per-season eyp_v31_{year}.csv files (rebuilt on the absolute bar) and eyp_career_v31.csv. The transition set is BLUE in season Y and GREEN in the next qualifying season; the exclusive count uses literal consecutive years only, the inclusive count also accepts the 2020 to 2022 pair. The predictor test links each BLUE forward-season to its next qualifying season and asks whether the player reached the bar (GREEN or RED). pts_gap is bar minus points (positive below the bar).
