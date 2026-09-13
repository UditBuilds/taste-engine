"""Assertions on the parsed dataset.

These are regression guards, not exploration. Every expected value was measured
from the real Takeout export; if the parser silently breaks (a markup change, a
bad regex, a timezone slip) these are what catch it.

Tolerances exist because the brief's reference figures were counted by a
slightly different prototype. Anything outside them means the parser changed
behaviour, not that the data drifted - the export is a frozen file.
"""
from datetime import datetime

import pytest

from taste_engine import config

# Reference figures from the build brief.
EXPECTED_PLAYS = 40_617
EXPECTED_UNIQUE_VIDEOS = 30_438
EXPECTED_NO_CHANNEL = 6_652
TOLERANCE = 100

EXPECTED_PLAYLIST_ROWS = 11_475
EXPECTED_PLAYLIST_UNIQUE = 8_457
EXPECTED_LIBRARY_SONGS = 239
EXPECTED_SPAN_DAYS = 363
EXPECTED_FIRST_DAY = "2025-09-14"
EXPECTED_LAST_DAY = "2026-09-13"


def _one(db, sql):
    return db.execute(sql).fetchone()[0]


class TestPlays:
    def test_row_count(self, db):
        got = _one(db, "SELECT COUNT(*) FROM plays")
        assert abs(got - EXPECTED_PLAYS) <= TOLERANCE, (
            f"parsed {got:,} plays, expected {EXPECTED_PLAYS:,} +/- {TOLERANCE}"
        )

    def test_unique_video_count(self, db):
        got = _one(db, "SELECT COUNT(DISTINCT video_id) FROM plays")
        assert abs(got - EXPECTED_UNIQUE_VIDEOS) <= TOLERANCE

    def test_date_span_is_363_days(self, db):
        lo, hi = db.execute("SELECT MIN(watched_at), MAX(watched_at) FROM plays").fetchone()
        span = (datetime.fromisoformat(hi) - datetime.fromisoformat(lo)).days
        assert span == EXPECTED_SPAN_DAYS

    def test_history_window_matches_the_12_month_autodelete(self, db):
        """Nothing before Sept 2025 exists and nothing after the export date."""
        lo, hi = db.execute("SELECT MIN(watched_at), MAX(watched_at) FROM plays").fetchone()
        assert datetime.fromisoformat(lo).date().isoformat() == EXPECTED_FIRST_DAY
        assert datetime.fromisoformat(hi).date().isoformat() == EXPECTED_LAST_DAY

    def test_every_video_id_is_well_formed(self, db):
        bad = _one(db, "SELECT COUNT(*) FROM plays WHERE LENGTH(video_id) != 11")
        assert bad == 0

    def test_timestamps_are_utc_iso8601(self, db):
        offsets = {
            r[0] for r in db.execute("SELECT DISTINCT SUBSTR(watched_at, -6) FROM plays")
        }
        assert offsets == {"+00:00"}, f"non-UTC offsets stored: {offsets}"

    def test_source_is_one_of_two_hosts(self, db):
        sources = {r[0] for r in db.execute("SELECT DISTINCT source FROM plays")}
        assert sources == {"youtube.com", "music.youtube.com"}

    def test_music_youtube_plays_are_a_meaningful_slice(self, db):
        """music.youtube.com is one of the strongest music signals we have."""
        got = _one(db, "SELECT COUNT(*) FROM plays WHERE source = 'music.youtube.com'")
        assert 5_000 <= got <= 7_000, got

    def test_rows_without_a_channel(self, db):
        """Deleted/private videos and Shorts: kept raw, excluded from training."""
        got = _one(db, "SELECT COUNT(*) FROM plays WHERE channel IS NULL")
        assert abs(got - EXPECTED_NO_CHANNEL) <= TOLERANCE

    def test_a_url_is_never_stored_as_a_title(self, db):
        got = _one(db, "SELECT COUNT(*) FROM plays WHERE title LIKE 'https://%'")
        assert got == 0

    def test_no_duplicate_play_events(self, db):
        got = _one(
            db,
            "SELECT COUNT(*) FROM (SELECT video_id, watched_at FROM plays "
            "GROUP BY video_id, watched_at HAVING COUNT(*) > 1)",
        )
        assert got == 0


