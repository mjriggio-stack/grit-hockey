# GRIT v3 — Frequently Asked Questions

---

## What is GRIT?

GRIT (Gritty Role Impact Total) is a hockey analytics metric that measures **contested-puck contribution** — a count of the events that happen when a player is physically competing for or against a puck in a contested area of the ice.

It is position-adjusted, rate-normalized, and validated across six NHL seasons (2019-20 through 2025-26).

---

## What does GRIT actually count?

GRIT counts 14 distinct event types, each weighted by its leverage and repeatability. Every event in the model is either a puck contest won, a puck contest lost, or a physical act directly tied to competing for the puck.

| Event | Weight | Why it counts |
|---|---:|---|
| Crease-area goals | +10.0 | Scoring from the doorstep requires winning a physical battle in the most contested real estate on the ice — through traffic, against a defender, in a crowd |
| Penalties drawn | +5.5 | Drawing a penalty means a defender was forced to foul you to stop your play — you won the puck contest badly enough that they had no legal way to stop you |
| Physical minors taken | +5.5 | Taking a physical penalty means you were contesting hard enough that you fouled someone in the act — aggressive physical engagement that crossed a line |
| HD blocked shots | +4.0 | Putting your body in the shooting lane in the slot — the most dangerous area of the ice — is the most direct form of puck contestation in the defensive zone |
| HD takeaways | +3.5 | Stripping the puck in the slot or near the net — high-danger zone contestation where the outcome matters most |
| Non-HD blocked shots | +3.0 | Same act as HD blocks, lower-leverage zone — still a direct puck contest won |
| Hits thrown | +3.0 | A hit is a direct attempt to separate a player from the puck or prevent them from reaching it — every hit is a puck contest |
| DZ faceoff wins | +2.0 | A faceoff is a structured one-on-one puck contest — winning it in your own zone is the highest-leverage faceoff outcome defensively |
| Other takeaways | +2.0 | Same act as HD takeaways, lower-leverage zone — still a direct puck contest won |
| Hits taken | +1.5 | Absorbing a hit to maintain possession or protect the puck — you're being contested and staying in the play anyway |
| Fighting majors | +3.5 | The most direct form of physical contestation in the sport — weighted mid-tier because it occurs outside of live puck play |
| NZ giveaways | −1.5 | A failed puck contest in the neutral zone — puck-management failure where the cost is meaningful |
| DZ giveaways | −2.5 | A failed puck contest in your own end — the highest-cost zone for puck loss |
| OZ giveaways | 0.0 | Not penalized — an OZ giveaway often reflects attempting a high-danger play, the same activity GRIT rewards on the positive side. Penalizing it would contradict the metric's own logic |

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

No — and this is the most common misconception about GRIT.

The metric doesn't know what line a player is on, what their body size is, or what their reputation is. It counts events. Some examples from the 2025-26 leaderboard:

- **Vincent Trocheck** (NYR) — 60+ point second-line center, top-15 among all NHL centers in GRIT. His reputation as a finesse player undersells the 193 hits and 18 penalties drawn his event log shows.
- **Ryan Hartman** (MIN) — top-line scorer with 15 crease goals and 29 penalties drawn. Top-25 among NHL wings despite throwing fewer hits than almost everyone else on that list. His contested-puck contribution comes from net-front scoring and drawing penalties, not physical aggression.
- **Peyton Krebs** (BUF) — 184 lb versatile forward deployed across all four lines. Top-25 among NHL centers despite small stature. Throws hits, draws penalties, goes to the net, wins faceoffs.

The grinder archetype tends to score well on GRIT — because grinders by definition go to hard areas and produce these events. But the metric is designed around the events, not the archetype. When it surfaces Trocheck or Hartman or Krebs, that's not a bug — it's the metric working correctly.

---

## Isn't this just measuring players who play the same way to keep a roster spot?

This is the strongest version of the skeptic's argument and deserves a direct answer: the stability data says no.

If GRIT were measuring survival behavior — players repeating the same role to keep their job — you'd expect high turnover in the leaderboard as roster compositions change. What the data actually shows:

| Window | Correlation (r) |
|---|---:|
| Year-over-year (avg across 5 pairs) | 0.86 |
| 2-year gap | 0.87 |
| 3-year gap | 0.75 |
| 4-year gap | 0.77 |
| 6-year gap (2019-20 → 2025-26) | 0.75 |

For context: Corsi/Fenwick year-over-year repeatability is approximately 0.60–0.70. Points per 60 is approximately 0.50–0.60. GRIT at 0.86 year-over-year — and 0.75 across six seasons — is more stable than either of those benchmarks.

That's not roster churn. That's a durable, repeatable individual characteristic of how players play the game.

---

## Does GRIT predict winning?

No — and it doesn't try to. GRIT measures **individual contested-puck contribution**, not team quality or winning probability.

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

GRIT v3 uses C/W/D pooling so that each player is compared only against others who can plausibly produce the same set of events. A center's GRIT-Z reflects where they rank among centers. A winger's reflects where they rank among wings.

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
- **Corsi/Fenwick:** Measures shot attempt share — a proxy for puck possession and zone time. Year-over-year repeatability ~0.60–0.70. GRIT repeatability ~0.86. Different dimensions.
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

GRIT v3 currently covers six seasons:

| Season | Notes |
|---|---|
| 2019-20 | COVID-paused March 12 — 71 games for most teams |
| 2021-22 | Full 82-game season |
| 2022-23 | Full 82-game season |
| 2023-24 | Full 82-game season |
| 2024-25 | Full 82-game season |
| 2025-26 | Full 82-game season |

The 2020-21 season (COVID bubble, 56 games) is intentionally excluded from the career aggregate due to its shortened format and abnormal competitive conditions.

---

## Can I use this data?

Yes. All data and code in this repository are provided for open use. If you publish analysis using GRIT, attribution to this repository is required.

If you find errors, have methodological questions, or want to discuss the metric, open an issue on GitHub.
