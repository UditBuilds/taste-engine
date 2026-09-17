# CLAUDE.md — working notes for taste-engine

Read this before touching anything. Most of it is hard-won: every "trap" below
cost a wrong number, a broken file, or a retracted claim.

## What this is

A single-user music recommender built on 40,619 YouTube plays from one Takeout
export. The interesting part is **not** the model — the scoring function has
not changed since the first version. It is the measurement: six times a number
was computed, believed, written down, and then found wrong by the harness.
`README.md` §1 is the spine of the project and §1.7 is its summary.

**Current headline:** rediscovery nDCG@20 **+139.7%** over a most-played
baseline, 3/3 held-out splits, sign-test p = 0.125 — *not* statistically
certifiable at n=3, and the README says so in those words. Do not soften that.

## Environment

Windows host, **WSL Ubuntu-24.04** for all execution. Repo lives on `/mnt/c`;
the venv lives on the WSL filesystem for speed.

```bash
# venv: ~/.venvs/taste-engine   (Python 3.11 via uv; no sudo available)
bash scripts/setup_env.sh        # first time
bash scripts/install_pkg.sh      # after changing pyproject/entry points
bash scripts/run.sh -m pytest -q # run anything inside the venv
```

### Trap 1 — calling `wsl.exe` from the Bash tool

The Bash tool is Git Bash (MSYS2). It rewrites POSIX-looking arguments, so
`/mnt/c/...` becomes `C:/Program Files/Git/mnt/c/...` and shell variables come
back empty. **Always prefix:**

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d Ubuntu-24.04 -- bash scripts/run.sh ...
```

**This varies by how the session was launched — verify, don't assume.** A
2026-09-13 session found its Bash tool already running natively inside
WSL Ubuntu (`uname -a` showed the WSL2 kernel directly, `python3`/`bash`
resolved under `/usr/bin`) rather than Git Bash. In that case the prefix
above is unnecessary — `wsl.exe` is reachable via interop but re-entering the
same distro from inside it is redundant at best. Run `uname -a` once at the
start of a session; if it reports a Linux/WSL2 kernel directly, skip the
prefix and call `bash scripts/run.sh ...` (or the venv python) directly. If
it reports something else (MSYS/MinGW), use the prefix.

### Trap 2 — heredocs mangle backslash escapes

Writing Python through `<<'PYEOF'` corrupts `\n`, `\b`, `\d` inside string
literals — this produced literal newlines inside string constants and broke
three files mid-session. For anything containing regex or escapes, **use the
Write tool, or write a patch script to a file and execute that.** Verify with
`ast.parse` afterwards.

### Trap 3 — don't pipe a long background job through `head`

`... | head -30` SIGPIPEs the producer. A 20-minute evaluation died after
printing its first table and reported exit 0.

### Trap 4 — `git push` has no credentials in this environment

`git push origin main` fails: `fatal: could not read Username for
'https://github.com': No such device or address`. No credential helper, no
`gh` CLI, HTTPS remote — not fixable from here. Ask Udit to run it himself
(suggest `! git push origin main` so it runs in his session and the output
lands in the conversation). Happened twice in one day (2026-09-13) across two
different briefs — don't retry blindly, just ask. Commits themselves work
fine once `user.name`/`user.email` are set (also not something to set
yourself — ask Udit the same way if `git commit` reports no identity).

## Commands

```bash
python -m taste_engine.parse_takeout   # Takeout -> SQLite (~15s, offline)
python -m taste_engine.resolve         # 609 units, needs YT_API_KEY (done)
python -m taste_engine.classify        # heuristics vs categoryId table
python -m taste_engine.cluster_eval    # embedding modes vs playlist ground truth
taste-engine clusters                  # what clusters exist
taste-engine write --cluster-name "..." --limit 45   # DRY RUN, 0 units

scripts/run.sh scripts/nested_eval.py        # the headline
scripts/run.sh scripts/canonical_impact.py   # every figure in §1-2
scripts/run.sh scripts/verify_strict_null.py # is the strict-filter null real?
scripts/run.sh scripts/contamination.py      # non-music audit
scripts/run.sh scripts/verify_write_plan.py  # pre-write gates
scripts/run.sh scripts/audit_notebook.py     # pre-push leak gate (exit 1 = leak)
scripts/run.sh scripts/backfill_report.py "T-Series" "Travis Scott"  # B4-style
                                              # native/backfill report, no API calls
