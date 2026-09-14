# Genre Coverage Measurement

Brief: `briefs/genre_coverage.md`. Read-only measurement, no API calls, no existing module modified. New code: `scripts/genre_coverage.py`.

## Step 0 - where things live

- Genre/topic field: `video_metadata.topic_categories` (`src/taste_engine/db.py`), JSON list of Wikipedia URLs from `resolve.py`'s `topicDetails.topicCategories`. Cached for 24,181 of 30,440 video_metadata rows - no fetch needed.

- Turned into readable labels by `classify._genres_from_topics` -> `genres` column, tidied (generic labels like the near-universal "Music" dropped) by `embed.tidy_genres`.

- Canonical tracks: `canonical.collapse()`, called by `score.scored_tracks(canonical=True)` (default). One row per merged song; `genres` on that row is the **representative (most-played) upload's** genres only, not a union across merged variants - see Coverage below.

- Cluster assignments: `embed.cluster_tracks()`, called by `recommend.build()`. Not persisted; recomputed deterministically from cached embeddings in `data/artifacts/`. Cluster **ids** are unstable across runs (CLAUDE.md); `cluster_name` is not.

- `config.MIN_SCORE` = 0.5. Shallow cluster threshold (from the brief) = 45 eligible members.

## Correctness gates (checked before any number below is trusted)

- Canonical tracks = 2,918, matches CLAUDE.md's independently measured 2,918: **OK**

- Re-derived canonical_key groups 1:1 with `collapse()`'s own grouping: **OK**

