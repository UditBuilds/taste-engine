"""Last.fm coverage measurement - parsing, retry, and cache tests.

No test here makes a real network call. `fetch_track_tags`/`fetch_artist_tags`
are monkeypatched wherever the orchestration loop (`run_coverage_fetch`) is
exercised; `_parse_toptags` and the retry helpers are tested directly against
strings/exceptions, matching how `tests/fake_youtube.py` shapes writer.py's
failures rather than hitting a real API.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from taste_engine import lastfm
from taste_engine.db import connect


# --- artist/track resolution -------------------------------------------

class TestResolveArtistTrack:
    def test_title_with_leading_artist_dash(self):
        """'Joji - Past Won't Leave My Bed (Official Video)', unresolved channel."""
        artist, track = lastfm.resolve_artist_track(
            "Joji - Past Won't Leave My Bed (Official Video)", "SomeReuploader"
        )
        assert artist == "Joji"
        assert track == "Past Won't Leave My Bed (Official Video)"

    def test_topic_channel_bare_title(self):
        """'PIXELATED KISSES' from a 'Joji - Topic' channel."""
        artist, track = lastfm.resolve_artist_track("PIXELATED KISSES", "Joji - Topic")
        assert artist == "Joji"
        assert track == "PIXELATED KISSES"

    def test_channel_artist_prefix_stripped_from_title(self):
        """Title still carries 'Artist - Track' even though the channel resolves."""
        artist, track = lastfm.resolve_artist_track(
            "Travis Scott - MY EYES", "TravisScottVEVO"
        )
        assert artist == "Travis Scott"
        assert track == "MY EYES"

    def test_no_dash_no_channel_at_all_is_unresolved(self):
        artist, track = lastfm.resolve_artist_track("TBH", None)
        assert artist == ""
        assert track == "TBH"

    def test_no_dash_falls_back_to_raw_channel_name(self):
        """Last resort: classify.py documents real artist-owned channels with
        no Topic/VEVO marker (Don Toliver). Accepted imprecision - a
        compilation channel would be wrong here too, and that shows up
        honestly in the coverage report rather than being hidden."""
        artist, track = lastfm.resolve_artist_track("TBH", "Some Random Uploads")
        assert artist == "Some Random Uploads"
        assert track == "TBH"

    def test_none_title(self):
        artist, track = lastfm.resolve_artist_track(None, None)
        assert artist == ""
        assert track == ""

    def test_nan_channel_and_library_artist_are_treated_as_missing(self):
        """Regression: a pandas NaN is truthy in plain Python, and
        embed.artist_from_channel(nan) returns the *string* 'nan' rather
        than raising or returning "". Both inputs come from pandas columns
        in the real pipeline (9 of 2,918 canonical tracks have a NaN
        channel) and must not be mistaken for a real artist name."""
        nan = float("nan")
        artist, track = lastfm.resolve_artist_track(
            "Travis Scott - MY EYES", nan, library_artist=nan
        )
        assert artist == "Travis Scott"
        assert track == "MY EYES"

    def test_multiple_dashes_splits_on_first(self):
        artist, track = lastfm.resolve_artist_track(
            "Travis Scott - MY EYES - Bonus", "Unresolvable Channel Name"
        )
        assert artist == "Travis Scott"
        assert track == "MY EYES - Bonus"


# --- suffix stripping ----------------------------------------------------

class TestStripReleaseFurniture:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("SLOW DANCING IN THE DARK (Official Video)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK (Official Music Video)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK (Official Audio)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK (Visualizer)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK (Official Visualizer)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK (Lyric Video)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK (Audio)", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK [Official Video]", "SLOW DANCING IN THE DARK"),
            ("SLOW DANCING IN THE DARK [Lyric Video]", "SLOW DANCING IN THE DARK"),
        ],
    )
    def test_brief_suffix_list(self, raw, expected):
        assert lastfm.strip_release_furniture(raw) == expected

    def test_leaves_feat_alone(self):
        """Pass-1 behaviour: feat./ft. must survive so a second pass can measure it."""
        out = lastfm.strip_release_furniture("MY EYES (feat. Kid Cudi) (Official Video)")
        assert "feat" in out.lower()
        assert "Official Video" not in out

    def test_empty_input(self):
        assert lastfm.strip_release_furniture("") == ""
        assert lastfm.strip_release_furniture(None) == ""


