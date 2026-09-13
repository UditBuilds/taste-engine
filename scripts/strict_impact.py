"""What would the tighter music rule cost, and what would it buy?

`config.STRICT_MUSIC` drops songs admitted by `categoryId` alone that do not
look like songs (too long, too short, or a tutorial/vlog/interview title).
It is OFF by default. This measures it so the decision is informed rather
than assumed.

Run:  scripts/run.sh scripts/strict_impact.py
"""
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/c/Users/uditk/Projects/taste-engine/src")

import pandas as pd

from taste_engine import classify as classify_mod
from taste_engine import config
from taste_engine.db import connect
from taste_engine.evaluate import nested_rediscovery
from taste_engine.score import scored_tracks

FMT = lambda v: f"{v:.4f}"  # noqa: E731
conn = connect()


def with_strict(flag):
    config.STRICT_MUSIC = flag
    classify_mod._CACHE.clear()


print("=" * 78)
print("1. WHAT THE RULE REMOVES")
print("=" * 78)
with_strict(False)
loose = scored_tracks(conn)
with_strict(True)
strict = scored_tracks(conn)
removed_ids = set(loose["video_id"]) - set(strict["video_id"])
removed = loose[loose["video_id"].isin(removed_ids)]

print(f"  songs, union rule (current)   {len(loose):>6,}")
print(f"  songs, strict rule            {len(strict):>6,}")
print(f"  removed                       {len(removed):>6,}  "
      f"({len(removed) / len(loose):.1%})")
print(f"  plays removed                 {int(removed['play_count'].sum()):>6,}  "
      f"({removed['play_count'].sum() / loose['play_count'].sum():.1%})")
print("\n  most-played songs the rule would drop:")
for _, r in removed.nlargest(12, "play_count").iterrows():
    print(f"    {int(r['play_count']):>3} plays  {str(r['title'])[:60]}")

print("\n" + "=" * 78)
print("2. EFFECT ON THE HEADLINE (nested rediscovery)")
print("=" * 78)
rows = []
for label, flag in (("union (current)", False), ("strict", True)):
    with_strict(flag)
    out = nested_rediscovery(conn, canonical=True)
    if out["status"] != "ok":
        print(f"  {label}: could not run ({out})")
        continue
    rows.append({
        "rule": label,
        "half_life": out["chosen_half_life"],
        "baseline": out["mean_baseline"],
        "score": out["mean_score"],
        "lift": out["lift"],
        "wins": f"{out['wins']}/{out['n']}",
        "p": out["sign_test_p"],
    })
    print(f"\n  {label}: {out['verdict']}")
print()
print(pd.DataFrame(rows).to_string(index=False, float_format=FMT))

with_strict(False)   # leave the default as we found it
conn.close()
print("\nDefault remains STRICT_MUSIC = False. Nothing was changed.")
print("DONE")
