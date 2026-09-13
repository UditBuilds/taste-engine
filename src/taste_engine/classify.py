"""Phase 2 - decide which watched videos are music.

Two independent classifiers:

1. **Heuristics** (free). Channel naming conventions, the playback host, and
   membership of the user's own playlists/library. Cheap, but blind to
   artist-owned channels that carry no `- Topic` or `VEVO` marker - Don Toliver
   has 230 plays on a channel named simply "Don Toliver".

2. **categoryId** (609 units). YouTube's own Music category, fetched by
   `resolve.py`. A far stronger label than any string match, and it arrives
   with `topicDetails.topicCategories` - free Wikipedia genre tags.

`comparison_table()` scores one against the other. That table is the honest
evaluation artefact the README leads with, and it costs under 7% of a day's
quota to produce.
"""
from __future__ import annotations

import json
import sqlite3

import numpy as np
import pandas as pd

from . import config

TOPIC_SUFFIX = " - Topic"
VEVO_MARKER = "VEVO"

HEURISTIC_SIGNALS = ("topic_channel", "vevo_channel", "music_host", "in_playlist", "in_library")

SIGNAL_LABELS = {
    "topic_channel": "Channel ends with '- Topic'",
    "vevo_channel": "Channel contains 'VEVO'",
    "music_host": "Played on music.youtube.com",
    "in_playlist": "Video appears in a playlist",
    "in_library": "Video in YT Music library",
}


def _video_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per unique video in the watch history, with play statistics."""
    return pd.read_sql(
        """
        SELECT
            video_id,
            COUNT(*)                                            AS play_count,
            MAX(title)                                          AS title,
            MAX(channel)                                        AS channel,
            MAX(channel_id)                                     AS channel_id,
            MAX(watched_at)                                     AS last_played,
            MIN(watched_at)                                     AS first_played,
            SUM(source = 'music.youtube.com')                   AS music_host_plays
        FROM plays
        GROUP BY video_id
        """,
        conn,
    )


def classify_heuristic(conn: sqlite3.Connection) -> pd.DataFrame:
    """Label every unique history video using signals that cost no quota."""
    df = _video_frame(conn)

    playlist_ids = set(
        r[0] for r in conn.execute("SELECT DISTINCT video_id FROM playlist_tracks")
    )
    library_ids = set(r[0] for r in conn.execute("SELECT video_id FROM library_songs"))

    channel = df["channel"].fillna("")
    df["topic_channel"] = channel.str.endswith(TOPIC_SUFFIX)
    df["vevo_channel"] = channel.str.contains(VEVO_MARKER, case=True, regex=False)
    df["music_host"] = df["music_host_plays"] > 0
    df["in_playlist"] = df["video_id"].isin(playlist_ids)
    df["in_library"] = df["video_id"].isin(library_ids)

    df["heuristic_music"] = df[list(HEURISTIC_SIGNALS)].any(axis=1)
    df["signal_count"] = df[list(HEURISTIC_SIGNALS)].sum(axis=1)
    return df


def _metadata_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT video_id, found, category_id, topic_categories, "
        "title AS api_title, channel_title AS api_channel, duration "
        "FROM video_metadata",
        conn,
    )


def has_metadata(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM video_metadata").fetchone()[0] > 0


def classify(conn: sqlite3.Connection) -> pd.DataFrame:
    """Heuristic labels, plus API labels wherever metadata has been fetched.

    `is_music` is the union of the two (see the reasoning below), so the
    pipeline runs to completion with or without API access: without metadata
    it degrades cleanly to the heuristics alone.
    """
    df = classify_heuristic(conn)

    if not has_metadata(conn):
        df["category_id"] = None
        df["api_music"] = pd.NA
        df["resolved"] = False
        df["genres"] = [[] for _ in range(len(df))]
        df["is_music"] = df["heuristic_music"]
        df["label_source"] = "heuristic"
        return df

    meta = _metadata_frame(conn)
    df = df.merge(meta, on="video_id", how="left")
    df["resolved"] = df["found"].fillna(0).astype(int).eq(1)
    # Nullable boolean: unresolved videos are genuinely unknown, not False.
    # (A plain bool column cannot hold pd.NA under pandas 3.)
    df["api_music"] = (
        df["category_id"].eq(config.MUSIC_CATEGORY_ID).astype("boolean")
    ).where(df["resolved"])
    df["genres"] = df["topic_categories"].map(_genres_from_topics)

    # Union, not categoryId-overrides-heuristic. The two label different things
    # and the disagreements show it:
    #
    #   712 videos categoryId calls music that the heuristics miss - artist-owned
    #       channels with no '- Topic' or VEVO marker (Don Toliver's own channel,
    #       75 plays on one track; Central Cee; PARTYNEXTDOOR; T-Series).
    #    53 videos the heuristics call music that categoryId files under
    #       'People & Blogs' or 'Entertainment' - fan re-uploads, slowed remixes,
    #       extended edits. categoryId describes the *uploader's* channel, not the
    #       content, and the signal that caught these was the user playing them on
    #       music.youtube.com or filing them in a playlist.
    #
    # Letting categoryId override would discard 53 tracks this user demonstrably
    # treats as music to avoid a handful of marginal compilations. The union
    # keeps both kinds of evidence.
    df["is_music"] = df["api_music"].fillna(False).astype(bool) | df["heuristic_music"]
    df["label_source"] = np.select(
        [
            df["api_music"].fillna(False).astype(bool) & df["heuristic_music"],
            df["api_music"].fillna(False).astype(bool),
            df["heuristic_music"],
        ],
        ["both", "categoryId", "heuristic"],
        default="none",
    )
    return df


def _genres_from_topics(raw) -> list[str]:
    """'https://en.wikipedia.org/wiki/Hip_hop_music' -> 'Hip hop music'."""
    if not raw:
        return []
    try:
        urls = json.loads(raw)
    except (TypeError, ValueError):
        return []
    out = []
    for url in urls:
        slug = str(url).rsplit("/", 1)[-1]
        label = slug.replace("_", " ").strip()
        if label and label not in out:
            out.append(label)
    return out


def signal_coverage(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per-signal and union coverage, in unique videos and in plays."""
    df = classify_heuristic(conn)
    total_videos = len(df)
    total_plays = int(df["play_count"].sum())

    rows = []
    for signal in HEURISTIC_SIGNALS:
        hit = df[df[signal]]
        rows.append(
            {
                "signal": SIGNAL_LABELS[signal],
                "videos": len(hit),
                "plays": int(hit["play_count"].sum()),
            }
        )
    union = df[df["heuristic_music"]]
    rows.append(
        {
            "signal": "Union (any signal)",
            "videos": len(union),
            "plays": int(union["play_count"].sum()),
        }
    )
    out = pd.DataFrame(rows)
    out["pct_videos"] = (out["videos"] / total_videos * 100).round(1)
    out["pct_plays"] = (out["plays"] / total_plays * 100).round(1)
    return out


