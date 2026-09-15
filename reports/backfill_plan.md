# Backfill Plan - Floor, Length, Genre Guard, Distance Rank

Briefs: `briefs/backfill_constraint.md` (floor, length, guard), `briefs/backfill_rank.md` (distance ranking within the guarded pool), `briefs/backfill_toggle.md` (the BACKFILL_ENABLED switch below). Dry-run only, no API calls, no `--commit`. Script: `scripts/backfill_plan.py`. Rules implemented in `writer.py`/`config.py` (`MIN_CLUSTER_NATIVE=12`, `MAX_BACKFILL_SHARE=0.25`).

**`config.BACKFILL_ENABLED = False`** - backfill is off by default (see config.py's comment: both admission signals, YouTube topicCategories and title+artist text embeddings, measure the wrong quantity for "sounds like this cluster" - the Naive vs strict genre guard and Distance ranking sections below are the measurement that motivated leaving it off). The **What ships** section immediately below is what a real `taste-engine write` produces today; every section after it, including the per-cluster plan table, is the enabled-mode comparison kept as evidence for that default - it is *not* what ships. `--backfill` re-enables it for a single run.

## What ships (config.BACKFILL_ENABLED=False)

Native eligible tracks only, in the same score-desc order the enabled path would rank them in first - no LENGTH target, no GUARD, no RANK, no CEILING. `native` here is the same number `writer.plan()` would report as `native_count` either way: native selection runs before the backfill_enabled branch, so this needs no separate disabled-mode `writer.plan()` call to compute.

| cluster | native = shipped length | quota units |
|---|---|---|
| 21 Savage | 14 | 751 |
| Don Toliver | 21 | 1,101 |
| Drake | 19 | 1,001 |
| Future | 19 | 1,001 |
| Joji | 12 | 651 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 701 |
| Metro Boomin | 26 | 1,351 |
| T-Series / Pritam / Sony Music India | 21 | 1,101 |
| The Weeknd | 20 | 1,051 |
| Travis Scott | 20 | 1,051 |

- Total quota to write every qualifying cluster's playlist today, native-only: **9,760 units** (cap 8,000). **Exceeds the cap: yes.**

- Cheapest-first, 8 of 10 of these playlists could actually be written today without breaching the cap.

## Which pool clears the floor

`writer.plan(mode="rediscover")` - the writer's default, and the only mode this report exercises - excludes the top-50 favourites *before* computing per-cluster eligibility. `reports/genre_coverage.md`'s per-cluster table used the favourites-included pool, so it does not say how many clusters clear the floor under the pool `writer.plan()` actually runs against. Both are computed fresh here, not read from that report.

- Favourites-included pool: **10 of 37** real clusters clear `MIN_CLUSTER_NATIVE=12`.

- Favourites-excluded (rediscover) pool - the real operating pool: **10 of 37** clear it.

- Pushed below the floor by favourites exclusion (cleared under favourites-included, do not clear under favourites-excluded): **0** - none.


A count of 0 is ambiguous on its own - it could mean exclusion never crosses the boundary, or that exclusion silently is not being applied to the favourites-excluded pool at all. It is the former: exclusion measurably reduces the native count of **8 of 10** clusters that clear the floor under the favourites-included pool - it simply does not cross 12 for any of them.


| cluster | favourites-included native | favourites-excluded native |
|---|---|---|
| Don Toliver | 25 | 21 |
| 21 Savage | 16 | 14 |
| The Weeknd | 26 | 20 |
| Metro Boomin | 29 | 26 |
| Future | 20 | 19 |
| Travis Scott | 28 | 20 |
| Drake | 22 | 19 |
| Lil Baby / Lil Peep / Chris Brown | 15 | 13 |

All numbers below use the favourites-excluded (rediscover) pool.


## Naive vs strict genre guard (report only)

The shipped GUARD is naive: a backfill candidate matches if it carries the cluster's modal genre at all. Approved as an additional report-only comparison (2026-09-14): what a STRICT guard would have admitted instead, excluding labels that touch more than 50% of labeled real clusters in this pool - the same sensitivity check `scripts/genre_coverage.py` ran, since a label that common cannot be what discriminates a cluster's sound from its neighbours'. **Neither the length nor the shipped selection reads this column; it never feeds back into `writer.plan()`.** Both columns below are guard-only (genre match, capped at deficit) with **no distance ceiling applied to either** - naive vs strict is a guard-to-guard comparison, so conflating one side with the post-ceiling shipped count would make the naive guard look stricter than it is by construction (it never can be - naive matches a superset of what strict matches). Where the ceiling actually cuts a cluster's backfill is reported below, in Distance ranking, and in the *next* table's `backfilled` column, which does reflect it.

Non-discriminative labels found (touch >50% of 32 labeled clusters): electronic, hip hop, pop, rhythm and blues, soul


| cluster | native | naive modal | naive admit (guard only) | strict modal | strict admit |
|---|---|---|---|---|---|
| Joji | 12 | 'pop' | 4 | 'independent' | 4 |
| Don Toliver | 21 | 'hip hop' | 7 | none | 0 |
| T-Series / Pritam / Sony Music India | 21 | 'music of asia' | 1 | 'music of asia' | 1 |
| 21 Savage | 14 | 'hip hop' | 4 | none | 0 |
| The Weeknd | 20 | 'pop' | 6 | 'independent' | 6 |
| Metro Boomin | 26 | 'hip hop' | 8 | 'reggae' | 1 |
| Future | 19 | 'hip hop' | 6 | none | 0 |
| Travis Scott | 20 | 'hip hop' | 6 | none | 0 |
| Drake | 19 | 'hip hop' | 6 | none | 0 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 'hip hop' | 4 | 'independent' | 4 |

## Per-cluster plan if backfill were enabled (naive guard)

**Not what ships** - `config.BACKFILL_ENABLED=False`; see What ships above for the real per-cluster numbers. `backfilled` here is guard **and** the `MAX_BACKFILL_DISTANCE` ceiling both applied, exactly what `writer.plan(..., backfill=True)` returns. It can be lower than the guard-only `naive admit` column in the table above - see Distance ranking below for which clusters (if any) that ceiling affected.

| cluster | native | backfilled | final length | target | modal genre | short by | quota units |
|---|---|---|---|---|---|---|---|
| Joji | 12 | 4 | 16 | 16 | 'pop' | - | 851 |
| Don Toliver | 21 | 7 | 28 | 28 | 'hip hop' | - | 1,451 |
| T-Series / Pritam / Sony Music India | 21 | 0 | 21 | 28 | 'music of asia' | 7 | 1,101 |
| 21 Savage | 14 | 4 | 18 | 18 | 'hip hop' | - | 951 |
| The Weeknd | 20 | 6 | 26 | 26 | 'pop' | - | 1,351 |
| Metro Boomin | 26 | 8 | 34 | 34 | 'hip hop' | - | 1,751 |
| Future | 19 | 6 | 25 | 25 | 'hip hop' | - | 1,301 |
| Travis Scott | 20 | 6 | 26 | 26 | 'hip hop' | - | 1,351 |
| Drake | 19 | 6 | 25 | 25 | 'hip hop' | - | 1,301 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 4 | 17 | 17 | 'hip hop' | - | 901 |

## Distance ranking (briefs/backfill_rank.md)

The genre GUARD above is unchanged - it still only filters the candidate pool. What changed is how that filtered pool is ranked: by cosine distance (in the PCA-reduced embedding space HDBSCAN clustered in) to the *requesting* cluster's own centroid, ascending, tie-broken (distance asc, score desc, video_id asc) - not by global score, which was identical for every cluster and is what made backfill collapse onto the same handful of tracks. `_clusters_by_distance` (nearest whole cluster) is not restored.

- Distinct backfill tracks: **before** (score-ranked) **11** distinct filling 52 slots across 10 playlists, largest single playlist 8 - **after** (distance-ranked) **45** distinct filling 51 slots, largest single playlist 8. (The brief's own recollection was "10 distinct ... 52 slots"; the before-figure measured here is 11, not 10 - reproduce it with `scripts/compare_backfill_ranking.py`.)

- Distance distribution across all 51 admitted backfill tracks: min **0.2336**, median **0.4778**, max **0.7380**.

- T-Series distance distribution: not computable - T-Series admitted 0 backfill tracks this run (MAX_BACKFILL_DISTANCE=1.0 excluded its only genre-matching candidate - see below).

- T-Series still admits Doja Cat: **no**.

- **MAX_BACKFILL_DISTANCE=1.0 now excludes every genre-matching candidate T-Series had** (recomputed directly, ignoring the ceiling, for this report: **Doja Cat - Streets (Official Video)** at distance **1.1166**). T-Series's final playlist is **21 tracks** this run, 1 fewer than the 22 it would have reached without the ceiling. This is the ceiling doing exactly what it was added to do: T-Series had exactly one genre-matching candidate anywhere in its eligible pool, so distance ranking had nothing to choose between, and the guard would have admitted it regardless of how far it sat - the ceiling is the only thing that can refuse it.


### Backfill provenance (native cluster -> admitting genre, distance)


**Joji**

- Playboi Carti - EVIL J0RDAN (Official Visualizer)  -  admitted by genre `pop`, distance 0.5461
- Playboi Carti - OLYMPIAN (Official Audio)  -  admitted by genre `pop`, distance 0.6374
- Playboi Carti - Sky [Official Video]  -  admitted by genre `pop`, distance 0.6831
- Tiramisu  -  admitted by genre `pop`, distance 0.7039

**Don Toliver**

- Metro Boomin, Don Toliver, Future - Too Many Nights (Official Video)  -  admitted by genre `hip hop`, distance 0.4687
- Metro Boomin, Future - I Can't Save You (Interlude) (Visualizer) ft. D  -  admitted by genre `hip hop`, distance 0.5258
- Yeat - ON NOTHING (Official Music Video)  -  admitted by genre `hip hop`, distance 0.6658
- Raindance  -  admitted by genre `hip hop`, distance 0.7144
- PARTYNEXTDOOR - MAKE IT TO THE MORNING (Lyric Video)  -  admitted by genre `hip hop`, distance 0.7161
- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`, distance 0.7239
- Ballin'  -  admitted by genre `hip hop`, distance 0.7380

**21 Savage**

- wgft (feat. Burna Boy)  -  admitted by genre `hip hop`, distance 0.3874
- B*tches Gone Tell (feat. Meek Mill)  -  admitted by genre `hip hop`, distance 0.5984
- made for this shit  -  admitted by genre `hip hop`, distance 0.6878
- 5 TO 10  -  admitted by genre `hip hop`, distance 0.6924

**The Weeknd**

- The Weeknd, Playboi Carti - Timeless  -  admitted by genre `pop`, distance 0.4661
- Dave - Raindance (ft. Tems)  -  admitted by genre `pop`, distance 0.5248
- Playboi Carti & The Weeknd - RATHER LIE (Official Audio)  -  admitted by genre `pop`, distance 0.5355
- Future, Metro Boomin, The Weeknd - Young Metro (Official Music Video)  -  admitted by genre `pop`, distance 0.5808
- Don Toliver - NO POLE | REMAKE 7 UP DAMN  -  admitted by genre `pop`, distance 0.6068
- Baby Came Home 2 / Valentines  -  admitted by genre `pop`, distance 0.6237

**Metro Boomin**

- Future - Trillionaire (Audio) ft. Youngboy Never Broke Again  -  admitted by genre `hip hop`, distance 0.3391
- 21 Savage x Metro Boomin - Runnin (Official Music Video)  -  admitted by genre `hip hop`, distance 0.3522
- The Weeknd - Starboy ft. Daft Punk (Official Video) ft. Daft Punk  -  admitted by genre `hip hop`, distance 0.4778
- 21 Savage & Metro Boomin - Glock In My Lap (Official Music Video)  -  admitted by genre `hip hop`, distance 0.4838
- Beat It  -  admitted by genre `hip hop`, distance 0.4855
- Drink N Dance  -  admitted by genre `hip hop`, distance 0.5255
- Slap The City  -  admitted by genre `hip hop`, distance 0.5342
- Don Toliver - NO POLE | REMAKE 7 UP DAMN  -  admitted by genre `hip hop`, distance 0.5849

**Future**

- Future, Metro Boomin - We Don't Trust You (Official Audio)  -  admitted by genre `hip hop`, distance 0.2523
- Future, Metro Boomin - Jealous (Official Audio)  -  admitted by genre `hip hop`, distance 0.3620
- Young Metro  -  admitted by genre `hip hop`, distance 0.3811
- Future, Metro Boomin - Mile High Memories (Official Audio)  -  admitted by genre `hip hop`, distance 0.4027
- Future - Throw Away (Lyrics)  -  admitted by genre `hip hop`, distance 0.4794
- If We Being Rëal [Official Audio]  -  admitted by genre `hip hop`, distance 0.4805

**Travis Scott**

- Chris Brown - Under The Influence (Official Video)  -  admitted by genre `hip hop`, distance 0.2776
- Metro Boomin, Travis Scott - Raindrops (Insane) (Visualizer)  -  admitted by genre `hip hop`, distance 0.2842
- Metro Boomin, Travis Scott, Young Thug - Trance (Visualizer)  -  admitted by genre `hip hop`, distance 0.2843
- Die Hard  -  admitted by genre `hip hop`, distance 0.3172
- Go Crazy  -  admitted by genre `hip hop`, distance 0.3340
- Runaway  -  admitted by genre `hip hop`, distance 0.3503

**Drake**

- ghost boy  -  admitted by genre `hip hop`, distance 0.2839
- ghost girl  -  admitted by genre `hip hop`, distance 0.3348
- haunt u  -  admitted by genre `hip hop`, distance 0.3402
- Freestyle  -  admitted by genre `hip hop`, distance 0.3597
- Lil Peep - Save That Shit (Official Video)  -  admitted by genre `hip hop`, distance 0.3704
- Die Hard  -  admitted by genre `hip hop`, distance 0.3745

**Lil Baby / Lil Peep / Chris Brown**

- Runaway  -  admitted by genre `hip hop`, distance 0.2336
- Die Hard  -  admitted by genre `hip hop`, distance 0.2640
- Pussy & Millions  -  admitted by genre `hip hop`, distance 0.2740
- B*tches Gone Tell (feat. Meek Mill)  -  admitted by genre `hip hop`, distance 0.2759

## Skipped: below the floor

27 of 37 real clusters have fewer than 12 eligible native tracks in the favourites-excluded pool and generate no playlist at all.


| cluster | native (favourites-excluded) |
|---|---|
| The Kid LAROI | 1 |
| Doja Cat | 3 |
| A$AP Rocky / LIVELOVEASAP / Major Lazer | 3 |
| Playboi Carti | 8 |
| backfromparadise / INTERWORLD / speed up france | 1 |
| Arjan Dhillon / APDHILLON / Prem Dhillon | 0 |
| Central Cee | 2 |
| Juice WRLD | 5 |
| Technical Guitarist Official | 0 |
| Technical Guitarist Official | 0 |
| King Von / New West / Matt Maltese | 1 |
| Novulent | 2 |
| PARTYNEXTDOOR | 8 |
| TL-Jhondi Gemar / Moviechat / $uicideboy$ | 0 |
| Yeat / Gunna / Cigarettes After Sex | 11 |
| XXXTENTACION | 6 |
| The Neighbourhood | 9 |
| Offset / Future / Quality Control | 0 |
| Justin Bieber | 3 |
| Radiohead / NBSPLV / softsync | 2 |
| Lana Del Rey | 1 |
| Post Malone | 5 |
| Lil Uzi Vert | 1 |
| Arctic Monkeys / Ellie Goulding / Chris Brown | 1 |
| Young Thug | 1 |
| Kendrick Lamar | 5 |
| Kanye West | 1 |

## Quota if backfill were enabled (comparison, not what ships)

See What ships at the top for the real (native-only) quota total - **9,760 units**. Everything below is what these same qualifying clusters would cost with `--backfill`.

- Qualifying clusters: **10** of 37.

- Total quota to write every qualifying cluster's playlist today, if backfill were enabled: **12,310 units** (breakdown per cluster in the table above; each is `50 + 50*count + 1`).

- Daily cap: 8,000 units. **Exceeds the cap: yes.**

- Cheapest-first, 7 of 10 of these playlists could actually be written today without breaching the cap; the rest would need another day (or several - see CLAUDE.md's cost model: this can write roughly one such playlist a day).
