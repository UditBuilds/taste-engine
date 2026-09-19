"""Pre-write gates: is this list distinct songs, ranked on canonical data?

Cluster length is computed (floor + genre guard, briefs/backfill_constraint.md),
not requested - there is no `limit` to pass.

Run:  scripts/run.sh scripts/verify_write_plan.py <cluster>
"""
import sys, warnings, collections, re
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from taste_engine.db import connect
from taste_engine.writer import plan
from taste_engine.canonical import canonical_key
from taste_engine.score import scored_tracks

cluster = int(sys.argv[1]) if len(sys.argv) > 1 else 34

conn = connect()
p = plan(conn, cluster=cluster)
t = p["tracks"]

print("=" * 70)
print("GATE 2 — is the list distinct songs, or entries that collapse?")
print("=" * 70)
keys = [canonical_key(r["title"], r.get("channel")) for _, r in t.iterrows()]
distinct = len({k for k in keys if k})
print(f"  entries in the plan          {len(t)}")
print(f"  DISTINCT CANONICAL SONGS     {distinct}")
dupes = [k for k, n in collections.Counter(keys).items() if n > 1 and k]
print(f"  entries sharing a canonical key: {len(dupes)}  "
      f"{'(none — one row per song)' if not dupes else dupes}")

print("\n=" * 1 + "=" * 69)
print("GATE 3 — was the RANKING built on canonical data, or only the output?")
print("=" * 70)
has_variants = "variants" in t.columns
print(f"  plan carries the `variants` column   {has_variants}")
print("    (added only by canonical.collapse(); its presence means the frame")
print("     came through the canonical path before ranking)")
if has_variants:
    merged = t[t["variants"] > 1]
    print(f"  selected songs built from >1 upload  {len(merged)} of {len(t)}")
    print(f"  total uploads behind these {len(t)} songs  {int(t['variants'].sum())}")
    print("\n  merged songs in this playlist (play counts are SUMS):")
    for _, r in merged.sort_values("play_count", ascending=False).head(6).iterrows():
        print(f"    {int(r['variants'])} uploads, {int(r['play_count']):>3} plays  "
              f"{str(r['title'])[:50]}")

# Independent proof: the representative's own raw play count is lower than the
# ranked play count, so the ranking cannot have used per-video counts.
raw = scored_tracks(conn, canonical=False).set_index("video_id")["play_count"]
checked = mismatched = 0
for _, r in t.iterrows():
    if r.get("variants", 1) > 1 and r["video_id"] in raw.index:
        checked += 1
        if int(r["play_count"]) > int(raw.loc[r["video_id"]]):
            mismatched += 1
print(f"\n  merged songs whose ranked play_count exceeds the single upload's: "
      f"{mismatched}/{checked}")
print("    (if the ranking had used raw per-video counts these would be equal)")
conn.close()
