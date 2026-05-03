# GRIT v3 — Methodology Specification

This document specifies GRIT v3 in full. v3 builds on v2.1 (which itself fixed bugs and realigned spatial methodology in v2). See `v3_deliverable/methodology/` reference and v2.1 deliverable for the full lineage.

## 0. What GRIT measures (and what it doesn't)

GRIT measures **contested-puck contribution**. It counts what happens when players battle for pucks: hits thrown and taken, blocked shots, takeaways, crease-area goals, defensive-zone faceoff wins, penalties drawn, physical minors, fights, and giveaways, each weighted by its estimated value.

Critically, GRIT is **not** a measure of toughness, body size, role designation, or "grinding." Those concepts are how mainstream hockey commentary describes some of the players who tend to score well on GRIT, but they are descriptions of *archetype*, not of what the metric actually counts.

### What this means in practice

A 6'4" fourth-line center who blocks shots and throws 250 hits will score well on GRIT. So will a 5'10" top-line winger who draws 25 penalties and scores 12 crease goals. So will a top-six center who throws 200 hits while putting up 60 points. The metric doesn't distinguish between them based on role; it counts the contested events each of them produced.

Three concrete cases from the 25-26 leaderboard worth keeping in mind:

- **Peyton Krebs** (BUF, listed at 184 lb) — top-line winger and physical agitator, top-25 among NHL centers in v3 despite small stature and skilled-line deployment. Krebs throws hits, draws penalties, goes to the net, and wins faceoffs. The metric doesn't care that he's not a typical 4C grinder.
- **Vincent Trocheck** (NYR) — skilled 2C and 60+ point scorer, top-15 among NHL centers. His reputation as a finesse player undersells the physical engagement his event count reveals (193 hits, 18 penalties drawn).
- **Ryan Hartman** (MIN) — top-line agitator/scorer with low hit volume but 15 crease goals and 29 penalties drawn. Top-25 among NHL wings despite throwing fewer hits than essentially everyone else on that list. His contested-puck contribution comes from net-front scoring and penalty-drawing, not physical engagement.

If a reader's intuition says "Hartman shouldn't be on a grit list, he's not a grinder" — that's the reader applying an archetype filter the metric doesn't apply. v3 is identifying contested-puck contribution honestly. The metric and the archetype are different things, and that's a feature: it means GRIT can pick up a Krebs or a Trocheck or a Hartman when the archetype filter would miss them.

### Implication for naming and presentation

The acronym "GRIT" (Gritty Role Impact Total) is itself slightly misleading because it primes readers to expect a toughness metric. The honest product is a contested-puck contribution metric. Anywhere v3 outputs are presented publicly — podcasts, dashboards, written analysis — the framing should be "contested-puck contribution" first, not "grit." This is especially important when explaining unintuitive results.

## 1. Weights

| Event | v2 | v2.1 | v3 |
|---|---:|---:|---:|
| Crease-area goals | +7.5 | +7.5 | **+10.0** |
| Penalties drawn | +5.5 | +5.5 | +5.5 |
| Fighting majors | +5.5 | +5.5 | **+3.5** |
| Physical minors taken | +5.5 | +5.5 | +5.5 |
| HD takeaways | +3.5 | +3.5 | +3.5 |
| HD blocks | (combined +3.0) | +4.0 | +4.0 |
| Non-HD blocks | (combined +3.0) | +3.0 | +3.0 |
| Hits thrown | +2.5 | +2.5 | **+3.0** |
| DZ faceoff wins | +2.0 | +2.0 | +2.0 |
| Other takeaways | +2.0 | +2.0 | +2.0 |
| Hits taken | +1.5 | +1.5 | +1.5 |
| OZ giveaways | −1.0 | −1.0 | **0.0** |
| NZ giveaways | −1.5 | −1.5 | −1.5 |
| DZ giveaways | −2.5 | −2.5 | −2.5 |

