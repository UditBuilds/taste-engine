"""Dormancy signal maths (briefs: dormancy signal measurement, 2026-09-15).

Pure functions are tested against synthetic frames, independent of the real
dataset - date-window boundary maths especially, since an off-by-one there
would be silent (see `plays_in_window`'s docstring). Canonical-key plumbing is
checked directly against the real database (session-scoped `db` fixture,
skipped if it has not been built) because it has to agree with
`canonical.collapse()`'s own grouping on real titles/channels/durations, which
a hand-built synthetic frame cannot exercise honestly.
"""
from __future__ import annotations

import pandas as pd
import pytest

from taste_engine import config, dormancy as d

UTC = "UTC"


def ts(iso: str) -> pd.Timestamp:
    return pd.Timestamp(iso, tz=UTC)


AS_OF = ts("2026-09-15T12:00:00")


# --- date-window maths -------------------------------------------------

class TestPlaysInWindowBoundary:
    def test_none_is_zero(self):
        assert d.plays_in_window(None, AS_OF, 30) == 0

    def test_empty_series_is_zero(self):
        assert d.plays_in_window(pd.Series([], dtype="datetime64[ns, UTC]"), AS_OF, 30) == 0

    def test_play_exactly_on_the_lower_boundary_counts(self):
        """as_of - 30 days, to the second, is inside the window (`>=`)."""
        times = pd.Series([AS_OF - pd.Timedelta(days=30)])
        assert d.plays_in_window(times, AS_OF, 30) == 1

    def test_play_one_second_before_the_boundary_does_not_count(self):
        times = pd.Series([AS_OF - pd.Timedelta(days=30) - pd.Timedelta(seconds=1)])
        assert d.plays_in_window(times, AS_OF, 30) == 0

    def test_play_exactly_at_as_of_counts(self):
        times = pd.Series([AS_OF])
        assert d.plays_in_window(times, AS_OF, 30) == 1

    def test_play_after_as_of_does_not_count(self):
        """Not expected on real data (as_of is "now"), but the bound is
        real - the upper end must not silently include it."""
        times = pd.Series([AS_OF + pd.Timedelta(seconds=1)])
        assert d.plays_in_window(times, AS_OF, 30) == 0

    def test_mixed_series_counts_only_the_ones_inside(self):
        times = pd.Series([
            AS_OF - pd.Timedelta(days=5),    # in
            AS_OF - pd.Timedelta(days=29),   # in
            AS_OF - pd.Timedelta(days=31),   # out
            AS_OF - pd.Timedelta(days=180),  # out
        ])
        assert d.plays_in_window(times, AS_OF, 30) == 2

    def test_windows_are_independent_not_cumulative_by_construction(self):
        """plays_last_90d must count the 30d plays too - it is not the
        30-90 day band alone."""
        times = pd.Series([AS_OF - pd.Timedelta(days=5), AS_OF - pd.Timedelta(days=60)])
        assert d.plays_in_window(times, AS_OF, 30) == 1
        assert d.plays_in_window(times, AS_OF, 90) == 2


class TestMonthsActive:
    def test_no_plays_is_zero(self):
        assert d.months_active(None) == 0.0
        assert d.months_active(pd.Series([], dtype="datetime64[ns, UTC]")) == 0.0

    def test_a_single_play_has_zero_span(self):
        assert d.months_active(pd.Series([AS_OF])) == 0.0

    def test_one_month_apart(self):
        times = pd.Series([AS_OF - pd.Timedelta(days=30.44), AS_OF])
        assert d.months_active(times) == pytest.approx(1.0, abs=0.05)

    def test_order_does_not_matter(self):
        times = pd.Series([AS_OF, AS_OF - pd.Timedelta(days=60.88)])
        assert d.months_active(times) == pytest.approx(2.0, abs=0.05)


# --- separation (threshold-free) ----------------------------------------

class TestRankSeparation:
    def test_perfect_separation_one_direction(self):
        values = pd.Series([1, 2, 3, 10, 11, 12])
        is_forgotten = pd.Series([True, True, True, False, False, False])
        out = d.rank_separation(values, is_forgotten)
        assert out["auc"] == pytest.approx(0.0)

    def test_perfect_separation_other_direction(self):
        values = pd.Series([10, 11, 12, 1, 2, 3])
        is_forgotten = pd.Series([True, True, True, False, False, False])
        out = d.rank_separation(values, is_forgotten)
        assert out["auc"] == pytest.approx(1.0)

    def test_identical_values_give_no_separation(self):
        values = pd.Series([5, 5, 5, 5])
        is_forgotten = pd.Series([True, True, False, False])
        out = d.rank_separation(values, is_forgotten)
        assert out["auc"] == pytest.approx(0.5)

    def test_no_positive_group_is_nan(self):
        values = pd.Series([1, 2, 3])
        is_forgotten = pd.Series([False, False, False])
        out = d.rank_separation(values, is_forgotten)
        assert out["auc"] != out["auc"]  # NaN

    def test_pair_count_is_n_forgotten_times_n_rotation(self):
        values = pd.Series([1, 2, 3, 4, 5])
        is_forgotten = pd.Series([True, True, False, False, False])
        out = d.rank_separation(values, is_forgotten)
        assert out["pairs"] == 2 * 3


