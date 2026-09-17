# Brief: ground-truth canonical/raw video ID mismatch

## Context
`cluster_eval.py` joins ground-truth playlist labels to tracks by video ID and
silently drops 48 of 486 tracks. Confirmed in the Sept 16 verification brief,
left unfixed. Ground truth is the denominator for ARI/NMI/purity, and the README
rewrite depends on those numbers, so this is measured before it is changed.

Baseline: commit 36e3b5a, 490 tests passing, min_samples=2, fixed seed.

## Part 0 — Diagnosis (READ-ONLY. Stop and report before Part 1.)

Write `scripts/ground_truth_audit.py`, output `reports/ground_truth_audit.md`.
Change no pipeline code in this part.

Report:
1. Total ground-truth rows, rows that join, rows that drop. Confirm the drop is 48.
2. Break the 48 down by cause, with counts:
   - raw video ID exists in `video_metadata` but has no canonical mapping
   - ground truth stores a canonical ID where the lookup uses a raw ID
   - ground truth stores a raw ID where the lookup uses a canonical ID
   - ID absent from the library entirely
   - anything else — name it, do not bucket it as "other" without a description
3. After mapping every ground-truth row raw -> canonical, count canonical tracks
   that receive MORE THAN ONE distinct playlist label. List them: canonical track
   id, track title, artist, the conflicting pseudonymised playlist names.
   This is the real risk — "filed in exactly one playlist" was enforced at the raw
   ID level, and canonicalisation can merge two raw IDs from two playlists.
4. State how many of the 48 are recoverable versus genuinely unmatchable.

STOP HERE. Do not fix anything until the conflict count is known.

## Part 1 — Fix (only after Part 0 is reviewed)

1. Fix the join so raw and canonical IDs resolve consistently. State in the commit
   message which direction the mapping now goes and why.
2. Conflict rule: DROP canonical tracks carrying conflicting playlist labels.
   Do not pick a winner, do not use play counts or recency to break the tie.
   Log the dropped count and expose it in the eval output.
3. The ground-truth denominator after this change must be reported explicitly in
   `cluster_eval` output — never inferred by the reader.

## Part 2 — Measurement (the point of the brief)

Produce `reports/ground_truth_ids.md` with a before/after table:

- All three embedding modes: title_artist, title_genre, title
- All three noise conventions from `coherence_by_convention()`: exclude /
  one-cluster / singletons
- Metrics: ARI, NMI, purity, and the ground-truth denominator for each
- Fixed seed, min_samples=2, same config as 36e3b5a otherwise

Answer these two questions in the report, in words, not just numbers:
1. Does the title_artist -> title_genre gap (0.179 at 36e3b5a) still survive the
   noise band from `briefs/min_samples_sweep.md` under every convention?
2. Does the ranking flip under any convention that it did not flip under before?

## Invariance check (non-negotiable)

Ground truth feeds coherence metrics ONLY. It must not touch scoring, clustering
input, or the recommender evaluation.

Re-run the pinned command:
`--split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14`

Rediscovery nDCG and replay figures must be BYTE-IDENTICAL before and after.
If anything moves, stop — ground truth is coupled to something it should not be.
Report that instead of continuing. Save the artifact as
`reports/eval_invariance_ground_truth.txt`.

## Part 3 — Tests and record

- Tests covering: the raw/canonical join both directions, the conflict-drop rule,
  the reported denominator, and a regression test asserting the recovered count.
- Add a row to the CLAUDE.md decisions table: the conflict rule and why drop
  rather than pick.
- DO NOT touch the README. That is separate work, after these numbers settle.

## Out of scope — do not fix in this brief
- `redact.py` alias rebuild rescrambling
- `resolve.py` caching a transient omission as found=0
- `genre_coverage.py` hard invariance gate (separate decision, still open)
- Any tuning of min_samples, MIN_SCORE, or half-life. That decision is closed.

## Environment
- Run from the main checkout at `C:\Users\uditk\Projects\taste-engine`, NOT a git
  worktree — `scripts/run.sh` hardcodes a cd to the main checkout and will
  silently test the wrong code.
- Commit email: 276203779+UditBuilds@users.noreply.github.com
