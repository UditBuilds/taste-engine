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


# --- as_of reproducibility (brief: reproducibility_and_distribution, Part B) --
# `build_report` used to read `pd.Timestamp.now(tz="UTC")` internally with no
# way to pin it, so every figure in reports/dormancy_signals.md was a
# snapshot of when the script happened to run, not a property of the
# dataset - and nothing recorded that this was so. Fixed by threading an
# optional `as_of` through `build_report`/`main --as-of`, defaulting to the
# original wall-clock behaviour when omitted, so no existing caller changes.

AS_OF_LABEL_PREFIX = '- `as_of` pinned for every "current"/live number below: `'


class TestAsOfReproducibility:
    def test_explicit_as_of_is_used_and_appears_labelled_in_output(self, db):
        pinned = pd.Timestamp("2026-08-15T00:00:00", tz="UTC")
        text = signals.build_report(as_of=pinned)
        matches = [l for l in text.splitlines() if l.startswith(AS_OF_LABEL_PREFIX)]
        assert len(matches) == 1, "expected exactly one labelled as_of line"
        assert matches[0] == AS_OF_LABEL_PREFIX + pinned.isoformat() + "`"

    def test_as_of_is_actually_threaded_through_not_just_labelled(self, db):
        """The label alone would not catch a regression where `as_of` is
        accepted but silently dropped before reaching `d.build_frames` /
        `track_signal_table` - strip the two lines that legitimately vary
        run-to-run (the as_of label itself, and the always-wall-clock
        "Report generated" provenance line) and require the rest of the
        report to differ when as_of differs by two months, since
        days_since/recency-window figures must move."""

        def strip_timestamp_lines(text: str) -> str:
            return "\n".join(
                line for line in text.splitlines()
                if not line.startswith(AS_OF_LABEL_PREFIX)
                and not line.startswith("- Report generated")
            )

        early = signals.build_report(as_of=pd.Timestamp("2026-06-01", tz="UTC"))
        late = signals.build_report(as_of=pd.Timestamp("2026-08-01", tz="UTC"))
        assert strip_timestamp_lines(early) != strip_timestamp_lines(late)

    def test_default_as_of_omitted_falls_back_to_wall_clock(self, db):
        before = pd.Timestamp.now(tz="UTC")
        text = signals.build_report()
        after = pd.Timestamp.now(tz="UTC")
        line = next(l for l in text.splitlines() if l.startswith(AS_OF_LABEL_PREFIX))
        used = pd.Timestamp(line[len(AS_OF_LABEL_PREFIX):-1])
        assert before <= used <= after

    def test_cli_as_of_flag_threads_through_main(self, db, tmp_path, monkeypatch):
        monkeypatch.setattr(signals, "REPORT_PATH", tmp_path / "report.md")
        rc = signals.main(["--as-of", "2026-08-15T00:00:00Z"])
        assert rc == 0
        text = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert AS_OF_LABEL_PREFIX + "2026-08-15T00:00:00+00:00`" in text

    def test_cli_naive_date_localizes_to_utc_not_silently_misinterpreted(
        self, db, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(signals, "REPORT_PATH", tmp_path / "report.md")
        signals.main(["--as-of", "2026-08-15"])
        text = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert AS_OF_LABEL_PREFIX + "2026-08-15T00:00:00+00:00`" in text

    def test_cli_default_omits_as_of_flag_and_still_writes_a_report(
        self, db, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(signals, "REPORT_PATH", tmp_path / "report.md")
        rc = signals.main([])
        assert rc == 0
        assert (tmp_path / "report.md").exists()