class TestStripFeat:
    def test_strips_trailing_feat_clause(self):
        assert lastfm.strip_feat("Double Fantasy ft. Future") == "Double Fantasy"

    def test_strips_featuring_clause(self):
        assert lastfm.strip_feat("Song Name featuring Someone Else") == "Song Name"

    def test_no_feat_clause_unchanged(self):
        assert lastfm.strip_feat("PIXELATED KISSES") == "PIXELATED KISSES"


# --- response parsing (the three API failure modes) ------------------------

class TestParseToptags:
    def test_track_found_with_tags(self):
        body = json.dumps({
            "toptags": {
                "tag": [{"name": "lo-fi", "count": 100, "url": "x"},
                        {"name": "sadboy", "count": 42, "url": "y"}],
                "@attr": {"artist": "Joji", "track": "SLOW DANCING IN THE DARK"},
            }
        })
        result = lastfm._parse_toptags(body, "toptags")
        assert result.status == "ok_tags"
        assert ("lo-fi", 100) in result.tags
        assert ("sadboy", 42) in result.tags

    def test_track_found_zero_tags(self):
        body = json.dumps({"toptags": {"tag": [], "@attr": {"artist": "X", "track": "Y"}}})
        result = lastfm._parse_toptags(body, "toptags")
        assert result.status == "ok_zero_tags"
        assert result.tags == []

    def test_single_tag_comes_back_as_object_not_list(self):
        """Last.fm's JSON collapses a one-item list to a bare object."""
        body = json.dumps({"toptags": {"tag": {"name": "pop", "count": 50}, "@attr": {}}})
        result = lastfm._parse_toptags(body, "toptags")
        assert result.status == "ok_tags"
        assert result.tags == [("pop", 50)]

    def test_track_not_found_error_6(self):
        body = json.dumps({"error": 6, "message": "Track not found"})
        result = lastfm._parse_toptags(body, "toptags")
        assert result.status == "not_found"
        assert "6" in result.error_detail

    def test_other_api_error_is_not_notfound(self):
        body = json.dumps({"error": 10, "message": "Invalid API key"})
        result = lastfm._parse_toptags(body, "toptags")
        assert result.status == "error"

    def test_unparseable_body(self):
        result = lastfm._parse_toptags("not json", "toptags")
        assert result.status == "error"


# --- retry / rate limit ------------------------------------------------

class TestRetry:
    def test_retries_429_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(lastfm.time, "sleep", lambda s: None)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError("url", 429, "rate limited", {}, None)
            return "ok"

        assert lastfm.call_with_retry(flaky) == "ok"
        assert calls["n"] == 3

    def test_does_not_retry_404(self, monkeypatch):
        monkeypatch.setattr(lastfm.time, "sleep", lambda s: None)
        calls = {"n": 0}

        def fails():
            calls["n"] += 1
            raise urllib.error.HTTPError("url", 404, "not found", {}, None)

        with pytest.raises(urllib.error.HTTPError):
            lastfm.call_with_retry(fails)
        assert calls["n"] == 1

    def test_exhausts_attempts_and_raises(self, monkeypatch):
        monkeypatch.setattr(lastfm.time, "sleep", lambda s: None)
        calls = {"n": 0}

        def always_500():
            calls["n"] += 1
            raise urllib.error.HTTPError("url", 500, "server error", {}, None)

        with pytest.raises(urllib.error.HTTPError):
            lastfm.call_with_retry(always_500)
        assert calls["n"] == lastfm.config.WRITE_RETRY_ATTEMPTS

    def test_retryable_statuses(self):
        assert lastfm._is_retryable(urllib.error.HTTPError("u", 429, "m", {}, None))
        assert lastfm._is_retryable(urllib.error.HTTPError("u", 500, "m", {}, None))
        assert lastfm._is_retryable(urllib.error.HTTPError("u", 503, "m", {}, None))
        assert not lastfm._is_retryable(urllib.error.HTTPError("u", 404, "m", {}, None))
        assert not lastfm._is_retryable(urllib.error.HTTPError("u", 403, "m", {}, None))
        assert lastfm._is_retryable(urllib.error.URLError("no route"))


