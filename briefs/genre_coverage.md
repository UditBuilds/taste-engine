# Brief — Genre Coverage Measurement (read-only)

**Shell for every command:** WSL Ubuntu
**Repo:** taste-engine
**Scope:** measurement only. No fix.

## Hard constraints
- Do NOT modify writer.py, config.py, evaluate.py, or any existing module.
- Do NOT make any YouTube Data API calls. Use cached/persisted metadata only.
  If the genre field is not already cached, STOP and report that — do not fetch.
- Do NOT git commit or push.
- New code goes in `scripts/genre_coverage.py` only. One new file.

## Step 0 — locate, don't assume
Find where canonical tracks, cluster assignments, scores, and any
genre/topic field are actually persisted. Report the exact file paths
and field names you used before reporting any numbers. If a genre
field does not exist anywhere in the cached data, say so and stop.

## Definitions
- Canonical track: as produced by the existing canonical-track layer.
- Eligible candidate: score >= config.MIN_SCORE.
- Shallow cluster: any cluster whose eligible members < 45.
- Genre match: shares at least one genre label with the cluster's
  modal genre. State explicitly how you computed the modal genre.

## The three numbers
1. **Coverage** — % of canonical tracks carrying >=1 genre label.
   Also: % carrying >1, and the top 15 labels by track count.
2. **Per shallow cluster** — a table with one row per shallow cluster:
   cluster id, eligible member count, modal genre, and how many
   eligible candidates outside the cluster share that genre.
3. **Reachability** — of the shallow clusters, how many could reach
   45 tracks using only genre-matching eligible candidates.

## Also report
- Coverage broken down by uploader type (`- Topic` vs VEVO vs other),
  since auto-uploads are the suspected gap.
- Any cluster where the modal genre is ambiguous (no label above 50%).

## Output
- Print a summary table to stdout.
- Write the full report to `reports/genre_coverage.md`.
- End with one sentence: is a genre-constrained backfill viable on
  this data, yes or no, and the number that decides it.

## Anti-assumption rule
Every number must come from the data. If something can't be computed
from cached data, say "not computable" — do not estimate.
