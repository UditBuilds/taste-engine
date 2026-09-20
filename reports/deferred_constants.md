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