# --- DB cache: hit/miss, including the zero-tag case -----------------------

@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "lastfm_test.db")
    yield c
    c.close()


class TestStoreAndCache:
    def test_store_then_read_back_tags(self, conn):
        result = lastfm.LastfmResult("ok_tags", tags=[("lo-fi", 90), ("sadboy", 40)])
        lastfm._store(conn, "vid1", "track", "feat_kept", "Joji", "Slow Dancing", result)
        rows = conn.execute(
            "SELECT tag, weight FROM track_tags WHERE canonical_id = ?", ("vid1",)
        ).fetchall()
        assert {(r[0], r[1]) for r in rows} == {("lo-fi", 90), ("sadboy", 40)}
        assert lastfm._existing_status(conn, "vid1", "track", "feat_kept") == "ok_tags"

    def test_zero_tags_distinguishable_from_never_fetched(self, conn):
        assert lastfm._existing_status(conn, "vid2", "track", "feat_kept") is None
        lastfm._store(conn, "vid2", "track", "feat_kept", "X", "Y",
                       lastfm.LastfmResult("ok_zero_tags"))
        assert lastfm._existing_status(conn, "vid2", "track", "feat_kept") == "ok_zero_tags"
        assert conn.execute(
            "SELECT COUNT(*) FROM track_tags WHERE canonical_id = ?", ("vid2",)
        ).fetchone()[0] == 0

    def test_variants_do_not_clobber_each_other(self, conn):
        lastfm._store(conn, "vid3", "track", "feat_kept", "X", "Y ft. Z",
                       lastfm.LastfmResult("not_found", error_detail="6: not found"))
        lastfm._store(conn, "vid3", "track", "feat_stripped", "X", "Y",
                       lastfm.LastfmResult("ok_tags", tags=[("pop", 10)]))
        assert lastfm._existing_status(conn, "vid3", "track", "feat_kept") == "not_found"
        assert lastfm._existing_status(conn, "vid3", "track", "feat_stripped") == "ok_tags"


