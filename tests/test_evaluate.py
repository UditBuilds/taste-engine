"""Recommendation strategies and hold-out metrics.

The most important test here is `test_training_frame_excludes_the_test_window`.
Everything else measures quality; that one is the reason a quality number means
anything at all.
"""
import pandas as pd
import pytest

from taste_engine.evaluate import (
    _window_end,
    evaluate,
    main,
    ndcg_at_k,
    precision_at_k,
    split_frames,
    sweep,
)
from taste_engine.recommend import STRATEGIES, by_cluster_diverse, recommend

SPLIT = "2026-06-01"


@pytest.fixture
def catalogue():
    return pd.DataFrame(
        {
            "video_id": [f"v{i}" for i in range(12)],
            "play_count": [50, 40, 30, 25, 20, 18, 15, 12, 10, 8, 5, 2],
            "days_since": [200, 150, 1, 100, 2, 90, 3, 80, 4, 70, 5, 60],
            "score": [1.0, 0.9, 2.5, 0.8, 2.4, 0.7, 2.3, 0.6, 2.2, 0.5, 2.1, 0.4],
            "cluster": [0, 0, 0, 1, 1, 1, 2, 2, 2, -1, -1, -1],
            "cluster_name": ["A"] * 3 + ["B"] * 3 + ["C"] * 3 + ["(outliers)"] * 3,
            "title": [f"t{i}" for i in range(12)],
        }
    )


class TestMetrics:
    def test_precision_counts_hits_over_k(self):
        assert precision_at_k(["a", "b", "c", "d"], {"a", "c"}, 4) == 0.5

    def test_precision_only_looks_at_the_first_k(self):
        assert precision_at_k(["a", "b", "c"], {"c"}, 2) == 0.0

    def test_precision_of_nothing_is_zero(self):
        assert precision_at_k([], {"a"}, 0) == 0.0

    def test_ndcg_is_one_for_a_perfect_ordering(self):
        relevance = {"a": 5.0, "b": 3.0, "c": 1.0}
        assert ndcg_at_k(["a", "b", "c"], relevance, 3) == pytest.approx(1.0)

    def test_ndcg_punishes_a_reversed_ordering(self):
        relevance = {"a": 5.0, "b": 3.0, "c": 1.0}
        assert ndcg_at_k(["c", "b", "a"], relevance, 3) < 1.0

    def test_ndcg_sees_position_where_precision_cannot(self):
        """Both orderings have precision 1.0; only nDCG separates them."""
        relevance = {"a": 10.0, "b": 1.0}
        good = ndcg_at_k(["a", "b"], relevance, 2)
        bad = ndcg_at_k(["b", "a"], relevance, 2)
        assert precision_at_k(["a", "b"], set(relevance), 2) == \
            precision_at_k(["b", "a"], set(relevance), 2)
        assert good > bad

    def test_ndcg_of_irrelevant_picks_is_zero(self):
        assert ndcg_at_k(["x", "y"], {"a": 1.0}, 2) == 0.0


class TestStrategies:
    @pytest.mark.parametrize("name", sorted(STRATEGIES))
    def test_returns_exactly_k(self, catalogue, name):
        assert len(recommend(catalogue, n=5, strategy=name)) == 5

    @pytest.mark.parametrize("name", sorted(STRATEGIES))
    def test_returns_no_duplicates(self, catalogue, name):
        picks = recommend(catalogue, n=8, strategy=name)
        assert picks["video_id"].is_unique

    def test_most_played_is_ordered_by_raw_count(self, catalogue):
        picks = recommend(catalogue, n=3, strategy="most_played")
        assert picks["play_count"].tolist() == [50, 40, 30]

    def test_score_is_ordered_by_score(self, catalogue):
        picks = recommend(catalogue, n=3, strategy="score")
        assert picks["score"].tolist() == [2.5, 2.4, 2.3]

    def test_recency_prefers_the_freshest(self, catalogue):
        picks = recommend(catalogue, n=3, strategy="recency")
        assert picks["days_since"].tolist() == [1, 2, 3]

    def test_unknown_strategy_is_refused(self, catalogue):
        with pytest.raises(KeyError, match="unknown strategy"):
            recommend(catalogue, strategy="vibes")

    def test_asking_for_more_than_exists_returns_everything(self, catalogue):
        assert len(recommend(catalogue, n=500, strategy="score")) == len(catalogue)