class TestSeparationSummary:
    def _table(self) -> pd.DataFrame:
        # 4 rows, all nine SIGNAL_COLUMNS populated; every column except
        # "current_score" is deliberately mixed (auc == 0.5, no separation)
        # so it is the unique cleanest separator, not just a tie-break winner.
        return pd.DataFrame(
            {
                "label": ["forgotten", "forgotten", "rotation", "rotation"],
                "days_since_last_play": [10, 12, 11, 9],
                "plays_last_30d": [0, 1, 1, 0],
                "plays_last_90d": [1, 2, 2, 1],
                "plays_last_180d": [2, 3, 1, 4],
                "plays_lifetime": [3, 5, 2, 6],
                "share_of_cluster_plays": [0.02, 0.05, 0.01, 0.06],
                "score_percentile_within_cluster": [20, 80, 10, 90],
                "current_score": [0.1, 0.2, 0.8, 0.9],
                "months_active": [1, 2, 1, 2],
            }
        )

    def test_best_separator_is_ranked_first(self):
        out = d.separation_summary(self._table(), positive_labels={"forgotten"})
        assert out.iloc[0]["signal"] == "current_score"
        assert out.iloc[0]["separation"] == pytest.approx(1.0)

    def test_every_signal_column_is_present_exactly_once(self):
        out = d.separation_summary(self._table(), positive_labels={"forgotten"})
        assert sorted(out["signal"]) == sorted(d.SIGNAL_COLUMNS)

    def test_n_counts_match_the_label_split(self):
        out = d.separation_summary(self._table(), positive_labels={"forgotten"})
        row = out[out["signal"] == "current_score"].iloc[0]
        assert row["n_positive"] == 2
        assert row["n_other"] == 2


# --- distributions / window-played counts --------------------------------

class TestDistribution:
    def test_empty(self):
        out = d.distribution(pd.Series([], dtype="float64"))
        assert out == {"n": 0, "min": None, "median": None, "mean": None, "max": None}

    def test_basic_stats(self):
        out = d.distribution(pd.Series([1.0, 2.0, 3.0, 4.0]))
        assert out["n"] == 4
        assert out["min"] == 1.0
        assert out["max"] == 4.0
        assert out["mean"] == 2.5


class TestWindowPlayedCounts:
    def test_counts_tracks_with_at_least_one_play(self):
        shipped = pd.DataFrame(
            {"plays_last_30d": [0, 1, 2], "plays_last_90d": [1, 1, 2], "plays_last_180d": [1, 1, 3]}
        )
        out = d.window_played_counts(shipped)
        assert out == {30: 2, 90: 3, 180: 3}


# --- qualifying_clusters (FLOOR check) ------------------------------------

class TestQualifyingClusters:
    def test_only_clusters_meeting_the_floor_qualify(self, monkeypatch):
        monkeypatch.setattr(config, "MIN_CLUSTER_NATIVE", 2)
        monkeypatch.setattr(config, "MIN_SCORE", 0.5)
        frame = pd.DataFrame(
            {
                "video_id": [f"v{i}" for i in range(6)],
                "cluster": [0, 0, 1, 1, 1, -1],
                "cluster_name": ["A", "A", "B", "B", "B", "(outliers)"],
                "score": [0.9, 0.1, 0.9, 0.9, 0.1, 0.9],
            }
        )
        out = d.qualifying_clusters(frame)
        # cluster 0: only 1 eligible (score>=0.5) - below floor of 2.
        # cluster 1: 2 eligible - meets floor.
        # cluster -1 (noise) is never a candidate regardless of score.
        assert out["cluster"].tolist() == [1]
        assert out.iloc[0]["native_eligible"] == 2
        assert out.iloc[0]["cluster_pool_size"] == 3

    def test_empty_frame_gives_empty_result(self, monkeypatch):
        monkeypatch.setattr(config, "MIN_CLUSTER_NATIVE", 2)
        frame = pd.DataFrame(columns=["video_id", "cluster", "cluster_name", "score"])
        out = d.qualifying_clusters(frame)
        assert out.empty


# --- track_signal_table ---------------------------------------------------

