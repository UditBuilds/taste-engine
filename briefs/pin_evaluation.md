# Brief — Pin the evaluation window, then refresh README §2

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Read first:** reports/eval_invariance.txt, reports/readme_audit.md

## The problem
`--test-days 30` counts backward from `datetime.now()`, so the
evaluation window slides with the calendar and the dataset keeps
growing. README §2's replay figures cannot be reproduced by
running the documented command:

| figure | README | today |
|---|---|---|
| score nDCG@50 | 0.551 | 0.5506 |
| most_played nDCG@50 | 0.539 | 0.5421 |
| score Spearman | 0.371 | 0.3583 |
| most_played Spearman | 0.440 | 0.4300 |

Confirmed NOT a regression: commit 55615fc (pre-change) produces
0.5421 / 0.4300 identically. The drift is dataset state, not code.

## Part 1 — make the window absolute
Add an explicit end-of-window bound to evaluate.py so the replay
evaluation is deterministic given the same database.

- New CLI flag for an absolute test-window end date. Name it as
  fits the existing flag conventions; state the name you chose.
- When passed, the test window is [split_date, end_date) — no
  reference to now() anywhere in that path.
- When NOT passed, behaviour is unchanged (relative --test-days),
  so existing callers and scripts keep working.
- Plays after end_date are excluded from the test set entirely.
- The two must be mutually exclusive: passing both --test-days and
  the new flag is an error, not a silent precedence rule. Same
  reasoning as the --limit fix.

## Part 2 — record the pinned result
- Choose the end date as split_date + 30 days so the pinned run
  covers the same window README's numbers were meant to describe.
  State the exact date.
- Run the pinned command. Save full output to
  reports/eval_invariance.txt, overwriting it. Header must give
  the commit SHA, run date, and the exact reproducing command.
- Run it TWICE in separate processes and confirm byte-identical
  output. A pin that isn't verified isn't a pin.

## Part 3 — README §2 only
- Update ONLY the §2 evaluation tables to the pinned figures.
- Add the exact reproducing command next to the table.
- Cite reports/eval_invariance.txt as the artifact.
- State the dataset snapshot date, so a reader with a different
  database understands why theirs may differ.
- Do NOT touch §807, §8, the Quickstart, or any other section.
  Those are the next brief.
- Do not editorialise about the scorer's performance. Report
  figures; I write the framing.

## Hard constraints
- evaluate.py may be modified (this brief supersedes the earlier
  prohibition, for this file only).
- Do NOT modify writer.py, score.py, embed.py, canonical.py,
  resolve.py.
- No git commit, no push, no API calls, no --commit.
- Tests must stay green; add tests for the new flag, including
  the mutual-exclusion error.

## Report back
- The flag name and the exact pinned command.
- Byte-identical confirmation across the two runs.
- Old vs new figures side by side.
- Test count before and after.

## Anti-assumption rule
Every number from the data. If not computable, say so.
