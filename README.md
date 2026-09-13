# taste-engine

A music recommender trained on one person's actual listening — 40,619 plays
pulled from a year of YouTube watch history — that scores tracks by implicit
feedback and groups them into playlists, inside a 10,000-unit/day API budget it
is not allowed to exceed.

Write-back to YouTube Music is designed and schema'd but deliberately not
built; see [§9](#9-not-built).

It is not a playlist transfer tool and not an LLM wrapper. Those exist. This
learns from behaviour: what got replayed, how recently, and in what company.

**Result:** on **rediscovery** — what gets played again *after removing the 50
tracks already in heavy rotation* — the model scores nDCG@20 of **0.373 vs
0.346** for a most-played baseline: **+7.8%**, winning 3 of 4 hold-out splits
and losing the fourth by 27%.

That is a real but modest effect on a small sample, and it is stated that way
throughout. On the easier "will he replay his favourites" task the baseline is
genuinely competitive, because that task is rigged in its favour by
construction. [Evaluation](#5-evaluation) reports both, a metric the model
loses on, and a leak in the harness that inflated an earlier version of this
number to +28.7%.

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
| Music tracks, heuristics only | 2,858 (9.4% of unique videos) |
| **Music tracks, heuristics ∪ `categoryId`** | **3,570** (11.7% of unique videos) |
| **Music plays** | **10,539** (25.9% of all plays) |

3,570 tracks is the number. Not 17,138, not 30,440 — those are *videos
watched*, and 88% of them are not music. The free heuristics alone find 2,858
of them; §3 is how the other 712 were found and why they matter.

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
- Titles repeat across the two March dates — one appears ×3, five more ×2 —
  the fingerprint of the same library imported twice. That also explains the
  **430 duplicate track rows** and why 58 playlists map to only 48 exported
  track files.

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

### The authoritative pass — run, 609 units

`videos.list` with `part=snippet,topicDetails` returns YouTube's own
`categoryId` (`10` = Music) plus `topicCategories`, free Wikipedia genre
labels. All 30,440 unique videos resolved in **609 calls = 609 units**, 7.6% of
one day's quota. 28,133 resolved; 2,307 were deleted or private and are cached
as misses so they are never paid for twice.

```bash
python -m taste_engine.resolve --dry-run   # costs nothing
python -m taste_engine.resolve             # 609 units, ~6 min
python -m taste_engine.classify            # the table below
```

### Heuristics vs. categoryId

| | videos |
|---|---:|
| Heuristic union | 2,858 |
| `categoryId == 10` | 3,510 |
| **Agreement rate** | **97.3%** |
| Heuristic precision vs. categoryId | 98.1% |
| Heuristic recall vs. categoryId | 79.7% |

| | categoryId says music | says not music |
|---|---:|---:|
| **heuristics say music** | 2,798 | 53 |
| **heuristics say not** | 712 | 24,570 |

The heuristics are **precise but incomplete**: when they fire they are almost
always right (98.1%), but they miss one music video in five.

**The 712 they miss are exactly the predicted blind spot** — artist-owned
channels with no `- Topic` or `VEVO` marker. Don Toliver's own channel accounts
for 75 plays of a single track; also Central Cee, PARTYNEXTDOOR, Santan Dave,
21 Savage, Radiohead, and the Indian labels T-Series, Saregama and YRF.

**The 53 going the other way are more interesting**, and they changed the
design. categoryId files them under *People & Blogs* or *Entertainment*: fan
re-uploads, slowed remixes, extended edits — "Lil Uzi Vert - XO Tour Llif3",
"Travis Scott - sdp interlude (Original Version)", "gta 4 theme (slowed)".
They are music. `categoryId` describes the **uploader's channel**, not the
content, and an uploader who is not a YouTube music partner gets a
non-music category regardless of what they uploaded.

So the two labels are not competing estimates of one truth. categoryId knows
the catalogue; the heuristics know what *this user* treats as music — the
signal that caught those 53 was playing them on `music.youtube.com` or filing
them in a playlist. **`is_music` is therefore the union, not an override**:
discarding 53 tracks the user demonstrably treats as music, to exclude a
handful of marginal compilations, is a bad trade.

**Final training set: 3,570 tracks** (2,858 heuristic ∪ 3,510 categoryId ∪ 7
unresolved-but-heuristic-positive), up 24.9% on heuristics alone.

A note on auth: `videos.list` reads *public* data, so it needs only an API key
— no OAuth consent screen, no browser flow. OAuth is required solely for Phase
4, which touches the user's own account. The original plan had OAuth gating
both.

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

`half_life = 14 days`, tuned on the rediscovery task rather than replay. See
below — including why that number deserves less confidence than it looks like.

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

The obvious fix is to drop the artist and embed title plus genre instead. To
test it rather than assume it, all three clusterings are scored against an
**external** ground truth: the user's own 48 hand-curated playlists, restricted
to tracks filed in exactly one of them. A silhouette score would only measure
how tidy a clustering looks in the space it was built from, which is circular.
A human saying "these belong together" is not.

```bash
python -m taste_engine.cluster_eval
```

| embedding text | ARI | NMI | purity | coverage | clusters | noise |
|---|---:|---:|---:|---:|---:|---:|
| **`"{title} - {artist}"`** | **0.627** | **0.627** | **0.668** | 53% | 45 | 44% |
| `"{title}"`, artist stripped | 0.180 | 0.611 | 0.563 | 25% | 51 | **70%** |
| `"{title}. {genres}"` | 0.397 | 0.458 | 0.437 | **67%** | 33 | 41% |

**The hypothesis was wrong.** Artist-keyed text agrees best with the user's own
filing on every alignment metric — ARI 0.627 against 0.397 for genre and 0.180
for bare titles.

Why each variant fails:

- **Bare titles** carry almost no semantic signal. The corpus is `TBH`,
  `20 Min`, `Ready`, `Snooze`. MiniLM cannot group those, so 70% land in noise
  and coverage collapses to 25%. The artist string was not crowding out the
  signal; it *was* most of the signal.
- **Genre labels are too coarse.** `topicCategories` returns 35 distinct tags
  across 3,570 tracks, and the common ones dominate — `hip hop`, `pop`,
  `electronic`, `rhythm and blues`. 95% of tracks carry at least one, so the
  coverage is real; the resolution is not. Genre gives the encoder something
  to hold onto, so
  coverage is the best of the three at 67% and noise the lowest at 41%. But
  the resulting 33 buckets are broad, and they cut across playlists the user
  drew much more finely.

That is a genuine trade-off rather than a clean win, and worth stating as one:
**genre clusters more tracks, artist clusters them more like the user would.**
Alignment is the goal here, so `title_artist` stays the default; `mode=
"title_genre"` is one argument away.

Removing the artist properly also meant stripping the `"Artist - "` prefix from
the *title*, not just dropping the channel — otherwise the artist survives in
the title and nothing is actually tested. `coverage` is reported so a
clustering cannot win by labelling everything noise.

**The honest caveat, which the genre result does not remove:** the ground truth
is itself partly artist-shaped — several of the 48 playlists are single-artist
collections, named after the artist they collect. It therefore rewards artist
clustering to some degree by construction. It remains
the best external label available, and if the goal is generating playlists like
the ones this user actually makes, that bias is pointing at the target rather
than away from it.

## 5. Evaluation

Temporal hold-out. Train strictly before the split, test after. The model sees
no test-window play — not for scoring, not for clustering, not for tuning.
`tests/test_evaluate.py::TestNoLeakage` asserts the windows do not overlap,
because if that fails every number here is meaningless.

```bash
scripts/run.sh scripts/final_numbers.py    # every figure below
```

### First, a leak I shipped and then caught

An earlier version of this README claimed **+28.7%** on rediscovery, winning
4 of 4 splits. That number was wrong, and the thing that caught it was a
control written into the code on the assumption it would never fire:

> `most_played` is invariant to half-life, so its column is a control — if it
> moves, something is leaking.

It moved. Baseline nDCG drifted **0.270 → 0.339** across a half-life sweep.
The cause: `scored_tracks` returns rows ordered by `score`, so where play
counts tie at the top-50 cutoff, *which tracks got held out* depended on the
half-life. The excluded set was a function of the model being evaluated.

Fixed by breaking ties on `video_id` in both the hold-out selection and every
strategy. Four tests now assert the excluded set, the ground truth, the
baseline's picks and the baseline's score are all invariant to half-life. With
the leak closed the baseline is a single constant (0.3457) across the whole
sweep, and the model's advantage drops from +28.7% to **+7.8%**.

### Rediscovery — the task that matters

Remove the training window's 50 most-played tracks from both the candidate pool
and the ground truth, then ask what else gets played. "Name the tracks he plays
most" *is* the baseline; a model that agrees with it has not recommended
anything.

| strategy | mean nDCG@20 | mean recall@20 | splits beating baseline |
|---|---:|---:|---:|
| **score** | **0.373** | **0.049** | **3 / 4** |
| most_played *(baseline)* | 0.346 | 0.042 | 0 / 4 |
| cluster_diverse | 0.288 | 0.044 | 1 / 4 |
| recency | 0.168 | 0.032 | 1 / 4 |

**+7.8% mean nDCG@20.** The per-split picture is what the mean hides:

| split | reachable truth | baseline | score | lift |
|---|---:|---:|---:|---:|
| 2026-04-01 | 325 | 0.388 | 0.476 | +22.8% |
| 2026-05-01 | 406 | 0.330 | 0.400 | +21.4% |
| 2026-06-01 | 458 | 0.202 | 0.275 | +35.8% |
| 2026-07-01 | 296 | 0.463 | 0.339 | **−26.8%** |

Three clear wins and one clear loss. **No half-life in the sweep wins all
four** — the settings that never lose (180d, 365d) do so by barely differing
from the baseline at all. So the effect is real and positive on average but
unstable, and on four splits it is not a significance test.

**The number deserves less confidence than it looks like.** The half-life was
chosen from a sweep over the same four splits this table reports, so +7.8% is
an upper bound, not an unbiased estimate. Holding out a fifth split to select
on would be the fix; 363 days of data does not comfortably provide one.

`recall@20` is capped by construction — 20 picks against 296–458 reachable
tracks puts the ceiling at 4.4% — so it is for comparing strategies, not a
headline. The ceiling is printed next to it.

At the 2026-06-01 split, `score` gets **20 hits to `recency`'s 13** yet scores
*lower* on nDCG (0.275 vs 0.320). nDCG is graded by how many times a track was
actually replayed, so a few heavy-rotation finds beat many marginal ones. Hits
and nDCG genuinely disagree, and the disagreement is the useful part.

### Replay — the trivial task, shown for contrast

Rank the catalogue by what gets played next, favourites included. Run exactly
as first specified — precision@20, test on the remaining 105 days — **every
strategy scores 1.00**. A track played 50 times in nine months is certain to
recur in the next three. A metric that cannot go up cannot rank anything, and
on the graded version of that same window the baseline *wins* (nDCG@20 0.578
vs 0.528).

Shortening the horizon to 30 days and raising *k* to 50 restores discrimination:

| strategy | precision@50 | nDCG@50 | Spearman |
|---|---:|---:|---:|
| **score** | **0.96** | **0.566** | 0.404 |
| most_played *(baseline)* | 0.86 | 0.548 | **0.479** |
| cluster_diverse | 0.64 | 0.328 | — |
| recency | 0.46 | 0.307 | 0.306 |

The model wins here too, by +3.3% nDCG — but the task is one where simply
naming the favourites is nearly optimal, which is exactly why it is not the
headline.

### The result that does not flatter the model

Over the **whole catalogue**, raw play count predicts future play volume
*better* than the recency-weighted score does — Spearman **0.479 vs 0.404**
(the last column above). Recency weighting helps at the head of the list, which
is what a playlist draws from, and hurts in the tail.

So the model beats the baseline at the job it is for and loses to it at
whole-catalogue ranking. If the goal were "predict every track's play count",
the right answer would be to drop the recency term entirely.

### Also honest

- One user, one year, four usable splits. The rediscovery margin is worth
  reporting; it is not statistically established, and one split contradicts it.
- 469 of 970 test tracks at the June split were never seen in training. No
  strategy can recommend a track it has never heard of, so even rediscovery
  measures re-ranking of a known library — not discovery of new music. That
  needs a catalogue this dataset does not contain.
- `cluster_diverse` loses on both tasks. It trades accuracy for variety
  deliberately — twenty Travis Scott tracks is a good prediction and a bad
  playlist — but as a predictor it is worse, and it is reported as worse.
- The earlier +28.7% figure stood in this README through one commit before the
  control caught it. The control existed because the invariance was written
  down as an assumption rather than assumed silently.

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
  redact.py          pseudonymises playlist titles before publication
  recommend.py       Phase 3 — playlist strategies
  evaluate.py        Phase 3 — replay + rediscovery hold-outs
notebooks/01_eda.ipynb
tests/               187 tests
```

## 8. Running it

Built and run on **WSL Ubuntu**, Python 3.11 via `uv` (no sudo required).

```bash
bash scripts/setup_env.sh                      # venv + deps
bash scripts/install_pkg.sh                    # editable install

# unzip the Takeout export into data/raw/ first, then:
python -m taste_engine.parse_takeout           # ~15s, no network
python -m taste_engine.resolve                 # 609 units, needs YT_API_KEY
python -m taste_engine.classify                # heuristic coverage
python -m taste_engine.score                   # top tracks
python -m taste_engine.embed                   # clusters
python -m taste_engine.cluster_eval            # clustering comparison, §4
python -m taste_engine.recommend               # candidate playlists
python -m taste_engine.evaluate --both --test-days 30   # both tasks, §5
scripts/run.sh scripts/final_numbers.py                 # every figure in §5
python -m pytest -q                            # 187 tests
```

The venv lives on the WSL filesystem (`~/.venvs/taste-engine`) while the repo
sits on `/mnt/c` — package installs on the 9p mount are slow enough to be worth
avoiding.

Only `resolve.py` needs network and credentials; everything else runs offline
and degrades to heuristic labels if you skip it.

### What this repo deliberately does not contain

It is public and built on one person's data, so:

- `data/raw/` — the Takeout export, a year of **watch and search history** — is
  gitignored, as is the derived `data/taste.db`.
- **Playlist titles are pseudonymised** (`Playlist A`, `Playlist B`, …)
  everywhere they could surface: notebook outputs, README tables, cluster
  summaries. Every metric that uses them — ARI, NMI, purity — treats them as
  opaque group labels, so the real names add nothing to the analysis and
  several are personal. Redaction is a pure relabelling; a test asserts the
  grouping is unchanged, so no number in §4 moves. The mapping lives in
  `data/playlist_aliases.json`, also gitignored.
- **Track, artist and cluster names are shown as-is.** They are the substance
  of the analysis, and a notebook that hides them would not be worth reading.

## 9. Not built

- **Write-back** (`writer.py`). Deliberate: review the evaluation numbers
  before spending quota writing playlists. The `written_playlists` /
  `written_tracks` tables are already in the schema. Dry-run will be the
  default and `--commit` explicit.
- **Mood clustering that is actually about mood.** `topicCategories` genres
  turned out too coarse (35 tags) to beat artist-keyed text on alignment.
  Audio features would be the real fix, and YouTube does not expose them.
- **Cross-service transfer** (Spotify ↔ YouTube). Blocked by Spotify's 25-user
  development-mode cap.
- **LLM-generated track lists.** They hallucinate songs and still leave you
  with the ID-resolution problem.
