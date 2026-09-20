# Gate-drift audit

Executed against `briefs/gate_drift_audit.md`, read-only, starting at `2ca8d13`
(HEAD at session start; also `origin/main` — see Part 3). Recomputed nothing;
every multiplier below is arithmetic on dates already recorded somewhere in
the repo. Every claim is labelled **executed** (I ran `git`/`grep`/a standalone
calculator, not a project measurement script), **source-read** (read directly
from a file), or **inferred** (a judgement call, flagged as such). No report,
README, or CLAUDE.md content was edited. No file under `briefs/` was touched.

## Methodology note — read before the table

**A figure's class is determined by the code that produced it, not by the
code at HEAD.** `dormancy_signals.py` and `dormancy_probe.py` were both fixed
today, in this session's own recent history (`9791196` at 10:21:46,
`cd1b28d` at 10:45:25) — at HEAD, both default to `MAX(watched_at)`. But
every currently-*published* figure from either script was computed **before**
its fix, under the old wall-clock default, because neither script has been
re-run since. Classifying by today's code would call these figures immune;
they are not. Every row below states the code state at the figure's own
computed date, separately from whether the script is immune today.

One arithmetic label needs defining: **"derived"** = a gap-days/multiplier
computed by me from two dates that are each independently source-read (the
`MAX(watched_at)` anchor, and a report's own recorded `as_of`). This is
distinct from "source-read" (the number came out of a file verbatim) and
from a qualitative "inferred" judgement call. It is the operation the brief's
hard rules explicitly permit ("deriving a multiplier arithmetically from
recorded dates is allowed").

**The method reproduces an independent measurement, checked before relying
on it anywhere below (executed, standalone calculator, no project code
run):** `reports/asof_core.md` measured a uniform **1.42430×**/**1.42431×**
on a live dry-run diff. Solving `multiplier = 2^(gap_days / 14)` backwards
for that value gives `gap_days = 14 · log2(1.4243) = 7.1435`, which lands
anchor (`2026-09-13T07:24:35`) + 7.1435 days = **2026-09-20T10:51:17** —
squarely between `cd1b28d`'s commit (10:45:25) and `2ca8d13`'s (10:54:38),
the two commits that produced and then documented that exact dry run. The
arithmetic is not merely plausible; it reproduces a real, already-measured
figure to within minutes, using only the recorded anchor and the half-life.
Every multiplier below uses the identical formula.

**A second correction, made before this table was final rather than after:**
grepping for wall-clock literals (0a) is necessary but not sufficient to
find every affected path. `dormancy.canonical_key_of` and several report
scripts (below) call `score.scored_tracks(conn)` with **no** `as_of` and
**no** `start`/`end` — a call that reaches `score.py:61` exactly as directly
as a literal `datetime.now()` would, but greps for datetime patterns cannot
see it, because the wall-clock read is one function call away, inside
`score.py`, not in the calling file at all. Confirmed by a further sweep
(executed: `grep -rn "scored_tracks(" src/ scripts/`, then checking every
call site for a passed `as_of`/`end`) rather than trusting the absence of a
literal-pattern hit as proof of immunity — the mistake an earlier draft of
this report made for rows 12–13 before this pass.

**Scope control for Part 1 (stated once, not per row).** "Every quantitative
claim in every report" is unbounded taken completely literally — this repo
has ~30 report files, an 1,117-line README and 17 briefs. Following Part 0c's
own instruction to bound the inventory by the blast radius established in
Part 0: figures on a path that touches `recommend.build()` / `score.py`'s
wall-clock choke point get a full row each. Files whose producing path never
reaches that choke point (clustering/embedding ARI, canonicalisation,
Last.fm coverage, NaN-guard and hash-seed-tie-break audits, quota-unit
arithmetic, contamination counts) get **one row citing the immunity
evidence**, not a row per number in them — transcribing every ARI value
under every noise convention would not change any drift finding.

---

## Part 0 — Blast radius

### 0a. Wall-clock read sites (executed: grep)

The brief's four patterns first, then a broadened sweep — **the brief's own
pattern list is insufficient**, confirmed independently: `dormancy_signals.py`
and `dormancy_distribution.py`'s actual wall-clock reads are
`pd.Timestamp.now(tz=...)`, which none of `datetime.now`, `datetime.utcnow`,
`date.today`, `time.time` would match. `reports/deferred_constants.md`'s own
C4 audit found this already; I re-ran the broadened grep myself rather than
inheriting that finding, and it reproduces exactly the same three additional
hits, no more, no fewer.

| file:line | reads | reaches a score / eligibility gate / dormancy band? |
|---|---|---|
| `src/taste_engine/score.py:61` (`_as_datetime(None)`) | `datetime.now(timezone.utc)` | **Yes — the sole choke point.** Every `as_of`-less call to `add_scores` funnels through this line. |
| `src/taste_engine/lastfm.py:367` | `datetime.now(timezone.utc)` | No — Last.fm lookup-cache `fetched_at` provenance timestamp |
| `src/taste_engine/resolve.py:135,144` | `datetime.now(timezone.utc)` | No — `videos.list` cache-row provenance timestamp |
| `src/taste_engine/quota.py:79,122,138` | `datetime.now(PACIFIC)` / `datetime.now(timezone.utc)` | No — quota-ledger day key and log timestamp; tracks real elapsed days against Google's own reset, by design |
| `src/taste_engine/writer.py:55` | `datetime.now(timezone.utc)` | No — `written_playlists` write-attempt provenance timestamp |
| `scripts/min_samples_sweep.py:181,238,278,280` | `time.time()` | No — wall-clock *duration* timing for a progress log, not calendar time |
| `scripts/dormancy_signals.py:252` | `pd.Timestamp.now(tz='UTC')` | No — "Report generated (UTC)" provenance line, printed alongside but distinct from the `as_of` value the report actually computes with |
| `scripts/dormancy_probe.py:338` | `pd.Timestamp.now(tz='UTC')` | No — same as above, same script family |
| **`scripts/dormancy_distribution.py:489`** | `pd.Timestamp.now(tz="UTC")`, CLI's `else` branch | **Latently yes.** Currently unexercised — the one committed report from this script was run with an explicit `--as-of` — but the CLI's own default, if invoked bare, is unconditional wall-clock, unchanged as of this session. |

`grep`'d for SQL-level reads too (`CURRENT_TIMESTAMP`, `datetime('now')`):
zero hits. Every timestamp in this codebase is Python-side.

### 0b. The four "prior work" claims, verified independently

**Claim: "`score.py:61` was the sole choke point via `recommend.build()`."**
**Holds.** Source-read `score.py` and `recommend.py` directly: `_as_datetime`
(`score.py:59-65`) is the only function in the module that reads wall-clock,
`add_scores` (`:81-104`) is its only caller with a bare `as_of=None` default,
and `recommend.build()` (`recommend.py:151-169`, pre-`cd1b28d`) called
`scored_tracks(conn, half_life=half_life)` with no `as_of` and no
`start`/`end` — so `scored_tracks:154`'s `as_of if as_of is not None else end`
resolved to `None` either way. Every caller of `build()` — `writer.plan()`,
`cli.cmd_clusters`, `recommend.main()`, `backfill_plan.py`,
`compare_backfill_ranking.py`, and `genre_coverage.py` — inherited wall-clock
with no override, until `cd1b28d` today.

**Claim: "`dormancy.py` and `evaluate.py` thread `as_of` explicitly."**
**Holds for the paths actually exercised; does not hold as a blanket
statement about either module.** Two counter-examples found by source-reading
both files in full, not by inheriting the claim:

- `dormancy.canonical_key_of` (`dormancy.py:45-65`) calls
  `scored_tracks(conn, canonical=False, music_only=True)` with **no `as_of`,
  no `start`/`end`** — this does reach `_as_datetime(None)`, i.e. wall-clock.
  Verified inert, not assumed inert: the function's own return value only
  ever reads `work["title"]`, `channels`, and `work["duration"]` off the
  `scored_tracks` result to build a canonical-key string; the `score`,
  `days_since` and `recency_weight` columns that wall-clock actually touches
  are computed and then never referenced. `dormancy_signals.py` and
  `dormancy_probe.py` both call this function to build their `key_of` mapping
  — a text/duration match, unaffected by which `as_of` produced the discarded
  score column.
- `evaluate.split_frames`'s **test** side (`evaluate.py:93-96`) passes
  `as_of=None` and relies on `end=_window_end(split_date, test_days,
  test_end)` to stand in for it (`scored_tracks:154`). `_window_end`
  (`:49-58`) returns `None` when *both* `test_days` and `test_end` are falsy
  — reachable from bare `python -m taste_engine.evaluate` (no flags), where
  `argparse` leaves both `None`. Traced every caller that could hit this:
  `canonical_impact.py` always passes `test_days=config.EVAL_TEST_DAYS`
  explicitly (`:92,109`); `nested_rediscovery` defaults its own `test_days`
  parameter to `config.EVAL_TEST_DAYS` internally when not given
  (`evaluate.py:420`) rather than leaving it `None`; README's own Quickstart
  and §10 command blocks always supply `--test-end`. No currently-published
  figure takes the bare path — same shape as the `dormancy.py` gap above:
  mechanism real, consequence inert, verified by tracing every caller rather
  than assumed.

**Claim: "`dormancy_signals.py` ... reads wall-clock at the caller."**
**Does not hold at HEAD. Held for the entire period that produced the
published report.** `build_report`'s `as_of is None` branch read
`pd.Timestamp.now(tz="UTC")` from the script's creation (`bcc2eaa`,
2026-09-16T04:14:52) until `9791196` today (2026-09-20T10:21:46), which
changed the default to `_last_play_at(conn)` (`MAX(watched_at)`). The
committed `reports/dormancy_signals.md` was generated once, at
2026-09-16T04:18:39 (its own line 7), inside that wall-clock window, and has
never been regenerated since the fix.

**Claim: "`dormancy_probe.py` ... reads wall-clock at the caller."**
**Does not hold at HEAD. Held for the entire period that produced the
published report — a longer window than the previous claim, and with no
escape hatch at all until today.** `build_report`'s default
(`as_of = pd.Timestamp.now(tz="UTC")`, unconditional, no parameter to
override it) was unchanged from the script's creation (`68bf839`,
2026-09-16T04:50:20) until `cd1b28d` today (2026-09-20T10:45:25) added both
an `as_of` parameter and a `--as-of` CLI flag, defaulting to
`last_played_at(conn)`. The committed `reports/dormancy_probe.md` was
generated once, at 2026-09-16T04:42:49 (its own line 7), and has never been
regenerated.

### 0c. Blast radius statement

**Affected (figures computed while the producing path read wall-clock with
no override, or still can):**

- `reports/dormancy_signals.md` (whole file — wall-clock 2026-09-16T04:18)
- `reports/dormancy_probe.md`'s per-cluster/per-track tables and eligible
  counts (wall-clock 2026-09-16T04:42) — **not** its two lifetime-fact
  figures (362-day span, 61.8% single-play), see Part 1
- `reports/listening_test.md` and `reports/recency_exclusion.md` — both
  *cite* `dormancy_signals.md`'s figure rather than compute their own, except
  `recency_exclusion.md`'s own §2/§3/§5 tables, which it computed itself, at
  its own wall-clock `as_of` (2026-09-20T06:27:25)
- `reports/backfill_plan.md` — via `recommend.build()`, pre-`cd1b28d`
- `reports/genre_coverage.md` — via `recommend.build()`, pre-`cd1b28d`; the
  report's own prose (line 28, 30) already names the mechanism ("score is
  computed as_of=now() and decays continuously")
- the live `--commit` write path (`writer.plan()`), pre-`cd1b28d` — not a
  report, the highest-stakes caller; already covered by `reports/asof_core.md`
- `scripts/dormancy_distribution.py`'s CLI default — latent, unexercised in
  the one committed report

**Two different kinds of "unaffected," not one — collapsing them was this
report's own first-draft mistake, caught before finalising (see the
methodology note's second correction).** IMMUNE BY PATH means the producing
code never executes `score.py:61` at all. ANCHOR-INDEPENDENT means it does,
but the specific published figure never reads the column that call produced.
Executed `grep -rn "scored_tracks(" src/ scripts/` and checked every call
site for a passed `as_of`/`end` before assigning either label to anything
below — absence of a wall-clock *literal* in 0a's grep is not evidence of
either, since `dormancy.canonical_key_of` (0b) proved a file can call
anchor-less `scored_tracks(conn)` with zero literal hits of its own.

**Genuinely IMMUNE BY PATH** (the call graph never reaches `score.py:61`):

- `src/taste_engine/evaluate.py`'s rediscovery path (`split_frames` →
  `rediscovery_split` → `evaluate_rediscovery` → `nested_rediscovery`), and
  therefore `scripts/nested_eval.py` and the published headline — both
  `train` and `test` get an explicit, non-`None` anchor on every path any
  committed figure actually takes (0b, above); `recommend.build()` is never
  called on this path at all (`cluster="cluster_diverse" in names` is
  `False` for `nested_rediscovery`'s hardcoded `strategies=["most_played",
  "score"]`, so `cluster_tracks` never runs).
- `scripts/verify_write_plan.py:53` — extracts only the `play_count` column
  (itself a plain `COUNT(*)`, never `as_of`-dependent) off `scored_tracks`'s
  result; the score/`days_since` columns are never even sliced out.

**ANCHOR-INDEPENDENT** (the path calls anchor-less `scored_tracks(conn)`,
reaching `score.py:61`, but the specific figures published never read the
`score`/`days_since`/`recency_weight` columns that call produces):

- Everything downstream of `embed.cluster_tracks` — HDBSCAN clusters on
  MiniLM embeddings of title+artist/genre text; `score` is carried in the
  frame but never enters the clustering call. Verified per call site, not
  assumed as a family: `embed.py:329`, `cluster_eval.py:150,348`,
  `scripts/cluster_sweep.py:21`, `scripts/embedding_modes_pool480.py:57`,
  `scripts/noise_convention_report.py:33`, `scripts/ground_truth_before_after.py:104`
  all call bare `scored_tracks(conn)` and pass the result straight to
  clustering or to an id-keyed ground-truth join — never to a score-sorted
  operation. Covers `reports/embedding_modes_pool480.md`,
  `embedding_modes_remeasured.md`, `ground_truth_ids.md`,
  `ground_truth_audit.md`, `min_samples_sweep.md`, `normalise_title_fix.md`,
  `nan_guard_fix.md`, and README's embedding-mode table (row 12).
- Canonicalisation/classification/coverage scripts that also call bare
  `scored_tracks(conn)` for the same reason `dormancy.canonical_key_of`
  does — to get title/channel/duration/category rows, not a score:
  `scripts/canonical_report.py:11`, `duration_merge_report.py:19`,
  `pipe_merge_report.py:48`, `ground_truth_audit.py:52,75`,
  `contamination.py:55`, `genre_coverage.py:80` (the *coverage* half of that
  file — distinct from its `build_frame`/`recommend.build()` half, row 8),
  `scripts/canonical_impact.py:31` (its *other* `scored_tracks` call, at
  line 52, passes `as_of=split` explicitly and is separately immune),
  `lastfm.py:384`. Covers `reports/lastfm_coverage.md`, `defect_audit.md`,
  and README §1.3–§1.6, §5 (duplicate collapse, contamination, duration
  merges, classification).
- `scripts/strict_impact.py:38,40` and `scripts/verify_strict_null.py:45,47`
  — both call bare `scored_tracks(conn)` twice (`STRICT_MUSIC` off/on) to
  compute **set differences and sums** ("202 songs removed", "220 plays",
  "mean 1.1 plays each", "pool shrinks −123/−136/−163") — count/sum
  operations, score discarded. `verify_strict_null.py`'s one rank-dependent
  figure ("best rank a removed song reaches: 209 of ~2,000+", README §1.5)
  does **not** come from these two calls at all — it comes from that same
  script's separate `rediscovery_split(...)` calls (lines 69,95,101), which
  route through `evaluate.split_frames`'s explicit `as_of=split_date` — so
  that specific figure is IMMUNE BY PATH, not merely anchor-independent, and
  by a different, cleaner mechanism than the rest of the file.
- `reports/eval_verification.md`'s `in_playlist`/`in_library` leak findings
  and `reports/readme_audit.md` — neither calls `scored_tracks` at all
  (confirmed: no hit for either file's producing script in the
  `scored_tracks(` sweep above).
- README §4, §7 (quota arithmetic), §9 — no scoring involved at any point.

---

## Part 1–3 — the figure table

PUBLIC/LOCAL is determined once, not per row (Part 3): **`origin/main` (local
remote-tracking ref, unfetched — executed `git rev-parse origin/main`, not
`git fetch`) equals `HEAD` exactly, both `2ca8d13`.** Every commit in this
repository's history is therefore an ancestor of `origin/main` and every
committed figure below is **PUBLIC**. This updates, rather than contradicts,
the repeated "nothing pushed" statements in today's own commit messages —
those were true when written; something has been pushed since (this
environment cannot push its own commits — CLAUDE.md Trap 4 — so this was
necessarily done from outside this session). The only **LOCAL** items are
this brief itself (`briefs/gate_drift_audit.md`, untracked — never
committed, so more local than "committed but unpushed") and this report
before its own commit lands.

| # | figure | file:line | producing script | computed date (code state) | class | multiplier / reason | exposure |
|---|---|---|---|---|---|---|---|
| 1 | headline: score nDCG@20 **0.3312** vs baseline **0.1382**, **+139.7%**, **3/3**, **p=0.125** | `README.md:9-14,333,341-342`; `CLAUDE.md:14-15`; `reports/rediscovery_headline.md` (whole file) | `scripts/nested_eval.py` → `evaluate.nested_rediscovery` | 2026-09-19 (commit `3873188`; file last revised `21ba400`, prose-only) | **IMMUNE BY PATH** | n/a — see 0c. Immune to *anchor* drift specifically; not a claim of general reproducibility — `rediscovery_headline.md`'s own Finding 2 documents a live (unrelated) temporal leak in test-side `in_playlist` that this brief does not re-litigate (explicitly out of scope: CLAUDE.md item 12) | PUBLIC |
| 2 | **177 of 180 (98.3%)** shipped tracks played in last 30 days | `reports/dormancy_signals.md:188` | `scripts/dormancy_signals.py` | 2026-09-16T04:18:39, **wall-clock** (pre-`9791196` code) | ANCHOR-DEPENDENT, downstream (threshold-crossing count, not a raw score) | gap = 2.8709 d, illustrative score-multiplier 1.15274× (derived) — but the actual corrected count is not a simple rescale of 177/180 (trap 2). See row 3 for the value that already exists. | PUBLIC |
| 3 | correction: **197 of 198 (99.5%)** | `reports/deferred_constants.md:249-251` (scratch-path re-run, never written to `dormancy_signals.md` itself) | `scripts/dormancy_signals.py` (post-fix), run to a scratch path | 2026-09-20, **`MAX(watched_at)` = the current anchor** (post-`9791196` code) | ANCHOR-DEPENDENT, FACTOR DERIVABLE | gap = 0, multiplier = 1.0× (this run *is* the current anchor) — already measured by the brief that fixed the code; not re-derived here, only cited | PUBLIC |
| 4 | derivative citations of row 2: "177 of 180 (98.3%)" | `reports/listening_test.md:63`; `briefs/recency_exclusion.md:12,57` (historical); `briefs/reproducibility_and_distribution.md:86` (historical) | none — quotes row 2, computes nothing | file written 2026-09-19/2026-09-20 respectively; quoted figure's own computed date is 2026-09-16T04:18 | same as row 2 (derivative) | same as row 2 | PUBLIC |
| 5 | **137 of 139 (98.6%)** played in last 30 days; **0 of 8** clusters clear `MIN_CLUSTER_NATIVE=12` at 30d/60d/90d; survivors **2 / 0 / 0** | `reports/recency_exclusion.md:37-56,66` | ad hoc scratch script (not in `scripts/`), calling `dormancy.build_frames` directly, per the report's own Method section | 2026-09-20T06:27:25.203526, **wall-clock** (explicit in report) | ANCHOR-DEPENDENT, downstream | gap = 6.9603 d, illustrative per-track score-multiplier 1.41144× (derived). Direction for "candidates today" is not just monotonic reasoning here — it is measured twice, by two independently-committed reports on the same day (see note directly below the table). Magnitude of the *survivor* and *clears-the-floor* counts specifically is not re-derivable without re-measuring — trap 2. | PUBLIC |
| 5a | cross-validation for row 5's "candidates today" column, two of eight clusters | `reports/recency_exclusion.md:40,45` (candidates today: T-Series 13, Travis Scott 16) vs. `reports/asof_core.md`'s dry-run table (before/after counts: Travis Scott 16→21, T-Series 13→22) | same two figures, two different, independently-committed reports | both 2026-09-20, within the same wall-clock window | ANCHOR-DEPENDENT, FACTOR DERIVABLE — **measured, not just reasoned** | `recency_exclusion.md`'s wall-clock candidate counts for these two specific clusters are *exactly* `asof_core.md`'s "before" counts, and `asof_core.md` independently supplies the "after" (dataset-anchor) counts for the same two clusters: 21 and 22. This is the one place in this audit where the corrected magnitude for a specific figure is known, not merely bounded by direction — measured twice, on the same day, by two different report-generation runs that never referenced each other. Scoped to exactly these 2 of `recency_exclusion.md`'s 8 rows; the other 6 have no such pairing. | PUBLIC |
| 6 | **198 eligible tracks**; **21 of 198** pooled in the 21–35 day band; largest single-cluster band = **7** (T-Series), bar = **20** | `reports/dormancy_distribution.md:26-39,459` | `scripts/dormancy_distribution.py --as-of 2026-09-13T07:24:35` | 2026-09-20 (commits `056ea09`,`6dd678a`), **`MAX(watched_at)` exactly** | ANCHOR-DEPENDENT, FACTOR DERIVABLE | gap = 0 d, multiplier = 1.0×. **Not drifted.** This is the one report in the family generated with the correct anchor passed explicitly; the brief's own framing (bullet 3 of "figures known to exist") groups it with the drifting ones by proximity, but it is the control case, not an instance. | PUBLIC |
| 7 | **10 qualifying clusters**; quota **9,760** units native-only, **12,310** with backfill; and the two README worked examples built directly on the same run: "27 of the library's 37 real clusters currently fall below it"; Joji native 12/target 16/4 backfilled/851 units; T-Series native 21/target 28/0 backfilled/short 7/1,101 units | `reports/backfill_plan.md:24,228,230`; `README.md:914-915,948-956,969-980` | `scripts/backfill_plan.py` (`build_frame` = `recommend.build(conn)`, no override) | commit `60ab22c`, 2026-09-15T07:04:20 (executed: `git log -S "9,760"` and `-S "12,310"` both resolve to this exact commit, not the two earlier same-file commits) | ANCHOR-DEPENDENT, **INDETERMINATE** | No `as_of` is printed by this script at all — the commit timestamp is a labelled inference (run ≈ commit time), not a recorded value. Worse: whether `MAX(watched_at)` had already reached today's `2026-09-13T07:24:35` by this early point is **not established by any repo artifact** — this session found no corroboration for the brief's own claim that the database was still growing in exactly this Sept 14–15 window (see "Figures that do not match the repo," below). *If* the anchor were already final, gap ≈ 1.99 d, illustrative multiplier ≈ 1.103× (derived, conditional, not asserted) | PUBLIC |
| 8 | genre-backfill viability: **26 of 37** (naive), **3 of 37** (strict) shallow clusters reach 45 tracks | `reports/genre_coverage.md:192,197`; `README.md:36-37` | `scripts/genre_coverage.py` (`build_frame` = `recommend.build(conn)`, no override) | commit `4edbc6f`, 2026-09-19T07:40:46 | ANCHOR-DEPENDENT, downstream | gap ≈ 6.0112 d (commit-time proxy, labelled inference), illustrative multiplier ≈ 1.34665×. Direction is known and the report *already self-documents an instance of it*: lines 28/30 record T-Series eligible-today = 15 vs. 22 "measured on 2026-09-13" (Δ −7) and Travis Scott 17 vs. 21 (Δ −4), explicitly attributed in-report to "score is computed as_of=now() and decays continuously." Since a smaller gap can only raise scores, never lower them, 26/37 and 3/37 are **floors**: re-measuring at the dataset anchor could only add clusters to the reachable set, never remove one. Magnitude not re-derivable without re-measuring. | PUBLIC |
| 9 | **362-day** export span; **61.8%** single-play rate | `reports/dormancy_probe.md:225,241`; `README.md:4-5,54` | `scripts/dormancy_probe.py` | 2026-09-16T04:42, wall-clock code, **irrelevant to this figure specifically** | **ANCHOR-INDEPENDENT** | Span is `max(last_played) − min(first_played)`; single-play share is `count(play_count==1)/count(*)`. Neither formula contains `as_of`. Confirmed by source-reading `dormancy_probe.build_report` directly, not inherited from `deferred_constants.md`'s C4 table (which reached the same conclusion). | PUBLIC |
| 10 | `dormancy_probe.md`'s *other* content: per-cluster eligible-track counts and ranked lists (N=90/180/365 tables, substitution check) | `reports/dormancy_probe.md` (whole file except lines 225,241) | `scripts/dormancy_probe.py` | 2026-09-16T04:42:49.990695, **wall-clock** (pre-`cd1b28d` code — no override existed at all until today) | ANCHOR-DEPENDENT | gap = 2.8877 d, illustrative multiplier 1.15370× (derived). Not individually itemised per Part 1's scope note — one file, one drift status. | PUBLIC |
| 11 | 40,619 plays / 2,918 canonical tracks / 362 days (opening dataset facts) | `README.md:4-5`; `reports/rediscovery_headline.md` provenance table | `parse_takeout.py` / direct `COUNT(*)` queries | asserted in `tests/test_dataset_facts.py`, re-confirmed 2026-09-19 in `rediscovery_headline.md`'s own provenance table | **ANCHOR-INDEPENDENT** | Lifetime facts of a static, gitignored `taste.db`; no `as_of` term | PUBLIC |
| 12 | embedding-mode ARI/NMI/purity table (`title_artist` 0.6561/0.1415/0.4140, etc.) | `README.md:671-710`; `reports/embedding_modes_pool480.md` (whole file); also `embedding_modes_remeasured.md`, `ground_truth_ids.md`, `ground_truth_audit.md`, `min_samples_sweep.md`, `normalise_title_fix.md`, `nan_guard_fix.md` | `scripts/embedding_modes_pool480.py` (`scored_tracks(conn)`, no `as_of`) → `cluster_eval.py`/`embed.cluster_tracks` | 2026-09-19, commit `4edbc6f...cdd4125` window | **ANCHOR-INDEPENDENT** *(corrected — see methodology note; this path is not path-immune, the figure is)* | The producing call does reach `score.py:61` (verified: `scored_tracks(conn)` with no `as_of`/`end`, `embedding_modes_pool480.py:57`). The figure is unaffected anyway because clustering runs on MiniLM text embeddings of title/artist/genre — the `score` column that call computes is carried in the frame and never read by `cluster_tracks` or by ARI/NMI/purity. Mechanism verified per call site in 0c, not assumed as a family. | PUBLIC |
| 13 | every remaining number in `reports/lastfm_coverage.md`, `defect_audit.md`, and README §1.3–§1.6, §5 (duplicate collapse, contamination, duration merges, classification) | (whole files / sections) | `lastfm.py:384`, `canonical_report.py:11`, `duration_merge_report.py:19`, `pipe_merge_report.py:48`, `ground_truth_audit.py:52,75`, `contamination.py:55`, `genre_coverage.py:80`, `canonical_impact.py:31` — all call bare `scored_tracks(conn)`, verified individually, not assumed | various, 2026-09-14 through 2026-09-19 | **ANCHOR-INDEPENDENT** *(corrected — see methodology note)* | Every one of these reaches `score.py:61` exactly like row 12 does. Each publishes counts/sums over title-, duration-, category- or id-matched groups (canonicalisation, contamination, genre-label coverage) — the score column each call computes is never referenced by the number published. `reports/eval_verification.md` and `reports/readme_audit.md` are genuinely different: neither script calls `scored_tracks` at all, confirmed by the same sweep, so nothing to correct there. README §4, §7, §9 involve no scoring at any point. | PUBLIC |
| 13a | `verify_strict_null.py`'s rank figure: "best rank a removed song reaches: 209 of ~2,000+; zero in top-20" | `README.md` §1.5 (contamination table) | `scripts/verify_strict_null.py:105` (`recommend(cands, ...)`, where `cands` comes from `rediscovery_split` at lines 69/95/101) | 2026-09-13T16:39:33+05:30 (executed: `git log -S "best rank a removed song"` resolves to `5b0596d`) | **IMMUNE BY PATH**, by a different mechanism than row 1 | Same file also makes two *anchor-independent* calls (row 13's family) for its count/sum checks, but this specific rank figure does not use them — it is ranked via `evaluate.rediscovery_split` → `split_frames`, the same explicit-`as_of` path as the headline. Called out separately because it would be easy to misclassify the whole script by its most visible (bare) calls. | PUBLIC |
| 14 | briefs, inventory only (historical, not corrected) | `briefs/asof_core_and_dormancy.md`, `briefs/deferred_constants.md` (distinct from the same-named report), `briefs/reproducibility_and_distribution.md`, `briefs/recency_exclusion.md` | — | 2026-09-20 (all four) | historical — see note | `ls briefs/` = 17 files. These four are the instructions documents behind rows 1–8's own execution; their content matches what was actually done (source-read, spot-checked against the reports they produced). `briefs/gate_drift_audit.md` (this brief) is the 5th and is covered in its own section above and below, not here. The remaining 12 (`backfill_constraint.md`, `backfill_rank.md`, `backfill_toggle.md`, `backfill_toggle_readback.md`, `genre_coverage.md`, `ground_truth_ids.md`, `limit_and_invariance.md`, `pin_evaluation.md`, `pin_plan_readback.md`, `readme_807.md`, `readme_807_plan_readback.md`, `readme_backfill.md`) do not name the recency/eligibility-gate family and are inventoried, not examined further. 4 + 1 + 12 = 17. | briefs/ are PUBLIC once committed; none is LOCAL except this session's own `gate_drift_audit.md` (untracked) |

---

## Figures classed INDETERMINATE

Only one, by the strict definition (historical anchor genuinely
unrecoverable, not merely "we chose not to re-run it"):

- **Row 7 — `reports/backfill_plan.md`'s 10 qualifying clusters / 9,760 /
  12,310.** Two independent gaps, not one: no `as_of` is ever printed by
  `backfill_plan.py`, so even the wall-clock instant is a commit-timestamp
  inference; and whether the database's `MAX(watched_at)` had already
  reached its final value by 2026-09-15T07:04 is not attested by anything
  in this repo (see next section — the brief's own stated reason for
  doubting it does not itself check out). This cannot be corrected without
  a re-measurement, and this brief did not perform one.

Everything else in the drift-affected set (rows 2, 4, 5, 8, 10) is
**ANCHOR-DEPENDENT with the direction known and, in most cases, the exact
wall-clock instant recorded or tightly inferred** — the *magnitude* of the
downstream count changes (how many more clusters would clear a floor, how
many more tracks would count as "shipped fresh") is not re-derivable without
re-measuring, per Part 2's own trap 2, but that is a narrower gap than true
indeterminacy and each row says so explicitly rather than defaulting to
"indeterminate" as a catch-all.

---

## Figures/claims named in this brief that do not match the repo

**One found**, and it is not among the nine headline figures — those all
check out exactly as stated (see the table). It is the brief's own
supporting justification for the INDETERMINATE class definition (lines
108–110 of `briefs/gate_drift_audit.md`):

> "the database is known to have grown mid-project (scores drifted 2.880 ->
> 2.861 between the Sept 14 and Sept 15 dry runs on the same window)"

Searched (executed: `grep -n "2.880\|2.861\|grown mid-project\|dry runs on
the same window"`) across `CLAUDE.md`, `README.md`, every file in `reports/`,
and every other file in `briefs/`: **zero hits outside the brief itself.**
Nothing in the repo's tracked history — including `CLAUDE.md`'s own
"Dataset-scale figures: verify before quoting" bullet, which documents a
*different*, already-known drift (40,617 vs. 40,619 plays; 3,143 vs. 2,918
canonical songs) — records this specific 2.880→2.861 comparison. This does
not mean it never happened; it means it cannot be verified from this
repository as it stands, the same standard applied to every other claim in
this audit.

Worth noting for calibration, not as a defence of the figure above: this is
not the first specific-sounding number in this project's history that traced
to nothing. `f0bc757` (today, 06:15:08) removed "179 of 183 shipped tracks"
from `reports/listening_test.md:63` — introduced in `504ed09` with no
computation behind it anywhere in the repo — and replaced it with the
traceable 177/180 (row 2). One flagged line, not further investigated, since
it is already fixed and out of this brief's scope: `reports/dormancy_probe.md:8`
states 10,319 total plays for its five named clusters where README §3 states
10,539 total music plays library-wide — different denominators (five
clusters vs. the whole library), anchor-independent either way, so not a
gate-drift finding.

---

## Provenance

- Full suite: **535 passed** (`scripts/run.sh -m pytest -q`, 280.30s) —
  matches the brief's stated starting point exactly, no discrepancy.
- `CLAUDE.md` was last touched at `e2505661` (2026-09-19T16:18:05) — none of
  today's ten commits (`f0bc757` through `2ca8d13`) updated it. Its
  Decisions table and State section therefore do not yet reflect any of the
  `as_of`/gate-drift work this audit inventories. Noted as a source-read
  fact about the repo's current state, not corrected — `CLAUDE.md` is
  explicitly out of scope for edits in this brief.
- Environment: this session's Bash tool runs natively inside WSL2
  (`uname -a` reports the WSL2 kernel directly) — no `wsl.exe` prefix
  needed, per CLAUDE.md's Trap 1.
- `git diff --stat` shows nothing, correctly — this file and
  `briefs/gate_drift_audit.md` are both untracked, and untracked files never
  appear in a plain `git diff`. The check the brief's "exactly one new file"
  criterion actually wants is `git show --stat` on the resulting commit,
  run after committing (below): only `reports/gate_drift_audit.md` is
  staged and committed. `briefs/gate_drift_audit.md` remains untracked
  and deliberately outside this commit — committing it too would make two
  new files, not one. Nothing pushed.
