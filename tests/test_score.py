"""Scoring maths, independent of the real dataset."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from taste_engine.score import add_scores, aggregate_plays

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def frame(rows):
    return pd.DataFrame(
        [
            {"video_id": v, "play_count": c, "last_played": (NOW - timedelta(days=d)).isoformat()}
            for v, c, d in rows
        ]
    )


class TestRecencyDecay:
    def test_a_play_today_keeps_full_weight(self):
        out = add_scores(frame([("a", 10, 0)]), as_of=NOW, half_life=30)
        assert out["recency_weight"].iloc[0] == pytest.approx(1.0)

    def test_one_half_life_halves_the_weight(self):
        out = add_scores(frame([("a", 10, 30)]), as_of=NOW, half_life=30)
        assert out["recency_weight"].iloc[0] == pytest.approx(0.5, abs=1e-6)

    def test_two_half_lives_quarter_it(self):
        out = add_scores(frame([("a", 10, 60)]), as_of=NOW, half_life=30)
        assert out["recency_weight"].iloc[0] == pytest.approx(0.25, abs=1e-6)

    def test_a_future_reference_cannot_inflate_the_weight(self):
        """Clamping days_since at zero keeps weights in (0, 1]."""
        out = add_scores(frame([("a", 10, -40)]), as_of=NOW, half_life=30)
        assert out["recency_weight"].iloc[0] <= 1.0

    def test_half_life_must_be_positive(self):
        with pytest.raises(ValueError):
            add_scores(frame([("a", 1, 0)]), as_of=NOW, half_life=0)


class TestLog1pCompression:
    def test_compresses_the_heavy_tail(self):
        """115 plays vs 20 is 5.75x raw but only ~1.57x after log1p.

        The obsessive repeat should win, but not erase everything else.
        """
        out = add_scores(frame([("big", 115, 0), ("small", 20, 0)]), as_of=NOW)
        ratio = out.set_index("video_id").loc["big", "score"] / \
            out.set_index("video_id").loc["small", "score"]
        assert 1.4 < ratio < 1.8
        assert ratio < 115 / 20

    def test_score_is_monotonic_in_play_count(self):
        out = add_scores(frame([("a", 1, 0), ("b", 5, 0), ("c", 50, 0)]), as_of=NOW)
        assert out.sort_values("play_count")["score"].is_monotonic_increasing

    def test_score_is_the_product_of_both_terms(self):
        out = add_scores(frame([("a", 9, 30)]), as_of=NOW, half_life=30)
        assert out["score"].iloc[0] == pytest.approx(np.log1p(9) * 0.5)

    def test_recency_can_outrank_raw_count(self):
        """A modest recent track should beat a huge stale one - that is the
        whole point of the decay term."""
        out = add_scores(frame([("stale", 100, 365), ("fresh", 10, 0)]), as_of=NOW,
                         half_life=30)
        top = out.sort_values("score", ascending=False)["video_id"].iloc[0]
        assert top == "fresh"


class TestNoDecayCollapsesToPlayCount:
    def test_an_enormous_half_life_ranks_exactly_like_raw_counts(self):
        """The control used in the evaluation sweep.

        With no effective decay, log1p is monotonic in play_count, so the
        ranking must be identical to the most-played baseline.
        """
        df = frame([("a", 3, 10), ("b", 50, 300), ("c", 7, 1)])
        out = add_scores(df, as_of=NOW, half_life=10_000_000)
        by_score = out.sort_values("score", ascending=False)["video_id"].tolist()
        by_count = out.sort_values("play_count", ascending=False)["video_id"].tolist()
        assert by_score == by_count


class TestEmptyInput:
    def test_empty_frame_gets_the_columns_anyway(self):
        out = add_scores(pd.DataFrame(columns=["video_id", "play_count", "last_played"]))
        for col in ("days_since", "recency_weight", "score"):
            assert col in out.columns


class TestWindowing:
    def test_end_bound_is_exclusive(self, db):
        """Train and test windows must not share a boundary day."""
        before = aggregate_plays(db, end="2026-06-01")["play_count"].sum()
        after = aggregate_plays(db, start="2026-06-01")["play_count"].sum()
        total = aggregate_plays(db)["play_count"].sum()
        assert before + after == total

    def test_a_window_is_a_strict_subset(self, db):
        windowed = aggregate_plays(db, start="2026-01-01", end="2026-02-01")
        assert 0 < windowed["play_count"].sum() < aggregate_plays(db)["play_count"].sum()
