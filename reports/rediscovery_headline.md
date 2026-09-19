# Rediscovery headline — re-derivation and provenance

The README publishes a rediscovery result (nDCG@20 0.3312 vs. 0.1382 baseline,
+139.7%, 3/3 held-out splits, p=0.125) that traced, until now, only to
convergent secondary evidence — CLAUDE.md, the README's own prior text, two
invariance files stating the number hadn't moved — and not to one committed
artifact. This report is that artifact, produced by actually running the
evaluation, twice, and recording what came back, including three findings
that qualify what a "match" means here.

**Note on the brief itself:** the brief this report executes was pasted into
the session as `briefs/rediscovery_headline.md`. That file does not exist in
the repository or anywhere in `git log --all`. Its stated starting state
(commit `3873188`, clean tree) matched reality exactly, so the pasted text
was executed as given; the file itself was simply never committed. Not
investigated further — noted here for the record.

## Gate

- Branch `main`, tree clean, `git log --oneline -1` = `3873188` — matched
  the brief's expected starting state exactly.
- Full suite: **517 passed, 0 failed** (`scripts/run.sh -m pytest -q`,
  241.45s). Worth flagging rather than passing over silently: CLAUDE.md's
  own State section documents a *known* wall-clock-dependent failure in
  `test_dormancy.py` as of the last few briefs (508/509, 512/513-shaped
  entries). That test passed clean in this run — the flakiness is
  time-dependent and evidently didn't trigger today, not evidence the
  underlying issue was fixed.
- Tree confirmed clean again after the suite ran, before proceeding.

## Provenance

| | |
|---|---|
| Commit at run time | `3873188` |
| Command | `scripts/run.sh scripts/nested_eval.py` (no flags exist — `nested_eval.py` takes no CLI arguments) |
| Resolves to | `~/.venvs/taste-engine/bin/python scripts/nested_eval.py`, run from repo root |
| Function called | `taste_engine.evaluate.nested_rediscovery(conn)` — every argument defaulted |
| Splits | `MONTHLY_SPLITS`: 2025-12-01, 2026-01-01, 2026-02-01, 2026-03-01, 2026-04-01, 2026-05-01, 2026-06-01, 2026-07-01, 2026-08-01 |
| Half-life grid (dev sweep) | 7, 14, 30, 60, 90, 180, 365 days |
| k | 20 |
| exclude_top | 50 |
| test_days | 30 (`config.EVAL_TEST_DAYS`) |
| min_reachable | 20 |
| canonical | True |
| STRICT_MUSIC | True |
| Seed / randomness | none anywhere in the call path — see "Determinism" below |
| Date run | 2026-09-19 |
| Network / quota | zero — confirmed by code trace (no API client imported in this path) and by the runs themselves completing with no network access |
| Writes | none — stdout only; `db.connect()` touches `PRAGMA`/schema state idempotently but performs no row writes in this path |

**Row counts at run time** (all measured, none quoted from memory —
CLAUDE.md documents an incident where a remembered canonical-track count was
off by 225):

| table / quantity | count |
|---|---:|
| `plays` | 40,619 |
| `video_metadata` | 30,440 |
| canonical tracks (`scored_tracks(conn)`) | 2,918 |
| `playlist_tracks` | 11,475 |

All four are **identical** to figures already published in README's opening
paragraph, `db.py`'s own schema comment, and CLAUDE.md's State section. That
match is itself evidence: it means no Takeout re-parse or re-resolve has
happened since those figures were last measured, not merely that this run
happened to agree with a stale memory.

**Pinned or current — both, on different axes.** Every date and
hyperparameter above is a hardcoded literal; all 9 split windows close
before today (last ends 2026-08-31), so nothing is a partially-filled
window. But the *data* those pinned windows are evaluated against is read
live from `data/taste.db` at whatever it currently contains — this
evaluation is **not pinned to a frozen snapshot**, and a different number on
a future run would not by itself indicate a defect. See the three findings
below for exactly which surfaces are live and what effect, if any, that
currently has.

## Raw output — run 1

