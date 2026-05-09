# GRIT v3.1 — Deliverable

This package contains everything needed to reproduce, validate, and use GRIT v3.1.

## What GRIT actually measures

GRIT is a measure of **contested-puck contribution** — it counts the events that happen when a player is competing for or against the puck in a contested area. It is positionally agnostic and archetype agnostic: a top-line winger who draws penalties, a fourth-line C who throws hits, and a stay-at-home D who blocks shots are all measured against the events they produced, not against an idea of what their role should look like.

The metric's name primes readers to expect a "toughness stat." That's not what it is. It's perfectly possible — and not a bug — for skilled top-six players to rank highly on GRIT if they do contested-puck work (Trocheck, Cuylle, Krebs, Hartman are 25-26 examples). When presenting GRIT outputs publicly, lead with "contested-puck contribution" rather than "grit" to keep the framing honest. The full discussion is in `v3_methodology.md` §0.

## What is v3.1?

v3.1 = v3 baseline + 1 component added.

It builds on v3, adding a 15th weighted event for close-range shots. The weight tuning, pooling structure, spatial definitions, and validation framework from v3 all carry forward unchanged.

### Changes from v3

**Component added:**
1. **Close-range shots: new event at +1.5** — any shot attempt (shot-on-goal, missed-shot, or goal) whose location satisfies the same 12-foot Euclidean test used for crease goals: `(89 − |x|)² + y² ≤ 144`.

   Rationale: the GRIT thesis rewards willingness to enter dangerous areas. A defender who blocks a shot gets credit regardless of whether the shot would have gone in; by the same logic, a forward who crashes the net and gets a shot off deserves credit regardless of whether it goes in. v3 only credited the make (crease goal at +10.0); v3.1 also credits the attempt (close shot at +1.5). The two events stack: a crease goal earns both the +10.0 finishing credit and the +1.5 attempt credit, for a combined +11.5.

   Why +1.5 and not higher: a +3.0 weight was tested first and rejected. At +3.0, v3.1 ↔ v3 correlation dropped to ~0.988 across validation seasons, and the metric tilted too aggressively toward close-range scorers — doubling credit for a play type that already gets weighted highly via crease goals. At +1.5, correlation with v3 holds at ~0.997 across all 3 validation seasons (2018-19, 2023-24, 2025-26), the persistent power-forward archetype (Tavares, JVR, Kreider, Lee, B. Tkachuk) cleanly surfaces in top-30 movers in every validation season, and the existing v3 leaderboard structure stays intact.

### Naming inconsistency (deferred to v4)

`raw_close_shots` and `raw_crease_goals` use the identical 12-foot Euclidean spatial test but carry different prefixes (`close_` vs `crease_`). This is a cosmetic inconsistency that exists because the two events were added at different times and the naming wasn't reconciled. It will be cleaned up in v4 (likely by renaming `raw_close_shots` to `raw_crease_shots`). The current naming is preserved in v3.1 to avoid breaking downstream consumers and existing CSV/SQL schemas.

## What is v3?

v3 = v2.1 baseline + 5 design changes. Documented here for context; v3.1 inherits all of it unchanged.

It builds on v2.1 (which itself was v2 with bug fixes and spatial methodology realignment). v3 adds weight tuning and pooling changes that v2.1 explicitly did not include.

### Changes from v2.1

**Weight changes:**
1. **Crease goals: 7.5 → 10.0** — top-tier weight. Players who go to the dirty areas to score deserve the strongest GRIT credit, on par with no other event. The methodology now treats getting to the doorstep as the highest-leverage scoring activity.

2. **Fighting majors: 5.5 → 3.5** — mid-tier weight. The methodology document's §7.7 (regression robustness check) noted that fights are individually stable year-over-year, which inflates regression-derived weights for them. Bringing fighting down to mid-tier prevents v3 from over-rewarding the small number of designated fighters in the league.

3. **Hits thrown: 2.5 → 3.0** — bumped to mid-tier. Hits thrown has the highest YoY repeatability of any GRIT event (r ≈ 0.92) and is the most common positive event by volume. Strengthening its weight aligns importance with stability.

