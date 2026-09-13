# taste-engine

A music recommender trained on one person's implicit feedback — 40,619 plays
from a year of YouTube watch history — that scores tracks, clusters them into
playlists, and writes them back to YouTube Music inside a 10,000-unit/day API
budget it is not allowed to exceed.

**The honest headline: the model does not significantly beat a most-played
baseline.** +1.9% nDCG@20 on three held-out splits, winning two of three,
sign-test p = 0.50. What this repo is actually worth reading for is how that
number was arrived at — including two earlier, larger, wrong versions of it
that were computed, believed, and then discarded.

---

## 1. How the number got smaller three times

This is the part I would want a reviewer to read. The measurement changed twice
before the result did, and both changes came from the harness catching itself
rather than from anything external.

| | reported | why it was wrong |
|---|---:|---|
| first | **+28.7%**, 4/4 splits | hold-out set leaked; see below |
| second | **+7.8%**, 3/4 splits | leak fixed, but the half-life was tuned on the same splits it was reported on |
| **final** | **+1.9%**, 2/3 splits, p = 0.50 | nested tuning: half-life selected on early splits, reported on later ones it never saw |

### The leak, and the control that caught it

`evaluate.py` carried this comment, written when the sweep was added, on the
assumption it would never matter:

> `most_played` is invariant to half-life, so its column is a control — if it
> moves, something is leaking.

It moved. Baseline nDCG drifted **0.270 → 0.339** across a half-life sweep, and
the baseline cannot depend on a parameter it does not use.

The cause: `scored_tracks()` returns rows ordered by `score`. The rediscovery
task holds out the top-50 most-played tracks, and where play counts *tie* at
that cutoff, `head(50)` silently inherited the incoming row order. So the
half-life decided which tracks were held out — the excluded set was a function
of the model being evaluated, and the "baseline" was a different baseline at
every setting.

The fix is one clause (`sort_values(["play_count", "video_id"])`) in the
hold-out selection and in every strategy. The guard against it returning is
four tests asserting that the excluded set, the ground truth, the baseline's
picks and the baseline's *score* are all invariant to half-life:

```python
def test_baseline_score_is_independent_of_half_life(self, db):
    scores = {evaluate_rediscovery(db, SPLIT, half_life=hl, ...)["results"]
              .iloc[0]["ndcg@20"] for hl in (7, 30, 90, 365)}
    assert len(scores) == 1, f"baseline nDCG moved with half-life: {scores}"
```

The +28.7% figure had already been written into this README and committed. It
was withdrawn rather than quietly edited, which is why the table above exists.

### The selection bias, and nested tuning

With the leak closed the lift was +7.8% — but the half-life had been chosen by
sweeping the same four splits the result was reported on. That makes the number
an upper bound, not an estimate.

Nested protocol (`scripts/nested_eval.py`): split the timeline, select the
half-life on the **earlier** splits, report on the **later** ones the selection
never touched.

```
SELECTION — on the 2 dev splits (2026-04, 2026-05)
 half_life  mean_baseline  mean_score  wins   lift
         7         0.3588      0.4312   2/2  +20.2%
        14         0.3588      0.4383   2/2  +22.1%     <- chosen
        30         0.3588      0.3968   2/2  +10.6%
       180         0.3588      0.3588   0/2    0.0%

REPORT — on 3 held-out splits (2026-06, 2026-07, 2026-08)
     split  baseline  score    lift   win
2026-06-01    0.2024 0.2749  +35.8%  True
2026-07-01    0.4628 0.3386  -26.8%  False
2026-08-01    0.2076 0.2760  +33.0%  True

  mean lift  +1.9%      wins 2/3      sign-test p = 0.500
```

**+22.1% on the splits used to choose the parameter becomes +1.9% on splits
that were not.** That gap is the whole lesson, and it is why the honest verdict
is *no significant improvement over the most-played baseline*.

### Why only five splits

Nine monthly boundaries fit in 363 days; four are unusable, and the reason is a
property of the data rather than a threshold I picked:

| split | train days | music tracks in train | reachable test truth |
|---|---:|---:|---:|
| 2025-12-01 | 78 | 166 | 0 |
| 2026-01-01 | 109 | 190 | 4 |
| 2026-02-01 | 140 | 227 | **0** |
| 2026-03-01 | 168 | 227 | 15 |
| **2026-04-01** | 199 | **1,139** | 325 |
| 2026-05-01 | 229 | 1,707 | 406 |
| 2026-06-01 | 260 | 2,460 | 458 |
| 2026-07-01 | 290 | 2,929 | 296 |
| 2026-08-01 | 321 | 3,138 | 496 |

Music tracks jump **227 → 1,139** between March and April. The account's *music*
listening effectively begins in March 2026 — the same weeks as the playlist
bulk import in §4 — so the 363-day figure describes the **watch** history while
the usable **music** history is about six months. Three held-out splits is the
ceiling this dataset supports, and three splits cannot establish significance.
A sign test would need a clean sweep to reach p < 0.05 at this n.

