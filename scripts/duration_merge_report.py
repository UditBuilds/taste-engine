"""What does the duration second-pass merge, and does it merge anything wrong?

Run:  scripts/run.sh scripts/duration_merge_report.py
"""
import sys, warnings, collections
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from taste_engine import config
from taste_engine.canonical import (
    add_canonical_key, canonical_key, iso_seconds, merge_by_duration, title_core,
)
from taste_engine.db import connect
from taste_engine.score import scored_tracks

conn = connect()
raw = scored_tracks(conn, canonical=False)
work = add_canonical_key(raw)
work["core_key"] = [title_core(t, c) for t, c in zip(work["title"], work["channel"])]
work["seconds"] = work["duration"].map(iso_seconds)

before = work["canonical_key"].nunique()
merged_keys = merge_by_duration(work)
after = merged_keys.nunique()

print("=" * 78)
print("1. HOW MUCH THE DURATION PASS MERGES")
print("=" * 78)
print(f"  canonical songs, artist rule only   {before:>6,}")
print(f"  canonical songs, + duration pass    {after:>6,}")
print(f"  additional merges                   {before - after:>6,}")
print(f"  songs with no runtime (never merge) "
      f"{int(work['seconds'].isna().sum()):>6,}")
print(f"  tolerance                           "
      f"{config.DURATION_MERGE_TOLERANCE_S:>6}s")

print("\n" + "=" * 78)
print("2. EVERY NEW MERGE — eyeball for false positives")
print("=" * 78)
work["new_key"] = merged_keys
groups = collections.defaultdict(set)
for _, r in work.iterrows():
    if r["new_key"] != r["canonical_key"] or True:
        groups[r["new_key"]].add(r["canonical_key"])
changed = {k: v for k, v in groups.items() if len(v) > 1}
print(f"  {len(changed)} groups gained a member\n")
rep = work.drop_duplicates("canonical_key").set_index("canonical_key")
for new_key, olds in sorted(changed.items()):
    secs = sorted({int(rep.loc[o, "seconds"]) for o in olds
                   if rep.loc[o, "seconds"] == rep.loc[o, "seconds"]})
    spread = (max(secs) - min(secs)) if secs else "?"
    print(f"  [{spread}s spread] {new_key[:46]}")
    for o in sorted(olds):
        row = rep.loc[o]
        s = int(row["seconds"]) if row["seconds"] == row["seconds"] else None
        mins = f"{s // 60}:{s % 60:02d}" if s else "  ?  "
        print(f"      {mins}  {str(row['title'])[:56]:<56} | {str(row['channel'])[:22]}")

print("\n" + "=" * 78)
print("3. THE CASES THAT MUST STAY SEPARATE")
print("=" * 78)
key_of = dict(zip(work["canonical_key"], work["new_key"]))
def final(title, channel):
    k = canonical_key(title, channel)
    return key_of.get(k, k)

checks = [
    ("Die For You", "Joji - Topic", "Die For You", "TheWeekndVEVO"),
    ("Falling", "Harry Styles - Topic", "Falling", "Trevor Daniel - Topic"),
    ("Love Me", "Justin Bieber - Topic", "Love Me", "Lil Wayne - Topic"),
]
for t1, c1, t2, c2 in checks:
    a, b = final(t1, c1), final(t2, c2)
    print(f"  {'SEPARATE' if a != b else 'MERGED !!'}  {t1!r}: {c1} vs {c2}")

raabta = work[work["core_key"].str.fullmatch("raabta", na=False)]
print(f"\n  'Raabta' uploads in the library: {len(raabta)}")
for _, r in raabta.iterrows():
    s = r["seconds"]
    mins = f"{int(s) // 60}:{int(s) % 60:02d}" if s == s else "  ?  "
    print(f"      {mins}  {str(r['title'])[:44]:<44} | {str(r['channel'])[:20]:<20} "
          f"-> {r['new_key'][:28]}")
print(f"  distinct songs after merge: {raabta['new_key'].nunique()}")
conn.close()
