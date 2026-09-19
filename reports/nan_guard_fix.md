# `redact.alias` / `embed.strip_artist_from_title` NaN guards — fix and measurement

Part A of `briefs/portability_defects.md`. Closes two of the three items in
CLAUDE.md's "Known open items #8" (the NaN-truthiness/hash-seed-tie-break
defect family): `redact.alias()`'s missing NaN guard, and
`embed.strip_artist_from_title()`'s missing *artist*-side NaN guard (the
title side was already fixed in `029319e`,
`reports/normalise_title_fix.md`). The third item in that list
(`scripts/genre_coverage.py`'s `label_counts` hash-seed tie-break) is out of
scope here — untouched.

## The bugs

**`redact.alias()`** (`src/taste_engine/redact.py`): the guard was
`if name is None`. A float NaN is not `None` (`float("nan") is None` is
`False`), so a NaN name fell through to `str(name)` → the literal 3-character
string `"nan"`, missed the alias mapping, and silently returned the "unknown
name" fallback (`"Playlist ?"`) instead of the correct `"(none)"`. Reachable
via `redact_series()` on a pandas-read column — `scripts/build_notebook.py`
does exactly this over `playlists.title`.

**`embed.strip_artist_from_title()`** (`src/taste_engine/embed.py`): the
guard was `if not artist or not title or title != title`, which covers a NaN
*title* but not a NaN *artist*. A NaN artist reached `artist.lower()`
unguarded and raised `AttributeError: 'float' object has no attribute
'lower'`. This exact gap was found and deliberately left open while fixing
the title side (`029319e`) — see that commit's own test,
`test_does_not_guard_a_nan_artist`, which asserted the crash. Both real call
sites (`embed.build_corpus`, `canonical.canonical_key`) always pass
`artist_from_channel`'s output as `artist`, and that function itself already
guards NaN and never returns it — so, like the title-side guard before it,
this closes a latent/defensive gap, not a currently-firing one.

Both fixes match the codebase's existing idiom (`x != x`, the same
self-inequality NaN check already used in `normalise_title`,
`artist_from_channel`, and `canonical.canonical_key`) rather than introducing
`pd.isna()` as a second convention.

## Provenance

- Base commit: `b655826f9d70aca4e482f15c9eac58888e9e86c3` (HEAD at
  measurement time; working tree clean apart from an untracked
  `AUDIT_REPORT.md`, unrelated).
- Date: 2026-09-19.
- Both "before" and "after" measurements ran on this machine, same session,
  same SQLite database (`data/` is gitignored; nothing in this brief writes
  to it) — the only variable between them is the code change itself.
  "Before" was captured to a scratch JSON file prior to editing either
  source file; "after" re-ran the identical measurement post-edit and
  diffed against it — the same method `reports/normalise_title_fix.md` used
  for this identical bug family, since pre-fix code ceases to exist in the
  tree once the fix lands (no permanent before/after script; see that
  report for precedent).
- `embed.MIN_SAMPLES` = 2 (shipped default, unchanged). PCA `random_state=0`
  (deterministic); HDBSCAN has no internal randomness given fixed input.

## A3.1 — how many of the 2,918 canonical tracks have a changed `embed_text`

**Zero, across all three modes.** Both structurally guaranteed and measured:

- *Structural:* `artist_from_channel` already guards NaN (fixed in `f689446`)
  and never returns one. `build_corpus` always calls
  `strip_artist_from_title(clean_title, artist)` with that function's
  output, so the new `artist != artist` branch can never evaluate `True` on
  any code path `build_corpus` exercises. The new guard is reachable only by
  a caller that passes a raw NaN artist directly — no such caller exists
  today.
- *Measured:* `build_corpus` was run for all three modes (`title_artist`,
  `title`, `title_genre`) over the full 2,918-row canonical frame, before
  and after the fix, and diffed by `video_id`. 0 differences in every mode.

## A3.2 — does `alias()` behaviour change for any playlist name currently in the data

**No currently-reachable name changes.** Checked against both paths that can
produce a playlist-name value:

- The SQL-backed path `aliases_for()`/`playlist_ground_truth()` actually use
  (`sqlite3`, not pandas): 52 distinct names. A SQLite `NULL` becomes Python
  `None` through this path, never a float NaN — already handled by the
  pre-existing `name is None` branch, unchanged by this fix.
- The pandas-read path `scripts/build_notebook.py` uses
  (`pd.read_sql("SELECT title FROM playlists", conn)`, then
  `redact_series`): 58 rows, **0 of which are NaN** in the current database.

The only output that changed was a synthetic, out-of-band probe
(`alias(float("nan"), mapping)`, not backed by any real row):
`"Playlist ?"` → `"(none)"`. **This fix closes a defensive/latent gap and
changes zero currently-published pseudonyms** — a valid and expected result
given A3.1's structural argument applies here too (nothing upstream of
`alias()` in the current data actually produces a float NaN).

## A3.3 — ARI for all three modes, before/after, under all three noise conventions

Ground truth: `canonical_ground_truth()`, pool 480 (3 conflicts dropped),
unchanged before/after (this fix touches neither ground-truth construction
nor clustering input). Harness: `coherence_by_convention()`.

The brief asks for "twelve numbers before, twelve after" and the acceptance
criteria restate this as "3 modes × 3 conventions × before/after"; 3×3×2 is
18, not 24, and there is no fourth dimension either statement identifies —
reported as a discrepancy rather than silently reconciled. The full,
untruncated 3×3×2 = 18-row ARI matrix is below (NMI and purity included as
free extra columns, since `coherence_by_convention()` returns them in the
same call — mirroring `reports/ground_truth_ids.md`'s table shape rather
than dropping columns to hit a miscounted target).

