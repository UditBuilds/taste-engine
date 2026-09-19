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


## Rediscover-pool cluster-size drift (informational, not gated)

Cluster size was previously asserted hard against the historical figures below, on the premise that it is time-invariant. That premise is false - a clustering *code* change moves it even with score/as_of held fixed - so as of 2026-09-19 this is reported, not gated (CLAUDE.md open item 9).

- 'T-Series' rediscover-pool cluster size = 490 (historical, `scripts/backfill_report.py` 2026-09-13: 492): **DRIFTED**. Eligible count today = 15 (differs from the 22 measured on 2026-09-13 by -7 - expected: score is computed as_of=now() and decays continuously, so a threshold count taken a day apart is not required to match).

- 'Travis Scott' rediscover-pool cluster size = 86 (historical, `scripts/backfill_report.py` 2026-09-13: 84): **DRIFTED**. Eligible count today = 17 (differs from the 21 measured on 2026-09-13 by -4 - expected: score is computed as_of=now() and decays continuously, so a threshold count taken a day apart is not required to match).


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

| cluster | name | eligible | labeled/eligible | modal genre | modal share | ambiguous | outside sharing genre (noise excl.) | admit ratio |
|---|---|---|---|---|---|---|---|---|
| 7 | Arjan Dhillon / APDHILLON / AP Dhillon | 0 | 0/0 | not computable | n/a | n/a | n/a | n/a |
| 14 | TL-Jhondi Gemar / $uicideboy$ / Moviechat | 0 | 0/0 | not computable | n/a | n/a | n/a | n/a |
| 13 | Technical Guitarist Official / Guitar With Aman / Strumming Strings | 0 | 0/0 | not computable | n/a | n/a | n/a | n/a |
| 16 | Offset / Future / Quality Control | 0 | 0/0 | not computable | n/a | n/a | n/a | n/a |
| 20 | MyGuyMars | 0 | 0/0 | not computable | n/a | n/a | n/a | n/a |
| 21 | Chadtag / wowday / Big K.R.I.T. | 0 | 0/0 | not computable | n/a | n/a | n/a | n/a |
| 4 | backfromparadise / INTERWORLD / Aarush Prashanth | 1 | 1/1 | electronic | 100% | no | 103 | 38% |
| 0 | The Kid LAROI / Cheema Y / The Kid LAROI. | 1 | 1/1 | electronic | 100% | no | 103 | 38% |
| 30 | Lil Uzi Vert | 1 | 1/1 | hip hop | 100% | no | 216 | 81% |
| 10 | King Von / Gesaffelstein / New West | 1 | 1/1 | hip hop | 100% | no | 216 | 81% |
| 1 | Doja Cat / dojacat / SZA | 1 | 1/1 | electronic | 100% | no | 103 | 38% |
| 29 | Lana Del Rey | 1 | 1/1 | electronic | 100% | no | 103 | 38% |
| 11 | Novulent | 2 | 2/2 | independent | 100% | no | 35 | 13% |
| 28 | Radiohead / softsync / Coldplay | 2 | 2/2 | independent | 100% | no | 35 | 13% |
| 31 | Arctic Monkeys / Ellie Goulding / Anna Marx | 2 | 2/2 | pop | 100% | no | 231 | 87% |
| 6 | Juice WRLD | 2 | 2/2 | hip hop | 100% | no | 215 | 81% |
| 22 | Gunna / d4vd / Ze66y | 2 | 2/2 | hip hop | 100% | no | 215 | 81% |
| 19 | Gunna / Yeat | 3 | 3/3 | hip hop | 100% | no | 214 | 80% |
| 3 | A$AP Rocky / LIVELOVEASAP / Major Lazer | 3 | 3/3 | electronic | 100% | no | 101 | 38% |
| 18 | Cigarettes After Sex / Chadtag / Hotel Ugly | 3 | 3/3 | independent | 100% | no | 34 | 13% |
| 27 | Justin Bieber | 4 | 4/4 | pop | 100% | no | 229 | 86% |
| 15 | XXXTENTACION | 5 | 5/5 | hip hop | 100% | no | 212 | 80% |
| 33 | Young Thug | 5 | 5/5 | hip hop | 100% | no | 212 | 80% |
| 2 | Playboi Carti | 8 | 8/8 | hip hop | 100% | no | 209 | 80% |
| 17 | The Neighbourhood | 8 | 8/8 | independent | 100% | no | 29 | 11% |
| 35 | Kendrick Lamar / Kanye West / Eminem | 9 | 9/9 | hip hop | 100% | no | 208 | 80% |
| 9 | PARTYNEXTDOOR | 10 | 9/10 | pop | 89% | no | 225 | 87% |
| 5 | Joji | 10 | 10/10 | pop | 70% | no | 226 | 87% |
| 36 | Lil Baby / Lil Peep / Chris Brown | 13 | 13/13 | hip hop | 100% | no | 204 | 80% |
| 12 | T-Series / Pritam / Sony Music India | 15 | 15/15 | music of asia | 93% | no | 0 | 0% |
| 24 | 21 Savage | 16 | 16/16 | hip hop | 100% | no | 201 | 79% |
| 26 | Future | 18 | 18/18 | hip hop | 100% | no | 199 | 79% |
| 8 | Don Toliver | 22 | 22/22 | hip hop | 100% | no | 195 | 79% |
| 23 | The Weeknd | 25 | 25/25 | pop | 100% | no | 208 | 85% |
| 34 | Drake | 25 | 25/25 | hip hop | 100% | no | 192 | 79% |
| 32 | Travis Scott | 25 | 25/25 | hip hop | 100% | no | 192 | 79% |
| 25 | Metro Boomin | 26 | 26/26 | hip hop | 100% | no | 191 | 79% |

