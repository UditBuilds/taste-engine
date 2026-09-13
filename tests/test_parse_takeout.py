"""Unit tests for the Takeout parser - no database or export required."""
from datetime import timezone

import pytest

from taste_engine.parse_takeout import (
    RE_CHANNEL,
    RE_WATCH,
    _clean,
    parse_timestamp,
)

# One real cell body, copied verbatim from watch-history.html.
CELL_BODY = (
    'Watched <a href="https://www.youtube.com/watch?v=A5mURRozXtg">'
    "Don Toliver - No Pole [Official Music Video]</a><br>"
    '<a href="https://www.youtube.com/channel/UCgT01FILdWB9BsXBXKjpQ7A">Don Toliver</a>'
    "<br>13 Sept 2026, 12:54:35 IST<br>"
)

# A deleted/private video: Takeout prints the URL where a title would go.
DELETED_BODY = (
    'Watched <a href="https://www.youtube.com/watch?v=ujIu6tWI2Gs">'
    "https://www.youtube.com/watch?v=ujIu6tWI2Gs</a>"
    "<br>9 Sept 2026, 14:19:34 IST<br>"
)


class TestTimestamps:
    def test_four_letter_sept_is_accepted(self):
        """strptime's %b rejects 'Sept'; the parser must normalise it."""
        got = parse_timestamp("13 Sept 2026, 12:54:35 IST")
        assert (got.year, got.month, got.day) == (2026, 9, 13)

    def test_converts_ist_to_utc(self):
        # 12:54:35 IST is UTC+05:30, so 07:24:35 UTC the same day.
        got = parse_timestamp("13 Sept 2026, 12:54:35 IST")
        assert got.tzinfo == timezone.utc
        assert got.hour == 7 and got.minute == 24 and got.second == 35

    def test_crosses_the_date_line_backwards(self):
        """A post-midnight IST time lands on the previous UTC day."""
        got = parse_timestamp("2 Jan 2026, 04:00:00 IST")
        assert got.date().isoformat() == "2026-01-01"
        assert got.hour == 22 and got.minute == 30

    @pytest.mark.parametrize(
        "raw",
        [
            "1 Jan 2026, 00:00:00 IST",
            "28 Feb 2026, 23:59:59 IST",
            "30 Sept 2025, 09:05:01 IST",
        ],
    )
    def test_representative_formats_parse(self, raw):
        assert parse_timestamp(raw).tzinfo == timezone.utc

    def test_three_letter_months_still_work(self):
        assert parse_timestamp("7 Apr 2026, 16:56:39 IST").month == 4


class TestFieldExtraction:
    def test_extracts_video_id_title_and_host(self):
        host, video_id, title = RE_WATCH.search(CELL_BODY).groups()
        assert host == "www"
        assert video_id == "A5mURRozXtg"
        assert _clean(title) == "Don Toliver - No Pole [Official Music Video]"

    def test_extracts_channel(self):
        channel_id, name = RE_CHANNEL.search(CELL_BODY).groups()
        assert channel_id == "UCgT01FILdWB9BsXBXKjpQ7A"
        assert _clean(name) == "Don Toliver"

    def test_music_host_is_recognised(self):
        body = 'Watched <a href="https://music.youtube.com/watch?v=44cICamRLwk">TBH</a>'
        host, video_id, _ = RE_WATCH.search(body).groups()
        assert host == "music"
        assert video_id == "44cICamRLwk"

    def test_deleted_video_has_a_url_where_the_title_should_be(self):
        """The loader turns this into NULL rather than storing a URL as a title."""
        _, _, title = RE_WATCH.search(DELETED_BODY).groups()
        assert _clean(title).startswith("https://")

    def test_deleted_video_has_no_channel(self):
        assert RE_CHANNEL.search(DELETED_BODY) is None

    def test_video_ids_are_exactly_eleven_chars(self):
        assert RE_WATCH.search(CELL_BODY).group(2).__len__() == 11


class TestCleaning:
    def test_unescapes_entities(self):
        assert _clean("don&#39;t underestimate") == "don't underestimate"

    def test_strips_tags_and_collapses_whitespace(self):
        assert _clean("<b>a</b>   b\n c") == "a b c"

    def test_empty_becomes_none(self):
        assert _clean("") is None
        assert _clean("   ") is None
        assert _clean(None) is None