```
==========================================================================
USABLE SPLITS (reachable truth >= 20, fixed half-life, chosen once)
==========================================================================
  2026-04-01  reachable  232   [dev]
  2026-05-01  reachable  313   [dev]
  2026-06-01  reachable  358   [HELD OUT]
  2026-07-01  reachable  212   [HELD OUT]
  2026-08-01  reachable  365   [HELD OUT]

==========================================================================
SELECTION — on the 2 dev splits only
==========================================================================
 half_life  mean_baseline  mean_score  wins  splits   lift
         7         0.3786      0.4299     1       2 0.1354
        14         0.3786      0.4481     2       2 0.1834
        30         0.3786      0.4338     2       2 0.1459
        60         0.3786      0.4171     2       2 0.1017
        90         0.3786      0.4029     1       2 0.0641
       180         0.3786      0.4026     1       2 0.0633
       365         0.3786      0.3886     1       2 0.0264

  chosen half-life: 14 days

==========================================================================
REPORT — on 3 held-out splits the selection never saw
==========================================================================
     split  baseline  score   lift  win
2026-06-01    0.1354 0.2227 0.6448 True
2026-07-01    0.1074 0.3916 2.6462 True
2026-08-01    0.1718 0.3794 1.2084 True

  mean baseline nDCG@20 : 0.1382
  mean score    nDCG@20 : 0.3312
  lift                  : +139.7%
  splits won            : 3/3
  sign-test p           : 0.125

  VERDICT: no significant improvement over the most-played baseline.
           +139.7% on 3 held-out splits is not
           distinguishable from chance at this sample size.
```

## Raw output — run 2

Byte-identical to run 1 (see Determinism below) — reproduced here in full
per the brief's instruction to capture both verbatim, not to dedupe them:

```
==========================================================================
USABLE SPLITS (reachable truth >= 20, fixed half-life, chosen once)
==========================================================================
  2026-04-01  reachable  232   [dev]
  2026-05-01  reachable  313   [dev]
  2026-06-01  reachable  358   [HELD OUT]
  2026-07-01  reachable  212   [HELD OUT]
  2026-08-01  reachable  365   [HELD OUT]

==========================================================================
SELECTION — on the 2 dev splits only
==========================================================================
 half_life  mean_baseline  mean_score  wins  splits   lift
         7         0.3786      0.4299     1       2 0.1354
        14         0.3786      0.4481     2       2 0.1834
        30         0.3786      0.4338     2       2 0.1459
        60         0.3786      0.4171     2       2 0.1017
        90         0.3786      0.4029     1       2 0.0641
       180         0.3786      0.4026     1       2 0.0633
       365         0.3786      0.3886     1       2 0.0264

  chosen half-life: 14 days

==========================================================================
REPORT — on 3 held-out splits the selection never saw
==========================================================================
     split  baseline  score   lift  win
2026-06-01    0.1354 0.2227 0.6448 True
2026-07-01    0.1074 0.3916 2.6462 True
2026-08-01    0.1718 0.3794 1.2084 True

  mean baseline nDCG@20 : 0.1382
  mean score    nDCG@20 : 0.3312
  lift                  : +139.7%
  splits won            : 3/3
  sign-test p           : 0.125

  VERDICT: no significant improvement over the most-played baseline.
           +139.7% on 3 held-out splits is not
           distinguishable from chance at this sample size.
```

## Determinism

`diff run1.txt run2.txt` — exit code 0, zero differences. Two fresh
processes, same database, byte-identical output on every line, including
the six-decimal internal DataFrame formatting. This matches the code-level
analysis in the earlier inventory: no stochastic component reaches this
path (clustering is never invoked — see Provenance), every ranking function
breaks ties on `video_id` explicitly, and `ndcg_at_k`'s `idcg` sorts raw
values rather than depending on dict/set iteration order.

## Comparison table

| figure | published | re-derived (both runs) | delta |
|---|---:|---:|---:|
| score nDCG@20 | 0.3312 | 0.3312 | 0 |
| baseline nDCG@20 | 0.1382 | 0.1382 | 0 |
| lift | +139.7% | +139.7% | 0 |
| splits held | 3 of 3 | 3 of 3 | 0 |
| p | 0.125 | 0.125 | 0 |

Every published figure reproduced exactly, to the digit.

## Finding 1 — the held-out n=3 is not fixed by design, and here is why it landed on 3 anyway

`nested_rediscovery` probes all 9 `MONTHLY_SPLITS` for `reachable >= 20`
(fixed half-life=30 probe), keeps only the "usable" ones, then splits usable
in half: `cut = len(usable)//2`, `dev = usable[:cut]`, `held =
usable[cut:]`. Held-out size is 3 only when `len(usable)` is 5 or 6; at 7 or
8 it becomes 4, moving the sign-test floor from 0.125 to 0.0625 — a
different, equally valid measurement, not drift or a bug.

Measured directly (probing all 9 splits individually):

| split | reachable | candidates | truth | usable? |
|---|---:|---:|---:|---|
| 2025-12-01 | 0 | 28 | 13 | below bar |
| 2026-01-01 | 2 | 42 | 34 | below bar |
| 2026-02-01 | — | — | — | `ValueError`: empty candidate or truth set |
| 2026-03-01 | 11 | 73 | 790 | below bar |
| 2026-04-01 | 232 | 853 | 778 | **usable** |
| 2026-05-01 | 313 | 1,334 | 973 | **usable** |
| 2026-06-01 | 358 | 2,016 | 835 | **usable** |
| 2026-07-01 | 212 | 2,406 | 410 | **usable** |
| 2026-08-01 | 365 | 2,553 | 687 | **usable** |