"admit ratio" = outside sharing genre / (eligible pool outside this cluster). The fraction of *everyone else's* eligible candidates this cluster's modal genre would admit into a backfill - a genuine constraint should be well under 100%.


**Clusters where the modal genre is ambiguous (no label above 50% of labeled eligible members), any cluster not just shallow ones:** 0 of 37


## Sensitivity check - is "genre match" actually discriminating?

Within the 268-track labeled-eligible pool (spanning 31 clusters), some labels are common to most clusters rather than distinguishing between them - the same failure mode `embed.GENERIC_TOPICS` already exists to filter for "Music"/"Entertainment", just not extended to these. Applying the brief's own 50% bar symmetrically (a label common across more than half of labeled clusters cannot be what discriminates between them, the same way a genre needs >50% share *within* a cluster to be an unambiguous modal genre) excludes:


| label | clusters it touches | share of labeled clusters |
|---|---|---|
| pop | 30 / 31 | 97% |
| hip hop | 26 / 31 | 84% |
| electronic | 24 / 31 | 77% |
| soul | 22 / 31 | 71% |
| rhythm and blues | 20 / 31 | 65% |

Under the naive (literal brief-definition) view, the median admit ratio across shallow clusters is 79% - most of a shallow cluster's "genre-matching" candidates are actually just most of everyone else's eligible pool. Re-running modal genre and reachability with the labels above excluded ("strict" view) gives the numbers below.


