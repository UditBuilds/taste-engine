# Embedding-mode comparison — re-measured

**`title_artist` still wins on every metric after re-measurement on current
data — the ranking (who wins) did not change.** What did change: the margin
over `title_genre` narrowed by ~21% (ARI gap 0.230 → 0.182), matching this
brief's own hypothesis that duplicate collapse plausibly helps `title_genre`
more than `title_artist`. The `title` (bare-title) mode moved the most of
the three — its ARI more than doubled (0.180 → 0.383) — without threatening
the overall winner. One secondary-metric reordering did happen: on NMI
specifically (not the primary ARI ranking the README's prose leads with),
`title_genre` now edges out `title` (0.478 vs 0.452); under the README's old
numbers `title` was ahead on NMI (0.611 vs 0.458). Flagged because it's a
real, measured reordering, even though it doesn't touch the headline
conclusion.

## Provenance

- Commit: `cde906eec8b1d31ef396fa7621d520047b32ee3a` (HEAD at measurement
  time; working tree clean — confirmed via `git status --porcelain`).
- Date: 2026-09-15.
- Part A ran on this commit **unmodified** — no code changed between this
  measurement and the commit above.
- Dataset counts at measurement time:

  | table | count |
  |---|---:|
  | `plays` | 40,619 |
  | `video_metadata` | 30,440 |
  | `playlist_tracks` | 11,475 |
  | distinct playlists | 48 |
  | canonical music tracks (`score.scored_tracks` defaults) | 2,918 |

- Ground truth: ARI is scored against the user's own YouTube playlist
  filings (`playlist_tracks`), restricted to videos filed in exactly one
  playlist — human curation, not derived from track title or artist text.
  (Full derivation and the artist-dominance check: `reports/lastfm_coverage.md`
  §0.)
- Harness: `cluster_eval.compare_modes(conn, tracks)`, default params
  (`embed.MIN_CLUSTER_SIZE=8`, `MIN_SAMPLES=2`, `PCA_COMPONENTS=20`,
  unchanged) — the same function `python -m taste_engine.cluster_eval` runs.

## Part A — three-mode comparison, README vs current, unmodified code

### `title_artist`

| metric | README | current | delta |
|---|---:|---:|---:|
| ARI | 0.627 | 0.6525 | +0.0255 |
| NMI | 0.627 | 0.6330 | +0.0060 |
| purity | 0.668 | 0.6795 | +0.0115 |
| coverage | 53% | 53.4% | +0.4pp |
| clusters | 45 | 37 | −8 |
| noise | 44% | 45.2% | +1.2pp |
| n_eval | — (not printed in README table) | 234 | — |

### `title` (bare title, artist stripped)

| metric | README | current | delta |
|---|---:|---:|---:|
| ARI | 0.180 | 0.3831 | **+0.2031** |
| NMI | 0.611 | 0.4520 | −0.1590 |
| purity | 0.563 | 0.4674 | −0.0956 |
| coverage | 25% | 42.0% | +17pp |
| clusters | 51 | 19 | **−32** |
| noise | 70% | 56.9% | −13.1pp |
| n_eval | — | 184 | — |

### `title_genre`

| metric | README | current | delta |
|---|---:|---:|---:|
| ARI | 0.397 | 0.4705 | +0.0735 |
| NMI | 0.458 | 0.4784 | +0.0204 |
| purity | 0.437 | 0.4440 | +0.0070 |
| coverage | 67% | 63.2% | −3.8pp |
| clusters | 33 | 32 | −1 |
| noise | 41% | 44.4% | +3.4pp |
| n_eval | — | 277 | — |

## Winner, and by how much

**`title_artist` wins on every metric, both in the README's numbers and in
the current re-measurement.** Current ARI gaps: `title_artist` (0.6525) beats
`title_genre` (0.4705) by **0.182** and `title` (0.3831) by **0.269**.

The `title_artist`-vs-`title_genre` gap **narrowed** from 0.230 (README) to
0.182 (current) — a ~21% relative narrowing, in the direction this brief's
§1 hypothesized (duplicate uploads carry inconsistent genre tags, so
collapsing them plausibly helps a genre-keyed embedding more than an
artist-keyed one). The gap did not close, reverse, or come close to
reversing — `title_artist` remains the clear winner on current data — but
"the gap may have narrowed" (brief §1) is now a measured fact, not a
hypothesis.

`title`'s ARI **more than doubled** (0.180 → 0.383) and its cluster count
dropped by nearly two-thirds (51 → 19), the largest absolute shift of the
three modes. Consistent with the same underlying cause: duplicate,
near-identical bare titles (no artist to distinguish "TBH" by one artist from
"TBH" by another) were plausibly fragmenting `title`-mode clustering into
many small, low-coverage, high-noise clusters before collapse; canonical
collapse removes exactly that duplication. This is reported as an
observation consistent with the collapse explanation, not verified by
re-running with collapse toggled off - that would be a second measurement
this brief did not ask for.

**Ranking did not change** on the metric the README's prose leads with
(ARI: `title_artist` > `title_genre` > `title`, in both the old and current
numbers). It did change on NMI specifically: README's numbers had `title`
(0.611) ahead of `title_genre` (0.458); current numbers have `title_genre`
(0.478) ahead of `title` (0.452) — a swap of 2nd and 3rd place on that one
metric. Reported because it's real and measured, not because it changes any
conclusion this repository currently draws (which is stated in terms of ARI).

---

## Part B — the `artist_from_channel` NaN fix and its delta

**The fix, matching `canonical.canonical_key`'s existing idiom rather than
inventing a second one** (`embed.py`):

```python
if not channel or channel != channel:
    return ""
```

One condition added to the existing check (`channel != channel` is true
only for float NaN) - not a second, separate `is None` block, since
`if not channel` already covers `None` and `""`. All 387 tests pass
(345 baseline + 42 Last.fm + this brief's new ones); the audit below and
the regression tests are in `tests/test_embed.py`.

### Measured, not predicted: which tracks actually changed

Before touching `embed.py`, `build_corpus()` was run on the 9 known
NaN-channel canonical tracks for all three modes and the output captured
verbatim. The same probe was re-run immediately after the fix. Full
before/after text for all 9 tracks, all 3 modes, is in this session's
record; the outcome:

- **`title_artist` mode: 2 of 9 tracks changed.** The 2 tracks with a real
  (if junk-looking) title lost a bogus `" - nan"` suffix -
  `'performance conversion NnekaTestimonial Music video 16x9 60s en V2 Tools, Licensing - nan'`
  → `'performance conversion NnekaTestimonial Music video 16x9 60s en V2 Tools, Licensing'`,
  and similarly for the Spotify-promo track. **The other 7 (NaN title *and*
  NaN channel) are unchanged - still the literal string `'nan'`, identically,
  both before and after.** Verified, not assumed: `f"{clean_title} - {artist}".strip(" -")`
  with `clean_title == "nan"` (from `normalise_title`'s own, separate,
  unfixed NaN gap - see below) reduces to `"nan"` whether `artist` is the
  bug's old `"nan"` or the fix's correct `""` - the fix cannot rescue a track
  whose title-side text is already degenerate for an unrelated reason.
- **`title` and `title_genre` modes: 0 of 9 tracks' text changed.** Both
  modes only use `artist` to strip a leading prefix from the title
  (`strip_artist_from_title`); for all 9 tracks - junk titles included -
  that prefix never matched in the first place, buggy or fixed, so the
  fix is a no-op for every track in these two modes.

### The re-measurement, and an artifact that needed explaining

Re-running `compare_modes` post-fix:

| mode | metric | Part A (pre-fix) | Part B (post-fix) | delta |
|---|---|---:|---:|---:|
| `title_artist` | ARI | 0.6525 | 0.6494 | **−0.0031** |
| | NMI | 0.6330 | 0.6326 | −0.0004 |
| | purity | 0.6795 | 0.6793 | −0.0001 |
| | coverage | 53.4% | 54.1% | +0.7pp |
| | clusters | 37 | 38 | +1 |
| | noise | 45.2% | 45.0% | −0.3pp |
| | n_eval | 234 | 237 | +3 |
| `title` | ARI | 0.3831 | 0.3831 | **0 (byte-identical)** |
| | all other fields | — | — | **0 (byte-identical)** |
| `title_genre` | ARI | 0.4705 | 0.4705 | **0 (byte-identical)** |
| | all other fields | — | — | **0 (byte-identical)** |

**`title` and `title_genre` moved by exactly zero, on every field, to every
decimal place printed** - confirming the "0 of 9 texts changed" finding
above at the whole-pipeline level, not just for the 9 rows individually
inspected.

**`title_artist` moved by a small but real amount, and not in the "obviously
correct" direction** - ARI went *down* very slightly (−0.0031, ~0.5%
relative), not up, even though the fix removes visible garbage from the
input. Plausible and unsurprising on reflection: the 2 corrected tracks are
themselves junk (an ad-testimonial script, a Spotify promo clip), not real
songs with a meaningful genre identity - "fixing" their text makes them
*less obviously wrong* without making them *more clusterable*, and 3 more
ground-truth-overlapping tracks entered the evaluated pool (n_eval 234→237,
clusters 37→38) with a very slightly worse alignment. The footprint (9
tracks, 0.3%) matches this brief's own expectation, and the ARI delta is
small - reported exactly as measured, not smoothed toward the "the fix
helped" story a reader might expect.

**An artifact worth resolving rather than leaving unexplained:** the
embedding-cache file hash changed for *all three* modes post-fix, including
`title`/`title_genre`, whose corpus text is provably unchanged (above).
Traced and confirmed: `canonical.canonical_key()` also calls
`artist_from_channel(channel)`, and for the 2 real-title NaN-channel tracks
the fix changes their canonical key's prefix from `"nan|..."` to `"?|..."`
(verified directly: `hTYsajteUpc` → `'?|nnekatestimonial'`,
`RowcnrYWra0` → `'?|bebo spills the tea'`). `"?"` sorts before `"n"`, so
`canonical.collapse()`'s internal `sort_values(["canonical_key", ...])`
places these two rows differently, which shifts `groupby(sort=False)`'s
first-appearance order, which - combined with pandas' non-stable default
sort and score ties elsewhere among 2,918 tracks - changes the row order
`scored_tracks()` returns, without changing the *set* of canonical tracks or
their scores. This was verified empirically rather than left as a plausible
story: re-running `build_corpus` twice in a row on identical (post-fix)
code produced the identical cache hash both times (ruling out run-to-run
nondeterminism), and `title`/`title_genre`'s zero-delta re-measurement
confirms HDBSCAN and the ARI computation are order-invariant for this
corpus in practice - the reordering is real but inert. Whether
`title_artist`'s small delta is caused by its 2 genuinely-changed texts,
by this same incidental reordering, or both together was not decomposed
further - that would be a second, controlled experiment this brief did not
ask for.

### Audit: other missing NaN guards in `embed.py`

Not fixed - only `artist_from_channel` is in scope for this brief.

- **`normalise_title` has the identical bug**, confirmed still present and
  reachable: `if not title: return ""` does not catch NaN, so
  `normalise_title(float('nan'))` still returns the literal string `'nan'`
  (`tests/test_embed.py::TestTitleNormalisation::test_nan_title_is_a_known_unfixed_gap`).
  This is the dominant remaining source of degenerate embedding text - it
  alone accounts for all 7 of the 9 tracks that stayed at `'nan'` above.
- **`strip_artist_from_title` has no guard and is a latent crash risk, not
  a silent-corruption risk**: `if not artist or not title: return title`
  would let a raw float NaN `title` fall through to `title.lower()`, which
  raises `AttributeError` (a float has no `.lower()`) rather than silently
  producing bad text. Currently unreachable in any shipped call path -
  `build_corpus` always passes `clean_title` (already stringified by
  `normalise_title`) - so this has never fired, but a future direct caller
  with an un-normalised title would crash.
- **`tidy_genres`/`_tidy_genre` are not exposed to this bug class.**
  `tidy_genres` guards with `isinstance(genres, (list, tuple))` - a type
  check, not a truthiness check - so a NaN `genres` cell (a float) is
  correctly rejected before `_tidy_genre` (which has no NaN guard of its
  own) ever sees an individual element. Genre lists come from parsed JSON,
  where a bare NaN element inside an already-valid list is not a realistic
  input shape.
- **`name_cluster` needed no changes and now benefits from the fix**: it
  calls `artist_from_channel` and explicitly drops blank results
  (`.replace("", np.nan).dropna()`); post-fix, a NaN-channel track's
  now-correctly-empty artist is dropped as intended, instead of being
  counted as a fake artist named `"nan"`.
