"""Dormancy probe maths (brief: dormancy probe, 2026-09-16).

`scripts/dormancy_probe.py` is not a package (this brief's own scope keeps
everything outside `src/taste_engine/`), so it is loaded here by file path
rather than imported normally - the standard way to unit-test a standalone
script without turning `scripts/` into a package or touching
`pyproject.toml`, both out of scope for this brief.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dormancy_probe.py"
_spec = importlib.util.spec_from_file_location("dormancy_probe", SCRIPT_PATH)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


# --- eligibility boundary (brief section 8: the N-day boundary especially) --

class TestEligibilityBoundary:
    def test_exactly_N_is_not_eligible(self):
        """"Not played in the last N days" excludes the boundary day itself -
        the complement of plays_in_window's `<= N` (inclusive) convention.
        In practice days_since is a float derived from a pinned `as_of`, so
        an exact `N.0` essentially never occurs on real data; this test
        fixes the convention, not a case that has been observed live."""
        assert probe.is_eligible(pd.Series([90.0]), 90).iloc[0] == False  # noqa: E712

    def test_just_above_N_is_eligible(self):
        assert probe.is_eligible(pd.Series([90.0001]), 90).iloc[0] == True  # noqa: E712

    def test_just_below_N_is_not_eligible(self):
        assert probe.is_eligible(pd.Series([89.9999]), 90).iloc[0] == False  # noqa: E712

    def test_vectorised_over_a_series(self):
        out = probe.is_eligible(pd.Series([0.0, 90.0, 90.1, 365.8]), 90)
        assert out.tolist() == [False, False, True, True]


# --- ranking ---------------------------------------------------------------

class TestProbeRank:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "video_id": ["a", "b", "c", "d", "e"],
                "days_since": [10.0, 95.0, 200.0, 91.0, 91.0],
                "play_count": [50, 3, 10, 1, 5],
            }
        )

    def test_only_tracks_past_N_are_included(self):
        out = probe.probe_rank(self._frame(), 90)
        assert set(out["video_id"]) == {"b", "c", "d", "e"}
        assert "a" not in set(out["video_id"])  # days_since=10, not eligible

    def test_ranked_by_log1p_lifetime_plays_descending(self):
        out = probe.probe_rank(self._frame(), 90)
        # c has 10 plays (highest among the eligible four) -> ranks first.
        assert out.iloc[0]["video_id"] == "c"

    def test_ties_broken_by_video_id_ascending(self):
        """d and e are not tied on play_count (1 vs 5) - use a frame where
        two eligible rows genuinely tie on log1p(play_count)."""
        frame = pd.DataFrame(
            {
                "video_id": ["z", "y"],
                "days_since": [100.0, 100.0],
                "play_count": [5, 5],
            }
        )
        out = probe.probe_rank(frame, 90)
        assert out["video_id"].tolist() == ["y", "z"]

    def test_empty_when_nothing_eligible(self):
        frame = pd.DataFrame(
            {"video_id": ["a"], "days_since": [1.0], "play_count": [10]}
        )
        out = probe.probe_rank(frame, 90)
        assert out.empty


# --- cluster resolution by name --------------------------------------------

class TestFindCluster:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "video_id": ["a", "b", "c", "d"],
                "cluster": [0, 0, 1, -1],
                "cluster_name": ["Joji", "Joji", "Travis Scott", "(outliers)"],
            }
        )

    def test_case_insensitive_substring_match(self):
        cid, cname = probe.find_cluster(self._frame(), "joji")
        assert cid == 0
        assert cname == "Joji"

    def test_noise_rows_are_never_matched(self):
        cid, _ = probe.find_cluster(self._frame(), "outlier")
        assert cid is None

    def test_no_match_returns_none(self):
        cid, cname = probe.find_cluster(self._frame(), "Nonexistent Artist")
        assert cid is None and cname is None


# --- table rendering regression --------------------------------------------

class TestMdTableIntegerPreservation:
    def test_all_numeric_frame_does_not_render_trailing_point_zero(self):
        """Regression: df.iterrows() builds each row as a single pandas
        Series, which is homogeneously typed - an all-numeric row (no string
        column to force object dtype) silently upcasts every int to float64,
        rendering "90" as "90.0". Caught in this brief's own report
        (pool-size table) before being fixed to use to_dict("records")
        instead of iterrows()."""
        df = pd.DataFrame({"N": [90, 180], "count": [1694, 186], "pct": [58.05, 6.37]})
        text = probe._md_table(df)
        assert "90.0" not in text
        assert "180.0" not in text
        assert "1694.0" not in text
        assert "| 90 |" in text
        assert "58.05" in text  # the genuinely-float column is untouched

    def test_pipe_in_a_cell_is_escaped_not_a_new_column(self):
        """An escaped "\\|" still contains a literal "|" glyph, so counting
        raw pipe characters would wrongly flag a correctly-escaped row as
        mismatched - split on the " | " cell delimiter instead, which an
        escaped "\\| " (backslash before the pipe) does not match."""
        df = pd.DataFrame({"title": ["A | B | C"], "n": [1]})
        text = probe._md_table(df)
        header, sep, row = text.splitlines()
        header_cells = header.strip("| ").split(" | ")
        row_cells = row.strip("| ").split(" | ")
        assert len(row_cells) == len(header_cells) == 2
        assert row_cells[0] == "A \\| B \\| C"

    def test_empty_frame(self):
        assert probe._md_table(pd.DataFrame(columns=["a", "b"])) == "*(none eligible)*"


# --- prose/table agreement regression (finish_regeneration.md, Part A3) ----
# Section 5's "hard dormancy ceiling" sentence used to hardcode "8", "0.27%"
# and "at most 1" as literal text, disconnected from the pool table it sits
# next to - so when the anchor moved to MAX(watched_at) and the table's
# N=365 row went to zero, the prose kept asserting 8. Guards against that
# recurring by parsing both the sentence and the table out of one real
# build_report() call and requiring them to agree, whatever today's actual
# figures are.

class TestN365ProseMatchesTable:
    def test_prose_figures_equal_table_figures(self, db):
        text = probe.build_report()

        m = re.search(
            r"library-wide, only (?P<lib>\d+) of [\d,]+ canonical tracks "
            r"\((?P<pct>[\d.]+)%\) exceed it at all, and at most "
            r"(?P<qual>\d+) falls within any single qualifying cluster",
            text,
        )
        assert m, "N=365 'hard dormancy ceiling' sentence not found or changed shape"

        header_idx = text.index("### Pool size per N")
        row_365 = next(
            line for line in text[header_idx:].splitlines()
            if line.startswith("| 365 |")
        )
        cells = [c.strip() for c in row_365.strip("|").split("|")]
        # N | library_wide_eligible | pct_of_library | invisible_under_floor
        # | in_noise_cluster(-1) | in_qualifying_cluster | in_nonqualifying_cluster
        # | five_probe_clusters_subtotal
        table_lib, table_pct, table_qual = cells[1], cells[2], cells[5]

        assert m.group("lib") == table_lib
        assert m.group("pct") == table_pct
        assert m.group("qual") == table_qual
