# as_of through the scoring core

Executed against `briefs/asof_core_and_dormancy.md`, Part A only, starting at
`9791196` (3 commits ahead of origin: `751d8ef`, `7e5c532`, `9791196`; 535
tests passing) - matches the brief's stated context exactly, no discrepancy.
Every claim below is labelled executed / source-read / inferred.

## A1. Trace: how as_of reaches score.py today (source-read)

**Every actual call site of `recommend.build()`** (not counting comments/
docstrings that mention it without calling it):

| call site | writes a report? |
|---|---|
| `src/taste_engine/recommend.py:171` (`main()`, the `python -m taste_engine.recommend` CLI; pre-edit line - this file's line numbers below shift after A2's edit) | No - stdout only |
| `src/taste_engine/cli.py:201` (`cmd_clusters`, the `taste-engine clusters` command; this file is untouched by this brief, so pre- and post-edit are the same) | No - stdout only |
| `src/taste_engine/writer.py:378` (`writer.plan()`) | **No report file, but this is the live write path** - `--commit` posts real playlists to the real YouTube account through this exact call |
| `scripts/backfill_plan.py:145` | **Yes** - writes `reports/backfill_plan.md` directly (`:735-736`) |
| `scripts/compare_backfill_ranking.py:77` | No report file of its own, but its numbers are the ones `backfill_plan.md`'s own docstring says it keeps reproducible |
| `scripts/genre_coverage.py:245` | **Yes** - writes `reports/genre_coverage.md` directly (`:586-587`) |

The brief's A1 said "expected: reports/backfill_plan.md" - confirmed, plus
**one more found**: `reports/genre_coverage.md` reaches this exact path too
(`scripts/genre_coverage.py:21` imports `build as build_frame`, `:245` calls
it with no override). Not a contradiction of the brief's expectation, an
addition to it.

**`score.py`'s own wall-clock read:** `src/taste_engine/score.py:61`
(pre-edit line number), inside `_as_datetime`:
```python
def _as_datetime(value) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
```
This is the sole choke point every as_of-less call funnels through.
`scored_tracks()` (`score.py:107`, pre-edit `:94`) exposes `as_of` as a
parameter, but `recommend.build()` (`recommend.py:151`, pre-edit) called
`scored_tracks(conn, half_life=half_life)` **without ever passing `as_of`
through** - so every `build()` caller inherited wall-clock via this chain,
with no override available at that level.

**Also found, out of A2's stated scope (not touched, flagged same as the
previous brief's discrepancy pattern):** `score.py`'s own `main()` (the
`python -m taste_engine.score` CLI, pre-edit line 149) calls
`scored_tracks(conn)` with no `as_of` either - a second, independent
wall-clock site not reached by fixing `recommend.build()`, since it never
goes through `build()` at all. A2 asked specifically for `recommend.build()`;
this is a sibling gap in the same file, reported not fixed.

**Confirmed NOT affected:** `taste_engine/dormancy.py` explicitly does not
call `recommend.build()` - its own docstring says so (`:120,123`) precisely
because `build()` didn't expose `as_of` - and instead calls
`score.scored_tracks(..., as_of=as_of)` directly. `evaluate.py` never calls
`recommend.build()` either; every `scored_tracks` call in `evaluate.py`
passes an explicit `end`/`half_life` for its temporal splits. Both were
already immune to this bug before this brief, confirmed by trace not by
running (though A4 measures it too - see below).

## A2. Fix (executed)

Added `score.last_played_at(conn) -> datetime` (`score.py:68-78`): queries
`SELECT MAX(watched_at) FROM plays`, reuses `_as_datetime` for tz
normalisation rather than re-implementing it. `recommend.build()`
(`recommend.py:151-169`) gained an `as_of=None` parameter; when omitted it
resolves via `last_played_at(conn)` before calling `scored_tracks(conn,
as_of=as_of, half_life=half_life)` - `scored_tracks:154` (`as_of=as_of if
as_of is not None else end`) means an explicit, non-None `as_of` always
wins over both `end` and the wall-clock fallback, so this fully bypasses
`_as_datetime`'s `None` branch for every `build()` caller. `_as_datetime`,
`add_scores`, and `scored_tracks` themselves are unchanged - callers that
go around `build()` (like `dormancy.py`) are unaffected either way.

