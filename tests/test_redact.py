"""Playlist-title pseudonymisation."""
from __future__ import annotations

from taste_engine.redact import alias


class TestAlias:
    def test_returns_none_label_for_none(self):
        assert alias(None, {}) == "(none)"

    def test_looks_up_a_known_name(self):
        assert alias("Sex Playlist ...", {"Sex Playlist ...": "Playlist K"}) == "Playlist K"

    def test_unknown_name_falls_back_without_leaking(self):
        assert alias("Some New Playlist", {}) == "Playlist ?"

    def test_handles_nan_name(self):
        """Regression: `name is None` alone misses a float NaN (`nan is
        None` is False), so a NaN name fell through to `str(name)` -> the
        literal string "nan", missed the mapping, and returned the "unknown
        name" fallback ("Playlist ?") instead of "(none)" - reachable via
        `redact_series()` on a pandas-read column (e.g.
        scripts/build_notebook.py), per CLAUDE.md open item 8. Same idiom
        embed.normalise_title/artist_from_channel and
        canonical.canonical_key already use for this - matched here rather
        than a second convention. Zero playlist names in the current
        database are actually NaN (see reports/nan_guard_fix.md), so this
        closes a defensive/latent gap rather than changing any
        currently-published pseudonym. See briefs/portability_defects.md
        Part A.
        """
        assert alias(float("nan"), {}) == "(none)"