| cluster | name | modal genre (strict) | outside sharing (strict) | admit ratio (strict) | reachable@45 (strict) |
|---|---|---|---|---|---|
| 7 | Arjan Dhillon / APDHILLON / AP Dhillon | not computable | n/a | n/a | no |
| 14 | TL-Jhondi Gemar / $uicideboy$ / Moviechat | not computable | n/a | n/a | no |
| 13 | Technical Guitarist Official / Guitar With Aman / Strumming Strings | not computable | n/a | n/a | no |
| 16 | Offset / Future / Quality Control | not computable | n/a | n/a | no |
| 20 | MyGuyMars | not computable | n/a | n/a | no |
| 21 | Chadtag / wowday / Big K.R.I.T. | not computable | n/a | n/a | no |
| 4 | backfromparadise / INTERWORLD / Aarush Prashanth | not computable | n/a | n/a | no |
| 0 | The Kid LAROI / Cheema Y / The Kid LAROI. | independent | 36 | 13% | no |
| 30 | Lil Uzi Vert | not computable | n/a | n/a | no |
| 10 | King Von / Gesaffelstein / New West | not computable | n/a | n/a | no |
| 1 | Doja Cat / dojacat / SZA | not computable | n/a | n/a | no |
| 29 | Lana Del Rey | independent | 36 | 13% | no |
| 11 | Novulent | independent | 35 | 13% | no |
| 28 | Radiohead / softsync / Coldplay | independent | 35 | 13% | no |
| 31 | Arctic Monkeys / Ellie Goulding / Anna Marx | independent | 36 | 13% | no |
| 6 | Juice WRLD | not computable | n/a | n/a | no |
| 22 | Gunna / d4vd / Ze66y | country | 0 | 0% | no |
| 19 | Gunna / Yeat | not computable | n/a | n/a | no |
| 3 | A$AP Rocky / LIVELOVEASAP / Major Lazer | independent | 34 | 13% | no |
| 18 | Cigarettes After Sex / Chadtag / Hotel Ugly | independent | 34 | 13% | no |
| 27 | Justin Bieber | independent | 36 | 14% | no |
| 15 | XXXTENTACION | independent | 34 | 13% | no |
| 33 | Young Thug | not computable | n/a | n/a | no |
| 2 | Playboi Carti | not computable | n/a | n/a | no |
| 17 | The Neighbourhood | independent | 29 | 11% | no |
| 35 | Kendrick Lamar / Kanye West / Eminem | not computable | n/a | n/a | no |
| 9 | PARTYNEXTDOOR | independent | 36 | 14% | yes |
| 5 | Joji | independent | 33 | 13% | no |
| 36 | Lil Baby / Lil Peep / Chris Brown | independent | 36 | 14% | yes |
| 12 | T-Series / Pritam / Sony Music India | music of asia | 0 | 0% | no |
| 24 | 21 Savage | not computable | n/a | n/a | no |
| 26 | Future | not computable | n/a | n/a | no |
| 8 | Don Toliver | not computable | n/a | n/a | no |
| 23 | The Weeknd | independent | 32 | 13% | yes |
| 34 | Drake | not computable | n/a | n/a | no |
| 32 | Travis Scott | not computable | n/a | n/a | no |
| 25 | Metro Boomin | reggae | 0 | 0% | no |

**T-Series** (CLAUDE.md's named example of incoherent nearest-embedding-centroid backfill - Known Open Item #3): modal genre `music of asia` survives the strict filter unchanged (`music of asia` touches only 1/31 labeled clusters - genuinely discriminative), with 0 outside eligible candidates sharing it either way. Genre-matching does not fix item #3 for this cluster - it fails differently: a short, genuinely-Bollywood-adjacent playlist instead of a full-length incoherent one (Joji, Playboi Carti, Doja Cat).


## Number 3 - Reachability

**Naive (literal brief definition):** of 37 shallow clusters, 26 could reach 45 tracks using genre-matching eligible candidates (native + outside-cluster eligible candidates sharing the modal genre, noise/cluster=-1 excluded because today's backfill mechanism, `writer._select_with_backfill`, never draws from noise either); 5 could not; 6 have no computable modal genre. **This number is inflated** - see the sensitivity check above: the modal genre for most clusters is "pop" or "hip hop", each present on 30/31 and 26/31 labeled clusters respectively, so "shares the modal genre" is close to "is anything at all" for most of the pool.


**Strict (non-discriminative labels excluded):** of 37 shallow clusters, **3 could reach 45 tracks**; 14 could not; **20 have no computable modal genre at all** once pop/hip hop/electronic/etc. are excluded - their eligible members carry no other label, so a genre constraint has nothing left to match on for them.


## Verdict

Genre-constrained backfill viable on this data: **no** - under the literal brief definition 26 of 37 shallow clusters (70% if 37 else 0) reach 45 tracks, but that figure is carried almost entirely by non-discriminative labels ("pop" alone touches 30 of 31 labeled clusters); once those are excluded only 3 of 37 reach 45 tracks and 20 have no genre signal left to constrain on at all.
