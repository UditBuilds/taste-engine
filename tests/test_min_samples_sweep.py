"""Perturbation and stability-metric logic for the min_samples sweep.

`scripts/` is not an installed package (no `__init__.py`, not on the default
path) - imported here the same way `verify_strict_null.py`-style scripts
import `src/`, via an explicit `sys.path` entry, since these are the only
tests in the repo that exercise a `scripts/` module directly.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from min_samples_sweep import drop_indices, stability_ari  # noqa: E402


class TestDropIndices:
    def test_same_seed_drops_the_same_indices(self):
        """The load-bearing property for the sweep's paired design: every
        (min_samples, mode) cell must see the identical 20 perturbations."""
        first = drop_indices(2918, 7, seed=1000)
        second = drop_indices(2918, 7, seed=1000)
        assert first == second

    def test_different_seeds_drop_different_indices(self):
        results = {tuple(drop_indices(2918, 7, seed=s)) for s in range(1000, 1020)}
        assert len(results) == 20, "20 distinct seeds produced fewer than 20 distinct drop-sets"

    def test_returns_exactly_n_drop_unique_sorted_indices(self):
        dropped = drop_indices(100, 7, seed=42)
        assert len(dropped) == 7
        assert len(set(dropped)) == 7
        assert dropped == sorted(dropped)
        assert all(0 <= i < 100 for i in dropped)

    def test_is_independent_of_call_order_elsewhere_in_the_process(self):
        """A prior, unrelated use of the `random` module must not perturb
        this - each call seeds its own `random.Random` instance rather than
        touching the shared global generator."""
        import random

        random.seed(0)
        random.random()
        random.random()
        a = drop_indices(2918, 7, seed=1000)
        random.seed(99999)
        for _ in range(50):
            random.random()
        b = drop_indices(2918, 7, seed=1000)
        assert a == b


class TestStabilityAri:
    """Fixture: a clustering (`labels_a`) and a lightly perturbed one
    (`labels_b`) that agree everywhere except how two originally-noise
    points are treated - one stays noise, one gets picked up by a real
    cluster in `labels_b`. Expected values computed directly with
    `sklearn.metrics.adjusted_rand_score`, not hand-derived.
    """

    LABELS_A = [0, 0, 1, 1, -1, -1]
    LABELS_B = [0, 0, 1, 1, -1, 2]

    def test_exclude_scores_only_points_neither_side_calls_noise(self):
        ari, n = stability_ari(self.LABELS_A, self.LABELS_B, "exclude")
        # Index 4 is noise on both sides; index 5 is noise only on A's side.
        # "exclude" drops a point if *either* side calls it noise, so both
        # are dropped, leaving the 4 points both sides confidently placed -
        # which agree perfectly.
        assert n == 4
        assert ari == pytest.approx(1.0)

    def test_single_cluster_scores_every_point_as_is(self):
        ari, n = stability_ari(self.LABELS_A, self.LABELS_B, "single_cluster")
        assert n == 6
        assert ari == pytest.approx(0.7619047619047619)

    def test_singletons_gives_each_sides_noise_its_own_label(self):
        ari, n = stability_ari(self.LABELS_A, self.LABELS_B, "singletons")
        assert n == 6
        # Both sides end up with exactly one point alone at index 4 and one
        # alone at index 5 - same partition shape, so perfect agreement even
        # though the fresh label *numbers* differ (2/3 vs 3/2).
        assert ari == pytest.approx(1.0)

    def test_identical_clusterings_are_perfectly_stable_under_every_convention(self):
        from min_samples_sweep import NOISE_CONVENTIONS

        labels = [0, 0, 1, 1, -1, -1]
        for convention in NOISE_CONVENTIONS:
            ari, _ = stability_ari(labels, list(labels), convention)
            assert ari == pytest.approx(1.0), convention

    def test_mismatched_lengths_are_refused(self):
        with pytest.raises(ValueError, match="same length"):
            stability_ari([0, 1], [0, 1, 1], "exclude")

    def test_unknown_convention_is_refused(self):
        with pytest.raises(ValueError, match="convention must be"):
            stability_ari([0, -1], [0, -1], "vibes")
