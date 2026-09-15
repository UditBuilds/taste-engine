# Brief — Make --limit fail loudly, and record the invariance check

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Read first:** reports/readme_audit.md

## Part 1 — --limit on cluster writes
Currently writer.py accepts --limit on a cluster-scoped write,
ignores it, and prints a note. A silently-ignored flag is worse
than a rejected one.

Change it to a hard error: if --limit is passed together with a
cluster-scoped request, exit non-zero with a message stating
that playlist length is computed from cluster depth
(MIN_CLUSTER_NATIVE / MAX_BACKFILL_SHARE) and --limit does not
apply. Do not silently proceed.

- --limit must keep working unchanged on non-cluster writes.
- Remove the now-dead "ignored" print.
- Tests: --limit + cluster = non-zero exit and no playlist
  object; --limit on a non-cluster write still behaves as
  before.

## Part 2 — record the invariance check
reports/readme_audit.md finds no committed artifact proving the
nDCG invariance check was re-run against the CURRENT mechanism.
Prior results only cover deleted code.

Re-run it and commit the evidence:
- Run the same --both --test-days 30 evaluation.
- Save the full output to reports/eval_invariance.txt as a
  committed file, with a header line giving the commit SHA and
  the date it was run.
- State in your report whether the nDCG figures match the ones
  currently in README.md, and quote both.
- If they DIFFER, stop immediately and report. Do not
  investigate, do not adjust, do not explain.

## Hard constraints
- Do NOT touch README.md. That is the next brief.
- Do not modify evaluate.py, score.py, embed.py, canonical.py,
  resolve.py.
- No git commit, no push, no API calls, no --commit.

## Anti-assumption rule
Every number from the data. If not computable, say so.
