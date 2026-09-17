"""Clustering coherence, measured against the user's own playlist filing."""
import pandas as pd
import pytest

from taste_engine.cluster_eval import (
    _drop_conflicts,
    canonical_ground_truth,
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


class TestDropConflicts:
    """`_drop_conflicts()` - the pure core of `canonical_ground_truth()`.

    Fixes the raw/canonical id mismatch measured in
    reports/ground_truth_audit.md: ground truth stores raw upload ids, but
    the collapsed frame only ever carries one representative id per song.
    `raw_truth`/`rep_map` below stand in for `playlist_ground_truth()`'s and
    `canonical.raw_to_canonical_map()`'s real shapes, so the join and the
    conflict rule are exercised without touching the database.
    """

    def test_a_representative_id_resolves_to_itself(self):
        """The join, direction one: a raw id that already IS its own
        group's representative keeps its label under its own id."""
        truth, _stats = _drop_conflicts({"rep1": "Playlist A"}, {"rep1": "rep1"})
        assert truth == {"rep1": "Playlist A"}

    def test_a_losing_duplicate_resolves_under_its_representative(self):
        """The join, direction two - the actual fix: a raw id that lost its
        group's representative slot to a different upload must still
        contribute its label, filed under the id that DID win - not under
        its own (now-vanished) id, and not dropped the way the old
        raw-vs-canonical join dropped it."""
        truth, _stats = _drop_conflicts({"loser": "Playlist A"}, {"loser": "winner"})
        assert truth == {"winner": "Playlist A"}
        assert "loser" not in truth

    def test_a_raw_id_outside_the_canonical_population_is_dropped_quietly(self):
        """Not is_music (absent from rep_map) - out of scope, not a conflict."""
        truth, stats = _drop_conflicts({"not_music": "Playlist A"}, {})
        assert truth == {}
        assert stats["conflicts_dropped"] == 0

    def test_two_uploads_of_one_song_in_one_playlist_merge_without_conflict(self):
        """Same label from both raw ids - not a conflict, just agreement."""
        truth, stats = _drop_conflicts(
            {"a": "Playlist A", "b": "Playlist A"}, {"a": "rep", "b": "rep"}
        )
        assert truth == {"rep": "Playlist A"}
        assert stats["conflicts_dropped"] == 0

    def test_two_uploads_in_different_playlists_are_dropped_not_resolved(self):
        """The conflict rule: DROP the canonical track, don't pick a winner.

        Data-quality exclusion, not a canonicalisation over-merge guard -
        reports/ground_truth_audit.md (Item 3) confirmed every conflict
        found is one song independently filed into two playlists, not two
        different songs wrongly fused by `canonical.py`.
        """
        truth, stats = _drop_conflicts(
            {"a": "Playlist A", "b": "Playlist B"}, {"a": "rep", "b": "rep"}
        )
        assert "rep" not in truth
        assert stats["conflicts_dropped"] == 1
        assert stats["conflict_detail"] == [{
            "representative_id": "rep",
            "labels": ["Playlist A", "Playlist B"],
            "raw_ids": ["a", "b"],
        }]

    def test_no_play_count_or_recency_tiebreak_is_possible(self):
        """The rule takes no play-count/recency input at all to break a tie
        with - enforced by the function's own signature, not just its
        behaviour: `_drop_conflicts` only ever sees (raw_truth, rep_map),
        neither of which carries a play count or a timestamp."""
        import inspect

        assert list(inspect.signature(_drop_conflicts).parameters) == [
            "raw_truth", "rep_map",
        ]

    def test_reported_denominator_matches_truth_length(self):
        truth, stats = _drop_conflicts(
            {"a": "P", "b": "Q", "c": "P", "d": "R"},
            {"a": "ra", "b": "rb", "c": "ra", "d": "rd"},
        )
        assert stats["denominator"] == len(truth) == 3

    def test_raw_ground_truth_count_is_the_full_input_even_when_all_dropped(self):
        _truth, stats = _drop_conflicts(
            {"a": "P", "b": "Q"}, {"a": "rep", "b": "rep"}
        )
        assert stats["raw_ground_truth"] == 2
        assert stats["denominator"] == 0

    def test_empty_input(self):
        truth, stats = _drop_conflicts({}, {})
        assert truth == {}
        assert stats == {
            "raw_ground_truth": 0, "denominator": 0,
            "conflicts_dropped": 0, "conflict_detail": [],
        }


class TestCanonicalGroundTruth:
    """The DB-facing wrapper: fetches raw ground truth and the raw ->
    canonical map for real, then delegates to `_drop_conflicts` (tested in
    isolation above)."""

    def test_population_mismatch_is_refused_not_silently_dropped(self, db):
        """`tracks` must carry exactly the representative-id population
        `raw_to_canonical_map(scored_tracks(canonical=False))` produces - a
        caller passing something else (a stale or differently-filtered
        frame) must get a loud failure, not ground truth silently missing
        rows the way the original bug did."""
        from taste_engine.score import scored_tracks

        tracks = scored_tracks(db)
        bogus = pd.concat(
            [tracks, pd.DataFrame([{**tracks.iloc[0].to_dict(), "video_id": "not-a-real-id"}])],
            ignore_index=True,
        )
        with pytest.raises(RuntimeError, match="does not produce the same"):
            canonical_ground_truth(db, bogus)

    def test_matches_the_real_scored_tracks_population(self, db):
        """The intended, correctly-populated call succeeds and every
        surviving id is a real canonical track."""
        from taste_engine.score import scored_tracks

        tracks = scored_tracks(db)
        truth, _stats = canonical_ground_truth(db, tracks)
        assert set(truth) <= set(tracks["video_id"])


class TestCanonicalGroundTruthRegression:
    """Pins today's measured figures (reports/ground_truth_audit.md) against
    the real database. A regression test, not a claim of general truth -
    this can legitimately move if the underlying data changes, but an
    unexplained move is exactly what this test exists to catch.

    Two SEPARATE assertions on purpose, not one combined number: the pool
    size (denominator) and the conflict-drop count answer different
    questions, and collapsing them (e.g. asserting their difference, or a
    tuple) would hide which one moved if this test ever fails.
    """

    @pytest.fixture(scope="class")
    def stats(self, db):
        from taste_engine.score import scored_tracks

        tracks = scored_tracks(db)
        _truth, stats = canonical_ground_truth(db, tracks)
        return stats

    def test_denominator_is_480(self, stats):
        assert stats["denominator"] == 480

    def test_conflicts_dropped_is_3(self, stats):
        assert stats["conflicts_dropped"] == 3


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
