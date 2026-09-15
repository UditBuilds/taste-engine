# README staleness audit — after commit 58799f7

Scope: README.md only, checked against the current repo state (HEAD =
58799f7) and the four documents the brief named. Sources actually used below:
`reports/backfill_plan.md`, `reports/genre_coverage.md`,
`briefs/backfill_constraint.md`, `briefs/backfill_rank.md`, current
`src/taste_engine/config.py` and `src/taste_engine/writer.py`, and a live
`pytest --collect-only` run (2026-09-14) where no committed report carried a
test count. No commit, push, or API call was made. Verified via
`git status` after writing this file: the only untracked files in the
working tree are `briefs/readme_backfill.md` (pre-existing, the brief itself)
and this report — nothing else was created or modified.

---

## 1. Lines describing the OLD backfill mechanism

The old mechanism: backfill by nearest **embedding centroid** (whole
neighbouring cluster, not individual tracks), ranked by **score** within that
cluster, against a **fixed 45-track target** requested via `--limit`, with no
genre guard and no distance ceiling. Superseded by commits 41502c6 (floor +
computed length + genre guard) and 58799f7 (distance ranking + ceiling +
tie-break fix). Every line below still describes the retired mechanism.

- **Line 36** (Quickstart step 6):
  > `taste-engine write --cluster-name "..." --limit 45` — dry run; nothing is written without `--commit`.

  `--limit` is now ignored whenever a cluster is requested (`--cluster` or
  `--cluster-name`) — confirmed in `writer.py`'s `plan()` (the `limit`
  parameter is only consumed in the no-cluster branch, line 388) and in
  `render_plan()`, which prints `(--limit ignored: length is computed, not
  requested)` (writer.py:448) on exactly this code path. Length is now
  computed (LENGTH rule below), not requested.

- **Lines 770–771** (§8 command block):
  ```
  taste-engine write --cluster-name "Travis Scott" --limit 50     # dry run
  taste-engine write --cluster-name "Travis Scott" --limit 50 --commit
  ```
  Same defect as line 36.

- **Lines 807–818** (§8, "### Backfill", full opening paragraph):
  > The pool-depth problem above is really a floor problem: how much of a
  > cluster the model itself believes in. `config.MIN_SCORE` (0.5) makes that
  > explicit - candidates below it are not eligible, deep cluster or not. A
  > cluster that clears the floor on its own is unaffected; the output for a
  > deep cluster is identical to before this existed. A cluster that does not
  > backfills from its nearest neighbours by embedding centroid - cosine
  > distance in the same PCA-reduced space HDBSCAN actually clustered in,
  > nearest cluster first, ranked by score within each. If every cluster's
  > eligible material runs out before the playlist fills, the playlist comes
  > back short. It is never padded below the floor.

  Every mechanism claim here is superseded:
  - "A cluster that clears the floor on its own is unaffected; ... identical
    to before this existed" — no longer true in either sense of "floor." The
    current FLOOR (`MIN_CLUSTER_NATIVE = 12`, config.py:117) gates whether a
    playlist is generated **at all** — below it, `writer.plan()` raises
    `WriteBlocked` and nothing is produced (writer.py:376–382), which is a
    stronger outcome than "unaffected." And above it, there is no longer a
    concept of a cluster being "deep enough to need no backfill": target
    length is now `floor(native / (1 - MAX_BACKFILL_SHARE))`
    (`MAX_BACKFILL_SHARE = 0.25`, config.py:118) — a formula *derived from*
    the native count, always exceeding it, so backfill is structurally
    invited for every qualifying cluster, not reserved for clusters short of
    a fixed request size.
  - "backfills from its nearest neighbours by embedding centroid ... ranked
    by score within each" — RANK no longer ranks by score, and no longer
    operates on whole neighbouring clusters. Since 58799f7, candidates are
    ranked individually by cosine distance to the *requesting* cluster's own
    centroid, ascending, tie-broken (distance asc, score desc, video_id asc)
    (config.py:120–129; `briefs/backfill_rank.md` explicitly forbids
    restoring `_clusters_by_distance`, the nearest-whole-cluster approach).
  - No genre GUARD, no distance CEILING, and no mention of the two-stage
    floor are present anywhere in this paragraph. All are load-bearing in
    the current mechanism (config.py:96–158).

