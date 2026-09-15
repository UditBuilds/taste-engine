# Brief — Make backfill switchable, default off

**Shell:** WSL Ubuntu
**Repo:** taste-engine
**Read first:** README.md §8 "Backfill", reports/backfill_plan.md,
CLAUDE.md's open item on coarse topicCategories

## Why
First live dry run of the Joji cluster backfilled three Playboi
Carti tracks and one Don Toliver track, admitted by the genre
`pop` and ranked nearest by centroid distance (d=0.546, 0.637,
0.683, 0.704 — all well inside the 1.0 ceiling).

That is not a threshold problem. Both backfill signals measure
the wrong thing for this task:

- GENRE: YouTube topicCategories tag `pop` on 2,176 of 2,918
  canonical tracks (75%) and `hip hop` on 1,695. Six of ten
  qualifying clusters have no discriminative genre at all.
- DISTANCE: embeddings are a sentence-transformer over
  "title + artist" text. The space measures textual similarity
  of names and titles, not musical similarity. Nothing in the
  pipeline has audio features.

No threshold fixes a signal that measures the wrong quantity.
The backfill ARCHITECTURE is sound — T-Series demonstrates the
refusal path working correctly — so this brief does NOT delete
it. It makes it opt-in, defaulting off, until the inputs improve.

## The change

### config.py
- Add `BACKFILL_ENABLED = False` with a comment explaining the
  signal-quality reason above in two or three lines — not just
  "off by default".
- Leave MIN_CLUSTER_NATIVE, MAX_BACKFILL_SHARE and
  MAX_BACKFILL_DISTANCE in place and unchanged. They are still
  correct; they are just unused while backfill is off.

### writer.py
- When BACKFILL_ENABLED is False: FLOOR still applies (a cluster
  below MIN_CLUSTER_NATIVE still generates no playlist), and the
  playlist is the native eligible block only, in its existing
  order.
- Target length is then the native count itself. Do NOT compute
  `floor(native / (1 - MAX_BACKFILL_SHARE))` and then report the
  playlist as short by the difference — that would report a
  shortfall against a target that no longer applies.
- GUARD, RANK and CEILING code stays in place, unreached while
  disabled. Do not delete, do not comment out, do not move to a
  separate module.
- `render_plan()` must state plainly that backfill is disabled,
  and name the config constant, so a user reading dry-run output
  understands why no backfill appears.

### CLI
- Add a flag to enable backfill for a single run, overriding the
  config default. Name it as fits existing conventions; state the
  name you chose.
- The flag must not silently do nothing anywhere. If it cannot
  apply to a given invocation, error — same standard as the
  --limit fix.

## Tests
- With backfill disabled: a qualifying cluster returns exactly
  its native eligible tracks, no more.
- With backfill disabled: the plan does NOT report a shortfall.
- FLOOR still rejects a below-floor cluster when backfill is
  disabled.
- The CLI override flag re-enables backfill for one run and
  produces the same result as the current enabled behaviour.
- Every existing backfill test must still pass with backfill
  explicitly enabled — adapt fixtures if they relied on the old
  default, but do not weaken any assertion.

## Report regeneration
- Regenerate reports/backfill_plan.md with backfill disabled,
  so it reflects what actually ships.
- Keep the enabled-mode comparison in the report: for each
  qualifying cluster, what backfill WOULD have added and at what
  distance. That comparison is the evidence for the default.
- State the new quota total for writing all qualifying playlists
  native-only, against the 8,000/day cap.

## README
- Update §8 Backfill to describe the switch, the default, and
  why. Keep the five rules documented — they still govern when
  enabled.
- Update the worked example: keep T-Series, and add the Joji
  case as the example that motivated the default. Use the real
  numbers from the dry run above.
- Do NOT rewrite the concluding paragraph. Leave it byte-
  identical; I will revise it myself.

## Hard constraints
- Do not modify score.py, embed.py, canonical.py, evaluate.py,
  resolve.py.
- No live API calls, no --commit, no git commit, no push.
- Cluster IDs are unstable across runs; cluster_name is stable.
- Re-run the pinned evaluation and confirm nDCG unchanged:
  `--split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14`

## Report back
- The CLI flag name.
- Test count before and after.
- Native-only quota total vs the current 8,000/day cap.
- Per-cluster: native count shipped, and what backfill would
  have added if enabled.

## Anti-assumption rule
Every number from the data or a committed report. If not
traceable, say so.
