"""Text normalisation and clustering, without loading the model."""
import numpy as np
import pandas as pd
import pytest

from taste_engine.embed import (
    artist_from_channel,
    build_corpus,
    cluster_embeddings,
    name_cluster,
    normalise_title,
    reduce_dims,
)


class TestTitleNormalisation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Travis Scott - MY EYES (Official Audio)", "Travis Scott - MY EYES"),
            ("d4vd - Here With Me [Official Music Video]", "d4vd - Here With Me"),
            ("The Weeknd - Out of Time", "The Weeknd - Out of Time"),
            ("Joji - Last of a Dying Breed (Visualizer)", "Joji - Last of a Dying Breed"),
            ("21 Savage - a lot (Official Video) ft. J. Cole", "21 Savage - a lot ft. J. Cole"),
            ("SZA - Snooze (Official Video)", "SZA - Snooze"),
        ],
    )
    def test_strips_release_furniture(self, raw, expected):
        assert normalise_title(raw) == expected

    def test_collapses_whitespace(self):
        assert normalise_title("A   (Official Video)   B") == "A B"

    def test_handles_missing_titles(self):
        assert normalise_title(None) == ""
        assert normalise_title("") == ""

    def test_nan_title_is_a_known_unfixed_gap(self):
        """Documents current behaviour, not desired behaviour.

        `float('nan')` is truthy in Python, so `if not title` lets it
        through to `str(title)` -> the literal string 'nan'. Same class of
        bug as artist_from_channel's (see TestArtistRecovery), but fixing
        it is out of scope for the brief that added this test - see
        reports/embedding_modes_remeasured.md. If normalise_title is ever
        given the same guard, this assertion should start failing and needs
        updating to `== ""`, not silently deleting.
        """
        assert normalise_title(float("nan")) == "nan"


class TestArtistRecovery:
    @pytest.mark.parametrize(
        "channel,expected",
        [
            ("PARTYNEXTDOOR - Topic", "PARTYNEXTDOOR"),
            ("Travis Scott - Topic", "Travis Scott"),
            ("TravisScottVEVO", "Travis Scott"),
            ("TheWeekndVEVO", "The Weeknd"),
            ("KendrickLamarVEVO", "Kendrick Lamar"),
            ("Don Toliver", "Don Toliver"),
            ("Rap Nation", "Rap Nation"),
        ],
    )
    def test_recovers_the_artist(self, channel, expected):
        assert artist_from_channel(channel) == expected

    def test_handles_missing_channel(self):
        assert artist_from_channel(None) == ""

    def test_handles_nan_channel(self):
        """Regression: pandas stores a missing channel as float('nan'),
        which is truthy in Python (`not float('nan')` is False), so the
        pre-fix code fell through to `str(nan).strip()` -> the literal
        string 'nan', treated as a real artist name. 9 of 2,918 canonical
        tracks had a NaN channel - see reports/embedding_modes_remeasured.md.
        """
        assert artist_from_channel(float("nan")) == ""