class TestTrackSignalTable:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "video_id": ["a", "b", "c"],
                "title": ["A", "B", "C"],
                "days_since": [5.0, 10.0, 15.0],
                "play_count": [10, 5, 5],
                "score": [2.0, 1.0, 1.0],
                "cluster": [0, 0, 0],
            }
        )

    def test_share_and_percentile_are_relative_to_the_cluster_pool(self):
        frame = self._frame()
        key_of = pd.Series({"a": "ka", "b": "kb", "c": "kc"})
        plays_by_key = {
            "ka": pd.Series([AS_OF - pd.Timedelta(days=1)] * 10),
            "kb": pd.Series([AS_OF - pd.Timedelta(days=1)] * 5),
            "kc": pd.Series([AS_OF - pd.Timedelta(days=1)] * 5),
        }
        out = d.track_signal_table(["a"], frame, key_of, plays_by_key, AS_OF)
        row = out.iloc[0]
        assert row["plays_lifetime"] == 10
        assert row["share_of_cluster_plays"] == pytest.approx(10 / 20)
        # "a" has the top score in its cluster of 3 -> 100th percentile.
        assert row["score_percentile_within_cluster"] == pytest.approx(100.0)
        assert row["n_plays_recorded"] == 10

    def test_missing_video_id_raises_rather_than_producing_nans(self):
        frame = self._frame()
        with pytest.raises(ValueError, match="not found"):
            d.track_signal_table(["does-not-exist"], frame, pd.Series(dtype=object), {}, AS_OF)

    def test_labels_default_to_unlabelled(self):
        frame = self._frame()
        key_of = pd.Series({"a": "ka"})
        out = d.track_signal_table(["a"], frame, key_of, {}, AS_OF)
        assert out.iloc[0]["label"] == "unlabelled"

    def test_explicit_cluster_pool_overrides_the_default(self):
        """Regression for the share_of_cluster_plays pre-/post-exclusion
        question (report Methodology): passing a narrower pool changes the
        denominator, not just the default's own cluster lookup."""
        frame = self._frame()
        key_of = pd.Series({"a": "ka"})
        narrow_pool = frame[frame["video_id"] != "b"]  # drop b's 5 plays from the pool
        out = d.track_signal_table(["a"], frame, key_of, {}, AS_OF, cluster_pool=narrow_pool)
        # The implementation rounds to 4dp for report readability; compare
        # against the same rounding rather than the raw fraction.
        assert out.iloc[0]["share_of_cluster_plays"] == pytest.approx(round(10 / 15, 4))


# --- integration against the real database (skipped if not built) --------

class TestAgainstRealDatabase:
    def test_canonical_key_plumbing_matches_collapsed_play_count(self, db):
        """PIXELATED KISSES (Joji, video_id HYXGY67fATk) - pinned against the
        static local database, same pattern as test_dataset_facts.py. If
        canonical_key_of's replication of canonical.collapse() ever drifts,
        this is the number that would silently go wrong first (advisor
        review, 2026-09-15): plays_lifetime (collapse()'s summed play_count)
        must equal the raw count of watched_at rows pooled by
        plays_by_canonical_key across every constituent upload.
        """
        key_of = d.canonical_key_of(db)
        plays_by_key = d.plays_by_canonical_key(db, key_of)
        vid = "HYXGY67fATk"
        assert vid in key_of.index
        key = key_of[vid]
        assert len(plays_by_key[key]) == 23

    def test_shipped_video_ids_match_the_known_joji_write(self, db):
        ids = d.shipped_video_ids(db, 5)
        assert len(ids) == 12
        assert ids[0] == "HYXGY67fATk"  # rank 1, PIXELATED KISSES
        assert ids[-1] == "ujriV3vkC9w"  # rank 12, Afterthought

    def test_qualifying_clusters_includes_the_three_labelled_ones(self, db):
        """Documents today's measured state (data is static/gitignored, so
        this pins a fact rather than asserting a general property) - Joji,
        Lil Baby/Lil Peep/Chris Brown and T-Series must all clear FLOOR,
        since all three already shipped a live playlist under this exact
        rule.

        Resolved by name, not a hardcoded cluster id: cluster ids are
        reassigned whenever the input set changes (CLAUDE.md - "Cluster ids
        are not identifiers"), the same idiom `dormancy_probe.find_cluster`
        and `writer.plan`'s `--cluster-name` matching already use. This
        test originally pinned ids 4/11/35 directly and broke - not
        flakily, but deterministically - the moment `embed.py`'s
        `normalise_title` NaN guard changed `title_artist` mode's
        clustering (38 -> 37 clusters); the three artists' clusters still
        qualify, just under different ids (5/12/36) - see
        reports/normalise_title_fix.md.
        """
        as_of = AS_OF
        _, frame_excl, _ = d.build_frames(db, as_of=as_of)
        qualifying = d.qualifying_clusters(frame_excl)
        names = qualifying["name"].fillna("")
        for artist in ("Joji", "T-Series", "Lil Baby"):
            assert names.str.contains(artist, case=False, regex=False).any(), (
                f"no qualifying cluster matched {artist!r}: {sorted(names)}"
            )
