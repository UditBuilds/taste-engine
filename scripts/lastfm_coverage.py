"""Last.fm tag coverage measurement - is this a usable genre signal?

Fetches track.getTopTags (falling back to artist.getTopTags) for every
canonical music track, caches everything in track_tags/track_tag_lookups
(db.py Phase 5), and computes every number reports/lastfm_coverage.md needs
from SECTION 3 onward. Idempotent and resumable - a canonical track already
attempted under a given (source, variant) is skipped, not re-fetched.

Measurement only: does not touch clustering, embeddings, scoring,
evaluation, or the write path. See reports/lastfm_coverage.md SECTION 0 for
the ARI ground-truth answer, which this script does not depend on.

Run:  scripts/run.sh scripts/lastfm_coverage.py
      scripts/run.sh scripts/lastfm_coverage.py --limit 50   # smoke test
      scripts/run.sh scripts/lastfm_coverage.py --report-only  # skip fetching
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

import numpy as np

from taste_engine import lastfm
from taste_engine.db import connect
from taste_engine.embed import artist_from_channel, cluster_tracks


def _header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# --- fetching ----------------------------------------------------------

def run_fetch(conn, api_key: str, limit: int | None = None) -> None:
    pool = lastfm.canonical_track_pool(conn)
    ids = list(pool["canonical_id"])
    if limit is not None:
        ids = ids[:limit]

    _header(f"Pass 1 (feat kept) - {len(ids):,} canonical tracks")
    counts1 = lastfm.run_coverage_fetch(
        conn, api_key, variant="feat_kept", only_canonical_ids=ids
    )
    for k, v in sorted(counts1.items()):
        print(f"  {k:<32} {v:>6,}")

    failed = _failed_canonical_ids(conn, "feat_kept", allowed_ids=ids)
    _header(f"Pass 2 (feat stripped) - {len(failed):,} tracks that failed pass 1")
    counts2 = lastfm.run_coverage_fetch(
        conn, api_key, variant="feat_stripped", only_canonical_ids=failed
    )
    for k, v in sorted(counts2.items()):
        print(f"  {k:<32} {v:>6,}")


def _failed_canonical_ids(conn, variant: str, allowed_ids=None) -> list[str]:
    rows = conn.execute(
        "SELECT canonical_id FROM track_tag_lookups "
        "WHERE source = 'track' AND query_variant = ? "
        "AND status IN ('not_found', 'error')",
        (variant,),
    ).fetchall()
    ids = {r[0] for r in rows}
    if allowed_ids is not None:
        ids &= set(allowed_ids)
    return sorted(ids)


# --- report numbers ------------------------------------------------------

def match_rate(conn, pool_size: int, source: str, variant: str) -> tuple[int, int, float]:
    matched = conn.execute(
        "SELECT COUNT(DISTINCT canonical_id) FROM track_tags "
        "WHERE source = ? AND canonical_id IN "
        "(SELECT canonical_id FROM track_tag_lookups WHERE source = ? AND query_variant = ?)",
        (source, source, variant),
    ).fetchone()[0]
    return matched, pool_size, (matched / pool_size if pool_size else 0.0)


def weight_percentiles(conn, source: str) -> dict[int, float]:
    weights = [r[0] for r in conn.execute(
        "SELECT weight FROM track_tags WHERE source = ?", (source,)
    ).fetchall()]
    if not weights:
        return {}
    arr = np.array(weights, dtype=float)
    return {p: float(np.percentile(arr, p)) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)}


def top_tags(conn, pool_size: int, source: str, n: int = 30):
    rows = conn.execute(
        "SELECT tag, COUNT(DISTINCT canonical_id) AS n FROM track_tags "
        "WHERE source = ? GROUP BY tag ORDER BY n DESC LIMIT ?",
        (source, n),
    ).fetchall()
    return [(tag, cnt, cnt / pool_size if pool_size else 0.0) for tag, cnt in rows]


def failure_breakdown(conn, source: str, variant: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM track_tag_lookups "
        "WHERE source = ? AND query_variant = ? GROUP BY status",
        (source, variant),
    ).fetchall()
    return dict(rows)


def artist_found_track_not_found(conn, variant: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM track_tag_lookups t "
        "WHERE t.source = 'track' AND t.query_variant = ? AND t.status = 'not_found' "
        "AND EXISTS (SELECT 1 FROM track_tag_lookups a "
        "  WHERE a.canonical_id = t.canonical_id AND a.source = 'artist' "
        "  AND a.query_variant = ? AND a.status IN ('ok_tags', 'ok_zero_tags'))",
        (variant, variant),
    ).fetchone()[0]


def rate_limit_errors(conn, source: str, variant: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM track_tag_lookups "
        "WHERE source = ? AND query_variant = ? AND status = 'error' "
        "AND error_detail LIKE '%429%'",
        (source, variant),
    ).fetchone()[0]


def single_artist_cluster_rate(conn, pool, threshold: float = 0.8) -> dict:
    """% of the CURRENT title_artist clustering's real clusters where one
    artist accounts for more than `threshold` of members. Needs no Last.fm
    data - the report-required baseline the follow-up work is judged
    against (brief SECTION 5 item 9).
    """
    clustered = cluster_tracks(pool, mode="title_artist")
    real = clustered[clustered["cluster"] >= 0].copy()
    real["artist"] = real["channel"].map(artist_from_channel)
    resolved = real[real["artist"] != ""]

    per_cluster = []
    for cid, grp in resolved.groupby("cluster"):
        c = Counter(grp["artist"])
        top_artist, top_n = c.most_common(1)[0]
        per_cluster.append((int(cid), len(grp), top_n / len(grp), top_artist))

    n_clusters = len(per_cluster)
    n_single = sum(1 for r in per_cluster if r[2] > threshold)
    return {
        "n_clusters": n_clusters,
        "n_single_artist": n_single,
        "rate": n_single / n_clusters if n_clusters else 0.0,
        "noise_share": float((clustered["cluster"] == -1).mean()),
        "member_coverage": len(resolved) / len(real) if len(real) else 0.0,
        "detail": sorted(per_cluster, key=lambda r: -r[2]),
    }


def print_report(conn, pool) -> None:
    pool_size = len(pool)
    _header(f"Match rate - track level ({pool_size:,} canonical tracks)")
    for variant in ("feat_kept", "feat_stripped"):
        n_attempted = conn.execute(
            "SELECT COUNT(*) FROM track_tag_lookups WHERE source='track' AND query_variant=?",
            (variant,),
        ).fetchone()[0]
        if not n_attempted:
            continue
        matched, total, rate = match_rate(conn, pool_size, "track", variant)
        print(f"  [{variant}] {matched:,}/{total:,} = {rate:.1%}")

    _header("Match rate - artist-level fallback (reported separately)")
    for variant in ("feat_kept", "feat_stripped"):
        n_attempted = conn.execute(
            "SELECT COUNT(*) FROM track_tag_lookups WHERE source='artist' AND query_variant=?",
            (variant,),
        ).fetchone()[0]
        if not n_attempted:
            continue
        matched, total, rate = match_rate(conn, pool_size, "artist", variant)
        print(f"  [{variant}] {matched:,}/{total:,} = {rate:.1%}")

    _header("Tag-weight percentiles")
    for source in ("track", "artist"):
        pct = weight_percentiles(conn, source)
        if pct:
            print(f"  [{source}] " + "  ".join(f"p{p}={v:.0f}" for p, v in pct.items()))

    _header("Top 30 tags by track coverage")
    for tag, cnt, share in top_tags(conn, pool_size, "track", 30):
        print(f"  {tag:<28} {cnt:>5,}  {share:>6.1%}")

    _header("Single-artist cluster rate (current clustering, no Last.fm data)")
    result = single_artist_cluster_rate(conn, pool)
    print(f"  clusters: {result['n_clusters']}  noise share: {result['noise_share']:.1%}")
    print(f"  >80% one artist: {result['n_single_artist']}/{result['n_clusters']} "
          f"= {result['rate']:.1%}")

    _header("Failure breakdown")
    for variant in ("feat_kept", "feat_stripped"):
        breakdown = failure_breakdown(conn, "track", variant)
        if not breakdown:
            continue
        print(f"  [track/{variant}] {breakdown}")
        print(f"    of which 429/rate-limited errors: "
              f"{rate_limit_errors(conn, 'track', variant)}")
    print(f"  artist-found-but-track-not-found (feat_kept): "
          f"{artist_found_track_not_found(conn, 'feat_kept')}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="fetch at most N canonical tracks")
    parser.add_argument("--report-only", action="store_true",
                         help="skip fetching, just compute numbers from what is cached")
    args = parser.parse_args(argv)

    conn = connect()
    try:
        pool = lastfm.canonical_track_pool(conn)
        print(f"canonical track pool: {len(pool):,}")

        if not args.report_only:
            api_key = lastfm.get_api_key()
            run_fetch(conn, api_key, limit=args.limit)

        print_report(conn, pool)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