**Anchor value, executed (query, not hardcoded):** `2026-09-13T07:24:35+00:00`.
Matches C1's value from `briefs/deferred_constants.md` exactly (same table,
same row - the dataset has not changed).

**Verified, executed (this is not A3, so running it is in scope):**
```
last_played_at:              2026-09-13T07:24:35+00:00
build() default as_of used:  days_since range 0.0 - 362.9  (was ~7-370 under wall-clock)
```
minimum `days_since` is now exactly 0.0 (a track played at the anchor
instant), which is only possible once the eligibility gate stops sitting
~7 days past the dataset's own last play. Also ran a real dry-run write
(`taste-engine write --cluster-name "Travis Scott"`, 0 API calls, nothing
committed) end to end through `writer.plan()` - produced a normal 21-track
scored, ranked playlist and printed "Nothing written," confirming the live
write path's integration is intact under the new default.

## A3. dormancy_probe.py --as-of override (executed, code only, not run)

Added `as_of: pd.Timestamp | None = None` to `build_report()`, resolving to
`pd.Timestamp(last_played_at(conn))` when omitted (reuses A2's helper rather
than a third hand-rolled copy - dormancy_signals.py's own `_last_play_at`
predates this and was not touched, since dormancy_signals.py is not named
in this brief). `main()` gained an `argv` parameter and a `--as-of` flag,
mirroring `dormancy_signals.py`'s existing pattern exactly, with help text
written to describe *this* fix's actual default (not copy-pasted from
there - see the note below).

**Per instruction, not executed in any form:** no manual invocation, no new
test written or run against `build_report()`/`main()`. `py_compile` only
(confirms the file parses; does not execute its logic).
`tests/test_dormancy_probe.py` was checked first and confirmed to test only
individual helper functions (`is_eligible`, ranking, `find_cluster`,
`_md_table`) - it does not call `build_report()`/`main()` at all, so running
the full suite for A4 (below) does not touch this code path either.
`reports/dormancy_probe.md` is untouched (confirmed via `git status`).

