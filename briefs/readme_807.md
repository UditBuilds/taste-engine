# Brief — Rewrite README §8 "Backfill" to match the code

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Read first:** reports/readme_audit.md, reports/backfill_plan.md,
briefs/backfill_constraint.md, briefs/backfill_rank.md

## The problem
README §8's Backfill section (~lines 807-857) describes
nearest-whole-cluster-by-centroid backfill, score-ranked, against
a fixed 45-track target. That mechanism was deleted. The worked
example is wrong in every column except total cluster size, and
the T-Series conclusion is REVERSED — the section argues the tool
knowingly ships an incoherent fill, but T-Series now backfills
zero tracks.

## What the section must describe
The five rules as they exist now, in order:
1. FLOOR — MIN_CLUSTER_NATIVE=12; below it, no playlist at all.
2. LENGTH — floor(native / (1 - MAX_BACKFILL_SHARE)), share 0.25.
3. GUARD — a backfill candidate must carry the cluster's modal
   genre.
4. RANK — candidates ordered by cosine distance to the requesting
   cluster's centroid, not by score.
5. CEILING — MAX_BACKFILL_DISTANCE=1.0; beyond it, refused.
   Rationale: distance >1.0 is negative cosine similarity.

Plus: a playlist returns SHORT rather than relaxing any rule.

## Worked example
Replace the stale one with a real, current example from
reports/backfill_plan.md. Use T-Series (22 native, 0 backfilled,
its one candidate refused at distance 1.1166) — it demonstrates
FLOOR, GUARD and CEILING in one case. Every number traceable to
the report.

## Also fix
- Any Quickstart or §8 command example using --limit with
  --cluster/--cluster-name. That now hard-errors.
- Test counts wherever stated: live count is 337.
- Anything the audit flagged as stale in this section.

## Hard constraints
- Do NOT touch §2 (just updated), the opener, or any section the
  audit did not flag.
- Do NOT write the concluding/interpretive paragraph. Describe
  the mechanism and the numbers; leave a clearly marked
  placeholder line `<!-- CONCLUSION: Udit writes this -->` where
  a summary judgement would go. I am writing that myself.
- Do not characterise the approach as refined, improved, or
  iterated. Describe what it does.
- No git commit, no push, no API calls.
- Code is not in scope. Docs only. If you find a code bug, report
  it, do not fix it.

## Report back
- Line ranges changed.
- Every number used, with its source.
- Anything in the section you could not verify.

## Anti-assumption rule
Every number from a committed report or the code. If not
traceable, say so.
