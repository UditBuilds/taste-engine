"""Recommendation strategies and hold-out metrics.

The most important test here is `test_training_frame_excludes_the_test_window`.
Everything else measures quality; that one is the reason a quality number means
anything at all.
"""
import pandas as pd
import pytest

from taste_engine.evaluate import ndcg_at_k, precision_at_k, split_frames
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
