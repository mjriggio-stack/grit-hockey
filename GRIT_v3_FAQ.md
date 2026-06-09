# GRIT v3.1 — Frequently Asked Questions

---

## What changed in v3.1?

v3.1 adds one new component to the v3 metric: **close-range shots, weighted at +1.5**.

A close-range shot is any shot attempt (shot-on-goal, missed-shot, or goal) taken within 12 feet of the net. The spatial test is identical to the one v3 already used for crease goals: `(89 − |x|)² + y² ≤ 144`.

The reasoning: GRIT rewards going to dangerous places. v3 already credited the goals scored from those places (crease goals at +10.0). v3.1 also credits the attempts. A defender who blocks a shot gets credit regardless of whether the shot would have scored; by the same logic, a forward who crashes the net and gets a shot off deserves credit regardless of whether it scores.

The choice to weight close-range shots at +1.5 was deliberate. A heavier +3.0 weight was tested first and produced a metric that tilted too aggressively toward close-range scorers, dropping correlation with v3 to ~0.988. At +1.5, v3.1 ↔ v3 correlation holds at ~0.997. The leaderboard structure is preserved; the change adds one missing dimension without rewriting the metric.

Other v3.1 effects:

- **Mean YoY repeatability** is r = 0.873 (down from v3's 0.876) — within consecutive-pair noise
- **Power-forward archetype** (Tavares, JVR, Kreider, Lee, B. Tkachuk) now properly surfaces in top-30 movers, where v3 understated them
- **Component count** is now 15 (was 14)
- **All other v3 design choices** carry forward unchanged: weights, pooling, spatial definitions, TOI floors, validation framework

---

## Why are close shots a separate event from crease goals when they use the same spatial shape?

Because they measure different things, even though they happen in the same place.

A crease goal is finishing in a dangerous area — the ability to put the puck past the goalie from a spot most shooters can't get to. A close-range shot is the act of getting to that spot at all, regardless of whether you finish.

Splitting them lets GRIT credit both:

- The forward who fights through traffic, gets to the net front, and scores from in tight earns the +10.0 crease-goal weight AND the +1.5 close-shot weight, for a combined +11.5
- The forward who fights through traffic, gets to the same spot, gets a shot off but the goalie makes the save earns the +1.5 close-shot weight only

The first player did more (got there AND scored) and gets more credit. The second player still did the hard part (got there) and gets credit for it. Under v3, the second player got nothing for the same effort. That was the gap v3.1 closes.

Note that the two events use identical filenames (`raw_close_shots` and `raw_crease_goals`) with different prefixes for the same spatial test. This is a cosmetic naming inconsistency that exists because the two events were added at different times. It will be cleaned up in v4 (likely by renaming `raw_close_shots` to `raw_crease_shots`). The current naming is preserved in v3.1 to avoid breaking downstream consumers.

---

## What is EYP (Earning Your Points)?

EYP is an analytical layer built on top of v3.1 GRIT scores. It classifies qualifying forwards into four quadrants based on two axes — GRIT contribution and scoring output — and uses that classification to identify players whose physical contribution is ahead of their offensive production.

The core question EYP asks: among forwards already doing the contested-puck work but not yet scoring, which ones are worth watching? EYP surfaces that population systematically rather than by eye test alone. An important caveat that the analysis forced (see "What is a Blue-to-Green transition?" below): EYP is a screen on the population, not a forecast. A high GRIT score does not predict that a low-scoring forward will start scoring. If anything it is a mild signal the other way.

EYP is not a metric. It's a classification and watchlist system. It doesn't produce a number; it produces a list of names worth paying attention to.

---

## How does the EYP quadrant system work?

Every qualifying forward (minimum 40 GP, positions C/L/R) is placed in one of four quadrants each season:

| | Hi GRIT (grit_z_blend ≥ 0) | Lo GRIT (grit_z_blend < 0) |
|---|---|---|
| **Hi pts (at/above the 41-pt bar)** | GREEN | RED |
| **Lo pts (below the 41-pt bar)** | BLUE | GRAY |

- **GREEN** — high GRIT, high scoring. The target state.
- **RED** — high scoring, low GRIT. Points are coming from somewhere other than contested-puck activity.
- **BLUE** — high GRIT, low scoring. The EYP watchlist quadrant. Doing the work; the production hasn't followed.
- **GRAY** — below the bar on points, below average on GRIT.

The points axis is an absolute bar, not the per-season median. The bar is 41 points (0.5 points per game over 82) for full seasons, pro-rated for shortened seasons (the 71-game 2019-20 season uses 35.5). The median was used originally and was wrong: a median split forces roughly 50/50 above and below every season, which mechanically guarantees symmetric crossing rates and makes "players cross the line" findings partly an artifact of the split. The fixed bar makes "high scoring" a real, stable population (about 40 percent of qualifying forwards) rather than half the field by construction. The GRIT cutoff is zero on the `grit_z_blend` scale, meaning above-average within positional pool.

---

## Who makes the EYP watchlist?

The watchlist is the BLUE quadrant (high GRIT, below the 41-point bar). The published "headline" shortlist narrows that to:

- Age ≤ 27 (end-of-season: `season_year − birth_year`)
- Within 5 points of the bar (`pts_gap ≤ 5`, i.e. 36+ points in a full season)

The age gate is set at 27 based on btog sustain analysis on the absolute bar. Transitions made at age ≤ 27 hold (stay at or above the bar the following season) about 78% of the time, dropping to roughly 54% at 28-30 and 50% at 31-33. Age 27 is the empirically supported upper bound; older transitions are more often role fluctuations than durable changes.

The proximity filter (within 5 points of the bar) is doing real predictive work, but not for the reason the original thesis assumed. A BLUE forward already close to the bar is far likelier to cross it than one 20 points below, and that proximity, together with age, is what actually predicts crossing. GRIT level does not (see below). So the headline list is best read as "young, high-effort forwards who are already close to the scoring bar," not "forwards whose GRIT predicts a breakout."

---

## Who are the 2025-26 EYP headline names?

| Player | Team | Age | Points gap to bar |
|---|---|---:|---:|
| Will Cuylle | NYR | 24 | 3 |
| Vasily Podkolzin | EDM | 25 | 4 |
| Peyton Krebs | BUF | 25 | 2 |
| Jake Neighbours | STL | 24 | 5 |
| Ryan Poehling | ANA | 27 | 5 |
| Eeli Tolvanen | SEA | 27 | 5 |

All six are age 24-27, within 5 points of the 41-point bar in 2025-26, and above zero on GRIT-Z. They are young, high-effort forwards sitting just under the scoring bar. The honest framing is proximity, not prophecy: being a few points short of 41 with a positive GRIT score is what lands them here, and the proximity is what makes a crossing plausible. The GRIT score is the screen that defines the pool, not evidence any one of them will cross.

Peyton Krebs (BUF) is the clean local case: 39 points, two off the bar, exactly the BLUE-near-the-bar profile that crosses most often. Jake Neighbours appears here in both 2023-24 and 2025-26, a genuine persistence signal. Sorting the list by GRIT-Z is misleading given the finding below; gap-to-bar or age is the more honest ordering.

---

## What is a Blue-to-Green transition?

A Blue-to-Green (btog) transition is when a player appears in the BLUE quadrant one season and the GREEN quadrant the next. It was built to test the original EYP thesis: if BLUE players are deployment-limited rather than talent-limited, a meaningful share should graduate to GREEN when their role expands, and GRIT should flag which ones. The test forced a correction to that thesis.

There is one definitional fork, and both counts are reported. The exclusive definition requires literal consecutive years, so the 2020-to-2022 pair does not count (the unobserved 2020-21 COVID season sits between them): 70 transitions across 63 players. The inclusive definition accepts 2020-to-2022 as a player's consecutive qualifying seasons: 79 transitions across 69 players.

**The points jump is real but largely a definitional artifact.** Raw, the increase averages about +17 points and every transition is positive. That is forced by the rule: BLUE is below the bar and GREEN is above it, so a transition is by construction a crossing of the bar from below. Pace-adjusted to per-82, the honest magnitude is about +13 points (exclusive) to +14.5 (inclusive, which runs hotter because the COVID-gap crossings span a short 2020 season into a full 2022).

**The base rate is low and GRIT does not predict who crosses.** Only about 11% of BLUE forwards reach GREEN the next season, and about 13% reach the bar at all (GREEN or RED). BLUE is sticky: the dominant outcome is another BLUE season. Critically, blue-season GRIT does not forecast the jump. Forwards who crossed had *lower* blue-season GRIT-Z than those who stayed (0.67 vs 0.99, p = 0.0012); the logistic odds ratio is about 0.66 per standard deviation. What predicts the jump is proximity to the bar and age, not grit.

**The negative control settles it.** Running the same test on GRAY forwards (low grit, below the bar) is the low-grit mirror. Low-grit below-bar forwards reach the bar at about 28%, more than double the 13% rate for high-grit BLUE forwards. A below-bar forward is roughly twice as likely to start scoring if their grit is *low*, not high. The proximity mechanism is identical in both pools, so the crossing is regression toward the bar, and grit is mildly the wrong direction. This is why EYP is framed as a population screen, not a breakout predictor: GRIT tells you which contested-puck forwards are worth watching, not which ones will score.

**Transitions that happen do tend to hold, more so when young.** Of transitions with a following season, about 68% sustain (stay at or above the bar). That rate is about 78% for transitions made at age ≤ 27 and falls to roughly 54% at 28-30 and 50% at 31-33, which is the basis for the age-27 watchlist gate. The wing-versus-center sustain gap is modest on the absolute bar (wings ~71%, centers ~65%), narrower than earlier median-era estimates suggested.

---

## What are some good examples of EYP Blue-to-Green transitions?

These are illustrations of transitions that happened, chosen with hindsight. Read them as survivorship, not proof the screen forecasts breakouts: for every name here, roughly eight BLUE forwards stayed BLUE, and the low-grit GRAY pool produced crossers at twice the rate. With that caveat:

**Sam Bennett (C, FLA)** crossed BLUE-to-GREEN in 2023-24 on the absolute bar, his scoring finally clearing 41 in Florida. He had logged high-GRIT, below-bar seasons before that. The role and finishing arrived together; the GRIT was present throughout but did not signal the timing.

**Lawson Crouse (L, UTA)** is a two-time crosser on the bar (2022-23 and again 2025-26), a forward who oscillates around the 41-point line rather than clearing it once and holding, which is itself typical of how noisy these crossings are.

**Tom Wilson (R, WSH)** crossed in 2019-20 and again in 2024-25, the latter a strong scoring year in Washington. One of the higher-GRIT forwards in the dataset, but his crossings track role and health, not a GRIT signal that led the production.

**Joel Eriksson Ek (C, MIN)** crossed in 2025-26. A center whose GRIT is driven by hits and physical engagement rather than faceoffs alone, which makes his contested-puck profile more durable than a faceoff-dependent center's, though that durability is about GRIT persistence, not scoring prediction.

**Josh Doan** is the instructive counter-case. He did not cross BLUE-to-GREEN at all. In 2024-25 he was GRAY (below the bar AND below-average GRIT, GRIT-Z −0.40, 19 points), then jumped to GREEN in 2025-26 with 52 points. His breakout came from the *low-grit* side of the board, not the watchlist quadrant. That is exactly the pattern the negative control predicts: below-bar forwards who break out are more often low-grit than high-grit. Doan is a useful reminder that GRIT did not flag the player who actually popped.

**Josh Anderson (R, MTL)** is the cautionary counterpoint. He crossed BLUE-to-GREEN in 2018-19, then fell back to BLUE and has stayed there for five consecutive seasons. The role expansion that produced the GREEN year was temporary. He is why "sustained" is tracked alongside the transition, and why a single crossing is weak evidence about a player.

---

## What is GRIT?

GRIT (Gritty Role Impact Total) is a hockey analytics metric that measures **contested-puck contribution** — a count of the events that happen when a player is physically competing for or against a puck in a contested area of the ice.

It is position-adjusted, rate-normalized, and validated across nine NHL seasons (2015-16 through 2025-26, with the 2020-21 COVID season intentionally excluded).

---

## What does GRIT actually count?

GRIT counts 15 distinct event types, each weighted by its leverage and repeatability. Every event in the model is either a puck contest won, a puck contest lost, or a physical act directly tied to competing for the puck.

| Event | Weight | Why it counts |
|---|---:|---|
| Crease-area goals | +10.0 | Scoring from the doorstep requires winning a physical battle in the most contested real estate on the ice — through traffic, against a defender, in a crowd |
| Penalties drawn | +5.5 | Drawing a penalty means a defender was forced to foul you to stop your play — you won the puck contest badly enough that they had no legal way to stop you |
| Physical minors taken | +5.5 | Taking a physical penalty means you were contesting hard enough that you fouled someone in the act — aggressive physical engagement that crossed a line |
| HD blocked shots | +4.0 | Putting your body in the shooting lane in the slot — the most dangerous area of the ice — is the most direct form of puck contestation in the defensive zone |
| Fighting majors | +3.5 | The most direct form of physical contestation in the sport — weighted mid-tier because it occurs outside of live puck play |
| HD takeaways | +3.5 | Stripping the puck in the slot or near the net — high-danger zone contestation where the outcome matters most |
| Hits thrown | +3.0 | A hit is a direct attempt to separate a player from the puck or prevent them from reaching it — every hit is a puck contest |
| Non-HD blocked shots | +3.0 | Same act as HD blocks, lower-leverage zone — still a direct puck contest won |
| DZ faceoff wins | +2.0 | A faceoff is a structured one-on-one puck contest — winning it in your own zone is the highest-leverage faceoff outcome defensively |
| Other takeaways | +2.0 | Same act as HD takeaways, lower-leverage zone — still a direct puck contest won |
| **Close-range shots** | **+1.5** | **Any shot from within 12 feet of the net — captures effort and exposure to dangerous areas regardless of finishing ability (NEW in v3.1)** |
| Hits taken | +1.5 | Absorbing a hit to maintain possession or protect the puck — you're being contested and staying in the play anyway |
| OZ giveaways | 0.0 | Not penalized — an OZ giveaway often reflects attempting a high-danger play, the same activity GRIT rewards on the positive side. Penalizing it would contradict the metric's own logic |
| NZ giveaways | −1.5 | A failed puck contest in the neutral zone — puck-management failure where the cost is meaningful |
| DZ giveaways | −2.5 | A failed puck contest in your own end — the highest-cost zone for puck loss |

---

## Why are only certain physical penalties included?

GRIT includes only the six penalties that represent direct physical engagement with another player: **roughing, charging, boarding, cross-checking, elbowing, and interference.**

Slashing, high-sticking, tripping, hooking, and holding are excluded. These are stickwork or skating-deficit penalties — they reflect competitive play but not contested-puck physical engagement in the sense GRIT measures.

---

## Why are blocked shots split into HD and non-HD?

Location matters. A block in the slot (high-danger zone) means the shooter had a dangerous look and you put your body in front of it — that's a higher-leverage act than blocking a shot from the point. GRIT uses the same slot rectangle definition for both HD blocks and HD takeaways: `|x| ≥ 70` AND `|y| ≤ 18` in NHL coordinate space (approximately 19 feet deep, 36 feet wide).

HD blocks are weighted +4.0; non-HD blocks +3.0.

---

## Why are crease goals weighted the highest?

Crease-area goals require a player to win a physical contest in the most contested real estate on the ice. You're not shooting from distance — you're going to the net through traffic, winning position against a defender, and converting in a crowd with a goalie directly in front of you. That's the GRIT thesis in its purest form: competing in hard areas and producing results.

A goal qualifies as a crease goal if it was scored within 12 feet of the net (Euclidean distance), which captures tipped pucks, rebounds, and net-front jams while excluding wraparounds and bad-angle shots from below the goal line.

---

## Isn't this just a stat for grinders and fourth-liners?

No, and this is the most common misconception about GRIT.

The metric doesn't know what line a player is on, what their body size is, or what their reputation is. It counts events. Some examples from the 2025-26 leaderboard:

- **Vincent Trocheck** (NYR) — 60+ point second-line center, top-15 among all NHL centers in GRIT. His reputation as a finesse player undersells the 193 hits and 18 penalties drawn his event log shows.
- **Ryan Hartman** (MIN) — top-line scorer with 15 crease goals and 29 penalties drawn. Top-25 among NHL wings despite throwing fewer hits than almost everyone else on that list. His contested-puck contribution comes from net-front scoring and drawing penalties, not physical aggression.
- **Peyton Krebs** (BUF) — 184 lb versatile forward deployed across all four lines. Top-25 among NHL centers despite small stature. Throws hits, draws penalties, goes to the net, wins faceoffs.

The grinder archetype tends to score well on GRIT because grinders by definition go to hard areas and produce these events. But the metric is designed around the events, not the archetype. When it surfaces Trocheck or Hartman or Krebs, that's not a bug — it's the metric working correctly.

---

## Isn't this just measuring players who play the same way to keep a roster spot?

This is the strongest version of the skeptic's argument and deserves a direct answer: the stability data says no.

If GRIT were measuring survival behavior — players repeating the same role to keep their job — you'd expect high turnover in the leaderboard as roster compositions change. What the data actually shows:

| Window | Correlation (r) | n pairs |
|---|---:|---:|
| Year-over-year (consecutive seasons) | 0.873 | 8 |
| 2-year gap | 0.821 | 6 |
| 3-year gap | 0.783 | 4 |
| 4-year gap | 0.777 | 2 |
| 6-year long-horizon (2019-20 → 2025-26)* | ~0.75 | 1 |

*The 6-year horizon spans the excluded 2020-21 COVID season, so it's a long-window spot check rather than part of the consecutive-pair series.

For context: Corsi/Fenwick year-over-year repeatability is approximately 0.60–0.70. Points per 60 is approximately 0.50–0.60. GRIT at 0.873 year-over-year — and still around 0.75 across a six-year span — is more stable than either of those benchmarks.

That's not roster churn. That's a durable, repeatable individual characteristic of how players play the game.

---

## Does GRIT predict winning?

No, and it doesn't try to. GRIT measures **individual contested-puck contribution**, not team quality or winning probability.

A team with high aggregate GRIT is a team that goes to hard areas, blocks shots, throws hits, and draws penalties. Whether that translates to wins depends on goaltending, skill, systems, and a dozen other factors GRIT doesn't capture.

Team-level GRIT is a descriptor of **style**, not a predictor of success. A skilled team that avoids physical play can outscore a high-GRIT team. Ottawa finishing first in team GRIT in 2025-26 and losing in the first round doesn't invalidate the metric — it reflects that GRIT measures one dimension of the game, not all of them.

---

## How is GRIT normalized?

GRIT uses a 70/30 blend of rate and volume:

- **Rate (70%):** weighted events per 60 minutes of ice time — controls for deployment and TOI differences
- **Volume (30%):** weighted events per game — partially rewards durability and availability

Both are z-scored within positional pools (C, W, D separately) before blending. The final `grit_z_blend` score represents how many standard deviations above or below average a player is within their position group.

---

## Why are centers, wings, and defensemen scored separately?

A winger structurally cannot win a defensive-zone faceoff. If wings and centers compete in the same pool, wings are systematically penalized for not doing something they're never asked to do — the comparison isn't fair.

GRIT v3.1 uses C/W/D pooling so that each player is compared only against others who can plausibly produce the same set of events. A center's GRIT-Z reflects where they rank among centers. A winger's reflects where they rank among wings.

---

## What does GRIT not measure?

GRIT is intentionally scoped to events trackable in the NHL play-by-play feed. It does not measure:

- **Zone entry or exit success** — not a discrete NHL event
- **Board battle outcomes** — the hit is tracked but winning possession after it isn't
- **Loose puck recoveries** — not directly tagged in PBP (some are captured indirectly as takeaways, but inconsistently)
- **Net-front battles without a shot** — not tracked
- **Sustained possession or cycle play** — not a discrete event
- **Goaltending, skill, or offensive production** — intentionally out of scope
- **Team quality or winning** — see above

The NHL API captures the outcomes of puck contests well. What it misses is the process — the battles that don't leave a traceable footprint. Player tracking data would fill some of these gaps; that data is not publicly available.

---

## How does GRIT compare to existing metrics?

GRIT is not designed to replace existing metrics — it measures a different dimension of the game. The closest public comparisons:

- **Hits and blocks (raw counts):** GRIT incorporates these but weights them by leverage, combines them with other events, and normalizes by ice time. Raw hit counts don't distinguish between a hit in the slot and a hit along the boards in the defensive zone.
- **Corsi/Fenwick:** Measures shot attempt share — a proxy for puck possession and zone time. Year-over-year repeatability ~0.60–0.70. GRIT repeatability ~0.873 across consecutive seasons. Different dimensions.
- **Points per 60:** Measures offensive production. Year-over-year repeatability ~0.50–0.60. Not a close comparison — GRIT and scoring are largely orthogonal (though some top scorers rank highly on GRIT too, via crease goals and penalties drawn).
- **WAR-based metrics (Evolving Hockey, MoneyPuck):** Comprehensive value metrics that attempt to capture total player contribution. GRIT is narrower by design — it measures one specific dimension (contested-puck contribution) rather than total value.

---

## Where does the data come from?

All data is sourced from the NHL's public API:

- **Play-by-play:** `api-web.nhle.com/v1/gamecenter/{gameId}/play-by-play` — every event in every game with x/y coordinates
- **Time on ice:** `api.nhle.com/stats/rest/en/skater/timeonice` — season-level EV/PP/SH TOI splits for all skaters

The scraper (`scrape_v3.py`) and builder (`build_v3.py`) are both open source in this repository. GRIT is fully reproducible from raw API data.

---

## How many seasons does GRIT cover?

GRIT v3.1 currently covers ten regular seasons (one of which — 2020-21 — is excluded from the career aggregate per the COVID exception below):

| Season | Notes |
|---|---|
| 2015-16 | Full 82-game season |
| 2016-17 | Full 82-game season |
| 2017-18 | Full 82-game season |
| 2018-19 | Full 82-game season |
| 2019-20 | COVID-paused March 12 — 71 games for most teams |
| 2020-21 | COVID bubble (56 games) — **excluded** from the project per shortened-format/abnormal-conditions exception |
| 2021-22 | Full 82-game season |
| 2022-23 | Full 82-game season |
| 2023-24 | Full 82-game season |
| 2024-25 | Full 82-game season |
| 2025-26 | Full 82-game season |

Nine of these (every season except 2020-21) carry data. Year-over-year correlation pairs that would bridge the COVID gap are also excluded from the validation summary.

Playoff GRIT is computed separately for every season above except 2019-20 (which had a COVID-altered playoff format) and 2020-21 (excluded above).

---

## Can I use this data?

Yes. All data and code in this repository are provided for open use. If you publish analysis using GRIT, attribution to this repository is required.

If you find errors, have methodological questions, or want to discuss the metric, open an issue on GitHub.
