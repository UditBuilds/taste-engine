# Backfill Plan - Floor, Length, Genre Guard, Distance Rank

Briefs: `briefs/backfill_constraint.md` (floor, length, guard), `briefs/backfill_rank.md` (distance ranking within the guarded pool). Dry-run only, no API calls, no `--commit`. Script: `scripts/backfill_plan.py`. Rules implemented in `writer.py`/`config.py` (`MIN_CLUSTER_NATIVE=12`, `MAX_BACKFILL_SHARE=0.25`).

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
| Joji | 13 | 'pop' | 4 | 'independent' | 4 |
| Don Toliver | 21 | 'hip hop' | 7 | none | 0 |
| T-Series / Pritam / Sony Music India | 22 | 'music of asia' | 1 | 'music of asia' | 1 |
| 21 Savage | 14 | 'hip hop' | 4 | none | 0 |
| The Weeknd | 20 | 'pop' | 6 | 'independent' | 6 |
| Metro Boomin | 26 | 'hip hop' | 8 | 'reggae' | 1 |
| Future | 19 | 'hip hop' | 6 | none | 0 |
| Travis Scott | 20 | 'hip hop' | 6 | none | 0 |
| Drake | 19 | 'hip hop' | 6 | none | 0 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 'hip hop' | 4 | 'independent' | 4 |

## Per-cluster dry-run plan (naive guard - what ships)

`backfilled` here is the actual shipped count: guard **and** the `MAX_BACKFILL_DISTANCE` ceiling both applied, exactly what `writer.plan()` returns. It can be lower than the guard-only `naive admit` column in the table above - see Distance ranking below for which clusters (if any) that ceiling affected.

| cluster | native | backfilled | final length | target | modal genre | short by | quota units |
|---|---|---|---|---|---|---|---|
| Joji | 13 | 4 | 17 | 17 | 'pop' | - | 901 |
| Don Toliver | 21 | 7 | 28 | 28 | 'hip hop' | - | 1,451 |
| T-Series / Pritam / Sony Music India | 22 | 0 | 22 | 29 | 'music of asia' | 7 | 1,151 |
| 21 Savage | 14 | 4 | 18 | 18 | 'hip hop' | - | 951 |
| The Weeknd | 20 | 6 | 26 | 26 | 'pop' | - | 1,351 |
| Metro Boomin | 26 | 8 | 34 | 34 | 'hip hop' | - | 1,751 |
| Future | 19 | 6 | 25 | 25 | 'hip hop' | - | 1,301 |
| Travis Scott | 20 | 6 | 26 | 26 | 'hip hop' | - | 1,351 |
| Drake | 19 | 6 | 25 | 25 | 'hip hop' | - | 1,301 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 4 | 17 | 17 | 'hip hop' | - | 901 |

## Distance ranking (briefs/backfill_rank.md)

The genre GUARD above is unchanged - it still only filters the candidate pool. What changed is how that filtered pool is ranked: by cosine distance (in the PCA-reduced embedding space HDBSCAN clustered in) to the *requesting* cluster's own centroid, ascending, tie-broken (distance asc, score desc, video_id asc) - not by global score, which was identical for every cluster and is what made backfill collapse onto the same handful of tracks. `_clusters_by_distance` (nearest whole cluster) is not restored.