### v3 weight change rationale

**Crease goals 7.5 → 10.0:** Top-tier weight. Players who score from the doorstep — tipping rebounds, jamming pucks past the goalie, going to the net through traffic — embody the GRIT thesis. v3 elevates this to the highest-leverage scoring activity.

**Fighting 5.5 → 3.5:** Mid-tier. The methodology document's §7.7 (regression robustness check) showed that fighting has unusually high individual stability year-over-year, which means regression-derived weights inflated it (~3× the design weight). Bringing fighting down to 3.5 prevents v3 from over-rewarding designated fighters who occupy a niche role on a small subset of teams.

**Hits thrown 2.5 → 3.0:** Hits thrown has the highest YoY repeatability of any GRIT event (r ≈ 0.92 in v2 historical analysis). It's also the most common positive GRIT event by volume. Aligning weight with stability is defensible.

**OZ giveaways −1.0 → 0.0:** Offensive-zone giveaways aren't comparable to DZ or NZ giveaways. They often reflect attempting a play in a dangerous area — the same thing GRIT rewards on the positive side via crease goals and HD takeaways. Penalizing them creates an internal contradiction (rewarding the attempt and punishing the failure of the same activity). NZ and DZ giveaways remain weighted negatively because puck-management failures in those zones genuinely cost teams.

## 2. Spatial definitions (inherited from v2.1)

**Crease-area goals:** A goal qualifies if its location satisfies `(89 − |x|)² + y² ≤ 144` (within 12 feet of the net, Euclidean). This is a circle around the goalmouth — captures going-to-the-net scoring, excludes wraparounds and bad-angle goals from below the goal line.

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

Three columns in v2's `grit_pk.csv` had inverted strength state — they counted events while the player was on the **power play** instead of the penalty kill. v3 corrects all three:

- `raw_blocked_shots` — was counting PP blocks; now correctly counts PK blocks
- `raw_hits_taken` — was counting PP hits taken; now correctly counts PK hits taken
- `raw_penalties_drawn` — was counting PP penalty draws; now correctly counts PK draws

The pattern: v2 inverted strength state for "recipient" events (player as blocker, hit recipient, penalty drawer) while correctly classifying "actor" events (player as hitter, takeaway taker, faceoff winner, giveaway committer, scorer). Likely cause was separate join logic between actor and recipient event roles.

## 6. Pooling — CHANGED in v3

**v3 uses C/W/D pooling.** Z-scores are computed within each pool:

- **C** (centers): position code `C`
- **W** (wings): position code `L` or `R`
- **D** (defense): position code `D`

This replaces v2 and v2.1's F/D pooling, where forwards (C+L+R) all competed in one pool against defensemen separately.

### Why CWD

A winger structurally cannot win a defensive-zone faceoff. Penalizing them in a pool that includes DZ-faceoff specialists isn't measuring contested-puck contribution; it's measuring "how center-like is this player." CWD pooling makes the comparison fair: each pool contains players who can plausibly produce the same set of events.

The cost is reduced pool sizes (~370 → ~180-200), which mechanically increases z-score noise. The trade-off is accepted on grounds of positional fairness. See Section 10 for full validation numbers.

## 7. Computation pipeline

Same as v2.1:

1. **Weighted aggregation:** sum `count_event × weight_event` across the 14 weighted components (15 with block subdivision counted separately, but `raw_blocked_shots` is the sum and is not separately weighted).
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

Same as v2.1, with no schema changes:

```
player_id, name, position, team, games_played, toi_min,
weighted_total, raw_grit_per_60, grit_per_game,
grit_z_pos, grit_z_vol, grit_z_blend,
raw_blocked_shots, raw_blocked_shots_hd, raw_blocked_shots_non_hd,
raw_crease_goals, raw_dz_faceoff_wins,
raw_fighting_majors, raw_giveaways_dz, raw_giveaways_nz,
raw_giveaways_oz, raw_hits_taken, raw_hits_thrown,
raw_penalties_drawn, raw_physical_minors_taken,
raw_takeaways_high_danger, raw_takeaways_other
```

