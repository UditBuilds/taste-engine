"""Contamination script's printed denominator matches its computed one.

`scripts/contamination.py:178` used to hardcode "3,143" as literal text in
the Section 5 banner ("CONTAMINATION ESTIMATE OVER ALL 3,143 SONGS"),
disconnected from `total = len(songs)`, the value the counts beneath it are
actually computed against - the same defect class as `dormancy_probe.py`'s
hardcoded N=365 prose, fixed in c51bda2. Fixed by interpolating `total`
directly. This guards against it recurring, regardless of what `total`
happens to be today (briefs/readme_final.md, Part A).

`scripts/` is not a package, so the script is loaded by file path rather
than imported normally - the same approach `tests/test_dormancy_probe.py`
uses. Unlike `dormancy_probe.py`'s `build_report()`, `contamination.py` has
no callable entry point: it is a flat, top-level script that runs on load
and prints directly, so the whole module is exec'd once with stdout
captured, and both the rendered text and the module's own `total` variable
are inspected from that one real run.
"""
from __future__ import annotations

import importlib.util
import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "contamination.py"


@pytest.fixture(scope="module")
def run(db):
    """Execute contamination.py once, capturing stdout and the module itself."""
    spec = importlib.util.spec_from_file_location("contamination", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    buf = io.StringIO()
    with redirect_stdout(buf):
        spec.loader.exec_module(mod)
    return mod, buf.getvalue()


class TestSection5DenominatorMatchesComputedTotal:
    def test_printed_denominator_equals_total(self, run):
        mod, text = run

        m = re.search(
            r"CONTAMINATION ESTIMATE OVER ALL ([\d,]+) SONGS", text
        )
        assert m, "Section 5 banner not found or changed shape"

        printed = m.group(1)
        computed = f"{mod.total:,}"
        assert printed == computed, (
            f"Section 5 banner says {printed!r} but the frame it measures "
            f"has {computed!r} songs - the banner is hardcoded again"
        )

    def test_section_1_and_section_5_denominators_agree(self, run):
        """Both banners derive from the same `total`; a regression in one
        without the other would itself be worth catching."""
        _, text = run

        m1 = re.search(r"THE MUSIC SET — ([\d,]+) canonical songs", text)
        m5 = re.search(r"CONTAMINATION ESTIMATE OVER ALL ([\d,]+) SONGS", text)
        assert m1 and m5
        assert m1.group(1) == m5.group(1)