`len(usable) = 5` today, giving `held = 3` (`cut=2`, `held = usable[2:]`).
The four dropped splits are all the earliest ones, and they fail for a
structural reason, not a threshold-hugging fluke: `plays.watched_at`'s
minimum is 2025-09-14, so at split 2025-12-01 there are only ~2.5 months of
training data (candidates=28); by 2026-03-01 there's still only 73
candidates against 790 truth tracks. The candidate pool grows roughly
monotonically as the training window lengthens, and it clears 20 reachable
by a wide margin (232+) from 2026-04-01 onward and stays there. Because
`plays` has a fixed start date and each later split only adds *more*
training history, this shape — early splits too thin, later ones
comfortably usable — is stable going forward; `len(usable)` moving to 6
would need a 10th monthly split with similarly thin history to newly clear
the bar, and moving to 7+ isn't structurally in view at all under the
current 9-split, single-year list. n=3 is not fixed by the code, but it is
not fragile either.

## Finding 2 — three undated ("live") surfaces feed a nominally pinned evaluation

Named specifically, with code evidence, not as a generic "reads the DB":

1. **`split_frames` dates the training frame's playlist membership,
   not the test frame's.** `evaluate.py:89-96`: `train` is scored with
   `playlist_as_of=split_date`; `test` is scored with no `playlist_as_of`
   (defaults to `None`), which `classify_heuristic` (`classify.py:79-86`)
   resolves to an **undated** `SELECT DISTINCT video_id FROM
   playlist_tracks` — every row in the table, regardless of when it was
   added. So a track's test-side `is_music` (and therefore whether its
   test-window plays count as truth at all) reflects *today's* playlist
   curation at every one of the 9 split dates, not that split's own
   date. The code's own docstring calls this deliberate ("test... exists
   only to record what was actually played... not a leak in the same
   sense" as the training side) — but it is, concretely, a temporal leak in
   the truth set: information from after a split date can determine
   whether a play within that split's test window is counted as music at
   all.
2. **`library_songs` carries no date column in the schema at all**
   (`db.py:54-59`) — it feeds the `in_library` heuristic signal undated on
   *both* the train and test sides, unconditionally.
3. **`video_metadata` (categoryId, duration) is undated** — `classify()`
   merges it in with no temporal restriction (`classify.py:174-175`), so a
   video resolved via the API after a given split changes that video's
   classification at every split that includes it, historical or not.

**Measured effect at the three splits this headline actually uses**, rather
than left as an unmeasured possibility: for each held-out split's test
window, every video played in that window was classified two ways —
currently (`playlist_as_of=None`, what the eval actually uses) and honestly
dated (`playlist_as_of=<window end>`, what a temporally clean version would
use) — and compared for `is_music` flipping True→False:

| split | test window | videos played in window | `is_music` flips (leak-only → non-music) |
|---|---|---:|---:|
| 2026-06-01 | [2026-06-01, 2026-07-01) | 2,843 | **0** |
| 2026-07-01 | [2026-07-01, 2026-07-31) | 3,350 | **0** |
| 2026-08-01 | [2026-08-01, 2026-08-31) | 3,008 | **0** |

