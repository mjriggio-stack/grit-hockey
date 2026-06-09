"""eyp_common.py — single source of truth for EYP classification.

Everything that DEFINES an EYP quadrant lives here so the per-season builder
(build_eyp.py) and the career builder (build_eyp_career.py) cannot drift.
Before this module existed, both files carried their own copies of the
threshold constants and assign_quadrant(); a points-bar change had to be made
in two places and kept in sync by comment. That is exactly how the 41-point
bar ended up in the docs but not the code. Import from here instead.

Eligibility / axis definitions:
  GP_FLOOR           — minimum games played to qualify as an EYP forward
  FORWARD_POSITIONS  — EYP scope (centers + wings)
  GRIT_CUTOFF        — grit_z_blend >= this is "high grit" (the vertical split)

Points axis (the horizontal split) is an ABSOLUTE bar, not a per-season median:
  FULL_SEASON_THRESHOLD        — 41 pts (0.5 pts/game over 82)
  SHORTENED_SEASON_THRESHOLDS  — per-season overrides for short schedules.
      2019-20 (tag '2020') was suspended at ~71 games → 0.5 * 71 = 35.5.
      (2020-21 is excluded from the EYP season set entirely, so it has no entry.)

To change the bar, edit it HERE and rerun both builders. One edit, no drift.
"""

import pandas as pd


GP_FLOOR          = 40
FORWARD_POSITIONS = ["C", "L", "R"]
GRIT_CUTOFF       = 0.0

FULL_SEASON_THRESHOLD       = 41.0
SHORTENED_SEASON_THRESHOLDS = {"2020": 35.5}


def season_points_threshold(season_tag) -> float:
    """Absolute points bar for a season: 41 for full seasons, pro-rated
    (0.5 * games) for shortened seasons."""
    return SHORTENED_SEASON_THRESHOLDS.get(str(season_tag), FULL_SEASON_THRESHOLD)


def assign_quadrant(grit_z: float, pts: float, pts_threshold: float):
    """Classify a forward into one of the four EYP quadrants.

      RED  (lo grit, hi pts) | GREEN (hi grit, hi pts)   <- pts >= pts_threshold
      ---------------------- + ------------------------
      GRAY (lo grit, lo pts) | BLUE  (hi grit, lo pts)   <- pts <  pts_threshold
                             ^ grit_z >= GRIT_CUTOFF

    Returns None if grit_z or pts is missing.
    """
    if pd.isna(grit_z) or pd.isna(pts):
        return None
    high_grit = grit_z >= GRIT_CUTOFF
    high_pts  = pts >= pts_threshold
    if high_grit and high_pts:     return "GREEN"
    if high_grit and not high_pts:  return "BLUE"
    if not high_grit and high_pts:  return "RED"
    return "GRAY"
