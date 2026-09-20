# Brief: deferred constants, notebook guard, and the as_of anchor

## Context
Repo is at 6dd678a, 531 tests passing, working tree clean.
This brief closes three unrelated items that were deferred, not decided against.
They are deliberately in separate parts with separate commits because they carry
different measurement risk. Do not combine them.

## Standing rules
- Report discrepancies; do not work around them. If a stated line number, test
  count, or figure in this brief does not match the repo, stop and report it.
- Any number that enters a file must be traceable to a repo artifact. Do not
  carry a figure from this brief into a report without recomputing it.
- Label every claim as executed / source-read / inferred.
- One commit per part. Do not push; the user pushes from Windows PowerShell.

## Out of scope (do not touch)
- CLAUDE.md item 12, the temporal leak. Open by decision, not neglect.
  Fixing it re-opens the confirmed headline.
- README.md. No edits in this brief, in any part.
- Any change to RECENCY_HALF_LIFE_DAYS, MIN_SCORE, MIN_CLUSTER_NATIVE,
  BACKFILL_ENABLED, or the noise convention (singletons).
- Any new selection experiment.

---

## Part A — deferred hardcoded constants

These are inert: nothing changes until someone edits a config value. That is
exactly why the invariant below is strict.

Sites (verify each before editing; report any that has moved):
1. scripts/canonical_impact.py — hardcodes 14 / 50 / 30 instead of reading config.
2. Four independently hardcoded `50` literals:
   - evaluate.py:199
   - evaluate.py:234
   - evaluate.py:772
   - config.EXCLUDE_TOP (confirm whether this one is the definition or a
     duplicate literal; report which)
3. k=20 hardcoded across four evaluate.py signatures. Replace with a default
   sourced from config, keeping the same effective value.
4. scripts/compare_backfill_ranking.py — Counter.most_common() with no
   tie-break. Apply the same fix already used in writer._modal_genre:
   min(counts.items(), key=lambda kv: (-kv[1], kv[0]))

Invariant: eval output byte-identical after every one of these.
Run `scripts/run.sh scripts/nested_eval.py` (no flags) before and after Part A
and diff. If any single change moves a number, that is a finding — stop, report
which site and what moved, and do not proceed to the next site.

Deliverable: reports/deferred_constants.md recording, per site, what changed and
the before/after diff result.

---

## Part B — build_notebook.py output guard

scripts/build_notebook.py run without --execute silently stripped 15 cells of
committed output from notebooks/01_eda.ipynb. Caught by git diff and reverted;
the script still has no guard.

Add a guard that refuses to write a notebook whose cell outputs would be
stripped, unless an explicit flag is passed. Do not auto-execute as the fix.

Invariant: notebooks/01_eda.ipynb byte-identical after this part.
Add a regression test.

---

## Part C — as_of anchor (run last, gated)

The plays table ends 2026-09-13T07:24:35Z. Anchoring as_of to wall-clock puts
the entire 0-7 day bucket outside the dataset, so every wall-clock measurement
since the 13th has had a phantom-empty recent window.

C1. Confirm the anchor first, by query, not assumption:
    SELECT MAX(watched_at) FROM plays;
    Report the value.

C2. scripts/dormancy_signals.py — change the --as-of default from wall-clock to
    MAX(watched_at). Keep --as-of working. Keep recording the as_of used in the
    output.

C3. Re-run dormancy_signals.py and diff reports/dormancy_signals.md.
    The 177 of 180 (98.3%) figure was computed 2026-09-16 under wall-clock,
    i.e. under this exact bug. It is expected to move.

    GATE: if any published figure moves, STOP. Report the old value, the new
    value, and every file that cites it (at minimum reports/listening_test.md
    and README.md). Do not update those files. Do not republish. The user
    decides what happens next.

C4. Audit-only, no fixes: grep the repo for other wall-clock reads
    (datetime.now, datetime.utcnow, date.today, time.time) and list them with
    file:line and whether each feeds a published figure. Append to
    reports/deferred_constants.md as a section. Fix nothing here.

---

## Explicitly report-only (do not fix)
- score.py:76 ValueError, reachable via rediscovery_half_life_sweep ->
  rediscovery_robustness:318; would drop a whole half-life row silently.
- evaluate.py:443-458 `_score` has no handler of its own, so evaluate.py:431's
  swallow is load-bearing and safe by invariant rather than by guard.
Confirm both are still accurate and record them in reports/deferred_constants.md.
Do not add guards.

## Done when
- Three commits, one per part.
- Full suite passing; report the count (starting point 531 — if it differs,
  report the discrepancy rather than assuming).
- reports/deferred_constants.md written.
- Nothing pushed.