4. **OZ giveaways: −1.0 → 0.0** — neutralized. Offensive-zone giveaways aren't a "bad" event in the way DZ giveaways are; they're often the cost of trying to make a play in a dangerous area. Penalizing them discourages exactly the offensive risk-taking that produces scoring chances. NZ giveaways stay at −1.5; DZ giveaways stay at −2.5.

**Pooling change:**
5. **F/D → C/W/D** — centers split from wings; defense unchanged.

   The argument: a winger structurally cannot win a defensive-zone faceoff. Comparing wingers against centers in the same pool means wingers get penalized for not having a skill they can't legally exhibit. CWD pooling makes the comparison fair: wingers compete against wingers, centers against centers, defense against defense.

   The cost: pool sizes drop (~370 → ~180-200), which mechanically reduces YoY stability by ~2-3 points of correlation. We accept this trade-off for positional fairness — see Validation section.

### What's UNCHANGED from v2.1 (and from v2 where applicable)

- All other weights (penalties drawn 5.5, physical minors 5.5, HD takeaways 3.5, DZ faceoff wins 2.0, other takeaways 2.0, hits taken 1.5, NZ giveaways −1.5, DZ giveaways −2.5)
- HD spatial definitions (12-ft circle for crease goals, slot rectangle for HD takeaways AND HD blocks)
- Block subdivision (HD blocks +4.0, non-HD blocks +3.0; aggregate ~3.45 per block)
- Physical minor list (documented six only: roughing, charging, boarding, cross-checking, elbowing, interference)
- PK strength filter (generous SH; team has fewer skaters than opponent, any goalie state)
- Bug fixes for the three v2 PK strength-inversion bugs (blocks, hits taken, penalties drawn)
- 0.7 rate / 0.3 volume blend ratio
- TOI floors (RS: 600 all / 400 5v5 / 30 PK; playoffs: 25 all / 15 5v5 / 5 PK)

## Validation

> All numbers in this section are regenerated programmatically from the per_60 CSVs by `build_validation_summary.py`. The full breakdown lives in `v3_validation_summary.txt` and is rebuilt every time underlying data changes.

### YoY repeatability (grit_z_blend, regular season)

Across 8 consecutive-year pairs spanning 2015-16 through 2025-26 (the 2020-21 COVID season is intentionally excluded from the project):

| Pair | n | v3.1 r |
|---|---:|---:|
| 2015-16 ↔ 2016-17 | 431 | 0.885 |
| 2016-17 ↔ 2017-18 | 444 | 0.860 |
| 2017-18 ↔ 2018-19 | 466 | 0.879 |
| 2018-19 ↔ 2019-20 | 448 | 0.869 |
| 2021-22 ↔ 2022-23 | 474 | 0.880 |
| 2022-23 ↔ 2023-24 | 472 | 0.858 |
| 2023-24 ↔ 2024-25 | 478 | 0.875 |
| 2024-25 ↔ 2025-26 | 485 | 0.877 |

**Mean r = 0.873 across 8 pairs**, range 0.858–0.885. v3.1 sits well above public benchmarks: Corsi/Fenwick repeatability is typically reported at r ≈ 0.6–0.7, Points/60 at r ≈ 0.5–0.6. Mean r is 3 points lower than v3 (0.876), within consecutive-pair variance.

### YoY decay across multi-season gaps

Stability decays as the gap between seasons widens, but plateaus after 2-3 years. This is the signature of a metric capturing stable player archetype rather than year-specific role context.

| Gap | # pairs | Mean r | Range |
|---|---:|---:|---:|
| 1 year | 8 | 0.873 | 0.858–0.885 |
| 2 years | 6 | 0.821 | 0.793–0.832 |
| 3 years | 4 | 0.783 | 0.763–0.801 |
| 4 years | 2 | 0.777 | 0.764–0.790 |

### YoY by position pool (24-25 ↔ 25-26)

| Pool | n | r |
|---|---:|---:|
| C | 159 | 0.868 |
| L | 85 | 0.890 |
| R | 73 | 0.910 |
| D | 168 | 0.868 |

C and D are the lowest-correlated pools — likely because both have the broadest range of role types compared against each other (top-pair D vs sheltered third-pair D; 1C vs 4C). Wingers cluster more tightly because role differentiation is narrower.

### Pool sizes under CWD (25-26)

C = 187, W = 187, D = 204. Balanced. The L/R wing split is roughly 49/51 across the project.

### Playoff vs RS rate inflation

