"""Reproduces the before/after distinct-backfill-track comparison this
session measured for briefs/backfill_rank.md: score-ranked (OLD, the
behaviour before that brief) vs distance-ranked with the
MAX_BACKFILL_DISTANCE ceiling (NEW, what `writer.plan()` does today).
`scripts/backfill_plan.py`'s regenerated report quotes this comparison's
numbers; this script is what keeps them reproducible instead of a one-off
measurement that vanishes with the session that produced it.

OLD is a deliberately FROZEN replica of the pre-fix selection rule (plain
score ranking, no distance, no ceiling) - it duplicates ~15 lines of logic
that exists nowhere else in the repo, on purpose. It reuses only what never
changed: `writer._target_length`, `writer._modal_genre`,
`config.MIN_SCORE`/`MIN_CLUSTER_NATIVE`, `embed.tidy_genres`. Do not "fix"
`old_backfill` to track `writer.py` as `writer.py` evolves further - the
entire point of this function is that it keeps doing what the old code did.

NEW just calls `writer.plan(mode="rediscover")` - the real, current code
path, always in sync automatically because it IS the code, not a replica of
it.

No API calls, no `--commit`: both sides are pure computation over the local
database and cached embeddings.

Run:  scripts/run.sh scripts/compare_backfill_ranking.py
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from taste_engine import config, writer
from taste_engine.db import connect
from taste_engine.embed import tidy_genres
from taste_engine.recommend import build as build_frame, favourites


def old_backfill(frame: pd.DataFrame, cluster: int) -> pd.DataFrame:
    """FROZEN: the score-ranked selection writer.py used before
    briefs/backfill_rank.md. Returns the backfilled rows only (a zero-row
    slice when none). See the module docstring before touching this."""
    real = frame[frame["cluster"] >= 0]
    eligible = real[real["score"] >= config.MIN_SCORE]

    def _ranked(pool: pd.DataFrame) -> pd.DataFrame:
        return pool.sort_values(["score", "video_id"], ascending=[False, True])

    native = _ranked(eligible[eligible["cluster"] == cluster])
    target_length = writer._target_length(len(native))
    deficit = target_length - len(native)
    if deficit <= 0:
        return native.iloc[0:0]
    modal_genre, _ = writer._modal_genre(native["genres"].map(tidy_genres))
    if modal_genre is None:
        return native.iloc[0:0]
    outside = eligible[eligible["cluster"] != cluster].copy()
    outside["genres_tidy"] = outside["genres"].map(tidy_genres)
    mask = outside["genres_tidy"].map(lambda gl: modal_genre in gl).astype(bool)
    return _ranked(outside[mask]).head(deficit)


def _summarize(label: str, per_cluster_ids: dict[int, list[str]]) -> dict:
    all_ids = [vid for ids in per_cluster_ids.values() for vid in ids]
    distinct = set(all_ids)
    largest = max((len(v) for v in per_cluster_ids.values()), default=0)
    print(f"{label}: {len(all_ids)} slots, {len(distinct)} distinct, "
          f"largest single playlist {largest}")
    return {
        "slots": len(all_ids), "distinct": len(distinct), "largest": largest,
        "freq": Counter(all_ids),
    }


def main() -> int:
    conn = connect()
    try:
        frame = build_frame(conn)
        obvious = favourites(frame, config.EXCLUDE_TOP)
        rediscover_frame = frame[~frame["video_id"].isin(obvious)]
        real = rediscover_frame[rediscover_frame["cluster"] >= 0]
        eligible = real[real["score"] >= config.MIN_SCORE]
        native_counts = eligible.groupby("cluster").size()
        qualifying = sorted(
            int(c) for c in native_counts.index
            if native_counts[c] >= config.MIN_CLUSTER_NATIVE
        )
        names = {
            cid: str(rediscover_frame.loc[rediscover_frame["cluster"] == cid,
                                           "cluster_name"].iloc[0])
            for cid in qualifying
        }

        old_ids: dict[int, list[str]] = {}
        new_ids: dict[int, list[str]] = {}
        for cid in qualifying:
            old_ids[cid] = list(old_backfill(rediscover_frame, cid)["video_id"])
            # backfill=True: Build Brief 5 made config.BACKFILL_ENABLED=False
            # the default, but this script's entire purpose is comparing the
            # old score-ranked backfill against the current distance-ranked
            # one - without the override the NEW side would backfill nothing.
            p = writer.plan(conn, cluster=cid, mode="rediscover", backfill=True)
            tracks = p["tracks"]
            new_ids[cid] = list(tracks[tracks["cluster"] != cid]["video_id"])

        print(f"qualifying clusters: {len(qualifying)}\n")
        old_stats = _summarize(
            "BEFORE (score-ranked, no ceiling - pre briefs/backfill_rank.md)", old_ids
        )
        new_stats = _summarize(
            f"AFTER  (distance-ranked, MAX_BACKFILL_DISTANCE={config.MAX_BACKFILL_DISTANCE})",
            new_ids,
        )
        print()

        print("per-cluster backfill count, before -> after:")
        for cid in qualifying:
            print(f"  {names[cid]:<45} {len(old_ids[cid]):>2} -> {len(new_ids[cid]):>2}")
        print()

        print("most repeated backfill tracks BEFORE (top 10):")
        for vid, n in old_stats["freq"].most_common(10):
            title = str(rediscover_frame.loc[rediscover_frame["video_id"] == vid, "title"].iloc[0])
            print(f"  {n:>2}x  {title[:60]}  ({vid})")
        print("\nmost repeated backfill tracks AFTER (top 10):")
        for vid, n in new_stats["freq"].most_common(10):
            title = str(rediscover_frame.loc[rediscover_frame["video_id"] == vid, "title"].iloc[0])
            print(f"  {n:>2}x  {title[:60]}  ({vid})")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
