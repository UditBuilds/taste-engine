"""Phase 3 - turn scores and clusters into playlists.

Strategies are pure functions over a scored (and optionally clustered) frame so
`evaluate.py` can run each one against the same temporal hold-out and compare
them honestly.

What "recommend" means here is worth stating plainly. There is one user and the
candidate pool is that user's own listening history, so this is **repeat-
consumption prediction**: of the tracks you have played, which will you play
again next? That is the question a personal playlist generator actually has to
answer, and it is the question the evaluation scores.
"""
from __future__ import annotations

import sqlite3

import pandas as pd


def favourites(df: pd.DataFrame, n: int | None = None) -> set[str]:
    """The n most-played tracks — the set the rediscovery hold-out removes.

    Shared by `evaluate.rediscovery_split` and the writer's
    `--mode rediscover` so the playlist that ships is drawn from the same pool
    the evaluation scores. Two copies of this rule would drift, and the drift
    would be invisible: the eval would keep reporting rediscovery while the
    product quietly shipped replay.

    `video_id` breaks ties deterministically; without it the excluded set
    inherits the frame's incoming order, which is sorted by `score`, and the
    hold-out would depend on the model being evaluated.
    """
    from . import config

    n = config.EXCLUDE_TOP if n is None else n
    if df.empty or n <= 0:
        return set()
    return set(
        df.sort_values(["play_count", "video_id"], ascending=[False, True])
        .head(n)["video_id"]
    )


def exclude_favourites(df: pd.DataFrame, n: int | None = None) -> pd.DataFrame:
    """Drop the most-played tracks, leaving what the model has to find."""
    return df[~df["video_id"].isin(favourites(df, n))].reset_index(drop=True)


# Every strategy breaks ties on `video_id` last. Without it a tied ranking
# inherits the frame's incoming row order, which `scored_tracks` sorts by
# `score` - so the baseline's picks would shift with the half-life and it would
# stop being a valid control.
def by_most_played(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Baseline: the n most-played tracks, ties broken by recency."""
    return df.sort_values(
        ["play_count", "days_since", "video_id"], ascending=[False, True, True]
    ).head(n).reset_index(drop=True)


def by_score(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """log1p(plays) * recency decay - the model in section 7.1."""
    return df.sort_values(
        ["score", "video_id"], ascending=[False, True]
    ).head(n).reset_index(drop=True)


def by_recency(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Ablation: recency alone, ignoring how often a track was played."""
    return df.sort_values(
        ["days_since", "play_count", "video_id"], ascending=[True, False, True]
    ).head(n).reset_index(drop=True)


def by_cluster_diverse(df: pd.DataFrame, n: int = 20, per_cluster: int = 3) -> pd.DataFrame:
    """Round-robin across the strongest clusters.

    Trades a little precision for variety: twenty Travis Scott tracks is a
    good prediction and a bad playlist.
    """
    if "cluster" not in df.columns:
        return by_score(df, n)

    ranked = df.sort_values("score", ascending=False)
    real = ranked[ranked["cluster"] >= 0]
    if real.empty:
        return by_score(df, n)

    order = (
        real.groupby("cluster")["score"].sum().sort_values(ascending=False).index.tolist()
    )
    buckets = {c: real[real["cluster"] == c] for c in order}

    picked, depth = [], 0
    while len(picked) < n and depth < per_cluster:
        for cluster in order:
            group = buckets[cluster]
            if depth < len(group):
                picked.append(group.iloc[depth])
                if len(picked) == n:
                    break
        depth += 1

    out = pd.DataFrame(picked)
    if len(out) < n:  # top up from outliers if the clusters ran dry
        extra = ranked[~ranked["video_id"].isin(out.get("video_id", []))]
        out = pd.concat([out, extra.head(n - len(out))])
    return out.head(n).reset_index(drop=True)


STRATEGIES = {
    "most_played": by_most_played,
    "score": by_score,
    "recency": by_recency,
    "cluster_diverse": by_cluster_diverse,
}


def recommend(df: pd.DataFrame, n: int = 20, strategy: str = "score") -> pd.DataFrame:
    try:
        fn = STRATEGIES[strategy]
    except KeyError:
        raise KeyError(
            f"unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}"
        ) from None
    return fn(df, n)


def cluster_playlists(
    df: pd.DataFrame, size: int = 25, min_tracks: int = 10
) -> list[dict]:
    """One candidate playlist per cluster, ranked internally by score."""
    playlists = []
    real = df[df["cluster"] >= 0] if "cluster" in df.columns else df
    for cluster, group in real.groupby("cluster"):
        if len(group) < min_tracks:
            continue
        ranked = group.sort_values("score", ascending=False)
        playlists.append(
            {
                "cluster": int(cluster),
                "name": str(ranked["cluster_name"].iloc[0]),
                "size": min(size, len(ranked)),
                "available": len(ranked),
                "total_score": float(ranked["score"].sum()),
                "tracks": ranked.head(size).reset_index(drop=True),
            }
        )
    return sorted(playlists, key=lambda p: p["total_score"], reverse=True)


def build(conn: sqlite3.Connection, half_life: float | None = None) -> pd.DataFrame:
    """Scored + clustered tracks, the input every strategy expects."""
    from .embed import cluster_tracks
    from .score import scored_tracks

    return cluster_tracks(scored_tracks(conn, half_life=half_life))


def main() -> int:
    import argparse

    from .db import connect

    parser = argparse.ArgumentParser(description="Generate candidate playlists")
    parser.add_argument("--size", type=int, default=25, help="tracks per playlist")
    parser.add_argument("--top", type=int, default=6, help="playlists to show")
    args = parser.parse_args()

    conn = connect()
    try:
        df = build(conn)
    finally:
        conn.close()

    playlists = cluster_playlists(df, size=args.size)
    print(f"{len(playlists)} candidate playlists from {len(df):,} tracks\n")
    for playlist in playlists[: args.top]:
        print(f"== {playlist['name']}  ({playlist['available']} tracks available)")
        for i, row in playlist["tracks"].head(8).iterrows():
            print(f"   {i + 1:>2}. {str(row['title'])[:54]:<54} {row['score']:.2f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
