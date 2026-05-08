"""
diff_close_shots.py -- compare raw_close_shots counts between a v3.1 build
output and the close_shot_test_{tag}.csv reference for that season.

Usage:
    python diff_close_shots.py <new_csv> <ref_csv>

Example (PowerShell):
    python diff_close_shots.py `
        "C:/Users/mjrig/OneDrive/Documents/Grit/Version 3/data/2025_playoffs_v31_test/grit_per_60_v3_2025_playoffs.csv" `
        "C:/Users/mjrig/OneDrive/Documents/Grit/Version 3/close_shot_test_2025_playoffs.csv"

Counts are weight-independent so they should match exactly even though the
reference CSVs were generated at +3.0 and v3.1 uses +1.5.
"""

import sys
import pandas as pd


def main():
    if len(sys.argv) != 3:
        print("Usage: python diff_close_shots.py <new_csv> <ref_csv>")
        sys.exit(1)

    new_path = sys.argv[1]
    ref_path = sys.argv[2]

    print(f"New: {new_path}")
    print(f"Ref: {ref_path}")
    print()

    new = pd.read_csv(new_path)[["player_id", "name", "raw_close_shots"]]
    ref = pd.read_csv(ref_path)[["player_id", "raw_close_shots"]].rename(
        columns={"raw_close_shots": "ref_close_shots"}
    )

    m = new.merge(ref, on="player_id", how="outer", indicator=True)

    n_total = len(m)
    n_both = (m["_merge"] == "both").sum()
    n_left = (m["_merge"] == "left_only").sum()
    n_right = (m["_merge"] == "right_only").sum()

    print(f"Total joined: {n_total}")
    print(f"Both:         {n_both}")
    print(f"Only new:     {n_left}")
    print(f"Only ref:     {n_right}")

    both = m[m["_merge"] == "both"].copy()
    mismatch = both[both["raw_close_shots"] != both["ref_close_shots"]]

    print(f"Mismatches:   {len(mismatch)}")
    if len(mismatch):
        print()
        print(mismatch[["player_id", "name", "raw_close_shots", "ref_close_shots"]]
              .head(20).to_string(index=False))
    else:
        print("All counts match.")


if __name__ == "__main__":
    main()
