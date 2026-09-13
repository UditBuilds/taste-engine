"""Does collapsing duplicate uploads change the result? Old vs new, both tasks.

Run:  scripts/run.sh scripts/canonical_impact.py
"""
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/c/Users/uditk/Projects/taste-engine/src")

import pandas as pd

from taste_engine import config
from taste_engine.canonical import collapse_report
from taste_engine.db import connect
from taste_engine.evaluate import (
    evaluate,
    evaluate_rediscovery,
    nested_rediscovery,
)
from taste_engine.score import scored_tracks

FMT = lambda v: f"{v:.4f}"  # noqa: E731
conn = connect()

print("=" * 76)
print("1. HOW MUCH COLLAPSES")
print("=" * 76)
rep = collapse_report(scored_tracks(conn, canonical=False))
print(f"  tracks by video id   {rep['rows_in']:>7,}")
print(f"  canonical songs      {rep['rows_out']:>7,}")
print(f"  collapsed            {rep['collapsed']:>7,}  "
      f"({rep['collapsed'] / rep['rows_in']:.1%})")
print(f"  songs with >1 upload {rep['groups_with_duplicates']:>7,}")
print(f"  largest group        {rep['largest_group']:>7}  "
      f"({rep['largest_group_key']})")

print("\n" + "=" * 76)
print("2. DID FAVOURITES LEAK PAST THE TOP-50 HOLD-OUT?")
print("=" * 76)
print("  A song whose plays split across uploads can sit below the cutoff on")
print("  every one of them, surviving into the candidate pool it should have")
print("  been removed from.\n")
rows = []
for split in ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01"]:
    from taste_engine.evaluate import rediscovery_split

    raw_c, _, raw_ex = rediscovery_split(conn, split, 14, 50, 30, cluster=False,
                                         canonical=False)
    can_c, _, can_ex = rediscovery_split(conn, split, 14, 50, 30, cluster=False,
                                         canonical=True)
    # Plays held out, as a share of all plays in the training window.
    raw_share = raw_c["play_count"].sum()
    can_share = can_c["play_count"].sum()
    rows.append({
        "split": split,
        "raw_candidate_plays": int(raw_share),
        "canon_candidate_plays": int(can_share),
        "raw_top_candidate": int(raw_c["play_count"].max()),
        "canon_top_candidate": int(can_c["play_count"].max()),
    })
leak = pd.DataFrame(rows)
print(leak.to_string(index=False))
print("\n  `top_candidate` is the most-played track that survived the hold-out.")
print("  Higher under `raw` means a bigger favourite leaked through.")

print("\n" + "=" * 76)
print("3. REDISCOVERY, per split, raw vs canonical (half-life 14, k=20)")
print("=" * 76)
rows = []
for split in ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01"]:
    rec = {"split": split}
    for label, canon in (("raw", False), ("canon", True)):
        try:
            r = evaluate_rediscovery(
                conn, split, 20, 14, strategies=["most_played", "score"],
                test_days=config.EVAL_TEST_DAYS, canonical=canon,
            )["results"].set_index("strategy")
            rec[f"{label}_base"] = r.loc["most_played", "ndcg@20"]
            rec[f"{label}_score"] = r.loc["score", "ndcg@20"]
        except ValueError:
            rec[f"{label}_base"] = rec[f"{label}_score"] = float("nan")
    rows.append(rec)
table = pd.DataFrame(rows)
table["raw_lift"] = (table.raw_score - table.raw_base) / table.raw_base
table["canon_lift"] = (table.canon_score - table.canon_base) / table.canon_base
print(table.to_string(index=False, float_format=FMT))

print("\n" + "=" * 76)
print("4. REPLAY, raw vs canonical (k=50, 30-day window)")
print("=" * 76)
for label, canon in (("raw", False), ("canonical", True)):
    r = evaluate(conn, k=50, test_days=30, half_life=14, canonical=canon)
    res = r["results"].set_index("strategy")
    print(f"  {label:<10} tracks {r['train_tracks']:>5,}  "
          f"score nDCG {res.loc['score', 'ndcg@50']:.4f}  "
          f"baseline {res.loc['most_played', 'ndcg@50']:.4f}  "
          f"spearman {res.loc['score', 'spearman']:.3f} vs "
          f"{res.loc['most_played', 'spearman']:.3f}")

print("\n" + "=" * 76)
print("5. NESTED HOLD-OUT ON CANONICAL TRACKS  (the headline)")
print("=" * 76)
out = nested_rediscovery(conn, canonical=True)
if out["status"] != "ok":
    print("  could not run:", out)
else:
    print(f"  dev splits      {out['dev_splits']}")
    print(f"  held-out splits {out['held_out_splits']}")
    print(f"  chosen half-life {out['chosen_half_life']:.0f}d")
    print()
    print(out["held_out"].to_string(index=False, float_format=FMT))
    print()
    print(f"  mean baseline {out['mean_baseline']:.4f}")
    print(f"  mean score    {out['mean_score']:.4f}")
    print(f"  lift          {out['lift']:+.1%}")
    print(f"  wins          {out['wins']}/{out['n']}")
    print(f"  sign-test p   {out['sign_test_p']:.3f}")
    print()
    print("  VERDICT:", "significant improvement" if out["significant"]
          else "no significant improvement over the most-played baseline")

conn.close()
print("\nDONE")
