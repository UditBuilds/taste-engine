"""`taste-engine status` / `status --verify` (brief: accumulated defect
fixes, B3, 2026-09-16).

No test file previously existed for cli.py: its other commands
(write/written/clusters) are covered indirectly, against the writer.py
functions they call, in test_writer.py. `status` gets its own coverage
here too, end-to-end through `cli.main`, because --verify's cost
disclosure and exit-code behaviour live in cli.py itself, not in
writer.verify (already covered by test_writer.py::TestVerification).
"""
from __future__ import annotations

import pandas as pd
import pytest

from fake_youtube import FakeYouTube
from taste_engine import cli, writer
from taste_engine.db import connect
from taste_engine.quota import QuotaLedger


def make_tracks(n=3):
    return pd.DataFrame(
        {
            "video_id": [f"vid{i:08d}abc"[:11] for i in range(n)],
            "title": [f"Track {i}" for i in range(n)],
            "score": [1.0 - i * 0.01 for i in range(n)],
            "cluster": [3] * n,
            "cluster_name": ["Test Artist"] * n,
            "genres": [["pop"]] * n,
        }
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """`cli.connect` opens a fresh connection per call, matching real
    behaviour - cmd_status closes its own connection in a `finally`, and a
    shared one would already be closed by the time the fixture's own
    teardown ran."""
    db_path = tmp_path / "cli.db"
    conn = connect(db_path)
    ledger = QuotaLedger(conn, daily_cap=8_000)
    api = FakeYouTube()
    monkeypatch.setattr(cli, "_service", lambda: api)
    monkeypatch.setattr(cli, "connect", lambda: connect(db_path))
    yield conn, ledger, api
    conn.close()


class TestStatusNoVerify:
    def test_reports_no_playlists_yet(self, env, capsys):
        assert cli.main(["status"]) == 0
        assert "No playlists written yet." in capsys.readouterr().out

    def test_lists_a_completed_write(self, env, capsys):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)
        assert cli.main(["status"]) == 0
        out = capsys.readouterr().out
        assert str(report["row_id"]) in out
        assert report["playlist_id"] in out
        assert "complete" in out

    def test_makes_no_api_call(self, env, capsys):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        writer.execute_write(conn, api, ledger, p)
        before = (api.insert_calls, api.created, api.list_calls)
        cli.main(["status"])
        capsys.readouterr()
        assert (api.insert_calls, api.created, api.list_calls) == before


class TestStatusVerify:
    def test_states_the_cost_before_calling(self, env, capsys):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        cli.main(["status", "--verify", str(report["row_id"])])
        out = capsys.readouterr().out
        before_verified = out.split("verified")[0]
        assert "Cost: 1 unit" in before_verified

    def test_confirms_a_matching_write(self, env, capsys):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p)
        assert cli.main(["status", "--verify", str(report["row_id"])]) == 0
        out = capsys.readouterr().out
        assert "OK" in out
        assert "YouTube holds 3, expected 3" in out

    def test_flags_a_mismatch_and_exits_nonzero(self, env, capsys):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(3))
        report = writer.execute_write(conn, api, ledger, p, verify_after=False)
        # Simulate drift discovered after the fact: YouTube's copy lost an item.
        api.items_store[report["playlist_id"]].pop()
        assert cli.main(["status", "--verify", str(report["row_id"])]) == 1
        assert "MISMATCH" in capsys.readouterr().out

    def test_costs_exactly_one_unit(self, env, capsys):
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        spent_before = QuotaLedger(conn).spent()
        cli.main(["status", "--verify", str(report["row_id"])])
        capsys.readouterr()
        assert QuotaLedger(conn).spent() - spent_before == 1

    def test_unknown_row_is_blocked_not_a_crash(self, env, capsys):
        assert cli.main(["status", "--verify", "999"]) == 1
        assert "blocked" in capsys.readouterr().err

    def test_does_not_touch_the_write_path(self, env, capsys):
        """--verify calls writer.verify (already tested against a fake
        YouTube in test_writer.py::TestVerification) and nothing else - no
        insert, no create, no rollback."""
        conn, ledger, api = env
        p = writer.plan(conn, cluster=3, tracks=make_tracks(2))
        report = writer.execute_write(conn, api, ledger, p)
        before = (api.insert_calls, api.created, api.delete_calls)
        cli.main(["status", "--verify", str(report["row_id"])])
        capsys.readouterr()
        assert (api.insert_calls, api.created, api.delete_calls) == before
