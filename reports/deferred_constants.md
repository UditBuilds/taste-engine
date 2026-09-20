# Deferred constants, notebook guard, and the as_of anchor

Executed against `briefs/deferred_constants.md`, starting at `6dd678a` (531
tests passing, working tree clean except the brief itself). Every number
below is labelled executed / source-read / inferred per the brief's standing
rule.

## Part A — deferred hardcoded constants

### Site 1 — scripts/canonical_impact.py (14 / 50 / 30)

**Source-read, then executed.** Found and fixed four occurrences of the
three named literals, each mapped to the config constant matching its
*semantic* role, not just its numeric value (`EVAL_K` and `EXCLUDE_TOP` are
both currently `50` but are different constants):

- `.head(50)` (the "top 50 genuinely most-played songs") -> `.head(config.EXCLUDE_TOP)`
- both `rediscovery_split(conn, split, 14, 50, 30, ...)` calls -> `config.RECENCY_HALF_LIFE_DAYS, config.EXCLUDE_TOP, config.EVAL_TEST_DAYS`
- the `14` in `evaluate_rediscovery(conn, split, 20, 14, ...)` -> `config.RECENCY_HALF_LIFE_DAYS`
- `evaluate(conn, k=50, test_days=30, half_life=14, ...)` -> `config.EVAL_K, config.EVAL_TEST_DAYS, config.RECENCY_HALF_LIFE_DAYS`

**Not touched, and worth flagging:** the `20` on the same line as the now-fixed
`14` (`evaluate_rediscovery(conn, split, 20, config.RECENCY_HALF_LIFE_DAYS, ...)`)
is still a literal. The brief's item 1 names only 14/50/30; this `20` is the
same value Site 3 gives a config home to (`REDISCOVERY_K`), but this specific
call site was not in scope. Left as-is rather than fixed unilaterally - see
"Discrepancies" below.

**Invariant, executed:** ran the script itself three times (not just
`nested_eval.py`, since sections 1-4 of this script are not reachable through
`nested_rediscovery` and so are not exercised by that check at all - only
section 5 is). Before-edit vs. after-edit output is byte-identical except for
one line:

```
Loading weights:   0%|          | 0/103 [00:00<?, ?it/s]Loading weights: 100%|...
```

Source-read: this string exists nowhere in this repo (`grep -rn "Loading
weights" src/ scripts/` = no hits); it comes from
`transformers/core_model_loading.py` in the venv. Executed: ran the
post-edit script a second time (three runs total) - the line appeared only
in run 1, never in runs 2 or 3, which were byte-identical to each other.
Consistent with an OS page-cache warm-up on first weights read in the
session, not with anything this brief touched (no edit in this brief is
anywhere near `embed.py` or model loading). All four sections' actual
numbers - collapse counts, leak rates, nDCG/lift tables, and the section 5
headline (`+139.7%`, `3/3`, `p=0.125`) - are identical across all three runs.

### Site 2 — exclude_top=50 (evaluate.py:199, 234, 772; config.EXCLUDE_TOP)

**Executed.** All three named lines fixed to `config.EXCLUDE_TOP`:
`rediscovery_split`'s default (199), `evaluate_rediscovery`'s default (234),
and the CLI's `--exclude-top` argparse default (772).

**Confirmed by source-read: `config.EXCLUDE_TOP` (config.py:75) is the
definition, not a duplicate.** It is already the value `recommend.py:35`,
`dormancy.py:127`, and five scripts (`backfill_plan.py`,
`compare_backfill_ranking.py`, `genre_coverage.py`, `verify_strict_null.py`,
`dormancy_distribution.py`) read today. `evaluate.py` was the one module in
the repo still hardcoding this value instead of reading it.

### Site 3 — k=20 across four evaluate.py signatures

**Executed, matches the brief exactly.** Exactly four signatures hardcoded
`k: int = 20`: `evaluate_rediscovery` (231), `rediscovery_robustness` (300),
`rediscovery_half_life_sweep` (354), `nested_rediscovery` (400) - no more,
no fewer. No existing config constant covered this value (`EVAL_K` is the
*replay* task's k, a different constant that happens to equal `50`, not
`20`); added `config.REDISCOVERY_K = 20` and pointed all four signatures at
it.

### Discrepancies found in Part A's own scope (reported, not worked around)