class TestClusterDiversity:
    def test_spreads_across_clusters(self, catalogue):
        """Twenty Travis Scott tracks is a good prediction and a bad playlist."""
        picks = by_cluster_diverse(catalogue, n=3)
        assert picks["cluster"].nunique() == 3

    def test_beats_pure_score_on_variety(self, catalogue):
        """Counting real clusters only - the -1 outlier bucket is not a mood."""
        def moods(picks):
            return picks.loc[picks["cluster"] >= 0, "cluster"].nunique()

        diverse = moods(by_cluster_diverse(catalogue, n=6))
        greedy = moods(recommend(catalogue, n=6, strategy="score"))
        assert diverse >= greedy

    def test_falls_back_when_there_are_no_clusters(self, catalogue):
        picks = by_cluster_diverse(catalogue.drop(columns=["cluster"]), n=4)
        assert len(picks) == 4

    def test_tops_up_from_outliers_when_clusters_run_dry(self, catalogue):
        picks = by_cluster_diverse(catalogue, n=11, per_cluster=2)
        assert len(picks) == 11
        assert picks["video_id"].is_unique


class TestNoLeakage:
    def test_training_frame_excludes_the_test_window(self, db):
        """If this fails, every other number in the README is meaningless."""
        train, test = split_frames(db, SPLIT, cluster=False)
        latest = db.execute(
            "SELECT MAX(watched_at) FROM plays WHERE video_id IN ({})".format(
                ",".join("?" * len(train))
            ),
            train["video_id"].tolist(),
        ).fetchone()[0]
        # A track may appear in both windows; what must not leak is its plays.
        assert train["play_count"].sum() == db.execute(
            "SELECT COUNT(*) FROM plays WHERE watched_at < ?", (SPLIT,)
        ).fetchone()[0] - _non_music_plays(db, end=SPLIT)
        assert latest is not None

    def test_test_frame_starts_at_the_split(self, db):
        _, test = split_frames(db, SPLIT, cluster=False)
        assert test["first_played"].min() >= SPLIT

    def test_windows_do_not_overlap(self, db):
        train, test = split_frames(db, SPLIT, cluster=False)
        assert train["last_played"].max() < SPLIT <= test["first_played"].min()


class TestPlaylistAsOf:
    """B2 - `in_playlist` must not see a playlist addition from after an
    evaluation split. `classify.py`'s `in_playlist` previously had no date
    condition at all - see reports/eval_verification.md (A2). Every test
    here fails with a TypeError against the pre-fix signatures, which took
    no `playlist_as_of` argument at all.
    """

    def test_default_is_undated(self, db):
        """Explicit None must reproduce every other caller's behaviour -
        the live write path is not supposed to change."""
        from taste_engine.classify import classify_heuristic

        default = classify_heuristic(db)
        explicit_none = classify_heuristic(db, playlist_as_of=None)
        pd.testing.assert_series_equal(
            default["in_playlist"], explicit_none["in_playlist"]
        )

    def test_an_impossibly_early_cutoff_empties_in_playlist(self, db):
        """Every real playlist_tracks.added_at postdates this - proves the
        date condition is actually applied, not silently ignored."""
        from taste_engine.classify import classify_heuristic

        dated = classify_heuristic(db, playlist_as_of="1900-01-01")
        assert not dated["in_playlist"].any()

    def test_a_cutoff_at_or_after_every_add_matches_undated(self, db):
        from taste_engine.classify import classify_heuristic

        latest_add = db.execute(
            "SELECT MAX(added_at) FROM playlist_tracks"
        ).fetchone()[0]
        dated = classify_heuristic(db, playlist_as_of=latest_add)
        undated = classify_heuristic(db)
        pd.testing.assert_series_equal(dated["in_playlist"], undated["in_playlist"])

    def test_cutoff_excludes_a_track_added_only_after_it(self, db):
        """The exact scenario A2 describes: a real track that is both a
        playlist member and has been played must lose `in_playlist` once
        the cutoff predates its addition, while staying `in_playlist`
        undated. Not a hardcoded video id - picked from live data so this
        does not rot across a re-parse."""
        from taste_engine.classify import classify_heuristic

        row = db.execute(
            "SELECT DISTINCT pt.video_id FROM playlist_tracks pt "
            "JOIN plays p ON p.video_id = pt.video_id LIMIT 1"
        ).fetchone()
        video_id = row[0]
        cutoff = "2000-01-01"  # predates this dataset's earliest playlist add
        dated = classify_heuristic(db, playlist_as_of=cutoff).set_index("video_id")
        undated = classify_heuristic(db).set_index("video_id")
        assert bool(undated.loc[video_id, "in_playlist"]) is True
        assert bool(dated.loc[video_id, "in_playlist"]) is False

    def test_scored_tracks_threads_playlist_as_of_to_classify(self, db):
        """An impossible cutoff can only remove is_music tracks, never add
        one - in_playlist only ever widens eligibility, never narrows it."""
        from taste_engine.score import scored_tracks

        dated = scored_tracks(db, playlist_as_of="1900-01-01", canonical=False)
        undated = scored_tracks(db, canonical=False)
        assert set(dated["video_id"]) <= set(undated["video_id"])
        assert len(dated) < len(undated)

    def test_split_frames_dates_the_training_frame_only(self, db):
        """The train/test asymmetry is deliberate (A2: dating `test` would
        censor the ground truth on no evidence of a real leak there) - pin
        it down so a future edit cannot silently drop `playlist_as_of` from
        `train` or add it to `test` without a test failing."""
        from taste_engine.score import scored_tracks

        train, test = split_frames(db, SPLIT, cluster=False)
        expected_train = scored_tracks(
            db, start=None, end=SPLIT, as_of=SPLIT, canonical=True,
            playlist_as_of=SPLIT,
        )
        expected_test = scored_tracks(
            db, start=SPLIT, end=None, as_of=None, canonical=True,
        )
        pd.testing.assert_frame_equal(
            train.reset_index(drop=True), expected_train.reset_index(drop=True)
        )
        pd.testing.assert_frame_equal(
            test.reset_index(drop=True), expected_test.reset_index(drop=True)
        )


