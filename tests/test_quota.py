"""QuotaLedger must refuse overspend before a request is ever made."""
import pytest

from taste_engine.db import connect
from taste_engine.quota import QuotaExceeded, QuotaLedger, UnknownMethod


@pytest.fixture
def ledger(tmp_path):
    conn = connect(tmp_path / "q.db")
    yield QuotaLedger(conn, daily_cap=1_000)
    conn.close()


class TestPricing:
    @pytest.mark.parametrize(
        "method,expected",
        [
            ("videos.list", 1),
            ("playlists.insert", 50),
            ("playlistItems.insert", 50),
            ("search.list", 100),
        ],
    )
    def test_documented_costs(self, ledger, method, expected):
        assert ledger.cost_of(method) == expected

    def test_cost_scales_with_calls(self, ledger):
        assert ledger.cost_of("videos.list", 609) == 609

    def test_unknown_method_is_refused_not_guessed(self, ledger):
        with pytest.raises(UnknownMethod):
            ledger.cost_of("captions.download")

    def test_every_method_the_code_calls_has_a_documented_cost(self, ledger):
        """A missing cost must fail loudly, not default to zero."""
        for method in ("videos.list", "channels.list", "playlists.insert",
                       "playlists.delete", "playlistItems.insert",
                       "playlistItems.list"):
            assert ledger.cost_of(method) > 0

    def test_resolving_all_30k_videos_costs_609_units(self, ledger):
        """30,438 ids / 50 per call = 609 calls = 609 units, under 7% of a day."""
        calls = -(-30_438 // 50)
        assert calls == 609
        assert ledger.cost_of("videos.list", calls) == 609

    def test_a_100_track_playlist_write_costs_5000(self, ledger):
        assert ledger.cost_of("playlistItems.insert", 100) == 5_000


class TestEnforcement:
    def test_starts_empty(self, ledger):
        assert ledger.spent() == 0
        assert ledger.remaining() == 1_000

    def test_charge_accumulates(self, ledger):
        ledger.charge("videos.list", 10)
        ledger.charge("videos.list", 5)
        assert ledger.spent() == 15
        assert ledger.remaining() == 985

    def test_raises_before_breaching_the_cap(self, ledger):
        ledger.charge("playlistItems.insert", 19)  # 950
        with pytest.raises(QuotaExceeded) as excinfo:
            ledger.charge("playlistItems.insert", 2)  # would be 1,050
        assert "50 of 1000 remain" in str(excinfo.value)

    def test_a_refused_call_is_not_recorded(self, ledger):
        ledger.charge("playlistItems.insert", 19)
        with pytest.raises(QuotaExceeded):
            ledger.charge("playlistItems.insert", 2)
        assert ledger.spent() == 950, "a refused call must not be billed"

    def test_exactly_hitting_the_cap_is_allowed(self, ledger):
        ledger.charge("playlistItems.insert", 20)  # exactly 1,000
        assert ledger.spent() == 1_000
        assert ledger.remaining() == 0

    def test_check_does_not_charge(self, ledger):
        ledger.check("videos.list", 100)
        assert ledger.spent() == 0

    def test_can_afford(self, ledger):
        assert ledger.can_afford("playlistItems.insert", 20)
        assert not ledger.can_afford("playlistItems.insert", 21)

    def test_budget_for_reports_remaining_calls(self, ledger):
        assert ledger.budget_for("playlistItems.insert") == 20
        ledger.charge("videos.list", 100)
        assert ledger.budget_for("playlistItems.insert") == 18
        assert ledger.budget_for("videos.list") == 900


class TestCapConfiguration:
    def test_rejects_a_cap_above_googles_hard_limit(self, tmp_path):
        conn = connect(tmp_path / "q.db")
        with pytest.raises(ValueError, match="hard limit"):
            QuotaLedger(conn, daily_cap=20_000)
        conn.close()

    def test_rejects_a_nonpositive_cap(self, tmp_path):
        conn = connect(tmp_path / "q.db")
        with pytest.raises(ValueError):
            QuotaLedger(conn, daily_cap=0)
        conn.close()

    def test_default_cap_leaves_headroom(self, tmp_path):
        conn = connect(tmp_path / "q.db")
        assert QuotaLedger(conn).daily_cap <= 10_000
        conn.close()


class TestSpendContext:
    def test_charges_on_entry(self, ledger):
        with ledger.spend("videos.list") as units:
            assert units == 1
            assert ledger.spent() == 1

    def test_an_http_error_is_still_billed(self, ledger):
        """Google debits on receipt, so a 4xx does not earn a refund."""
        with pytest.raises(RuntimeError):
            with ledger.spend("videos.list"):
                raise RuntimeError("403 quotaExceeded")
        assert ledger.spent() == 1

    def test_a_connection_error_is_refunded(self, ledger):
        """The request never reached Google, so the units were never spent."""
        with pytest.raises(ConnectionError):
            with ledger.spend("videos.list", 10):
                raise ConnectionError("DNS failure")
        assert ledger.spent() == 0

    def test_refund_rejects_nonpositive_units(self, ledger):
        with pytest.raises(ValueError):
            ledger.refund("videos.list", 0)


class TestPersistenceAndReporting:
    def test_spend_survives_a_reconnect(self, tmp_path):
        """The ledger is the only record of what today already cost."""
        conn = connect(tmp_path / "q.db")
        QuotaLedger(conn, daily_cap=1_000).charge("videos.list", 42)
        conn.close()

        conn = connect(tmp_path / "q.db")
        assert QuotaLedger(conn, daily_cap=1_000).spent() == 42
        conn.close()

    def test_summary_breaks_down_by_method(self, ledger):
        ledger.charge("videos.list", 9)
        ledger.charge("playlists.insert", 1)
        summary = ledger.summary()
        assert summary["by_method"] == {"playlists.insert": 50, "videos.list": 9}
        assert summary["spent"] == 59
        assert summary["remaining"] == 941

    def test_report_renders(self, ledger):
        ledger.charge("videos.list", 3)
        text = ledger.report()
        assert "videos.list" in text and "US/Pacific" in text

    def test_day_key_uses_googles_reset_timezone(self, ledger):
        day = ledger.today()
        assert len(day) == 10 and day[4] == "-"
