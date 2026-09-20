# Dormancy distribution inside the eligible pool

Brief: `briefs/reproducibility_and_distribution.md`, Part C. Read-only - no change to selection, scoring, ranking, clustering, or the write path. Follows on from `reports/recency_exclusion.md`, which tested survivorship at flat 30/60/90-day thresholds and found almost nothing past 30 days; this measures the distribution *inside* that range instead, since eligibility scales with play count rather than being a flat window.

- Base commit: `056ea09d6b208d4b9e729272f1492910b1e4f3f1`
- `as_of` (pinned via `scripts/dormancy_signals.py`'s Part B parameter, reused here): `2026-09-13T07:24:35+00:00`
- `plays` row count: **40,619**
- Canonical (music-only) tracks in the current frame: **2,918**
- `RECENCY_HALF_LIFE_DAYS = 14`, `MIN_SCORE = 0.5`, `MIN_CLUSTER_NATIVE = 12`, `EXCLUDE_TOP = 50` (all unchanged, read not set).
- Method: a script under `scripts/`, run against the real database, calling `taste_engine.dormancy.build_frames`, `qualifying_clusters`, `canonical_key_of`, `plays_by_canonical_key`, and `plays_in_window` directly - no eligibility or recency logic reimplemented. Command: `scripts/run.sh scripts/dormancy_distribution.py --as-of 2026-09-13T07:24:35+00:00`.

## 1. Eligibility arithmetic - verified against `score.py`, not assumed

The brief's premise table, checked two ways: a closed form solved from `score.add_scores`'s actual formula (reading `config.RECENCY_HALF_LIFE_DAYS` = 14 and `config.MIN_SCORE` = 0.5 directly), and an empirical call to `add_scores` itself at the computed boundary and one day later, so a transcription error in the closed form would still be caught.

| plays | brief_claimed_days | computed_days | score.add_scores @ computed_days | score.add_scores @ +1 day |
|---|---|---|---|---|
| 1 | 6.6 | 6.6 | 0.5 | 0.4758 |
| 10 | 32.0 | 31.7 | 0.5 | 0.4758 |
| 30 | 39.0 | 38.9 | 0.5 | 0.4758 |

**Verified: the brief's table is correct.** At each computed boundary `add_scores` returns a score within 0.001 of `MIN_SCORE`, and one day later it has dropped below it. Proceeding with the measurement on this premise.

## 2. Qualifying clusters today

**10 clusters** clear `MIN_CLUSTER_NATIVE = 12` at this `as_of` (native-eligible, i.e. `score >= MIN_SCORE`, post global-top-50 exclusion - the same FLOOR test `writer.plan()` applies). Cluster ids and membership are not stable across runs (CLAUDE.md item 9) - reported as observed here, not reconciled against `reports/recency_exclusion.md`'s count from roughly an hour earlier the same day.

| cluster | name | eligible (score>=MIN_SCORE) | cluster_pool_size |
|---|---|---|---|
| 5 | Joji | 13 | 26 |
| 8 | Don Toliver | 21 | 71 |
| 12 | T-Series / Pritam / Sony Music India | 22 | 490 |
| 23 | The Weeknd | 22 | 75 |
| 24 | 21 Savage | 14 | 49 |
| 25 | Metro Boomin | 26 | 65 |
| 26 | Future | 23 | 84 |
| 32 | Travis Scott | 21 | 86 |
| 34 | Drake | 23 | 102 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 13 | 44 |

## 3. Histogram of `days_since_last_play` within the eligible pool

Every track with `score >= MIN_SCORE`, per qualifying cluster and in aggregate. `median_play_count` is the point: it tests whether the older buckets are in fact the heavily-played tracks the arithmetic in §1 predicts.

### 3a. Per cluster

| cluster | name | bucket | n_tracks | median_play_count |
|---|---|---|---|---|
| 5 | Joji | 0-7 | 11 | 5.0 |
| 5 | Joji | 7-14 | 0 |  |
| 5 | Joji | 14-21 | 2 | 4.5 |
| 5 | Joji | 21-28 | 0 |  |
| 5 | Joji | 28-35 | 0 |  |
| 5 | Joji | 35+ | 0 |  |
| 8 | Don Toliver | 0-7 | 14 | 11.5 |
| 8 | Don Toliver | 7-14 | 1 | 9.0 |
| 8 | Don Toliver | 14-21 | 4 | 4.5 |
| 8 | Don Toliver | 21-28 | 2 | 10.0 |
| 8 | Don Toliver | 28-35 | 0 |  |
| 8 | Don Toliver | 35+ | 0 |  |
| 12 | T-Series / Pritam / Sony Music India | 0-7 | 7 | 4.0 |
| 12 | T-Series / Pritam / Sony Music India | 7-14 | 3 | 3.0 |
| 12 | T-Series / Pritam / Sony Music India | 14-21 | 5 | 4.0 |
| 12 | T-Series / Pritam / Sony Music India | 21-28 | 7 | 12.0 |
| 12 | T-Series / Pritam / Sony Music India | 28-35 | 0 |  |
| 12 | T-Series / Pritam / Sony Music India | 35+ | 0 |  |
| 23 | The Weeknd | 0-7 | 18 | 9.0 |
| 23 | The Weeknd | 7-14 | 1 | 16.0 |
| 23 | The Weeknd | 14-21 | 3 | 3.0 |
| 23 | The Weeknd | 21-28 | 0 |  |
| 23 | The Weeknd | 28-35 | 0 |  |
| 23 | The Weeknd | 35+ | 0 |  |
| 24 | 21 Savage | 0-7 | 11 | 11.0 |
| 24 | 21 Savage | 7-14 | 2 | 15.0 |
| 24 | 21 Savage | 14-21 | 1 | 19.0 |
| 24 | 21 Savage | 21-28 | 0 |  |
| 24 | 21 Savage | 28-35 | 0 |  |
| 24 | 21 Savage | 35+ | 0 |  |
| 25 | Metro Boomin | 0-7 | 20 | 11.0 |
| 25 | Metro Boomin | 7-14 | 1 | 6.0 |
| 25 | Metro Boomin | 14-21 | 3 | 14.0 |
| 25 | Metro Boomin | 21-28 | 2 | 7.0 |
| 25 | Metro Boomin | 28-35 | 0 |  |
| 25 | Metro Boomin | 35+ | 0 |  |
| 26 | Future | 0-7 | 12 | 7.0 |
| 26 | Future | 7-14 | 3 | 11.0 |
| 26 | Future | 14-21 | 5 | 5.0 |
| 26 | Future | 21-28 | 1 | 19.0 |
| 26 | Future | 28-35 | 2 | 14.5 |
| 26 | Future | 35+ | 0 |  |
| 32 | Travis Scott | 0-7 | 15 | 8.0 |
| 32 | Travis Scott | 7-14 | 2 | 13.5 |
| 32 | Travis Scott | 14-21 | 1 | 17.0 |
| 32 | Travis Scott | 21-28 | 2 | 6.5 |
| 32 | Travis Scott | 28-35 | 1 | 10.0 |
| 32 | Travis Scott | 35+ | 0 |  |
| 34 | Drake | 0-7 | 15 | 13.0 |
| 34 | Drake | 7-14 | 2 | 3.5 |
| 34 | Drake | 14-21 | 3 | 8.0 |
| 34 | Drake | 21-28 | 3 | 9.0 |
| 34 | Drake | 28-35 | 0 |  |
| 34 | Drake | 35+ | 0 |  |
| 36 | Lil Baby / Lil Peep / Chris Brown | 0-7 | 9 | 6.0 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 7-14 | 1 | 9.0 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 14-21 | 2 | 11.5 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 21-28 | 0 |  |
| 36 | Lil Baby / Lil Peep / Chris Brown | 28-35 | 1 | 11.0 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 35+ | 0 |  |

### 3b. Aggregate, across all qualifying clusters

| bucket | n_tracks | median_play_count |
|---|---|---|
| 0-7 | 132 | 8.0 |
| 7-14 | 16 | 9.0 |
| 14-21 | 29 | 5.0 |
| 21-28 | 17 | 9.0 |
| 28-35 | 4 | 11.0 |
| 35+ | 0 |  |

## 4. Top-20-by-score: where it falls, and how it compares to what actually ships

`top-20` here is **this report's own convention**, matching evaluate.py's k=20 - it is not necessarily what the pipeline ships. `dormancy.qualifying_clusters`'s own docstring is explicit that with `config.BACKFILL_ENABLED = False` (current default), `writer._select_with_backfill` returns the whole native-eligible block **unchanged and uncapped** - there is no top-N cut in production at all. So the top-20 cut below only *binds* (changes what's shown vs. the full eligible pool) in a cluster whose eligible count exceeds 20; everywhere else it is a no-op and "top-20-by-score" **is** what ships, in full.