class TestPlaylists:
    def test_track_rows_are_kept_verbatim(self, db):
        """All 11,475 source rows, duplicates included - see README."""
        assert _one(db, "SELECT COUNT(*) FROM playlist_tracks") == EXPECTED_PLAYLIST_ROWS

    def test_unique_videos_across_playlists(self, db):
        got = _one(db, "SELECT COUNT(DISTINCT video_id) FROM playlist_tracks")
        assert got == EXPECTED_PLAYLIST_UNIQUE

    def test_duplicates_are_preserved_not_deduped(self, db):
        rows = _one(db, "SELECT COUNT(*) FROM playlist_tracks")
        pairs = _one(
            db,
            "SELECT COUNT(*) FROM (SELECT 1 FROM playlist_tracks "
            "GROUP BY playlist_name, video_id)",
        )
        assert rows - pairs == 430

    def test_forty_eight_playlists_have_exported_tracks(self, db):
        got = _one(db, "SELECT COUNT(DISTINCT playlist_name) FROM playlist_tracks")
        assert got == 48

    def test_playlist_metadata_row_count(self, db):
        """58 playlists have metadata; only 48 have an exported track CSV."""
        assert _one(db, "SELECT COUNT(*) FROM playlists") == 58

    def test_creation_dates_collapse_onto_two_bulk_import_days(self, db):
        """Playlist creation time is an import artefact, not user behaviour.

        53 of 58 playlists claim to have been created on 2026-03-11 or
        2026-03-17. That is a bulk transfer into the account, so creation order
        carries no information about when the user actually liked anything.
        Asserted rather than merely documented so nothing downstream starts
        treating playlist recency as a signal.
        """
        top_two = db.execute(
            "SELECT SUBSTR(created_at, 1, 10) d, COUNT(*) n FROM playlists "
            "WHERE created_at IS NOT NULL GROUP BY d ORDER BY n DESC LIMIT 2"
        ).fetchall()
        assert [r[0] for r in top_two] == ["2026-03-11", "2026-03-17"]
        assert sum(r[1] for r in top_two) >= 50

    def test_update_timestamps_collapse_onto_the_export_date(self, db):
        """The export itself restamped nearly every playlist."""
        got = _one(
            db,
            "SELECT COUNT(*) FROM playlists "
            f"WHERE SUBSTR(updated_at, 1, 10) = '{EXPECTED_LAST_DAY}'",
        )
        assert got >= 55

    def test_playlist_titles_are_not_unique(self, db):
        """Why playlist_tracks is keyed by name and the mapping is lossy.

        The per-playlist CSVs are named after the playlist title, but titles
        repeat ('Jim' appears three times). A track CSV therefore cannot be
        mapped back to a single playlist id - the export loses that link.
        """
        collisions = _one(
            db,
            "SELECT COUNT(*) FROM (SELECT title FROM playlists "
            "GROUP BY title HAVING COUNT(*) > 1)",
        )
        assert collisions > 0


class TestLibrary:
    def test_library_song_count(self, db):
        assert _one(db, "SELECT COUNT(*) FROM library_songs") == EXPECTED_LIBRARY_SONGS

    def test_library_songs_carry_artist_metadata(self, db):
        """The only Takeout source with real artist names."""
        got = _one(db, "SELECT COUNT(*) FROM library_songs WHERE artists IS NOT NULL")
        assert got >= EXPECTED_LIBRARY_SONGS * 0.9

    def test_multi_artist_rows_are_joined(self, db):
        row = db.execute(
            "SELECT artists FROM library_songs WHERE artists LIKE '%; %' LIMIT 1"
        ).fetchone()
        assert row is not None and "; " in row[0]


class TestSchemaContract:
    @pytest.mark.parametrize(
        "table", ["plays", "playlists", "playlist_tracks", "library_songs",
                  "video_metadata", "quota_log", "written_playlists", "written_tracks"]
    )
    def test_table_exists(self, db, table):
        db.execute(f"SELECT 1 FROM {table} LIMIT 1")

    def test_config_paths_point_inside_the_repo(self):
        assert config.DB_PATH.is_relative_to(config.REPO_ROOT)
        assert config.TAKEOUT_DIR.is_relative_to(config.RAW_DIR)