The brief's item 2 lists three `evaluate.py` lines carrying the literal `50`
plus `config.EXCLUDE_TOP` as "four independently hardcoded 50 literals."
Source-read found **three more** `exclude_top: int = 50` defaults in the
same file, in the same four functions Site 3 already had to touch for `k`:
`rediscovery_robustness` (302), `rediscovery_half_life_sweep` (355),
`nested_rediscovery` (401). These are not dead defaults - `nested_eval.py`'s
`nested_rediscovery(conn)` and `canonical_impact.py`'s
`nested_rediscovery(conn, canonical=True)` both invoke `nested_rediscovery`
without an `exclude_top` argument, so line 401's hardcoded `50` is live in
exactly the code path this brief's own invariant check exercises. Same
family: `evaluate.py`'s `main()` hardcodes `20` twice more as explicit
call-site arguments (805, 810: `evaluate_rediscovery(conn, args.split, 20,
...)` and `rediscovery_robustness(conn, k=20, ...)`), which override the
Site-3 defaults regardless, so the CLI's own behaviour is unaffected either
way by that fix.

None of these six extra literals were named in the brief, so none were
touched - fixing them would have been deciding, unilaterally, that the
brief's enumeration was incomplete rather than deliberate. They carry the
same value as their respective config constants today, so leaving them does
not create a live bug, only a latent one (identical risk profile to the
three named `exclude_top` sites before this brief fixed them). Flagged here
per the standing rule ("report discrepancies, do not work around them")
for a decision on whether a follow-up should close them the same way.

### Site 4 — scripts/compare_backfill_ranking.py Counter tie-break

