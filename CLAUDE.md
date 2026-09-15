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

- 392 tests pass. Phases 1–4 built; Phase 5 (Last.fm tag coverage
  measurement, table-only) added 2026-09-15.
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
   `reports/embedding_modes_remeasured.md`. Current: `title_artist` 0.649 vs
   `title_genre` 0.470 vs `title` 0.383 — same winner, margin narrowed ~21%.
   **README's table is now current; item 4's split table is not** — this
   fixed one stale table, not the pattern. A general guard against a third
   instance is out of scope for the brief that did this and gets its own.

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
  cli.py          `taste-engine`
```

Remote: https://github.com/UditBuilds/taste-engine (public).
