# `normalise_title` NaN guard — fix and re-measurement

**`embed.normalise_title` had the same NaN-truthiness bug as the already-fixed
`artist_from_channel`, and it was the dominant cause of the "still `nan`"
residue that fix left behind.** `bool(float('nan'))` is `True` in Python, so
`if not title` let a NaN title fall through to `str(title)` — the literal
3-character string `"nan"`. Fixed by matching the exact idiom
`canonical.canonical_key` already uses (`if title is None or title != title`),
not a second one. The same guard was also added to
`embed.strip_artist_from_title`, defensively — see "Known, deliberately not
fixed" below.

## Provenance

- Base commit: `68bf8397d5475c519697426d0bf3802874906404` (HEAD at
  measurement time; working tree clean at the start of this brief).
- Date: 2026-09-16.
- Both the "before" and "after" measurements below ran on this machine, same
  session, same SQLite database (`data/` is gitignored and nothing in this
  brief writes to it) — the only variable between them is the code change
  itself.
- Dataset counts, confirmed identical before and after (see "Canonical-layer
  invariance" below):

  | table | count |
  |---|---:|
  | canonical music tracks (`score.scored_tracks` defaults) | 2,918 |
  | canonical tracks with a NaN title | 7 |

## The "0.646" figure in the brief

The brief that requested this fix stated the last recorded post-fix figures
as `title_artist` 0.646 / `title_genre` 0.470 / `title` 0.383. **Measured
"before" (unmodified code): 0.649351 / 0.470492 / 0.383064** — matching
CLAUDE.md's open item #6 ("Current: `title_artist` 0.649...") and
`reports/embedding_modes_remeasured.md`'s Part B figure (0.6494) almost to
the decimal, not the brief's 0.646. Per this brief's own stop condition
(§A2): a genuine third-cause drift would be expected to move all three
figures, or move them away from both prior sources at once. Here, two of
three (`title_genre` 0.470492, `title` 0.383064) match **both** CLAUDE.md and
the prior report exactly, and the third (`title_artist` 0.649351) also
matches both of those same sources, just not the brief's own citation of
them. **Conclusion: the brief's "0.646" is a citation slip (off by 0.003),
not new drift.** Continuing per §A2's instruction for the reproducing case.

## Canonical-layer invariance (verified, not assumed)

`canonical.canonical_key` returns `""` for a NaN title *before* it ever calls
`normalise_title` or `strip_artist_from_title` (canonical.py:139, checked
ahead of line 150/151) — so this fix, unlike the earlier `artist_from_channel`
one, cannot touch canonical grouping at all. Verified rather than only
argued:

- Canonical track count: **2,918 before, 2,918 after.**
- NaN-title track count and identity: **7 before, 7 after, the same 7
  `video_id`s** (`-ErZ9-Nrcnc`, `9HCxhQsRBdg`, `AIM7vDvUAnw`, `HIrRlN4fpCs`,
  `iLHCn6C9AsQ`, `sFSVW3YkO8U`, `x-mar1osQdY`).
- `video_id` sequence hash (order + membership of `scored_tracks()`'s output,
  independent of score): **`9e8f7955522295e51a3344ccfb3b65b4f368d8541bd946c2fa677b5a1692fd82`
  both before and after — byte-identical.**
- A separate fingerprint that additionally includes each row's `score`
  *does* differ (`9b9ac79c...` → `b219378...`). This is not evidence against
  invariance: `score.scored_tracks(conn)` defaults `as_of` to the current
  wall-clock time, several minutes of real time elapsed between the before
  and after runs, and every row's recency-decayed score shifts continuously
  with time regardless of any code change — the same drift
  `scripts/genre_coverage.py` already documents ("score is computed
  `as_of=now()` ... so it legitimately drifts... between measurements taken
  at different times"). Title and channel are masked to a constant `"NAN"`
  placeholder in this fingerprint for missing values, so neither could be
  the source of the difference either way. The order-only hash above is the
  correct invariance signal, and it matches exactly.

All 7 NaN-title tracks also have a NaN channel (confirmed both times) —
consistent with `reports/embedding_modes_remeasured.md`'s finding that 7 of
the 9 NaN-channel tracks stayed at the literal string `"nan"` even after the
`artist_from_channel` fix, because their title-side text was independently
degenerate.

## Part 1 — three-mode comparison, before vs after (unmodified `title_artist` numbers repeated for cross-reference against CLAUDE.md)

Harness: `cluster_eval.compare_modes(conn, tracks)`, default params
(`embed.MIN_CLUSTER_SIZE=8`, `MIN_SAMPLES=2`, `PCA_COMPONENTS=20`,
unchanged). Each side (before, after) run twice as two separate processes —
byte-identical both times in both cases, so nothing below is HDBSCAN
run-to-run noise.

### `title_artist`

| metric | before | after | delta |
|---|---:|---:|---:|
| ARI | 0.649351 | 0.665487 | **+0.016136** |
| NMI | 0.632646 | 0.637697 | +0.005051 |
| purity | 0.679325 | 0.684874 | +0.005549 |
| coverage | 54.11% | 54.34% | +0.23pp |
| clusters | 38 | 37 | −1 |
| noise | 44.96% | 44.83% | −0.14pp |
| n_eval | 237 | 238 | +1 |

### `title` (bare title, artist stripped)

| metric | before | after | delta |
|---|---:|---:|---:|
| ARI | 0.383064 | 0.370727 | −0.012337 |
| NMI | 0.452000 | 0.453698 | +0.001698 |
| purity | 0.467391 | 0.462766 | −0.004625 |
| coverage | 42.01% | 42.92% | +0.91pp |
| clusters | 19 | 24 | +5 |
| noise | 56.92% | 54.83% | −2.09pp |
| n_eval | 184 | 188 | +4 |

### `title_genre`

| metric | before | after | delta |
|---|---:|---:|---:|
| ARI | 0.470492 | 0.366119 | **−0.104373** |
| NMI | 0.478383 | 0.445179 | −0.033204 |
| purity | 0.444043 | 0.394904 | −0.049139 |
| coverage | 63.24% | 71.69% | **+8.45pp** |
| clusters | 32 | 25 | −7 |
| noise | 44.38% | 36.02% | −8.36pp |
| n_eval | 277 | 314 | +37 |

## Part 2 — did the winning mode change?

**No — `title_artist` wins on ARI both before (0.649) and after (0.665).**
But the ranking *below* the winner did change, on the primary metric the
README leads with, not just a secondary one like the prior brief's NMI swap:
before, `title_genre` (0.470) was clearly 2nd and `title` (0.383) 3rd; after,
`title` (0.371) edges narrowly into 2nd and `title_genre` (0.366) drops to
3rd. Flagged because it is real and measured and touches the primary metric,
even though it does not change the headline (`title_artist` wins) any
README conclusion is currently drawn from.

**This makes CLAUDE.md's open item #6 and README's embedding-mode table
stale as of this commit** (they cite 0.649/0.470/0.383). Per §A4 this
report's commit is scoped to `embed.py` + tests + this report only, so
those two documents are deliberately not touched here — flagged instead in
this session's final report back to Udit as an open decision, per this
project's "withdraw/update wrong numbers in public" rule and CLAUDE.md open
item #6's own warning that this is a pattern, not a one-off.

## Part 3 — pinned eval, before vs after, per strategy

Two commands, matching `reports/eval_invariance_embed_remeasure.txt`'s
precedent: the literal pinned command (`--test-end`, replay-only — it and
`--rediscovery`/`--both` are mutually exclusive in `evaluate.py`'s argparse)
plus a `--both --test-days 30` companion to actually exercise rediscovery
and `cluster_diverse`. Each run twice as separate processes on each side —
byte-identical both times in both cases.

```
A. bash scripts/run.sh -m taste_engine.evaluate --split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14
B. bash scripts/run.sh -m taste_engine.evaluate --split 2026-06-01 --test-days 30 -k 50 --half-life 14 --both
```

### Command A (replay, `--test-end 2026-07-01`)

| strategy | field | before | after | moved? |
|---|---|---:|---:|---|
| score | hits/precision@50/ndcg@50/spearman | 31 / 0.62 / 0.5506 / 0.3583 | 31 / 0.62 / 0.5506 / 0.3583 | **no — byte-identical** |
| most_played | same | 32 / 0.64 / 0.5421 / 0.4300 | 32 / 0.64 / 0.5421 / 0.4300 | **no — byte-identical** |
| recency | same | 22 / 0.44 / 0.3088 / 0.2620 | 22 / 0.44 / 0.3088 / 0.2620 | **no — byte-identical** |
| cluster_diverse | same | 27 / 0.54 / 0.3080 / NaN | 25 / 0.50 / 0.3360 / NaN | **yes** (expected — the only strategy that reads clustering output) |

### Command B (rediscovery, single split + across-4-splits summary, plus the same replay at 30d)

| table | strategy | before | after | moved? |
|---|---|---|---|---|
| rediscovery (single split) | recency | hits 12 / recall 0.0335 / prec 0.6 / ndcg 0.3299 | same | no |
| | score | hits 14 / recall 0.0391 / prec 0.7 / ndcg 0.2227 | same | no |
| | most_played | hits 10 / recall 0.0279 / prec 0.5 / ndcg 0.1354 | same | no |
| | cluster_diverse | hits 12 / recall 0.0335 / prec 0.6 / ndcg 0.1688 | hits 12 / recall 0.0335 / prec 0.6 / **ndcg 0.1748** | yes (ndcg only — same hit set, reordered) |
| rediscovery (4-split summary) | score | mean_ndcg 0.3776 / mean_recall 0.0576 / beats 4/4 | same | no |
| | most_played | mean_ndcg 0.2500 / mean_recall 0.0441 / beats 0/4 | same | no |
| | recency | mean_ndcg 0.2304 / mean_recall 0.0432 / beats 2/4 | same | no |
| | cluster_diverse | mean_ndcg 0.2567 / mean_recall 0.0534 / beats 3/4 | mean_ndcg **0.2281** / mean_recall **0.0505** / beats **2/4** | yes |
| replay (30d, same window as A) | score/most_played/recency | identical to Command A | identical to Command A | no |
| | cluster_diverse | 27/0.54/0.3080 | 25/0.50/0.3360 | yes, matches Command A exactly |

**Confirmed exactly as the brief predicted: `score`, `most_played` and
`recency` are byte-identical in every table, in both commands. Only
`cluster_diverse` — the sole strategy that reads clustering output — moved,
and it moved consistently between Command A and Command B's replay table
(same window, same numbers).** No strategy required stopping under §A3
item 4.

## Part 4 — exactly how many tracks' `embed_text` changed

**Exactly 7 of 2,918 canonical tracks (0.24%), identically across all three
modes.** This is both a structural guarantee and a direct measurement:

- *Structural:* the only change to `normalise_title`/`strip_artist_from_title`
  is one added `or title != title` condition, which evaluates `False` — a
  no-op — for every title that is not NaN. No non-NaN-title row's code path
  changes at all.
- *Measured:* `df["title"].isna()` was queried directly against the full
  2,918-row canonical frame (not assumed from the prior brief's 9
  NaN-*channel* tracks, which is a different, only-partially-overlapping
  set) — 7 rows, before and after, same 7 `video_id`s.

All 7 have both a NaN title and a NaN channel, and none carry any genre
label, so all 7 collapse to the identical transformation in every mode:

| mode | before | after |
|---|---|---|
| `title_artist` | `"nan"` | `""` |
| `title` | `"nan"` | `""` |
| `title_genre` | `"nan"` | `""` |

This differs from the `artist_from_channel` fix's footprint in one important
way, worth stating plainly since it changes what "the same fix" means for
impact: that fix only changed `title_artist`'s text (2 of 9 tracks) because
`title`/`title_genre` only consume the channel/artist to strip a leading
prefix that rarely matches. `normalise_title`'s output feeds `clean_title`
directly in **every** mode, so this fix's 7 changed tracks show up in the
corpus text of all three modes, not just one.

## Part 5 — is the ARI delta attributable to the 7 tracks, or did something else move?

**The *corpus-text* delta is attributable to exactly these 7 tracks and
nothing else** — proven above both structurally and by exhaustive query, not
by sampling. **The *clustering/ARI* delta is a downstream, non-linear
consequence of HDBSCAN re-clustering the full 2,918-track corpus with those
7 embeddings changed**, not evidence that something else moved:

- The canonical layer (which rows exist, their order, their scores' time
  drift aside) is proven invariant above — ruling out a sort-order/reordering
  cascade like the one `reports/embedding_modes_remeasured.md` found for the
  `artist_from_channel` fix.
- Both the "before" and "after" measurements are internally deterministic
  (two independent process runs, byte-identical both times) — ruling out
  hash-seed or other run-to-run nondeterminism as the explanation.
- HDBSCAN is density-based (mutual-reachability distances over the whole
  point set), not point-independent, so moving 7 points from a
  shared, degenerate `"nan"`-embedding location to a different location
  (`""`, likely close to other short/sparse texts elsewhere in the corpus)
  can shift density estimates near existing cluster boundaries for *other*
  tracks too — consistent with `title_genre`'s coverage rising 8.4
  points and its cluster count dropping by 7 (n_eval alone moved by 37,
  far more than 7), and with `title`'s cluster count rising by 5. This is
  offered as the plausible mechanism, not verified by isolating and
  re-clustering with only one of the 7 changed at a time — that would be a
  separate, controlled experiment this brief did not ask for, matching this
  repository's established practice of not chasing every mechanism a
  measurement brief surfaces.

`title_artist`'s delta (+0.016 ARI) is modest and in the "obviously
plausible" direction (less garbage text should not hurt, and here it
slightly helps). `title_genre`'s delta (−0.104 ARI, the largest of the
three) is real, measured, and not smoothed toward a "the fix helped"
narrative just because the fix is a bug fix: removing a fabricated word
from 7 tracks' text measurably *hurt* that mode's agreement with the user's
own playlist filing, even as it changed the underlying representation from
"wrong" to "correct."

## A test this fix broke, and why (distinct from `cluster_diverse` moving)

Worth separating clearly from Part 3's `cluster_diverse` movement above:
that is an *expected*, governed-by-§A3 consequence of re-clustering.
This is a *different* consequence with a different cause - a test that
pinned a raw cluster id, which this fix's `title_artist`-mode reclustering
(38 -> 37 clusters) then reassigned.

`tests/test_dormancy.py::TestAgainstRealDatabase::test_qualifying_clusters_includes_the_three_labelled_ones`
asserted `{4, 11, 35} <= qualifying` - Joji, T-Series, and Lil Baby/Lil
Peep/Chris Brown's cluster ids, hardcoded. This is precisely the fragility
CLAUDE.md documents under "Cluster ids are not identifiers" ("HDBSCAN
reassigns them whenever the input set changes... nothing in the repo
records a cluster id") - this test violated that rule, and this fix's
change to `title_artist` mode's embeddings (see Part 1) is exactly the kind
of input-set change the warning is about. It failed deterministically, not
flakily: the same 45 tests before this fix, run any number of times, pass;
after it, this one specific assertion fails every time until updated.

**Checked, not assumed, that this is a test-fragility problem and not a
real regression:** re-querying `qualifying_clusters()` post-fix, all three
artists' clusters still clear FLOOR - only the numeric ids moved (Joji
4→5, T-Series 11→12, Lil Baby/Lil Peep/Chris Brown 35→36; all three shifted
by exactly +1, apparently coincidentally). Grepped the rest of `tests/` for
the same pattern (`{4, 11, 35}`, `cluster == 4/11/35`, etc.) - this is the
**only** site; Part A's blast radius on the test suite is one assertion,
not a class of them.

**Fix: resolve the three clusters by name**, matching
`dormancy_probe.find_cluster` and `writer.plan`'s own
`cluster_name.fillna("").str.contains(name, case=False, regex=False)`
idiom, rather than renumbering the hardcoded ids to today's values -
renumbering would just re-break on the next embedding change, which is the
outcome CLAUDE.md's own guidance already argues against. Landed in this
same commit, since Part A's own diff is what broke it.

**Not touched:** `reports/dormancy_signals.md`'s prose ("cluster 4, 35 and
11 respectively") now describes stale ids too, for the same reason. That is
a frozen, `as_of`-pinned report from an earlier brief, not code under test
- out of scope for a commit that touches `embed.py` + tests + this report
only. Flagged here so it isn't silently wrong for the next reader.

Full suite after this fix: **445 passed** (438 baseline + 7 new tests this
brief added - `TestTitleNormalisation.test_handles_nan_title` replaces
rather than adds, `TestStripArtistFromTitle` adds 6, `TestCorpus` adds 1
net new alongside 2 renamed/updated - 438 + 7 = 445).

## Known, deliberately not fixed here

`strip_artist_from_title` got the same title-side guard `normalise_title`
did (`if not artist or not title or title != title: return title`), matching
this brief's instruction to add "the same guard." While verifying it, a
**second, separate** NaN-crash path was found and deliberately left alone:
a NaN **artist** (not title) still reaches `artist.lower()` unguarded and
raises `AttributeError` —

```pycon
>>> strip_artist_from_title("Some Title", float("nan"))
AttributeError: 'float' object has no attribute 'lower'
```

This is not in scope for this brief, which asks for the title-side guard
specifically (matching `normalise_title`'s own fix), and it is unreachable
via either real call site today: both `embed.build_corpus` and
`canonical.canonical_key` always pass `artist_from_channel`'s output as the
`artist` argument, and that function never returns NaN (already fixed,
`f689446`). Covered by
`tests/test_embed.py::TestStripArtistFromTitle::test_does_not_guard_a_nan_artist`
(asserts the crash, so this stays visible rather than silently disappearing
if someone "helpfully" closes it later) and carried into
`reports/defect_audit.md` (Part B, B4) rather than fixed here.

## Test coverage added

`tests/test_embed.py`: `TestTitleNormalisation.test_handles_nan_title`
(replacing the old "known unfixed gap" test, per its own docstring's
instruction to update rather than delete), a new `TestStripArtistFromTitle`
class (matching prefix, non-matching prefix, missing artist, NaN title,
NaN title + missing artist, and the documented-not-fixed NaN-artist crash),
and `TestCorpus` updates covering NaN title with a real channel (now
`["Don Toliver"]`, not `["nan - Don Toliver"]`), the same case in `title`/
`title_genre` mode (now `[""]`), and NaN title + NaN channel together (now
`[""]`, not `["nan"]`).
