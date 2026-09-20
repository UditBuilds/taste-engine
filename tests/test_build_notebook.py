"""Regression test for the output-stripping guard in scripts/build_notebook.py.

`scripts/` is not an installed package - imported here the same way
tests/test_min_samples_sweep.py imports scripts/min_samples_sweep.py, via an
explicit sys.path entry.

Context: a run of `scripts/build_notebook.py` without --execute silently
stripped 15 cells of committed output from notebooks/01_eda.ipynb. It was
caught by `git diff` and reverted, not by anything in the script itself -
this test is the guard that replaces "someone happens to notice the diff".
"""
import sys
from pathlib import Path

import nbformat as nbf
import pytest
from nbformat.v4 import new_output

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_notebook import OutputWouldBeStripped, build  # noqa: E402


def _mark_executed(path: Path) -> None:
    """Stamp the first code cell with a fake output, simulating what
    --execute (or a real Jupyter run) leaves on disk."""
    nb = nbf.read(path, as_version=4)
    code_cell = next(c for c in nb.cells if c.cell_type == "code")
    code_cell.outputs = [new_output("stream", name="stdout", text="hi\n")]
    nbf.write(nb, path)


class TestOutputStrippingGuard:
    def test_first_write_needs_no_flag(self, tmp_path):
        out = tmp_path / "nb.ipynb"
        build(out=out)
        assert out.exists()

    def test_second_unexecuted_write_is_fine_when_nothing_would_be_lost(self, tmp_path):
        out = tmp_path / "nb.ipynb"
        build(out=out)
        build(out=out)  # still no outputs on disk - nothing to strip
        assert out.exists()

    def test_refuses_to_overwrite_executed_outputs_without_a_flag(self, tmp_path):
        out = tmp_path / "nb.ipynb"
        build(out=out)
        _mark_executed(out)

        with pytest.raises(OutputWouldBeStripped):
            build(out=out)

        # Refusing must mean refusing - the file on disk keeps its output.
        after = nbf.read(out, as_version=4)
        assert any(c.outputs for c in after.cells if c.cell_type == "code")

    def test_allow_output_loss_overrides_the_guard(self, tmp_path):
        out = tmp_path / "nb.ipynb"
        build(out=out)
        _mark_executed(out)

        build(out=out, allow_output_loss=True)

        after = nbf.read(out, as_version=4)
        assert all(not c.outputs for c in after.cells if c.cell_type == "code")
