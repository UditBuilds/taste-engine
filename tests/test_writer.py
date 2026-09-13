"""Phase 4 write-back. No test here touches the real API.

A 50-track playlist costs 2,551 units - about a third of a day's quota - so the
behaviours that matter are the ones that stop a mistake being expensive:
dry-run by default, resume after interruption, never a silent partial, and a
write that verifies itself.
"""
import pandas as pd
import pytest

from fake_youtube import FakeYouTube
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
        with pytest.raises(writer.WriteBlocked, match="no tracks"):
            writer.plan(conn, cluster=99, limit=5)

    def test_a_present_cluster_is_selected(self, env, monkeypatch):
        conn, _, _ = env
        monkeypatch.setattr(
            "taste_engine.recommend.build", lambda *a, **k: make_tracks(9)
        )
        p = writer.plan(conn, cluster=3, limit=4)
        assert p["count"] == 4
        assert p["title"] == "taste-engine: Test Artist"