class TestCorpus:
    def test_appends_the_artist_when_the_title_lacks_it(self):
        df = pd.DataFrame({"title": ["TORE UP"], "channel": ["Don Toliver - Topic"]})
        assert build_corpus(df) == ["TORE UP - Don Toliver"]

    def test_does_not_repeat_an_artist_already_in_the_title(self):
        df = pd.DataFrame(
            {"title": ["Travis Scott - MY EYES (Official Audio)"],
             "channel": ["TravisScottVEVO"]}
        )
        assert build_corpus(df) == ["Travis Scott - MY EYES"]

    def test_survives_a_missing_channel(self):
        df = pd.DataFrame({"title": ["Some Song"], "channel": [None]})
        assert build_corpus(df) == ["Some Song"]

    def test_one_text_per_row(self):
        df = pd.DataFrame({"title": ["a", "b", "c"], "channel": [None, None, None]})
        assert len(build_corpus(df)) == 3

    def test_nan_channel_no_longer_appends_the_literal_string_nan(self):
        """The artist_from_channel fix, exercised end-to-end: a NaN channel
        with a real title must no longer produce a bogus '- nan' suffix."""
        df = pd.DataFrame({"title": ["Some Song"], "channel": [float("nan")]})
        assert build_corpus(df) == ["Some Song"]

    def test_nan_title_still_becomes_the_literal_string_nan(self):
        """Known, unfixed gap (normalise_title, not artist_from_channel) -
        a real channel does not rescue a NaN title. See
        TestTitleNormalisation.test_nan_title_is_a_known_unfixed_gap and
        reports/embedding_modes_remeasured.md."""
        df = pd.DataFrame({"title": [float("nan")], "channel": ["Don Toliver - Topic"]})
        assert build_corpus(df) == ["nan - Don Toliver"]

    def test_nan_title_and_nan_channel_both_stay_fully_degenerate(self):
        """The combined case the fix does NOT resolve: 7 of the 9 affected
        canonical tracks have both a NaN title and a NaN channel, and all
        seven still embed as the identical literal string 'nan' after the
        artist_from_channel fix - measured, not assumed, in
        reports/embedding_modes_remeasured.md."""
        df = pd.DataFrame({"title": [float("nan")], "channel": [float("nan")]})
        assert build_corpus(df) == ["nan"]


class TestDimensionReduction:
    def test_projects_to_the_requested_width(self):
        rng = np.random.default_rng(0)
        out = reduce_dims(rng.normal(size=(100, 384)), n_components=20)
        assert out.shape == (100, 20)

    def test_output_is_unit_norm(self):
        rng = np.random.default_rng(0)
        out = reduce_dims(rng.normal(size=(50, 384)), n_components=10)
        assert np.allclose(np.linalg.norm(out, axis=1), 1.0)

    def test_a_no_op_width_passes_through(self):
        vectors = np.random.default_rng(0).normal(size=(10, 8))
        assert reduce_dims(vectors, n_components=0).shape == vectors.shape


class TestClustering:
    def test_finds_planted_groups(self):
        """Three well-separated blobs must not come back as one."""
        rng = np.random.default_rng(0)
        blobs = []
        for centre in ([5, 0], [-5, 0], [0, 5]):
            pts = rng.normal(loc=centre, scale=0.25, size=(40, 2))
            blobs.append(np.hstack([pts, rng.normal(scale=0.01, size=(40, 30))]))
        vectors = np.vstack(blobs)
        labels = cluster_embeddings(vectors, min_cluster_size=8, min_samples=2,
                                    n_components=10)
        assert len({l for l in labels if l >= 0}) == 3

    def test_marks_outliers_rather_than_forcing_membership(self):
        """The reason for HDBSCAN over KMeans."""
        rng = np.random.default_rng(1)
        dense = rng.normal(loc=[0, 0], scale=0.1, size=(60, 2))
        far = np.array([[50.0, 50.0], [-50.0, 60.0]])
        pts = np.vstack([dense, far])
        vectors = np.hstack([pts, rng.normal(scale=0.01, size=(len(pts), 30))])
        labels = cluster_embeddings(vectors, min_cluster_size=8, min_samples=2,
                                    n_components=5)
        assert (labels == -1).any()


class TestNaming:
    def test_names_a_dominated_cluster_after_its_one_artist(self):
        group = pd.DataFrame({"channel": ["Travis Scott - Topic"] * 9 + ["Drake - Topic"]})
        assert name_cluster(group) == "Travis Scott"

    def test_names_a_mixed_cluster_after_its_top_artists(self):
        group = pd.DataFrame(
            {"channel": ["Drake - Topic"] * 4 + ["Future - Topic"] * 4 +
                        ["SZA - Topic"] * 3}
        )
        assert name_cluster(group).count("/") == 2

    def test_handles_a_cluster_with_no_channels(self):
        assert name_cluster(pd.DataFrame({"channel": [None, None]})) == "Unnamed"
