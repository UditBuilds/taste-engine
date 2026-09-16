"""genre_coverage._modal tie-break regression (brief: accumulated defect
fixes, 2026-09-16).

`scripts/genre_coverage.py` is not a package, so it is loaded here by file
path rather than imported normally - the same precedent
`tests/test_dormancy_probe.py` already established for testing a
standalone script.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "genre_coverage.py"
_spec = importlib.util.spec_from_file_location("genre_coverage", SCRIPT_PATH)
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)


class TestModalTieBreak:
    """_modal's tie-break must not depend on Python's per-process string
    hash seed - the identical bug class already found and fixed in
    `writer._modal_genre` (2026-09-14). Live on this corpus, not
    hypothetical: a scan found 16 of 37 real clusters carrying an exact
    top-1 vote tie today, including Metro Boomin (28-28, "pop"/"hip hop")
    and T-Series (19-19, "music of asia"/"pop") - the same two clusters
    `writer._modal_genre`'s own docstring names.
    """

    TIE_INPUT = pd.Series([["hip hop", "pop"], ["pop", "hip hop"]])  # 2-2 exact tie

    def test_repeated_calls_in_one_process_agree(self):
        results = {coverage._modal(self.TIE_INPUT)[0] for _ in range(20)}
        assert len(results) == 1

    def test_tie_break_is_alphabetical_on_the_count(self):
        # highest count first (both tie at 2), then alphabetically-first
        # label - "hip hop" < "pop".
        modal_genre, n_labeled, modal_share, ambiguous = coverage._modal(self.TIE_INPUT)
        assert (modal_genre, n_labeled) == ("hip hop", 2)
        assert modal_share == 1.0
        assert ambiguous is False  # both labels clear 50% - the check's own known gap

    def test_tie_break_is_stable_across_process_hash_seeds(self):
        script = (
            "import importlib.util\n"
            "import pandas as pd\n"
            f"spec = importlib.util.spec_from_file_location('genre_coverage', {str(SCRIPT_PATH)!r})\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "s = pd.Series([['hip hop', 'pop'], ['pop', 'hip hop']])\n"
            "genre, n, share, amb = mod._modal(s)\n"
            "print(genre)\n"
        )
        seeds = [str(s) for s in range(10)]
        results = set()
        for seed in seeds:
            env = {**os.environ, "PYTHONHASHSEED": seed}
            out = subprocess.run(
                [sys.executable, "-c", script],
                env=env, capture_output=True, text=True, check=True,
            )
            results.add(out.stdout.strip())
        assert results == {"hip hop"}, (
            f"tie-break varied across PYTHONHASHSEED values: {results}"
        )

    def test_non_tied_input_is_unaffected(self):
        s = pd.Series([["pop"], ["pop"], ["hip hop"]])
        modal_genre, n_labeled, modal_share, ambiguous = coverage._modal(s)
        assert (modal_genre, n_labeled) == ("pop", 3)
        assert modal_share == pytest.approx(2 / 3)

    def test_empty_series_returns_none(self):
        assert coverage._modal(pd.Series([], dtype=object)) == (None, 0, None, None)
