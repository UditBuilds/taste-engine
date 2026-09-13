"""Phase 1 - parse the Google Takeout export into SQLite.

Why regex and not an HTML parser: `watch-history.html` is a single 41.9 MB
document with ~41.5k repeated cells and no nesting worth traversing. Splitting
on the cell delimiter and running four small regexes over each fragment is far
faster than building a DOM, and the markup Google emits here is
machine-generated and stable.

Run:  python -m taste_engine.parse_takeout
"""
from __future__ import annotations

import csv
import html as htmllib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .db import connect, table_count

# --- cell-level regexes -----------------------------------------------------
CELL_DELIM = '<div class="outer-cell'
RE_BODY = re.compile(r'mdl-typography--body-1">(.*?)</div>', re.S)
RE_WATCH = re.compile(
    r'href="https://(www|music)\.youtube\.com/watch\?v=([\w-]{11})[^"]*">(.*?)</a>', re.S
)
RE_CHANNEL = re.compile(
    r'href="https://www\.youtube\.com/channel/([\w-]+)"[^>]*>(.*?)</a>', re.S
)
RE_TIMESTAMP = re.compile(r"<br>\s*([^<>]*?\d{4},\s*\d{1,2}:\d{2}:\d{2}[^<>]*?)\s*<br>")
RE_TAG = re.compile(r"<[^>]+>")

# Google writes "Sept" for September; strptime's %b only accepts three letters.
MONTH_FIXES = {"Sept": "Sep"}
RE_TZ_SUFFIX = re.compile(r"\s+[A-Z]{2,5}$")


def _clean(fragment):
    """Strip tags, unescape entities, collapse whitespace."""
    if fragment is None:
        return None
    text = htmllib.unescape(RE_TAG.sub("", fragment)).replace("\xa0", " ")
    text = " ".join(text.split())
    return text or None


def parse_timestamp(raw: str) -> datetime:
    """Turn "13 Sept 2026, 12:54:35 IST" into an aware UTC datetime.

    The trailing abbreviation is dropped and `config.LOCAL_TZ` applied instead:
    bare zone abbreviations are globally ambiguous and Python cannot resolve
    them. This export belongs to an Asia/Kolkata account.
    """
    text = " ".join(htmllib.unescape(raw).split())
    for bad, good in MONTH_FIXES.items():
        text = re.sub(r"\b" + bad + r"\b", good, text)
    text = RE_TZ_SUFFIX.sub("", text).strip()
    naive = datetime.strptime(text, "%d %b %Y, %H:%M:%S")
    return naive.replace(tzinfo=config.LOCAL_TZ).astimezone(timezone.utc)


def parse_watch_history(path: Path | None = None) -> list[dict]:
    """Return one row per play that carries a resolvable video ID."""
    path = path or config.WATCH_HISTORY_HTML
    if not path.exists():
        raise FileNotFoundError(
            str(path) + " not found - extract the Takeout zip into data/raw/ first."
        )

    raw = path.read_text(encoding="utf-8", errors="replace")
    cells = raw.split(CELL_DELIM)[1:]  # element 0 is the document preamble

    rows: list[dict] = []
    for cell in cells:
        body_match = RE_BODY.search(cell)
        if not body_match:
            continue
        body = body_match.group(1)

        watch = RE_WATCH.search(body)
        if not watch:
            # Community posts, ad impressions, Shorts-tool usage - not plays.
            continue
        host, video_id, title_fragment = watch.groups()

        title = _clean(title_fragment)
        # For a deleted or private video Takeout prints the URL as the link
        # text. That is not a title.
        if title and title.startswith("https://"):
            title = None

        channel_id = None
        channel = None
        chan = RE_CHANNEL.search(body)
        if chan:
            channel_id = chan.group(1)
            channel = _clean(chan.group(2))

        stamp = RE_TIMESTAMP.search(body)
        if not stamp:
            continue

        rows.append(
            {
                "video_id": video_id,
                "title": title,
                "channel": channel,
                "channel_id": channel_id,
                "watched_at": parse_timestamp(stamp.group(1)).isoformat(),
                "source": "music.youtube.com" if host == "music" else "youtube.com",
            }
        )
    return rows


def parse_playlists(path: Path | None = None) -> list[dict]:
    """Playlist metadata. Note the timestamps here are not trustworthy."""
    path = path or config.PLAYLISTS_CSV
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [
            {
                "playlist_id": r.get("Playlist ID", "").strip(),
                "title": r.get("Playlist title (original)", "").strip() or None,
                "description": r.get("Playlist description (original)", "").strip() or None,
                "created_at": r.get("Playlist create timestamp", "").strip() or None,
                "updated_at": r.get("Playlist update timestamp", "").strip() or None,
                "visibility": r.get("Playlist visibility", "").strip() or None,
            }
            for r in csv.DictReader(fh)
            if r.get("Playlist ID", "").strip()
        ]


