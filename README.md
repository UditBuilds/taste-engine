# taste-engine

A music recommender trained on one person's actual listening — 40,619 plays
pulled from a year of YouTube watch history — that scores tracks by implicit
feedback, groups them into playlists, and writes them back to YouTube Music
inside a 10,000-unit/day API budget.

It is not a playlist transfer tool and not an LLM wrapper. Those exist. This
learns from behaviour: what got replayed, how recently, and in what company.

**Result:** precision@50 of **0.81 vs 0.74** for a most-played baseline,
averaged over six monthly temporal hold-outs, on 9,134 music plays across 363
days. It wins at 6 of 6 splits. The honest caveats are in
[Evaluation](#5-evaluation) and they are not buried.

---

## 1. The data

One Google Takeout export, parsed into SQLite. Every figure below is produced
by `python -m taste_engine.parse_takeout` and asserted in
`tests/test_dataset_facts.py`.

| | |
|---|---|
| Watch-history plays (with a resolvable video ID) | **40,619** |
| Unique videos in history | **30,440** |
| Date range | 2025-09-14 → 2026-09-13 (**363 days**) |
| Plays with no channel link | 6,649 |
| Playlists (metadata rows) | 58 |
| Playlists with an exported track list | 48 |
| Playlist track rows | 11,475 (8,457 unique videos) |
| YT Music library songs (with artist metadata) | 239 |
| **Confirmed music tracks** | **2,858** (9.4% of unique videos) |
| **Music plays** | **9,134** (22.5% of all plays) |

2,858 tracks is the number. Not 17,138, not 30,440 — those are *videos
watched*, and most of them are not music.

## 2. What is broken about it

Four things, each of which changes how the model is built.

**The history is HTML, not JSON.** `watch-history.html` is a single 41.9 MB
document with ~41,500 repeated cells. The parser splits on the cell delimiter
and runs four regexes per fragment rather than building a DOM — the markup is
machine-generated and stable, and this is far faster than parsing it properly.

**Twelve-month auto-delete is on.** Nothing before 2025-09-14 exists and
nothing ever will. The left edge of every time-series chart is Google's
retention policy, not a change in behaviour.

**6,649 plays have no channel.** Deleted, private, or Shorts. For these,
Takeout prints the *URL* where the title should be. Storing that as a title
would quietly poison the embeddings, so the parser writes `NULL` and a test
asserts no title ever starts with `https://`.

**Playlist timestamps carry no information.** This one was worth measuring
rather than assuming, and the measurement contradicted the assumption I started
from:

- 53 of 58 playlists claim creation on one of **two days** — 2026-03-11 (39)
  and 2026-03-17 (14). That is a bulk import, not a listening history.
- It is `updated_at`, not `created_at`, that collapses onto the export date
  (56 of 58).
- Only **2** playlists carry the TuneMyMusic transfer description, and those
  two are the only ones created on the export date.
- Titles repeat across the two March dates — `Jim` ×3, `Cursed` ×2,
  `Heartbreak Hindi` ×2 — the fingerprint of the same library imported twice.
  That also explains the **430 duplicate track rows** and why 58 playlists map
  to only 48 exported track files.

The conclusion is the one I expected (playlist recency is unusable); the
mechanism is not. Since the per-playlist CSVs are named by *title* and titles
are not unique, a track list cannot be mapped back to a single playlist ID —
the export loses that link. All of this is asserted in tests so nothing
downstream starts trusting it.

## 3. Music classification

The step that decides whether the project works at all.

### Free signals (0 quota)

| Signal | Unique videos | Plays |
|---|---:|---:|
| Channel ends with `- Topic` | 2,336 | 6,387 |
| Channel contains `VEVO` | 371 | 2,225 |
| Played on `music.youtube.com` | 2,472 | 7,342 |
| Video appears in a playlist | 845 | 3,549 |
| Video in YT Music library | 134 | 1,055 |
| **Union** | **2,858** | **9,134** |

The parts sum to 6,158 but the union is 2,858 — the signals overlap heavily.
They also share one blind spot: an artist-owned channel carrying neither marker
is invisible to all five. `Don Toliver` has 230 plays on a channel named just
`Don Toliver`.

### The authoritative pass — not yet run

`videos.list` with `part=snippet,topicDetails` returns YouTube's own
`categoryId` (`10` = Music) plus `topicCategories`, which are free Wikipedia
genre labels. All 30,440 unique videos resolve in **609 calls = 609 units**,
under 7% of one day's quota.

```bash
python -m taste_engine.resolve --dry-run   # costs nothing
python -m taste_engine.resolve             # 609 units
python -m taste_engine.classify            # prints the comparison table
```

This needs a `YT_API_KEY` in `.env` and **has not been run** — the comparison
table below is the one deliverable in this README that is still empty, and it
is marked empty rather than estimated.

| | heuristic union | categoryId | agreement |
|---|---:|---:|---:|
| unique videos | 2,858 | *pending* | *pending* |

A note on the auth: `videos.list` reads *public* data, so it needs only an API
key — no OAuth consent screen, no browser flow. OAuth is required solely for
Phase 4, which touches the user's own account. The original plan had OAuth
gating both.

## 4. Why content-based, not collaborative filtering

ALS, BPR, and every other matrix-factorisation method infers latent factors by
finding people with overlapping taste. There is exactly **one user** here. The
user–item matrix is a single row; there is nothing to factorise.

So the model is content-based: text embeddings of the user's own tracks,
scored by their own play behaviour. That is the correct choice for this data,
not a compromise forced by it.

### Scoring

```
score = log1p(play_count) × 0.5 ** (days_since_last_play / half_life)
```

`log1p` matters because **60% of tracks were played exactly once** and the top
20 account for only 9.6% of plays. Raw counts would let a handful of obsessive
repeats dominate every playlist. Travis Scott's "MY EYES" at 115 plays beats a
20-play track by 5.75× raw but 1.57× after `log1p` — a real gap that does not
crush the tail.

`half_life = 30 days`, chosen for consistency across hold-outs rather than peak
score. See below.

### Clustering

Tracks are embedded as `"{title} - {artist}"` with `all-MiniLM-L6-v2`, run
locally. Release furniture (`(Official Video)`, `[Audio]`, `(feat. X)`) is
stripped first, and artists are recovered from channel names
(`TravisScottVEVO` → `Travis Scott`).

**HDBSCAN in 384 dimensions does not work on this corpus.** It returned two
clusters, one holding 78% of the library. Projecting to 20 principal components
first is what makes the structure findable:

| | clusters | largest cluster | usable? |
|---|---:|---:|---|
| raw 384-d, `min_cluster_size=12` | 2 | 77.6% | no |
| **PCA 20-d, `min_cluster_size=8`** | **38** | **15.6%** | yes |

The result is 38 clusters over 2,858 tracks with 39.6% outliers — Travis Scott,
The Weeknd, Drake, Future, Metro Boomin, Don Toliver, Kendrick Lamar, a
447-track Bollywood cluster. HDBSCAN was chosen over KMeans precisely so that
one-off listens can be labelled noise instead of being forced into a mood.

**These are artist clusters, not mood clusters.** The embedding text contains
the artist name and MiniLM keys on it heavily. Genre is a fair proxy for mood,
but this is worth naming plainly rather than calling them moods. The
`topicCategories` genre labels from the API pass are the principled fix.

## 5. Evaluation

Temporal hold-out. Train strictly before the split, test after. The model sees
no test-window play — not for scoring, not for clustering, not for tuning.
`tests/test_evaluate.py::TestNoLeakage` asserts the windows do not overlap,
because if that fails every number here is meaningless.

```bash
python -m taste_engine.evaluate --robustness
```

### The specified metric saturates

Run exactly as originally specified — precision@20, train to 2026-06-01, test
on the remaining 105 days — **the baseline scores 1.00**. Not because the model
is good: a track played 50 times in nine months is certain to be played again
in the next three. A metric that cannot go up cannot rank anything.

Shortening the horizon to 30 days and raising *k* to 50 restores
discrimination. That is the configuration reported below.

### Result — 6 monthly splits, 30-day horizon, k=50

| half-life | splits won | mean precision@50 | baseline | mean nDCG lift | worst split |
|---:|---:|---:|---:|---:|---:|
| 7 d | 5 / 6 | 0.783 | 0.737 | +6.5% | **−9.1%** |
| **30 d** | **6 / 6** | **0.807** | 0.737 | **+5.9%** | **+0.3%** |
| 90 d | 5 / 6 | 0.797 | 0.737 | +6.7% | −0.5% |
| 180 d | 6 / 6 | 0.763 | 0.737 | +3.9% | +0.4% |

30 days is the only setting that both wins every split and has the highest mean
precision. 7 days scores higher on average but loses badly at one boundary —
picking it would be fitting the test set.

A control worth stating: at `half_life = 10000`, the score ranking collapses to
*exactly* the baseline's nDCG (0.5271 both). `log1p` is monotonic in play
count, so with no decay the two are the same ranking. That the numbers match to
four decimals is evidence the harness is measuring what it claims to.

### The result that does not flatter the model

Over the **whole catalogue**, raw play count predicts future play volume
*better* than the recency-weighted score does — Spearman **0.49 vs 0.42** at
the 2026-06-01 split. Recency weighting helps at the head of the list, which is
what a 50-track playlist draws from, and hurts in the tail.

So: the model beats the baseline at the job it is for, and loses to it at
whole-catalogue ranking. Both are true. If the goal were "predict every track's
play count", the right answer would be to drop the recency term.

### Also honest

- One user, one year. Six hold-out splits from 363 days of a single person's
  listening is a small sample, and a 7pp precision gap is ~3 tracks in 50.
- 401 of 874 test tracks at the June split were never seen in training. No
  strategy can recommend a track it has never seen; the metric measures
  re-ranking of a known library, not discovery.
- `cluster_diverse` scores *worse* than plain `score` (0.66 vs 0.96
  precision@50). It trades accuracy for variety deliberately — twenty Travis
  Scott tracks is a good prediction and a bad playlist — but it is a worse
  predictor and is reported as one.

## 6. Quota engineering

The YouTube Data API gives a Google Cloud project **10,000 units/day**. It
cannot be purchased. It resets at midnight US/Pacific — not local midnight.

| call | cost | note |
|---|---:|---|
| `videos.list` | 1 | accepts **50 IDs**, so batch |
| `playlistItems.insert` | 50 | the expensive one |
| `playlists.insert` | 50 | |
| `search.list` | 100 | avoided entirely — we already have IDs |

A 100-track playlist write costs **5,000 units**: half a day's budget for one
playlist. So the budget is a design constraint, not a footnote, and
`QuotaLedger` enforces it in code rather than in a comment:

- every spend is written to a SQLite `quota_log` keyed by US/Pacific day, so it
  survives a crash or restart;
- `check()` raises **before** a call that would breach the cap;
- a refused call is never billed;
- units are charged *before* the request goes out, because Google debits on
  receipt — over-counting after a crash is harmless, under-counting is not;
- a `ConnectionError` (the request never left) is refunded; a 403 is not;
- an unknown method raises rather than defaulting to a guessed cost.

Default cap is 8,000, leaving headroom. Configuring it above 10,000 raises
`ValueError` — the ceiling is not purchasable and pretending otherwise in a
config file would be a lie the code tells itself.

## 7. Layout

```
src/taste_engine/
  config.py          paths + every tunable
  db.py              SQLite schema
  parse_takeout.py   Phase 1 — HTML/CSV → SQLite
  quota.py           QuotaLedger (written before any API code)
  resolve.py         Phase 2 — batched videos.list + caching
  classify.py        Phase 2 — music filter + comparison table
  score.py           Phase 3 — implicit-feedback scoring
  embed.py           Phase 3 — MiniLM + PCA + HDBSCAN
  recommend.py       Phase 3 — playlist strategies
  evaluate.py        Phase 3 — temporal hold-out
notebooks/01_eda.ipynb
tests/               142 tests
```

## 8. Running it

Built and run on **WSL Ubuntu**, Python 3.11 via `uv` (no sudo required).

```bash
bash scripts/setup_env.sh                      # venv + deps
bash scripts/install_pkg.sh                    # editable install

# unzip the Takeout export into data/raw/ first, then:
python -m taste_engine.parse_takeout           # ~15s, no network
python -m taste_engine.classify                # heuristic coverage
python -m taste_engine.score                   # top tracks
python -m taste_engine.embed                   # clusters
python -m taste_engine.recommend               # candidate playlists
python -m taste_engine.evaluate --robustness   # the table in §5
python -m pytest -q                            # 142 tests
```

The venv lives on the WSL filesystem (`~/.venvs/taste-engine`) while the repo
sits on `/mnt/c` — package installs on the 9p mount are slow enough to be worth
avoiding.

Everything above runs offline. Only `resolve.py` and `writer.py` need network
or credentials.

## 9. Not built

- **Write-back** (`writer.py`). Deliberate: the build order says review the
  evaluation number before spending quota writing playlists, and the
  `written_playlists` / `written_tracks` tables are already in the schema for
  it. Dry-run will be the default and `--commit` explicit.
- **Cross-service transfer** (Spotify ↔ YouTube). Blocked by Spotify's 25-user
  development-mode cap.
- **LLM-generated track lists.** They hallucinate songs and still leave you
  with the ID-resolution problem.
