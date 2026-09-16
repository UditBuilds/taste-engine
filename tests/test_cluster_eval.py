"""Clustering coherence, measured against the user's own playlist filing."""
import pandas as pd
import pytest

from taste_engine.cluster_eval import (
    coherence,
    coherence_by_convention,
    playlist_ground_truth,
    purity,
)
from taste_engine.embed import build_corpus, strip_artist_from_title


class TestPurity:
    def test_perfect_clustering_is_pure(self):
        assert purity([0, 0, 1, 1], ["A", "A", "B", "B"]) == 1.0

    def test_a_fully_mixed_cluster_is_half_pure(self):
        assert purity([0, 0, 0, 0], ["A", "A", "B", "B"]) == 0.5

    def test_empty_input_is_zero(self):
        assert purity([], []) == 0.0


class TestCoherence:
    def test_recovers_a_perfect_partition(self):
        clustered = pd.DataFrame(
            {"video_id": list("abcd"), "cluster": [0, 0, 1, 1]}
        )
        truth = {"a": "P", "b": "P", "c": "Q", "d": "Q"}
        got = coherence(clustered, truth)
        assert got["ari"] == pytest.approx(1.0)
        assert got["purity"] == pytest.approx(1.0)
        assert got["coverage"] == pytest.approx(1.0)

    def test_noise_is_excluded_but_lowers_coverage(self):
        """A clustering that refuses to label anything must not look perfect."""
        clustered = pd.DataFrame(
            {"video_id": list("abcd"), "cluster": [0, 0, -1, -1]}
        )
        truth = {"a": "P", "b": "P", "c": "Q", "d": "Q"}
        got = coherence(clustered, truth)
        assert got["n_eval"] == 2
        assert got["coverage"] == pytest.approx(0.5)

    def test_ignores_tracks_with_no_ground_truth(self):
        clustered = pd.DataFrame(
            {"video_id": list("abcz"), "cluster": [0, 0, 1, 1]}
        )
        got = coherence(clustered, {"a": "P", "b": "P", "c": "Q"})
        assert got["n_eval"] == 3

    def test_degenerate_input_does_not_raise(self):
        clustered = pd.DataFrame({"video_id": ["a"], "cluster": [-1]})
        assert coherence(clustered, {"a": "P"})["ari"] == 0.0


class TestCoherenceByConvention:
    """Noise scored three ways, side by side - see reports/eval_verification.md (A1/B1).

    Fixture: two clean clusters (a,b -> P; c,d -> Q) plus two noise points
    that are truly heterogeneous (e is P-like, f is Q-like). `coherence()`
    only ever implements "exclude"; this checks the other two conventions
    without changing that default.
    """

    CLUSTERED = pd.DataFrame(
        {"video_id": list("abcdef"), "cluster": [0, 0, 1, 1, -1, -1]}
    )
    TRUTH = {"a": "P", "b": "P", "c": "Q", "d": "Q", "e": "P", "f": "Q"}

    def test_exclude_matches_coherence_exactly(self):
        """The new function's "exclude" row must agree with the existing,
        unmodified `coherence()` - it is a reproduction, not a replacement."""
        table = coherence_by_convention(self.CLUSTERED, self.TRUTH)
        exclude = table.set_index("convention").loc["exclude"]
        old = coherence(self.CLUSTERED, self.TRUTH)
        assert exclude["n_eval"] == old["n_eval"]
        assert exclude["ari"] == pytest.approx(old["ari"])
        assert exclude["nmi"] == pytest.approx(old["nmi"])
        assert exclude["purity"] == pytest.approx(old["purity"])

    def test_exclude_looks_perfect_by_hiding_the_noise(self):
        table = coherence_by_convention(self.CLUSTERED, self.TRUTH)
        row = table.set_index("convention").loc["exclude"]
        assert row["n_eval"] == 4
        assert row["ari"] == pytest.approx(1.0)

    def test_single_cluster_scores_lower_than_exclude(self):
        """Lumping heterogeneous noise (P and Q) into one cluster manufactures
        a disagreement the exclude convention hid."""
        table = coherence_by_convention(self.CLUSTERED, self.TRUTH)
        row = table.set_index("convention").loc["single_cluster"]
        assert row["n_eval"] == 6
        assert row["ari"] == pytest.approx(0.24242424242424243)

    def test_singletons_scores_between_exclude_and_single_cluster(self):
        """Each noise point isolated in its own cluster: no false agreement
        between e and f, but also no reward for the two clean clusters
        beyond what singletons cost by existing at all."""
        table = coherence_by_convention(self.CLUSTERED, self.TRUTH)
        row = table.set_index("convention").loc["singletons"]
        assert row["n_eval"] == 6
        assert row["ari"] == pytest.approx(0.375)

    def test_singletons_never_lets_two_noise_points_share_a_label(self):
        table = coherence_by_convention(self.CLUSTERED, self.TRUTH)
        # e and f are the two noise points; if the convention worked, their
        # predicted labels are >= 0 (real HDBSCAN ids never collide with the
        # fresh ones assigned here) and distinct from each other.
        from taste_engine.cluster_eval import _relabel_noise

        remapped = _relabel_noise(self.CLUSTERED["cluster"].tolist(), "singletons")
        noise_positions = [i for i, c in enumerate(self.CLUSTERED["cluster"]) if c == -1]
        noise_labels = [remapped[i] for i in noise_positions]
        assert len(set(noise_labels)) == len(noise_labels)
        assert all(label >= 0 for label in noise_labels)

    def test_degenerate_input_does_not_raise(self):
        table = coherence_by_convention(
            pd.DataFrame({"video_id": ["a"], "cluster": [-1]}), {"a": "P"}
        )
        assert (table["ari"] == 0.0).all()

    def test_unknown_convention_is_refused(self):
        from taste_engine.cluster_eval import _relabel_noise

        with pytest.raises(ValueError, match="convention must be"):
            _relabel_noise([0, -1], "vibes")


