# Brief: as_of through the scoring core, then re-measure dormancy_distribution

## Context
Repo is 3 commits ahead of origin (751d8ef, 7e5c532, 9791196), 535 tests passing.
briefs/deferred_constants.md fixed the as_of anchor in dormancy_signals.py only.
The same bug class remains in the scoring core: recommend.build() never exposes
as_of to score.py, so the eligible pool (MIN_SCORE=0.5) is still computed at
wall-clock while dormancy bands are now computed at MAX(watched_at).

reports/dormancy_distribution.md was measured under the old anchor. Its bands
labelled 21-35 days were really measuring 14-28 days of dormancy. That report
is the sole basis for the closed direction "there is no dormant population to
rank". It must not be re-measured until the eligibility gate shares the anchor,
or the result mixes two clocks.

## Standing rules
- Report discrepancies; do not work around them. If a stated commit, test count
  or figure does not match the repo, stop and report it.
- Any number entering a file must be traceable to a repo artifact. Do not carry
  a figure from this brief into a report without recomputing it.
- Label every claim as executed / source-read / inferred.
- One commit per part. Do not push.
- Parts run in order. Part B does not start until Part A's gate passes.

## Out of scope (do not touch)
- CLAUDE.md item 12, the temporal leak. Open by decision.
- README.md. No edits, any part.
- Any change to MIN_SCORE, RECENCY_HALF_LIFE_DAYS, MIN_CLUSTER_NATIVE,
  BACKFILL_ENABLED, or the noise convention (singletons).
- Re-running dormancy_probe.py or any report it feeds. Its code fix is in scope
  (A3); re-measuring it is not.

---

## Part A - expose as_of through the scoring core

A1. Read first, change nothing. Trace how as_of reaches score.py today:
    - recommend.build() signature and every call site
    - score.py's use of wall-clock (datetime.now / utcnow / date.today)
    - which reports depend on this path (expected: reports/backfill_plan.md)
    Report the trace with file:line before editing.

A2. Add an `as_of` parameter to recommend.build(), threaded to score.py.
    DEFAULT: MAX(watched_at), queried from the plays table, NOT wall-clock.
    This is a deliberate behaviour change for every caller. Keep an explicit
    override available.
    Query the anchor, do not hardcode it. Report the value returned.

A3. scripts/dormancy_probe.py - add an --as-of override with the same
    MAX(watched_at) default. Code only. DO NOT run it, DO NOT regenerate
    reports/dormancy_probe.md. README cites that report.

A4. GATE - run `scripts/run.sh scripts/nested_eval.py` (no flags) and diff
    against the current committed output.
    - If byte-identical: record that, proceed to Part B.
    - If ANY number moves: STOP. Do not proceed to Part B. Report what moved,
      by how much, and which call path carried the change. The headline
      (0.3312 / 0.1382 / +139.7% / 3-of-3 / p=0.125) is confirmed and
      reproduced; moving it is a halting finding, not something to absorb.

A5. Record in reports/asof_core.md: the A1 trace, the anchor value, the A4
    diff result, and every report whose inputs now change anchor.

---

## Part B - re-measure dormancy_distribution (only if A4 passed byte-identical)

PRE-REGISTERED BEFORE RUNNING. Do not alter these after seeing results.

Bar: 20 tracks, taken from the existing reports/dormancy_distribution.md.
Band: 21-35 days dormant, per single cluster. Pooled-across-clusters counts
may be reported as context but do NOT decide the verdict - no single write
combines clusters.

Verdict rules, both stated in advance:
- If any single cluster's 21-35 day band >= 20 tracks: the seventh direction
  REOPENS. Report it; implement nothing.
- If every cluster's band < 20: the direction STAYS CLOSED, now on a
  consistent anchor. Report the largest band and the cluster it came from.

B1. Re-run the dormancy_distribution measurement with the corrected anchor
    reaching both the eligibility gate and the band computation. Confirm in
    output which as_of each stage used - they must match.

B2. Write reports/dormancy_distribution_pool198.md as a NEW file. Do not
    overwrite reports/dormancy_distribution.md. Include, on every row, the
    anchor used and the denominator.

B3. Report the old-vs-new comparison explicitly: previous largest band
    (7, T-Series) vs new largest band, and the eligible pool (was 198) vs new.

B4. Do not edit README.md, reports/listening_test.md, or
    reports/recency_exclusion.md even if the verdict changes. Report the
    consequence; the user decides.

---

## Part C - finish the unnamed Part A sites from briefs/deferred_constants.md
Run last. Skippable if Parts A/B produce anything needing attention.

The previous brief's agent flagged but did not fix:
- 3 further exclude_top=50 defaults in evaluate.py
- 2 further hardcoded 20s in evaluate.py
Locate them, confirm the counts (report if they differ), route them to config
the same way Part A of that brief did.
Invariant: nested_eval byte-identical. If it moves, revert and report.

---

## Done when
- Up to three commits, one per part.
- Full suite passing; report the count (starting point 535 - report any
  discrepancy rather than assuming).
- reports/asof_core.md written; reports/dormancy_distribution_pool198.md
  written only if Part B ran.
- Nothing pushed.
