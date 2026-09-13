"""Phase 4 write-back. No test here touches the real API.

A 50-track playlist costs 2,551 units - about a third of a day's quota - so the
behaviours that matter are the ones that stop a mistake being expensive:
dry-run by default, resume after interruption, never a silent partial, and a
write that verifies itself.
"""
import pandas as pd
import pytest

from fake_youtube import (
    FakeHttpError,
    FakeYouTube,
    quota_exceeded,
    transient_error,
    unauthorized,
)
from taste_engine import writer
from taste_engine.db import connect
from taste_engine.quota import QuotaLedger


def make_tracks(n=5, start=0):
    return pd.DataFrame(
        {
            "video_id": [f"vid{i:08d}abc"[:11] for i in range(start, start + n)],
            "title": [f"Track {i}" for i in range(start, start + n)],
            "score": [1.0 - i * 0.01 for i in range(start, start + n)],
            "cluster": [3] * n,
            "cluster_name": ["Test Artist"] * n,
        }
    )


@pytest.fixture
def env(tmp_path):
    conn = connect(tmp_path / "w.db")
    ledger = QuotaLedger(conn, daily_cap=8_000)
    yield conn, ledger, FakeYouTube()
    conn.close()


class TestCostModel:
    def test_fifty_track_playlist_costs_2551(self, env):
        conn, _, _ = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(50))
        assert p["units"] == 50 + 50 * 50 + 1 == 2551

    def test_cost_is_itemised(self, env):
        conn, _, _ = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(10))
        assert p["breakdown"] == {
            "playlists.insert": 50,
            "playlistItems.insert": 500,
            "playlistItems.list": 1,
        }

    def test_a_days_cap_cannot_absorb_four_playlists(self, env):
        """The constraint that makes dry-run and resume necessary."""
        _, ledger, _ = env
        assert 2551 * 4 > ledger.daily_cap


class TestDryRun:
    def test_spends_no_quota(self, env):
        conn, ledger, _ = env
        writer.plan(conn, cluster=3, tracks=make_tracks(20))
        assert ledger.spent() == 0

    def test_creates_no_rows(self, env):
        conn, _, _ = env
        writer.plan(conn, cluster=3, tracks=make_tracks(20))
        assert writer.list_written(conn).empty

    def test_renders_every_track_and_the_total(self, env):
        conn, ledger, _ = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(4))
        text = writer.render_plan(p, ledger)
        assert "DRY RUN" in text
        for title in ("Track 0", "Track 1", "Track 2", "Track 3"):
            assert title in text
        assert "251" in text  # 50 + 4x50 + 1

    def test_refuses_when_it_would_exceed_remaining_quota(self, tmp_path):
        conn = connect(tmp_path / "w.db")
        ledger = QuotaLedger(conn, daily_cap=100)
        p = writer.plan(conn, cluster=3, tracks=make_tracks(30))
        assert "REFUSED" in writer.render_plan(p, ledger)
        conn.close()


