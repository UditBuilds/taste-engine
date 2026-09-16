# Defect audit — B4

Inventory only, per the brief: **nothing below is fixed in this pass.**
Searched for remaining instances of the two bug families this session's
work has now hit three times between them:

1. unguarded NaN reaching a string conversion (`bool(float('nan'))` is
   `True`, so `if not X` alone lets a NaN `X` fall through to `str(X)` ->
   the literal string `"nan"`, or to `X.method()` -> a crash).
2. tie-breaks resolved by unordered iteration or string hashing
   (`Counter.most_common()`'s tie order comes from dict-insertion order,
   which traces back to iterating a Python `set()` of strings - and set
   iteration order for strings is randomised per process by
   `PYTHONHASHSEED` unless pinned).

Run after B1, B2 and B3 landed, so "remaining" reflects the current tree,
not the tree this brief started from - `embed.artist_from_channel` (fixed
`f689446`), `embed.normalise_title`/`strip_artist_from_title`'s title side
(fixed this brief, Part A), `writer._modal_genre` (fixed `60ab22c`-era) and
`genre_coverage._modal()` (fixed this brief, B2) do **not** appear below.

## Family 1 — unguarded NaN reaching a string conversion

### `redact.py:81` (`alias()`)

```python
def alias(name, mapping: dict[str, str] | None = None) -> str:
    """Pseudonym for one playlist title. Unknown names never leak through."""
    if name is None:
        return "(none)"
    mapping = load_aliases() if mapping is None else mapping
    return mapping.get(str(name), PREFIX + "?")
```

`if name is None` does not catch a float NaN - `str(nan)` would proceed to
`mapping.get("nan", ...)`. **Reachable**, not just theoretical:
`redact_series()` (`redact.py:87`) applies `alias()` across an arbitrary
pandas Series via `.map(...)`, and is called at
`scripts/build_notebook.py:90` (`pl['label'] =
redact.redact_series(pl.title, ...)`) on a `title` column that can contain
missing values. The call site this brief traced through in detail
(`cluster_eval.playlist_ground_truth`) is *not* affected - it reads raw
`sqlite3` rows, where SQL NULL surfaces as Python `None`, not NaN, so
`is None` already catches it there.

**Consequence is real but mild**, unlike the embed.py cases: a NaN `name`
stringifies to `"nan"`, which will not match any registered alias, so
`mapping.get("nan", PREFIX + "?")` falls through to the same
*already-designed* "unknown name" fallback every other unmapped name gets
- not a fabricated-but-plausible label. Not confirmed either way whether
`pl.title` in `build_notebook.py`'s actual current data ever contains a
real NaN at the point `redact_series` is called - not traced further,
per this section's own "inventory, not investigation" scope.

### `embed.strip_artist_from_title`'s `artist` parameter

Found and left deliberately unfixed during this brief's own Part A (full
detail: `reports/normalise_title_fix.md`, "Known, deliberately not fixed
here"). The guard added there covers `title` only, matching
`normalise_title`'s exact pattern per the brief's own instruction; a NaN
`artist` still reaches `artist.lower()` unguarded:

```pycon
>>> strip_artist_from_title("Some Title", float("nan"))
AttributeError: 'float' object has no attribute 'lower'
```

Unreachable via either real call site today (`embed.build_corpus`,
`canonical.canonical_key`) - both always pass `artist_from_channel`'s
output, which is never NaN. Covered by
`tests/test_embed.py::TestStripArtistFromTitle::test_does_not_guard_a_nan_artist`,
which asserts the crash rather than silently letting a future "fix" make
it disappear unnoticed.

### Checked and ruled out (for completeness, not exhaustively re-derived here)