- **Line 820**: "Measured before writing anything (`scripts/backfill_report.py`, no API calls), at limit 45:" — `scripts/backfill_report.py` itself was updated in 41502c6 to call the current `writer.plan()` (no `limit` argument any more) and is not itself stale, but "at limit 45" describes a parameter that no longer exists in that call. Re-running this script today reproduces neither the number "45" nor the table that follows it.

- **Lines 822–826** (the table itself):
  ```
  | cluster | tracks | native (>= 0.5) | backfilled | final | source clusters |
  |---|---:|---:|---:|---:|---|
  | T-Series / Pritam / Sony Music India | 492 | 22 | 23 | 45 | Joji (13), Playboi Carti (8), Doja Cat (2) |
  | Travis Scott | 84 | 21 | 24 | 45 | Kendrick Lamar (5), Drake (6), Post Malone (5), Justin Bieber (3), Young Thug (2), Radiohead/NBSPLV/softsync (2), Kanye West (1) |
  ```
  Every column except `tracks` (total cluster size) is now wrong — see list 2.

- **Lines 828–831**:
  > Both filled to the requested 45 - the global pool (276 eligible tracks
  > across 32 clusters, after the rediscovery favourites exclusion) had
  > headroom for these two. That will not hold for every cluster; a thinner
  > neighbourhood returns fewer tracks rather than padding, per the
  > measurement above.

  "Filled to the requested 45" is false for both example clusters under the
  current mechanism (see list 2), and "the requested 45" itself is the
  retired fixed-target model — there is no longer a single requested number
  shared across clusters.

- **Lines 833–847** (the "musically sensible" discussion): this is not just
  numerically stale — its **conclusion is reversed**. The paragraph's thesis
  is that the system knowingly ships a genre-incoherent T-Series fill (Joji,
  Playboi Carti, Doja Cat) and reports that honestly rather than tuning it
  away: "That is not a bug to tune away ... adjusting it to hide the
  T-Series mismatch would trade an honest problem for a harder-to-see one."
  That output no longer exists. Under the current mechanism T-Series
  backfills **zero** tracks — the GUARD finds exactly one genre-matching
  candidate (Doja Cat) and the CEILING refuses it at distance 1.1166 (list
  2). The thing the README says was accepted as an honest tradeoff was
  subsequently mitigated by a mechanism change (GUARD + CEILING, briefs
  `backfill_constraint.md` / `backfill_rank.md`). The observable symptom
  changed from *incoherent fill* to *short playlist* (22 of a 29 target).
  "'Nearest cluster' can only be as meaningful as the clustering it is
  measured in" is also no longer accurate as a mechanism description —
  nearest is no longer a cluster-level concept at all; ranking is per-track
  distance to the requesting cluster's centroid (see line 813–818 note
  above). A rewrite cannot fix this paragraph by refreshing its numbers —
  the conclusion it argues for needs to change.

