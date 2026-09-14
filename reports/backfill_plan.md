# Backfill Plan - Floor, Length, Genre Guard

Brief: `briefs/backfill_constraint.md`. Dry-run only, no API calls, no `--commit`. New code: `scripts/backfill_plan.py`. Rule implemented in `writer.py`/`config.py` (`MIN_CLUSTER_NATIVE=12`, `MAX_BACKFILL_SHARE=0.25`).

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

The shipped GUARD is naive: a backfill candidate matches if it carries the cluster's modal genre at all. Approved as an additional report-only comparison (2026-09-14): what a STRICT guard would have admitted instead, excluding labels that touch more than 50% of labeled real clusters in this pool - the same sensitivity check `scripts/genre_coverage.py` ran, since a label that common cannot be what discriminates a cluster's sound from its neighbours'. **Neither the length nor the shipped selection reads this column; it never feeds back into `writer.plan()`.**

Non-discriminative labels found (touch >50% of 32 labeled clusters): electronic, hip hop, pop, rhythm and blues, soul


| cluster | native | naive modal | naive admit | strict modal | strict admit |
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

| cluster | native | backfilled | final length | target | modal genre | short by | quota units |
|---|---|---|---|---|---|---|---|
| Joji | 13 | 4 | 17 | 17 | 'pop' | - | 901 |
| Don Toliver | 21 | 7 | 28 | 28 | 'hip hop' | - | 1,451 |
| T-Series / Pritam / Sony Music India | 22 | 1 | 23 | 29 | 'music of asia' | 6 | 1,201 |
| 21 Savage | 14 | 4 | 18 | 18 | 'hip hop' | - | 951 |
| The Weeknd | 20 | 6 | 26 | 26 | 'pop' | - | 1,351 |
| Metro Boomin | 26 | 8 | 34 | 34 | 'hip hop' | - | 1,751 |
| Future | 19 | 6 | 25 | 25 | 'hip hop' | - | 1,301 |
| Travis Scott | 20 | 6 | 26 | 26 | 'hip hop' | - | 1,351 |
| Drake | 19 | 6 | 25 | 25 | 'hip hop' | - | 1,301 |
| Lil Baby / Lil Peep / Chris Brown | 13 | 4 | 17 | 17 | 'hip hop' | - | 901 |

### Backfill provenance (native cluster -> admitting genre)


**Joji**

- Dave - Raindance (ft. Tems)  -  admitted by genre `pop`
- NEW DROP  -  admitted by genre `pop`
- Love Me  -  admitted by genre `pop`
- DUMBO  -  admitted by genre `pop`

**Don Toliver**

- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`
- 21 Savage - redrum (Official Music Video)  -  admitted by genre `hip hop`
- Love Me  -  admitted by genre `hip hop`
- DUMBO  -  admitted by genre `hip hop`
- 21 Savage & Metro Boomin - Glock In My Lap (Official Music Video)  -  admitted by genre `hip hop`
- The Neighbourhood - The Beach (Audio)  -  admitted by genre `hip hop`
- The Weeknd - Heartless (Official Video)  -  admitted by genre `hip hop`

**T-Series / Pritam / Sony Music India**

- Doja Cat - Streets (Official Video)  -  admitted by genre `music of asia`

**21 Savage**

- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`
- 5 TO 10  -  admitted by genre `hip hop`
- NEW DROP  -  admitted by genre `hip hop`
- Love Me  -  admitted by genre `hip hop`

**The Weeknd**

- Dave - Raindance (ft. Tems)  -  admitted by genre `pop`
- PIXELATED KISSES  -  admitted by genre `pop`
- NEW DROP  -  admitted by genre `pop`
- Love Me  -  admitted by genre `pop`
- DUMBO  -  admitted by genre `pop`
- The Neighbourhood - The Beach (Audio)  -  admitted by genre `pop`

**Metro Boomin**

- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`
- 5 TO 10  -  admitted by genre `hip hop`
- NEW DROP  -  admitted by genre `hip hop`
- 21 Savage - redrum (Official Music Video)  -  admitted by genre `hip hop`
- Love Me  -  admitted by genre `hip hop`
- DUMBO  -  admitted by genre `hip hop`
- 21 Savage & Metro Boomin - Glock In My Lap (Official Music Video)  -  admitted by genre `hip hop`
- The Neighbourhood - The Beach (Audio)  -  admitted by genre `hip hop`

**Future**

- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`
- 5 TO 10  -  admitted by genre `hip hop`
- NEW DROP  -  admitted by genre `hip hop`
- 21 Savage - redrum (Official Music Video)  -  admitted by genre `hip hop`
- Love Me  -  admitted by genre `hip hop`
- DUMBO  -  admitted by genre `hip hop`

**Travis Scott**

- 5 TO 10  -  admitted by genre `hip hop`
- NEW DROP  -  admitted by genre `hip hop`
- 21 Savage - redrum (Official Music Video)  -  admitted by genre `hip hop`
- Love Me  -  admitted by genre `hip hop`
- 21 Savage & Metro Boomin - Glock In My Lap (Official Music Video)  -  admitted by genre `hip hop`
- The Neighbourhood - The Beach (Audio)  -  admitted by genre `hip hop`

**Drake**

- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`
- 5 TO 10  -  admitted by genre `hip hop`
- NEW DROP  -  admitted by genre `hip hop`
- 21 Savage - redrum (Official Music Video)  -  admitted by genre `hip hop`
- Love Me  -  admitted by genre `hip hop`
- DUMBO  -  admitted by genre `hip hop`

**Lil Baby / Lil Peep / Chris Brown**

- Dave - Raindance (ft. Tems)  -  admitted by genre `hip hop`
- 5 TO 10  -  admitted by genre `hip hop`
- NEW DROP  -  admitted by genre `hip hop`
- 21 Savage - redrum (Official Music Video)  -  admitted by genre `hip hop`

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

- Total quota to write every qualifying cluster's playlist today: **12,460 units** (breakdown per cluster in the table above; each is `50 + 50*count + 1`).

- Daily cap: 8,000 units. **Exceeds the cap: yes.**

- Cheapest-first, 7 of 10 of these playlists could actually be written today without breaching the cap; the rest would need another day (or several - see CLAUDE.md's cost model: this can write roughly one such playlist a day).
