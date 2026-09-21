# Recency-based exclusion for rediscover — closed by measurement (§2)

**Brief:** `briefs/recency_exclusion.md`
**Base SHA:** `f0bc757`
**Status:** Closed at the §2 feasibility gate. No implementation followed — §3-§6 of the brief do not apply.

---

## 0. Gate

- Branch `main`, tree clean at start.
- Full suite: **517 passed, 0 failed, 0 skipped.**
- Starting SHA: `f0bc757` (already on `origin/main`).

## 1. Provenance

- `as_of` (UTC): `2026-09-13T07:24:35+00:00`
- `plays` row count: **40,619**
- Canonical (music-only) tracks in the current frame: **2,918**
- Method: a read-only script, run against the real database, that calls `taste_engine.dormancy.build_frames` (`dormancy.py:110-129`), `qualifying_clusters` (`dormancy.py:132-164`), `canonical_key_of` (`dormancy.py:45-65`), `plays_by_canonical_key` (`dormancy.py:68-81`), and `plays_in_window` (`dormancy.py:86-97`) directly — no recency logic was reimplemented. The script was kept in a scratch location, not added to `scripts/`, since the brief never reached a "go" for implementation and this measurement was never meant to be a permanent artifact.
- These figures are now reproducible via `scripts/recency_exclusion.py` (default `--as-of`: `MAX(watched_at)`).
- `half_life`: default (`config.RECENCY_HALF_LIFE_DAYS = 14`, unchanged — this brief touches no scoring).

## 2. Primary finding: the eligibility gate already is a recency filter

This is the reason for every number below, not a footnote to them.

`MIN_SCORE = 0.5` combined with `RECENCY_HALF_LIFE_DAYS = 14` means a single lone play decays below the eligibility floor in about **6.6 days** (derivation already published at `reports/dormancy_signals.md:188`: `log1p(1) = 0.693`, decaying at a 14-day half-life crosses 0.5 at ~6.6 days). A track needs either a play within roughly the last week, or several plays, to clear `score >= MIN_SCORE` at all.

That means the set this brief proposed to filter — "native-eligible, but not played recently" — is close to empty **by construction**, before any recency exclusion is even applied: clearing the existing eligibility gate already selects almost exclusively for tracks with a recent play. A downstream recency exclusion and the existing `MIN_SCORE` eligibility gate are measuring nearly the same quantity. Stacking them doesn't trim a still-in-rotation tail out of a larger eligible pool; it removes nearly the entire pool, because the pool was never anything but recency-selected to begin with.

Everything in §3-§5 is that mechanism showing up in the data.

## 3. §2 feasibility table

Qualifying clusters today: **10** (`native_eligible >= MIN_CLUSTER_NATIVE = 12`, post global-top-50 exclusion — the same FLOOR test `writer.plan()` applies for a `--cluster-name` write).

| cluster | name | cluster pool size | candidates today (score ≥ `MIN_SCORE`) | survivors @30d | survivors @60d | survivors @90d |
|---:|---|---:|---:|---:|---:|---:|
| 5 | Joji | 26 | 13 | 0 | 0 | 0 |
| 8 | Don Toliver | 71 | 21 | 0 | 0 | 0 |
| 12 | T-Series / Pritam / Sony Music India | 490 | 22 | 0 | 0 | 0 |
| 23 | The Weeknd | 75 | 22 | 0 | 0 | 0 |
| 24 | 21 Savage | 49 | 14 | 0 | 0 | 0 |
| 25 | Metro Boomin | 65 | 26 | 0 | 0 | 0 |
| 26 | Future | 84 | 23 | 1 | 0 | 0 |
| 32 | Travis Scott | 86 | 21 | 0 | 0 | 0 |
| 34 | Drake | 102 | 23 | 0 | 0 | 0 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 44 | 13 | 0 | 0 | 0 |

"Survivors" = candidates today with **zero** plays inside the trailing window (i.e. what would remain as a candidate if that window's exclusion were applied).

**Aggregate, by threshold:**

| threshold | clusters clearing `MIN_CLUSTER_NATIVE` (12) | total candidate pool across all 10 clusters |
|---|---:|---:|
| 30d | 0 of 10 | 1 |
| 60d | 0 of 10 | 0 |
| 90d | 0 of 10 | 0 |

No cluster clears the floor at 90d (the aggressive end). The floor is not the effective constraint here — the pool empties (1 track, then 0, then 0) well before the question of which clusters individually clear 12 members becomes the deciding factor. No adjustment to `MIN_CLUSTER_NATIVE` changes this outcome.

## 4. Cluster-count drift (noted as drift, not investigated)

`reports/dormancy_signals.md` (2026-09-16) recorded **10** qualifying clusters. Today's frame gives **8** — e.g. T-Series is cluster `12` at pool size 490 here, where it was recorded as cluster `11` on 2026-09-16. This is the same class of drift CLAUDE.md's open item 9 already documents (cluster ids and membership are not stable across reclustering/data growth). It was not traced to a specific cause, since it doesn't change the verdict: the result is 0 clusters clearing the floor at every threshold whether the denominator is 8 or 10.

## 5. Reconfirmation against the published freshness figure

Summing the table above: 198 candidates today across all 10 clusters, of which 1 was not played in the last 30 days — **197 of 198 (99.5%)** were played within the last 30 days. This agrees with reports/dormancy_signals.md, but it is not an independent confirmation: both reports now share one anchor and one 198-track pool, and their tables match cell for cell. Before the anchor fix they looked like two measurements on different days. They were the same measurement.

## 6. Verdict

**Not viable at any threshold (30d, 60d, or 90d).** This is the sixth direction closed by measurement. No implementation code was written; `writer.py`, `config.py`, `recommend.py`, `evaluate.py`, and every existing file under `reports/` other than this new one are untouched. No tests were added — none of §3's implementation is in scope for a killed brief. No live write ran; nothing was committed to YouTube.

## 7. Implication for future work (constraint only — no fix proposed or evaluated)

The freshness problem cannot be fixed by adding an exclusion downstream of the eligibility gate (`score >= MIN_SCORE`), because the candidate pool that gate produces is already recency-bound by construction, not incidentally recency-heavy. Any filter applied after eligibility is filtering a set that eligibility itself already narrowed to "recently played, or played often enough to still be near the top" — there is close to nothing else in that set for a downstream filter to find. A fix for this problem, if one exists, is not a filter that runs after `MIN_SCORE`; it is something that changes what makes a track eligible in the first place. This report does not evaluate what that would be.