class TestCommit:
    def test_writes_every_track(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(5))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["written"] == 5
        assert report["status"] == "complete"
        assert api.items_store[report["playlist_id"]] == list(p["tracks"].video_id)

    def test_new_playlists_are_private(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        assert api.playlists_store[report["playlist_id"]]["privacyStatus"] == "private"

    def test_quota_spent_matches_the_plan(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(5))
        writer.execute_write(conn, api, ledger, p)
        assert ledger.spent() == p["units"]

    def test_preserves_ranking_order(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(6))
        report = writer.execute_write(conn, api, ledger, p)
        assert api.items_store[report["playlist_id"]] == list(p["tracks"].video_id)


class TestResume:
    def test_interruption_leaves_a_partial_not_a_crash(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(fail_inserts_after=3)
        p = writer.plan(conn, cluster=3, tracks=make_tracks(8))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["status"] == "partial"
        assert report["written"] == 3
        assert report["stopped"]
        assert writer.get_row(conn, report["row_id"])["status"] == "partial"

    def test_resume_writes_exactly_the_missing_tracks(self, env):
        conn, ledger, _ = env
        tracks = make_tracks(8)
        p = writer.plan(conn, cluster=3, tracks=tracks)

        first = writer.execute_write(conn, FakeYouTube(fail_inserts_after=3), ledger, p)
        assert first["written"] == 3

        api2 = FakeYouTube()
        api2.playlists_store[first["playlist_id"]] = {"privacyStatus": "private"}
        api2.items_store[first["playlist_id"]] = list(tracks.video_id[:3])

        second = writer.execute_write(conn, api2, ledger, p, row_id=first["row_id"])
        assert second["skipped_already_present"] == 3
        assert api2.insert_calls == 5, "resume must insert only the missing five"
        assert second["written"] == 8
        assert second["status"] == "complete"

    def test_resume_does_not_duplicate(self, env):
        conn, ledger, _ = env
        tracks = make_tracks(6)
        p = writer.plan(conn, cluster=3, tracks=tracks)
        first = writer.execute_write(conn, FakeYouTube(fail_inserts_after=2), ledger, p)

        api2 = FakeYouTube()
        api2.playlists_store[first["playlist_id"]] = {"privacyStatus": "private"}
        api2.items_store[first["playlist_id"]] = list(tracks.video_id[:2])
        writer.execute_write(conn, api2, ledger, p, row_id=first["row_id"])

        stored = api2.items_store[first["playlist_id"]]
        assert len(stored) == len(set(stored)) == 6

    def test_resume_does_not_recreate_the_playlist(self, env):
        conn, ledger, _ = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(5))
        first = writer.execute_write(conn, FakeYouTube(fail_inserts_after=1), ledger, p)
        api2 = FakeYouTube()
        api2.playlists_store[first["playlist_id"]] = {"privacyStatus": "private"}
        api2.items_store[first["playlist_id"]] = list(p["tracks"].video_id[:1])
        writer.execute_write(conn, api2, ledger, p, row_id=first["row_id"])
        assert api2.created == 0


class TestIdempotence:
    def test_rerunning_a_completed_write_is_a_no_op(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(4))
        first = writer.execute_write(conn, api, ledger, p)
        spent_after_first = ledger.spent()

        again = writer.execute_write(conn, api, ledger, p, row_id=first["row_id"])
        assert again["skipped_already_present"] == 4
        assert again["written"] == 4
        # Only the 1-unit verification is paid again.
        assert ledger.spent() == spent_after_first + 1


class TestQuotaEnforcement:
    def test_stops_before_breaching_the_cap(self, tmp_path):
        conn = connect(tmp_path / "w.db")
        # 50 create + 3x50 inserts = 200; the fourth insert would breach.
        ledger = QuotaLedger(conn, daily_cap=200)
        api = FakeYouTube()
        p = writer.plan(conn, cluster=3, tracks=make_tracks(8))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["status"] == "partial"
        assert report["written"] == 3
        assert ledger.spent() <= 200
        conn.close()

    def test_refuses_to_create_without_quota_for_it(self, tmp_path):
        conn = connect(tmp_path / "w.db")
        ledger = QuotaLedger(conn, daily_cap=60)
        ledger.charge("videos.list", 30)
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        with pytest.raises(writer.WriteBlocked, match="quota"):
            writer.execute_write(conn, FakeYouTube(), ledger, p)
        conn.close()

    def test_a_partial_write_is_recorded_not_lost(self, tmp_path):
        conn = connect(tmp_path / "w.db")
        ledger = QuotaLedger(conn, daily_cap=200)
        p = writer.plan(conn, cluster=3, tracks=make_tracks(8))
        report = writer.execute_write(conn, FakeYouTube(), ledger, p)
        rows = writer.list_written(conn)
        assert len(rows) == 1
        assert rows.iloc[0]["status"] == "partial"
        assert rows.iloc[0]["written"] == 3
        assert len(writer.already_written(conn, report["row_id"])) == 3
        conn.close()


class TestVerification:
    def test_confirms_a_good_write(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(5))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["verified"] == {
            "checked": True, "remote": 5, "expected": 5, "match": True
        }

    def test_detects_and_records_a_mismatch(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(drop_every=3)  # silently loses every third insert
        p = writer.plan(conn, cluster=3, tracks=make_tracks(6))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["verified"]["match"] is False
        assert report["verified"]["remote"] == 4
        assert report["status"] == "mismatch"
        assert writer.get_row(conn, report["row_id"])["status"] == "mismatch"

    def test_costs_one_unit(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        writer.execute_write(conn, api, ledger, p)
        assert ledger.summary()["by_method"]["playlistItems.list"] == 1

    def test_pages_through_long_playlists(self, env):
        conn, ledger, api = env
        pid = api._create_playlist(body={"snippet": {}, "status": {}})["id"]
        api.items_store[pid] = [f"v{i}" for i in range(120)]
        conn.execute(
            "INSERT INTO written_playlists (id, playlist_id, title, status, "
            "planned, written) VALUES (1, ?, 't', 'complete', 120, 120)", (pid,)
        )
        conn.commit()
        assert writer.verify(conn, api, ledger, 1)["remote"] == 120


class TestRollback:
    def test_deletes_the_remote_playlist_and_its_tracks(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(4))
        report = writer.execute_write(conn, api, ledger, p)

        result = writer.rollback(conn, api, ledger, report["row_id"])
        assert result["deleted_remote"] is True
        assert report["playlist_id"] in api.deleted
        assert writer.already_written(conn, report["row_id"]) == set()
        assert writer.get_row(conn, report["row_id"])["status"] == "rolled_back"

    def test_costs_fifty_units(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        before = ledger.spent()
        writer.rollback(conn, api, ledger, report["row_id"])
        assert ledger.spent() - before == 50

    def test_a_rolled_back_row_cannot_be_resumed(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)
        writer.rollback(conn, api, ledger, report["row_id"])
        with pytest.raises(writer.WriteBlocked, match="rolled back"):
            writer.execute_write(conn, api, ledger, p, row_id=report["row_id"])


class TestBookkeeping:
    def test_unknown_row_is_refused(self, env):
        conn, _, _ = env
        with pytest.raises(writer.WriteBlocked, match="no written_playlists row"):
            writer.get_row(conn, 999)

    def test_listing_reports_status_and_counts(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        writer.execute_write(conn, api, ledger, p)
        row = writer.list_written(conn).iloc[0]
        assert (row["status"], row["written"], row["planned"]) == ("complete", 3, 3)
        assert row["privacy"] == "private"

    def test_empty_cluster_is_refused(self, env, monkeypatch):
        conn, _, _ = env
        # Stub the pipeline: this asserts the guard, not the recommender.
        monkeypatch.setattr(
            "taste_engine.recommend.build", lambda *a, **k: make_tracks(3)
        )
        # mode="top" isolates the cluster filter from the favourites filter.
        with pytest.raises(writer.WriteBlocked, match="no tracks"):
            writer.plan(conn, cluster=99, limit=5, mode="top")

    def test_a_present_cluster_is_selected(self, env, monkeypatch):
        conn, _, _ = env
        monkeypatch.setattr(
            "taste_engine.recommend.build", lambda *a, **k: make_tracks(9)
        )
        p = writer.plan(conn, cluster=3, limit=4, mode="top")
        assert p["count"] == 4
        assert p["title"] == "taste-engine: Test Artist"


class TestModes:
    """The playlist must be drawn from the pool the evaluation scores.

    The README argues rediscovery is the task worth measuring. If the writer
    ranked everything, the product would ship *replay* - the trivial task the
    most-played baseline wins - while the README reported a rediscovery number.
    That gap is what `--mode rediscover` closes, and it closes it by calling
    the same `recommend.favourites` the hold-out uses.
    """

    @pytest.fixture
    def catalogue(self):
        return pd.DataFrame({
            "video_id": [f"v{i:02d}aaaaaaa"[:11] for i in range(12)],
            "title": [f"Song {i}" for i in range(12)],
            "channel": ["A - Topic"] * 12,
            "play_count": [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5, 1],
            "score": [9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.9, 0.8, 0.7],
            "cluster": [1] * 12,
            "cluster_name": ["A"] * 12,
            "days_since": [1] * 12,
        })

    def test_rediscover_is_the_default(self, env, monkeypatch, catalogue):
        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        assert writer.plan(conn, cluster=1, limit=3, exclude_top=4)["mode"] ==             "rediscover"

    def test_rediscover_drops_the_most_played(self, env, monkeypatch, catalogue):
        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        picks = writer.plan(conn, cluster=1, limit=3, exclude_top=4)["tracks"]
        assert set(picks["play_count"]) & {100, 90, 80, 70} == set()
        assert picks["play_count"].tolist() == [60, 50, 40]

    def test_top_mode_keeps_them(self, env, monkeypatch, catalogue):
        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        picks = writer.plan(conn, cluster=1, limit=3, mode="top")["tracks"]
        assert picks["play_count"].tolist() == [100, 90, 80]

    def test_the_two_modes_differ(self, env, monkeypatch, catalogue):
        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        a = writer.plan(conn, cluster=1, limit=5, exclude_top=4)["tracks"]["video_id"]
        b = writer.plan(conn, cluster=1, limit=5, mode="top")["tracks"]["video_id"]
        assert list(a) != list(b)

    def test_exclusion_matches_the_evaluations_hold_out(self, env, monkeypatch,
                                                        catalogue):
        """The whole point: same function, same set, no drift."""
        from taste_engine.recommend import favourites

        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        held_out = favourites(catalogue, 4)
        picks = writer.plan(conn, cluster=1, limit=8, exclude_top=4)["tracks"]
        assert not set(picks["video_id"]) & held_out

    def test_exclusion_is_global_not_per_cluster(self, env, monkeypatch):
        """The eval removes the library's favourites, not each cluster's."""
        conn, _, _ = env
        frame = pd.DataFrame({
            "video_id": [f"v{i:02d}bbbbbbb"[:11] for i in range(6)],
            "title": [f"S{i}" for i in range(6)],
            "channel": ["A - Topic"] * 6,
            "play_count": [100, 90, 5, 4, 3, 2],
            "score": [9.0, 8.0, 3.0, 2.0, 1.0, 0.5],
            "cluster": [1, 1, 2, 2, 2, 2],
            "cluster_name": ["A", "A", "B", "B", "B", "B"],
            "days_since": [1] * 6,
        })
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: frame)
        # Cluster 2's own top tracks are not favourites of the library, so
        # excluding the global top 2 must leave cluster 2 untouched.
        picks = writer.plan(conn, cluster=2, limit=4, exclude_top=2)["tracks"]
        assert len(picks) == 4

    def test_mode_is_recorded_in_the_plan_and_title(self, env, monkeypatch, catalogue):
        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        p = writer.plan(conn, cluster=1, limit=3, exclude_top=4)
        assert p["excluded_favourites"] == 4
        assert "rediscover" in p["title"]
        assert "excluded" in p["description"]

    def test_render_shows_the_mode(self, env, monkeypatch, catalogue):
        conn, ledger, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        text = writer.render_plan(writer.plan(conn, cluster=1, limit=3,
                                              exclude_top=4), ledger)
        assert "rediscover" in text and "matching the eval" in text

    def test_unknown_mode_is_refused(self, env):
        conn, _, _ = env
        with pytest.raises(writer.WriteBlocked, match="unknown mode"):
            writer.plan(conn, cluster=1, limit=3, mode="vibes",
                        tracks=make_tracks(3))

    def test_a_small_cluster_cannot_do_rediscover(self, env, monkeypatch):
        """A real constraint, not a corner case.

        `--mode rediscover` removes the library's 50 most-played songs, so a
        cluster with fewer than ~50 songs of its own can be emptied outright.
        The writer says which of the two filters emptied it.
        """
        conn, _, _ = env
        small = pd.DataFrame({
            "video_id": [f"v{i:02d}ccccccc"[:11] for i in range(5)],
            "title": [f"S{i}" for i in range(5)],
            "channel": ["A - Topic"] * 5,
            "play_count": [50, 40, 30, 20, 10],
            "score": [5.0, 4.0, 3.0, 2.0, 1.0],
            "cluster": [7] * 5, "cluster_name": ["A"] * 5, "days_since": [1] * 5,
        })
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: small)
        with pytest.raises(writer.WriteBlocked, match="after excluding favourites"):
            writer.plan(conn, cluster=7, limit=3)   # default exclude_top=50

    def test_a_cluster_emptied_by_exclusion_says_so(self, env, monkeypatch,
                                                    catalogue):
        conn, _, _ = env
        monkeypatch.setattr("taste_engine.recommend.build", lambda *a, **k: catalogue)
        with pytest.raises(writer.WriteBlocked, match="after excluding favourites"):
            writer.plan(conn, cluster=1, limit=3, exclude_top=12)


class TestRetry:
    """The first live write (2026-09-13) hit a 409 SERVICE_UNAVAILABLE on the
    second insert - an unhandled traceback, because every error path before
    this only ever modelled 403 quotaExceeded. These pin the fix: transient
    statuses retry with backoff and are charged per attempt; 403 quotaExceeded
    and 401 never retry; and no failure, retryable or not, predicted or not,
    ever leaves execute_write() without a persisted, resumable partial.
    """

    @pytest.fixture(autouse=True)
    def no_real_sleep(self, monkeypatch):
        self.slept = []
        monkeypatch.setattr(writer.time, "sleep", lambda s: self.slept.append(s))

    def test_retries_409_then_succeeds(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={1: transient_error(409)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["status"] == "complete"
        assert report["written"] == 3
        assert api.insert_calls == 4  # 1 failed attempt + 3 successful inserts
        assert len(self.slept) == 1

    def test_retries_503_then_succeeds(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={2: transient_error(503)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["status"] == "complete"
        assert report["written"] == 3
        assert api.insert_calls == 4

    def test_backoff_doubles_and_stays_within_jitter_bounds(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={i: transient_error(503) for i in range(1, 6)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(1))
        writer.execute_write(conn, api, ledger, p, verify_after=False)
        assert len(self.slept) == 4  # 5 attempts -> 4 waits between them
        for wait, nominal in zip(self.slept, [1.0, 2.0, 4.0, 8.0]):
            assert nominal * 0.5 <= wait <= nominal * 1.5

    def test_each_retry_attempt_is_separately_charged(self, env):
        """Google bills a request whether or not it succeeds (quota.py's own
        rule); a retry that skipped charging its failed attempts would
        under-count real spend - the direction that risks the real cap."""
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={1: transient_error(409)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(1))
        writer.execute_write(conn, api, ledger, p, verify_after=False)
        assert ledger.summary()["by_method"]["playlistItems.insert"] == 100

    def test_exhausts_five_attempts_then_leaves_a_resumable_partial(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={i: transient_error(503) for i in range(1, 6)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)

        assert report["status"] == "partial"
        assert report["written"] == 0
        assert report["stopped"]
        assert api.insert_calls == 5
        assert writer.get_row(conn, report["row_id"])["status"] == "partial"

        api2 = FakeYouTube()
        api2.playlists_store[report["playlist_id"]] = {"privacyStatus": "private"}
        api2.items_store[report["playlist_id"]] = []
        resumed = writer.execute_write(conn, api2, ledger, p, row_id=report["row_id"])
        assert resumed["written"] == 3
        assert resumed["status"] == "complete"

    def test_arbitrary_unexpected_exception_leaves_a_resumable_partial(self, env):
        """Not shaped like an HttpError at all - the general guarantee, not a
        quota-specific one."""
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={2: ValueError("boom - wholly unpredicted")})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)

        assert report["status"] == "partial"
        assert report["written"] == 1
        assert "boom" in report["stopped"]
        assert api.insert_calls == 2  # not retried: unrecognised failures don't wait
        assert writer.get_row(conn, report["row_id"])["status"] == "partial"

        api2 = FakeYouTube()
        api2.playlists_store[report["playlist_id"]] = {"privacyStatus": "private"}
        api2.items_store[report["playlist_id"]] = list(p["tracks"].video_id[:1])
        resumed = writer.execute_write(conn, api2, ledger, p, row_id=report["row_id"])
        assert resumed["written"] == 3
        assert resumed["status"] == "complete"

    def test_never_retries_quota_exceeded(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={1: quota_exceeded()})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)
        assert api.insert_calls == 1
        assert not self.slept
        assert "quotaExceeded" in report["stopped"]
        assert report["status"] == "partial"

    def test_never_retries_401(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(insert_errors={1: unauthorized()})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        assert api.insert_calls == 1
        assert not self.slept
        assert report["status"] == "partial"

    def test_create_retries_a_503_then_succeeds(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(create_errors={1: transient_error(503)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["status"] == "complete"
        assert api.created == 2  # one failed attempt + one success

    def test_verify_retries_a_502_then_succeeds(self, env):
        conn, ledger, _ = env
        api = FakeYouTube(list_errors={1: transient_error(502)})
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        assert report["verified"] == {
            "checked": True, "remote": 2, "expected": 2, "match": True
        }
        assert api.list_calls == 2

    def test_rollback_retries_a_409_then_succeeds(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        api.delete_errors = {1: transient_error(409)}
        result = writer.rollback(conn, api, ledger, report["row_id"])
        assert result["deleted_remote"] is True
        assert api.delete_calls == 2

    def test_rollback_treats_404_as_already_gone(self, env):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        api.delete_errors = {1: FakeHttpError(404, "playlistNotFound")}
        result = writer.rollback(conn, api, ledger, report["row_id"])
        assert result["deleted_remote"] is False
        assert result["already_absent"] is True
        assert writer.get_row(conn, report["row_id"])["status"] == "rolled_back"
