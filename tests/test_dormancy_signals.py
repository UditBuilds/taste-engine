"""dormancy_signals._md_table regression (brief: accumulated defect fixes,
2026-09-16).

`scripts/dormancy_signals.py` is not a package, so it is loaded here by
file path rather than imported normally - the same precedent
`tests/test_dormancy_probe.py` already established for testing a
standalone script without turning `scripts/` into a package.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dormancy_signals.py"
_spec = importlib.util.spec_from_file_location("dormancy_signals", SCRIPT_PATH)
signals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(signals)


class TestMdTableIntegerPreservation:
    def test_all_numeric_frame_does_not_render_trailing_point_zero(self):
        """Regression: df.iterrows() builds each row as a single pandas
        Series, which is homogeneously typed - an all-numeric row (no
        string column to force object dtype) silently upcasts every int to
        float64, rendering "90" as "90.0". Every table this script actually
        renders happens to carry a string column, so this was latent, not
        yet visible in any generated report - this constructs the one
        shape that does trigger it. Same fix as
        scripts/dormancy_probe.py's `_md_table`, ported here."""
        df = pd.DataFrame({"N": [90, 180], "count": [1694, 186], "pct": [58.05, 6.37]})
        text = signals._md_table(df)
        assert "90.0" not in text
        assert "180.0" not in text
        assert "1694.0" not in text
        assert "| 90 |" in text
        assert "58.05" in text  # the genuinely-float column is untouched

    def test_pipe_in_a_cell_is_escaped_not_a_new_column(self):
        df = pd.DataFrame({"title": ["A | B | C"], "n": [1]})
        text = signals._md_table(df)
        header, sep, row = text.splitlines()
        header_cells = header.strip("| ").split(" | ")
        row_cells = row.strip("| ").split(" | ")
        assert len(row_cells) == len(header_cells) == 2
        assert row_cells[0] == "A \\| B \\| C"

    def test_empty_frame(self):
        assert signals._md_table(pd.DataFrame(columns=["a", "b"])) == "*(none)*"
