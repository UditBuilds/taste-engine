# Brief: Recency-based exclusion for rediscover (Option C)

**Date:** 2026-09-20
**Repo:** `taste-engine`
**Branch:** `main`
**Expected starting state:** tree clean, pushed through the `179 of 183` correction (`f0bc757`).

---

## 0. The problem, and what this is not

`--mode rediscover` ships tracks that are still in heavy rotation. Measured: **177 of 180 shipped tracks (98.3%)** across all 10 qualifying clusters had been played within the previous 30 days (`reports/dormancy_signals.md:188`, computed 2026-09-16).

The cause is that the only exclusion is **global top-50 by raw play count** (`recommend.favourites`, `recommend.py:20-41`), applied once across the whole library before any cluster filtering (`writer.py:379-386`). Your own measurement found 2 of 10 qualifying clusters overlap that top-50 **zero** times, and the rest lose 1–8 tracks — so for most clusters the exclusion does nothing.

**This brief adds a second, recency-based exclusion: drop tracks played within the last N days.**

### Why this and not the alternatives

Two other fixes were considered and rejected before writing this:

- **Per-cluster top-N exclusion** — the replacements are ranked by the same score, which rewards recency, so it would swap recent tracks for other recent tracks.
- **Longer half-life** — flattens decay toward 1, so score converges on `log1p(play_count)` and ships all-time favourites, which are mostly also recent.

Both change *which* recent tracks ship. Only a recency filter attacks freshness directly.

### On the dormancy probe

`reports/dormancy_probe.md` found dormancy signals weak. **That finding does not block this work, and you should not treat it as doing so.** The probe tested dormancy as a **ranking** signal — whether "days since last play" orders candidates usefully — and found it mostly measures when a track first appeared, given a 362-day window and 61.8% single-play tracks.

This brief uses recency as an **exclusion filter**, which is a different use. "Don't ship what I heard last week" can work as a filter even when the surviving order carries no information. If you find yourself about to argue this is already-closed ground, re-read the probe's own scope first, then raise it — don't silently narrow the work.

### Out of scope — do not touch

- `config.RECENCY_HALF_LIFE_DAYS`, `MIN_SCORE`, or any scoring code in `score.py`
- The existing global top-50 exclusion (`recommend.favourites`) — leave its behaviour exactly as is
- The four independently hardcoded `50` literals in `evaluate.py:199`, `:234`, `:772`. **Do not unify them in this brief.** They are a real latent defect and belong in their own change; touching them here would mix a refactor into a behaviour change.
- `README.md`, `CLAUDE.md`, and every existing file under `reports/`
- `nested_eval.py`, `evaluate.py`, and anything that produces the published headline
- Any live YouTube write. Dry runs only.
- Open item 12 (the temporal leak). Leave it open.

---

## 1. Gate

1. Confirm branch `main`, tree clean, and that `f0bc757` is pushed.
2. Run the full suite; record the count. Stop and report if anything fails.
3. Record the starting SHA.

---

## 2. Feasibility — MEASURE, REPORT, AND STOP

**This section can kill the brief. Do it before writing any implementation code, and stop at the end of it regardless of what you find.**

The risk is that a recency exclusion empties the candidate pool. Qualifying clusters run roughly 13–48 tracks, 98.3% of shipped tracks were played in the last 30 days, and `MIN_CLUSTER_NATIVE = 12` gates whether a cluster-scoped write happens at all.

Using read-only queries (`dormancy.plays_in_window` already exists — reuse it, do not reimplement):

For each of the 10 qualifying clusters, report:

| | |
|---|---|
| cluster | identifier and size |
| candidates today | tracks passing `score >= MIN_SCORE`, i.e. the current native-eligible count |
| survivors at 30d | how many of those were NOT played in the last 30 days |
| survivors at 60d | same, 60-day window |
| survivors at 90d | same, 90-day window |

Then state plainly, for each threshold: **how many of the 10 clusters would still clear `MIN_CLUSTER_NATIVE = 12`.**

Also report:
- The total candidate pool across all clusters at each threshold
- Whether any cluster survives at 90d (the aggressive end)
- `as_of` used, and today's row counts for `plays` and canonical tracks

**Verdict, stated in one line:** viable at 30d / viable at 60d only / viable at 90d only / not viable at any threshold.

**If no threshold leaves enough clusters above the floor, say so and stop. The brief ends there and that is a legitimate outcome** — it would be the sixth direction closed by measurement, and it gets written up as one rather than worked around.

**Stop here. Report and wait for a go.**

---

## 3. Implementation — only after an explicit go

