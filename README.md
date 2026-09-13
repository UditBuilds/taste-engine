# taste-engine

A music recommender trained on one person's actual listening — 40,619 plays
pulled from a year of YouTube watch history — that scores tracks by implicit
feedback, groups them into playlists, and writes them back to YouTube Music
inside a 10,000-unit/day API budget.

It is not a playlist transfer tool and not an LLM wrapper. Those exist. This
learns from behaviour: what got replayed, how recently, and in what company.

**Result:** on **rediscovery** — predicting what gets played again *after
removing the 50 tracks already in heavy rotation* — the model scores nDCG@20 of
**0.324 vs 0.252** for a most-played baseline, winning **4 of 4** hold-out
splits. The baseline wins none.

That is the number that matters. On the easier "will he replay his favourites"
task the same model beats the same baseline by **+0.6%**, because that task is
rigged in the baseline's favour by construction. Both are reported in
[Evaluation](#5-evaluation), along with a metric the model loses on.

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
the artist name and MiniLM keys on it heavily.

### Does removing the artist help? No — measurably not

The obvious fix is to build the embedding from title and genre alone. To test
it rather than assume it, the clusterings are scored against an **external**
ground truth: the user's own 48 hand-curated playlists, restricted to tracks
filed in exactly one of them. A silhouette score would only measure how tidy a
clustering looks in the space it was built from, which is circular; a human
saying "these belong together" is not.

```bash
python -m taste_engine.cluster_eval
```

| embedding text | ARI | NMI | purity | coverage | noise |
|---|---:|---:|---:|---:|---:|
| **`"{title} - {artist}"`** | **0.609** | **0.598** | **0.651** | **61%** | 40% |
| `"{title}"`, artist stripped | 0.547 | 0.538 | 0.556 | 39% | **62%** |
| `"{title}. {genres}"` | *pending* | | | | *needs `resolve.py`* |

Stripping the artist makes every metric worse and pushes noise from 40% to
62%. The reason is visible in the data: song titles alone are `TBH`, `20 Min`,
`Ready`, `Snooze` — near-zero semantic signal for a sentence encoder. The
artist string was not noise crowding out the signal; on this corpus it was
carrying most of it.

Removing it properly also means stripping the `"Artist - "` prefix from the
title, not just dropping the channel — otherwise the artist survives inside the
title and nothing is actually tested. `coverage` is reported so a clustering
cannot win by labelling everything noise.

**The honest caveat on this result:** the ground truth is itself somewhat
artist-shaped — several of the 48 playlists are single-artist collections
(`The Weeknd - Essential Playlist`, `Juice WRLD Unreleased`). So it partly
rewards artist clustering by construction. It is still the best external label
available, and if the goal is generating playlists like the ones this user
actually makes, artist-coherent clusters are the right target. The genre
variant is the real test of the hypothesis and it is blocked on the API key.

## 5. Evaluation

Temporal hold-out. Train strictly before the split, test after. The model sees
no test-window play — not for scoring, not for clustering, not for tuning.
`tests/test_evaluate.py::TestNoLeakage` asserts the windows do not overlap,
because if that fails every number here is meaningless.

```bash
python -m taste_engine.evaluate --both --test-days 30
```

### Two tasks, and only one of them is a recommender

**Replay.** Rank the user's catalogue by what they will play next. Run exactly
as first specified — precision@20, test on the remaining 105 days — **the
baseline scores 1.00**. A track played 50 times in nine months is certain to
recur in the next three.

The first instinct is to blame the metric and make it harder: shorten the
horizon to 30 days, raise *k* to 50. That does restore discrimination, and the
model wins — by **+0.6% nDCG**. But it is fixing the wrong thing. The task
itself is the problem. "Name the tracks he plays most" *is* the baseline; a
model that agrees with it has not recommended anything.

**Rediscovery.** Remove the training window's 50 most-played tracks from both
the candidate pool and the ground truth, then ask what else gets played. This
is the question the product exists to answer — what do you come back to that
you were not already hammering — and it is the one the baseline should be bad
at.

| task | best strategy | baseline | lift |
|---|---:|---:|---:|
| Replay (nDCG@50, 30-day) | 0.530 | 0.527 | **+0.6%** |
| **Rediscovery (nDCG@20)** | **0.324** | **0.252** | **+28.7%** |

Mean over hold-out splits; rediscovery over the 4 with enough reachable truth
to discriminate. On rediscovery the model beats the baseline at **4 of 4**
splits and the baseline wins **0**.

### Rediscovery detail

| strategy | mean nDCG@20 | mean recall@20 | splits beating baseline |
|---|---:|---:|---:|
| **score** | **0.324** | **0.054** | **4 / 4** |
| most_played *(baseline)* | 0.252 | 0.047 | 0 / 4 |
| recency | 0.248 | 0.035 | 3 / 4 |
| cluster_diverse | 0.210 | 0.045 | 1 / 4 |

`recall@20` is small by construction: 20 picks against ~430 reachable tracks
caps it at 4.7%. It is reported for comparability across strategies, not as a
headline. The ceiling is printed alongside it.

One thing the table shows that a single metric would hide: at the 2026-06-01
split, `score` gets **20 hits to `recency`'s 14** yet scores *lower* on nDCG
(0.247 vs 0.370). nDCG is graded by how many times a track was actually
replayed, so a few heavy-rotation finds beat many marginal ones. Hits and nDCG
genuinely disagree, and the disagreement is the useful part.

### Replay result — 6 monthly splits, 30-day horizon, k=50

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

- One user, one year. Four to six hold-out splits from 363 days of one
  person's listening is a small sample. The rediscovery margin is wide enough
  to be worth reporting; it is not a significance test.
- 401 of 874 test tracks at the June split were never seen in training. No
  strategy can recommend a track it has never heard of, so even rediscovery
  measures re-ranking of a known library — not discovery of new music. That
  would need a catalogue this dataset does not contain.
- `cluster_diverse` is the *worst* strategy on both tasks (0.210 nDCG@20 on
  rediscovery, against 0.324 for plain `score`). It trades accuracy for
  variety deliberately — twenty Travis Scott tracks is a good prediction and a
  bad playlist — but as a predictor it loses, and it is reported as losing.
- The half-life was tuned on the replay task, then reused for rediscovery
  without re-tuning. Tuning it on rediscovery would likely help and would also
  be fitting the set it is scored on.

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
  cluster_eval.py    Phase 3 — clustering vs. the user's own playlists
  recommend.py       Phase 3 — playlist strategies
  evaluate.py        Phase 3 — replay + rediscovery hold-outs
notebooks/01_eda.ipynb
tests/               174 tests
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
python -m taste_engine.cluster_eval            # clustering comparison, §4
python -m taste_engine.recommend               # candidate playlists
python -m taste_engine.evaluate --both --test-days 30   # both tasks, §5
python -m taste_engine.evaluate --robustness            # half-life choice
python -m pytest -q                            # 174 tests
```

The venv lives on the WSL filesystem (`~/.venvs/taste-engine`) while the repo
sits on `/mnt/c` — package installs on the 9p mount are slow enough to be worth
avoiding.

Everything above runs offline. Only `resolve.py` and `writer.py` need network
or credentials.

## 9. Not built

- **Write-back** (`writer.py`). Deliberate: review the evaluation numbers
  before spending quota writing playlists. The `written_playlists` /
  `written_tracks` tables are already in the schema. Dry-run will be the
  default and `--commit` explicit.
- **The genre embedding variant.** Coded and tested (`build_corpus(mode=
  "title_genre")`), blocked only on `YT_API_KEY`. It is the real test of
  whether artist-keying is the problem; the artist-stripped variant alone
  says it is not.
- **Cross-service transfer** (Spotify ↔ YouTube). Blocked by Spotify's 25-user
  development-mode cap.
- **LLM-generated track lists.** They hallucinate songs and still leave you
  with the ID-resolution problem.
