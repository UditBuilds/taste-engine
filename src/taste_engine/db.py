"""SQLite schema and connection helpers.

One file, no ORM. Every table is rebuildable from `data/raw/` except
`video_metadata` and `quota_log`, which are the two things that cost API
quota to produce and must therefore survive a re-parse.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
-- Phase 1: parsed straight from Takeout ------------------------------------

CREATE TABLE IF NOT EXISTS plays (
    id          INTEGER PRIMARY KEY,
    video_id    TEXT NOT NULL,
    title       TEXT,            -- NULL when the video is deleted/private
    channel     TEXT,            -- NULL for ~6.6k deleted/private/Shorts rows
    channel_id  TEXT,
    watched_at  TEXT NOT NULL,   -- ISO-8601 UTC
    source      TEXT NOT NULL    -- 'music.youtube.com' | 'youtube.com'
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_plays ON plays(video_id, watched_at);
CREATE INDEX IF NOT EXISTS ix_plays_video ON plays(video_id);
CREATE INDEX IF NOT EXISTS ix_plays_time  ON plays(watched_at);

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id TEXT PRIMARY KEY,
    title       TEXT,
    description TEXT,
    created_at  TEXT,   -- unreliable, see README: TuneMyMusic rewrote these
    updated_at  TEXT,
    visibility  TEXT
);

-- Stored one row per source CSV line, duplicates included: 430 of the 11,475
-- rows are the same video repeated inside one playlist (TuneMyMusic re-added
-- tracks on transfer). Deduping here would quietly lose that signal, so
-- callers dedupe explicitly instead.
CREATE TABLE IF NOT EXISTS playlist_tracks (
    id            INTEGER PRIMARY KEY,
    playlist_name TEXT NOT NULL,  -- from the CSV filename; the per-track CSVs
                                  -- carry no playlist id
    video_id      TEXT NOT NULL,
    added_at      TEXT,
    position      INTEGER NOT NULL  -- 0-based order within the source CSV
);
CREATE INDEX IF NOT EXISTS ix_pt_video ON playlist_tracks(video_id);
CREATE INDEX IF NOT EXISTS ix_pt_name  ON playlist_tracks(playlist_name);

CREATE TABLE IF NOT EXISTS library_songs (
    video_id    TEXT PRIMARY KEY,
    song_title  TEXT,
    album_title TEXT,
    artists     TEXT   -- '; '-joined, up to 7 columns in the source CSV
);

-- Phase 2: bought with API quota, never discard ----------------------------

CREATE TABLE IF NOT EXISTS video_metadata (
    video_id         TEXT PRIMARY KEY,
    found            INTEGER NOT NULL,  -- 0 = deleted/private; still cached so
                                        -- we never pay to look it up twice
    title            TEXT,
    channel_id       TEXT,
    channel_title    TEXT,
    category_id      TEXT,
    published_at     TEXT,
    duration         TEXT,              -- ISO-8601 period, e.g. PT3M21S
    topic_categories TEXT,              -- JSON list of Wikipedia URLs
    tags             TEXT,              -- JSON list
    fetched_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vm_category ON video_metadata(category_id);

CREATE TABLE IF NOT EXISTS quota_log (
    id        INTEGER PRIMARY KEY,
    day       TEXT NOT NULL,   -- YYYY-MM-DD in US/Pacific (Google's reset zone)
    method    TEXT NOT NULL,
    units     INTEGER NOT NULL,
    spent_at  TEXT NOT NULL,
    note      TEXT
);
CREATE INDEX IF NOT EXISTS ix_quota_day ON quota_log(day);

-- Phase 4: what we wrote back, so it can be undone -------------------------

CREATE TABLE IF NOT EXISTS written_playlists (
    playlist_id TEXT PRIMARY KEY,
    title       TEXT,
    created_at  TEXT,
    track_count INTEGER,
    committed   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS written_tracks (
    playlist_id TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    position    INTEGER,
    written_at  TEXT,
    PRIMARY KEY (playlist_id, video_id)
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the database, creating the schema if needed."""
    path = Path(path) if path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
