"""How many tracks collapse, and where the merge might be too aggressive."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/mnt/c/Users/uditk/Projects/taste-engine/src")
from taste_engine.db import connect
from taste_engine.canonical import collapse_report
from taste_engine.score import scored_tracks

conn = connect()
raw = scored_tracks(conn, canonical=False)
rep = collapse_report(raw)
conn.close()

print(f"music tracks (by video id) : {rep['rows_in']:,}")
print(f"canonical songs            : {rep['rows_out']:,}")
print(f"collapsed away             : {rep['collapsed']:,} "
      f"({rep['collapsed']/rep['rows_in']:.1%})")
print(f"songs with >1 upload       : {rep['groups_with_duplicates']:,}")
print(f"largest group              : {rep['largest_group']} uploads "
      f"-> {rep['largest_group_key']!r}")
for t in rep["largest_group_titles"]:
    print(f"    {str(t)[:70]}")
print(f"\ncross-artist merges (possible over-merge): {rep['cross_artist_count']}")
for g in rep["cross_artist_groups"][:8]:
    print(f"  x{g['n']}  {g['key'][:40]!r:<42} {g['artists'][:4]}")
