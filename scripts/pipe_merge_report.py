"""Does stripping pipe metadata merge the label/Topic pairs, and what breaks?

Run:  scripts/run.sh scripts/pipe_merge_report.py
"""
import collections
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from taste_engine.canonical import canonical_key, collapse, strip_pipe_metadata
from taste_engine.db import connect
from taste_engine.score import scored_tracks

TARGETS = [
    ("Lyrical: Chammak Challo | Ra One | ShahRukh Khan | Kareena Kapoor",
     "Chammak Challo"),
    ("Lyrical : Jee Le Zaraa Song | Talaash | Aamir Khan, Rani Mukherjee",
     "Jee Le Zaraa"),
    ("Rockstar: Tum Ho (Lyrical Video) Song | Ranbir Kapoor | Nargis", "Tum Ho"),
    ("ANIMAL:Pehle Bhi Main(Full Video) | Ranbir Kapoor,Tripti Dimri",
     "Pehle Bhi Main"),
    ("Talwiinder - KAMMO JI (Prod. Parth Parashar) | Punjabi Lofi", "Kammo Ji"),
]

print("=" * 78)
print("1. THE FIVE NAMED PAIRS")
print("=" * 78)
for label_title, topic_title in TARGETS:
    a = canonical_key(label_title, "T-Series")
    b = canonical_key(topic_title, "Pritam - Topic")
    # Artist differs by construction here; the duration pass decides. Compare
    # the artist-stripped cores, which is what the duration pass groups on.
    core_a, core_b = a.partition("|")[2], b.partition("|")[2]
    mark = "MATCH  " if core_a == core_b else "NO     "
    print(f"  {mark} {strip_pipe_metadata(label_title)[:44]:<44} -> {core_a!r}")
    if core_a != core_b:
        print(f"          vs {topic_title[:40]:<40} -> {core_b!r}")

print("\n" + "=" * 78)
print("2. EFFECT ON THE WHOLE LIBRARY")
print("=" * 78)
conn = connect()
raw = scored_tracks(conn, canonical=False)
after = collapse(raw)
print(f"  uploads in the music set   {len(raw):>6,}")
print(f"  canonical songs            {len(after):>6,}")

# Which groups this change created, by comparing keys with and without the
# pipe strip.
import taste_engine.canonical as C

original = C.strip_pipe_metadata
C.strip_pipe_metadata = lambda x: str(x)       # disable
before_keys = [C.canonical_key(t, c) for t, c in zip(raw["title"], raw["channel"])]
C.strip_pipe_metadata = original               # re-enable
after_keys = [C.canonical_key(t, c) for t, c in zip(raw["title"], raw["channel"])]

groups_before = collections.defaultdict(set)
groups_after = collections.defaultdict(set)
for i, (b, a) in enumerate(zip(before_keys, after_keys)):
    groups_before[b].add(i)
    groups_after[a].add(i)
print(f"  distinct keys before strip {len(groups_before):>6,}")
print(f"  distinct keys after strip  {len(groups_after):>6,}")

new_merges = []
for key, members in groups_after.items():
    if len(members) < 2:
        continue
    was = {before_keys[i] for i in members}
    if len(was) > 1:
        new_merges.append((key, sorted(members)))

print(f"\n  groups that gained a member: {len(new_merges)}")
print("\n" + "=" * 78)
print("3. EVERY NEW MERGE — check for false positives")
print("=" * 78)
for key, members in sorted(new_merges, key=lambda kv: -len(kv[1])):
    print(f"\n  {key[:56]}")
    for i in members:
        r = raw.iloc[i]
        print(f"      {str(r['title'])[:58]:<58} | {str(r['channel'])[:20]}")
conn.close()
