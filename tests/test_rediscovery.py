"""The rediscovery task - scoring the tracks that are not already favourites.

The replay task is rigged for the baseline by construction: naming the track
someone played 50 times is not a recommendation. These tests pin down the
filtering that makes the harder question measurable.
"""
import pandas as pd
import pytest

from taste_engine.evaluate import (
    evaluate_rediscovery,
    ndcg_at_k,
    rediscovery_split,
)

SPLIT = "2026-06-01"


class TestCandidateFiltering:
    def test_favourites_leave_the_candidate_pool(self, db):
        candidates, _, obvious = rediscovery_split(db, SPLIT, exclude_top=50,
                                                   cluster=False)
        assert len(obvious) == 50
        assert not set(candidates["video_id"]) & obvious

    def test_favourites_leave_the_ground_truth_too(self, db):
        """Otherwise the baseline scores by re-finding what we just excluded."""
        _, truth, obvious = rediscovery_split(db, SPLIT, exclude_top=50,
                                              cluster=False)
        assert not set(truth["video_id"]) & obvious

    def test_the_excluded_set_really_is_the_most_played(self, db):
        candidates, _, obvious = rediscovery_split(db, SPLIT, exclude_top=50,
                                                   cluster=False)
        from taste_engine.score import scored_tracks

        train = scored_tracks(db, end=SPLIT, as_of=SPLIT)
        cutoff = train.nlargest(50, "play_count")["play_count"].min()
        assert candidates["play_count"].max() <= cutoff

    def test_exclusion_shrinks_the_pool(self, db):
        wide, _, _ = rediscovery_split(db, SPLIT, exclude_top=10, cluster=False)
        narrow, _, _ = rediscovery_split(db, SPLIT, exclude_top=200, cluster=False)
        assert len(narrow) < len(wide)

    def test_still_leaves_a_usable_pool(self, db):
        candidates, truth, _ = rediscovery_split(db, SPLIT, exclude_top=50,
                                                 cluster=False)
        assert len(candidates) > 500 and len(truth) > 100


class TestRediscoveryMetrics:
    @pytest.fixture(scope="class")
    def report(self, db):
        return evaluate_rediscovery(db, SPLIT, k=20, exclude_top=50, test_days=30)

    def test_reports_every_strategy(self, report):
        assert set(report["results"]["strategy"]) == {
            "most_played", "score", "recency", "cluster_diverse"
        }

    def test_recall_is_bounded_by_the_ceiling(self, report):
        assert (report["results"]["recall@20"] <= report["ceiling"] + 1e-9).all()

    def test_ceiling_reflects_unreachable_truth(self, report):
        """20 picks cannot cover hundreds of reachable tracks."""
        # The report rounds to 4 decimals.
        assert report["ceiling"] == pytest.approx(
            min(20, report["reachable"]) / report["reachable"], abs=1e-4
        )

    def test_hits_and_recall_agree(self, report):
        row = report["results"].iloc[0]
        assert row["recall@20"] == pytest.approx(row["hits"] / report["reachable"], abs=1e-4)

    def test_metrics_are_in_range(self, report):
        for col in ("recall@20", "precision@20", "ndcg@20"):
            assert report["results"][col].between(0, 1).all()

    def test_the_task_is_harder_than_replay(self, db, report):
        """If rediscovery were as easy as replay, it would not be worth having."""
        from taste_engine.evaluate import evaluate

        replay = evaluate(db, SPLIT, k=20, test_days=30)
        replay_base = replay["results"].set_index("strategy").loc[
            "most_played", "precision@20"
        ]
        redis_base = report["results"].set_index("strategy").loc[
            "most_played", "ndcg@20"
        ]
        assert redis_base < replay_base


