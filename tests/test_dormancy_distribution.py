"""Bucket-boundary maths for scripts/dormancy_distribution.py (brief:
reproducibility_and_distribution.md, Part C).

`scripts/` is not a package - loaded here by file path, the same precedent
`tests/test_dormancy_probe.py` / `tests/test_dormancy_signals.py` already
established. Boundary correctness matters the same way it does for
`dormancy.plays_in_window` (see tests/test_dormancy.py): an off-by-one here
would silently move a track into the wrong bucket in every table this
script renders.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dormancy_distribution.py"
_spec = importlib.util.spec_from_file_location("dormancy_distribution", SCRIPT_PATH)
dist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dist)


class TestBucketOf:
    def test_zero_is_the_first_bucket(self):
        assert dist._bucket_of(0.0) == "0-7"

    def test_just_under_a_boundary_stays_in_the_lower_bucket(self):
        assert dist._bucket_of(6.999) == "0-7"
        assert dist._bucket_of(13.999) == "7-14"
        assert dist._bucket_of(34.999) == "28-35"

    def test_exactly_on_a_boundary_moves_to_the_upper_bucket(self):
        """lo <= days < hi: the boundary day belongs to the bucket that
        starts there, not the one that ends there."""
        assert dist._bucket_of(7.0) == "7-14"
        assert dist._bucket_of(14.0) == "14-21"
        assert dist._bucket_of(21.0) == "21-28"
        assert dist._bucket_of(28.0) == "28-35"
        assert dist._bucket_of(35.0) == "35+"

    def test_far_past_the_last_finite_bucket_is_still_35_plus(self):
        assert dist._bucket_of(400.0) == "35+"

    def test_every_bucket_label_is_reachable(self):
        labels = {dist._bucket_of(d) for d in (0, 7, 14, 21, 28, 35, 1000)}
        assert labels == {"0-7", "7-14", "14-21", "21-28", "28-35", "35+"}

    def test_negative_days_is_a_bug_elsewhere_not_a_bucket_here(self):
        """`score.add_scores` clips days_since to >= 0.0, so this should
        never receive a negative value in practice - raises rather than
        silently mis-bucketing if that guarantee is ever violated."""
        with pytest.raises(AssertionError):
            dist._bucket_of(-0.5)


class TestBucketLabel:
    def test_finite_range(self):
        assert dist._bucket_label(21, 28) == "21-28"

    def test_open_ended_range(self):
        assert dist._bucket_label(35, None) == "35+"