- 'T-Series' rediscover-pool cluster size = 492 (matches `scripts/backfill_report.py`'s measured 492, time-invariant): **OK**. Eligible count today = 22 (matches).

- 'Travis Scott' rediscover-pool cluster size = 84 (matches `scripts/backfill_report.py`'s measured 84, time-invariant): **OK**. Eligible count today = 20 (differs from the 21 measured on 2026-09-13 by -1 - expected: score is computed as_of=now() and decays continuously, so a threshold count taken a day apart is not required to match).


## Methodology note - which pool is "eligible"

The brief defines eligible candidate as `score >= config.MIN_SCORE` with no mention of excluding favourites. The primary numbers below use that plain reading: the full canonical+clustered pool, favourites included. `writer.plan(mode="rediscover")` - the actual backfill path - excludes the top-50 favourites *before* computing per-cluster eligibility; CLAUDE.md's cited T-Series (22) / Travis Scott (21) figures are that rediscover-pool count, reproduced above as a cross-check, not the primary figure used below. Clustering itself is identical either way - `recommend.build()` clusters the full frame before any favourites exclusion happens.


## Number 1 - Coverage

- As-delivered (representative upload's genres): 2,808 / 2,918 (96.2%) canonical tracks carry >=1 label; 2,318 / 2,918 (79.4%) carry >1.

- Available-in-cache (union of genres across every merged upload sharing a canonical key): 2,809 / 2,918 (96.3%) carry >=1 label; 2,347 / 2,918 (80.4%) carry >1.

- **Gap: 1 canonical tracks (0.0%) have a genre label sitting in cache on a merged-away upload, but the canonical layer only keeps the representative's, so they show 0 labels as-delivered.** Of those recovered-by-union tracks, 1 / 1 (100.0%) had a `- Topic` upload among their merged variants - the representative itself was not.

- Of the 110 as-delivered zero-genre canonical tracks: 103 are resolved (metadata exists, genuinely untagged by YouTube) and 7 are unresolved (deleted/private - metadata never existed to tag).


**Top 15 genre labels by canonical-track count (as-delivered):**

| label | tracks |
|---|---|
| pop | 2,176 |
| hip hop | 1,695 |
| electronic | 773 |
| music of asia | 615 |
| rhythm and blues | 486 |
| soul | 423 |
| independent | 402 |
| film | 128 |
| rock | 92 |
| music of latin america | 21 |
| reggae | 12 |
| video game culture | 12 |
| jazz | 10 |
| action game | 10 |
| lifestyle (sociology) | 10 |

**Coverage by uploader type (representative upload's channel):**

| uploader type | tracks | with >=1 genre | coverage |
|---|---|---|---|
| - Topic | 2,113 | 2,059 | 97.4% |
| other | 542 | 495 | 91.3% |
| VEVO | 254 | 254 | 100.0% |
| unknown | 9 | 0 | 0.0% |

## Number 2 - Per shallow cluster

37 real (non-noise) clusters total; 37 are shallow (eligible members < 45).

| cluster | name | eligible | labeled/eligible | modal genre | modal share | ambiguous | outside sharing genre (noise excl.) |
|---|---|---|---|---|---|---|---|
| 7 | Arjan Dhillon / APDHILLON / Prem Dhillon | 0 | 0/0 | nan | nan% | n/a | nan |
| 11 | Technical Guitarist Official | 0 | 0/0 | nan | nan% | n/a | nan |
| 12 | Technical Guitarist Official | 0 | 0/0 | nan | nan% | n/a | nan |
| 16 | TL-Jhondi Gemar / Moviechat / $uicideboy$ | 0 | 0/0 | nan | nan% | n/a | nan |
| 20 | Offset / Future / Quality Control | 0 | 0/0 | nan | nan% | n/a | nan |
| 13 | King Von / New West / Matt Maltese | 1 | 1/1 | pop | 100% | no | 259.0 |
| 5 | backfromparadise / INTERWORLD / speed up france | 1 | 1/1 | electronic | 100% | no | 114.0 |
| 0 | The Kid LAROI | 1 | 1/1 | electronic | 100% | no | 114.0 |
| 27 | Lana Del Rey | 1 | 1/1 | pop | 100% | no | 259.0 |
| 31 | Arctic Monkeys / Ellie Goulding / Chris Brown | 1 | 1/1 | electronic | 100% | no | 114.0 |
| 36 | Kanye West | 1 | 1/1 | pop | 100% | no | 259.0 |
| 29 | Lil Uzi Vert | 2 | 2/2 | pop | 100% | no | 258.0 |
| 8 | Central Cee | 2 | 2/2 | hip hop | 100% | no | 239.0 |
| 14 | Novulent | 2 | 2/2 | independent | 100% | no | 37.0 |
| 32 | Young Thug | 2 | 2/2 | pop | 100% | no | 258.0 |
| 26 | Radiohead / NBSPLV / softsync | 2 | 2/2 | rock | 100% | no | 3.0 |
| 1 | Doja Cat | 3 | 3/3 | pop | 100% | no | 257.0 |
| 25 | Justin Bieber | 3 | 3/3 | pop | 100% | no | 257.0 |
| 2 | A$AP Rocky / LIVELOVEASAP / Major Lazer | 4 | 4/4 | pop | 100% | no | 256.0 |
| 9 | Juice WRLD | 5 | 5/5 | pop | 100% | no | 255.0 |
| 28 | Post Malone | 5 | 5/5 | pop | 100% | no | 255.0 |
| 35 | Kendrick Lamar | 5 | 5/5 | pop | 100% | no | 255.0 |
| 18 | XXXTENTACION | 6 | 6/6 | pop | 100% | no | 254.0 |
| 3 | Playboi Carti | 8 | 8/8 | pop | 100% | no | 252.0 |
| 19 | The Neighbourhood | 9 | 9/9 | pop | 100% | no | 251.0 |
| 17 | Yeat / Gunna / Cigarettes After Sex | 11 | 11/11 | hip hop | 82% | no | 232.0 |
| 15 | PARTYNEXTDOOR | 11 | 10/11 | rhythm and blues | 90% | no | 80.0 |
| 4 | Joji | 13 | 13/13 | pop | 77% | no | 250.0 |
| 34 | Lil Baby / Lil Peep / Chris Brown | 15 | 15/15 | hip hop | 100% | no | 226.0 |
| 21 | 21 Savage | 16 | 16/16 | hip hop | 100% | no | 225.0 |
| 24 | Future | 20 | 20/20 | hip hop | 100% | no | 221.0 |
| 10 | T-Series / Pritam / Sony Music India | 22 | 22/22 | music of asia | 95% | no | 1.0 |
| 33 | Drake | 22 | 22/22 | hip hop | 100% | no | 219.0 |
| 6 | Don Toliver | 25 | 25/25 | hip hop | 100% | no | 216.0 |
| 22 | The Weeknd | 26 | 26/26 | pop | 100% | no | 234.0 |
| 30 | Travis Scott | 28 | 28/28 | hip hop | 100% | no | 213.0 |
| 23 | Metro Boomin | 29 | 29/29 | pop | 100% | no | 231.0 |

**Clusters where the modal genre is ambiguous (no label above 50% of labeled eligible members), any cluster not just shallow ones:** 0 of 37


## Number 3 - Reachability

Of 37 shallow clusters: **29 could reach 45 tracks** using only genre-matching eligible candidates (native eligible + eligible candidates outside the cluster sharing its modal genre, noise/cluster=-1 excluded because today's backfill mechanism (`writer._select_with_backfill`) never draws from noise either). 3 could not. 5 have no computable modal genre (zero eligible members carry any genre label) and are excluded from both counts rather than assumed either way.


## Verdict

Genre-constrained backfill viable on this data: **yes** - 29 of 37 shallow clusters (78%) reach 45 tracks via genre-matching eligible candidates alone.