class TestGroundTruth:
    def test_only_single_playlist_videos_are_used(self, db):
        """A track in two playlists cannot disagree with either."""
        truth = playlist_ground_truth(db)
        multi = {
            r[0]
            for r in db.execute(
                "SELECT video_id FROM (SELECT DISTINCT playlist_name, video_id "
                "FROM playlist_tracks) GROUP BY video_id HAVING COUNT(*) > 1"
            )
        }
        assert not set(truth) & multi

    def test_ground_truth_is_non_trivial(self, db):
        truth = playlist_ground_truth(db)
        assert len(truth) > 1_000
        assert len(set(truth.values())) > 10


class TestArtistExclusion:
    @pytest.mark.parametrize(
        "title,artist,expected",
        [
            ("Travis Scott - MY EYES", "Travis Scott", "MY EYES"),
            ("The Weeknd - Out of Time", "The Weeknd", "Out of Time"),
            ("Snooze", "SZA", "Snooze"),
            ("d4vd - Here With Me", "d4vd", "Here With Me"),
        ],
    )
    def test_strips_a_leading_artist_prefix(self, title, artist, expected):
        assert strip_artist_from_title(title, artist) == expected

    def test_never_empties_a_title(self):
        assert strip_artist_from_title("Drake", "Drake") == "Drake"

    def test_title_mode_removes_the_artist_entirely(self):
        df = pd.DataFrame(
            {"title": ["Travis Scott - MY EYES (Official Audio)"],
             "channel": ["TravisScottVEVO"]}
        )
        assert build_corpus(df, mode="title") == ["MY EYES"]

    def test_title_artist_mode_keeps_it(self):
        df = pd.DataFrame({"title": ["TORE UP"], "channel": ["Don Toliver - Topic"]})
        assert build_corpus(df, mode="title_artist") == ["TORE UP - Don Toliver"]

    def test_genre_mode_appends_genre_labels(self):
        df = pd.DataFrame(
            {
                "title": ["Travis Scott - MY EYES"],
                "channel": ["TravisScottVEVO"],
                "genres": [["Hip_hop_music", "Rapping"]],
            }
        )
        assert build_corpus(df, mode="title_genre") == ["MY EYES. hip hop, rapping"]

    def test_generic_topics_are_dropped(self):
        """`topicCategories` tags nearly every music video with bare 'Music'.

        Keeping it would put the same token on almost every track, separating
        nothing while diluting the labels that do discriminate.
        """
        from taste_engine.embed import tidy_genres

        assert tidy_genres(
            ["https://en.wikipedia.org/wiki/Music",
             "https://en.wikipedia.org/wiki/Hip_hop_music"]
        ) == ["hip hop"]

    def test_genre_labels_are_deduplicated(self):
        from taste_engine.embed import tidy_genres

        assert tidy_genres(["Pop_music", "Pop music", "Rock_music"]) == ["pop", "rock"]

    def test_genre_mode_ignores_a_music_only_topic_list(self):
        df = pd.DataFrame(
            {"title": ["X - Song"], "channel": ["X - Topic"], "genres": [["Music"]]}
        )
        assert build_corpus(df, mode="title_genre") == ["Song"]

    def test_genre_mode_degrades_to_title_without_genres(self):
        df = pd.DataFrame(
            {"title": ["Some Song"], "channel": ["X - Topic"], "genres": [[]]}
        )
        assert build_corpus(df, mode="title_genre") == ["Some Song"]

    def test_unknown_mode_is_refused(self):
        df = pd.DataFrame({"title": ["a"], "channel": [None]})
        with pytest.raises(ValueError, match="mode must be one of"):
            build_corpus(df, mode="vibes")


class TestRedaction:
    """Playlist titles must not reach anything publishable.

    This repo is public and several playlist titles are personal. Every metric
    that uses them treats them as opaque group labels, so pseudonymising costs
    the analysis nothing.
    """

    def test_ground_truth_is_pseudonymised_by_default(self, db):
        from taste_engine.cluster_eval import playlist_ground_truth

        labels = set(playlist_ground_truth(db).values())
        assert labels, "no ground truth at all"
        assert all(l.startswith("Playlist ") for l in labels), sorted(labels)[:5]

    def test_real_titles_are_available_only_on_request(self, db):
        from taste_engine.cluster_eval import playlist_ground_truth

        real = set(playlist_ground_truth(db, redacted=False).values())
        assert not all(l.startswith("Playlist ") for l in real)

    def test_redaction_does_not_change_the_grouping(self, db):
        """Pseudonyms must be a relabelling, not a merge - otherwise every
        ARI/NMI number would silently change."""
        from taste_engine.cluster_eval import playlist_ground_truth

        plain = playlist_ground_truth(db, redacted=False)
        coded = playlist_ground_truth(db)
        assert set(plain) == set(coded)
        assert len(set(plain.values())) == len(set(coded.values()))
        pairs = {(plain[v], coded[v]) for v in plain}
        assert len({p for p, _ in pairs}) == len({c for _, c in pairs})

    def test_aliases_are_stable_across_calls(self, db):
        from taste_engine.cluster_eval import playlist_ground_truth

        assert playlist_ground_truth(db) == playlist_ground_truth(db)

    def test_unknown_names_never_leak_through(self):
        from taste_engine.redact import alias

        assert alias("some playlist that does not exist") == "Playlist ?"
        assert alias(None) == "(none)"

    def test_label_generation(self):
        from taste_engine.redact import _label

        assert (_label(0), _label(25), _label(26)) == ("A", "Z", "AA")