- **Lines 849–857** (the invariance-check paragraph, "The eval does not move,
  and cannot..."): this documents an invariance check that was real when
  written — but it was run once, for the nearest-centroid mechanism
  (commit 55615fc), by stashing that code and re-running the eval. That code
  path has since been deleted outright (`briefs/backfill_constraint.md`:
  "Remove the old nearest-centroid backfill path. Do not leave both behind a
  flag."). Both replacement briefs required the identical check be re-run
  against the new code (`briefs/backfill_constraint.md` "Invariance check
  (required)"; `briefs/backfill_rank.md` "Invariance check") — see the
  "nDCG invariance result" entry in the assembled facts below: no committed
  report or test records that it was. This paragraph, read today, credits a
  check to code that no longer exists, and **cannot be carried into a
  rewrite in any form** — not refreshed numbers, not a caveat — until the
  check is actually re-run and its result recorded. Per CLAUDE.md's own
  rule ("no status line changes on the strength of a plan or a passing test
  suite alone"), this is a gate with no recorded result, not a data gap that
  can be footnoted around.

---

## 2. Numbers changed or invalidated

| line(s) | stated value | current value | source |
|---|---|---|---|
| 36, 770–771 | `--limit 45` / `--limit 50` sets the playlist length | ignored on any cluster-scoped write; length is computed | `writer.py:388,448` |
| 694 | "53 tests" (`tests/test_writer.py`) | **72 tests** | measured: `pytest --collect-only tests/test_writer.py`, 2026-09-14 |
| 825, "native" | T-Series 22 | 22 (unchanged) | `reports/backfill_plan.md`, per-cluster plan table |
| 825, "backfilled" | T-Series 23 | **0** | `reports/backfill_plan.md`, per-cluster plan table |
| 825, "final" | T-Series 45 | **22** (target 29, short by 7) | `reports/backfill_plan.md`, per-cluster plan table |
| 825, "source clusters" | Joji (13), Playboi Carti (8), Doja Cat (2) | **none admitted.** T-Series's only genre-matching candidate — Doja Cat, "Streets (Official Video)" — sits at distance 1.1166, outside `MAX_BACKFILL_DISTANCE = 1.0`; without the ceiling the guard alone would have admitted it, reaching 23 | `reports/backfill_plan.md`, "Distance ranking" section |
| 825, "tracks" | T-Series 492 | **492 (still current)** — not invalidated | `reports/genre_coverage.md`, "Correctness gates": "matches `scripts/backfill_report.py`'s measured 492, time-invariant: OK" |
| 826, "native" | Travis Scott 21 | **20** (1-day score decay, expected) | `reports/genre_coverage.md`, "Correctness gates" |
| 826, "backfilled" | Travis Scott 24 | **6** | `reports/backfill_plan.md`, per-cluster plan table |
| 826, "final" | Travis Scott 45 | **26** (equals its own new target — not short) | `reports/backfill_plan.md`, per-cluster plan table |
| 826, "source clusters" | 7-cluster breakdown (Kendrick, Drake, Post Malone, Justin Bieber, Young Thug, Radiohead/NBSPLV/softsync, Kanye West) | current report gives per-track distances, not cluster-name/count pairs. Travis Scott's 6 current backfill tracks are all admitted by genre `hip hop`, distances 0.2776–0.3503 — no longer a like-for-like table | `reports/backfill_plan.md`, "Backfill provenance" section |
| 826, "tracks" | Travis Scott 84 | **84 (still current)** — not invalidated | `reports/genre_coverage.md`, "Correctness gates" |
| 828–829 | "global pool (276 eligible tracks across 32 clusters)" | split: **32 is confirmable today** — `reports/genre_coverage.md`'s Number 2 table lists 37 real clusters under the favourites-included pool, 5 with 0 eligible members (Arjan Dhillon/APDHILLON/Prem Dhillon, both "Technical Guitarist Official" clusters, TL-Jhondi Gemar/Moviechat/$uicideboy$, Offset/Future/Quality Control) → 32 with ≥1. **276 is not traceable** — not restated as a sum in either current report, and not re-derived here per the anti-assumption rule. Worth flagging directionally rather than assuming it still holds: `reports/backfill_plan.md`'s floor table shows the favourites-excluded pool losing tracks relative to favourites-included for just 8 of the 32 non-zero clusters (a combined loss of 29 across those 8 alone) — so 276 has a real chance of having drifted, in an unknown direction, not just a chance of being unmeasured | `reports/genre_coverage.md`, Number 2 table; `reports/backfill_plan.md`, "Which pool clears the floor" table |
| 882 | "tests/               301 tests" | **320 tests** | measured: `pytest --collect-only`, 2026-09-14 |
| 904 | "python -m pytest -q  # 301 tests" | **320 tests** | measured: `pytest --collect-only`, 2026-09-14 |

Not invalidated, noted only to pre-empt confusion: line 744's "289 tests
passed" is a historical statement about the suite size at the moment of the
2026-09-13 live-write 409 (§8, "The first live write"). It describes the
past correctly; this work did not touch it and it should not be "corrected"
to 320.

---

## 3. True but now incomplete

- **Lines 784–805** ("### The two write modes" / "**What rediscover mode
  needs:**"): still accurate about *why* rediscover mode needs pool depth.
  It does not mention that the current code can refuse to generate a
  playlist outright (FLOOR) rather than degrade into fan re-uploads, or that
  length is computed rather than requested via `--limit`. The section
  immediately after it (Backfill) is where that gap should be closed, and
  currently is not (list 1).
- **Lines 799–800**: "23 of 50 tracks below score 0.5 for the small cluster,
  against 5 of 50 for the large one" measures raw top-N-by-score padding
  from *before* `MIN_SCORE` was enforced at all (i.e. pre-55615fc, not just
  pre-41502c6/58799f7). The current code cannot reproduce this measurement
  under any configuration — a track below `MIN_SCORE` has been categorically
  ineligible since the floor was introduced. Same category as line 744's
  "289 tests": accurate as history, not as a description of current
  behaviour. Unlike that line, the surrounding prose ("fills the rest with
  fan re-uploads, extended cuts and remixes") reads as a description of what
  the tool still does, not of a fixed problem — a rewrite should mark it
  historical explicitly, not just refresh the two numbers.
- **Line 712** (§8, quota arithmetic): "`50-track playlist  =  50 + 50x50 + 1
  =  2,551 units, at minimum`". The formula is still correct, but the
  *instance* is now unreachable through `--cluster-name`: no qualifying
  cluster's computed length reaches 50. The largest is Metro Boomin at 34
  (native 26, `floor(26 / (1 - 0.25)) = 34`) —
  `reports/backfill_plan.md`, per-cluster plan table. This sits directly
  above the `--cluster-name "Travis Scott" --limit 50` command block already
  flagged in list 1 (lines 770–771); the two together imply a playlist
  length nothing in the current cluster-write path can produce.
- **Line 879** (§9 Layout, `writer.py` entry): "writer.py          Phase 4 —
  quota-aware, resumable, self-verifying write" does not mention backfill,
  the floor, or the guard at all — unlike CLAUDE.md's own repo-shape entry
  for the same file, which does (and which is itself now stale — see list
  4).
- **Lines 692–703** (§8 status block): scoped to write-back correctness, not
  backfill, so it isn't wrong on its own terms — but its "53 tests" figure
  (list 2) means a reader relying on this block for "what does the test
  suite cover" undercounts `tests/test_writer.py` by 19 tests before even
  reaching the Backfill section.
- **Lines 849–857**: see list 1's last entry — true as history, silent about
  the fact that the code it verified was later deleted and the check was not
  documented as re-run.

---

## 4. CLAUDE.md contradictions with README (after the SUPERSEDED row)

- CLAUDE.md's decisions table carries the row:
  > **SUPERSEDED 2026-09-14** — shallow-cluster backfill by nearest
  > **embedding centroid**, `MIN_SCORE = 0.5` floor | ... Replaced by
  > depth-based length (`MIN_CLUSTER_NATIVE`/`MAX_BACKFILL_SHARE`) plus a
  > genre guard on each backfill candidate — briefs/backfill_constraint.md.

  README §8's "Backfill" section (lines 807–847) still presents exactly the
  mechanism this row marks retired, as the current shipped behaviour, with
  no mention of the replacement. This is the direct contradiction.

- CLAUDE.md was updated by commit 41502c6 (which added the SUPERSEDED row)
  but **not touched at all** by 58799f7. So CLAUDE.md itself — independent
  of README — does not mention RANK (distance-to-requesting-cluster
  ranking), CEILING (`MAX_BACKFILL_DISTANCE`), or the genre tie-break fix.
  Its "State" bullet ("Backfill shipped (2026-09-13), not yet exercised
  live...") and "Known open items" #5 both still narrate the nearest-centroid
  mechanism in present/recent-past tense, immediately below the row that
  retires it, in the same file. Not a README contradiction per se, but
  relevant: a rewrite sourcing "what CLAUDE.md says is current" for backfill
  will find CLAUDE.md itself only half-updated.

- CLAUDE.md's Commands section entry
  (`scripts/run.sh scripts/backfill_report.py "T-Series" "Travis Scott"`) is
  accurate — that script was updated in 41502c6 to the current mechanism
  (list 1, line 820 note) — but CLAUDE.md never mentions
  `scripts/backfill_plan.py`, the script that actually produced every
  current number in this audit.

- CLAUDE.md's "State" section states "307 tests pass" (written at 41502c6
  time). This is also now stale — current is 320 (list 2) — for the same
  reason as README's two counts: neither document was updated when 58799f7
  added the `TestBackfillDistanceRanking`, `TestModalGenreTieBreak`, and
  `TestLengthFormula` classes.

---

## Also assemble — verified current numbers a rewrite would need

- **Clusters clearing the floor** (`MIN_CLUSTER_NATIVE = 12`): **10 of 37**,
  identical under both the favourites-included and favourites-excluded
  pools. — `reports/backfill_plan.md`, "Which pool clears the floor."
- **Total real (non-noise) clusters**: **37**. — `reports/genre_coverage.md`
  ("37 real (non-noise) clusters total") and `reports/backfill_plan.md`
  ("10 of 37").
- **Distinct backfill tracks** (current: distance-ranked, ceiling applied,
  post tie-break-fix): **45**, confirmed stable across 10/10 separate
  process runs. — `reports/backfill_plan.md`, "Distance ranking" and "Genre
  tie-break" sections.
- **Total backfill slots filled**: **51** (largest single playlist: 8). —
  `reports/backfill_plan.md`, "Distance ranking" section.
- **T-Series's outcome and distance**: **0** backfill tracks admitted; final
  playlist **22** tracks against a target of **29** (short by 7). Its one
  genre-matching candidate — Doja Cat, "Streets (Official Video)" — sits at
  distance **1.1166**, outside `MAX_BACKFILL_DISTANCE = 1.0`; the ceiling,
  not the genre guard, is what excludes it (the guard alone would have
  admitted it, reaching 23). — `reports/backfill_plan.md`, per-cluster plan
  table and "Distance ranking" section.
- **The tie vote counts**: Metro Boomin — `hip hop` vs `pop`, **26–26** (of
  26 labeled native members, every one carrying both labels); T-Series —
  `music of asia` vs `pop`, **21–21** (of 22 labeled native members). —
  `reports/backfill_plan.md`, "Genre tie-break" section.
- **Test count**: **320** tests collected in the full suite; **72** of them
  in `tests/test_writer.py`. — measured directly (`pytest --collect-only`,
  and the same with `tests/test_writer.py` alone), run 2026-09-14 during
  this audit; not stated in either committed report.
- **nDCG invariance result for the current mechanism**: **not traceable —
  and not a data gap, a gate with no recorded result.** Both
  `briefs/backfill_constraint.md` ("Invariance check (required) ... nDCG@20
  must be BYTE-IDENTICAL") and `briefs/backfill_rank.md` ("Invariance check
  ... BYTE-IDENTICAL to the saved baseline") make this check a required step
  of shipping the change, not optional follow-up. `reports/backfill_plan.md`
  contains no occurrence of "ndcg," "invariance," or "byte-identical"
  anywhere, and neither commit message (41502c6, 58799f7) records a result.
  The only byte-identical-nDCG result that *is* traceable belongs to the
  now-deleted nearest-centroid mechanism (commit 55615fc) — the claim
  currently sitting at README lines 849–857, which verified code that no
  longer exists (list 1, list 3). Per CLAUDE.md's own rule, no status line
  should change on the strength of a plan or passing tests alone; the same
  applies here in reverse — nothing about the invariance claim at 849–857
  should carry forward, refreshed or caveated, until the check is actually
  re-run against the current code and a result is recorded.