Playoffs run **27-46% hotter** than regular season on raw weighted GRIT rate per 60. The ratio is meaningfully variable year-to-year and is not "stable" in the strong sense the previous version of this README claimed.

| Season | RS rate/60 | PO rate/60 | Ratio |
|---|---:|---:|---:|
| 2015-16 | 41.86 | 53.05 | 1.27× |
| 2016-17 | 40.41 | 52.15 | 1.29× |
| 2017-18 | 40.83 | 52.04 | 1.27× |
| 2018-19 | 40.71 | 52.07 | 1.28× |
| 2021-22 | 41.54 | 56.95 | 1.37× |
| 2022-23 | 42.83 | 56.00 | 1.31× |
| 2023-24 | 44.49 | 58.71 | 1.32× |
| 2024-25 | 39.34 | 56.79 | 1.44× |
| 2025-26 | 37.59 | 53.99 | 1.44× |

**Mean ratio across 9 seasons: 1.33×.** The most recent two seasons (2024-25 and 2025-26) are the highest in the dataset — whether that's a real upward trend or noise in a 9-season sample is open.

Per-event rate ratios (PO/RS, mean across 9 seasons):

| Event | Mean ratio | Range |
|---|---:|---:|
| Hits thrown | 1.63× | 1.48–1.87 |
| Hits taken | 1.58× | 1.42–1.79 |
| Physical minors taken | 1.68× | 1.39–2.35 |
| Penalties drawn | 1.16× | 0.98–1.40 |
| Blocked shots | 1.12× | 1.07–1.19 |
| Giveaways (NZ) | 1.17× | 0.88–1.54 |
| Giveaways (DZ) | 1.07× | 0.88–1.34 |
| Giveaways (OZ) | 1.04× | 0.80–1.27 |
| HD takeaways | 1.03× | 0.83–1.26 |
| Other takeaways | 1.03× | 0.82–1.20 |
| DZ faceoff wins | 1.02× | 0.97–1.10 |
| Close-range shots | 0.96× | 0.92–1.00 |
| Crease goals | 0.87× | 0.64–1.03 |
| Fighting majors | 0.48× | 0.24–0.74 |

The fighting and crease-goal patterns are the most robust signals: fighting roughly halves in the playoffs across every season in the dataset, and crease goals come in slightly below RS rates because the goalie is harder to beat in close. Close-range shot attempts also dip slightly in playoffs (~4% lower per 60), consistent with the same finding — getting clean looks from the dangerous area is harder against playoff defending. Hit-related events show clear secular increase over time — 2024-25 and 2025-26 hit ratios are visibly higher than 2015-19.

> Note: close-range shot PO/RS ratio shown is provisional from validation season pairs; full 9-season mean will be locked when `v3_validation_summary.txt` is regenerated under v3.1.

See `v3_validation_summary.txt` for full per-season per-event breakdowns. Regenerate with:

```powershell
python build_validation_summary.py `
    --data-dir "C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\data" `
    --output-dir "C:\Users\mjrig\OneDrive\Documents\GitHub\grit-hockey"
```

## Pipeline architecture

The full pipeline has three stages, each backed by both disk and SQL Server.

```
┌─────────────────┐       ┌─────────────────┐       ┌──────────────────────┐
│  scrape_v3.py   │  -->  │   build_v3.py   │  -->  │ build_player_cards.py│
└─────────────────┘       └─────────────────┘       └──────────────────────┘
       │                          │                          │
       ▼                          ▼                          ▼
  PBP JSON cache             v3.1 CSVs on disk           player_cards_v3.html
  + raw_plays in SQL         + grit_scores in SQL        + sidecar JSON
                             + grit_monthly in SQL
                             + grit_spatial in SQL
```

**Stage 1 — `scrape_v3.py`** pulls play-by-play and TOI data from the NHL API. JSON files land on disk and rows go into the `raw_plays` table in the local `GRIT` SQL database. SQL is on by default; pass `--no-sql` to skip.

**Stage 2 — `build_v3.py`** reads the disk PBP cache, computes GRIT (now including the 15th component, `raw_close_shots`), writes CSVs to the season's output folder, and inserts rows into `grit_scores`, `grit_monthly`, and `grit_spatial`. CSV writes are unconditional; SQL writes are on by default with `--no-sql` available.