class TestBaselineIsAValidControl:
    """The baseline must not move when the model's hyperparameter moves.

    It did once: `scored_tracks` returns rows ordered by `score`, so tied play
    counts at the top-50 cutoff let the half-life decide which tracks were held
    out. The baseline's nDCG drifted 0.270 -> 0.339 across a half-life sweep,
    which would have made every comparison in the README meaningless. These
    tests are why that cannot come back silently.
    """

    def test_excluded_set_is_independent_of_half_life(self, db):
        sets = [
            frozenset(rediscovery_split(db, SPLIT, half_life=hl, cluster=False)[2])
            for hl in (7, 30, 90, 365)
        ]
        assert len(set(sets)) == 1, "the held-out favourites shifted with half-life"

    def test_ground_truth_is_independent_of_half_life(self, db):
        truths = [
            frozenset(rediscovery_split(db, SPLIT, half_life=hl, cluster=False)[1]["video_id"])
            for hl in (7, 90)
        ]
        assert truths[0] == truths[1]

    def test_baseline_picks_are_independent_of_half_life(self, db):
        from taste_engine.recommend import recommend

        picks = []
        for hl in (7, 30, 90, 365):
            candidates, _, _ = rediscovery_split(db, SPLIT, half_life=hl, cluster=False)
            picks.append(tuple(recommend(candidates, n=20, strategy="most_played")["video_id"]))
        assert len(set(picks)) == 1, "most_played is not invariant to half-life"

    def test_baseline_score_is_independent_of_half_life(self, db):
        scores = {
            evaluate_rediscovery(
                db, SPLIT, k=20, half_life=hl, strategies=["most_played"], test_days=30
            )["results"].iloc[0]["ndcg@20"]
            for hl in (7, 30, 90, 365)
        }
        assert len(scores) == 1, f"baseline nDCG moved with half-life: {scores}"


class TestNdcgGrading:
    def test_grades_by_play_volume_not_just_presence(self):
        relevance = {"a": 20.0, "b": 1.0, "c": 1.0}
        assert ndcg_at_k(["a", "b"], relevance, 2) > ndcg_at_k(["b", "c"], relevance, 2)

    def test_more_hits_can_still_score_worse(self):
        """Three low-play hits can lose to one heavy-rotation hit.

        This is why the rediscovery table reports hits and nDCG side by side:
        they genuinely disagree, and the disagreement is informative.
        """
        relevance = {"big": 50.0, "s1": 1.0, "s2": 1.0, "s3": 1.0}
        many_small = ndcg_at_k(["s1", "s2", "s3"], relevance, 3)
        one_big = ndcg_at_k(["big"], relevance, 3)
        assert one_big > many_small


class TestUnderpoweredIsNotTheSameAsNoEffect:
    """A clean sweep of 3 splits cannot reach p < 0.05. Say that, not "no effect".

    The sign test's floor at n is 1/2**n: 0.125 at n=3, 0.031 at n=5. Reporting
    a large, consistent lift as "not significant" without that context reads as
    "no improvement", which is a different and wrong claim.
    """

    def test_p_floor_is_reported(self, db):
        from taste_engine.evaluate import nested_rediscovery

        out = nested_rediscovery(db)
        if out["status"] != "ok":
            import pytest

            pytest.skip("not enough usable splits in this database")
        assert out["p_floor"] == 1 / (2 ** out["n"])

    def test_three_splits_are_flagged_underpowered(self, db):
        from taste_engine.evaluate import nested_rediscovery

        out = nested_rediscovery(db)
        if out["status"] != "ok" or out["n"] != 3:
            import pytest

            pytest.skip("this database does not yield 3 held-out splits")
        assert out["underpowered"] is True
        assert not out["significant"]

    def test_a_clean_sweep_is_not_called_no_improvement(self, db):
        from taste_engine.evaluate import nested_rediscovery

        out = nested_rediscovery(db)
        if out["status"] != "ok" or out["wins"] != out["n"]:
            import pytest

            pytest.skip("not a clean sweep on this database")
        assert "NOT statistically established" in out["verdict"]
        assert "No significant improvement" not in out["verdict"]

    def test_verdict_wording_by_case(self):
        from taste_engine.evaluate import _verdict

        certified = _verdict(wins=5, n=5, p=0.031, p_floor=0.031, base=0.1, score=0.2)
        assert certified.startswith("Improvement over")

        sweep_small_n = _verdict(wins=3, n=3, p=0.125, p_floor=0.125,
                                 base=0.134, score=0.297)
        assert "NOT statistically established" in sweep_small_n
        assert "3/3 splits" in sweep_small_n
        assert "5 held-out splits" in sweep_small_n

        genuinely_null = _verdict(wins=2, n=5, p=0.5, p_floor=0.031,
                                  base=0.20, score=0.19)
        assert genuinely_null.startswith("No significant improvement")