| mode | convention | when | n_eval | total_labelled | ari | nmi | purity |
|---|---|---|---:|---:|---:|---:|---:|
| title_artist | exclude | before | 261 | 480 | 0.656104 | 0.625851 | 0.674330 |
| title_artist | exclude | after | 261 | 480 | 0.656104 | 0.625851 | 0.674330 |
| title_artist | single_cluster | before | 480 | 480 | 0.141484 | 0.410664 | 0.441667 |
| title_artist | single_cluster | after | 480 | 480 | 0.141484 | 0.410664 | 0.441667 |
| title_artist | singletons | before | 480 | 480 | 0.413993 | 0.639355 | 0.822917 |
| title_artist | singletons | after | 480 | 480 | 0.413993 | 0.639355 | 0.822917 |
| title | exclude | before | 197 | 480 | 0.379859 | 0.452961 | 0.477157 |
| title | exclude | after | 197 | 480 | 0.379859 | 0.452961 | 0.477157 |
| title | single_cluster | before | 480 | 480 | 0.031429 | 0.229424 | 0.287500 |
| title | single_cluster | after | 480 | 480 | 0.031429 | 0.229424 | 0.287500 |
| title | singletons | before | 480 | 480 | 0.193310 | 0.582704 | 0.785417 |
| title | singletons | after | 480 | 480 | 0.193310 | 0.582704 | 0.785417 |
| title_genre | exclude | before | 340 | 480 | 0.336512 | 0.433098 | 0.391176 |
| title_genre | exclude | after | 340 | 480 | 0.336512 | 0.433098 | 0.391176 |
| title_genre | single_cluster | before | 480 | 480 | 0.168256 | 0.334664 | 0.337500 |
| title_genre | single_cluster | after | 480 | 480 | 0.168256 | 0.334664 | 0.337500 |
| title_genre | singletons | before | 480 | 480 | 0.253884 | 0.511795 | 0.568750 |
| title_genre | singletons | after | 480 | 480 | 0.253884 | 0.511795 | 0.568750 |

**Byte-identical before vs after, every mode, every convention** — the
direct consequence of A3.1's zero `embed_text` changes (identical corpus in
→ identical HDBSCAN clustering out → identical ARI/NMI/purity).

**Correctness gate:** all nine "after" rows here reproduce
`reports/ground_truth_ids.md`'s own already-published pool=480 "after"
figures exactly (e.g. `title_artist`/`single_cluster` 0.141484 ≈ 0.1415;
`title_genre`/`single_cluster` 0.168256 ≈ 0.1683; all nine checked, all
nine match to the 4 decimals that report publishes). This is an
independent cross-check, not a copy — this report's numbers were computed
fresh, from a separate script, before comparing.

## A3.4 — does the mode ranking change under any convention

**No.** Unchanged from the current published state in every convention:

| convention | ranking (ARI) |
|---|---|
| exclude | title_artist (0.6561) > title (0.3799) > title_genre (0.3365) |
| single_cluster | title_genre (0.1683) > title_artist (0.1415) > title (0.0314) |
| singletons | title_artist (0.4140) > title_genre (0.2539) > title (0.1933) |

The `single_cluster` flip (`title_genre` > `title_artist`) is CLAUDE.md's
already-known open item 10 — untouched by this fix, reproduces identically,
not re-litigated here.

## Test coverage added

- `tests/test_redact.py` (new file — no test previously existed for
  `redact.py`): `TestAlias` — `None` still returns `"(none)"`, a known name
  still resolves, an unknown name still falls back to `"Playlist ?"`, and
  the new regression, `test_handles_nan_name` (`alias(float("nan"), {})`
  now returns `"(none)"`).
- `tests/test_embed.py::TestStripArtistFromTitle`: replaced
  `test_does_not_guard_a_nan_artist` (which asserted the pre-fix crash) with
  `test_handles_nan_artist`, asserting the fixed contract — same as a
  missing artist, the title comes back unchanged. Updating rather than
  deleting matches the precedent `029319e` itself set for this exact
  situation.
- Both new/changed assertions verified to fail against pre-fix code before
  the fix was verified to pass: source-only changes were `git stash`ed
  (test files untouched), both tests run red (`AssertionError` for
  `alias`, `AttributeError` for `strip_artist_from_title`), then the stash
  was popped and both tests re-run green. No other test in either file
  moved during this isolation check (8 passed alongside the 2 expected
  failures; all 10 passed after the pop).

## Full suite

**513 collected: 512 passed, 1 failed** — the same, sole, pre-existing
`tests/test_dormancy.py::TestAgainstRealDatabase::test_qualifying_clusters_includes_the_three_labelled_ones`
failure recorded at this brief's gate (wall-clock dependent; Part B's
target), unrelated to this fix and unchanged by it. 509 (gate) + 4 net new
tests (`test_redact.py` adds 4; `test_embed.py` replaces 1-for-1) = 513.

## What this does and does not establish

- Does not change which noise convention `coherence()` uses by default, and
  does not touch `README.md` — both remain Udit's call, unaffected by a fix
  that (measured above) moves nothing this table reports on.
- Does not re-tune `min_samples` or any other clustering parameter.
- Closes 2 of CLAUDE.md open item 8's 3 entries (`redact.alias`,
  `embed.strip_artist_from_title`'s artist side). The third
  (`scripts/genre_coverage.py`'s `label_counts` hash-seed tie-break) is
  untouched — out of scope for this brief.
