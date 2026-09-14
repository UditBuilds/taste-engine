# Brief — Depth-Based Playlist Length + Genre Guard

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Prior measurement:** reports/genre_coverage.md — read it first, do not re-derive its numbers.

## Problem
All 37 real clusters are shallow (<45 eligible). The current fixed
45-track target forces heavy backfill, and nearest-centroid backfill
pulls musically unrelated tracks (T-Series padded with Travis Scott).
The target is the bug, not the padding method.

## The rule (replaces the fixed 45 target)
1. FLOOR — a cluster with fewer than config.MIN_CLUSTER_NATIVE
   eligible members generates NO playlist. Skip it entirely.
2. LENGTH — target length = floor(native / (1 - MAX_BACKFILL_SHARE)).
   Backfill may never exceed MAX_BACKFILL_SHARE of final length.
3. GUARD — a backfill candidate must share at least one genre label
   with the cluster's modal genre. If not enough genre-matching
   candidates exist, return SHORT. Never relax the guard to hit length.

## New config constants (config.py)
- MIN_CLUSTER_NATIVE = 12
- MAX_BACKFILL_SHARE = 0.25
Do not hardcode these anywhere else.

## Modal genre
Compute per cluster from its eligible members' tidied genre labels,
using the same definition reports/genre_coverage.md used. Reuse the
existing tidy/label path (embed.tidy_genres); do not write a new one.

## Hard constraints
- Modify writer.py and config.py only. Do NOT touch score.py,
  embed.py, canonical.py, evaluate.py, or resolve.py.
- NO YouTube API calls. NO --commit. Dry-run output only.
- Do NOT git commit or push.
- Cluster IDs are UNSTABLE across runs; cluster_name is stable.
  Never key logic, config, or test fixtures to a cluster id.
- Remove the old nearest-centroid backfill path. Do not leave both
  behind a flag.

## Invariance check (required)
Re-run the rediscovery evaluation before and after. evaluate.py must
not read playlist construction at all, so nDCG@20 must be BYTE-IDENTICAL.
If it moves, you have leaked playlist logic into evaluation — stop and
report, do not adjust the number.

## Tests (new, in the existing test suite)
- cluster below floor yields no playlist
- backfill share never exceeds MAX_BACKFILL_SHARE
- a cluster with a rare modal genre returns short rather than
  borrowing a non-matching track
- length formula correct at native = 12, 22, 29

## Output
- Dry-run plan for all qualifying clusters: cluster_name, native count,
  backfill count, final length, modal genre, and for each backfill
  track the genre that admitted it.
- Write to reports/backfill_plan.md
- Flag total quota cost and whether it exceeds the 8,000/day ledger.

## Anti-assumption rule
Every number must come from the data. If something is not computable,
say "not computable" — do not estimate.
