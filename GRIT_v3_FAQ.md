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