class TestWindowEnd:
    """--test-end pins an absolute window bound - briefs/pin_evaluation.md."""

    def test_test_end_is_returned_verbatim(self):
        assert _window_end("2026-06-01", None, "2026-07-01") == "2026-07-01"

    def test_test_days_arithmetic_is_unchanged(self):
        assert _window_end("2026-06-01", 30, None) == "2026-07-01"

    def test_neither_bound_is_open_ended(self):
        assert _window_end("2026-06-01", None, None) is None

    def test_both_bounds_together_is_refused(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            _window_end("2026-06-01", 30, "2026-07-01")


class TestTestEnd:
    """test_end must produce the identical window test_days already computes
    for the same span, and thread cleanly through the single-split callers."""

    def test_test_end_matches_equivalent_test_days(self, db):
        by_days = evaluate(db, split_date="2026-06-01", test_days=30)
        by_end = evaluate(db, split_date="2026-06-01", test_end="2026-07-01")
        assert by_days["test_tracks"] == by_end["test_tracks"]
        assert by_days["test_plays"] == by_end["test_plays"]
        assert by_days["train_tracks"] == by_end["train_tracks"]
        pd.testing.assert_frame_equal(
            by_days["results"].reset_index(drop=True),
            by_end["results"].reset_index(drop=True),
        )

    def test_report_records_test_end_not_a_recomputed_test_days(self, db):
        report = evaluate(db, split_date="2026-06-01", test_end="2026-07-01")
        assert report["test_end"] == "2026-07-01"
        assert report["test_days"] is None

    def test_sweep_accepts_test_end(self, db):
        result = sweep(db, split_date="2026-06-01", test_end="2026-07-01", half_lives=[14])
        assert len(result) == 1


class TestTestEndCLI:
    """The multi-split flags (--rediscovery/--both/--sweep-splits/--robustness)
    each sweep their own hardcoded split list; an absolute --test-end would
    apply a different, inconsistent window to every one of them, so the CLI
    refuses the combination outright rather than silently misapplying it.
    --sweep-half-life is deliberately not in that list: it holds --split
    fixed and only varies half-life, so it stays coherent with --test-end.
    """

    def test_test_days_and_test_end_together_is_refused(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--test-days", "30", "--test-end", "2026-07-01"])
        assert exc.value.code == 2
        assert "not allowed with argument --test-days" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "flag", ["--rediscovery", "--both", "--sweep-splits", "--robustness"]
    )
    def test_test_end_with_a_multi_split_flag_is_refused(self, flag, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--test-end", "2026-07-01", flag])
        assert exc.value.code == 2
        assert "cannot be applied across" in capsys.readouterr().err

    def test_test_end_alone_is_allowed(self, db, capsys):
        """`db` is requested only to skip cleanly without data/taste.db; main()
        opens its own connection via config.DB_PATH, the same database."""
        assert main(["--test-end", "2026-07-01"]) == 0
        assert "to 2026-07-01" in capsys.readouterr().out


def _non_music_plays(db, end):
    """Plays in the window belonging to videos the classifier excluded."""
    from taste_engine.classify import classify

    labels = classify(db)
    music = set(labels.loc[labels["is_music"], "video_id"])
    rows = db.execute(
        "SELECT video_id, COUNT(*) FROM plays WHERE watched_at < ? GROUP BY video_id",
        (end,),
    ).fetchall()
    return sum(c for v, c in rows if v not in music)
