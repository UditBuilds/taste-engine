Everything's implemented, tested, and verified. Here's the full report.

## What changed

`config.BACKFILL_ENABLED = False` is now the master switch. `writer.py` gates LENGTH/GUARD/RANK/CEILING behind it (early-return in `_select_with_backfill` right after `native_count` is computed — that code stays in place, just unreached). CLI gets **`--backfill`** to re-enable it for one run, with explicit errors (not silent no-ops) when it's passed without a cluster, or alongside `--resume`/`--rollback`. Two companion scripts not named in the brief (`scripts/backfill_report.py`, `scripts/compare_backfill_ranking.py`) also got fixed — they call `writer.plan()` too and would have silently started lying once the default flipped.

## Tiramisu — verified against the DB, not assumed

Video `_pqiY9FbWd8`, title exactly `"Tiramisu"`, channel **"Don Toliver - Topic"**. The other 5 "Tiramisu" hits in the DB all carry suffixes (remix/edit/official video) that wouldn't produce that bare title. Your brief's "one Don Toliver track" is correct — now traceable to the DB, not just your recollection.

## Test count

**337 → 345** (8 new tests, all passing): native-only under the real default, the config-path (not just parameter-path) honors `BACKFILL_ENABLED=True`, no-shortfall-when-disabled, FLOOR rejects regardless of the flag (parametrized True/False/None), plus two for the `--backfill`-without-a-cluster validation. All pre-existing backfill tests still pass with `backfill=True` added explicitly (~13 call sites adapted, no assertions weakened).

## Pinned eval — byte-identical, no new file

Ran `--split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14` before and after every code change. `diff` exit 0 — completely identical output. Confirms the same thing `reports/eval_invariance_backfill.txt` already documents; per your instruction, I didn't create a third file for it.

## Native-only quota vs. the 8,000/day cap

**9,760 units — exceeds the cap.** 8 of 10 qualifying clusters could be written today, cheapest-first.

| cluster | native (shipped) | shipped quota | if `--backfill` | if-enabled final | if-enabled quota |
|---|---|---|---|---|---|
| Joji | 12 | 651 | +4 | 16 | 851 |
| 21 Savage | 14 | 751 | +4 | 18 | 951 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 701 | +4 | 17 | 901 |
| T-Series / Pritam / Sony Music India | 21 | 1,101 | +0 (ceiling refuses Doja Cat, d=1.1166) | 21 | 1,101 |
| Drake | 19 | 1,001 | +6 | 25 | 1,301 |
| Future | 19 | 1,001 | +6 | 25 | 1,301 |
| The Weeknd | 20 | 1,051 | +6 | 26 | 1,351 |
| Travis Scott | 20 | 1,051 | +6 | 26 | 1,351 |
| Don Toliver | 21 | 1,101 | +7 | 28 | 1,451 |
| Metro Boomin | 26 | 1,351 | +8 | 34 | 1,751 |
| **total** | | **9,760** | | | **12,310** |

(If-enabled total also exceeds the cap: 12,310 vs 8,000, 7 of 10 affordable.) `reports/backfill_plan.md` now leads with this "What ships" table and relabels everything else as the enabled-mode comparison you asked me to keep.

## CLAUDE.md

Added the decisions-table row for `BACKFILL_ENABLED = False`, dated 2026-09-15.

## Worktree — nothing committed, nothing pushed

Path: **`/mnt/c/Users/uditk/Projects/taste-engine/.claude/worktrees/backfill-toggle`**, branch **`worktree-backfill-toggle`**. Per your hard constraint I made zero commits — everything is sitting as uncommitted working-tree edits (`git status` shows 10 modified files, `git diff --check` clean, no stray files). To get it into your main checkout:

```bash
cd /mnt/c/Users/uditk/Projects/taste-engine/.claude/worktrees/backfill-toggle
git diff                                    # review
git add -A && git commit -m "..."           # your message, your call
cd /mnt/c/Users/uditk/Projects/taste-engine
git merge worktree-backfill-toggle          # brings the commit into main
git worktree remove .claude/worktrees/backfill-toggle   # optional cleanup
```

One thing worth knowing: your branch already sits on top of `ab9afde` ("README: describe the backfill rules as they now work") — I checked, that's an ancestor of my branch, not a concurrent edit I clobbered. My README edits landed on that content correctly (confirmed by every `Edit` call matching exact text, none failed).

## Two things I noticed but did not touch (out of scope for this brief)

1. README's "What the measurement found..." paragraph (the one right before "The design that survived...", which I left frozen per your instruction) says "six of the ten qualifying clusters have no discriminative genre at all" — but both the old and freshly-regenerated `backfill_plan.md` tables show only **5** with `strict_modal=none` (Don Toliver, 21 Savage, Future, Travis Scott, Drake). Pre-existing, not something I introduced. Flagging rather than fixing since it's outside what you asked for.
2. A minor infra gap I worked around but didn't fix: `scripts/run.sh` hardcodes `cd` to the main checkout, so running it from inside *any* worktree silently tests the main checkout's code instead of the worktree's. I used direct `python -c` invocations with an explicit `sys.path` insert instead, and symlinked the worktree's (gitignored) `data/` to the main checkout's for the duration — removed before finishing. Not fixing `scripts/run.sh` itself since it's unrelated to this brief.

result: `--backfill` toggle shipped (off by default), 345/345 tests pass, pinned eval byte-identical, all uncommitted in worktree `backfill-toggle` — awaiting your review/commit/merge into main.
