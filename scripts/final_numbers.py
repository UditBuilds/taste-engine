"""Produce every number the README cites, in one run.

Run:  scripts/run.sh scripts/final_numbers.py
"""
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/c/Users/uditk/Projects/taste-engine/src")

import pandas as pd

from taste_engine import config
from taste_engine.db import connect
from taste_engine.evaluate import (
    evaluate,
    evaluate_rediscovery,
    rediscovery_half_life_sweep,
    rediscovery_robustness,
)

FMT = lambda v: f"{v:.4f}"  # noqa: E731
conn = connect()

print("=" * 74)
print("1. REDISCOVERY half-life sweep  (tuned on the task that matters)")
print("=" * 74)
sweep = rediscovery_half_life_sweep(conn, test_days=config.EVAL_TEST_DAYS)
print(sweep.to_string(index=False, float_format=FMT))
base = sweep["baseline_ndcg"].round(6).nunique()
print(f"\n  CONTROL: baseline nDCG takes {base} distinct value(s) across "
      f"half-lives — must be 1.")

best = sweep.sort_values(["wins", "mean_ndcg"], ascending=False).iloc[0]
hl = float(best["half_life"])
print(f"  Chosen half-life: {hl:.0f}d "
      f"(wins {int(best['wins'])}/{int(best['splits'])}, "
      f"mean nDCG {best['mean_ndcg']:.4f}, worst lift {best['worst_lift']:+.2%})")

print("\n" + "=" * 74)
print(f"2. REDISCOVERY per split @ half-life {hl:.0f}d")
print("=" * 74)
detail, summary = rediscovery_robustness(
    conn, k=20, half_life=hl, test_days=config.EVAL_TEST_DAYS
)
print(detail[["split", "reachable", "most_played_ndcg", "score_ndcg",
              "most_played_recall", "score_recall"]]
      .to_string(index=False, float_format=FMT))
print()
print(summary.to_string(index=False, float_format=FMT))
lift = (summary.set_index("strategy").loc["score", "mean_ndcg@20"]
        / summary.set_index("strategy").loc["most_played", "mean_ndcg@20"] - 1)
print(f"\n  score vs baseline: {lift:+.1%} mean nDCG@20")

print("\n" + "=" * 74)
print(f"3. REDISCOVERY single split {config.EVAL_SPLIT_DATE} @ {hl:.0f}d")
print("=" * 74)
r = evaluate_rediscovery(conn, k=20, half_life=hl, test_days=config.EVAL_TEST_DAYS)
print(f"  candidates {r['candidates']:,} | truth {r['truth']:,} "
      f"(reachable {r['reachable']:,}) | ceiling@20 {r['ceiling']:.1%}")
print(r["results"].to_string(index=False))

print("\n" + "=" * 74)
print("4. REPLAY (the trivial task) — saturation + bounded window")
print("=" * 74)
sat = evaluate(conn, k=20, test_days=None, half_life=hl)
print(f"  precision@20 over the full window — saturated: {sat['saturated']}")
print(sat["results"][["strategy", "hits", "precision@20", "ndcg@20"]]
      .to_string(index=False))
print()
rep = evaluate(conn, k=50, test_days=config.EVAL_TEST_DAYS, half_life=hl)
print(f"  k=50, {config.EVAL_TEST_DAYS}-day window:")
print(rep["results"].to_string(index=False))

conn.close()
print("\nDONE")