Zero, across all three. This is not because there was nothing to leak:
489–491 `playlist_tracks` rows were added after each of these three
windows' close (a single batch on 2026-09-13, matching the "Lofi Japan..."
/ "Liked videos" playlists found in Finding 3 below) — real, recent
additions exist, they simply don't correspond to any video whose *only*
`is_music` signal is `in_playlist`, among videos actually played in these
three windows. **Mechanism present and correctly characterized as a
temporal leak in the truth set; measured effect on this specific headline
is zero.** This is the same shape CLAUDE.md already documents for the
train-side version of this same undated-`in_playlist` defect (fixed
anyway, because "an undated global in a temporal hold-out is wrong
regardless of today's data") — the test side remains a live, unmeasured-until-now
mechanism that happens to net to zero here, not a settled non-issue.

## Finding 3 — `playlist_tracks` state, and the 2026-09-16 listening test

Requested: `playlist_tracks` row count, and whether the schema permits
determining when rows were added.

- **Row count: 11,475**, `added_at` populated for all 11,475 rows (0 NULL,
  0 empty string). `added_at` is sourced directly from Takeout's own
  per-row `"Playlist video creation timestamp"` field
  (`parse_takeout.py:158`), not synthesized at parse time — the range
  (2023-01-24 through 2026-09-13T07:01:01) and per-playlist variation
  confirm genuine per-track granularity, not one blanket value. This is a
  different table from `playlists.created_at`/`updated_at`, which README
  documents as unreliable ("TuneMyMusic rewrote these") — no equivalent
  caveat was found for `playlist_tracks.added_at`, though this was not
  exhaustively audited beyond the NULL/empty-string check above.

- **The 2026-09-16 date does not match what `written_playlists` holds.**
  All 7 rows in that table:

  | id | title | status | created_at |
  |---:|---|---|---|
  | 1 | T-Series / Pritam / Sony Music India (rediscover) | rolled_back | 2026-09-13T11:00:28Z |
  | 2 | T-Series / Pritam / Sony Music India (rediscover) | rolled_back | 2026-09-13T11:15:20Z |
  | 3 | T-Series / Pritam / Sony Music India (rediscover) | rolled_back | 2026-09-13T17:13:23Z |
  | 4 | T-Series / Pritam / Sony Music India (rediscover) | complete | 2026-09-13T17:49:55Z |
  | 5 | Joji (rediscover) | complete | 2026-09-15T09:37:59Z |
  | 6 | Lil Baby / Lil Peep / Chris Brown (rediscover) | complete | 2026-09-15T17:15:35Z |
  | 7 | T-Series / Pritam / Sony Music India (rediscover) | complete | 2026-09-15T17:15:57Z |

  The only set of exactly three matches **2026-09-15** (ids 5–7, all
  `status=complete`), not 2026-09-16. Recorded as a flat discrepancy, not
  resolved by guessing which day was meant.

- **Neither date affects this result, on two independent grounds:**
  first, none of the three `written_playlists` titles above appears
  anywhere in `playlist_tracks.playlist_name` — confirmed by direct query,
  not inferred: writing a playlist back to YouTube through this app does
  not feed into the Takeout-sourced table the classifier reads, they are
  structurally separate. Second, `playlist_tracks`'s own `added_at` maximum
  (2026-09-13T07:01:01) and `plays.watched_at`'s maximum (also
  2026-09-13T07:24:35) both **predate** both the claimed 2026-09-16 date
  and the actual 2026-09-15 date — meaning no Takeout re-parse capturing
  either event has happened, regardless of which date is correct.

## Finding 4 — `nested_eval.py`'s printed verdict is not the codebase's tested verdict

The raw output above prints:

> VERDICT: no significant improvement over the most-played baseline.
> +139.7% on 3 held-out splits is not distinguishable from chance at this
> sample size.

`nested_eval.py` produces this from its own inline `if out["significant"]`
check (`nested_eval.py:49-54`) — it never reads `out["verdict"]`, even
though `nested_rediscovery` already computes it via `_verdict()`
(`evaluate.py:525-552`), a function specifically written, documented, and
tested to avoid collapsing "not certified" into "no effect." Calling
`nested_rediscovery(conn)` directly and reading that field back gives:

> Lift of +140% winning 3/3 splits, but NOT statistically established: with
> 3 held-out splits a clean sweep gives p = 0.125, so no result at this
> sample size can reach p < 0.05. At least 5 held-out splits would be
> needed. The effect is consistent and large; the evidence is thin.

Same numbers, materially different framing — the script's own printed text
reads as "no effect," which is exactly the misreading `_verdict()` and
CLAUDE.md's `p_floor` discussion exist to prevent. This is a genuine
finding, noted here rather than fixed: `scripts/nested_eval.py` is outside
this brief's scope (not `src/`, but editing the script that just produced
the headline, mid-verification, is exactly the kind of same-session change
that would make this artifact harder to trust), and "improving the
evaluation" is explicitly out of scope regardless.

## Verdict

**Reproduced exactly** — all five published figures (0.3312, 0.1382,
+139.7%, 3/3, p=0.125) are byte-identical across two independent,
fresh-process runs.

That match is not the same finding as a match under a provably sound
evaluation, and shouldn't be read as one. The evaluation's hyperparameters
and split dates are pinned, but the underlying data is not: three undated
surfaces (test-side `in_playlist`, `in_library`, and `video_metadata`) feed
this pinned computation from whatever `data/taste.db` currently contains,
not from a frozen snapshot. Measured directly rather than left as a
caveat — none of the three currently flips any video's `is_music` for
tracks actually played within the three held-out test windows (zero
flips, checked individually per split, against 489–491 real, recently
added `playlist_tracks` rows that exist but don't happen to matter here).
The held-out count of 3 is similarly not guaranteed by the code, but is
structurally stable under the current 9-split list for a legible reason
(the four dropped splits fail on too little training history this early in
the dataset, not on a fragile threshold). So: **the figures match, the
mechanisms that could have made them not match are real and were checked
rather than assumed, and today none of them are exerting any measured
effect.** A future re-run producing a different number — whether from
`len(usable)` shifting, from a genuinely leak-causing playlist edit, or
from new Takeout data — would not by itself indicate a defect in the
pipeline; this report is what "unpinned but currently inert" looks like
measured, not asserted.