**Executed.** Replaced both `Counter.most_common(10)` calls with
`sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:10]` - the same
ordering rule as `writer._modal_genre`'s `min(counts.items(), key=lambda kv:
(-kv[1], kv[0]))`, generalised from picking 1 winner to picking 10.

**Measured before/after (git stash/run/pop/run, same pattern used to verify
the backfill code's invariance in CLAUDE.md's State section):** the summary
numbers are byte-identical either side of the fix - `qualifying clusters:
8`, `38 slots` on both the old (8 distinct) and new (35 distinct) side, and
every per-cluster count (Don Toliver 5, The Weeknd 6, 21 Savage 4, Metro
Boomin 7, Future 5, Travis Scott 5, Drake 6, T-Series 0). The fix touches
only the diagnostic "top 10 most repeated" printout, never selection.

**Unlike Site 2/3's defaults, this tie-break is measured live today, not
dormant.** On the old (score-ranked) side there are only 8 distinct tracks
total, so nothing is truncated and the fix only reorders equal-count rows.
On the new (distance-ranked) side there are 35 distinct tracks competing
for 10 print slots, and the specific tracks shown at the `1x` boundary are
**entirely different** before and after:

| | before (insertion-order tie-break) | after (alphabetical-by-video_id) |
|---|---|---|
| 1x slots (7 of 10) | Too Many Nights, I Can't Save You, PARTYNEXTDOOR, Raindance, Timeless, RATHER LIE, Young Metro | Young Metro, Mile High Memories, ghost girl, Raindance, Starboy, Timeless, PARTYNEXTDOOR |

Executed (set intersection on the two 7-item lists by video id): 4 of the 7
survive in both by coincidence (Young Metro, Timeless, Raindance,
PARTYNEXTDOOR); 3 are unique to the before list (Too Many Nights, I Can't
Save You, RATHER LIE) and 3 are unique to the after list (Mile High
Memories, ghost girl, Starboy). Checked `reports/backfill_plan.md` for any
citation of this specific list or these video ids: none found (`grep` for
the track ids and for "most repeated" / "top 10" returns nothing), so no
committed report goes stale as a result of this fix.

### Invariant check — nested_rediscovery headline (the brief's required check)

Executed `scripts/run.sh scripts/nested_eval.py` before any Part A edit and
after all of them (Sites 1-4 applied). Diff: **empty**. Headline unchanged:
mean baseline nDCG@20 0.1382, mean score 0.3312, lift +139.7%, 3/3 wins,
sign-test p=0.125.

### Test suite

531 passed - unchanged from the brief's stated starting count. (Run before
Part B's new test file existed, so this number isolates Part A only; see
Part B below for the count with that file added.)

---

## Part B — build_notebook.py output guard

**Executed.** `scripts/build_notebook.py`'s module-level code ran
unconditionally on import (writing the notebook, and executing it if
`--execute` was in `sys.argv`), which made it impossible to import for a
test without the import itself writing to `notebooks/01_eda.ipynb` as a
side effect. Refactored into `build(out=OUT, execute=False,
allow_output_loss=False)` and `main(argv=None)`, called only under `if
__name__ == "__main__"` - required to make the guard testable at all, not
scope creep beyond the brief's own ask for "a regression test."

Guard: `build()` raises `OutputWouldBeStripped` when `out` already has an
executed code cell, `execute` is not requested, and `allow_output_loss` is
not passed. New CLI flag `--allow-output-loss` is the explicit override the
brief asked for; `--execute` continues to work as before (regenerating
outputs makes the strip moot, so the guard steps aside for it) and was not
changed to "fix" the guard problem automatically, per the brief's "do not
auto-execute as the fix."

**Invariant, executed twice:**
1. `tests/test_build_notebook.py` (4 new tests, all against `tmp_path`,
   never the real notebook): first write needs no flag; a second unexecuted
   write is fine when there is nothing to lose; an executed notebook is
   protected and the refusal leaves the file untouched; `--allow-output-loss`
   overrides. All 4 pass.
2. Ran `scripts/build_notebook.py` for real, no flags, against the actual
   `notebooks/01_eda.ipynb` (which has committed output on all 15 code
   cells): it refused, exit code 1, and `git status --short
   notebooks/01_eda.ipynb` printed nothing - the file is untouched.

Full suite with this part's test file added: 535 passed (531 + 4 new).

---

## Explicitly report-only (not fixed, per the brief)

Both confirmed accurate by source-read, line numbers unchanged:

- **`score.py:76`** - `raise ValueError("half_life must be positive")`
  inside `add_scores`. Reachable via
  `rediscovery_half_life_sweep` -> `rediscovery_robustness`, whose loop at
  **`evaluate.py:318`** (`except ValueError: continue`) is a *blanket*
  ValueError catch - it cannot distinguish "half_life must be positive"
  from the ordinary "empty candidate or truth set" case it was written for,
  so a bad half-life in a swept list would silently drop that row rather
  than surface an error.
- **`evaluate.py:443-458`** - `_score` (inside `nested_rediscovery`) has no
  `try`/`except` of its own. It is safe only because
  `nested_rediscovery`'s own filtering loop (line 431's `except ValueError:
  continue`, at a fixed `half_life=30` probe) has already restricted `dev`/
  `held` to splits known usable - safe by invariant, not by guard. A swept
  half-life that failed in a way the fixed-30 probe did not would raise
  unhandled out of `_score`.

No guards added to either, per instruction.

---

## Part C — as_of anchor

### C1. Confirm the anchor

Executed: `SELECT MAX(watched_at) FROM plays` -> **`2026-09-13T07:24:35+00:00`**.
Matches the brief's stated value exactly.

### C2. Fix scripts/dormancy_signals.py's default

Executed. Added `_last_play_at(conn)` (queries the same statement as C1,
tz-normalises to UTC) and changed `build_report`'s `as_of is None` branch
from `pd.Timestamp.now(tz="UTC")` to `_last_play_at(conn)`. `--as-of` and
`main()` are untouched - both already threaded an explicit value straight
through to `build_report`, so the only thing that changes is what happens
when neither is given. The as_of-recording line
(`` `as_of` pinned for every "current"/live number below: ``) is untouched
and now simply records whichever value was actually used.

`tests/test_dormancy_signals.py::TestAsOfReproducibility::
test_default_as_of_omitted_falls_back_to_wall_clock` asserted the *old*
behaviour directly (`before <= used <= after` bracketing
`pd.Timestamp.now()`) and would fail after this fix by construction, not by
regression - replaced with
`test_default_as_of_omitted_falls_back_to_the_datasets_last_play`, which
independently recomputes `MAX(watched_at)` via the `db` fixture (not by
importing the fix's own helper) and asserts the report's recorded `as_of`
equals it exactly. All 9 tests in that file pass; full suite unaffected
(a separate command below reports the count including this).

### C3. Re-run and diff - GATE TRIGGERED, per the brief's own prediction

**Executed via scratch path, not the tracked file** (`build_report()` called
directly, written to a scratch path - same technique the "Part B" commit in
this report's own git history used for the identical reason: don't
overwrite a report you don't yet know is safe to overwrite).
`reports/dormancy_signals.md` is untouched (`git status --short` confirms
empty). Diff against that scratch output is **not empty** - every
`as_of`-dependent number in the report moved, as the brief said to expect.

**The named figure:**

| | old (as_of = 2026-09-16T04:18:39, wall-clock) | new (as_of = 2026-09-13T07:24:35, MAX(watched_at)) |
|---|---|---|
| §4 headline | 177 of 180 shipped tracks (98.3%) | **197 of 198 shipped tracks (99.5%)** |

The denominator itself moved (180 -> 198), not just the numerator - the
qualifying-cluster count and per-cluster `shipped_n` both shifted alongside
every `days_since`/`plays_last_Nd`/percentile figure in the report (full
diff available; not reproduced here in full to avoid the report itself
becoming a second place this number is asserted).

**Every file that cites the old figure (repo-wide grep, both the literal
number and a title/prose paraphrase check on README specifically - not
just the two files the brief named as "at minimum"):**

| file | kind | what it says |
|---|---|---|
| `reports/dormancy_signals.md:188` | published report (source) | 177 of 180 (98.3%) |
| `reports/listening_test.md:63` | published report | quotes 177/180 (98.3%) directly |
| `reports/recency_exclusion.md:66` | published report | cites 177/180 (98.3%) **and** independently reconfirms a related figure (137/139, 98.6%) at a different as_of, calling the two "different day, different denominator, same result" |
| `briefs/recency_exclusion.md:12,57` | historical brief | cites 98.3% as reasoning toward that brief's own decision (closed at commit `6e475d9`, "§2 feasibility gate") |
| `briefs/reproducibility_and_distribution.md:86` | historical brief | cites 177/180 (98.3%) as the motivating example for why `as_of` needed pinning at all |
| `reports/ground_truth_ids.md:61` | published report | **not a citation** - `98.3` there is a coincidental substring inside an unrelated ARI-gap-multiplier table; confirmed unrelated topic, not touched |

**README.md does not cite this figure**, contrary to the brief's "at
minimum reports/listening_test.md and README.md": grepped for the exact
numbers (`177 of 180`, `98.3`, `197 of 198`, `99.5`) and for a paraphrase
(`last 30 days`, `shipped track`, `played in the last`) - zero hits, all
four searches. README's own "Dormancy signals" paragraph cites
`reports/dormancy_probe.md`, a **different** report (see below) - this
looks like the brief conflating the two dormancy reports, not a citation
that was missed.

**Not measured, and flagged rather than inferred:**
`reports/recency_exclusion.md:66`'s independent 98.6% figure sits between the old
(98.3%) and new (99.5%) values, which is suggestive that the qualitative
conclusion ("shipped tracks are almost all very recently played") is
robust to the exact anchor - but that report's own as_of methodology was
not audited here, and treating three numbers as validating each other
without checking whether they share the same underlying bug would be
exactly the kind of unearned confidence this brief's standing rules warn
against. Left for whoever picks this up next.

**GATE, per instruction: not fixed further.** `reports/dormancy_signals.md`,
`reports/listening_test.md`, `reports/recency_exclusion.md`, and README.md
are all untouched. This section documents the move; it does not resolve
it. **This report's own commit therefore leaves the repo in a state where
`scripts/dormancy_signals.py`'s code and `reports/dormancy_signals.md`'s
committed content now disagree by construction** - the code is fixed, the
publication is deliberately not regenerated, pending a decision on
`reports/listening_test.md`/`reports/recency_exclusion.md`/README.md (none
of which currently cite the wrong report, but the underlying phenomenon
`recency_exclusion.md` treated as corroboration and
`briefs/recency_exclusion.md` partly reasoned from is affected). That
decision is Udit's, not this brief's.

### C4. Audit-only: other wall-clock reads

Executed: grepped for the brief's four literal patterns
(`datetime.now`, `datetime.utcnow`, `date.today`, `time.time`), plus
`pd.Timestamp.now(` and `datetime.today(` (the brief's list would
otherwise miss the exact pattern C2 just fixed - `dormancy_signals.py`'s
own bug was `pd.Timestamp.now(tz="UTC")`, not a bare `datetime.now()`),
plus a SQL-level check (`CURRENT_TIMESTAMP`, `datetime('now')` - zero hits,
this codebase's timestamps are all Python-side). One verdict per site, not
just a list, per the standing rule that a number's provenance must be
traceable:

| file:line | reads | feeds a published figure? |
|---|---|---|
| `src/taste_engine/lastfm.py:367` | `datetime.now(timezone.utc)` | No - lookup-cache provenance timestamp (`fetched_at`), not a measurement input |
| `src/taste_engine/resolve.py:135,144` | `datetime.now(timezone.utc)` | No - `videos.list` cache-row provenance timestamp |
| `src/taste_engine/quota.py:79,122,138` | `datetime.now(PACIFIC)` / `datetime.now(timezone.utc)` | No - quota-ledger date key and log timestamp; the ledger's whole job is tracking real elapsed days against Google's daily reset |
| `src/taste_engine/writer.py:55` | `datetime.now(timezone.utc)` | No - write-attempt provenance timestamp in `written_playlists` |
| `scripts/min_samples_sweep.py:181,238,278,280` | `time.time()` | No - wall-clock *duration* timing (sweep runtime reporting), not calendar-time measurement |
| `scripts/dormancy_signals.py:252` / `dormancy_probe.py:330` | `pd.Timestamp.now(tz='UTC')` | No - "Report generated (UTC)" provenance line, distinct from the `as_of` these reports also print (the thing C2 fixed) |
| `scripts/dormancy_signals.py:289` | (comment text, not code) | N/A - prose describing the pre-Part-B design, not a live read |
| **`src/taste_engine/score.py:61`** (`_as_datetime(None)`) | `datetime.now(timezone.utc)` | **Yes, indirectly and widely.** This is `add_scores`'s default when `as_of` is not given. `scored_tracks()` exposes `as_of`, but `recommend.build(conn, half_life=None)` (`recommend.py:151-156`) calls `scored_tracks(conn, half_life=half_life)` **without** ever passing `as_of` through - so every caller of `recommend.build()` inherits wall-clock with no override available at that level. Traced two live report-writing call sites: `scripts/backfill_plan.py:145` (`frame = build_frame(conn)`) writes `reports/backfill_plan.md` directly (`:735-736`); `scripts/compare_backfill_ranking.py:77` (same call, no override) feeds Part A Site 4's own before/after measurement earlier in this report. **This is correct, not a bug, for the live write path** - `writer.py`'s `--commit` should score against wall-clock "now" when actually building a playlist for today. It is a reproducibility gap specifically for measurement scripts built on `recommend.build()` with no way to pin a snapshot - the same class of bug C2 fixed in `dormancy_signals.py`, reached through the scoring core instead of `dormancy.py`, and with a wider blast radius since more scripts sit on top of `recommend.build()` than on top of `dormancy.build_frames`. |
| **`scripts/dormancy_probe.py:162`** | `pd.Timestamp.now(tz="UTC")`, **unconditional** | **Partially - see below.** No `--as-of` flag exists on this script at all (confirmed: no `as_of`/`as-of` argparse entry anywhere in the file) - stricter than `dormancy_signals.py`'s pre-fix state, which at least had an escape hatch. The committed `reports/dormancy_probe.md` is pinned at `as_of = 2026-09-16T04:42:49`, ~2 days 21 hours past `MAX(watched_at)` - the same bucket-blindness class C3 measured, unfixed. **README.md cites this report** ("Dormancy signals (`reports/dormancy_probe.md`)"), but the two figures README actually quotes from it - the 362-day export span and 61.8% one-lifetime-play rate - are both lifetime/structural facts computed from `watched_at` min/max and per-track total play counts, neither of which depends on where `as_of` is anchored. Not re-measured (doing so would be a de facto republish, out of scope for an audit step); **whether any of the report's *other*, as_of-dependent figures are stale is unmeasured and left open**, but README's specific quoted conclusion does not appear to hinge on this bug based on what it quotes. |
| **`scripts/dormancy_distribution.py:489`** | `pd.Timestamp.now(tz="UTC")` in the CLI's `else` branch | **No, currently - but latently yes.** The committed `reports/dormancy_distribution.md` is correctly anchored (`as_of = 2026-09-13T07:24:35+00:00`, exactly `MAX(watched_at)`) - but only because it was generated with an explicit `--as-of` override in the most recent commit (`6dd678a`, before this brief started); the CLI's *default* (line 489, taken whenever `--as-of` is omitted) is still unconditional wall-clock. The next default-invoked run of this script would silently regenerate a worse report than the one currently committed, with nothing to flag that it happened - the same observability gap C3 just measured firing on `dormancy_signals.py`. |

No fixes applied in this section, per instruction - `score.py`,
`recommend.py`, `dormancy_probe.py`, and `dormancy_distribution.py` are
all unchanged.

### Test suite (Part C)

535 passed (unchanged from Part B's count - Part C added no new source
files besides the `dormancy_signals.py`/`test_dormancy_signals.py` pair,
whose test count was already 9 before and after this brief; net test count
across the whole brief is unchanged by Part C, only by Part B's +4).