def parse_playlist_tracks(directory: Path | None = None) -> list[dict]:
    """Per-playlist CSVs carry only `Video ID` plus a timestamp - no titles."""
    directory = directory or config.PLAYLISTS_DIR
    if not directory.exists():
        return []
    rows: list[dict] = []
    for csv_path in sorted(directory.glob("*.csv")):
        if csv_path.name == "playlists.csv":
            continue
        # "Chill videos.csv" -> "Chill"
        name = re.sub(r"\s+videos$", "", csv_path.stem)
        with csv_path.open(encoding="utf-8", newline="") as fh:
            for position, r in enumerate(csv.DictReader(fh)):
                vid = (r.get("Video ID") or "").strip()
                if not vid:
                    continue
                rows.append(
                    {
                        "playlist_name": name,
                        "video_id": vid,
                        "added_at": (r.get("Playlist video creation timestamp") or "").strip()
                        or None,
                        "position": position,
                    }
                )
    return rows


def parse_library_songs(path: Path | None = None) -> list[dict]:
    """The only Takeout source with real artist metadata (239 rows)."""
    path = path or config.LIBRARY_SONGS_CSV
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            vid = (r.get("Video ID") or "").strip()
            if not vid:
                continue
            artists = [(r.get("Artist Name " + str(i)) or "").strip() for i in range(1, 8)]
            rows.append(
                {
                    "video_id": vid,
                    "song_title": (r.get("Song Title") or "").strip() or None,
                    "album_title": (r.get("Album Title") or "").strip() or None,
                    "artists": "; ".join(a for a in artists if a) or None,
                }
            )
    return rows


def load_all(db_path: Path | None = None) -> dict:
    """Parse every Takeout source and replace the Phase-1 tables.

    `video_metadata` and `quota_log` are deliberately left untouched - they cost
    API quota and are not derivable from the export.
    """
    conn = connect(db_path)
    counts: dict = {}
    try:
        with conn:
            plays = parse_watch_history()
            conn.execute("DELETE FROM plays")
            conn.executemany(
                "INSERT OR IGNORE INTO plays "
                "(video_id, title, channel, channel_id, watched_at, source) "
                "VALUES (:video_id, :title, :channel, :channel_id, :watched_at, :source)",
                plays,
            )

            playlists = parse_playlists()
            conn.execute("DELETE FROM playlists")
            conn.executemany(
                "INSERT OR REPLACE INTO playlists "
                "(playlist_id, title, description, created_at, updated_at, visibility) "
                "VALUES (:playlist_id, :title, :description, :created_at, "
                ":updated_at, :visibility)",
                playlists,
            )

            tracks = parse_playlist_tracks()
            conn.execute("DELETE FROM playlist_tracks")
            conn.executemany(
                "INSERT INTO playlist_tracks "
                "(playlist_name, video_id, added_at, position) "
                "VALUES (:playlist_name, :video_id, :added_at, :position)",
                tracks,
            )

            songs = parse_library_songs()
            conn.execute("DELETE FROM library_songs")
            conn.executemany(
                "INSERT OR REPLACE INTO library_songs "
                "(video_id, song_title, album_title, artists) "
                "VALUES (:video_id, :song_title, :album_title, :artists)",
                songs,
            )

        for table in ("plays", "playlists", "playlist_tracks", "library_songs"):
            counts[table] = table_count(conn, table)
        counts["unique_videos"] = conn.execute(
            "SELECT COUNT(DISTINCT video_id) FROM plays"
        ).fetchone()[0]
        counts["plays_without_channel"] = conn.execute(
            "SELECT COUNT(*) FROM plays WHERE channel IS NULL"
        ).fetchone()[0]
        counts["playlist_unique_videos"] = conn.execute(
            "SELECT COUNT(DISTINCT video_id) FROM playlist_tracks"
        ).fetchone()[0]
        counts["_span"] = conn.execute(
            "SELECT MIN(watched_at), MAX(watched_at) FROM plays"
        ).fetchone()
    finally:
        conn.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    counts = load_all()
    span = counts.pop("_span")
    print("Parsed Takeout ->", config.DB_PATH)
    for key, value in counts.items():
        print("  {:<24}{:>9,}".format(key, value))
    if span and span[0]:
        lo = datetime.fromisoformat(span[0])
        hi = datetime.fromisoformat(span[1])
        print(
            "  {:<24}{} -> {}  ({} days)".format(
                "date range", lo.date(), hi.date(), (hi - lo).days
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
