# Dormancy distribution inside the eligible pool

Brief: `briefs/reproducibility_and_distribution.md`, Part C. Read-only - no change to selection, scoring, ranking, clustering, or the write path. Follows on from `reports/recency_exclusion.md`, which tested survivorship at flat 30/60/90-day thresholds and found almost nothing past 30 days; this measures the distribution *inside* that range instead, since eligibility scales with play count rather than being a flat window.

- Base commit: `6e475d9e1b868cd96203951b4da5057ab580eaa1`
- `as_of` (pinned via `scripts/dormancy_signals.py`'s Part B parameter, reused here): `2026-09-20T07:25:12+00:00`
- `plays` row count: **40,619**
- Canonical (music-only) tracks in the current frame: **2,918**
- `RECENCY_HALF_LIFE_DAYS = 14`, `MIN_SCORE = 0.5`, `MIN_CLUSTER_NATIVE = 12`, `EXCLUDE_TOP = 50` (all unchanged, read not set).
- Method: a script under `scripts/`, run against the real database, calling `taste_engine.dormancy.build_frames`, `qualifying_clusters`, `canonical_key_of`, `plays_by_canonical_key`, and `plays_in_window` directly - no eligibility or recency logic reimplemented. Command: `scripts/run.sh scripts/dormancy_distribution.py --as-of 2026-09-20T07:25:12+00:00`.

## 1. Eligibility arithmetic - verified against `score.py`, not assumed

The brief's premise table, checked two ways: a closed form solved from `score.add_scores`'s actual formula (reading `config.RECENCY_HALF_LIFE_DAYS` = 14 and `config.MIN_SCORE` = 0.5 directly), and an empirical call to `add_scores` itself at the computed boundary and one day later, so a transcription error in the closed form would still be caught.

| plays | brief_claimed_days | computed_days | score.add_scores @ computed_days | score.add_scores @ +1 day |
|---|---|---|---|---|
| 1 | 6.6 | 6.6 | 0.5 | 0.4758 |
| 10 | 32.0 | 31.7 | 0.5 | 0.4758 |
| 30 | 39.0 | 38.9 | 0.5 | 0.4758 |

**Verified: the brief's table is correct.** At each computed boundary `add_scores` returns a score within 0.001 of `MIN_SCORE`, and one day later it has dropped below it. Proceeding with the measurement on this premise.

## 2. Qualifying clusters today

**8 clusters** clear `MIN_CLUSTER_NATIVE = 12` at this `as_of` (native-eligible, i.e. `score >= MIN_SCORE`, post global-top-50 exclusion - the same FLOOR test `writer.plan()` applies). Cluster ids and membership are not stable across runs (CLAUDE.md item 9) - reported as observed here, not reconciled against `reports/recency_exclusion.md`'s count from roughly an hour earlier the same day.

| cluster | name | eligible (score>=MIN_SCORE) | cluster_pool_size |
|---|---|---|---|
| 8 | Don Toliver | 17 | 71 |
| 12 | T-Series / Pritam / Sony Music India | 13 | 490 |
| 23 | The Weeknd | 19 | 75 |
| 24 | 21 Savage | 14 | 49 |
| 25 | Metro Boomin | 23 | 65 |
| 26 | Future | 16 | 84 |
| 32 | Travis Scott | 16 | 86 |
| 34 | Drake | 20 | 102 |

## 3. Histogram of `days_since_last_play` within the eligible pool

Every track with `score >= MIN_SCORE`, per qualifying cluster and in aggregate. `median_play_count` is the point: it tests whether the older buckets are in fact the heavily-played tracks the arithmetic in §1 predicts.

### 3a. Per cluster

| cluster | name | bucket | n_tracks | median_play_count |
|---|---|---|---|---|
| 8 | Don Toliver | 0-7 | 0 |  |
| 8 | Don Toliver | 7-14 | 14 | 11.5 |
| 8 | Don Toliver | 14-21 | 1 | 9.0 |
| 8 | Don Toliver | 21-28 | 1 | 14.0 |
| 8 | Don Toliver | 28-35 | 1 | 12.0 |
| 8 | Don Toliver | 35+ | 0 |  |
| 12 | T-Series / Pritam / Sony Music India | 0-7 | 0 |  |
| 12 | T-Series / Pritam / Sony Music India | 7-14 | 6 | 4.5 |
| 12 | T-Series / Pritam / Sony Music India | 14-21 | 3 | 3.0 |
| 12 | T-Series / Pritam / Sony Music India | 21-28 | 1 | 14.0 |
| 12 | T-Series / Pritam / Sony Music India | 28-35 | 3 | 14.0 |
| 12 | T-Series / Pritam / Sony Music India | 35+ | 0 |  |
| 23 | The Weeknd | 0-7 | 0 |  |
| 23 | The Weeknd | 7-14 | 17 | 10.0 |
| 23 | The Weeknd | 14-21 | 1 | 16.0 |
| 23 | The Weeknd | 21-28 | 1 | 13.0 |
| 23 | The Weeknd | 28-35 | 0 |  |
| 23 | The Weeknd | 35+ | 0 |  |
| 24 | 21 Savage | 0-7 | 0 |  |
| 24 | 21 Savage | 7-14 | 11 | 11.0 |
| 24 | 21 Savage | 14-21 | 2 | 15.0 |
| 24 | 21 Savage | 21-28 | 1 | 19.0 |
| 24 | 21 Savage | 28-35 | 0 |  |
| 24 | 21 Savage | 35+ | 0 |  |
| 25 | Metro Boomin | 0-7 | 0 |  |
| 25 | Metro Boomin | 7-14 | 19 | 12.0 |
| 25 | Metro Boomin | 14-21 | 1 | 6.0 |
| 25 | Metro Boomin | 21-28 | 3 | 14.0 |
| 25 | Metro Boomin | 28-35 | 0 |  |
| 25 | Metro Boomin | 35+ | 0 |  |
| 26 | Future | 0-7 | 0 |  |
| 26 | Future | 7-14 | 11 | 8.0 |
| 26 | Future | 14-21 | 2 | 18.0 |
| 26 | Future | 21-28 | 2 | 7.0 |
| 26 | Future | 28-35 | 1 | 19.0 |
| 26 | Future | 35+ | 0 |  |
| 32 | Travis Scott | 0-7 | 0 |  |
| 32 | Travis Scott | 7-14 | 12 | 10.0 |
| 32 | Travis Scott | 14-21 | 2 | 13.5 |
| 32 | Travis Scott | 21-28 | 1 | 17.0 |
| 32 | Travis Scott | 28-35 | 1 | 7.0 |
| 32 | Travis Scott | 35+ | 0 |  |
| 34 | Drake | 0-7 | 0 |  |
| 34 | Drake | 7-14 | 14 | 13.5 |
| 34 | Drake | 14-21 | 2 | 3.5 |
| 34 | Drake | 21-28 | 2 | 8.5 |
| 34 | Drake | 28-35 | 2 | 10.5 |
| 34 | Drake | 35+ | 0 |  |

### 3b. Aggregate, across all qualifying clusters

| bucket | n_tracks | median_play_count |
|---|---|---|
| 0-7 | 0 |  |
| 7-14 | 104 | 10.0 |
| 14-21 | 14 | 9.5 |
| 21-28 | 12 | 13.5 |
| 28-35 | 8 | 12.0 |
| 35+ | 0 |  |

**Observation, not tuned for:** the `0-7` bucket is empty in every qualifying cluster at this `as_of`. Plausible mechanism, not verified further here: a track played within the last week is also likely to be among the library's most-played, which is exactly what the global top-50 exclusion (`obvious`, applied before this pool is built) removes — so the freshest plays are disproportionately filtered out before `score >= MIN_SCORE` is even evaluated, leaving this pool's youngest survivors starting around a week old rather than at zero.

## 4. What currently ships: where the top-20-by-score tracks fall

Per cluster, the top 20 eligible tracks by `score` (descending) - what `--mode rediscover` actually ranks to the front today - bucketed the same way as §3.

| cluster | name | bucket | n_in_top_by_score |
|---|---|---|---|
| 8 | Don Toliver | 0-7 | 0 |
| 8 | Don Toliver | 7-14 | 14 |
| 8 | Don Toliver | 14-21 | 1 |
| 8 | Don Toliver | 21-28 | 1 |
| 8 | Don Toliver | 28-35 | 1 |
| 8 | Don Toliver | 35+ | 0 |
| 12 | T-Series / Pritam / Sony Music India | 0-7 | 0 |
| 12 | T-Series / Pritam / Sony Music India | 7-14 | 6 |
| 12 | T-Series / Pritam / Sony Music India | 14-21 | 3 |
| 12 | T-Series / Pritam / Sony Music India | 21-28 | 1 |
| 12 | T-Series / Pritam / Sony Music India | 28-35 | 3 |
| 12 | T-Series / Pritam / Sony Music India | 35+ | 0 |
| 23 | The Weeknd | 0-7 | 0 |
| 23 | The Weeknd | 7-14 | 17 |
| 23 | The Weeknd | 14-21 | 1 |
| 23 | The Weeknd | 21-28 | 1 |
| 23 | The Weeknd | 28-35 | 0 |
| 23 | The Weeknd | 35+ | 0 |
| 24 | 21 Savage | 0-7 | 0 |
| 24 | 21 Savage | 7-14 | 11 |
| 24 | 21 Savage | 14-21 | 2 |
| 24 | 21 Savage | 21-28 | 1 |
| 24 | 21 Savage | 28-35 | 0 |
| 24 | 21 Savage | 35+ | 0 |
| 25 | Metro Boomin | 0-7 | 0 |
| 25 | Metro Boomin | 7-14 | 16 |
| 25 | Metro Boomin | 14-21 | 1 |
| 25 | Metro Boomin | 21-28 | 3 |
| 25 | Metro Boomin | 28-35 | 0 |
| 25 | Metro Boomin | 35+ | 0 |
| 26 | Future | 0-7 | 0 |
| 26 | Future | 7-14 | 11 |
| 26 | Future | 14-21 | 2 |
| 26 | Future | 21-28 | 2 |
| 26 | Future | 28-35 | 1 |
| 26 | Future | 35+ | 0 |
| 32 | Travis Scott | 0-7 | 0 |
| 32 | Travis Scott | 7-14 | 12 |
| 32 | Travis Scott | 14-21 | 2 |
| 32 | Travis Scott | 21-28 | 1 |
| 32 | Travis Scott | 28-35 | 1 |
| 32 | Travis Scott | 35+ | 0 |
| 34 | Drake | 0-7 | 0 |
| 34 | Drake | 7-14 | 14 |
| 34 | Drake | 14-21 | 2 |
| 34 | Drake | 21-28 | 2 |
| 34 | Drake | 28-35 | 2 |
| 34 | Drake | 35+ | 0 |

## 5. What would ship if ranked by `days_since_last_play` descending instead

Same eligible pool, same top-20 cutoff, ranked by dormancy instead of score. Full candidate list per cluster, not just a bucket count, since the play-count column is what the whole question turns on.

**Cluster 8 — Don Toliver:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Call Back | 30.9 | 12 | 3 | 11 | 0.5542 |
| Tiramisu | 27.1 | 14 | 6 | 13 | 0.7077 |
| BANDIT | 14.9 | 9 | 5 | 8 | 1.0985 |
| Let Her Go (feat. James Blake) | 13.5 | 3 | 2 | 3 | 0.7091 |
| BACKSTREETS (FEAT. TEEZO TOUCHDOWN) | 13.5 | 5 | 2 | 5 | 0.9204 |
| Don Toliver - NO POLE \| REMAKE 7 UP DAMN | 13.4 | 4 | 2 | 4 | 0.827 |
| Don Toliver - Way Bigger [Official Music Video] | 12.8 | 9 | 4 | 9 | 1.2228 |
| Cardigan | 8.6 | 8 | 3 | 7 | 1.4361 |
| Flocky Flocky (feat. Travis Scott) | 8.5 | 3 | 1 | 3 | 0.9089 |
| DEEP IN THE WATER | 8.3 | 12 | 10 | 12 | 1.7028 |
| ATM | 8.3 | 13 | 5 | 12 | 1.7522 |
| Gemstone | 8.0 | 18 | 5 | 15 | 1.9836 |
| FWU | 7.9 | 11 | 3 | 10 | 1.68 |
| Excavator | 7.9 | 16 | 10 | 16 | 1.9158 |
| 5 TO 10 | 7.8 | 26 | 14 | 25 | 2.239 |
| Don Toliver - KRYPTONITE [Official Audio] | 7.1 | 18 | 13 | 18 | 2.0757 |
| NEW DROP | 7.0 | 22 | 7 | 20 | 2.215 |

**Cluster 12 — T-Series / Pritam / Sony Music India:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Jiyein Kyun | 31.9 | 12 | 5 | 11 | 0.5279 |
| Tum Ho | 28.4 | 15 | 9 | 14 | 0.6797 |
| Jee Le Zaraa | 28.3 | 14 | 5 | 14 | 0.6686 |
| Talwiinder - KAMMO JI (Prod. Parth Parashar) \| Punjabi Lofi | 26.0 | 14 | 13 | 14 | 0.7484 |
| "Senorita Zindagi Na Milegi Dobara" Full HD Video Song \| Farhan Akhtar, Hrithik Roshan, Abhay Deol | 20.0 | 3 | 2 | 3 | 0.5158 |
| Lyrical: Chammak Challo \| Ra One \| ShahRukh Khan \| Kareena Kapoor | 20.0 | 3 | 1 | 3 | 0.5159 |
| Kabira | 14.9 | 9 | 4 | 9 | 1.0993 |
| Kaisa Mai | 13.8 | 8 | 6 | 8 | 1.111 |
| Jo Tere Sang - Blood Money \| Kunal Khemu, Amrita Puri \| Mustafa Zahid \| Jeet Gannguli \| 4K | 8.4 | 5 | 1 | 5 | 1.1834 |
| 12 Saal \| Bilal Saeed \| Twelve \| Punjabi Songs \| Speed Records | 8.4 | 3 | 1 | 3 | 0.916 |
| Rockstar: Tum Ho (Lyrical Video) Song \| Ranbir Kapoor \| Nargis \| A R Rahman, Mohit Chauhan | 8.4 | 4 | 3 | 4 | 1.0642 |
| Pehle Bhi Main | 8.4 | 16 | 5 | 16 | 1.8735 |
| Pehli Nazar Mein Kaise Jaado Kar Diya \| Atif Aslam Hits \| Race I Akshaye, Bipasha & Saif Ali | 8.3 | 4 | 1 | 4 | 1.0646 |

**Cluster 23 — The Weeknd:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| The Weeknd - Less Than Zero (Official Lyric Video) | 26.9 | 13 | 3 | 10 | 0.6976 |
| The Weeknd - Save Your Tears (Official Music Video) | 19.8 | 16 | 4 | 10 | 1.0635 |
| Drive | 13.6 | 4 | 1 | 3 | 0.8217 |
| The Weeknd - In Your Eyes (Official Video) | 10.8 | 2 | 1 | 1 | 0.6421 |
| The Weeknd - Can't Feel My Face (Official Video) | 10.8 | 2 | 1 | 1 | 0.6422 |
| Blinding Lights | 10.8 | 10 | 1 | 5 | 1.402 |
| The Weeknd - I Feel It Coming ft. Daft Punk (Official Video) | 8.9 | 10 | 2 | 4 | 1.5442 |
| The Weeknd - Often (NSFW) (Official Video) | 8.7 | 20 | 4 | 17 | 1.9821 |
| The Weeknd - Starboy ft. Daft Punk (Official Video) ft. Daft Punk | 8.6 | 23 | 3 | 14 | 2.0764 |
| The Weeknd - The Morning | 8.5 | 2 | 2 | 2 | 0.7208 |
| The Weeknd - Party Monster (Official Video) | 8.5 | 7 | 2 | 6 | 1.3645 |
| The Weeknd - Die For You | 8.5 | 11 | 2 | 7 | 1.6308 |
| Cry For Me | 8.5 | 20 | 2 | 12 | 1.9986 |
| The Weeknd - Reminder (Official Video) | 8.4 | 13 | 2 | 7 | 1.7374 |
| NAV - Some Way ft. The Weeknd | 7.9 | 2 | 2 | 2 | 0.7438 |
| The Weeknd - The Hills | 7.8 | 20 | 5 | 16 | 2.0692 |
| The Weeknd, Ariana Grande - Die For You (Remix / Lyric Video) | 7.8 | 5 | 3 | 4 | 1.2177 |
| The Weeknd - King Of The Fall (Official Video) | 7.8 | 8 | 8 | 8 | 1.4936 |
| The Weeknd - Heartless (Official Video) | 7.8 | 23 | 4 | 19 | 2.1616 |

**Cluster 24 — 21 Savage:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| ball w/o you | 26.0 | 19 | 6 | 18 | 0.828 |
| 21 Savage, Summer Walker - prove it (Official Audio) | 20.0 | 20 | 7 | 20 | 1.1303 |
| red sky | 14.9 | 10 | 4 | 10 | 1.1448 |
| n.h.i.e. | 13.6 | 13 | 6 | 13 | 1.3473 |
| BETRAYED | 13.5 | 2 | 1 | 2 | 0.5619 |
| all of me | 11.1 | 21 | 9 | 21 | 1.7868 |
| Runnin | 9.9 | 7 | 1 | 6 | 1.2762 |
| a lot | 9.9 | 11 | 5 | 10 | 1.5252 |
| 21 Savage - all of me (Official Audio) | 8.8 | 8 | 6 | 8 | 1.4179 |
| 21 Savage x Metro Boomin - Runnin (Official Music Video) | 8.8 | 4 | 4 | 4 | 1.0387 |
| 21 Savage - Can't Leave Without It (Official Audio) | 8.7 | 7 | 1 | 7 | 1.3515 |
| 21 Savage - ball w/o you (Official Video) | 8.0 | 14 | 11 | 14 | 1.8192 |
| 21 Savage - redrum (Official Music Video) | 7.8 | 25 | 10 | 23 | 2.2114 |
| 21 Savage & Metro Boomin - Glock In My Lap (Official Music Video) | 7.7 | 23 | 5 | 22 | 2.1683 |

**Cluster 25 — Metro Boomin:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Trance | 26.0 | 14 | 4 | 12 | 0.7485 |
| Calling (Spider-Man: Across the Spider-Verse) | 24.0 | 14 | 1 | 8 | 0.826 |
| Overdue | 23.9 | 12 | 5 | 11 | 0.7844 |
| Space Cadet | 18.1 | 6 | 2 | 5 | 0.796 |
| Young Metro | 13.6 | 14 | 5 | 13 | 1.3844 |
| Raindrops (Insane) | 13.5 | 27 | 5 | 26 | 1.7047 |
| Umbrella | 13.5 | 10 | 3 | 10 | 1.2268 |
| On Time | 13.5 | 3 | 1 | 3 | 0.7119 |
| Future, Metro Boomin, Kendrick Lamar - Like That (Official Audio) | 11.1 | 2 | 1 | 1 | 0.6347 |
| Future, Metro Boomin, The Weeknd - Young Metro (Official Music Video) | 10.9 | 12 | 7 | 12 | 1.4928 |
| I Can't Save You (Interlude) | 9.9 | 23 | 15 | 23 | 1.9476 |
| Creepin' (Remix) (Official Video) | 8.8 | 12 | 12 | 12 | 1.6574 |
| Future, Metro Boomin, Travis Scott, Playboi Carti - Type Shit (Official Video) | 8.7 | 21 | 7 | 15 | 2.0116 |
| Future, Metro Boomin - Jealous (Official Audio) | 8.5 | 2 | 2 | 2 | 0.7197 |
| Around Me | 7.9 | 22 | 7 | 18 | 2.1206 |
| Metro Boomin, Don Toliver, Future - Too Many Nights (Official Video) | 7.9 | 9 | 3 | 7 | 1.5609 |
| Future, Metro Boomin, Travis Scott - Cinderella (Official Audio) | 7.8 | 17 | 8 | 16 | 1.9607 |
| Future, Metro Boomin - We Don't Trust You (Official Audio) | 7.8 | 7 | 3 | 6 | 1.4121 |
| Future, Metro Boomin - Mile High Memories (Official Audio) | 7.8 | 22 | 21 | 21 | 2.1313 |
| 10 Freaky Girls | 7.7 | 9 | 3 | 8 | 1.5699 |

**Cluster 26 — Future:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Cinderella | 28.8 | 19 | 6 | 17 | 0.7195 |
| Future - BACK TO THE BASICS (Official Music Video) | 27.0 | 7 | 6 | 7 | 0.5463 |
| TOLD MY | 23.9 | 7 | 5 | 7 | 0.6363 |
| Weight Up | 14.9 | 11 | 11 | 11 | 1.1855 |
| Always Be My Fault | 14.7 | 25 | 9 | 20 | 1.571 |
| Eye To Eye | 13.6 | 2 | 2 | 2 | 0.5608 |
| LOVE YOU BETTER | 13.5 | 16 | 7 | 14 | 1.4557 |
| Beat It | 12.8 | 5 | 3 | 5 | 0.9518 |
| 712PM | 11.0 | 8 | 2 | 6 | 1.2752 |
| Throw Away | 8.8 | 12 | 12 | 12 | 1.6575 |
| Too Comfortable | 8.7 | 12 | 4 | 11 | 1.6687 |
| Mask Off | 8.7 | 8 | 3 | 6 | 1.4316 |
| All to Myself | 8.6 | 20 | 3 | 14 | 1.9902 |
| Kick | 8.3 | 2 | 2 | 2 | 0.7267 |
| Drink N Dance | 8.0 | 6 | 3 | 4 | 1.311 |
| Future - Alice (Official Audio) | 7.8 | 2 | 2 | 2 | 0.7472 |

**Cluster 32 — Travis Scott:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Travis Scott - My Eyes - (Second Half Extended) | 28.2 | 7 | 3 | 6 | 0.5149 |
| SKELETONS | 24.0 | 17 | 5 | 14 | 0.8813 |
| ASTROTHUNDER | 19.9 | 11 | 4 | 10 | 0.9284 |
| Raindance | 14.9 | 16 | 4 | 16 | 1.3523 |
| DUMBO | 8.9 | 28 | 6 | 19 | 2.1712 |
| Drugs You Should Try It | 8.7 | 20 | 7 | 17 | 1.9771 |
| Travis Scott - Antidote (Official Video) | 8.7 | 2 | 1 | 1 | 0.7154 |
| Mamacita | 8.7 | 3 | 1 | 3 | 0.9029 |
| Travis Scott - goosebumps (Official Video) ft. Kendrick Lamar | 8.6 | 20 | 3 | 15 | 1.9872 |
| TOPIA TWINS | 8.5 | 8 | 3 | 7 | 1.4403 |
| 4X4 | 8.5 | 8 | 1 | 7 | 1.4408 |
| FE!N | 8.5 | 8 | 2 | 7 | 1.4447 |
| TIL FURTHER NOTICE | 8.3 | 15 | 5 | 12 | 1.8401 |
| YOSEMITE | 8.3 | 11 | 2 | 10 | 1.651 |
| CAN'T SAY | 7.8 | 9 | 4 | 8 | 1.567 |
| Dave - Raindance (ft. Tems) | 7.0 | 28 | 17 | 28 | 2.3771 |

**Cluster 34 — Drake:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| God's Plan | 28.3 | 9 | 3 | 8 | 0.567 |
| Passionfruit | 28.3 | 12 | 1 | 11 | 0.6329 |
| Pussy & Millions | 24.0 | 8 | 4 | 8 | 0.6707 |
| One Dance | 23.9 | 9 | 1 | 8 | 0.7043 |
| Drake - Laugh Now Cry Later (Official Music Video) ft. Lil Durk | 19.9 | 4 | 2 | 3 | 0.6002 |
| No Face | 14.9 | 3 | 2 | 3 | 0.6614 |
| Drake - Make Them Know | 13.5 | 20 | 9 | 20 | 1.5631 |
| Slap The City | 12.8 | 18 | 9 | 18 | 1.5641 |
| Drake - Plot Twist | 8.9 | 14 | 4 | 14 | 1.7438 |
| Drake, Qendresa - Slap The City | 8.9 | 12 | 11 | 12 | 1.6527 |
| Shabang | 8.7 | 5 | 3 | 5 | 1.1644 |
| Drake - Hotline Bling | 8.7 | 15 | 8 | 15 | 1.8025 |
| Rihanna - Work (Explicit) ft. Drake | 8.6 | 4 | 4 | 4 | 1.0493 |
| Way 2 Sexy | 8.6 | 2 | 1 | 1 | 0.7169 |
| Drake - Sticky (Official Music Video) | 8.6 | 2 | 1 | 2 | 0.7176 |
| Road Trips | 8.6 | 13 | 11 | 13 | 1.7274 |
| IDGAF | 8.5 | 10 | 4 | 9 | 1.5705 |
| Trust Issues | 8.5 | 16 | 2 | 13 | 1.8586 |
| B’s On The Table | 8.0 | 19 | 6 | 19 | 2.0178 |
| Drake - Burning Bridges | 7.8 | 20 | 20 | 20 | 2.0643 |

## 6. Overlap between §4 and §5, per cluster

| cluster | name | n_top_by_score | n_top_by_dormancy | overlap | differ |
|---|---|---|---|---|---|
| 8 | Don Toliver | 17 | 17 | 17 | 0 |
| 12 | T-Series / Pritam / Sony Music India | 13 | 13 | 13 | 0 |
| 23 | The Weeknd | 19 | 19 | 19 | 0 |
| 24 | 21 Savage | 14 | 14 | 14 | 0 |
| 25 | Metro Boomin | 20 | 20 | 17 | 6 |
| 26 | Future | 16 | 16 | 16 | 0 |
| 32 | Travis Scott | 16 | 16 | 16 | 0 |
| 34 | Drake | 20 | 20 | 20 | 0 |

## 7. Verdict — is there a population of heavily-played, 3-to-5-weeks-dormant tracks large enough to fill a playlist?

"3-to-5-weeks-dormant" = the `21-28` and `28-35` buckets. "Large enough to fill a playlist" means at least 20 tracks from that band alone (this report's own top-N convention, matching evaluate.py's k=20) - the raw counts above let you judge against any other size directly. A count below 20 is answered as **no**, however close: a playlist needs the full count, and `--cluster-name` ships one cluster at a time, so a shortfall in one cluster is not made up by a surplus in another.

- **Cluster 8 (Don Toliver): no** — 2 of 20 needed, in the 21-35 day range (21-28: n=1, median plays=14.0; 28-35: n=1, median plays=12.0).
- **Cluster 12 (T-Series / Pritam / Sony Music India): no** — 4 of 20 needed, in the 21-35 day range (21-28: n=1, median plays=14.0; 28-35: n=3, median plays=14.0).
- **Cluster 23 (The Weeknd): no** — 1 of 20 needed, in the 21-35 day range (21-28: n=1, median plays=13.0).
- **Cluster 24 (21 Savage): no** — 1 of 20 needed, in the 21-35 day range (21-28: n=1, median plays=19.0).
- **Cluster 25 (Metro Boomin): no** — 3 of 20 needed, in the 21-35 day range (21-28: n=3, median plays=14.0).
- **Cluster 26 (Future): no** — 3 of 20 needed, in the 21-35 day range (21-28: n=2, median plays=7.0; 28-35: n=1, median plays=19.0).
- **Cluster 32 (Travis Scott): no** — 2 of 20 needed, in the 21-35 day range (21-28: n=1, median plays=17.0; 28-35: n=1, median plays=7.0).
- **Cluster 34 (Drake): no** — 4 of 20 needed, in the 21-35 day range (21-28: n=2, median plays=8.5; 28-35: n=2, median plays=10.5).

**Aggregate: no.** No single cluster reaches 20 on its own — the largest is cluster 12 (T-Series / Pritam / Sony Music India) / cluster 34 (Drake) (tied) at 4. Summed across all 8 qualifying clusters, 20 of 138 eligible tracks fall in the 21-35 day range — noted for completeness, but this pooled figure does **not** answer "yes": it mixes tracks from unrelated artist clusters that no single `--cluster-name` write would ever combine, so it does not correspond to any playlist the product could actually ship.
