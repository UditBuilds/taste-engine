"""Nested hold-out: tune the half-life on early splits, report on later ones.

Run:  scripts/run.sh scripts/nested_eval.py
"""
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/c/Users/uditk/Projects/taste-engine/src")

from taste_engine.db import connect
from taste_engine.evaluate import nested_rediscovery

FMT = lambda v: f"{v:.4f}"  # noqa: E731

conn = connect()
out = nested_rediscovery(conn)
conn.close()

if out["status"] != "ok":
    print("could not run:", out)
    raise SystemExit(1)

print("=" * 74)
print("USABLE SPLITS (reachable truth >= 20, fixed half-life, chosen once)")
print("=" * 74)
for u in out["usable_splits"]:
    where = "dev" if u["split"] in out["dev_splits"] else "HELD OUT"
    print(f"  {u['split']}  reachable {u['reachable']:>4}   [{where}]")

print("\n" + "=" * 74)
print(f"SELECTION — on the {len(out['dev_splits'])} dev splits only")
print("=" * 74)
print(out["dev_table"].to_string(index=False, float_format=FMT))
print(f"\n  chosen half-life: {out['chosen_half_life']:.0f} days")

print("\n" + "=" * 74)
print(f"REPORT — on {out['n']} held-out splits the selection never saw")
print("=" * 74)
print(out["held_out"].to_string(index=False, float_format=FMT))
print()
print(f"  mean baseline nDCG@20 : {out['mean_baseline']:.4f}")
print(f"  mean score    nDCG@20 : {out['mean_score']:.4f}")
print(f"  lift                  : {out['lift']:+.1%}")
print(f"  splits won            : {out['wins']}/{out['n']}")
print(f"  sign-test p           : {out['sign_test_p']:.3f}")
print()
if out["significant"]:
    print("  VERDICT: improvement over the most-played baseline, p < 0.05.")
else:
    print("  VERDICT: no significant improvement over the most-played baseline.")
    print(f"           {out['lift']:+.1%} on {out['n']} held-out splits is not")
    print("           distinguishable from chance at this sample size.")
