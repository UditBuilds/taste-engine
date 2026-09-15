# Brief — README staleness audit (report only, no edits)

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Read:** reports/backfill_plan.md, reports/genre_coverage.md,
briefs/backfill_constraint.md, briefs/backfill_rank.md

## Task
Find every claim in README.md that is now false or misleading
after commit 58799f7. Report them. Do NOT edit README.md.

## What to find
1. Every line describing the OLD backfill mechanism (nearest
   embedding centroid, the fixed 45-track target, the --limit
   flag on cluster requests). Give line numbers and exact text.
2. Every number stated anywhere in the README that this work
   changed or invalidated. Line number, stated value, current
   value.
3. Any claim that is still true but now incomplete — e.g. a
   section describing playlist construction that no longer
   mentions the floor, the length formula, the genre guard, or
   the distance ceiling.
4. Anything in CLAUDE.md that contradicts the README after the
   SUPERSEDED row was added.

## Also assemble (facts only, no prose)
A plain bullet list of the verified current numbers a rewrite
would need: clusters clearing the floor, total real clusters,
distinct backfill tracks, total backfill slots, T-Series's
outcome and distance, the tie vote counts, test count, and the
nDCG invariance result. Each with where it came from.

## Hard constraints
- Do NOT write, edit, or draft README prose. Not even a
  suggested paragraph. I am writing the rewrite myself.
- Do NOT edit any file except creating reports/readme_audit.md.
- No git commit, no push, no API calls.

## Output
reports/readme_audit.md — the three lists above, nothing else.

## Anti-assumption rule
Every number from the data or a committed report. If a number
can't be traced to one, say "not traceable" rather than
restating it.