### 3.1 Shape

Add recency exclusion as an **opt-in parameter with a default that preserves current behaviour exactly**. Do not redefine what `--mode rediscover` does today — every existing measurement in this repo used the current definition, and silently changing it would make them ambiguous.

- A new config constant, defaulting to `None`/off
- A CLI flag (suggested `--exclude-recent-days N`; use whatever matches this codebase's existing flag conventions)
- Applied in the same place as the global exclusion so both compose, with the existing exclusion untouched and running first

Where exactly it goes is your call from reading `writer.py:379-386` — **state where you put it and why** in the report.

### 3.2 Constraints

- With the parameter off, behaviour must be **byte-identical** to today. Prove this: run a dry-run plan before and after your change with the flag unset and diff the output.
- Reuse `dormancy.plays_in_window`. Do not write a second recency implementation.
- If a cluster falls below `MIN_CLUSTER_NATIVE` after exclusion, it must raise `WriteBlocked` the same way it does today. Shipping a short playlist silently is not acceptable; the existing failure path is correct.

### 3.3 Tests

- Parameter off → identical selection to before
- Parameter on → tracks played within the window are absent from the plan
- A cluster that drops below the floor after exclusion → `WriteBlocked`
- Boundary: a track played exactly N days ago (state which side of the boundary you chose and why)

---

## 4. Measurement

### 4.1 Recompute the baseline today — do not reuse 177/180

**The published 177/180 was computed at `as_of` 2026-09-16.** Recency figures move as the database grows and as calendar time passes. Comparing a today-run against a four-day-old baseline would produce a difference that is partly just elapsed time.

Recompute the current freshness figure using the same method as `reports/dormancy_signals.md`, at today's `as_of`, with the flag **off**. That is your baseline. Report it alongside the 2026-09-16 figure and note any difference.

### 4.2 Then measure with the flag on

At each viable threshold from §2, dry-run the plan and report:

- Shipped tracks played within the last 30 days — the headline freshness number, before and after
- Number of clusters that still produce a write
- Playlist lengths per cluster, before and after
- Any cluster that went from writing to `WriteBlocked`

### 4.3 State the cost honestly

This is a trade, not a free win. Report what was given up: fewer clusters, shorter playlists, or both. **If freshness improves but half the clusters stop writing, say that in the verdict line, not in a footnote.**

### 4.4 What this does not measure

State explicitly in the report: this measures **freshness**, not rediscovery **quality**. The repo has 7 hand-labelled data points for quality anywhere (`reports/listening_test.md:74`, `dormancy_signals.py:473-481`), and no automatic proxy for it. A tracks-are-fresher result does not establish that the playlists are better. Do not imply that it does.

---

## 5. Report file

Write `reports/recency_exclusion.md` containing: provenance (SHA, `as_of`, row counts, exact commands), the §2 feasibility table, the recomputed baseline against the old one, before/after at each threshold, the cost statement, the §4.4 limitation, and a one-line verdict.

Write it whatever the outcome — including if §2 kills the brief.

---

## 6. Acceptance criteria

- [ ] §2 reported and stopped on, before any implementation
- [ ] Flag-off behaviour proven byte-identical by diff
- [ ] `dormancy.plays_in_window` reused, not reimplemented
- [ ] Baseline recomputed today, not reused from 2026-09-16
- [ ] Tests added and passing; full suite green
- [ ] `reports/recency_exclusion.md` written
- [ ] `README.md`, `CLAUDE.md`, and every existing report unmodified
- [ ] No change to scoring, to the global exclusion, or to the four hardcoded `50` literals
- [ ] Committed, **not pushed**

## 7. Traps

1. **Do not `git push`.** WSL has no credentials.
2. **Commit email must be `276203779+UditBuilds@users.noreply.github.com`.**
3. **Line endings** — `.gitattributes` handles it. A diff of thousands of unchanged lines means stop and report.
4. **Scores drift as the database grows.** Known. This is why §4.1 recomputes the baseline.
5. **No `--commit`, no live writes.** The human runs every write himself.
6. **Do not tune the threshold to produce a good number.** Report 30/60/90 as measured. Picking the flattering one and presenting it as the default is the exact failure this repo documents.

## 8. Report format

1. Gate: SHA, test count
2. The §2 feasibility table and verdict — **then stop**
3. (after go) Where the exclusion was applied and why
4. Flag-off identity proof
5. Recomputed baseline vs. 2026-09-16
6. Before/after at each threshold, with the cost statement
7. Anything you wanted to change and didn't
8. Commit SHAs
