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
    strip_artist_from_title,
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

    def test_handles_nan_title(self):
        """Regression: pandas stores a missing title as float('nan'), which
        is truthy in plain Python (`not float('nan')` is False), so the
        pre-fix code fell through to `str(nan)` -> the literal string 'nan'.
        Same class of bug as artist_from_channel's (see TestArtistRecovery)
        and canonical.canonical_key's - fixed the same way here. 7 of 2,918
        canonical tracks had a NaN title (and, for all 7, also a NaN
        channel) - see reports/normalise_title_fix.md.
        """
        assert normalise_title(float("nan")) == ""


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


class TestStripArtistFromTitle:
    def test_strips_a_matching_prefix(self):
        assert strip_artist_from_title("Don Toliver - TORE UP", "Don Toliver") == "TORE UP"

    def test_leaves_a_non_matching_title_unchanged(self):
        assert strip_artist_from_title("Some Other Title", "Don Toliver") == "Some Other Title"

    def test_handles_missing_artist(self):
        assert strip_artist_from_title("Some Title", "") == "Some Title"

    def test_handles_nan_title(self):
        """Regression: same NaN-truthiness class as normalise_title's,
        fixed the same way, defensively - both real call sites
        (embed.build_corpus, canonical.canonical_key) already pass a
        normalise_title()-cleaned string, so a raw NaN title has never
        reached this function in practice. Without the guard, `title.lower()`
        raises AttributeError on a float - see reports/normalise_title_fix.md.
        The function's existing contract for unusable input is to return
        `title` unchanged (see test_handles_missing_artist above), so a NaN
        title comes back as that same NaN, not "" - `!=` self is how NaN
        equality actually works, so this checks that rather than `==`.
        """
        result = strip_artist_from_title(float("nan"), "Don Toliver")
        assert result != result

    def test_handles_nan_title_and_missing_artist(self):
        result = strip_artist_from_title(float("nan"), "")
        assert result != result

    def test_handles_nan_artist(self):
        """Regression: the title-side NaN guard above (from
        reports/normalise_title_fix.md) left a separate gap - a NaN
        *artist* still reached `artist.lower()` unguarded and raised
        AttributeError. Documented, deliberately unfixed as CLAUDE.md open
        item 8 (unreachable via either real call site today - both always
        pass artist_from_channel's output, which is never NaN). Closed by
        briefs/portability_defects.md Part A: same contract as a missing
        artist (test_handles_missing_artist above) - the title comes back
        unchanged rather than crashing. See reports/nan_guard_fix.md.
        """
        assert strip_artist_from_title("Some Title", float("nan")) == "Some Title"


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

    def test_nan_title_no_longer_becomes_the_literal_string_nan(self):
        """Fixed: a real channel now rescues a NaN title. Previously this
        was 'nan - Don Toliver' - the bogus 'nan' prefix normalise_title's
        pre-fix behaviour produced. See reports/normalise_title_fix.md."""
        df = pd.DataFrame({"title": [float("nan")], "channel": ["Don Toliver - Topic"]})
        assert build_corpus(df) == ["Don Toliver"]

    def test_nan_title_no_longer_becomes_nan_in_title_mode(self):
        """Unlike the artist_from_channel fix, this one changes `title` and
        `title_genre` mode text too, not just `title_artist` - both modes
        derive from normalise_title's own output, not just the channel side.
        See reports/normalise_title_fix.md."""
        df = pd.DataFrame({"title": [float("nan")], "channel": ["Don Toliver - Topic"]})
        assert build_corpus(df, mode="title") == [""]
        assert build_corpus(df, mode="title_genre") == [""]

    def test_nan_title_and_nan_channel_both_now_resolve_to_empty(self):
        """The combined case: 7 of 2,918 canonical tracks have both a NaN
        title and a NaN channel. Before this fix all seven embedded as the
        literal string 'nan' even after the artist_from_channel fix alone
        (that fix could not rescue them - normalise_title's own NaN gap
        dominated); now both sides resolve to "" and the corpus text is a
        genuinely empty string rather than a fabricated word. See
        reports/normalise_title_fix.md."""
        df = pd.DataFrame({"title": [float("nan")], "channel": [float("nan")]})
        assert build_corpus(df) == [""]


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
