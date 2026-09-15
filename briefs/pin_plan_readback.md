## Correction acknowledged

`_window_end()` is pure date arithmetic — confirmed by reading it, and confirmed further downstream: `score.py`'s `scored_tracks()` falls back `as_of → end` whenever a window bound is set, so the test frame's scoring never touches `now()` either on this path. The drift is rows-in-window, not window-position. Applying that: Part 3 will not claim the pinned command reproduces README's numbers for a different `taste.db` — only that it's the command that produced *this* snapshot's numbers.

Before planning further I ran the advisor and then verified its one empirical concern myself (both read-only, no files touched, nothing committed):

**Pre-check done:** ran the current replay path twice as separate processes (`--split 2026-06-01 --test-days 30 -k 50 --half-life 14`, same window Part 2 will pin) — **byte-identical, confirmed** (`diff` empty). This mattered because that path runs HDBSCAN clustering, which has caused hash-seed nondeterminism elsewhere in this repo (`writer._modal_genre`). It doesn't here — PCA is seeded (`random_state=0`) and HDBSCAN's `eom` selection is deterministic on fixed input. So Part 2's "byte-identical" requirement is achievable as specified, not just hoped for.

## Plan

**Flag name:** `--test-end` (matching your own usage), an absolute `YYYY-MM-DD` string, plain arg like `--split` — no extra format validation, since `_window_end` never parses it, just passes it straight through to the existing `watched_at < ?` SQL bound.

### Part 1 — where things live

`_window_end(split_date, test_days, test_end=None)`: if `test_end` given, return it verbatim (bypassing the day-count arithmetic); if both `test_days` and `test_end` given, raise `ValueError`. This is the single point of truth — `split_frames`, `evaluate`, `evaluate_rediscovery`, `rediscovery_split`, and `sweep` (all single-split-per-call) gain a `test_end` passthrough parameter and inherit the check for free.

**Not touched:** `rediscovery_robustness`, `nested_rediscovery`, `sweep_splits`, `robustness`, `rediscovery_half_life_sweep` — these iterate their own hardcoded/independent split lists, so a single absolute end date would silently apply a different, inconsistent window width per split (no crash — `evaluate_rediscovery`'s `ValueError` on an empty/short window is already swallowed by `except ValueError: continue` in the loop, so it'd just quietly drop some splits and misreport others). No new parameter added there at all.

**CLI, in `main()`:**
- `--test-days`/`--test-end` mutual exclusion: an `argparse` mutually-exclusive group — free, standard message, no custom code.
- New guard, placed between `parse_args()` and `connect()` (so it fires with no `data/taste.db` needed): `--test-end` combined with `--rediscovery`, `--both`, `--sweep-splits`, or `--robustness` → `parser.error(...)` explaining why (multi-split sweep, inconsistent window per split). `--sweep-half-life` is *not* guarded — it calls `sweep()` with one fixed `split_date=args.split`, varying only half-life, so it's coherent with an absolute end date.

**Judgment call to flag:** your note says "hard error for `--test-end` with `--rediscovery` alone." `--both` triggers the identical unconditional `rediscovery_robustness()` call `--rediscovery` does (same `if args.rediscovery or args.both:` block), so leaving `--both` unguarded would let the exact same silent-inconsistency bug through. I'm extending the guard to `--both`/`--sweep-splits`/`--robustness` too, for the same reason `--limit` was rejected outright rather than special-cased. Say so if you want it scoped narrower.

**New field:** `test_plays` (`test["play_count"].sum()`, one line, already in scope) added to `evaluate()`'s return dict and `_print_report()`'s output — this is the number that actually drifts, and it's what Part 3 needs.

### Part 2 — the pinned run

Fully explicit, no reliance on any `config.py` default (same reasoning your note gave for `--test-end` itself, extended to `-k`/`--half-life`/`--split`):

```
bash scripts/run.sh -m taste_engine.evaluate --split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14
```

Bare replay, no `--both`/`--rediscovery` — sidesteps the multi-split guard entirely and matches what README §2's Replay table actually needs. I'll run it twice, diff the **raw command output** (not a header-bearing file — a run-date header would never diff-equal across two processes), confirm empty diff, then write `reports/eval_invariance.txt` with the header (commit SHA, run date, exact command) plus that verified output.

**Flag for confirmation:** this overwrites `reports/eval_invariance.txt`'s current content, which documents a *different* brief's rediscovery-invariance check (backfill mechanism, unrelated to this window-pinning). Your Part 2 says "overwriting it," and the new pinned command doesn't run rediscovery at all, so I'll take that literally unless you want the old content preserved elsewhere first.

### Part 3 — README §2, replay subsection only

Touches only the Replay table and its lift sentence (current lines ~371–379). **Leaves the Rediscovery/nested table (lines ~344–349) untouched** — those figures come from `nested_rediscovery()` via `scripts/nested_eval.py`, which iterates `MONTHLY_SPLITS`; an absolute end date is exactly as incoherent there as in `rediscovery_robustness`, so it isn't pinnable by this mechanism, and your drift table never showed those numbers as stale anyway.

Also updates the derived "+2.2%" lift sentence at line 378 — that number is computed from the stale 0.551/0.539 pair, so it moves with the table (a number, not framing — I'll leave "which is exactly why it is not the headline" as written).

Snapshot language, per your correction:
> Measured on a dataset snapshot dated `<pin run date>`. This is the command that produced these figures; a different `taste.db` will produce different ones.

Row counts cited will be `train_tracks` / `train_plays` / `test_tracks` / `test_plays` **from the pinned run itself**, labeled explicitly as window-scoped — not the README-opener's global 2,918 canonical-song count (§3, untouched). I will **not** claim the window "grew by N rows" — that would need a historical snapshot of this specific window's row count that doesn't exist anywhere in the repo. The mechanism (database state vs. calendar state) is confirmed by code-reading; the magnitude of drift isn't measured, so per the anti-assumption rule I'll only report the current snapshot's counts, not a delta.

### Tests to add

- `_window_end` / `split_frames`: returns `test_end` verbatim; raises `ValueError` on both bounds given.
- **Equivalence test** (the one that actually validates the half-open-interval arithmetic): `evaluate(..., split="2026-06-01", test_days=30)` and `evaluate(..., split="2026-06-01", test_end="2026-07-01")` produce identical results.
- CLI (`main()` called directly, no DB required — fires before `connect()`): `--test-days`+`--test-end` → `SystemExit(2)`; `--test-end` with each of `--rediscovery`/`--both`/`--sweep-splits`/`--robustness` → `SystemExit(2)`; `--test-end` with `--sweep-half-life` → succeeds (the "safe" side, not just the error side).

### Report back (once you approve and I run it)

Flag name and exact pinned command; byte-identical confirmation on the actual `--test-end` command (the pre-check above used `--test-days`, same window, same code path — I'll reconfirm on the real command since the deliverable should stand on its own); old-vs-new figures **side by side per metric** (the output shape changes with the new `test_plays` field, so this won't be a clean file diff); test count 324 → N (324 measured this session, not the audit's stale 320).

Four things above are marked as judgment calls beyond the brief's literal text (guard scope, no new global query, overwriting the report file, replay-only pin). Let me know if any should go differently — otherwise I'll start on Part 1.
