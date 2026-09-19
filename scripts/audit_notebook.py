"""Print every personal-looking string the committed notebook would publish.

Run before pushing. Playlist titles must not appear; track and artist names
are expected and are the substance of the analysis.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from taste_engine.redact import load_aliases  # noqa: E402

NB = REPO_ROOT / "notebooks" / "01_eda.ipynb"

nb = json.loads(NB.read_text(encoding="utf-8"))
chunks, images = [], 0
for cell in nb["cells"]:
    for out in cell.get("outputs", []):
        if "image/png" in out.get("data", {}):
            images += 1
        for key in ("text",):
            if key in out:
                chunks.append("".join(out[key]))
        for key, val in out.get("data", {}).items():
            if key.startswith("text/plain") or key == "text/html":
                chunks.append("".join(val) if isinstance(val, list) else str(val))
blob = "\n".join(chunks)
blob = re.sub(r"<[^>]+>", " ", blob)  # strip HTML table markup

print(f"notebook: {NB.name}")
print(f"  code cells with output : {sum(1 for c in nb['cells'] if c.get('outputs'))}")
print(f"  rendered plots         : {images}")
print(f"  total output text      : {len(blob):,} chars")

# --- 1. playlist titles must be gone -----------------------------------------
real = [n for n in load_aliases() if n]
leaked = sorted({n for n in real if n and len(n) > 3 and n in blob})
print("\n" + "=" * 70)
print("PLAYLIST TITLES IN COMMITTED OUTPUT  (must be empty)")
print("=" * 70)
if leaked:
    for n in leaked:
        print(f"  !! LEAK: {n!r}")
else:
    print(f"  clean - none of the {len(real)} real playlist titles appear")
aliases = sorted({a for a in load_aliases().values() if a in blob})
print(f"  pseudonyms present instead: {', '.join(aliases) if aliases else '(none shown)'}")

# --- 2. what IS published ----------------------------------------------------
print("\n" + "=" * 70)
print("TRACK AND ARTIST NAMES THAT WILL BE PUBLISHED")
print("=" * 70)
print(blob)