def comparison_table(conn: sqlite3.Connection) -> dict:
    """Heuristic union vs. categoryId, with the agreement rate between them.

    Returns a dict with a `status` key so callers can render something useful
    before any quota has been spent.
    """
    coverage = signal_coverage(conn)
    if not has_metadata(conn):
        return {
            "status": "heuristic_only",
            "coverage": coverage,
            "note": "No video_metadata cached yet - run `python -m taste_engine.resolve`.",
        }

    df = classify(conn)
    resolved = df[df["resolved"]]
    both = resolved.dropna(subset=["api_music"])

    api_yes = both["api_music"].astype(bool)
    heur_yes = both["heuristic_music"].astype(bool)

    agree = int((api_yes == heur_yes).sum())
    confusion = {
        "both_music": int((api_yes & heur_yes).sum()),
        "api_only": int((api_yes & ~heur_yes).sum()),      # heuristics missed it
        "heuristic_only": int((~api_yes & heur_yes).sum()),  # heuristic false positive
        "neither": int((~api_yes & ~heur_yes).sum()),
    }
    precision = (
        confusion["both_music"] / (confusion["both_music"] + confusion["heuristic_only"])
        if (confusion["both_music"] + confusion["heuristic_only"])
        else 0.0
    )
    recall = (
        confusion["both_music"] / (confusion["both_music"] + confusion["api_only"])
        if (confusion["both_music"] + confusion["api_only"])
        else 0.0
    )
    return {
        "status": "compared",
        "coverage": coverage,
        "unique_videos": len(df),
        "resolved": len(resolved),
        "unresolved": int((~df["resolved"]).sum()),
        "api_music_videos": int(api_yes.sum()),
        "heuristic_music_videos": int(df["heuristic_music"].sum()),
        "agreement_rate": round(agree / len(both), 4) if len(both) else 0.0,
        "confusion": confusion,
        "heuristic_precision": round(precision, 4),
        "heuristic_recall": round(recall, 4),
    }


def music_tracks(conn: sqlite3.Connection) -> pd.DataFrame:
    """Music-labelled videos that carry enough metadata to model.

    A track with no title cannot be embedded and is dropped here rather than
    silently carried into the scorer as an empty string.
    """
    df = classify(conn)
    music = df[df["is_music"]].copy()
    if "api_title" in music.columns:
        music["title"] = music["api_title"].fillna(music["title"])
        music["channel"] = music["api_channel"].fillna(music["channel"])
    return music[music["title"].notna() & (music["title"].str.len() > 0)].reset_index(drop=True)


def main() -> int:
    from .db import connect

    conn = connect()
    try:
        table = comparison_table(conn)
        print("Heuristic signal coverage")
        print(table["coverage"].to_string(index=False))
        print()
        if table["status"] == "heuristic_only":
            print(table["note"])
        else:
            print(f"unique videos        {table['unique_videos']:>8,}")
            print(f"resolved via API     {table['resolved']:>8,}")
            print(f"categoryId == music  {table['api_music_videos']:>8,}")
            print(f"heuristic == music   {table['heuristic_music_videos']:>8,}")
            print(f"agreement rate       {table['agreement_rate']:>8.1%}")
            print(f"heuristic precision  {table['heuristic_precision']:>8.1%}")
            print(f"heuristic recall     {table['heuristic_recall']:>8.1%}")
            print(f"confusion            {table['confusion']}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