- `lastfm.py` in full: `_clean()` already guards both `None` and NaN
  correctly (the fix CLAUDE.md's State section credits to this module);
  `_channel_recognisably_encodes_artist` and `strip_release_furniture`/
  `strip_feat` only ever receive `_clean()`-sanitised or
  `resolve_artist_track()`-returned strings at their real call sites -
  traced through `resolve_artist_track`'s every return path, all end in
  `.strip()` on a real string, never a raw NaN.
- `classify._genres_from_topics`: `if not raw` doesn't catch NaN either,
  but a NaN `raw` reaching `json.loads(nan)` raises `TypeError`, caught by
  the function's own `except (TypeError, ValueError): return []` -
  produces the same `[]` either way. Inert, not a defect.
- `writer.status_rows`'s `playlist_url` construction had exactly this bug
  (`if pid else ""` on a `playlist_id` that comes back as NaN, not `None`,
  for a rolled-back row once the column also holds real strings) - caught
  live against the real database and fixed within this same brief (B3);
  not listed above since it no longer exists in the tree.

## Family 2 — tie-breaks resolved by unordered iteration or string hashing

### `scripts/genre_coverage.py:319-322` (module-level `label_counts`, in `main()`)

```python
label_counts = Counter()
for gl in frame["genres_tidy"]:
    label_counts.update(set(gl))
top15 = label_counts.most_common(15)
```

Feeds the "Top 15 genre labels by canonical-track count" table. Same
mechanism B2 just fixed in this file's `_modal()` - `.update(set(gl))`
inserts in the set's hash-seed-dependent iteration order, so a count tie
at the 15th/16th-place boundary can print a different label there across
process runs. A **separate** `Counter` instance from `_modal()`'s (not
touched by B2's fix, which only changed how a `Counter`'s current contents
are read, not how any other `Counter` gets built) - not confirmed whether
a tie actually sits at today's 15th/16th boundary (unlike `_modal()`,
where 16 of 37 clusters' top-1 ties were directly measured - see B2's
commit message); flagged on the mechanism alone, the same standard the
rest of this inventory uses.

### Checked and ruled out

- `scripts/lastfm_coverage.py:146-147` (`Counter(grp["artist"])`) and
  `scripts/compare_backfill_ranking.py:70,121,125` (`Counter(all_ids)`):
  both build their `Counter` from an already-ordered pandas Series or
  Python list (row order / insertion order), never from iterating a
  `set()` - dict/Counter iteration itself is insertion-order-stable since
  Python 3.7, so these are *not* hash-seed-dependent, unlike the two
  flagged instances above. Deterministic by construction, not just
  observed to be so.
- `scripts/verify_write_plan.py:30` (`Counter(keys).items()`): `keys` is a
  list comprehension over `t.iterrows()`, same reasoning - deterministic
  row order in, and it's used to *filter* (`n > 1`), not to pick a single
  "winner" by position, so even a hypothetical order difference couldn't
  change which keys are flagged as duplicates.
- `.idxmax()` call sites (`canonical.py:339`, `evaluate.py:704,729`,
  `writer.py:400`, `dormancy_probe.py:87`, `genre_coverage.py:272`):
  `pandas.Series.idxmax()` is documented to return the *first* row label
  achieving the maximum, which is deterministic given a deterministic
  Series order; the three `value_counts().idxmax()` sites all operate on
  an integer `cluster` column, and Python's `hash()` for `int` is not
  seed-randomised (only `str`/`bytes` are) - different mechanism, not the
  same bug family.
- `genre_coverage.label_cluster_spread`'s `seen.update(gl)` (a `set`, not
  a `Counter`) only feeds a later *membership test*
  (`label not in non_discriminative`), never a positional "first/most
  common" selection - iteration order can't change the output set.

## Methodology

Grepped `src/taste_engine/*.py` and every file in `scripts/` for both
families' signatures (`if not <text-var>` without `!= self`/`isinstance`,
`Counter(`, `.most_common(`, `set(`/`sorted(set(` feeding an output,
`.iterrows()` alongside a markdown/table-rendering helper, `.idxmax()`)
and read the context around every hit rather than pattern-matching alone -
several candidates that matched the grep were traced through their actual
call sites and ruled out above, not omitted silently. Not a formal static
analysis; a third, unrelated bug shape could exist that neither pattern
would surface.
