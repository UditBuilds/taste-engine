"""Build Brief 3, B4 - report backfill's effect before writing anything.

No --commit, no API calls: this only exercises writer.plan(), which is pure
computation over the local database and the cached embeddings.

Build Brief 5: this calls writer.plan() with no `backfill` override, so it
shows exactly what `taste-engine write --cluster-name X` would - backfill
disabled by default (config.BACKFILL_ENABLED). Pass a cluster name and read
"backfill disabled" in the output if that's what you're seeing; it is not a
bug in this script.

Run:  scripts/run.sh scripts/backfill_report.py "T-Series" "Travis Scott"
"""
from __future__ import annotations

import sys

from taste_engine.canonical import canonical_key
from taste_engine.db import connect
from taste_engine import config, writer


def report(conn, cluster_name: str) -> None:
    print("=" * 78)
    print(f"{cluster_name!r}")
    print("=" * 78)

    try:
        p = writer.plan(conn, cluster_name=cluster_name, mode="rediscover")
    except writer.WriteBlocked as exc:
        print(f"  BLOCKED: {exc}")
        print()
        return
    tracks = p["tracks"]

    print(f"  requested cluster        {p['cluster']} ({p['title']})")
    print(f"  native (>= {config.MIN_SCORE} in-cluster) {p['native_count']}")
    if p["backfill_enabled"]:
        print(f"  modal genre                {p['modal_genre']!r}")
        print(f"  target length              {p['target_length']} "
              f"= floor({p['native_count']} / (1 - {config.MAX_BACKFILL_SHARE}))")
    else:
        print(f"  backfill disabled          config.BACKFILL_ENABLED=False; "
              "target length is the native count itself")
    print(f"  backfilled                {p['backfilled_count']} "
          f"from {len(p['backfill_by_cluster'])} neighbouring cluster(s)")
    for cid, cname, n in p["backfill_by_cluster"]:
        print(f"      {n:>3} from cluster {cid} ({cname})")
    print(f"  final count                {p['count']} of {p['target_length']} target"
          + (f"  -- SHORT by {p['shortfall']}, not enough genre-matching material"
             if p["shortfall"] else ""))
    if len(tracks):
        print(f"  score range                {tracks['score'].min():.3f} - "
              f"{tracks['score'].max():.3f}")
    keys = [canonical_key(r["title"], r.get("channel")) for _, r in tracks.iterrows()]
    distinct = len({k for k in keys if k})
    print(f"  distinct canonical songs   {distinct} of {len(tracks)}")

    print()
    print("  per-track (native vs backfilled):")
    requested = p["cluster"]
    for i, row in tracks.iterrows():
        native = row.get("cluster") == requested
        tag = "native   " if native else f"backfill from {row.get('cluster_name')!r}"
        print(f"    {i + 1:>3}. [{tag}] {str(row.get('title'))[:60]:<60} "
              f"{row.get('score'):.3f}")
    print()


def main() -> int:
    names = sys.argv[1:] or ["T-Series", "Travis Scott"]
    conn = connect()
    try:
        for name in names:
            report(conn, name)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
