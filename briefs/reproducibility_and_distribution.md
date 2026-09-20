# Brief: Reproducibility pass + dormancy distribution

**Date:** 2026-09-20
**Repo:** `taste-engine`
**Branch:** `main`
**Expected starting state:** tree clean, 517 tests passing, pushed through `6e475d9`.

---

## 0. Scope

Three parts, in order. They share a theme: **whether this project's existing measurements are reproducible, and what the eligible candidate pool actually looks like.**

- **Part A** — diagnose a `ValueError` that is silently swallowed inside the path producing the published headline. **Diagnosis only. No behaviour change without a go.**
- **Part B** — make `scripts/dormancy_signals.py` reproducible. It currently reads wall-clock.
- **Part C** — measure the distribution of `days_since_last_play` inside the eligible candidate pool. Read-only. This decides whether a follow-up design change is worth pursuing.

Part C depends on Part B being done first, so the measurement is pinned rather than being another snapshot.

### Out of scope — do not touch

- `README.md`, `CLAUDE.md`
- **Any existing file under `reports/`.** These are `as_of`-pinned evidence. In particular, **do not regenerate `reports/dormancy_signals.md`** — it contains the published 177/180 figure and it must survive this brief byte-identical.
- `scripts/nested_eval.py`, and any change to what the headline produces
- `score.py`, `MIN_SCORE`, `RECENCY_HALF_LIFE_DAYS`, `MIN_CLUSTER_NATIVE`
- `recommend.py` — the ranking-strategy change is a separate brief and Part C decides whether it happens at all
- `canonical_impact.py`'s hardcoded `14, 50, 30`, and the `k=20` defaults across four signatures. Real, known, deferred — leave them.
- Open item 12 (temporal leak). Leave it open.
- Any live YouTube write or API call.

---

## 1. Gate

1. Confirm branch `main`, tree clean, `6e475d9` pushed.
2. Run the full suite, record the count. Stop and report on any failure.
3. Record the starting SHA.

---

## Part A — The swallowed `ValueError` (DIAGNOSE, REPORT, STOP)

### What's known

`evaluate.py:318-319` (and the same pattern elsewhere, including inside `nested_rediscovery`) wraps split evaluation in:

```python
try:
    report = evaluate_rediscovery(...)
except ValueError:
    continue
```

A split that raises is silently dropped. **This is firing today.** A run on 2026-09-19 reported the early splits failing the usability bar as: reachable 0, reachable 2, **a `ValueError`**, then reachable 11.

So one of your nine monthly splits is being discarded by an exception rather than by the `reachable >= 20` rule, inside the path that produces the published headline.

### What to find out

1. **Every place this pattern appears.** Cite each `file.py:line`.
2. **Which split raises**, by date.
3. **What the exception actually is** — the message and the line that raises it.
4. **Whether the split is genuinely unusable.** Is this an empty window, a legitimately degenerate case, or a bug discarding valid data?
5. **Whether it changes the headline.** `len(usable)` is currently 5, and `held = usable[cut:]` with `cut = len(usable)//2` gives `held=3` at both 5 and 6. So if that split *were* usable, does `n` stay 3, and does the membership of the held-out set change? **Answer this precisely** — it determines whether this is cosmetic or material.
6. **Whether any other exception type could be swallowed** by the same handlers.

### Hard constraints

- **Do not change the handler's behaviour in this part.** Adding a `stderr` warning is the obvious fix and it is *probably* right, but if the split turns out to be recoverable, the correct fix is different and it would move published numbers.
- **Do not re-run `nested_eval.py` with modified code.** You may run it unmodified, and you may write a throwaway diagnostic script in a scratch directory that does not write to the repo.

**Stop at the end of Part A. Report and wait for a go before Parts B and C.**

---

## Part B — Make `scripts/dormancy_signals.py` reproducible

### The problem

`scripts/dormancy_signals.py:109` does:

```python
as_of = pd.Timestamp.now(tz="UTC")
```

Every run shifts the analysis window. The figures in `reports/dormancy_signals.md` — including the published **177 of 180 (98.3%)** — are a snapshot of when the script ran, not a property of the dataset. Nothing records that this is so.

### The fix

Add an explicit `as_of` parameter with a CLI flag, **defaulting to current behaviour** (wall-clock) so nothing silently changes for an existing caller. Then:

1. The `as_of` actually used must be written into the script's output, clearly labelled, so any future report states the timestamp its figures depend on.
2. Add a note in the script itself that figures are `as_of`-dependent and must be compared only against runs at the same `as_of`.