`raw_blocked_shots` is preserved as the sum (HD + non-HD) for backward compatibility.

## 10. Validation summary

See `validation/v3_validation_summary.txt` for full numbers.

**YoY repeatability (full dataset, all skaters):**

| Season pair | GRIT z r | Fwd points r |
|-------------|:--------:|:------------:|
| 15-16 to 16-17 | 0.887 | 0.794 |
| 16-17 to 17-18 | 0.863 | 0.751 |
| 17-18 to 18-19 | 0.882 | 0.840 |
| 18-19 to 19-20 | 0.872 | 0.828 |
| 19-20 to 21-22 * | 0.803 | 0.744 |
| 21-22 to 22-23 | 0.883 | 0.813 |
| 22-23 to 23-24 | 0.861 | 0.832 |
| 23-24 to 24-25 | 0.878 | 0.836 |
| 24-25 to 25-26 | 0.879 | 0.840 |
| **Average** | **0.877** | **0.809** |

* Spans the COVID bubble and 2020-21 lockout gap. Both metrics drop as expected.

GRIT z is more stable year-over-year than forward points across every single season pair in the dataset. The average advantage is +0.068 r. This holds for forwards in isolation as well (avg GRIT z r = 0.876 vs points r = 0.809).

The stability gap is meaningful: it means a player's contested-puck contribution rank relative to peers is a more persistent signal than their scoring rank. The metric captures something structural about how players play, not just what they produced in a given year.

For context, public possession metrics (Corsi, Fenwick) typically show YoY r of 0.6-0.7 at the player level. Points per 60 for forwards is typically 0.5-0.6 for full samples but rises toward 0.8 when constrained to qualifying players as done here.

**v3 vs v2.1 (25-26 RS):** r ≈ 0.96 on `grit_z_blend`. v3 makes meaningful but not radical changes from v2.1.

**Pool sizes under CWD (25-26):** C=182, W=182, D=198. Balanced.

**Playoff vs RS rate inflation:** Consistent across all nine playoff seasons in the dataset. Overall GRIT rate runs approximately 1.43-1.64× the regular season baseline. Hits inflate most (~1.84×), physical minors follow (~2.02×), fighting runs counter-intuitively lower (~0.47×) — likely because designated fighters see reduced ice time in the playoffs. Signature is stable and robust across years.

## 11. Honest framing

**v3 is more conceptually coherent than v2 at the cost of ~2-3 points of YoY stability.** Don't claim v3 is "better validated" — by the cleanest validation criterion (YoY repeatability), v2 is better. v3 is preferred because:

1. Bug fixes (v2 had three confirmed strength-inversion bugs in the PK file)
2. Spatial methodology coherence (v2 had the wrong shape for HD takeaways in the all-strengths file)
3. Positional fairness in the comparison pool (v2's F pool penalized wingers for not being centers)
4. Defensible weight choices (v3 reflects considered design decisions; v2's weights were initial drafts)

The trade is conceptual integrity for raw stability. The metric remains strongly repeatable in absolute terms.

## 12. What v3 does NOT include

The following are intentionally out of scope:

- **TOI floor adjustments.** Low-TOI rate noise on PK is a known issue; v3 keeps v2's 30-min floor for backward consistency.
- **Component-level z-scoring before weighting.** v3 weights raw counts directly. An alternative approach (z-score each component within pool first, then sum the z-scores) would change the metric's behavior; not adopted in v3.
- **Position deployment context.** A center playing 22 minutes vs a center playing 12 minutes are compared at the rate level (per-60). The 0.3-volume blend partially addresses this; full deployment-controlling normalization is not v3 scope.
- **Multi-season aggregates.** v3 produces single-season files. Career or multi-season GRIT is computed downstream by the consumer.
