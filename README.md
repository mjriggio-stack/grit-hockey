# grit-hockey
# GRIT v3 — Deliverable

This package contains everything needed to reproduce, validate, and use GRIT v3.

## What GRIT actually measures

GRIT is a measure of **contested-puck contribution** — it counts the events that happen when a player is competing for or against the puck in a contested area. It is positionally agnostic and archetype agnostic: a top-line winger who draws penalties, a fourth-line C who throws hits, and a stay-at-home D who blocks shots are all measured against the events they produced, not against an idea of what their role should look like.

The metric's name primes readers to expect a "toughness stat." That's not what it is. It's perfectly possible — and not a bug — for skilled top-six players to rank highly on GRIT if they do contested-puck work (Trocheck, Cuylle, Krebs, Hartman are 25-26 examples). When presenting GRIT outputs publicly, lead with "contested-puck contribution" rather than "grit" to keep the framing honest. The full discussion is in `methodology/v3_methodology.md` §0.

## What is v3?

v3 = v2.1 baseline + 5 design changes.

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

### YoY repeatability (grit_z_blend, regular season)

| Pair | v2 r | v3 r | Δ |
|---|---:|---:|---:|
| 22-23 ↔ 23-24 | 0.877 | 0.851 | −0.026 |
| 23-24 ↔ 24-25 | 0.886 | 0.869 | −0.018 |
| 24-25 ↔ 25-26 | 0.892 | 0.865 | −0.026 |

**v3 is ~2-3 points less stable than v2** — the cumulative cost of the design changes, primarily CWD pooling. v3's r still sits well above public benchmarks: Corsi/Fenwick repeatability is typically reported at r ≈ 0.6-0.7, Points/60 at r ≈ 0.5-0.6.

### v3 YoY by position pool (24-25 ↔ 25-26)

| Pool | n | r |
|---|---:|---:|
| C | 149 | 0.853 |
| D | 157 | 0.839 |
| L | 72 | 0.911 |
| R | 67 | 0.913 |

The C and D pools are the weakest. C splitting from F is the structural cost of CWD pooling.

### Pool sizes under CWD (25-26)

C=182, W=182, D=198. Balanced.

### Playoff vs RS rate inflation (stable across 4 seasons)

Playoffs run **45-65% hotter** than regular season on raw weighted GRIT rate per 60.

| Season | RS rate/60 | PO rate/60 | Ratio |
|---|---:|---:|---:|
| 22-23 | 41.21 | 58.74 | 1.43× |
| 23-24 | 42.71 | 62.48 | 1.46× |
| 24-25 | 37.96 | 59.56 | 1.57× |
| 25-26 | 37.66 | 61.73 | 1.64× (R1 only) |

Per-event rate ratios (mean across 4 seasons):
- Hits thrown: 1.84× (nearly doubles)
- Hits taken: 1.79×
- Physical minors: 2.02× (more than doubles)
- Penalties drawn: 1.30×
- Blocks: 1.17×
- Crease goals: 0.90× (slightly down — playoffs harder to score)
- Fighting: 0.47× (halves — counterintuitive but stable across all four seasons)

See `validation/v3_validation_summary.txt` and `validation/v3_validation_results.json` for full numbers.

## v2.1 → v3 Sabres example (25-26 RS)

For eye-test calibration, the Sabres list under v3 vs v2.1:

| Player | Pos | v2.1 z | v3 z | Notes |
|---|---|---:|---:|---|
| Beck Malenstyn | L | +2.36 | +2.95 | Hits weight bump → big lift |
| Luke Schenn | D | +2.44 | +2.59 | D pool unchanged |
| Sam Carrick | C | +1.82 | +1.42 | CWD pool: C now competes vs C only |
| Logan Stanley | D | +1.18 | +1.09 | |
| Peyton Krebs | C | +1.28 | +1.02 | CWD adjustment |
| Mattias Samuelsson | D | +0.78 | +0.78 | |
| Alex Tuch | R | −0.12 | +0.17 | OZ giveaway removal lifts him |
| Conor Timmins | D | +0.25 | +0.15 | |
| Josh Doan | R | −0.18 | +0.12 | OZ giveaway removal + crease goal weight bump |
| Josh Norris | C | +0.43 | +0.05 | CWD: DZ faceoff value less unique vs C peers |
| Tanner Pearson | L | −0.32 | −0.02 | |
| Tage Thompson | C | +0.08 | −0.20 | CWD: shot-volume scorer less differentiated vs C peers |
| Zach Benson | L | −0.42 | −0.20 | |
| Jason Zucker | L | −0.74 | −0.38 | |
| Rasmus Dahlin | D | −0.53 | −0.46 | DZ giveaway burden still high |
| Ryan McLeod | C | −0.17 | −0.56 | CWD: lost F-pool comparison |
| Bowen Byram | D | −0.61 | −0.57 | |
| Jack Quinn | R | −1.27 | −1.06 | OZ giveaway removal helps |
| Owen Power | D | −1.19 | −1.18 | |
| Noah Ostlund | C | −1.08 | −1.43 | CWD: small-sample C |