### Hard constraints

- **Do not regenerate `reports/dormancy_signals.md`.** `git diff` must show it unchanged. If you want to verify the script still works, write output to a scratch path outside the repo.
- Do not change what the script computes — only how `as_of` is obtained and recorded.
- Add a test covering that an explicitly passed `as_of` is used and appears in the output.

---

## Part C — The dormancy distribution inside the eligible pool (MEASURE ONLY)

### Why

Yesterday's feasibility measurement (`reports/recency_exclusion.md`) tested survivors at 30, 60 and 90 days and found 2 of 139, then 0, then 0. That killed a downstream recency filter.

But it never measured the distribution **between** 0 and 30 days, and that's the interesting range — because eligibility is not a flat recency window. It scales with play count. With `MIN_SCORE = 0.5` and a 14-day half-life:

| plays | stays eligible up to roughly |
|---:|---:|
| 1 | 6.6 days |
| 10 | 32 days |
| 30 | 39 days |

**Verify that arithmetic against `score.py` rather than trusting this table.** If it's wrong, say so — it's the premise of the whole measurement.

If it's right, a heavily-played track can sit ~35 days unheard and still be eligible. The open question is whether there are enough such tracks to matter.

### What to measure

Read-only, at a **pinned `as_of`** (use Part B's new parameter), for each qualifying cluster and in aggregate:

1. **Histogram of `days_since_last_play`** across all tracks passing `score >= MIN_SCORE`. Buckets: 0–7, 7–14, 14–21, 21–28, 28–35, 35+.
2. For each bucket: **track count, and median play count.** The play-count column is the point — it tests whether the older buckets are in fact the heavily-played tracks the arithmetic predicts.
3. **What currently ships:** where in that distribution do the top-20-by-score tracks fall, per cluster?
4. **What would ship if ranked by `days_since_last_play` descending** instead, restricted to the same eligible pool: the same distribution, plus each candidate's play count.
5. **Overlap** between (3) and (4) per cluster — how many tracks differ?

### The question to answer plainly

**Is there a population of heavily-played, 3-to-5-weeks-dormant tracks large enough to fill a playlist?**

Answer it in one line per cluster and once in aggregate. If the answer is no, say so — that closes the direction before any code gets written, as yesterday's did.

### Constraints

- Reuse `dormancy.plays_in_window`, `build_frames`, `qualifying_clusters`. Do not reimplement.
- Do not change ranking, `recommend.py`, or anything that ships.
- **Do not tune anything to make the answer come out well.** Report the distribution as measured.
- Write `reports/dormancy_distribution.md` with provenance (SHA, pinned `as_of`, row counts, exact commands), all tables, and the plain verdict. Write it whatever the outcome.

---

## 2. Acceptance criteria

- [ ] Part A reported, stopped on, no behaviour changed
- [ ] Part A answers whether the dropped split would change `n` or held-out membership
- [ ] `reports/dormancy_signals.md` byte-identical (`git diff` proves it)
- [ ] `dormancy_signals.py` default behaviour unchanged; `as_of` recorded in output; test added
- [ ] `reports/dormancy_distribution.md` written, at a pinned `as_of`, with the verdict stated plainly
- [ ] The eligibility arithmetic verified against `score.py`, not assumed
- [ ] `README.md`, `CLAUDE.md`, all existing reports untouched
- [ ] Full suite green
- [ ] Committed, **not pushed**

## 3. Traps

1. **Do not `git push`.** WSL has no credentials.
2. **Commit email must be `276203779+UditBuilds@users.noreply.github.com`.**
3. **Line endings** — `.gitattributes` handles it. A diff of thousands of unchanged lines means stop and report.
4. **`scripts/dormancy_signals.py` writes `reports/dormancy_signals.md` on `main()`.** Redirect to a scratch path when testing.
5. **Scores drift as the database grows.** Known. This is why Part C pins `as_of`.
6. **Cluster ids and membership move between runs.** Known (CLAUDE.md item 9). Report ids as observed; don't reconcile them against older reports.

## 4. Report format

1. Gate: SHA, test count
2. Part A: every occurrence, which split, the exception, whether the split is genuinely unusable, and the precise answer on `n` and held-out membership — **then stop**
3. (after go) Part B: what changed, proof the existing report is untouched, the test added
4. Part C: the arithmetic check, all tables, the plain verdict
5. Anything you wanted to change and didn't
6. Commit SHAs
