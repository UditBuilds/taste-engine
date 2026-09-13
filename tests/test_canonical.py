"""Collapsing duplicate uploads of the same recording.

The asymmetry these tests protect: an **over-merge** sums the play counts of
two different songs and puts the wrong track in a playlist; an **under-merge**
leaves a duplicate, which is the problem we already had. So the key is
deliberately conservative, and the tests that matter most are the ones asserting
different songs stay apart.
"""
import pandas as pd
import pytest

from taste_engine.canonical import (
    add_canonical_key,
    canonical_key,
    collapse,
    collapse_report,
)


def key(title, channel=None):
    return canonical_key(title, channel)


class TestPackagingVariantsMerge:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("Travis Scott - MY EYES (Official Audio)", "MY EYES"),
            ("Travis Scott - BUTTERFLY EFFECT (Official Video)", "BUTTERFLY EFFECT"),
            ("Travis Scott - I KNOW ? (Official Music Video)",
             "Travis Scott - I KNOW ? (Official Audio)"),
            ("Travis Scott - My Eyes - (Second Half Extended)", "MY EYES"),
            ("SICKO MODE", "Travis Scott - SICKO MODE (Official Video)"),
        ],
    )
    def test_same_recording_same_key(self, a, b):
        assert key(a, "TravisScottVEVO") == key(b, "Travis Scott - Topic")

    def test_slowed_and_sped_up_are_the_same_song(self):
        assert key("Nightcrawler (slowed + reverb)", "Travis Scott - Topic") == \
            key("Nightcrawler (sped up)", "Travis Scott - Topic")

    def test_featured_artists_do_not_split_a_song(self):
        assert key("OUT WEST (feat. Young Thug)", "JACKBOYS - Topic") == \
            key("OUT WEST", "JACKBOYS - Topic")

    def test_artist_case_does_not_split_a_song(self):
        assert key("XO Tour Llif3", "LIL UZI VERT") == \
            key("XO Tour Llif3", "Lil Uzi Vert")


class TestDifferentSongsStayApart:
    def test_same_title_different_artist_is_not_merged(self):
        """The bug this rule exists to prevent.

        Keying on title alone fused 'Die For You' by Joji with 'Die For You'
        by The Weeknd, and 103 other distinct-song pairs.
        """
        assert key("Die For You", "Joji - Topic") != key("Die For You", "TheWeekndVEVO")

    @pytest.mark.parametrize(
        "title,a,b",
        [
            ("Falling", "Harry Styles - Topic", "Trevor Daniel - Topic"),
            ("Love Me", "Justin Bieber - Topic", "Lil Wayne - Topic"),
            ("Nights Like This", "Future - Topic", "The Kid LAROI - Topic"),
        ],
    )
    def test_real_collisions_from_this_library(self, title, a, b):
        assert key(title, a) != key(title, b)

    def test_a_remix_is_not_the_original(self):
        assert key("Sicko Mode", "TravisScottVEVO") != \
            key("Sicko Mode (Remix)", "TravisScottVEVO")

    @pytest.mark.parametrize("variant", ["Cover", "Live", "Instrumental", "Acoustic"])
    def test_different_recordings_keep_their_identity(self, variant):
        base = key("Creep", "Radiohead - Topic")
        assert key(f"Creep ({variant})", "Radiohead - Topic") != base


class TestUnusableTitles:
    def test_missing_title_never_merges(self):
        assert key(None) == "" and key("") == ""

    def test_nan_never_merges(self):
        """NaN is truthy, so a naive guard lets every untitled track merge."""
        assert key(float("nan")) == ""
        assert key("nan") == ""

    def test_blank_keys_fall_back_to_the_video_id(self):
        df = pd.DataFrame(
            {"video_id": ["aaa", "bbb"], "title": [None, float("nan")],
             "channel": [None, None], "play_count": [1, 1]}
        )
        keyed = add_canonical_key(df)
        assert keyed["canonical_key"].nunique() == 2


class TestCollapse:
    @pytest.fixture
    def frame(self):
        return pd.DataFrame(
            {
                "video_id": ["v1", "v2", "v3", "v4"],
                "title": [
                    "Travis Scott - MY EYES (Official Audio)",
                    "MY EYES",
                    "Travis Scott - SICKO MODE (Official Video)",
                    "Die For You",
                ],
                "channel": [
                    "TravisScottVEVO", "Travis Scott - Topic",
                    "TravisScottVEVO", "Joji - Topic",
                ],
                "play_count": [100, 20, 30, 5],
                "last_played": ["2026-06-01T00:00:00+00:00", "2026-07-01T00:00:00+00:00",
                                "2026-05-01T00:00:00+00:00", "2026-04-01T00:00:00+00:00"],
                "first_played": ["2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00",
                                 "2026-01-15T00:00:00+00:00", "2026-03-01T00:00:00+00:00"],
            }
        )

    def test_merges_only_the_duplicate_pair(self, frame):
        assert len(collapse(frame)) == 3

    def test_play_counts_sum(self, frame):
        out = collapse(frame).set_index("video_id")
        assert out.loc["v1", "play_count"] == 120

    def test_representative_is_the_most_played_upload(self, frame):
        assert "v1" in set(collapse(frame)["video_id"])
        assert "v2" not in set(collapse(frame)["video_id"])

    def test_representative_is_a_real_video_id(self, frame):
        """The writer inserts this id, so it must exist on YouTube."""
        out = collapse(frame)
        assert set(out["video_id"]) <= set(frame["video_id"])

    def test_last_played_is_the_latest_across_uploads(self, frame):
        out = collapse(frame).set_index("video_id")
        assert out.loc["v1", "last_played"].startswith("2026-07-01")

    def test_first_played_is_the_earliest(self, frame):
        out = collapse(frame).set_index("video_id")
        assert out.loc["v1", "first_played"].startswith("2026-01-01")

    def test_variant_count_is_recorded(self, frame):
        out = collapse(frame).set_index("video_id")
        assert out.loc["v1", "variants"] == 2
        assert out.loc["v3", "variants"] == 1

    def test_empty_input(self):
        empty = pd.DataFrame(columns=["video_id", "title", "channel", "play_count"])
        assert collapse(empty).empty

    def test_total_plays_are_conserved(self, frame):
        """Collapsing must move plays, never invent or lose them."""
        assert collapse(frame)["play_count"].sum() == frame["play_count"].sum()


