"""README figures with no existing script, computed read-only.

Part B2 of briefs/readme_final.md: every CURRENT-DATA figure from
reports/readme_inventory.md's Part 0 that no existing script already prints,
computed here with a plain read-only query per figure and written to
reports/readme_facts.md, one row per figure with the query that produced it.

Nothing here writes to the database, changes config, or touches selection,
scoring, clustering or eval code - it only reads `data/taste.db` through
existing, unmodified functions (`score.scored_tracks`, `classify.classify`,
`embed.tidy_genres`) plus a couple of direct SQL queries for facts those
functions don't expose (playlist title repeats, test collection counts).

Run:  scripts/run.sh scripts/readme_facts.py
"""
from __future__ import annotations

import collections
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from taste_engine import config, embed, score  # noqa: E402
from taste_engine.classify import classify as classify_fn  # noqa: E402
from taste_engine.classify import _CACHE as classify_cache  # noqa: E402
from taste_engine.db import connect  # noqa: E402

REPORT_PATH = REPO_ROOT / "reports" / "readme_facts.md"

rows: list[dict] = []


def record(figure: str, value: str, query: str) -> None:
    rows.append({"figure": figure, "value": value, "query": query})


def main() -> int:
    conn = connect()

    # --- 1. STRICT_MUSIC regime pair for README section 3's dataset table -
    # the table currently mixes STRICT_MUSIC=True's canonical song count
    # (2,918) with STRICT_MUSIC=False's play count (10,539). Both regimes,
    # computed the same way, so the table can use one consistent pair.
    for flag in (False, True):
        config.STRICT_MUSIC = flag
        classify_cache.clear()
        can = score.scored_tracks(conn, canonical=True)
        record(
            f"canonical songs / plays, STRICT_MUSIC={flag}",
            f"{len(can):,} songs / {int(can.play_count.sum()):,} plays",
            "score.scored_tracks(conn, canonical=True) with "
            f"config.STRICT_MUSIC={flag}; len(df), df.play_count.sum()",
        )
    config.STRICT_MUSIC = True
    classify_cache.clear()

    # --- 2. Playlist title repeats (README section 4) -----------------
    rows_pl = conn.execute("SELECT title FROM playlists").fetchall()
    tc = collections.Counter(r[0] for r in rows_pl)
    dup3 = sum(1 for c in tc.values() if c == 3)
    dup2 = sum(1 for c in tc.values() if c == 2)
    record(
        "playlist titles repeated x3 / x2",
        f"{dup3} title(s) x3, {dup2} title(s) x2",
        "Counter(title for title, in SELECT title FROM playlists); "
        "count values == 3, count values == 2",
    )

    # --- 3. Scoring paragraph, canonical frame (README section 6) -----
    can = score.scored_tracks(conn, canonical=True)
    tot = can.play_count.sum()
    top20_share = can.sort_values("play_count", ascending=False).play_count.head(20).sum() / tot
    played_once = (can.play_count == 1).mean()
    record(
        "canonical: % played exactly once",
        f"{played_once:.1%}",
        "scored_tracks(canonical=True); (play_count == 1).mean()",
    )
    record(
        "canonical: top-20 share of plays",
        f"{top20_share:.1%}",
        "scored_tracks(canonical=True); "
        "sorted play_count.head(20).sum() / play_count.sum()",
    )
    raw = score.scored_tracks(conn, canonical=False)
    tot_raw = raw.play_count.sum()
    top20_share_raw = raw.sort_values("play_count", ascending=False).play_count.head(20).sum() / tot_raw
    played_once_raw = (raw.play_count == 1).mean()
    record(
        "raw (uncollapsed): % played exactly once",
        f"{played_once_raw:.1%}",
        "scored_tracks(canonical=False); (play_count == 1).mean() "
        "- the frame the '115 plays / 5.75x / 1.57x' paragraph is actually on",
    )
    record(
        "raw (uncollapsed): top-20 share of plays",
        f"{top20_share_raw:.1%}",
        "scored_tracks(canonical=False); "
        "sorted play_count.head(20).sum() / play_count.sum()",
    )

    # --- 4. Distinct genre labels (README section 6's "35 distinct tags") -
    # Two different counts exist and README's "35 distinct tags" reads as
    # topicCategories's own raw diversity (the sentence's subject is
    # "topicCategories returns 35 distinct tags", not the clustering
    # pipeline's tidied set) - so both are computed, and the raw one is the
    # closer match (36 vs 35, one off; tidied is 32, four off).
    raw_tags: set[str] = set()
    tidy_tags: set[str] = set()
    for g in can["genres"]:
        if isinstance(g, (list, tuple)):
            raw_tags.update(g)
        tidy_tags.update(embed.tidy_genres(g))
    record(
        "distinct genre labels, raw (untidied topicCategories)",
        str(len(raw_tags)),
        "scored_tracks(canonical=True)['genres']; "
        "size of the union of every row's raw label list",
    )
    record(
        "distinct genre labels, tidied (generic labels dropped)",
        str(len(tidy_tags)),
        "scored_tracks(canonical=True)['genres'].map(embed.tidy_genres); "
        "size of the union across all rows",
    )

    # --- 5. Test counts (README sections 8, 9) -------------------------
    collect = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    last_line = [ln for ln in collect.stdout.splitlines() if ln.strip()][-1]
    record(
        "tests/ total collected",
        last_line.strip(),
        "pytest --collect-only -q; last non-blank stdout line",
    )
    writer_tests = subprocess.run(
        ["grep", "-c", "def test_", "tests/test_writer.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    record(
        "tests/test_writer.py test count",
        writer_tests.stdout.strip(),
        'grep -c "def test_" tests/test_writer.py',
    )

    # --- write the report ------------------------------------------------
    lines = [
        "# README facts - figures with no existing script",
        "",
        "Part B2 of `briefs/readme_final.md`. Every row is a plain read-only "
        "query against the current `data/taste.db`, run through existing, "
        "unmodified functions. No config left toggled after this script "
        "returns (STRICT_MUSIC is reset to its default).",
        "",
        "| figure | value | query |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['figure']} | {r['value']} | `{r['query']}` |")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines))
    print(f"wrote {REPORT_PATH} ({len(rows)} rows)")
    for r in rows:
        print(f"  {r['figure']:45s} {r['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
