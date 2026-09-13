"""Phase 3 - implicit-feedback scoring.

    score = log1p(play_count) * 0.5 ** (days_since_last_play / half_life)

`log1p` compresses the long tail. Travis Scott's "MY EYES" has 115 plays; a
20-play track should rank below it but not be buried by it. Raw counts give a
5.75x gap, `log1p` gives 1.57x - a meaningful but survivable difference.

Everything takes an explicit `as_of` date. The temporal hold-out in
`evaluate.py` scores the training window *as it looked on the split date*;
using "now" there would leak the future into the training signal.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config
from .classify import classify


def aggregate_plays(
    conn: sqlite3.Connection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Play counts per video within [start, end).

    Bounds are ISO dates. `end` is exclusive so train/test windows cannot
    overlap on the boundary day.
    """
    where, params = [], []
    if start:
        where.append("watched_at >= ?")
        params.append(start)
    if end:
        where.append("watched_at < ?")
        params.append(end)
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    return pd.read_sql(
        f"""
        SELECT video_id,
               COUNT(*)        AS play_count,
               MAX(watched_at) AS last_played,
               MIN(watched_at) AS first_played
        FROM plays
        {clause}
        GROUP BY video_id
        """,
        conn,
        params=params,
    )


def _as_datetime(value) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_scores(
    df: pd.DataFrame,
    as_of=None,
    half_life: float | None = None,
) -> pd.DataFrame:
    """Attach days_since_last_play, recency_weight and score."""
    half_life = config.RECENCY_HALF_LIFE_DAYS if half_life is None else half_life
    if half_life <= 0:
        raise ValueError("half_life must be positive")

    reference = _as_datetime(as_of)
    out = df.copy()
    if out.empty:
        for col in ("days_since", "recency_weight", "score"):
            out[col] = pd.Series(dtype="float64")
        return out

    last = pd.to_datetime(out["last_played"], format="ISO8601", utc=True)
    out["days_since"] = (pd.Timestamp(reference) - last).dt.total_seconds() / 86_400.0
    # A future reference date would otherwise inflate weights above 1.
    out["days_since"] = out["days_since"].clip(lower=0.0)
    out["recency_weight"] = 0.5 ** (out["days_since"] / half_life)
    out["score"] = np.log1p(out["play_count"]) * out["recency_weight"]
    return out


def scored_tracks(
    conn: sqlite3.Connection,
    as_of=None,
    start: str | None = None,
    end: str | None = None,
    half_life: float | None = None,
    music_only: bool = True,
    canonical: bool = True,
) -> pd.DataFrame:
    """Scored tracks for a window, joined to titles and music labels.

    `as_of` defaults to `end` when a window is given, so the training window is
    always scored from its own edge rather than from today.

    `canonical=True` collapses multiple uploads of the same recording into one
    track and sums their plays. Leaving it off inflates nDCG and leaks
    favourites past the rediscovery hold-out — see `canonical.py`. It is a
    parameter only so the two can be measured against each other.
    """
    labels = classify(conn)
    if music_only:
        labels = labels[labels["is_music"]]

    agg = aggregate_plays(conn, start=start, end=end)
    if agg.empty:
        return agg.assign(score=pd.Series(dtype="float64"))

    keep = [
        c
        for c in ("video_id", "title", "channel", "channel_id", "is_music",
                  "label_source", "genres", "in_library", "in_playlist",
                  "duration")
        if c in labels.columns
    ]
    df = agg.merge(labels[keep], on="video_id", how="inner")
    if canonical:
        from .canonical import collapse

        df = collapse(df)
    df = add_scores(df, as_of=as_of if as_of is not None else end, half_life=half_life)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def top_tracks(conn: sqlite3.Connection, n: int = 20, **kwargs) -> pd.DataFrame:
    return scored_tracks(conn, **kwargs).head(n)


def main() -> int:
    from .db import connect

    conn = connect()
    try:
        df = scored_tracks(conn)
        print(f"{len(df):,} scored music tracks "
              f"(half-life {config.RECENCY_HALF_LIFE_DAYS:.0f}d)\n")
        show = df.head(25)[["score", "play_count", "days_since", "title", "channel"]]
        show = show.assign(
            score=show["score"].round(3),
            days_since=show["days_since"].round(0).astype(int),
            title=show["title"].str.slice(0, 46),
            channel=show["channel"].fillna("").str.slice(0, 22),
        )
        print(show.to_string(index=False))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