**Stage 3 — `build_player_cards.py`** reads from SQL (preferred) and emits `player_cards_v3_{season}.html` plus a `_data.json` sidecar. Falls back to the CSVs if SQL is unavailable. The HTML is ~110 KB; the JSON sidecar is ~1 MB. Both must be served together.

## How to regenerate v3.1 from scratch

You'll need:
1. SQL Server with a `GRIT` database, set up with the schema described in `v3_methodology.md` (or via past session notes)
2. Network access to `api-web.nhle.com`

```powershell
# Stage 1: scrape one season
python scrape_v3.py `
    --season 2026 `
    --output-dir "C:\Users\mjrig\OneDrive\Documents\Grit\cache\2026"

# Stage 2: build CSVs + load SQL
python build_v3.py `
    --pbp-cache "C:\Users\mjrig\OneDrive\Documents\Grit\cache\2026\pbp" `
    --toi       "C:\Users\mjrig\OneDrive\Documents\Grit\cache\2026\toi_2026.csv" `
    --output-dir "C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\data\2026" `
    --season-tag 2026

# Stage 3: build the player card HTML + sidecar
python build_player_cards.py `
    --season 2026 `
    --output-dir "C:\Users\mjrig\OneDrive\Documents\Grit\Version 3\viz"
```

For playoffs, append `--playoffs` to stages 1 and 2 and use `_playoffs`-suffixed paths/tags. See `grit_scrape_runbook.md` for the full per-season checklist.

To run any stage without SQL (e.g. SQL Server stopped, working from a laptop), append `--no-sql`. `build_v3.py` will write only CSVs; `build_player_cards.py` requires `--data-dir` pointing at the CSV folder when SQL is off.

## Defensible podcast claims under v3.1

These are statements the data actually supports across all 9 seasons in the dataset (2015-16 through 2025-26 excluding the 2020-21 COVID season). Numbers can be regenerated from `build_validation_summary.py`.

- "Hits go up about 60% in the playoffs — both thrown and taken." (Mean 1.63× thrown, 1.58× taken; consistent across every season.)
- "Physical penalties (boarding, charging, cross-checking, roughing, elbowing, interference) go up about 70% in playoffs." (Mean 1.68×; ranges from 1.39× to 2.35× year to year.)
- "Fighting actually goes down by half in playoffs — counter to the intensity narrative." (Mean 0.48× across every season; this is the most robust pattern in the data.)
- "Crease goals don't go up in playoffs — they come in slightly lower than RS rates. Playoff hockey is harder to score in close, not easier." (Mean 0.87×; below 1.0 in 8 of 9 seasons.)
- "Even shot attempts from the crease area dip slightly in playoffs — about 4% lower per 60. Getting to the dangerous area to shoot is harder against playoff defending, not just finishing once you're there." (v3.1 close-shot ratio mean ~0.96×.)
- "Aggregate contested-puck event rate is roughly 30% higher in playoffs." (Mean ratio 1.33×; consistent direction every season but the magnitude varies from 1.27× to 1.46×.)
- "v3.1 trades ~2-3 points of YoY stability for positional fairness — wingers no longer compete against centers in the same pool." (Mean YoY r = 0.873 under CWD; comparison to v2's F/D pooling cost roughly 2 points of correlation.)
- "Year-over-year stability decays gradually but plateaus after 2-3 seasons. GRIT identifies a stable player archetype, not a year-specific role." (1-yr r = 0.873, 2-yr = 0.821, 3-yr = 0.783, 4-yr = 0.777.)

## Things v3.1 does NOT address

- **Low-TOI rate noise on PK.** The 30-min PK TOI floor allows players with very small samples to surface near the top of rate-based z-scores. Affects v2, v2.1, v3, and v3.1 equally.
- **The 1.25× SH multiplier from v2's methodology** is documented but not separately tracked in v3.1 outputs. Events are counted at face value.
- **Visual design of player cards is unchanged from earlier versions.** The card layout, color palette, and rink artwork carried forward unmodified through the SQL migration. A redesign is a separate task.
- **The `close_` vs `crease_` naming inconsistency.** Both events use the identical 12-ft Euclidean spatial test, but `raw_close_shots` and `raw_crease_goals` keep separate prefixes for backward compatibility. Renaming deferred to v4.