```

Evaluations take **10–30 minutes**. Run them with `run_in_background: true` and
redirect to a file.

## Decisions that must not be silently reverted

Each of these was measured. Changing one without re-measuring will produce a
wrong number that looks fine.

| decision | why |
|---|---|
| `is_music` = **union** of heuristics ∪ categoryId | categoryId describes the *uploader*; heuristics describe the *listener*. 712 vs 53 disagreements, both directions real. |
| canonical key includes the **artist** | Title-only fused Joji's "Die For You" with The Weeknd's, +103 more pairs. Over-merge sums different songs; under-merge just leaves a duplicate. Not symmetric. |
| duration merge tolerance **3 s** | 14 merges, measured false-merge rate **2/14**. Tolerance 0 loses 6 good merges. Documented, not hidden. |
| pipe split keeps the **first** segment | Longest picks the cast list — it fused "Pink Lips" with "BABY DOLL". |
| `--mode rediscover` is the writer's **default** | Otherwise the product ships *replay*, the task the baseline wins, while the README reports rediscovery. Both paths call `recommend.favourites`. |
| `STRICT_MUSIC = True` | 5.6% contamination; the permissive signal is categoryId (121 of 127), not playlists (5). |
| half-life selected by **nested** tuning | Selecting and reporting on the same splits turned +1.9% into an upper bound presented as a finding. |
| playlist titles **pseudonymised** | Public repo, personal titles, and every metric treats them as opaque labels. `redact.py`; mapping is gitignored. |
| **SUPERSEDED 2026-09-14** — shallow-cluster backfill by nearest **embedding centroid**, `MIN_SCORE = 0.5` floor | Fan-re-upload degradation was worse than a shorter, floor-respecting playlist. Not tuned to flatter: T-Series's backfill is musically incoherent (Joji, Playboi Carti, Doja Cat) and that's reported in README, not hidden. Replaced by depth-based length (`MIN_CLUSTER_NATIVE`/`MAX_BACKFILL_SHARE`) plus a genre guard on each backfill candidate — briefs/backfill_constraint.md. |
| `BACKFILL_ENABLED = False` (2026-09-15) | Joji's first live dry run backfilled 3 Playboi Carti tracks + 1 Don Toliver track, admitted by genre `pop` at distance 0.55–0.70 — well inside the 1.0 ceiling, so no threshold fixes it. Both admission signals measure the wrong quantity: topicCategories tags `pop`/`hip hop` on most of the whole library (not discriminative), and the embedding space is title+artist text, not audio. FLOOR/LENGTH/GUARD/RANK/CEILING code is unchanged and unreached, not deleted. `--backfill` re-enables it for one run — briefs/backfill_toggle.md. |
| Last.fm tags **not integrated** into scoring/clustering (2026-09-15) | Measurement-only precursor for a future decision brief: 640/2,918 canonical tracks (21.9%) matched directly, +118 (4.0%) via artist-name fallback; dominant failure is the track having zero tags on Last.fm, not a failed lookup. Not viable as a standalone per-track genre/mood signal. `lastfm.py`, `track_tags`/`track_tag_lookups` tables exist for possible future combination with other signals — nothing in scoring/clustering/write-path reads them. `reports/lastfm_coverage.md`. |
| `evaluate.split_frames`'s **training** frame dates `in_playlist` via `playlist_as_of=split_date`; its **test** frame stays undated (2026-09-16) | An external review found `classify.py`'s `in_playlist` had no date condition at all, and it reaches row membership of the frame a temporal hold-out clusters, not just an `is_music` label. Confirmed, and fixed — `classify()`/`scored_tracks()` take an optional `playlist_as_of` cutoff, `None` everywhere except this one call site, so the live write path and every other caller is unaffected. Measured zero actual impact at the pinned split and all 9 nested-tuning splits before *and* after fixing it (stash/re-run/pop, byte-identical eval output) — no track's `is_music` currently depends on a post-split playlist add — but an undated global in a temporal hold-out is wrong regardless of today's data, so it was fixed anyway. `test` was deliberately left undated: it is ground truth of what was actually played, not training input, and no leak was found on that side. `reports/eval_verification.md`. |
| `cluster_eval`'s ground truth is mapped raw → canonical **before** the coherence join; a canonical track whose raw ground-truth members carry conflicting playlist labels is **dropped**, never a tiebreak (2026-09-17) | The raw/canonical id mismatch (item 11, below) silently dropped 48 of 486 ground-truth music tracks — `canonical_ground_truth()` fixes the join direction (raw → canonical, matching `clustered["video_id"]`, not the reverse) and reports the resulting denominator explicitly (438 → 480). Canonicalising surfaces 3 canonical tracks carrying two playlists' labels — this is a **data-quality exclusion, not a canonicalisation over-merge guard**: every conflict found is one song independently filed into two playlists by the user, not two different songs wrongly fused (`reports/ground_truth_audit.md`, Item 3, checked all three). Picking a winner by play count or recency would assert a single label the source data does not agree on, so the whole track is dropped instead. `reports/ground_truth_audit.md` (diagnosis), `reports/ground_truth_ids.md` (before/after across modes/conventions — the `title_artist`/`title_genre` gap still clears its noise band under `exclude`/`singletons` both before and after; the already-known `single_cluster` flip, item 10, persists but its margin depends on which `min_samples` the noise band is measured at). |

### Cluster ids are not identifiers

HDBSCAN reassigns them whenever the input set changes — enabling the strict
filter moved one cluster from 24 to 11 with unchanged contents. **Use
`--cluster-name`.** Nothing in the repo records a cluster id.

## The invariance-control pattern

The single most valuable thing here. `most_played` cannot depend on the
half-life, so its column is a control; when it moved, it exposed a hold-out set
that varied with the parameter being evaluated. Four tests now assert it
(`tests/test_rediscovery.py::TestBaselineIsAValidControl`).

**Write down invariants you believe are trivially true, and assert them.** Two
of the six bugs were found this way and no other.

Related: `nested_rediscovery` reports `p_floor`. At n=3 a clean sweep gives
p = 0.125, so "not significant" there means *underpowered*, not *no effect* —
`_verdict()` distinguishes three cases and is tested.

## Working agreements with Udit

- **Measure, don't assert.** Every claim in the README maps to a script.
- **Report the failure rate, not just the wins.** False-merge rates, inert
  guards, and things that did not work are stated explicitly.
- **Never claim verification that did not happen.** §8 said write-back was
  mock-tested only, and that line stayed until a real run was reported —
  which happened 2026-09-13; §8 now documents the live 409, the fix, and the
  write that verified it. Keep applying the same rule from here: no status
  line changes on the strength of a plan or a passing test suite alone.
- **Don't change a rule unilaterally.** Propose it, measure its impact on the
  headline, and let him decide. `STRICT_MUSIC` shipped as default-off first.
- **Withdraw wrong numbers in public.** The +28.7% and +7.8% figures stayed in
  the README as retracted rows rather than being edited away.
- Correct your own earlier statements plainly when a check contradicts them —
  this happened several times and is expected, not a problem.

## State

- 424 tests pass. Phases 1–4 built; Phase 5 (Last.fm tag coverage
  measurement, table-only; dormancy signal measurement, table-only) added
  2026-09-15.
- Takeout parsed; all 30,440 videos resolved (609 units spent, quota ledger has
  the record).
- **Live write-back has now run.** The first `--commit` against the real
  account (2026-09-13) hit `HttpError 409 SERVICE_UNAVAILABLE` from
  `playlistItems.insert` on the second insert — an unhandled traceback,
  because the error path only ever handled `403 quotaExceeded`. Three partial
  playlists (13, 3, 2 of 45 tracks; 1,050 units) landed on the real account
  before anyone looked. Fixed: `_call_with_retry` in `writer.py` backs off
  409/500/502/503/504/socket errors with jitter, never retries 403
  quotaExceeded or 401, and any insert failure — predicted or not — now ends
  in a persisted resumable partial instead of a crash (README §8). All three
  junk rows were rolled back (150 units, no retries needed), and a clean
  45-track `--cluster-name "T-Series"` write completed and verified — the
  retry fired for real mid-write and recovered transparently. `token.json`
  is already a valid cached credential, so nothing here needed a browser;
  `run_local_server` still needs one for a *first* consent on a fresh machine.
- **Backfill shipped (2026-09-13), not yet exercised live.** `--cluster-name`
  requests can run out of material scoring >= `config.MIN_SCORE` (0.5) long
  before the playlist fills — T-Series has 22 of 492 eligible, Travis Scott 21
  of 84. `writer.plan()` now backfills from the nearest clusters by embedding
  centroid instead of padding below the floor; if the whole pool runs dry
  first, the playlist comes back short instead of full. Measured
  (`scripts/backfill_report.py`, dry run, no API calls) and written up in
  README's "Backfill" section: Travis Scott's backfill is musically coherent
  (Kendrick, Drake, Post Malone), T-Series's is not (Joji, Playboi Carti, Doja
  Cat — see Known open items #3). Confirmed the rediscovery eval can't move
  and doesn't: stashed the backfill code, re-ran `--both --test-days 30`,
  restored, ran again — byte-identical output both times, not just an
  architectural argument. **The live T-Series playlist on the account predates
  this** — written under the old top-N-by-score logic before `MIN_SCORE`
  existed, so it does not reflect what the current code would produce if
  re-run today. No `--commit` ran this session.
- **Dataset-scale figures: verify before quoting, don't trust a remembered
  number.** A same-day brief stated 40,617 plays / 30,438 videos / 3,143
  canonical songs; querying the DB directly gave 40,619 / 30,440 / 2,918. The
  first two are off by 2 from measurement (matches this file's older figures;
  source of the brief's numbers unclear). The third is off by 225 and
  unreconciled through STRICT_MUSIC-off or any other filter variant tried.
  README's opener uses the measured figures (2,918 canonical songs).
- `data/` is entirely gitignored: Takeout, `taste.db`, embeddings, alias map,
  contamination sample.
- **Last.fm tag coverage measured (2026-09-15), not integrated.** A
  precursor measurement for a future decision brief, not a pipeline change:
  `lastfm.py` (rate-limited `track.getTopTags`/`artist.getTopTags` client,
  ~5 req/s, retried on 429/5xx) plus `track_tags` and `track_tag_lookups`
  tables. Match rate 640/2,918 canonical tracks (21.9%) matched directly,
  another 118 (4.0%) via artist-name fallback; the dominant failure mode is
  the track having zero tags on Last.fm, not a failed match. Top tags skew
  genre-ish but include real junk (decade tags, "seen live", language
  tags). Verdict: **not** usable as a standalone per-track signal —
  `reports/lastfm_coverage.md`. Caught and fixed along the way: a
  NaN-truthiness bug in this new code's own artist resolution, and a
  pre-existing, identically-shaped bug in shipped `embed.artist_from_channel`
  (see Known open items #6 and the Decisions table above) — found while
  cross-checking Last.fm's numbers against the clustering ARI, fixed in a
  separate, later brief.
- **Accumulated defect fixes (2026-09-16), strictly sequential: Part A
  alone, measured and committed, before Part B started.** Part A:
  `embed.normalise_title`'s NaN guard — the same bug class as
  `artist_from_channel` (`f689446`), in a function whose output feeds
  `title_artist`/`title`/`title_genre` corpus text directly, so all three
  modes' ARI moved this time, not just one (open item 6, updated above;
  full before/after `reports/normalise_title_fix.md`). Landed alongside a
  same-commit fix to `tests/test_dormancy.py`'s hardcoded cluster ids,
  which Part A's own reclustering broke (open item 9). Part B, four
  independent fixes, four commits: `dormancy_signals.py`'s `_md_table`
  integer-upcast (cosmetic, no report regenerated — confirmed nothing in
  it renders wrong); `genre_coverage.py`'s `_modal()` hash-seed tie-break
  (16 of 37 real clusters had an exact vote tie — not a two-track edge
  case; `reports/genre_coverage.md` regeneration blocked by open item 9's
  stale gate, not by this fix); `taste-engine status` / `status --verify`
  (`writer.status_rows`, reusing `writer.verify()` unmodified — closes
  open item 7's observability gap; caught and fixed its own NaN-truthiness
  bug live, against the real database, while building it); a defect audit
  (open item 8). 467 tests passing as of the `status` commit; final count
  in that brief's own session report.
- **External review of the embedding-mode comparison: one finding confirmed
  with teeth, one confirmed but inert, three smaller ones triaged
  (2026-09-16).** Independent, read-only review with no project history;
  verified before anything changed, per that brief's own Part A/Part B
  split. **Confirmed, with real consequence:** `cluster_eval.coherence()`
  excludes HDBSCAN noise before computing ARI/NMI/purity (line 68); the
  three modes' ARI denominator ranges 42.9%-71.7% coverage of the same
  438-track ground truth, and the published ranking on ARI specifically
  (not NMI, not purity) is convention-dependent — `title_artist` beats
  `title_genre` under "exclude" (current) and "singletons", but loses to it
  under "noise as one cluster" (0.145 vs 0.185), because that convention's
  penalty scales with the square of a mode's noise count and `title_artist`
  carries the second-highest noise rate of the three. Not changed
  unilaterally — `coherence()` keeps its default; `coherence_by_convention()`
  is additive, backed by `scripts/noise_convention_report.py`, and the
  choice of convention is explicitly left to Udit. **Confirmed, zero
  impact:** `classify.py`'s `in_playlist` had no date condition (fixed, see
  Decisions table); measured zero effect on `is_music`/corpus membership at
  the pinned split and all 9 nested-tuning splits, both directions checked
  (union-rescue and STRICT_MUSIC-filter-rescue), before and after the fix.
  **Confirmed, not fixed (non-goals, see open item 10):** canonical
  collapse silently drops 48 of 486 ground-truth music tracks from
  `cluster_eval` (raw vs. canonical id mismatch); `redact.build_aliases`
  can scramble existing pseudonym labels when a new, alphabetically-earlier
  playlist name appears (mechanism confirmed, no evidence found that it has
  fired on a published figure); `resolve.py` caches a `videos.list`
  omission as permanently deleted with no retry path (matches the
  already-published 2,307-not-found count, not an anomaly). **Refuted in
  its specific consequence:** Last.fm's `error` status is cached exactly
  like a success (real mechanism, `lastfm.py`), but zero of 3,784
  `track_tag_lookups` rows currently carry that status, so the published
  21.9% match-rate conclusion was not drawn on poisoned data, contrary to
  what the review inferred. Also established the review's framing was
  wrong on one point: the `in_playlist` leak has no bearing on the
  embedding-mode comparison at all, since `cluster_eval.compare_modes`
  never applies a temporal split. Full detail, all numbers, and the
  reasoning behind each verdict: `reports/eval_verification.md`. 480 tests
  passing (three commits: verify, then the noise-convention measurement,
  then the `in_playlist` fix — no batching).
- **Ground-truth raw/canonical id mismatch fixed (2026-09-17), three
  commits, strictly sequential per the brief's own Part 0/1/2/3 split.**
  Part 0 (`scripts/ground_truth_audit.py`, `reports/ground_truth_audit.md`,
  read-only): confirmed the 48-of-486 drop (item 11), found all 48 reduce
  to one mechanism (ground truth is raw-id-only, the collapsed frame is
  representative-id-only — the other three hypothesised causes measured
  zero), and found 3 canonical tracks that would carry conflicting playlist
  labels if naively remapped — duplicate uploads of one song, independently
  filed into two playlists by the user, confirmed by checking all three, not
  a canonicalisation over-merge. Part 1 (`canonical.raw_to_canonical_map()`,
  `cluster_eval.canonical_ground_truth()`, Decisions table): fixed the join
  direction (raw → canonical) and the conflict rule (drop the whole
  canonical track, no tiebreak). Denominator: 438 → 480. Invariance check
  (non-negotiable per the brief): pinned eval
  (`--split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14`)
  byte-identical before and after, and also byte-identical to the
  pre-existing `reports/eval_invariance_minsamples.txt` snapshot — ground
  truth feeds coherence metrics only. Part 2
  (`scripts/ground_truth_before_after.py`, `reports/ground_truth_ids.md`):
  re-measured ARI/NMI/purity for all three modes under all three noise
  conventions, before and after, against seven correctness gates that all
  reproduce already-published figures exactly. Two things a future session
  would otherwise have to rediscover: the brief's own cited "0.179 gap at
  36e3b5a" traces to **stale, published README figures** that predate the
  `normalise_title` fix, not `min_samples_sweep.md`'s own §2 measurement
  (0.6655/0.3661, gap 0.2994) — the two numbers look like they should agree
  and do not, for a documented reason, not a bug. And item 10's
  `single_cluster` flip (0.145 vs 0.185) reproduces exactly (0.1453/0.1846)
  but its survival against measured structural noise depends on which
  `min_samples` the noise band is taken from — it clears the band at this
  project's own `min_samples=2`, not the worst-case band across every value
  tested (dominated by a regime break at `min_samples=10` this project does
  not run at). README untouched throughout, per the brief's own scope — that
  is separate work, after these numbers settle. 509 tests (508 passing, 1
  pre-existing failure unrelated to this brief and confirmed present on a
  clean checkout too — `test_dormancy.py`'s real-database test is
  wall-clock-dependent and had already decayed past its threshold before
  this brief started).

### Known open items

1. **3 duplicate pairs survive** a 45-track Hindi-film playlist (45 distinct by
   key, 42 to the eye). A label "Full Video" genuinely runs longer than its
   Topic twin — `Chammak Challo` 4:06 vs 3:48 — so duration cannot merge them
   and widening the tolerance would break everything else.
2. **`Talwiinder - KAMMO JI`** needs a leading-artist strip, which is riskier
   than it looks (must not eat titles legitimately containing a dash).
3. **Clusters are artist-shaped, not mood-shaped.** Genre embeddings were
   tested and rejected (ARI 0.470 vs 0.649, re-measured 2026-09-15 — see item
   6); `topicCategories` is too coarse at 35 tags. Audio features would be the
   real fix and YouTube does not expose them. New evidence (2026-09-13): this
   is also why nearest-cluster backfill (item 5) is musically coherent for an
   artist-genre-shaped cluster (Travis Scott → Kendrick, Drake, Post Malone)
   and incoherent for an industry/language-shaped one (T-Series → Joji,
   Playboi Carti, Doja Cat). "Nearest cluster" is only as meaningful as the
   clustering it's measured in.
4. **§1.4's split table** predates the strict filter; caveated in place rather
   than re-run. Still true as of item 6's fix — that brief re-measured the
   *other* stale table (item 6), not this one.
5. **Rediscover mode pool depth — addressed, not solved.** A shallow cluster
   used to degrade into fan re-uploads once native material ran out; backfill
   (2026-09-13, README §8 "Backfill") fixes the *floor* — nothing below
   `MIN_SCORE` ships — but not the *coherence* (item 3). A cluster whose
   nearest neighbours are genuinely unrelated gets an oddly-mixed playlist
   instead of a low-quality one, not a fixed one.
6. **A second table shared item 4's cause, and has now been fixed.** README's
   embedding-mode ARI table (`title_artist`/`title_genre`/`title`) was
   measured at `f46dc24`, before the exact same two changes item 4's split
   table predates: canonical-upload collapse (`8e7dd42`) and the strict music
   filter (`5b0596d`). Found and re-measured 2026-09-15 while investigating a
   fresh `title_artist`-only probe that didn't match the README (0.652 vs the
   table's 0.627) — full three-mode re-measurement, an
   `embed.artist_from_channel` NaN-guard fix (9/2,918 tracks, `title_artist`
   ARI moved −0.003; `title`/`title_genre` unaffected), and the delta:
   `reports/embedding_modes_remeasured.md`. Current (at that point):
   `title_artist` 0.649 vs `title_genre` 0.470 vs `title` 0.383 — same
   winner, margin narrowed ~21%. **README's table is now current; item 4's
   split table is not** — this fixed one stale table, not the pattern. A
   general guard against a third instance is out of scope for the brief
   that did this and gets its own — see item 9.

   **Stale again as of 2026-09-16.** `embed.normalise_title`'s own
   NaN-guard fix (same bug class, a different function - no Decisions
   table entry, since it's a bugfix rather than a tunable) moved
   `title_artist` 0.649→0.665, `title` 0.383→0.371, `title_genre`
   0.470→0.366: same winner, but `title` and `title_genre` swap 2nd/3rd on
   ARI itself this time, not just on a secondary metric.
   `reports/normalise_title_fix.md` has the full before/after. Deliberately
   **not** folded into this item or README's table by the commit that
   measured it — that commit is scoped to `embed.py` + tests + its own
   report, and whether to update the public-facing numbers now or on the
   next brief that touches this table is Udit's call, not a bugfix
   commit's to make unilaterally. This is now the *second* time this exact
   table has gone stale from an unrelated fix — the pattern this item's
   own text already called out as "out of scope... gets its own" is now
   two-for-two; still not built (see item 9).

   **Stale a third time as of 2026-09-17, for a different reason: the 438
   ground-truth pool this table's ARI is computed against is now 480** —
   the raw/canonical ground-truth join fix (Decisions table; item 11 below)
   changed the denominator, not the clustering. `reports/ground_truth_ids.md`
   re-measured ARI/NMI/purity for all three modes under the new pool: same
   `exclude`-convention winner (`title_artist`), gap over `title_genre`
   widened slightly (0.2994 → 0.3196). Not folded into this table or the
   README for the same reason as the second staleness — Udit's call, not a
   ground-truth-fix commit's to make unilaterally.
7. **A completed write can be invisible — the observability gap is now
   closed, the root cause is not.** (2026-09-15) A `--commit` write
   completed successfully — it produced the Lil Baby/Lil Peep/Chris Brown and
   T-Series playlists the dormancy-signal measurement brief is grounded in,
   `written_playlists` rows 6 and 7 — but printed no confirmation block: no
   playlist URL, no row id, no verification line. It was only caught by
   noticing the quota ledger had dropped by 1,102 units. `taste-engine
   written` (`writer.list_written`) can confirm a row after the fact, but
   nothing detects a write that finished without printing its report or
   prompts a user to go check — quota arithmetic was the only signal that
   caught this one.

   **2026-09-16: `taste-engine status`** (local read of every
   `written_playlists` row, zero quota — `writer.status_rows()`) **and
   `status --verify ROW`** (+1 unit, calls `playlistItems.list` via
   `writer.verify()`, unmodified) now answer "did that write actually
   happen?" without quota arithmetic. What still isn't known: *why*
   `execute_write`'s report went unprinted that one time — deliberately
   not investigated by the brief that added `status` ("B3 adds
   observation only").
8. **Two more instances of the NaN-truthiness / hash-seed-tie-break bug
   families, found and deliberately left unfixed.** (2026-09-16) A
   full-repo audit after this session's other fixes: `redact.alias()`'s
   `if name is None` doesn't catch a float NaN (reachable via
   `redact_series()` → `scripts/build_notebook.py`; mild consequence —
   falls to the existing "unknown name" fallback rather than a fabricated
   label); `embed.strip_artist_from_title`'s `artist` parameter (not
   `title`, which this session did fix) still crashes on a NaN artist,
   unreachable via any real call site today; `scripts/genre_coverage.py`'s
   module-level `label_counts` (the "Top 15 genre labels" table) has the
   identical `Counter.update(set(...))` hash-seed-dependent tie-break this
   session fixed in that file's `_modal()`, as a separate, untouched
   `Counter`. Full inventory, including what was checked and ruled out:
   `reports/defect_audit.md`.
9. **A clustering change breaks any hardcoded assumption downstream of
   it, and this happened three ways from one fix in one session.**
   (2026-09-16) `embed.normalise_title`'s NaN fix (item 6, above) changed
   `title_artist` mode's clustering (38→37 clusters) as a side effect of
   fixing unrelated text. Three things downstream broke or went stale as a
   result: (1) `tests/test_dormancy.py` hardcoded cluster ids `{4, 11,
   35}` for Joji/T-Series/Lil Baby — fixed in the same commit as the fix
   that broke it, resolved by name instead, the same idiom `--cluster-name`
   already uses; (2) `reports/dormancy_signals.md`'s prose ("cluster 4, 35
   and 11 respectively") is now stale and was **not** corrected — it's a
   frozen, `as_of`-pinned report, not code; (3)
   `scripts/genre_coverage.py`'s `EXPECTED_REDISCOVER_CLUSTER_SIZE` gate
   (492/84, commented "time-invariant" — true against score/`as_of` drift,
   false against a clustering *code* change) now hard-fails and blocks
   that script from running at all. Cross-checked against
   `scripts/backfill_report.py`'s independently-computed eligible counts
   (20/18 either way) to confirm the gate's constants are simply stale,
   not a pipeline bug — but **not updated**: it is a hardcoded rule, not a
   bug, and "don't change a rule unilaterally" applies same as anywhere
   else in this file. `reports/genre_coverage.md` is therefore stale for
   two compounding, independent reasons (this, plus item 8's now-fixed
   `_modal()` tie-break) and its "29 of 37 shallow clusters reach 45...
   viable: yes" verdict should not be trusted until Udit decides on the
   gate and it's regenerated. No general staleness guard was built —
   considered and explicitly deferred to its own future brief, same as
   item 6 already flagged before this made it two-for-two.
10. **Which noise convention `coherence()` should use is now a live
    decision, not settled.** (2026-09-16) `cluster_eval.coherence()`
    excludes HDBSCAN noise before scoring ARI/NMI/purity — a defensible
    convention, but the published `title_artist`-wins-on-ARI headline does
    not survive it: under "noise as one cluster" `title_genre` wins ARI
    instead (0.185 vs 0.145). NMI and purity favour `title_artist` under
    every convention tried, and ARI itself still favours `title_artist`
    under "exclude" and "singletons" — only the "one cluster" convention
    flips it, and reports/eval_verification.md argues from ARI's own
    pairwise definition that "one cluster" is the least defensible of the
    three (its penalty scales with the *square* of a mode's noise count,
    not with how wrong the model actually is). `coherence_by_convention()`
    exists and is tested; `coherence()`'s default is untouched and the
    README's table is untouched — both deliberately, pending Udit's choice
    of convention. Once chosen, item 6's table (already stale for other
    reasons) should be re-measured under it in the same pass, not a
    separate one.

    **2026-09-17: the 0.145/0.185 flip reproduces exactly, and is now
    further qualified, not just re-confirmed.** `reports/ground_truth_ids.md`
    independently re-measured it after the ground-truth join fix (item 11)
    — 0.1453/0.1846 — and additionally checked it against
    `reports/min_samples_sweep.md`'s structural noise band: the flip clears
    the band measured at this project's own `min_samples=2`, but not the
    (larger) worst-case band across every `min_samples` value tested, which
    is dominated by `title_artist`'s own one-off bimodal regime break at
    `min_samples=10` — a value this project does not run at. Read as fragile
    rather than as a large, settled reversal either way. The 438-track pool
    quoted above is also now stale for an unrelated reason: after the
    ground-truth join fix it is 480.
11. **Two of three smaller findings from the same external review remain
    deliberately unfixed (non-goals of the brief that found them,
    2026-09-16) — do not re-investigate, only re-open if the convention
    changes underneath them. The third — the raw/canonical ground-truth id
    mismatch — is fixed as of 2026-09-17; see the Decisions table.**
    `redact.build_aliases` re-sorts its *entire* input whenever any new
    playlist name appears, so a new name that sorts before an existing one
    silently relabels everything after it — mechanism confirmed with a
    worked example; no evidence found that it has actually fired against a
    published figure (current mapping is one clean, internally-consistent
    build over all 52 current names), but `data/playlist_aliases.json` is
    gitignored with no history to audit further. `resolve.py`'s
    `pending_video_ids` caches a `videos.list` response that omits a
    requested id as `found=0` forever, with no retry path — real, but the
    current 2,307 such rows match the original resolve run's
    already-published count exactly, not a growing or anomalous number, and
    confirming any specific row as a false negative would require spending
    API quota this brief did not spend. `reports/eval_verification.md` (A3)
    has the full original mechanism and numbers for all three, including the
    now-fixed one — that analysis is still the diagnosis the fix was built
    from.

    **The fixed one, briefly:** `cluster_eval.py`'s ground truth held raw
    `playlist_tracks` video ids while the clustered frame held canonical
    ones; canonical collapse silently dropped 48 of 486 ground-truth music
    tracks whenever the raw id was not the surviving representative — the
    438 quoted throughout item 10 and README's ARI table was already net of
    this, not a clean number. `canonical_ground_truth()` now maps raw ids to
    canonical before the join and drops canonical tracks with conflicting
    playlist labels (Decisions table; `reports/ground_truth_audit.md`,
    `reports/ground_truth_ids.md`). New denominator: 480.

## Repo shape

```
src/taste_engine/
  config.py       every tunable, each with the measurement that chose it
  db.py           schema + a guarded Phase-4 migration
  parse_takeout.py  Phase 1  (regex over 41.9MB HTML; not a DOM parser)
  quota.py        QuotaLedger — written before any API code
  resolve.py      Phase 2  videos.list, batched 50, cached incl. misses
  classify.py     music filter, memoised (cache key includes STRICT_MUSIC)
  canonical.py    duplicate-upload collapse — read its docstring first
  score.py        log1p(plays) x recency decay
  embed.py        MiniLM + PCA(20) + HDBSCAN  (384-d directly does not work)
  cluster_eval.py clustering vs the user's own playlists
  recommend.py    strategies + `favourites` (shared with the eval)
  evaluate.py     replay + rediscovery + nested tuning
  redact.py       pseudonymise playlist titles before publication
  auth.py         OAuth (write only; reads use an API key)
  writer.py       quota-aware, resumable, self-verifying write; backfills a
                  shallow cluster from its nearest neighbours, never below floor
  lastfm.py       Last.fm tag coverage measurement — client + matching; not
                  read by scoring/clustering/write-path (State, above)
  dormancy.py     dormancy signal measurement — which signal predicts
                  "forgotten"; not read by scoring/clustering/write-path
  cli.py          `taste-engine`
```

Remote: https://github.com/UditBuilds/taste-engine (public).