- Distinct backfill tracks: **before** (score-ranked) **11** distinct filling 52 slots across 10 playlists, largest single playlist 8 - **after** (distance-ranked) **45** distinct filling 51 slots, largest single playlist 8. (The brief's own recollection was "10 distinct ... 52 slots"; the before-figure measured here is 11, not 10 - reproduce it with `scripts/compare_backfill_ranking.py`.) Confirmed stable: 10/10 separate process runs give exactly 45 - see "Genre tie-break" below for why that needed checking.

- Distance distribution across all 51 admitted backfill tracks: min **0.2336**, median **0.4778**, max **0.7380**.

- T-Series distance distribution: not computable - T-Series admitted 0 backfill tracks this run (MAX_BACKFILL_DISTANCE=1.0 excluded its only genre-matching candidate - see below).

- T-Series still admits Doja Cat: **no**.

- **MAX_BACKFILL_DISTANCE=1.0 excludes every genre-matching candidate T-Series has** (recomputed directly, ignoring the ceiling, for this report: **Doja Cat - Streets (Official Video)** at distance **1.1166**). T-Series's final playlist is **22 tracks**, 1 fewer than the 23 it would reach without the ceiling. T-Series has exactly one genre-matching candidate anywhere in its eligible pool, so distance ranking has nothing to choose between, and the guard would admit it regardless of how far it sat - the ceiling is the only thing that can refuse it. This is a stable, deterministic outcome - see "Genre tie-break" immediately below for why that needed checking rather than assuming.

### Genre tie-break: found live on this corpus, fixed 2026-09-14

While regenerating this report, the distinct-backfill-track figure kept changing (45 one run, 46 the next) with no code change in between. Root cause: `writer._modal_genre` picked a cluster's modal genre via `Counter.most_common(1)`, whose tie-break follows dict-insertion order - which here traced back to iterating a Python `set` of genre labels. Python randomises string hashing per process by default, so a set's iteration order, and with it which label won an exact vote tie, could differ from one process to the next. Everything else in the pipeline (row order, embed_text, cluster assignments, the PCA-reduced embedding array, cluster centroids, RANK, CEILING) was verified bit-identical across 10 separate process runs throughout - this was the only non-deterministic step, and it sat inside GUARD, which feeds `writer.plan()`'s actual `--commit` path, not just this report.

Two qualifying clusters carry an exact vote tie for the top spot:

| cluster | tied labels | vote count |
|---|---|---|
| Metro Boomin | `hip hop` vs `pop` | 26 vs 26 (of 26 labeled native members - every one carries both) |
| T-Series / Pritam / Sony Music India | `music of asia` vs `pop` | 21 vs 21 (of 22 labeled native members) |

Before the fix, 10 separate process runs split Metro Boomin's tie **5 `hip hop` / 5 `pop`** (T-Series happened to land on `music of asia` in all 10 sampled, though the vote count proves `pop` was an equally live outcome - not something that particular sample ruled out). **Fix:** break the tie at selection time instead of relying on `Counter`'s insertion order at all - `min(counts.items(), key=lambda kv: (-kv[1], kv[0]))`, highest count first, then alphabetically-first label. That is a pure function of the (count, label) values, independent of iteration order, hence of hash seed. The alphabetical rule was fixed before checking what it would give either cluster; that it prefers `hip hop` and `music of asia` over `pop` (h, m < p) is a consequence of the rule, not a reason for it.

**Post-fix, re-verified 10/10 stable:** Metro Boomin now deterministically lands on `hip hop` (184 genre-matching candidates before the ceiling) - its eight backfilled tracks are the "Metro Boomin" block in Backfill provenance below. T-Series deterministically stays on `music of asia` (unchanged: Doja Cat, distance 1.1166, ceiling-excluded, 0 backfilled). Distinct backfill tracks is now a stable **45** (was oscillating 45/46 pre-fix, 3-of-10 vs 7-of-10 sampled), out of 51 slots.

**Why `reports/genre_coverage.md`'s "0 of 37 clusters ambiguous" (its line 117) is unaffected:** that check's `ambiguous` flag and `modal_share` depend only on the winning label's *vote count*, which is identical on both sides of an exact tie - so neither is disturbed by which label wins. Only the modal-genre *label itself* was ever at risk, and only for a tied cluster. `genre_coverage.py` has its own, separate copy of this same bug pattern (`_modal()`, and its top-15-labels table) - not shared code with `writer.py`, not fixed here (out of this brief's scope), and by the same reasoning does not put "0 of 37" at risk either. See `config.py`'s `MAX_BACKFILL_DISTANCE` comment and `writer.py`'s `_modal_genre` docstring for the same fix documented in the code itself.


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
- Want Me Dead (feat. 21 Savage)  -  admitted by genre `hip hop`, distance 0.5195
- B*tches Gone Tell (feat. Meek Mill)  -  admitted by genre `hip hop`, distance 0.5984
- made for this shit  -  admitted by genre `hip hop`, distance 0.6878

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
- Want Me Dead (feat. 21 Savage)  -  admitted by genre `hip hop`, distance 0.3453
- Freestyle  -  admitted by genre `hip hop`, distance 0.3597
- Lil Peep - Save That Shit (Official Video)  -  admitted by genre `hip hop`, distance 0.3704

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
| A$AP Rocky / LIVELOVEASAP / Major Lazer | 4 |
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
| Young Thug | 2 |
| Kendrick Lamar | 5 |
| Kanye West | 1 |

## Quota

- Qualifying clusters: **10** of 37.

- Total quota to write every qualifying cluster's playlist today: **12,410 units** (breakdown per cluster in the table above; each is `50 + 50*count + 1`).

- Daily cap: 8,000 units. **Exceeds the cap: yes.**

- Cheapest-first, 7 of 10 of these playlists could actually be written today without breaching the cap; the rest would need another day (or several - see CLAUDE.md's cost model: this can write roughly one such playlist a day).