## Sabres 25-26 playoffs (R1 only, 4 games)

| Player | Pos | v3 z |
|---|---|---:|
| Beck Malenstyn | L | +2.08 |
| Peyton Krebs | C | +1.39 |
| Conor Timmins | D | +1.15 |
| Jordan Greenway | L | +0.88 |
| Alex Tuch | R | +0.29 |
| Zach Benson | L | +0.28 |
| Mattias Samuelsson | D | +0.13 |
| Josh Doan | R | +0.03 |
| Logan Stanley | D | −0.03 |
| Tage Thompson | C | −0.09 |
| Josh Norris | C | −0.16 |
| Rasmus Dahlin | D | −0.38 |
| Jason Zucker | L | −0.66 |
| Bowen Byram | D | −0.95 |
| Jack Quinn | R | −1.25 |
| Ryan McLeod | C | −1.34 |
| Owen Power | D | −1.36 |
| Noah Ostlund | C | −1.79 |

## Directory structure

```
v3_deliverable/
├── README.md                          (this file)
├── source/
│   └── build_v3.py                    (main builder — produces all CSVs)
├── data/
│   ├── regular_season/                (4 seasons × 3 splits = 12 files)
│   │   ├── 2022/  grit_per_60_v3_2022.csv, grit_5v5_v3_2022.csv, grit_pk_v3_2022.csv
│   │   ├── 2023/  ...
│   │   ├── 2024/  ...
│   │   └── 2025/  ...
│   ├── playoffs/                      (4 seasons × 3 splits = 12 files)
│   │   ├── 2022/  grit_per_60_v3_2022_playoffs.csv, ...
│   │   ├── 2023/  ...
│   │   ├── 2024/  ...
│   │   └── 2025/  (R1 in progress)
│   └── toi/                           (8 TOI files: 4 seasons × RS+playoffs)
├── methodology/
│   └── v3_methodology.md              (full v3 spec)
├── validation/
│   ├── v3_validation_results.json     (structured validation data)
│   └── v3_validation_summary.txt      (human-readable validation tables)
└── findings/
    ├── v2_pk_block_bug.md             (original v2 PK bug discovery)
    └── v2_pk_rules_reverse_engineered.md  (full v2 PK file analysis)
```

## How to regenerate v3 from scratch

You'll need:
1. A play-by-play cache for each season (one JSON per game from `api-web.nhle.com/v1/gamecenter/{gameId}/play-by-play`)
2. TOI splits CSV from `api.nhle.com/stats/rest/en/skater/timeonice` (already in `data/toi/`)

```bash
# Regular season for one year:
python source/build_v3.py \
  --pbp-cache /path/to/pbp_cache_2025 \
  --toi data/toi/toi_2025.csv \
  --output-dir data/regular_season/2025 \
  --season-tag 2025

# Playoffs for one year:
python source/build_v3.py \
  --pbp-cache /path/to/pbp_cache_2025_playoffs \
  --toi data/toi/toi_2025_playoffs.csv \
  --output-dir data/playoffs/2025 \
  --season-tag 2025_playoffs \
  --playoffs
```

## Defensible claims under v3

- "Hits double in the playoffs."
- "Physical penalties (boarding, charging, cross-checking) more than double in playoffs."
- "Fights actually go down by half in playoffs — counter to the intensity narrative."
- "Crease goals don't go up in playoffs. Playoff hockey is harder to score in close, not easier."
- "Aggregate contested-puck event rate is ~60% higher in playoffs, stable across four seasons."
- "v3 trades ~2-3 points of YoY stability for positional fairness — wingers no longer compete against centers in the same pool."

## Things v3 does NOT address

- **Low-TOI rate noise on PK.** The 30-min PK TOI floor allows players with very small samples to surface near the top of rate-based z-scores. Affects v2, v2.1, and v3 equally.
- **Dashboard HTML is version-agnostic.** It renders any uploaded CSV. Works with v3 files as-is.
- **The 1.25× SH multiplier from v2's methodology** is documented but not separately tracked in v3 outputs. Events are counted at face value.

