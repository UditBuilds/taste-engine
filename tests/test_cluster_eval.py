"""Clustering coherence, measured against the user's own playlist filing."""
import pandas as pd
import pytest

from taste_engine.cluster_eval import coherence, playlist_ground_truth, purity
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

    def test_genre_mode_degrades_to_title_without_genres(self):
        df = pd.DataFrame(
            {"title": ["Some Song"], "channel": ["X - Topic"], "genres": [[]]}
        )
        assert build_corpus(df, mode="title_genre") == ["Some Song"]

    def test_unknown_mode_is_refused(self):
        df = pd.DataFrame({"title": ["a"], "channel": [None]})
        with pytest.raises(ValueError, match="mode must be one of"):
            build_corpus(df, mode="vibes")
