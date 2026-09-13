"""Is the strict filter's null result real, or did the filter never arrive?

`STRICT_MUSIC` removes 202 songs yet the headline is identical to four
decimals. That is equally consistent with two very different stories:

  (a) the filter never reached the evaluated set, so the null means nothing;
  (b) the filter reached it, and the contamination sits below top-k.

Only (b) is a finding. This distinguishes them by checking the candidate pool
actually shrinks at every split before accepting the null.

Run:  scripts/run.sh scripts/verify_strict_null.py
"""
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/c/Users/uditk/Projects/taste-engine/src")

import pandas as pd

from taste_engine import classify as classify_mod
from taste_engine import config
from taste_engine.db import connect
from taste_engine.evaluate import rediscovery_split
from taste_engine.recommend import recommend
from taste_engine.score import scored_tracks

SPLITS = ["2026-06-01", "2026-07-01", "2026-08-01"]   # the held-out ones
K = 20


def with_strict(flag):
    config.STRICT_MUSIC = flag
    classify_mod._CACHE.clear()


conn = connect()

print("=" * 78)
print("CHECK 1 — does the filter remove anything at all?")
print("=" * 78)
with_strict(False)
loose = scored_tracks(conn)
with_strict(True)
strict = scored_tracks(conn)
removed = set(loose["video_id"]) - set(strict["video_id"])
print(f"  canonical songs, union   {len(loose):>6,}")
print(f"  canonical songs, strict  {len(strict):>6,}")
print(f"  removed                  {len(removed):>6,}  "
      f"({len(removed) / len(loose):.1%})")
plays_removed = loose[loose.video_id.isin(removed)]["play_count"]
print(f"  plays removed            {int(plays_removed.sum()):>6,}  "
      f"(mean {plays_removed.mean():.1f} plays per removed song)")
check1 = len(removed) > 0
print(f"  => {'PASS' if check1 else 'FAIL'}: the filter removes songs")

print("\n" + "=" * 78)
print("CHECK 2 — does the EVALUATED pool shrink at every split?")
print("=" * 78)
print("  If these are identical, the filter is not on the eval path and any")
print("  null result is meaningless.\n")
rows = []
for split in SPLITS:
    per = {}
    for flag in (False, True):
        with_strict(flag)
        cands, truth, _ = rediscovery_split(
            conn, split, config.RECENCY_HALF_LIFE_DAYS, config.EXCLUDE_TOP,
            config.EVAL_TEST_DAYS, cluster=False,
        )
        per[flag] = (cands, truth)
    lc, lt = per[False]
    sc, st = per[True]
    rows.append({
        "split": split,
        "cands_union": len(lc), "cands_strict": len(sc),
        "cands_delta": len(sc) - len(lc),
        "truth_union": len(lt), "truth_strict": len(st),
        "truth_delta": len(st) - len(lt),
    })
pool = pd.DataFrame(rows)
print(pool.to_string(index=False))
check2 = bool((pool.cands_delta < 0).all())
print(f"\n  => {'PASS' if check2 else 'FAIL'}: the pool shrinks at "
      f"{int((pool.cands_delta < 0).sum())}/{len(pool)} splits")

print("\n" + "=" * 78)
print("CHECK 3 — where in the ranking does the removed material sit?")
print("=" * 78)
rows = []
for split in SPLITS:
    with_strict(True)
    strict_cands, strict_truth, _ = rediscovery_split(
        conn, split, config.RECENCY_HALF_LIFE_DAYS, config.EXCLUDE_TOP,
        config.EVAL_TEST_DAYS, cluster=False,
    )
    strict_ids = set(strict_cands["video_id"])
    with_strict(False)
    cands, truth, _ = rediscovery_split(
        conn, split, config.RECENCY_HALF_LIFE_DAYS, config.EXCLUDE_TOP,
        config.EVAL_TEST_DAYS, cluster=False,
    )
    ranked = recommend(cands, n=len(cands), strategy="score")["video_id"].tolist()
    gone = [i for i, v in enumerate(ranked) if v not in strict_ids]
    reachable_gone = (set(truth["video_id"]) & set(cands["video_id"])) - strict_ids
    rows.append({
        "split": split,
        "removed_in_pool": len(gone),
        f"in_top_{K}": sum(1 for i in gone if i < K),
        "in_top_100": sum(1 for i in gone if i < 100),
        "best_rank": (min(gone) + 1) if gone else None,
        "in_reachable_truth": len(reachable_gone),
    })
rank = pd.DataFrame(rows)
print(rank.to_string(index=False))
check3 = bool((rank[f"in_top_{K}"] == 0).all())
print(f"\n  => removed songs never enter the top {K}: "
      f"{'yes' if check3 else 'NO'}")
print(f"     best rank any removed song achieves: "
      f"{rank.best_rank.min()} of ~2,000+")

print("\n" + "=" * 78)
print("VERDICT")
print("=" * 78)
if check1 and check2 and check3:
    print("  The filter reaches the evaluated set (pool shrinks 123-163 songs")
    print("  per split) and the metric still does not move. The contamination")
    print("  is real but sits in the tail, far below top-k, so it never enters")
    print("  a 20-item recommendation. The null is a finding, not an artefact.")
elif check1 and not check2:
    print("  The filter does NOT reach the evaluated pool. The null result is")
    print("  meaningless - fix the plumbing before drawing any conclusion.")
else:
    print("  Mixed result; read the checks above individually.")

with_strict(False)
conn.close()