**Minor discrepancy noticed, not fixed (out of this brief's scope):**
`dormancy_signals.py`'s own `--as-of` help text still reads "Omit for
current (wall-clock) behaviour" - stale since `briefs/deferred_constants.md`
Part C changed that default to `MAX(watched_at)` and the help text was not
updated at the time. Cosmetic only (the code is correct; only the `--help`
string is wrong). Not touched here since `dormancy_signals.py` is not named
anywhere in this brief.

## A4. GATE (executed) - PASSED, byte-identical

Ran `scripts/run.sh scripts/nested_eval.py` after A1-A3's edits and diffed
against the output captured immediately after `briefs/deferred_constants.md`
Part A's own commit (`751d8ef`) - valid as "the current committed output"
because nothing between that commit and this session's edits touches
`evaluate.py`, `config.py`, or `score.scored_tracks`/`add_scores` (Parts B
and C of that brief touched `build_notebook.py` and `dormancy_signals.py`
only). Diff: **empty**. Headline reproduced exactly: mean baseline nDCG@20
0.1382, mean score 0.3312, lift +139.7%, 3/3 wins, sign-test p=0.125 -
matching the brief's own stated confirmation value-for-value.

This is expected, not a coincidence needing further explanation:
`nested_rediscovery`'s internal `_score` hardcodes
`strategies=["most_played", "score"]` (no `cluster_diverse`), so
`rediscovery_split`'s `cluster="cluster_diverse" in names` is `False` for
every call `nested_eval.py`
makes - clustering, and therefore anything touching `recommend.build()`, is
never invoked on this path. Confirmed by trace (A1) and by measurement
(this gate), not by trace alone.

**Per the user's explicit instruction, stopping here.** Part A's gate
passed, which per the brief's own text ("Part B does not start until Part
A's gate passes") would permit continuing - but the user asked to stop and
report at this exact gate regardless of outcome, before touching Part B.
Part B and Part C are not started.

## Full suite

535 passed - unchanged from the brief's stated starting count, no
discrepancy.

## Reports whose inputs now change anchor (source-read, not re-measured)

Everyone downstream of `recommend.build()` with no explicit `as_of`/`half_life`
override now gets `MAX(watched_at)` instead of wall-clock as of this commit:

- `reports/backfill_plan.md` (`scripts/backfill_plan.py`) - the brief's
  named expectation, confirmed.
- `reports/genre_coverage.md` (`scripts/genre_coverage.py`) - found in
  addition to the brief's expectation (see A1).
- The live `--commit` write path (`writer.py`, via `taste-engine write`) -
  not a report, but the highest-stakes caller: playlists written *today*
  will now be scored against the dataset's last known play rather than
  today's wall-clock date. Confirmed via dry run to still function
  end-to-end (see A2); not exercised with `--commit` by this brief.
- `reports/dormancy_probe.md` gets an override capability (A3) but is
  explicitly **not** re-measured or regenerated by this brief - it still
  reflects its old, wall-clock-anchored content until someone runs it with
  the new code.

None of these were re-measured or regenerated by this brief - A1-A5 is a
code change plus a trace, not a re-publication. Whether/when to regenerate
`backfill_plan.md`/`genre_coverage.md` against the new anchor is a decision
for whoever picks this up next, same as `briefs/deferred_constants.md` left
`dormancy_signals.md` for.

---

## Pre/Part-B check: live-write dry-run diff, requested separately after A4

Requested before starting Part B, as an end-to-end sanity check on A2's
change to the actual write path (`writer.plan()`), independent of anything
`nested_eval.py` exercises. Executed with a temporary git worktree, removed
afterward; nothing pushed; Part B not started.

### Confirming the run.sh / 399dc2f claim - true, but not sufficient on its own

`399dc2f` (Udit, 2026-09-19, "Part C1: replace 18 hardcoded
`/mnt/c/Users/uditk/...` paths with dynamic resolution") is confirmed an
ancestor of `9791196` - the fix is present at the commit this brief's
BEFORE state needed. Empirically confirmed too, not just via `git
merge-base`: invoking `<worktree>/scripts/run.sh -c "import os;
print(os.getcwd())"` from a worktree checked out at `9791196` printed the
**worktree's own path**, not main's.

**That is not the whole story, and trusting it alone would have produced a
silently-wrong BEFORE capture.** `taste_engine` is installed editable into
the shared venv, pointing at an absolute path
(`/mnt/c/Users/uditk/Projects/taste-engine/src/...`) baked in at install
time - independent of process cwd. Proved this empirically before trusting
anything further: ran `<worktree>/scripts/run.sh -c "import
taste_engine.recommend as r; import inspect; print(r.__file__,
'as_of' in inspect.signature(r.build).parameters)"` from the 9791196
worktree. Result: **resolved from
`/mnt/c/Users/uditk/Projects/taste-engine/src/taste_engine/recommend.py`**
(main, not the worktree) **with
`as_of` already present** - i.e., a naive "worktree + `scripts/run.sh`"
capture would have silently tested the AFTER code while believing it was
testing BEFORE. `run.sh`'s fix is real and correctly scoped to what it
claims (shell cwd); it does not and cannot reach into how Python's import
system resolves an editable install. Worth carrying forward:
**`scripts/run.sh` alone is not sufficient to test a worktree's Python
code in this repo** - anything importing `taste_engine` needs an explicit
`sys.path.insert(0, "<worktree>/src")` ahead of the editable install, or a
separate venv `pip install -e`'d from the worktree.

### Method

Neither capture used `scripts/run.sh`, for the reason above. One
throwaway script (`capture_dry_run.py`, scratchpad only, not part of the
repo), run twice with `~/.venvs/taste-engine/bin/python` directly and
`--root` pointed at the worktree (BEFORE) or the main checkout (AFTER):

1. Sets `TASTE_DB` to the main checkout's real database
   (`/mnt/c/Users/uditk/Projects/taste-engine/data/taste.db`) **before**
   any `taste_engine` import, so both captures score the identical data -
   the only variable is the code.
2. `sys.path.insert(0, "<root>/src")` before importing `taste_engine`.
3. **Hard assertion 1:** `taste_engine.__file__` resolves under `<root>`.
   Both passed (worktree path for BEFORE, main path for AFTER).
4. **Hard assertion 2, on the thing actually being measured:**
   `"as_of" in inspect.signature(recommend.build).parameters` equals the
   expected value (`False` for BEFORE, `True` for AFTER). Both passed.
5. Calls `writer.plan(conn, cluster_name=..., mode="rediscover")` directly
   for `"Travis Scott"` and `"T-Series"` (both resolved without
   `WriteBlocked`), and serializes rank/video_id/score/title - membership
   and ordering are then comparable by construction, with no CLI/argparse
   formatting in between.

### Result

| cluster | before count | after count | delta | ordering of common tracks | score ratio (after/before) |
|---|---|---|---|---|---|
| Travis Scott | 16 | 21 | **+5** | unchanged (verified: identical relative order for all 16 shared tracks) | uniform **1.42430** across all 16 |
| T-Series | 13 | 22 | **+9** | unchanged (verified: identical relative order for all 13 shared tracks) | uniform **1.42431** across all 13 |

**Nothing reordered. Membership grew, in both clusters, via the `MIN_SCORE`
floor.** Every track present in BEFORE is present in AFTER, in the same
relative position - the diff's only content is (a) a uniform score
multiplier and (b) new tracks appended below the previously-last-eligible
one. This matches the model's own arithmetic exactly, not a coincidence:
`score = log1p(plays) * 0.5^(days_since/14)`; moving the anchor 7 days
earlier (2026-09-13 vs. wall-clock at capture time, ~2026-09-20) shifts
every track's `days_since` down by the same ~7.1 days, which multiplies
every score by the same `0.5^(-7.1/14) ≈ 1.424` - confirmed to 5 decimal
places, identical for both clusters (both captures ran against the same
wall-clock instant). A uniform multiplier cannot reorder anything; it can
only push tracks that were just below `MIN_SCORE = 0.5` over it, which is
exactly what happened - all 14 new tracks (5 Travis Scott, 9 T-Series) sit
in the after-score range 0.52-0.70, i.e. within reach of a ~1.42x lift
from just under the floor.

New tracks, Travis Scott (5): SZA - Open Arms (ft. Travis Scott), NEMZZZ -
GASS (feat. Travis Scott), sdp interlude, Travis Scott - STOP TRYING TO BE
GOD, FLORIDA FLOW.

New tracks, T-Series (9): Ishq Shava, Subhanallah, Tujhe Sochta Hoon, Yaar
Bathere, Tere Liye, Saibo, Raabta, Chahun Main Ya Naa, Yeh Fitoor Mera.

**Consequence for the live write path, not exercised further here:**
`writer._target_length()` derives target playlist length from native
count, so a cluster-scoped write today will ship a **longer** playlist
than the same request would have under the old wall-clock default, for
any cluster with tracks sitting just under `MIN_SCORE`. This is the direct,
concrete form of A2's "deliberate behaviour change for every caller" -
measured on the two clusters requested, not generalised to every cluster
in the library.

### Cleanup

`git worktree remove <path>` then `git worktree prune`;
`git worktree list` confirmed only `main` and the pre-existing,
untouched `worktree-backfill-toggle` remain. `git status --short` on
main was clean before, during, and after. Nothing pushed. Part B not
started.
