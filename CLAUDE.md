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

### Trap 2 — heredocs mangle backslash escapes

Writing Python through `<<'PYEOF'` corrupts `\n`, `\b`, `\d` inside string
literals — this produced literal newlines inside string constants and broke
three files mid-session. For anything containing regex or escapes, **use the
Write tool, or write a patch script to a file and execute that.** Verify with
`ast.parse` afterwards.

### Trap 3 — don't pipe a long background job through `head`

`... | head -30` SIGPIPEs the producer. A 20-minute evaluation died after
printing its first table and reported exit 0.

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
- **Never claim verification that did not happen.** §8 says write-back is
  mock-tested only because no live write has been confirmed. Change that line
  only when a real run is reported.
- **Don't change a rule unilaterally.** Propose it, measure its impact on the
  headline, and let him decide. `STRICT_MUSIC` shipped as default-off first.
- **Withdraw wrong numbers in public.** The +28.7% and +7.8% figures stayed in
  the README as retracted rows rather than being edited away.
- Correct your own earlier statements plainly when a check contradicts them —
  this happened several times and is expected, not a problem.

## State

- 289 tests pass. Phases 1–4 built.
- Takeout parsed; all 30,440 videos resolved (609 units spent, quota ledger has
  the record).
- **No live write has happened.** OAuth `run_local_server` cannot open a
  browser on headless WSL; Udit runs `--commit` himself.
- `data/` is entirely gitignored: Takeout, `taste.db`, embeddings, alias map,
  contamination sample.

### Known open items

1. **Live write-back unverified.** Blocked on Udit running `--commit`.
2. **3 duplicate pairs survive** a 45-track Hindi-film playlist (45 distinct by
   key, 42 to the eye). A label "Full Video" genuinely runs longer than its
   Topic twin — `Chammak Challo` 4:06 vs 3:48 — so duration cannot merge them
   and widening the tolerance would break everything else.
3. **`Talwiinder - KAMMO JI`** needs a leading-artist strip, which is riskier
   than it looks (must not eat titles legitimately containing a dash).
4. **Clusters are artist-shaped, not mood-shaped.** Genre embeddings were
   tested and rejected (ARI 0.397 vs 0.627); `topicCategories` is too coarse at
   35 tags. Audio features would be the real fix and YouTube does not expose
   them.
5. **§1.4's split table** predates the strict filter; caveated in place rather
   than re-run.
6. **Rediscover mode needs pool depth** — a ~90-song cluster asked for 50
   degrades into fan re-uploads by the 27th.

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
  writer.py       quota-aware, resumable, self-verifying write
  cli.py          `taste-engine`
```

Remote: https://github.com/UditBuilds/taste-engine (public).
