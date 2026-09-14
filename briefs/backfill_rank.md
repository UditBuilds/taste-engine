# Brief — Genre Filters, Distance Ranks

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Read first:** reports/backfill_plan.md, briefs/backfill_constraint.md

## What went wrong
The shipped guard filters by genre then ranks by global score.
Score order is identical for every cluster, so all ten playlists
draw the same top-scored tracks: 10 distinct backfill tracks fill
52 slots. Drake, Future and Lil Baby have byte-identical backfill.
Removing nearest-centroid ranking removed the only per-cluster
differentiator.

## The change
Genre guard stays exactly as-is — it FILTERS the candidate pool.
Ranking within that filtered pool changes from score to embedding
distance to the requesting cluster's centroid, ascending.

- Rank INDIVIDUAL candidate tracks by distance to the requesting
  cluster's centroid. Do NOT restore _clusters_by_distance() —
  nearest-whole-cluster is too coarse and is what failed on
  2026-09-13.
- Deterministic tie-break: (distance asc, score desc, video_id asc).
- Everything else unchanged: FLOOR, target-length formula,
  MIN_SCORE, noise exclusion, favourites exclusion, native-then-
  backfill row order.
- _cluster_centroids() was deleted in the current HEAD. Recover it
  from commit 55615fc rather than rewriting it.

## Do NOT
- Do not add a distance ceiling or any new config constant. That is
  a separate decision I will make from the numbers you report.
- Do not touch score.py, embed.py, canonical.py, evaluate.py,
  resolve.py.
- No API calls, no --commit, no git commit, no push.
- Cluster IDs are unstable across runs; cluster_name is stable.

## Required new test
The existing suite passed while producing identical backfill across
six playlists — no test covers this. Add one:

- Across a full multi-cluster dry run, assert that no two clusters
  receive an identical backfill set, and that the count of distinct
  backfill tracks across all playlists is greater than the largest
  single playlist's backfill count.
- Keep every existing guard-contract test (every backfilled row
  carries the cluster's modal genre) passing unchanged.

## Invariance check
Re-run the same --both --test-days 30 evaluation. nDCG must be
BYTE-IDENTICAL to the saved baseline. If it moves, stop and report;
do not explain the difference away.

## Report (regenerate reports/backfill_plan.md)
Keep the existing sections. Add:
1. Distinct backfill tracks across all playlists, and the
   before/after comparison against the current 10-of-52.
2. For every admitted backfill track: its distance to the
   requesting cluster's centroid.
3. A distance distribution summary — min, median, max, and the
   distance of each admitted track for T-Series specifically.
4. State plainly whether T-Series still admits Doja Cat and at what
   distance.

## Anti-assumption rule
Every number from the data. If not computable, say "not computable".