## 2. The result, with its caveats attached

### Rediscovery — the task worth measuring

Remove the training window's 50 most-played tracks from both the candidate pool
and the ground truth, then ask what else gets played. "Name the tracks he plays
most" *is* the baseline; a model that agrees with it has recommended nothing.

| | mean nDCG@20 | splits won | verdict |
|---|---:|---:|---|
| score (log1p × recency) | 0.297 | 2/3 | **not significant** |
| most_played (baseline) | 0.291 | — | |

`recall@20` is capped at **4.4%** by construction — 20 picks against 296–496
reachable tracks — so it is for comparing strategies, never a headline. The
ceiling is printed beside it.

At the 2026-06-01 split, `score` finds **20 tracks to `recency`'s 13** yet
scores *lower* on nDCG (0.275 vs 0.320). nDCG grades by how often a track was
actually replayed, so a few heavy-rotation finds beat many marginal ones. Hits
and nDCG disagree, and the disagreement is the informative part.

### Replay — the trivial task, kept as contrast

Rank the catalogue by what gets played next, favourites included. Run as
originally specified — precision@20 over the remaining 105 days — **every
strategy scores 1.00**. A track played 50 times in nine months is certain to
recur in the next three; a metric that cannot go up cannot rank anything. On
the graded version of that same window the baseline *wins* (nDCG@20 0.578 vs
0.528).

Bounding the horizon to 30 days and raising *k* to 50 restores discrimination:

| strategy | precision@50 | nDCG@50 | Spearman |
|---|---:|---:|---:|
| **score** | **0.96** | **0.566** | 0.404 |
| most_played *(baseline)* | 0.86 | 0.548 | **0.479** |
| cluster_diverse | 0.64 | 0.328 | — |
| recency | 0.46 | 0.307 | 0.306 |

This is the task the model most clearly wins, and it is the one that matters
least — which is the point of keeping it.

### Results that do not flatter the model

- **Raw play count predicts future play volume better than the model does.**
  Spearman **0.479 vs 0.404** over the whole catalogue. Recency weighting helps
  the head of the list, which is what a playlist draws from, and hurts the tail.
  If the goal were "predict every track's play count", the right move would be
  to delete the recency term.
- **`cluster_diverse` loses on both tasks.** It trades accuracy for variety
  deliberately — twenty Travis Scott tracks is a good prediction and a bad
  playlist — but as a predictor it is worse, and is reported as worse.
- **Two design hypotheses were tested and rejected**, not quietly dropped: see
  §6 on removing the artist from the embedding, and on replacing it with genre.

### No leakage

`tests/test_evaluate.py::TestNoLeakage` asserts the training window never
overlaps the test window, because if that fails every number above is
meaningless.

```bash
scripts/run.sh scripts/nested_eval.py    # the nested result
scripts/run.sh scripts/final_numbers.py  # every other figure
```

## 3. The data

One Google Takeout export, parsed into SQLite. Every figure is produced by
`python -m taste_engine.parse_takeout` and asserted in
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
watched*, and 88% of them are not music. The free heuristics alone find 2,858;
§5 is how the other 712 were found and why they matter.

Note the gap between 363 days of *watch* history and roughly six months of
usable *music* history (§1). The headline dataset size is not the dataset the
model is evaluated on.

## 4. What is broken about it

Four things, each of which changed how the model is built.

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
  **430 duplicate track rows**, why 58 playlists map to only 48 exported track
  files, and (see §1) why the model's usable history starts in March.

The conclusion is the one I expected — playlist recency is unusable — but the
mechanism is not the one I assumed. Since the per-playlist CSVs are named by
*title* and titles are not unique, a track list cannot be mapped back to a
single playlist ID; the export loses that link. All of it is asserted in tests
so nothing downstream starts trusting it.

## 5. Music classification

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

## 6. Why content-based, not collaborative filtering

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

`half_life = 14 days`, selected by nested tuning on dev splits only (§1). The
lift it buys on splits the selection never saw is not significant.

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

## 7. Quota engineering

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

## 8. Layout

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

## 9. Running it

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
python -m taste_engine.cluster_eval            # clustering comparison, §6
python -m taste_engine.recommend               # candidate playlists
python -m taste_engine.evaluate --both --test-days 30   # both tasks, §2
scripts/run.sh scripts/nested_eval.py                   # the headline, §1
scripts/run.sh scripts/final_numbers.py                 # every other figure
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
  grouping is unchanged, so no number in §6 moves. The mapping lives in
  `data/playlist_aliases.json`, also gitignored.
- **Track, artist and cluster names are shown as-is.** They are the substance
  of the analysis, and a notebook that hides them would not be worth reading.

## 10. Not built

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