class TestReport:
    def test_counts_the_collapse(self):
        df = pd.DataFrame(
            {
                "video_id": ["a", "b", "c"],
                "title": ["Song One (Official Video)", "Song One", "Song Two"],
                "channel": ["X - Topic"] * 3,
                "play_count": [3, 2, 1],
            }
        )
        rep = collapse_report(df)
        assert rep["rows_in"] == 3
        assert rep["rows_out"] == 2
        assert rep["collapsed"] == 1
        assert rep["largest_group"] == 2


class TestDurationMerge:
    """The second pass: same title, different artist, same runtime.

    Exists because the artist-keyed rule under-merges systematically - a label
    uploads under its own channel while the `- Topic` twin sits under the
    composer, so they never share an artist. Runtime settles it.
    """

    def frame(self, rows):
        return pd.DataFrame(
            [
                {"video_id": f"v{i:02d}aaaaaaa"[:11], "title": t, "channel": c,
                 "play_count": p, "duration": d, "genres": g,
                 "last_played": "2026-06-01T00:00:00+00:00",
                 "first_played": "2026-01-01T00:00:00+00:00"}
                for i, (t, c, p, d, g) in enumerate(rows)
            ]
        )

    def test_same_song_different_credit_merges(self):
        """Singer-credited and composer-credited uploads of one recording."""
        df = self.frame([
            ("Raabta", "Arijit Singh - Topic", 10, "PT4M4S", ["Pop music"]),
            ("Raabta", "Pritam - Topic", 4, "PT4M4S", ["Pop music"]),
        ])
        assert len(collapse(df)) == 1

    def test_different_songs_sharing_a_title_stay_apart(self):
        """The 4:46 'Raabta' is a different song from the 4:04 one."""
        df = self.frame([
            ("Raabta", "Arijit Singh - Topic", 10, "PT4M4S", ["Pop music"]),
            ("Raabta", "Jokhay - Topic", 3, "PT4M46S", ["Hip_hop_music"]),
        ])
        assert len(collapse(df)) == 2

    def test_tolerance_is_respected(self):
        df = self.frame([
            ("Bulleya", "Arijit Singh - Topic", 9, "PT5M50S", ["Pop music"]),
            ("Bulleya", "Pritam - Topic", 5, "PT5M49S", ["Pop music"]),
        ])
        assert len(collapse(df)) == 1

    def test_beyond_tolerance_does_not_merge(self):
        df = self.frame([
            ("Song", "A - Topic", 9, "PT3M0S", ["Pop music"]),
            ("Song", "B - Topic", 5, "PT3M20S", ["Pop music"]),
        ])
        assert len(collapse(df)) == 2

    def test_missing_runtime_never_merges(self):
        """Unknown is not a match."""
        df = self.frame([
            ("Song", "A - Topic", 9, "PT3M0S", ["Pop music"]),
            ("Song", "B - Topic", 5, None, ["Pop music"]),
        ])
        assert len(collapse(df)) == 2

    def test_disjoint_genres_block_a_merge(self):
        """The tiebreaker. Inert on this library - `pop` and `hip hop` are on
        almost everything, so real collisions overlap - but it is the guard
        that would catch a genuinely different song at the same runtime."""
        df = self.frame([
            ("Mirror", "A - Topic", 9, "PT3M0S", ["Hip_hop_music"]),
            ("Mirror", "B - Topic", 5, "PT3M1S", ["Classical_music"]),
        ])
        assert len(collapse(df)) == 2

    def test_overlapping_genres_still_merge(self):
        df = self.frame([
            ("Mirror", "A - Topic", 9, "PT3M0S", ["Hip_hop_music", "Pop music"]),
            ("Mirror", "B - Topic", 5, "PT3M1S", ["Pop music"]),
        ])
        assert len(collapse(df)) == 1

    def test_unknown_genres_do_not_block(self):
        """Refusing on missing data would throw away the pairs this finds."""
        df = self.frame([
            ("Mirror", "A - Topic", 9, "PT3M0S", []),
            ("Mirror", "B - Topic", 5, "PT3M1S", ["Pop music"]),
        ])
        assert len(collapse(df)) == 1

    def test_plays_are_summed_across_the_merge(self):
        df = self.frame([
            ("Raabta", "Arijit Singh - Topic", 10, "PT4M4S", ["Pop music"]),
            ("Raabta", "Pritam - Topic", 4, "PT4M4S", ["Pop music"]),
        ])
        assert collapse(df)["play_count"].iloc[0] == 14

    def test_stay_with_me_is_not_stay(self):
        """`with` was treated as a featured-artist marker, so 'Stay With Me'
        normalised to 'stay' and matched The Kid LAROI's 'STAY' - both 2:22."""
        df = self.frame([
            ("Stay With Me", "1nonly - Topic", 5, "PT2M22S", ["Pop music"]),
            ("STAY", "The Kid LAROI - Topic", 9, "PT2M22S", ["Pop music"]),
        ])
        assert len(collapse(df)) == 2