**Cut binds** (eligible pool > 20, so ships in full but this report's top-20 table is a genuine truncation): Don Toliver (21 eligible), T-Series / Pritam / Sony Music India (22 eligible), The Weeknd (22 eligible), Metro Boomin (26 eligible), Future (23 eligible), Travis Scott (21 eligible), Drake (23 eligible).
**Cut is a no-op** (eligible pool <= 20, so this report's top-20 table already shows everything that ships): Joji (13 eligible), 21 Savage (14 eligible), Lil Baby / Lil Peep / Chris Brown (13 eligible).

| cluster | name | bucket | n_in_top_by_score |
|---|---|---|---|
| 5 | Joji | 0-7 | 11 |
| 5 | Joji | 7-14 | 0 |
| 5 | Joji | 14-21 | 2 |
| 5 | Joji | 21-28 | 0 |
| 5 | Joji | 28-35 | 0 |
| 5 | Joji | 35+ | 0 |
| 8 | Don Toliver | 0-7 | 14 |
| 8 | Don Toliver | 7-14 | 1 |
| 8 | Don Toliver | 14-21 | 3 |
| 8 | Don Toliver | 21-28 | 2 |
| 8 | Don Toliver | 28-35 | 0 |
| 8 | Don Toliver | 35+ | 0 |
| 12 | T-Series / Pritam / Sony Music India | 0-7 | 7 |
| 12 | T-Series / Pritam / Sony Music India | 7-14 | 3 |
| 12 | T-Series / Pritam / Sony Music India | 14-21 | 4 |
| 12 | T-Series / Pritam / Sony Music India | 21-28 | 6 |
| 12 | T-Series / Pritam / Sony Music India | 28-35 | 0 |
| 12 | T-Series / Pritam / Sony Music India | 35+ | 0 |
| 23 | The Weeknd | 0-7 | 18 |
| 23 | The Weeknd | 7-14 | 1 |
| 23 | The Weeknd | 14-21 | 1 |
| 23 | The Weeknd | 21-28 | 0 |
| 23 | The Weeknd | 28-35 | 0 |
| 23 | The Weeknd | 35+ | 0 |
| 24 | 21 Savage | 0-7 | 11 |
| 24 | 21 Savage | 7-14 | 2 |
| 24 | 21 Savage | 14-21 | 1 |
| 24 | 21 Savage | 21-28 | 0 |
| 24 | 21 Savage | 28-35 | 0 |
| 24 | 21 Savage | 35+ | 0 |
| 25 | Metro Boomin | 0-7 | 16 |
| 25 | Metro Boomin | 7-14 | 1 |
| 25 | Metro Boomin | 14-21 | 3 |
| 25 | Metro Boomin | 21-28 | 0 |
| 25 | Metro Boomin | 28-35 | 0 |
| 25 | Metro Boomin | 35+ | 0 |
| 26 | Future | 0-7 | 12 |
| 26 | Future | 7-14 | 3 |
| 26 | Future | 14-21 | 3 |
| 26 | Future | 21-28 | 1 |
| 26 | Future | 28-35 | 1 |
| 26 | Future | 35+ | 0 |
| 32 | Travis Scott | 0-7 | 14 |
| 32 | Travis Scott | 7-14 | 2 |
| 32 | Travis Scott | 14-21 | 1 |
| 32 | Travis Scott | 21-28 | 2 |
| 32 | Travis Scott | 28-35 | 1 |
| 32 | Travis Scott | 35+ | 0 |
| 34 | Drake | 0-7 | 14 |
| 34 | Drake | 7-14 | 2 |
| 34 | Drake | 14-21 | 2 |
| 34 | Drake | 21-28 | 2 |
| 34 | Drake | 28-35 | 0 |
| 34 | Drake | 35+ | 0 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 0-7 | 9 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 7-14 | 1 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 14-21 | 2 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 21-28 | 0 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 28-35 | 1 |
| 36 | Lil Baby / Lil Peep / Chris Brown | 35+ | 0 |

## 5. What would ship if ranked by `days_since_last_play` descending instead

Same eligible pool, same top-20 cutoff, ranked by dormancy instead of score. Full candidate list per cluster, not just a bucket count, since the play-count column is what the whole question turns on.

**Cluster 5 — Joji:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Demons | 19.0 | 3 | 2 | 3 | 0.5419 |
| SLOW DANCING IN THE DARK | 17.8 | 6 | 2 | 6 | 0.8066 |
| Fragments | 6.6 | 7 | 4 | 7 | 1.5024 |
| Die For You | 6.6 | 5 | 4 | 5 | 1.295 |
| YEAH RIGHT | 4.1 | 3 | 2 | 3 | 1.1298 |
| Joji & BENEE - Afterthought | 2.8 | 1 | 1 | 1 | 0.6035 |
| Joji & Diplo - Daylight (Official Music Video) | 2.8 | 1 | 1 | 1 | 0.6037 |
| Joji - If It Only Gets Better (Official Video) | 2.0 | 3 | 3 | 3 | 1.2529 |
| LOVE YOU LESS | 2.0 | 15 | 15 | 15 | 2.5064 |
| Joji - Last of a Dying Breed (Visualizer) | 0.0 | 7 | 7 | 7 | 2.0753 |
| Joji - Past Won't Leave My Bed (Official Video) | 0.0 | 4 | 4 | 4 | 1.6064 |
| PIXELATED KISSES | 0.0 | 23 | 17 | 23 | 3.1732 |
| NITROUS | 0.0 | 11 | 11 | 11 | 2.4824 |

**Cluster 8 — Don Toliver:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| TMU | 24.9 | 8 | 5 | 8 | 0.6394 |
| Call Back | 23.9 | 12 | 4 | 12 | 0.7837 |
| Tiramisu | 20.1 | 14 | 6 | 13 | 1.0009 |
| Embarrassed (feat. Travis Scott) | 20.1 | 5 | 2 | 5 | 0.6625 |
| What You Need | 17.0 | 4 | 2 | 4 | 0.6941 |
| GEEKED UP (FEAT. YEAT) | 17.0 | 3 | 1 | 3 | 0.5988 |
| BANDIT | 7.9 | 9 | 5 | 8 | 1.5535 |
| Let Her Go (feat. James Blake) | 6.5 | 3 | 2 | 3 | 1.0029 |
| BACKSTREETS (FEAT. TEEZO TOUCHDOWN) | 6.5 | 5 | 2 | 5 | 1.3017 |
| Don Toliver - NO POLE \| REMAKE 7 UP DAMN | 6.4 | 4 | 2 | 4 | 1.1695 |
| Don Toliver - Way Bigger [Official Music Video] | 5.8 | 9 | 4 | 9 | 1.7293 |
| Cardigan | 1.6 | 8 | 3 | 8 | 2.031 |
| Flocky Flocky (feat. Travis Scott) | 1.5 | 3 | 1 | 3 | 1.2855 |
| DEEP IN THE WATER | 1.3 | 12 | 10 | 12 | 2.4081 |
| ATM | 1.3 | 13 | 5 | 13 | 2.478 |
| Gemstone | 1.0 | 18 | 5 | 17 | 2.8052 |
| FWU | 0.9 | 11 | 4 | 11 | 2.3759 |
| Excavator | 0.9 | 16 | 11 | 16 | 2.7094 |
| 5 TO 10 | 0.8 | 26 | 14 | 26 | 3.1665 |
| Don Toliver - KRYPTONITE [Official Audio] | 0.1 | 18 | 13 | 18 | 2.9356 |

**Cluster 12 — T-Series / Pritam / Sony Music India:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Tere Liye | 27.9 | 12 | 2 | 12 | 0.6458 |
| Jiyein Kyun | 24.9 | 12 | 5 | 12 | 0.7466 |
| Tujhe Sochta Hoon | 22.9 | 7 | 4 | 7 | 0.6698 |
| Chahun Main Ya Naa | 22.9 | 5 | 2 | 5 | 0.5772 |
| Ishq Shava | 21.9 | 7 | 1 | 6 | 0.7043 |
| Tum Ho | 21.4 | 15 | 10 | 15 | 0.9612 |
| Jee Le Zaraa | 21.3 | 14 | 5 | 14 | 0.9455 |
| Saibo | 19.0 | 4 | 3 | 4 | 0.629 |
| Talwiinder - KAMMO JI (Prod. Parth Parashar) \| Punjabi Lofi | 19.0 | 14 | 13 | 14 | 1.0585 |
| Yeh Fitoor Mera | 19.0 | 3 | 2 | 3 | 0.5424 |
| Subhanallah | 16.9 | 4 | 2 | 3 | 0.6961 |
| Raabta | 16.9 | 3 | 2 | 3 | 0.6 |
| "Senorita Zindagi Na Milegi Dobara" Full HD Video Song \| Farhan Akhtar, Hrithik Roshan, Abhay Deol | 13.0 | 3 | 3 | 3 | 0.7295 |
| Lyrical: Chammak Challo \| Ra One \| ShahRukh Khan \| Kareena Kapoor | 13.0 | 3 | 2 | 3 | 0.7296 |
| Kabira | 7.9 | 9 | 4 | 9 | 1.5547 |
| Kaisa Mai | 6.8 | 8 | 6 | 8 | 1.5713 |
| Jo Tere Sang - Blood Money \| Kunal Khemu, Amrita Puri \| Mustafa Zahid \| Jeet Gannguli \| 4K | 1.4 | 5 | 1 | 5 | 1.6737 |
| Yaar Bathere (8K Video) Alfaaz Ft. Yo Yo Honey Singh \| Full Song \| Latest Punjabi Song 2026 | 1.4 | 1 | 1 | 1 | 0.6477 |
| 12 Saal \| Bilal Saeed \| Twelve \| Punjabi Songs \| Speed Records | 1.4 | 3 | 1 | 3 | 1.2955 |
| Rockstar: Tum Ho (Lyrical Video) Song \| Ranbir Kapoor \| Nargis \| A R Rahman, Mohit Chauhan | 1.4 | 4 | 3 | 4 | 1.505 |

**Cluster 23 — The Weeknd:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Swedish House Mafia and The Weeknd - Moth To A Flame (Official Video) | 19.9 | 3 | 2 | 3 | 0.5181 |
| The Weeknd - Less Than Zero (Official Lyric Video) | 19.9 | 13 | 5 | 12 | 0.9866 |
| Gesaffelstein & The Weeknd - Lost in the Fire (Official Video) | 19.8 | 3 | 1 | 2 | 0.5193 |
| The Weeknd - Save Your Tears (Official Music Video) | 12.8 | 16 | 5 | 10 | 1.5041 |
| Drive | 6.6 | 4 | 1 | 4 | 1.162 |
| The Weeknd - In Your Eyes (Official Video) | 3.8 | 2 | 1 | 2 | 0.9081 |
| The Weeknd - Can't Feel My Face (Official Video) | 3.8 | 2 | 1 | 1 | 0.9083 |
| Blinding Lights | 3.8 | 10 | 1 | 6 | 1.9827 |
| The Weeknd - I Feel It Coming ft. Daft Punk (Official Video) | 1.9 | 10 | 2 | 5 | 2.1839 |
| The Weeknd - Often (NSFW) (Official Video) | 1.7 | 20 | 4 | 18 | 2.8032 |
| The Weeknd - Starboy ft. Daft Punk (Official Video) ft. Daft Punk | 1.6 | 23 | 3 | 15 | 2.9366 |
| The Weeknd - Trust Issues (Remix) | 1.5 | 1 | 1 | 1 | 0.6431 |
| The Weeknd - The Morning | 1.5 | 2 | 2 | 2 | 1.0194 |
| The Weeknd - Party Monster (Official Video) | 1.5 | 7 | 2 | 6 | 1.9298 |
| The Weeknd - Die For You | 1.5 | 11 | 2 | 9 | 2.3064 |
| Cry For Me | 1.5 | 20 | 2 | 15 | 2.8266 |
| The Weeknd - Reminder (Official Video) | 1.4 | 13 | 2 | 9 | 2.4572 |
| NAV - Some Way ft. The Weeknd | 0.9 | 2 | 2 | 2 | 1.052 |
| The Weeknd - The Hills | 0.8 | 20 | 5 | 17 | 2.9263 |
| The Weeknd, Ariana Grande - Die For You (Remix / Lyric Video) | 0.8 | 5 | 3 | 4 | 1.7222 |

**Cluster 24 — 21 Savage:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| ball w/o you | 19.0 | 19 | 7 | 19 | 1.1709 |
| 21 Savage, Summer Walker - prove it (Official Audio) | 13.0 | 20 | 7 | 20 | 1.5985 |
| red sky | 7.9 | 10 | 4 | 10 | 1.619 |
| n.h.i.e. | 6.6 | 13 | 6 | 13 | 1.9054 |
| BETRAYED | 6.5 | 2 | 1 | 2 | 0.7947 |
| all of me | 4.1 | 21 | 9 | 21 | 2.527 |
| Runnin | 2.9 | 7 | 1 | 7 | 1.8048 |
| a lot | 2.9 | 11 | 5 | 11 | 2.157 |
| 21 Savage - all of me (Official Audio) | 1.8 | 8 | 6 | 8 | 2.0052 |
| 21 Savage x Metro Boomin - Runnin (Official Music Video) | 1.8 | 4 | 4 | 4 | 1.469 |
| 21 Savage - Can't Leave Without It (Official Audio) | 1.7 | 7 | 1 | 7 | 1.9113 |
| 21 Savage - ball w/o you (Official Video) | 1.0 | 14 | 11 | 14 | 2.5728 |
| 21 Savage - redrum (Official Music Video) | 0.8 | 25 | 10 | 24 | 3.1275 |
| 21 Savage & Metro Boomin - Glock In My Lap (Official Music Video) | 0.7 | 23 | 6 | 23 | 3.0665 |

**Cluster 25 — Metro Boomin:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Future - Cinderella (Visualizer) Feat. Metro Boomin & Travis Scott | 25.1 | 9 | 3 | 9 | 0.6647 |
| Metro Spider | 23.7 | 5 | 4 | 5 | 0.553 |
| Trance | 19.0 | 14 | 4 | 12 | 1.0585 |
| Calling (Spider-Man: Across the Spider-Verse) | 17.0 | 14 | 2 | 11 | 1.1682 |
| Overdue | 16.9 | 12 | 5 | 12 | 1.1093 |
| Space Cadet | 11.1 | 6 | 2 | 6 | 1.1257 |
| Young Metro | 6.6 | 14 | 5 | 13 | 1.9579 |
| Raindrops (Insane) | 6.5 | 27 | 5 | 26 | 2.4108 |
| Umbrella | 6.5 | 10 | 3 | 10 | 1.735 |
| On Time | 6.5 | 3 | 1 | 3 | 1.0069 |
| Future, Metro Boomin, Kendrick Lamar - Like That (Official Audio) | 4.1 | 2 | 1 | 1 | 0.8976 |
| Future, Metro Boomin, The Weeknd - Young Metro (Official Music Video) | 3.9 | 12 | 7 | 12 | 2.1112 |
| I Can't Save You (Interlude) | 2.9 | 23 | 15 | 23 | 2.7544 |
| Creepin' (Remix) (Official Video) | 1.8 | 12 | 12 | 12 | 2.344 |
| Future, Metro Boomin, Travis Scott, Playboi Carti - Type Shit (Official Video) | 1.7 | 21 | 8 | 17 | 2.845 |
| Future, Metro Boomin - Jealous (Official Audio) | 1.5 | 2 | 2 | 2 | 1.0179 |
| Around Me | 0.9 | 22 | 7 | 20 | 2.999 |
| Future - Throw Away (Lyrics) | 0.9 | 1 | 1 | 1 | 0.6636 |
| Metro Boomin, Don Toliver, Future - Too Many Nights (Official Video) | 0.9 | 9 | 3 | 7 | 2.2075 |
| Future, Metro Boomin, Travis Scott - Cinderella (Official Audio) | 0.8 | 17 | 9 | 17 | 2.773 |

**Cluster 26 — Future:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| We Still Don't Trust You | 35.0 | 18 | 5 | 18 | 0.5209 |
| Type Shit | 29.1 | 11 | 2 | 9 | 0.589 |
| Cinderella | 21.8 | 19 | 7 | 18 | 1.0176 |
| One Two | 20.1 | 3 | 3 | 3 | 0.5122 |
| If I Could | 20.1 | 3 | 3 | 3 | 0.5124 |
| Future - BACK TO THE BASICS (Official Music Video) | 20.0 | 7 | 6 | 7 | 0.7727 |
| Where Ya At | 18.8 | 5 | 3 | 5 | 0.7067 |
| TOLD MY | 16.9 | 7 | 5 | 7 | 0.8999 |
| Future - Trillionaire (Audio) ft. Youngboy Never Broke Again | 13.8 | 2 | 2 | 2 | 0.5552 |
| Weight Up | 7.9 | 11 | 11 | 11 | 1.6766 |
| Always Be My Fault | 7.7 | 25 | 9 | 22 | 2.2217 |
| Eye To Eye | 6.6 | 2 | 2 | 2 | 0.7931 |
| LOVE YOU BETTER | 6.5 | 16 | 7 | 15 | 2.0587 |
| Beat It | 5.8 | 5 | 3 | 5 | 1.3461 |
| 712PM | 4.0 | 8 | 3 | 7 | 1.8034 |
| Throw Away | 1.8 | 12 | 12 | 12 | 2.3442 |
| Too Comfortable | 1.7 | 12 | 4 | 12 | 2.36 |
| Mask Off | 1.7 | 8 | 3 | 6 | 2.0247 |
| All to Myself | 1.6 | 20 | 3 | 16 | 2.8146 |
| Gunna & Future - pushin P (feat. Young Thug) [Official Video] | 1.6 | 1 | 1 | 1 | 0.6412 |

**Cluster 32 — Travis Scott:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| sdp interlude | 28.8 | 10 | 2 | 9 | 0.5758 |
| SZA - Open Arms (Lyric Video) ft. Travis Scott | 21.3 | 6 | 6 | 6 | 0.679 |
| Travis Scott - My Eyes - (Second Half Extended) | 21.2 | 7 | 3 | 6 | 0.7281 |
| SKELETONS | 17.0 | 17 | 6 | 17 | 1.2464 |
| ASTROTHUNDER | 12.9 | 11 | 5 | 11 | 1.3129 |
| Raindance | 7.9 | 16 | 4 | 16 | 1.9125 |
| FLORIDA FLOW | 5.8 | 1 | 1 | 1 | 0.5204 |
| Travis Scott - STOP TRYING TO BE GOD (Official Video) | 3.8 | 1 | 1 | 1 | 0.5729 |
| DUMBO | 1.9 | 28 | 7 | 21 | 3.0707 |
| Drugs You Should Try It | 1.7 | 20 | 7 | 19 | 2.796 |
| NEMZZZ - GASS FEAT. TRAVIS SCOTT [OFFICIAL VIDEO] | 1.7 | 1 | 1 | 1 | 0.6377 |
| Travis Scott - Antidote (Official Video) | 1.7 | 2 | 1 | 2 | 1.0118 |
| Mamacita | 1.7 | 3 | 1 | 3 | 1.2769 |
| Travis Scott - goosebumps (Official Video) ft. Kendrick Lamar | 1.6 | 20 | 3 | 16 | 2.8104 |
| TOPIA TWINS | 1.5 | 8 | 3 | 7 | 2.0369 |
| 4X4 | 1.5 | 8 | 2 | 7 | 2.0377 |
| FE!N | 1.5 | 8 | 2 | 7 | 2.0432 |
| TIL FURTHER NOTICE | 1.3 | 15 | 5 | 13 | 2.6024 |
| YOSEMITE | 1.3 | 11 | 3 | 11 | 2.3349 |
| CAN'T SAY | 0.8 | 9 | 4 | 8 | 2.2161 |

**Cluster 34 — Drake:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| The Way Life Goes (feat. Oh Wonder) | 23.7 | 8 | 2 | 8 | 0.6781 |
| God's Plan | 21.3 | 9 | 3 | 9 | 0.8019 |
| Passionfruit | 21.3 | 12 | 1 | 12 | 0.8951 |
| Make Them Pay | 17.9 | 3 | 2 | 3 | 0.5728 |
| Pussy & Millions | 17.0 | 8 | 6 | 8 | 0.9485 |
| One Dance | 16.9 | 9 | 1 | 9 | 0.9961 |
| Drake - Laugh Now Cry Later (Official Music Video) ft. Lil Durk | 12.9 | 4 | 2 | 3 | 0.8488 |
| No Face | 7.9 | 3 | 2 | 3 | 0.9353 |
| Drake - Make Them Know | 6.5 | 20 | 13 | 20 | 2.2106 |
| Slap The City | 5.8 | 18 | 11 | 18 | 2.2121 |
| Drake - Plot Twist | 1.9 | 14 | 5 | 14 | 2.4662 |
| Drake, Qendresa - Slap The City | 1.9 | 12 | 11 | 12 | 2.3373 |
| Shabang | 1.7 | 5 | 3 | 5 | 1.6468 |
| Drake - Hotline Bling | 1.7 | 15 | 8 | 15 | 2.5492 |
| Rihanna - Work (Explicit) ft. Drake | 1.6 | 4 | 4 | 4 | 1.484 |
| Way 2 Sexy | 1.6 | 2 | 1 | 2 | 1.0139 |
| Drake - Sticky (Official Music Video) | 1.6 | 2 | 1 | 2 | 1.0149 |
| Lil Uzi Vert - Just Wanna Rock [Official Music Video] | 1.6 | 1 | 1 | 1 | 0.6405 |
| Road Trips | 1.6 | 13 | 11 | 13 | 2.4429 |
| IDGAF | 1.5 | 10 | 5 | 10 | 2.2211 |

**Cluster 36 — Lil Baby / Lil Peep / Chris Brown:**

| title | days_since_last_play | play_count | plays_last_90d | plays_last_180d | score |
|---|---|---|---|---|---|
| Chris Brown - Under The Influence (Official Video) | 28.8 | 11 | 5 | 11 | 0.5978 |
| Stuff | 17.0 | 19 | 6 | 19 | 1.2912 |
| Running This Shit | 16.9 | 4 | 2 | 4 | 0.6965 |
| ghost boy | 7.9 | 9 | 6 | 9 | 1.5536 |
| Go Crazy | 6.6 | 4 | 4 | 4 | 1.162 |
| right here | 6.6 | 6 | 4 | 6 | 1.4058 |
| ghost girl | 6.6 | 4 | 4 | 4 | 1.1628 |
| Never Recover | 6.5 | 4 | 2 | 4 | 1.1643 |
| Freestyle | 5.8 | 15 | 4 | 15 | 2.0825 |
| Lil Peep - Save That Shit (Official Video) | 1.8 | 6 | 6 | 6 | 1.7815 |
| haunt u | 1.3 | 7 | 7 | 7 | 1.9474 |
| Idol | 1.0 | 1 | 1 | 1 | 0.6603 |
| Love Me | 0.9 | 25 | 5 | 25 | 3.1207 |

## 6. Overlap between §4 and §5, per cluster

`differ` is the symmetric difference (tracks unique to one side plus tracks unique to the other), not a fraction of 20. `forced_identical = True` means the eligible pool itself has 20 or fewer tracks, so top-by-score and top-by-dormancy are **the same set by construction** - `overlap`/`differ` in that row measures nothing about ranking, only that there was no ranking decision to make. Only a `forced_identical = False` row is a genuine comparison of the two rankings.

| cluster | name | eligible_pool | n_top_by_score | n_top_by_dormancy | overlap | differ | forced_identical |
|---|---|---|---|---|---|---|---|
| 5 | Joji | 13 | 13 | 13 | 13 | 0 | True |
| 8 | Don Toliver | 21 | 20 | 20 | 19 | 2 | False |
| 12 | T-Series / Pritam / Sony Music India | 22 | 20 | 20 | 18 | 4 | False |
| 23 | The Weeknd | 22 | 20 | 20 | 18 | 4 | False |
| 24 | 21 Savage | 14 | 14 | 14 | 14 | 0 | True |
| 25 | Metro Boomin | 26 | 20 | 20 | 14 | 12 | False |
| 26 | Future | 23 | 20 | 20 | 17 | 6 | False |
| 32 | Travis Scott | 21 | 20 | 20 | 19 | 2 | False |
| 34 | Drake | 23 | 20 | 20 | 17 | 6 | False |
| 36 | Lil Baby / Lil Peep / Chris Brown | 13 | 13 | 13 | 13 | 0 | True |

**7 of 10 clusters have a genuine ranking decision** (Don Toliver, T-Series / Pritam / Sony Music India, The Weeknd, Metro Boomin, Future, Travis Scott, Drake); the other 3 are identical by construction (§4).

## 7. Verdict — is there a population of heavily-played, 3-to-5-weeks-dormant tracks large enough to fill a playlist?

"3-to-5-weeks-dormant" = the `21-28` and `28-35` buckets. "Large enough to fill a playlist" means at least 20 tracks from that band alone (this report's own top-N convention, matching evaluate.py's k=20 - not the same bar as `MIN_CLUSTER_NATIVE = 12`, which only gates whether a cluster ships at all, per §2). The raw counts above let you judge against any other size directly. A count below 20 is answered as **no**, however close: a playlist needs the full count, and `--cluster-name` ships one cluster at a time, so a shortfall in one cluster is not made up by a surplus in another.

- **Cluster 5 (Joji): no** — 0 of 20 needed, in the 21-35 day range (no tracks in either bucket).
- **Cluster 8 (Don Toliver): no** — 2 of 20 needed, in the 21-35 day range (21-28: n=2, median plays=10.0).
- **Cluster 12 (T-Series / Pritam / Sony Music India): no** — 7 of 20 needed, in the 21-35 day range (21-28: n=7, median plays=12.0).
- **Cluster 23 (The Weeknd): no** — 0 of 20 needed, in the 21-35 day range (no tracks in either bucket).
- **Cluster 24 (21 Savage): no** — 0 of 20 needed, in the 21-35 day range (no tracks in either bucket).
- **Cluster 25 (Metro Boomin): no** — 2 of 20 needed, in the 21-35 day range (21-28: n=2, median plays=7.0).
- **Cluster 26 (Future): no** — 3 of 20 needed, in the 21-35 day range (21-28: n=1, median plays=19.0; 28-35: n=2, median plays=14.5).
- **Cluster 32 (Travis Scott): no** — 3 of 20 needed, in the 21-35 day range (21-28: n=2, median plays=6.5; 28-35: n=1, median plays=10.0).
- **Cluster 34 (Drake): no** — 3 of 20 needed, in the 21-35 day range (21-28: n=3, median plays=9.0).
- **Cluster 36 (Lil Baby / Lil Peep / Chris Brown): no** — 1 of 20 needed, in the 21-35 day range (28-35: n=1, median plays=11.0).

**Aggregate: no.** No single cluster reaches 20 on its own — the largest is cluster 12 (T-Series / Pritam / Sony Music India) at 7. Summed across all 10 qualifying clusters, 21 of 198 eligible tracks fall in the 21-35 day range — noted for completeness, but this pooled figure does **not** answer "yes": it mixes tracks from unrelated artist clusters that no single `--cluster-name` write would ever combine, so it does not correspond to any playlist the product could actually ship.