class TestRunCoverageFetch:
    def test_track_found_stores_tags_no_artist_fallback(self, conn, monkeypatch):
        monkeypatch.setattr(lastfm, "canonical_track_pool", lambda c: _pool([
            ("v1", "Joji - Topic", "Joji - Topic"),
        ]))
        monkeypatch.setattr(lastfm, "fetch_track_tags",
                             lambda *a, **k: lastfm.LastfmResult("ok_tags", tags=[("lo-fi", 50)]))
        calls = {"artist": 0}
        monkeypatch.setattr(lastfm, "fetch_artist_tags",
                             lambda *a, **k: calls.__setitem__("artist", calls["artist"] + 1))

        counts = lastfm.run_coverage_fetch(conn, "fakekey")
        assert counts["track_ok_tags"] == 1
        assert calls["artist"] == 0
        assert lastfm._existing_status(conn, "v1", "track", "feat_kept") == "ok_tags"

    def test_track_not_found_falls_back_to_artist(self, conn, monkeypatch):
        monkeypatch.setattr(lastfm, "canonical_track_pool", lambda c: _pool([
            ("v2", "Joji - Topic", "Joji - Topic"),
        ]))
        monkeypatch.setattr(lastfm, "fetch_track_tags",
                             lambda *a, **k: lastfm.LastfmResult("not_found", error_detail="6: x"))
        monkeypatch.setattr(lastfm, "fetch_artist_tags",
                             lambda *a, **k: lastfm.LastfmResult("ok_tags", tags=[("j-pop", 20)]))

        counts = lastfm.run_coverage_fetch(conn, "fakekey")
        assert counts["track_not_found"] == 1
        assert counts["artist_ok_tags"] == 1
        assert lastfm._existing_status(conn, "v2", "artist", "feat_kept") == "ok_tags"

    def test_rerun_skips_already_cached(self, conn, monkeypatch):
        pool = _pool([("v3", "Joji - Topic", "Joji - Topic")])
        monkeypatch.setattr(lastfm, "canonical_track_pool", lambda c: pool)
        fetch_calls = {"n": 0}

        def fake_fetch(*a, **k):
            fetch_calls["n"] += 1
            return lastfm.LastfmResult("ok_tags", tags=[("lo-fi", 1)])

        monkeypatch.setattr(lastfm, "fetch_track_tags", fake_fetch)

        lastfm.run_coverage_fetch(conn, "fakekey")
        assert fetch_calls["n"] == 1

        counts = lastfm.run_coverage_fetch(conn, "fakekey")
        assert fetch_calls["n"] == 1  # not re-fetched
        assert counts["skipped_cached"] == 1

    def test_artist_fallback_deduped_across_tracks(self, conn, monkeypatch):
        """Two canonical tracks, same unresolvable artist: only one real
        artist.getTopTags call should happen."""
        monkeypatch.setattr(lastfm, "canonical_track_pool", lambda c: _pool([
            ("v4", "T-Series Upload One", "T-Series"),
            ("v5", "T-Series Upload Two", "T-Series"),
        ]))
        monkeypatch.setattr(lastfm, "fetch_track_tags",
                             lambda *a, **k: lastfm.LastfmResult("not_found", error_detail="6: x"))
        artist_calls = {"n": 0}

        def fake_artist(*a, **k):
            artist_calls["n"] += 1
            return lastfm.LastfmResult("ok_zero_tags")

        monkeypatch.setattr(lastfm, "fetch_artist_tags", fake_artist)

        counts = lastfm.run_coverage_fetch(conn, "fakekey")
        assert artist_calls["n"] == 1
        assert counts["artist_calls_saved_by_cache"] == 1

    def test_unresolvable_artist_is_not_queried(self, conn, monkeypatch):
        monkeypatch.setattr(lastfm, "canonical_track_pool", lambda c: _pool([
            ("v6", "TBH", None),
        ]))
        called = {"n": 0}

        def fail_if_called(*a, **k):
            called["n"] += 1
            raise AssertionError("should not query Last.fm with no resolvable artist")

        monkeypatch.setattr(lastfm, "fetch_track_tags", fail_if_called)
        counts = lastfm.run_coverage_fetch(conn, "fakekey")
        assert called["n"] == 0
        assert counts["track_unresolved"] == 1
        assert lastfm._existing_status(conn, "v6", "track", "feat_kept") == "unresolved"


def _pool(rows):
    import pandas as pd

    return pd.DataFrame(rows, columns=["canonical_id", "title", "channel"])


# --- auth --------------------------------------------------------------

class TestGetApiKey:
    def test_missing_key_raises_clear_error(self, monkeypatch):
        monkeypatch.delenv("LASTFM_API_KEY", raising=False)
        monkeypatch.setattr(lastfm, "_load_dotenv", lambda: None)
        with pytest.raises(lastfm.MissingLastfmKey, match="LASTFM_API_KEY"):
            lastfm.get_api_key()

    def test_present_key_returned(self, monkeypatch):
        monkeypatch.setattr(lastfm, "_load_dotenv", lambda: None)
        monkeypatch.setenv("LASTFM_API_KEY", "abc123")
        assert lastfm.get_api_key() == "abc123"
