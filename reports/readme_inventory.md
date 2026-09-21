# README figure inventory — re-derived

**Brief:** `briefs/readme_final.md`, Part 0.
**Branch:** `readme-final`. **Base commit:** `7d24dbd` (tree clean except untracked `briefs/`).
**Anchor confirmed (0a):** `SELECT MAX(watched_at) FROM plays` = `2026-09-13T07:24:35+00:00`, matching the brief's expected value exactly.

This re-derives a prior read-only inventory (chat-only, not saved) as a committed
artifact. Every figure below was re-executed or re-read fresh in this session
against the current repo state (README.md is byte-identical to `origin/main`,
confirmed by diff), not carried over from memory. Labels: **[executed]** = run
in this session (DB query, script, or grep against a file). **[source-read]**
= read from an existing report at HEAD. **[inferred]** = arithmetic or
reasoning over the above, not a new artifact.

Status values: **CURRENT** (matches its source at HEAD) / **STALE** (source
now gives a different value, both shown) / **UNTRACEABLE** (no repo artifact
produces it) / **INCONSISTENT** (README asserts two different values for the
same quantity, neither wrong on its own).

---

## Regime issues (flagged separately, per 0b)

Two regime mixes run through the whole document and are called out once here
rather than repeated in every row that touches them:

- **`STRICT_MUSIC` on vs off.** Default is `True` (`config.py:95`). Toggling
  it live `[executed]`:

  | `STRICT_MUSIC` | raw tracks | raw plays | canonical songs | canonical plays |
  |---|---:|---:|---:|---:|
  | `False` | 3,570 | 10,539 | 3,119 | 10,539 |
  | `True` (default) | 3,365 | 10,319 | **2,918** | **10,319** |

  §3's table publishes **2,918** (strict-on) beside **10,539** (strict-on's
  play count is 10,319) — a same-table regime mix. See row-level detail below.

- **362 vs 363 days.** Two distinct spans, both real, both published without
  being labelled as different quantities:
  - `plays` table span (all watch history): **363 days, 15h** `[executed]` —
    matches `tests/test_dataset_facts.py:26` (`EXPECTED_SPAN_DAYS = 363`).
  - Canonical **music-track** span: **362 days, 21h** `[source-read,
    dormancy_probe.md:217]` — max(last_played) − min(first_played) over
    canonical tracks only.
  README uses 363 at lines 189, 208, 474 and 362 at lines 5, 54, 1111. Both
  are internally correct for what they measure; the README does not label
  which is which.

- **Raw vs canonical frame** in the scoring paragraph (§6, ~lines 628–632):
  three of five figures are computed on the pre-collapse (raw) frame, not the
  canonical one used everywhere else in §3/§6. Detailed in the §6 row group.

---

## Figure table, by README section

### Opening (lines 1–61)

| figure | line | source | status |
|---|---|---|---|
| 40,619 plays | 4 | `plays` COUNT(*) = 40,619 `[executed]` | CURRENT |
| 2,918 canonical tracks | 5 | `scored_tracks(canonical=True)` = 2,918 `[executed]` | CURRENT |
| 362 days | 5 | `dormancy_probe.md:217` `[source-read]` | CURRENT (see regime note above) |
| nDCG@20 0.3312 / 0.1382 baseline / 139.7% / 3 splits held out / p=0.125 | 9–12 | `rediscovery_headline.md:116-119,410` `[source-read]` | CURRENT |
| six successive corrections | 13 | §1.7 table, 6 rows `[source-read]` | CURRENT |
| **Five separate directions** | 18 | see Part 3-equivalent note below | **STALE** — `recency_exclusion.md:72` self-declares itself "the sixth direction closed by measurement"; `dormancy_distribution.md:465` carries an independent, uncounted seventh verdict ("Aggregate: no"). Current count is 6 by the repo's own label, 7 if `dormancy_distribution.md` counts separately. **C3 already adds a 6th entry (recency exclusion) — confirm the resulting count says "six," not "five," once C3 lands.** |
| pop covers 2,176 of 2,918, ~75% | 34–35 | `genre_coverage.md:53` = 2,176 `[source-read]`; 2,176/2,918 = 74.6% `[inferred]` | CURRENT |
| only 3 of 37 clusters usable genre signal | 36–37 | `genre_coverage.md:197` `[source-read]` | CURRENT |
| Last.fm 640 of 2,918 (21.9%) | 41 | `lastfm_coverage.md:265` `[source-read]` | CURRENT |
| Joji 7 of 11 forgotten; mixed 3 of 13 | 47–48 | `listening_test.md:39-40` `[source-read]` | CURRENT |
| 362 days; 61.8% one lifetime play | 54–55 | `dormancy_probe.md:217,235` `[source-read]`; re-derived 1,802/2,918 = 61.8% `[executed]` | CURRENT |
| `BACKFILL_ENABLED` is `False` | 58–59 | `config.py:110` `[executed]` | CURRENT |

### §1 — how the number was wrong (lines 81–370)

| figure | line | source | status |
|---|---|---|---|
| +28.7% 4/4, +7.8% 3/4, +1.9% 2/3, +140% 3/3 | 85–88 | historical, §1.7 | CURRENT as history |
| baseline nDCG drifted **0.270 → 0.339** | 102 | no hit in `reports/` or `scripts/` `[executed grep]` | **UNTRACEABLE** — 0c: PAST-STATE (describes the pre-fix tie-break leak; the code path that produced it, unsorted `head(50)`, no longer exists) |
| **+22.1% on the dev splits** | 133 | no hit anywhere; `rediscovery_headline.md:99-105` dev sweep at the chosen half-life (14d) gives **+18.3%** (0.3786→0.4481) `[source-read]` | **STALE** — current value +18.3% |
| leaked-into-raw-pool table (35/34/34/36/37 of 50) | 158–162 | `canonical_impact.py` fresh run, §2 `[executed]`: current leaked_raw = **36/35/36/37/38** | **PAST-STATE** — same family, off by 1–2 per split |
| 70% of favourites surviving | 164 | same run: mean leaked = 36.4/50 = **72.8%** (the script's own text rounds this to "73%") | **PAST-STATE** — same family, current value ~73% not 70% |
| baseline nDCG falls 0.29–0.46 → 0.11–0.17 | 167 | `canonical_impact.py` fresh run, §3 "REDISCOVERY, per split, raw vs canonical" `[executed]`: raw_base range **0.2024–0.4628**, canon_base range **0.1074–0.4303** | **PAST-STATE** — same canonicalisation-drift family as line 170; neither range matches, joins the §1.3 group covered by C2 |
| **3,570 tracks → 3,143 songs (427 collapsed, 12%)** | 170 | see "the 3,143 chain" below — reconstructed under the best-matching hypothesis (artist-key-only collapse, `STRICT_MUSIC=False`) gives 3,570→**3,136** (434 collapsed, 12.2%), not an exact match `[executed]` | **PAST-STATE** — close but not exact under the closest-matching methodology; canonicalisation (`normalise_title`, `strip_artist_from_title`) has been bugfixed twice since (2026-09-16, 2026-09-19), so the original count is not exactly reproducible even under the right methodology. Covered by C2's new §1 disclaimer. |
| 359 songs had >1 upload | 171 | same family; artist-key-only `STRICT_MUSIC=False` gives **364** today, not 359 `[executed]` | **PAST-STATE**, same reasoning as the row above |
| 102 other distinct-song pairs | 177 | no committed report (CLAUDE.md says "+103 more", a different count) | **PAST-STATE** — describes the original title-only-vs-artist-key over-merge comparison; not a quantity any current script restates, and the canonicalisation it exercises has since changed |
| 7 remaining cross-artist groups | 184–185 | no committed report | **PAST-STATE**, same reasoning |
| §1.4 split table (train days / music tracks / reachable truth, lines 194–204) | 194–204 | no committed report; README self-caveats "measured before the non-music filter" | **UNTRACEABLE** — 0c: **PAST-STATE** (pre-dates the strict filter by the README's own admission; CLAUDE.md open item 4 confirms this table was never re-run) |
| 363-day watch history | 208 | `plays` span 363d 15h `[executed]` | CURRENT |
| 5.6% upper bound — **176 of 3,143** | 220 | denominator: PAST-STATE, see "3,143 chain"; the count (176) needs a fixed, freshly-run `contamination.py` (currently crashes — Part A) | **PAST-STATE (denominator) / not yet regenerable (count)** — the whole §1.5 sentence sits inside §1, covered by C2 |
| 127 flagged by title/duration; categoryId alone = **121** | 223–233 | `scripts/contamination.py` stdout only, currently crashes | **PAST-STATE-adjacent** — same family as above; count not regenerable until Part A's crash fix, and even then would be a *new* current count, not a reproduction of the original (canonicalisation has moved) |
| STRICT_MUSIC removes **202 songs / 220 plays**, mean **1.1** | 243–244 | canonical-level removal: 3,119→2,918 = **201** songs, 220 plays exactly, mean 1.09 `[executed]` | **PAST-STATE** — same canonicalisation-drift reasoning as the 3,143 family; 201 is very close (off by one) but reflects today's code, not the code that produced "202". Covered by C2. |
| filter removes songs: 202 (**6.4%**) | 253 | 201/3,119 = 6.4% `[executed]` | **PAST-STATE**, same reasoning; 6.4% itself is unaffected by the ±1 count |
| pool shrinks −123/−136/−163, 3/3 | 254 | `scripts/verify_strict_null.py` — ran fresh this session (10 min, per CLAUDE.md's estimate) `[executed]`: current values **−122/−135/−162**, still 3/3 | **PAST-STATE** — off by exactly one per split, same small systematic drift as the rest of this family (canonicalisation fixes since original measurement); joins the §1 group covered by C2 |
| best rank a removed song reaches **209** of ~2,000 | 254 | same fresh run `[executed]`: current value **172** | **PAST-STATE** — same family, larger drift than the ±1 pattern elsewhere but same root cause (canonicalisation + the same removed-song population shifting) |
| **"14 further merges"; "2 of 14 (14%)" false-merge** | 269, 279 | `scripts/duration_merge_report.py` — ran fresh `[executed]`, exit 0, own header: "canonical songs, artist rule only 2,935 \| + duration pass 2,918 \| **additional merges: 17**" | **STALE — clean, confident swap.** Current value: **17 further merges**, false-merge rate **2 of 17 (11.8%)**. The two named false merges (Demons, FLEX UP) are unchanged and still the only two; three additional *good* merges now fire (21 Savage "all of me", "prove it", "n.h.i.e.", plus "12 Saal", "#hoyoverse", "One Two Three Four", "Kalank Title Track" — 17 total vs the original 14) because upstream canonicalisation fixes (§6 provenance) now feed the duration pass more matching title pairs. Direction of the conclusion is unaffected — the false-merge rate is *better*, not worse (11.8% vs 14%), so keeping 3s tolerance is if anything a stronger case, not a weaker one. This does not trip Part B3's verdict gate. |
| Raabta 4:04/4:04/4:46; Demons 2:58/2:57; FLEX UP 2:48/2:51 | 273–282 | same script, same run | **CURRENT** — every one of these specific examples reproduces exactly: Raabta (Arijit Singh - Topic 4:04, Pritam - Topic 4:04, Jokhay - Topic 4:46, "distinct songs after merge: 2"), Demons (Imagine Dragons - Topic 2:58, Joji - Topic 2:57), FLEX UP (Lil Uzi Vert - Topic 2:48, Lil Yachty - Topic 2:51 — titled "Flex Up" on the Yachty upload) `[executed]` |
| "lose six of the twelve good merges" at 0s tolerance | 282–283 | counted directly from `duration_merge_report.py`'s 17-row spread list `[executed]`: 7 of 17 merges have 0s spread, none are the 2 false ones, so 15 good merges total, 7 kept at 0-tolerance | **STALE** — current value: would lose **eight of the fifteen** good merges (not six of twelve); matches the 14→17 total-merge swap above |
| 35 genre tags | 287 | counted distinct raw `topicCategories` labels across the canonical frame `[executed]`: **36**. (The tidied — generic-label-dropped — count is 32; "35" reads as the raw count, matching the sentence's own subject, "topicCategories returns 35 distinct tags") | **STALE** — current value **36**, off by one, not 35 |
| §1.7 six-row lift table (…, **+139.7%**) | 328–333 | row 6 = `rediscovery_headline.md:118` `[source-read]`; rows 1–5 historical | CURRENT |
| 0.3343 → 0.3312; 0.1466 → 0.1382 | 341–342 | 0.3312/0.1382 confirmed current; the "before" pair (0.3343/0.1466) is not in any committed report | **UNTRACEABLE (before-values only)** — 0c: **PAST-STATE** (describes the pipeline before the feature-clause fix, which no longer exists to re-measure) |
| 289-test suite | 360 | historical (2026-09-13) | CURRENT as history |

### §2 — the result (lines 372–462)

| figure | line | source | status |
|---|---|---|---|
| per-split 0.135/0.223/+64%; 0.107/0.392/+265%; 0.172/0.379/+121% | 385–387 | `rediscovery_headline.md:110-113`: 0.1354/0.2227/+64.48%; 0.1074/0.3916/+264.62%; 0.1718/0.3794/**+120.84%** `[source-read]` | CURRENT (all three rows) |
| mean 0.138 / 0.331 / +140% / 3/3 | 388 | `rediscovery_headline.md:116-119` `[source-read]` | CURRENT |
| p = 0.125, five splits minimum | 390–393 | `rediscovery_headline.md:394-396` `[source-read]` | CURRENT |
| **"the honest summary: a +121% lift winning every held-out split"** | 399 | string `121` does not appear anywhere in `rediscovery_headline.md` `[executed grep]`. 1.2084 (+120.84%, rounds to +121%) is the **2026-08-01 split alone**; the three-split aggregate is +139.7% (line 388, nine lines above) | **STALE** — presents one split's lift as the reported aggregate |
| recall@20 capped ~4.4%; 20 picks vs **296–496** reachable | 403–404 | `rediscovery_headline.md:86-92` reachable at the 5 usable splits: 232, 313, 358, 212, **365** `[source-read]` | **STALE** — current reachable range is 212–365; 20/365 = 5.5% (not 4.4%) |
| every strategy scores 1.00 on replay | 409 | tried both readings `[executed]`, cheap (single `evaluate()` call, seconds not minutes): `test_days=105` at k=20 gives precision@20 **0.60–0.75** across strategies; at defaults (k=50) gives precision@50 **0.60–0.68** | **PAST-STATE** — does not reproduce under either reading; describes the evaluation before `--test-end` replaced the relative `test_days` window (README's own §2 text: "pinned to an absolute window end... so the boundary no longer depends on when the command runs" — a fix this figure predates) |
| nDCG@50 0.551 vs 0.542; Spearman 0.358 vs 0.430 | 423–424 | `eval_invariance_window.txt:39-40` = 0.5506/0.5421, 0.3583/0.4300 `[source-read]` | CURRENT |
| +1.6% edge | 426 | `eval_invariance_window.txt:44` `[source-read]` | CURRENT |
| 2,066 train tracks (5,465 plays); 867 test (1,613 plays) | 429–430 | `eval_invariance_window.txt:33-34` `[source-read]` | CURRENT |
| Spearman 0.430 vs 0.358 | 441 | same as above | CURRENT |
| **369 of 970 test songs** never seen in training | 449 | no hit in `reports/` or `scripts/` `[executed grep]` | **UNTRACEABLE** — 0c: NEEDS-NEW-CODE (requires re-running `evaluate.split_frames` at a specific split and diffing train/test vocabularies — not a simple read-only query, and out of scope per the brief's "rediscovery headline computation... out of scope") |

### §3 — the data (lines 464–491) — all `[executed]` against `data/taste.db`, read-only

| figure | line | measured | status |
|---|---|---|---|
| Watch-history plays 40,619 | 472 | 40,619 | CURRENT |
| Unique videos 30,440 | 473 | 30,440 | CURRENT |
| 2025-09-14 → 2026-09-13, 363 days | 474 | exact; span 363d 15h | CURRENT |
| Plays with no channel 6,649 | 475 | 6,649 | CURRENT |
| Playlists 58 | 476 | 58 | CURRENT |
| Playlists with exported track list 48 | 477 | 48 distinct `playlist_name` | CURRENT |
| Playlist track rows 11,475 (8,457 unique) | 478 | 11,475 / 8,457 | CURRENT |
| YT Music library songs 239 | 479 | 239 | CURRENT |
| Music tracks, heuristics only 2,858 (9.4%) | 480 | 2,858; /30,440 = 9.4% | CURRENT |
| heuristics ∪ categoryId 3,570 (11.7%) | 481 | 3,563 resolved + 7 unresolved = 3,570; 11.7% | CURRENT |
| **Canonical songs 2,918** | 482 | 2,918 at `STRICT_MUSIC=True` | CURRENT |
| **Music plays 10,539 (25.9%)** | 483 | **10,319** at `STRICT_MUSIC=True` (25.4%); 10,539 is the `STRICT_MUSIC=False` value | **STALE — regime mismatch** (this is 0d's flagged item; confirmed). The row above it (2,918) is strict-on; this row is strict-off. Consistent pair is 2,918 / 10,319. |
| 3,570 / not 17,138 / not 30,440; 88% not music | 485–486 | 3,570 and 30,440 confirmed; 17,138 not independently checked | CURRENT |

### §4 — what is broken (lines 493–530) — all `[executed]`

| figure | line | measured | status |
|---|---|---|---|
| 41.9 MB, ~41,500 cells | 497–498 | raw export is gitignored, not re-checked | not verifiable from this repo state; not flagged as a defect (external file) |
| 6,649 plays have no channel | 506 | 6,649 | CURRENT |
| 53 of 58 on two days — 2026-03-11 (39), 2026-03-17 (14) | 515–516 | 39 + 14 = 53 exactly | CURRENT |
| `updated_at` collapses on export date (56 of 58) | 517–518 | 56 on 2026-09-13 | CURRENT |
| Only 2 carry TuneMyMusic description; the only two created on export date | 519–520 | exactly 2, both created 2026-09-13T07:00 | CURRENT |
| **"one title x3, five more x2"** | 521–522 | one x3 ("Jim"), **eight** x2 | **STALE** — current value is one ×3, **eight** ×2. Self-falsifying against README's own arithmetic: 58 − 2 − 5 = 51 ≠ 48 (line 524's own figure), but 58 − 2 − 8 = 48 ✓ |
| 430 duplicate track rows | 523 | 11,475 − 11,045 distinct = 430 | CURRENT |
| 58 playlists → 48 exported track files | 524 | 58 / 48 | CURRENT |

### §5 — music classification (lines 532–610) — all `[executed]`, scoped to `found=1` (n=28,133) unless noted

| figure | line | measured | status |
|---|---|---|---|
| `- Topic` 2,336 / 6,387 | 540 | exact (all 30,440) | CURRENT |
| VEVO 371 / 2,225 | 541 | exact | CURRENT |
| music.youtube.com 2,472 / 7,342 | 542 | exact | CURRENT |
| in playlist 845 / 3,549 | 543 | exact | CURRENT |
| in library 134 / 1,055 | 544 | exact | CURRENT |
| Union 2,858 / 9,134 | 545 | exact | CURRENT |
| parts sum to 6,158 | 547 | 2,336+371+2,472+845+134 = 6,158 | CURRENT |
| 30,440 resolved in 609 calls; 28,133 resolved, 2,307 misses | 556–558 | exact | CURRENT |
| Heuristic union 2,858 / categoryId 3,510 | 570–571 | exact | CURRENT |
| Agreement 97.3%, precision 98.1%, recall 79.7% | 572–574 | exact, scoped to `found=1` | CURRENT |
| Confusion matrix 2,798 / 53 / 712 / 24,570 | 578–579 | exact, scoped to `found=1` | CURRENT |
| Final training set 3,570 = 2,858 ∪ 3,510 ∪ 7 | 604–605 | 3,563 + 7 = 3,570 | CURRENT |

*Note (unchanged from prior inventory): §5's table is scoped to the 28,133 resolved videos; §3's is over all 30,440. The README never states this scoping; the numbers are correct but the scope is undocumented. Not a defect requiring a number swap — flagged, not fixed, per C7 (a wording fix is out of scope under NUMBERS-ONLY).*

### §6 — model and clustering (lines 612–748)

| figure | line | source | status |
|---|---|---|---|
| **"60% of tracks played exactly once"** | 628 | canonical 61.8%, raw 61.6% `[executed]` | **STALE** — swapped to **61.6% (raw)**, not 61.8% (canonical): the paragraph's other 3 figures (115 plays / 5.75× / 1.57×) are already correct only on the raw frame, so the fix keeps the whole paragraph on one frame per C7's explicit instruction, rather than fixing this one figure to canonical and leaving the other three internally inconsistent with it |
| **"top 20 account for 9.6% of plays"** | 629 | canonical 11.7%, raw 9.0% `[executed]` | **STALE** — swapped to **9.0% (raw)**, same reasoning as the row above |
| MY EYES at **115 plays**; **5.75×** raw; **1.57×** after log1p | 630–632 | raw frame: 115 plays, 115/20 = 5.75, log1p(115)/log1p(20) = 1.561 `[executed]`; canonical frame: 136 plays, 6.80×, 1.616× | **CURRENT on the raw frame** — this paragraph is written on the pre-collapse frame while §3/§6 elsewhere use canonical. See regime note. |
| **"half_life … 30 days on canonical songs"** | 634 | `rediscovery_headline.md:106,154` "chosen half-life: **14** days"; `config.py:63` `RECENCY_HALF_LIFE_DAYS = 14.0` `[executed]` | **STALE** |
| raw 384-d → 2 clusters, 77.6% largest | 652 | no committed report | **UNTRACEABLE** — 0c: PAST-STATE (this was the pre-PCA diagnostic run, kept only as a negative comparison; not part of the current pipeline's regular output) |
| **PCA 20-d → 38 clusters, 15.6% largest** | 653 | `genre_coverage.md`, `backfill_plan.md:191`, `readme_audit.md:257` all say **37** real clusters on the current 2,918-canonical-track frame `[source-read]` — but no report states a current largest-cluster % for that 37-cluster result, and a fresh ad hoc clustering run gave 16.8%, not 15.6% (different run, parameters not verified identical) `[executed]` | **Not swapped, on reflection** — flagged STALE on first pass for the cluster-count alone, but "15.6%" is this same table cell's paired figure from the *same* old run as line 655's 39.6%/2,858. Swapping only "38→37" while leaving "15.6%" would assert an unverified pairing (37 clusters *with* 15.6% largest) that is likely false. Left untouched alongside line 655, both listed as one PAST-STATE unit in Part C's execution — this row's status here undersold the interdependency on first pass; the actual README edit correctly treats it as PAST-STATE, not STALE. |
| **"38 clusters over 2,858 tracks, 39.6% outliers"** | 655 | 2,858 is the heuristics-only (pre-canonical, pre-STRICT_MUSIC) video count (§3); the current pipeline clusters 2,918 canonical tracks | **STALE / UNTRACEABLE mix** — 0c: **PAST-STATE**. "2,858" ties this whole sentence to a clustering run on a frame the current pipeline no longer produces (canonical collapse post-dates it). 37 is the current cluster count (traceable); 15.6%/39.6% are not stated for either frame in any committed report, and re-deriving them precisely for the *current* 2,918/37-cluster result would require re-running the embedding+HDBSCAN pipeline (existing code, but not a "read-only query" in Part B's sense) — listed, not regenerated. |
| ground truth 480 tracks after dropping 3 | 666 | `embedding_modes_pool480.md:9,17` `[source-read]` | CURRENT |
| ARI table (9 cells: title_artist/title_genre/title × exclude/single_cluster/singletons) | 673–675 | `embedding_modes_pool480.md:27-35` — all nine cells exact `[source-read]` | CURRENT |
| exclude denominators 261/197/340 of 480 | 681 | `embedding_modes_pool480.md:27,30,33` `[source-read]` | CURRENT |
| beats title_genre by 0.1601, 16.85× noise band | 691–692 | `embedding_modes_pool480.md:48,75` `[source-read]` | CURRENT |
| title_genre beats title by 0.0606, 0.55× | 694–695 | `embedding_modes_pool480.md:56,75` `[source-read]` | CURRENT |
| provenance commit `4edbc6fa…`, pool 480, min_samples 2, 2026-09-19 | 707–708 | `embedding_modes_pool480.md:7,9` `[source-read]` | CURRENT |
| 48 playlists in ground truth | 700 | 48 distinct playlist names `[executed]` | CURRENT |
| **"35 distinct tags; 95% of tracks carry at least one"** | 718–720 | `genre_coverage.md:41` (Number 1: "As-delivered … 2,808 / 2,918 (**96.2%**) canonical tracks carry >=1 label") `[source-read]`. A direct ad hoc re-check on untidied topic labels gave 98.3% `[executed]` — different methodology (no `tidy_genres` filtering of generic labels), not used as the reference value. | **STALE** — current value is 96.2% (genre_coverage.md, tidied methodology, matching README's own stated pipeline); 35 tags not independently re-counted |
| `artist_from_channel` NaN: 9 of 2,918, 2 of 9 changed, ARI −0.003 | 735–738 | `embedding_modes_remeasured.md` `[source-read]` | CURRENT |
| **"a second, currently unfixed instance … in `normalise_title`"** | 740–741 | CLAUDE.md State (2026-09-16): "`embed.normalise_title`'s NaN guard — the same bug class... fixed" `[source-read]`; `reports/normalise_title_fix.md` exists as the fix record | **STALE prose** — this is the brief's named C6 exception; fixed 2026-09-16, five days before this session |

### §7 — quota (lines 750–778)

| figure | line | source | status |
|---|---|---|---|
| 10,000 units/day; videos.list 1, insert 50, search 100 | 752–760 | `quota.py` constants `[source-read]` | CURRENT |
| 100-track write = 5,000 units minimum | 762 | 100 × 50 `[inferred]` | CURRENT |
| Default cap 8,000 | 776 | `config.py` `[source-read]` | CURRENT |

### §8 — write-back (lines 780–999)

| figure | line | source | status |
|---|---|---|---|
| **`tests/test_writer.py`, 76 tests** | 782 | `grep -c "def test_" tests/test_writer.py` = **85** `[executed]` | **STALE** |
| 45 tracks written, `playlistItems.list` confirming 45 | 786–787 | `written_playlists` has 7 rows `[executed]`; historical claim | CURRENT as history |
| 50-track playlist = 50 + 50×50 + 1 = 2,551 | 800 | arithmetic `[inferred]`; `readme_audit.md:190` confirms formula still correct | CURRENT |
| 409 on second track; 13/3/2 of 45; 150 units rollback | 829–836 | historical; CLAUDE.md State | CURRENT as history |
| 5 attempts, 1s→16s; up to 250 units/track | 838–846 | `writer.py:_call_with_retry` `[source-read]` | CURRENT |
| **"23 of 50 below score 0.5 (small) vs 5 of 50 (large)"** | 887–888 | `readme_audit.md:178-179` flags this as measuring a superseded top-N-by-score padding mechanism, already replaced by FLOOR/LENGTH/GUARD/RANK/CEILING | **STALE / PAST-STATE** — already flagged in `readme_audit.md` 2026-09-14; describes a mechanism the current writer no longer uses |
| 37 distinct songs → 48 | 892 | attempted read-only reconstruction: T-Series cluster (490 tracks), top-50-by-score raw tracks → 47 distinct canonical songs (not 37); top-50 canonical → 50 by construction (not 48) `[executed]` | **PAST-STATE** — doesn't reproduce even approximately under the obvious reading, and sits in the same paragraph/mechanism as line 887-888's "23 of 50 / 5 of 50," which `readme_audit.md:178-179` already identifies as the superseded top-N-by-score padding writer (pre-FLOOR/LENGTH/GUARD/RANK/CEILING). Almost certainly describes that same retired mechanism. |
| topicCategories: pop 2,176 of 2,918, hip hop 1,695 | 900–902 | `genre_coverage.md:53-54` `[source-read]` | CURRENT |
| FLOOR=12, MAX_BACKFILL_SHARE=0.25, MAX_BACKFILL_DISTANCE=1.0 | 911–934 | `config.py:133,134,174` `[executed]` | CURRENT |
| 27 of 37 real clusters below floor | 914 | `backfill_plan.md:191` `[source-read]` | CURRENT (out of scope: `backfill_plan.md` regeneration excluded) |
| Joji worked example (12/16/pop/4 admitted/851 units) | 948–956 | `backfill_plan.md:65,82,113-116` `[source-read]` | CURRENT (regeneration out of scope) |
| T-Series worked example (21/28/music of asia/1.1166/0 backfilled/short 7/1,101 units) | 969–980 | `backfill_plan.md:20,67,84,105` `[source-read]` | CURRENT (regeneration out of scope) |
| ten distinct tracks across fifty-two slots; six hip-hop playlists | 982 | `readme_audit.md:155` — current report gives per-track distances, "no longer a like-for-like table" | **STALE / PAST-STATE** narrative, already flagged 2026-09-14 |
| **"five of the ten qualifying clusters have no discriminative genre"** | 984 | not restated in `backfill_plan.md` at HEAD `[executed grep]` | **UNTRACEABLE at HEAD** — 0c: out of scope (`backfill_plan.md` regeneration explicitly excluded by the brief) |

*Note: every `backfill_plan.md`-sourced figure above carries `gate_drift_audit.md`'s own caveat (row 7): ANCHOR-DEPENDENT, INDETERMINATE — the script prints no `as_of`, and its historical anchor is not recoverable. These are graded CURRENT against the report (the stated grading axis), with this caveat carried forward, not re-litigated, since `backfill_plan.md` regeneration is explicitly out of scope.*

### §9–§11 + Known limitations (lines 1001–1117)

| figure | line | source | status |
|---|---|---|---|
| **tests/ 337 tests** | 1022, 1044 | `pytest --collect-only -q` = **536 collected** `[executed]` | **STALE** |
| 609 units, needs YT_API_KEY | 1035 | confirmed §5 | CURRENT |
| n=3, p=0.125, Apr–Aug clear reachable≥20 | 1102–1104 | `rediscovery_headline.md:86-92,199` `[source-read]` | CURRENT |
| Spotify audio-features closed since Nov 2024 | 1108–1110 | external claim, not repo-verifiable | not gradable from this repo |
| 362-day listening history | 1111 | see regime note | CURRENT (music-track span) |
| 14-day half-life, 0.5 floor → ~6.6 days | 1113–1115 | `dormancy_signals.md:188` derives this exactly; `config.py:63,132` `[executed]` | CURRENT |

---

## The "3,143 chain" (0d item, expanded)

README publishes **3,143** in two places (lines 170, 220) as a canonical-song
denominator. Measured fresh this session `[executed]`, at the **full**
production collapse (`canonical.collapse()`, artist-key + duration-merge —
what `score.scored_tracks(canonical=True)` and everywhere else in the repo
means by "canonical"):

| regime | raw tracks | canonical songs (full collapse) |
|---|---:|---:|
| `STRICT_MUSIC=False` | 3,570 | 3,119 |
| `STRICT_MUSIC=True` (default) | 3,365 | **2,918** |

3,143 matches neither. Its only literal source in the repo is a **hardcoded
string** in `scripts/contamination.py:178`:

```python
print("5. CONTAMINATION ESTIMATE OVER ALL 3,143 SONGS")
```

Chasing where 3,143 actually came from (not just where it's hardcoded today)
turned up a second, more interesting mechanism:

**`canonical.py` has two different collapse functions, and they disagree.**
`collapse()` (the production path, used by `scored_tracks(canonical=True)`)
calls `_canonicalise()`, which runs the artist-key merge **and then** the
duration-merge second pass (§1.6). `collapse_report()` — called directly by
`scripts/canonical_impact.py`'s "1. HOW MUCH COLLAPSES" section — calls
`add_canonical_key()` only, **skipping the duration-merge pass entirely**.
Run fresh this session `[executed]`:

| regime | raw | artist-key-only (`collapse_report`) | full collapse (`collapse`) |
|---|---:|---:|---:|
| `STRICT_MUSIC=False` | 3,570 | 3,136 (434 collapsed, 12.2%, 364 multi-upload, largest 5) | 3,119 |
| `STRICT_MUSIC=True` | 3,365 | 2,935 (430 collapsed, 12.8%, 360 multi-upload, largest 5) | 2,918 |

`duration_merge_report.py`'s own header confirms this split independently:
`canonical songs, artist rule only 2,935 | + duration pass 2,918 | additional
merges 17` `[executed]`.

README's own text structure explains why this matters: §1.3 (line 170)
describes the artist-keyed collapse **before** §1.6 introduces the
duration-merge pass as an addition on top of it. So "3,570 → 3,143" was very
likely measured via the `collapse_report()`-style artist-key-only path, at
`STRICT_MUSIC=False` (matching "3,570" exactly) — not the full production
path. Reconstructing that exact combination today gives **3,136**, not 3,143
(427 vs 434 collapsed, 359 vs 364 multi-upload — close, same order, same
largest-group value of 5, but not exact). The gap is best explained by
canonicalisation itself having been bugfixed twice since (`normalise_title`
NaN guard, 2026-09-16; `strip_artist_from_title` artist-side guard,
2026-09-19) — each concrete evidence of the same "measured before a
since-fixed bug" pattern the brief's PAST-STATE category describes, not
merely of a stale hardcoded label.

**This resolves CLAUDE.md's own standing note** ("A same-day brief stated
40,617 plays / 30,438 videos / 3,143 canonical songs... The third is off by
225 and unreconciled"): 225 = 3,143 − 2,918 (a strict-regime *and*
methodology difference, not unexplained drift), and the residual gap against
the closest same-methodology reconstruction (3,143 vs 3,136 = 7) is
attributable to the two documented canonicalisation bugfixes since. Not fully
exact-reconciled to the single track, but no longer "unreconciled" in the
sense CLAUDE.md meant it — the mechanism is now known on both axes (regime
and methodology), not just regime.

**A second, independent mechanism, found while verifying Part A's fix:**
`contamination.py`'s "5. CONTAMINATION ESTIMATE" section calls
`scored_tracks(conn)` with no override, so it inherits `config.STRICT_MUSIC`'s
**default (`True`)** — meaning today it measures residual contamination
*after* strict filtering has already removed the worst offenders, not the
pre-filter contamination that `STRICT_MUSIC` exists to address. Run today
(fixed, STRICT_MUSIC=True, the shipped default): **58 of 2,918 flagged
(2.0%)**, categoryId-alone = **3**. Run with `config.STRICT_MUSIC` toggled to
`False` (a read-only check, not a script change) `[executed]`: **175 of
3,119 flagged (5.6%)**, categoryId-alone = **120** — matching README's "176"
and "121" almost exactly (off by one each), and 5.6% matches the README's
stated upper bound exactly. This confirms the 176/121/5.6% family was
originally measured under `STRICT_MUSIC=False` (or before the toggle
existed), describing the contamination problem *before* the filter that
now addresses it — not a mismeasurement, a different, no-longer-default
regime. **Not fixed**: toggling `STRICT_MUSIC` inside `contamination.py`,
even only for this one internal measurement, is exactly the kind of change
the brief's Out of Scope section names explicitly ("Any change to ...
STRICT_MUSIC ... or the noise convention"), so it is reported here and left
alone. This closes the loop on why §1.5's contamination figures are
PAST-STATE rather than a simple stale-value swap: two independent causes
(canonicalisation drift *and* a regime default that flipped underneath the
script), both now identified, neither in scope to correct via a number swap.

**Consequence for Part B/C:** `canonical_impact.py`'s own "canonical songs"
figure (2,935 today) is **not** the same quantity as the "2,918" used
everywhere else in this repo (§3, `dormancy_probe.md`, `genre_coverage.md`,
`score.scored_tracks()` itself) — it measures collapse *before* the
duration-merge pass, silently. Part B1 will still run `canonical_impact.py`
and save its stdout verbatim, per the brief — that stdout will legitimately
say "2,935," and it is not wrong for what it measures, only easy to
misread next to the rest of the repo's "2,918." Flagged here so it is not
mistaken for a fresh candidate value to swap into README's "2,918" (§3) or
used to "fix" line 170 — line 170 is PAST-STATE and stays untouched under
C2, not swapped to 2,935 or 3,136. This asymmetry — `collapse_report()`
silently omitting the duration-merge pass that `collapse()` includes — is
itself worth Udit's attention as a latent inconsistency in `canonical.py`,
but fixing it is a behaviour change to core pipeline code, not a "hardcoded
literal in a print banner," and is out of this brief's scope (Part A is
scoped to `contamination.py`'s literal only). Reported, not fixed.

**Unplanned finding, not in the brief:** `scripts/contamination.py` currently
**crashes** (`KeyError: 'duration'`) when run against the current codebase,
independent of the hardcoded-denominator defect. `score.scored_tracks()` now
returns its own `duration` column (added for `canonical.py`'s duration-merge
pass, §1.6), and `contamination.py`'s merge with `video_metadata` (which also
selects `duration`, without suffix handling) collides into `duration_x`/
`duration_y`. Line 73's bare `songs["duration"]` then raises. Confirmed by
direct reproduction:

```
scored_tracks() columns include: ..., 'duration', ...
merge with meta (also selecting 'duration') -> columns become
  ['duration_x', 'duration_y']
songs["duration"]  # KeyError
```

This blocks Part B1's requirement to run `contamination.py` and save its
stdout — it cannot currently produce any output at all, including the
already-hardcoded-denominator figures ("176 of 3,143", "121 categoryId
alone", "202 songs / 220 plays"). Per the standing rule ("report
discrepancies; do not work around them"), this is reported here rather than
silently patched. **Handled in Part A** (see that section's commit) as a
second, clearly-separated fix in the same file Part A already touches — not
a scope expansion of the brief's stated hardcoded-denominator task, but a
necessary precondition for it to run at all.

---

## 0c — classification of every UNTRACEABLE row

Two figures moved out of this table since the first pass: "14 further
merges / 2 of 14" and the Raabta/Demons/FLEX UP examples both turned out to
have an exact, currently-running source (`duration_merge_report.py`) once
actually executed — reclassified to STALE (with a swap-in value) and CURRENT
respectively, in the main table above. Five figures moved **into**
PAST-STATE that a first pass had marked CURRENT-DATA (359, 102, 7 cross-artist
groups, 176-of-3,143's denominator, 127/121, 202/220/1.1) once the
`collapse()`-vs-`collapse_report()` divergence explained *why* they don't
reproduce, not just *that* they don't.

| figure | class | reason |
|---|---|---|
| 0.270 → 0.339 (half-life leak demo) | PAST-STATE | describes the pre-fix tie-break bug; code path no longer exists |
| leaked-into-raw-pool table (35/34/34/36/37) | PAST-STATE | `canonical_impact.py`, run to completion: current 36/35/36/37/38 |
| 70% of favourites surviving | PAST-STATE | same run: current ~73% |
| baseline nDCG 0.29–0.46 → 0.11–0.17 | PAST-STATE | same run: current 0.2024–0.4628 / 0.1074–0.4303 |
| 3,570→3,143 (427 collapsed, 12%) | PAST-STATE | closest reconstruction (artist-key-only, `STRICT_MUSIC=False`) gives 3,136, not exact — canonicalisation bugfixed twice since |
| 359 songs had >1 upload | PAST-STATE | same family as above |
| 102 distinct-song pairs (title-only over-merge) | PAST-STATE | same family |
| 7 remaining cross-artist groups | PAST-STATE | same family |
| §1.4 split table (train days/tracks/reachable, pre-strict) | PAST-STATE | README's own caveat: measured before the non-music filter existed |
| 176 of 3,143 (denominator) | PAST-STATE | same 3,143-chain family |
| 127 flagged / 121 categoryId-alone (count) | PAST-STATE | same family; not regenerable to the *original* number even once Part A's crash fix lands, since canonicalisation has moved |
| 202 songs / 220 plays / 1.1 mean removed by STRICT_MUSIC | PAST-STATE | same family; current re-derivation gives 201 (off by one), not an exact reproduction |
| 202 (6.4%) | PAST-STATE | same figure as above, second occurrence |
| pool shrinks −123/−136/−163, 3/3 | PAST-STATE | `verify_strict_null.py`, run to completion: current −122/−135/−162, off by one per split |
| best rank a removed song reaches 209 | PAST-STATE | same run: current value 172 |
| 0.3343→0.3312 / 0.1466→0.1382 ("before" values) | PAST-STATE | pre-feature-clause-fix pipeline state, no longer producible |
| every replay strategy scores 1.00 | PAST-STATE | tried both readings, cheap to check: neither reproduces (0.60–0.75 at k=20, 0.60–0.68 at k=50 defaults) |
| 369 of 970 unseen test songs | NEEDS-NEW-CODE | requires re-running `evaluate.split_frames` and diffing train/test vocabularies; eval internals are out of scope |
| raw 384-d clustering (2 clusters, 77.6% largest) | PAST-STATE | one-off diagnostic run kept as a negative comparison, not part of regular pipeline output |
| "38 clusters / 2,858 tracks / 15.6% / 39.6%" | PAST-STATE | tied to the pre-canonical-collapse frame (2,858); current frame is 2,918 canonical tracks, 37 clusters |
| 37 distinct songs → 48 (a specific write) | PAST-STATE | attempted reconstruction gives 47/50, not 37/48; almost certainly the same superseded top-N-by-score mechanism as its neighbouring paragraph |
| "five of ten clusters, no discriminative genre" | out of scope | source is `backfill_plan.md`, whose regeneration the brief explicitly excludes |

**0c counts:**

| class | count |
|---|---:|
| CURRENT-DATA | 0 |
| PAST-STATE | 20 |
| NEEDS-NEW-CODE | 1 |
| out of scope (not classified) | 1 |
| **Total UNTRACEABLE rows** | **22** |

Every figure that first looked like a cheap CURRENT-DATA regeneration turned
out, once actually run rather than assumed, to be PAST-STATE — none
reproduced its original value under current code. This is not a coincidence
worth downplaying: it is the same pattern the project's own CLAUDE.md
already documents happening to entire published tables (item 6, "a second
table shared item 4's cause," now stale a third time) — a defect-fixing
session moves the pipeline, and every number computed before the fix quietly
stops matching what the current code would say, whether or not anyone
re-checks it. This inventory re-checked all of them.

(Same total as the first pass (21), but the composition moved substantially
as pending scripts actually finished running rather than being assumed to
regenerate cleanly. Six figures left the UNTRACEABLE set entirely once
their source script was actually executed, run to completion, and read:
"14 merges/2 of 14" and "lose six of twelve" became confident STALE swaps
(17 merges, 2 of 17, lose eight of fifteen); "Raabta/Demons/FLEX UP" became
a CURRENT confirmation; "35 genre tags" became a STALE swap (36, the raw
topicCategories count — a second, tidied count of 32 also exists and is
recorded but is the wrong methodology match). Five more
rows that a first pass had marked CURRENT-DATA ("would just need the script
run") turned out, once actually run, to reproduce only approximately —
leaked-pool table, 70% surviving, and the baseline-nDCG range all drift by
the same small amount as the rest of the 3,143-chain family, so they moved
to PAST-STATE alongside it rather than being swapped in as if exact. Three
rows were added as their own line once distinguished from a figure they'd
been folded into: "176 of 3,143"'s denominator, "best rank 209", and the
second "202 (6.4%)" occurrence. "37→48" resolved to PAST-STATE after a
bounded reconstruction attempt rather than staying open for Part B. Net:
21 → 22, one more than the first pass; almost every row's classification
changed even where the count didn't — see the main table above for what
actually changed and why, not just the tally.)

---

## 0d — confirmation of the prior inventory's named items

Every item the brief lists was independently re-confirmed this session
(all `[executed]` fresh, not carried from memory):

| item | confirmed? | current value |
|---|---|---|
| line ~399 "+121%" presented as the aggregate | ✅ confirmed | aggregate is +139.7%; +121% is the 2026-08-01 split alone |
| §3 "Music plays 10,539 (25.9%)" beside 2,918 canonical | ✅ confirmed | 10,539 is `STRICT_MUSIC=False`; consistent value is 10,319 |
| §6 half-life "30 days" vs config/report 14 | ✅ confirmed | config and report both say 14 |
| test counts "337" (×2) and "76 tests" | ✅ confirmed | 536 collected; `test_writer.py` has 85 `def test_` |
| "38 clusters", "over 2,858 tracks", 39.6% outliers | ✅ confirmed | current: 37 clusters over 2,918 canonical tracks; 2,858 is a stale (pre-canonical) frame |
| "one title x3, five more x2" | ✅ confirmed | current: one x3, **eight** x2 |
| "60% played exactly once", "top 20 account for 9.6%" | ✅ confirmed | 61.8% canonical / 61.6% raw; 11.7% canonical / 9.0% raw |
| "35 genre tags", "95% carry at least one" | ✅ confirmed | 95% -> current 96.2% (genre_coverage.md); 35 -> current **36** raw topicCategories labels (counted `[executed]`; a tidied count of 32 also exists, wrong methodology match) |
| "currently unfixed ... normalise_title" | ✅ confirmed | fixed 2026-09-16, `reports/normalise_title_fix.md` |
| the 3,143 chain and "176 of 3,143" | ✅ confirmed | see dedicated section above; source is a hardcoded literal, and the script currently crashes independent of that |
| "202 songs" removed by STRICT_MUSIC | ✅ confirmed | current re-derivation gives 201 (PAST-STATE, not a clean swap — see 3,143-chain reasoning) |
| "20 picks vs 296-496 reachable", "recall@20 capped ~4.4%" | ✅ confirmed | current reachable range is 212–365; cap is ~5.5% at the tightest split |

**No discrepancies found against the brief's list** — every item it names
reproduces exactly as stated. Three items not on the brief's list surfaced
during this re-derivation and are flagged separately: the **INCONSISTENT**
362-vs-363-day usage (both values are individually correct; the README
doesn't label which is which); `contamination.py`'s independent crash
(unrelated to the hardcoded-denominator defect it also carries); and
`canonical.py`'s two collapse functions (`collapse()` vs `collapse_report()`)
silently disagreeing by 17 tracks because only one of them runs the
duration-merge pass — the mechanism behind why "3,143" doesn't reproduce
even under its best-guess original methodology (see "the 3,143 chain").

One additional discrepancy against the brief's own text, not the prior
inventory's: the brief's Context section (line 6) cites
"`reports/dormancy_signals.md` shows 197 of 198" — confirmed exactly
(`dormancy_signals.md:188`) `[source-read]`.

---

## Part B — regeneration

**B1.** All four expected stdout-only scripts confirmed and run with
defaults, output saved verbatim: `reports/canonical_impact.txt`,
`reports/contamination.txt` (post-Part-A-fix — denominator now reads
"2,918", matching `total`), `reports/duration_merge_report.txt`,
`reports/verify_strict_null.txt`. No fifth script found beyond the
brief's expected four.

**B2.** `scripts/readme_facts.py` (new, committed) covers every remaining
CURRENT-DATA figure no existing script produces: the STRICT_MUSIC regime
pair for §3's table, playlist title repeat counts, the scoring paragraph's
canonical- and raw-frame stats, both raw and tidied genre-tag counts, and
both test-count figures. Output: `reports/readme_facts.md`. One correction
made while building it: the first pass computed only the *tidied* genre-tag
count (32, `embed.tidy_genres`) for the "35 distinct tags" figure; re-read
against README's own sentence ("topicCategories *returns* 35 distinct
tags" — describing the raw signal, not the clustering pipeline's tidied
set), the raw count (**36**, off by one) is the closer methodology match
and is what `readme_facts.py` now records; the tidied count (32) is kept
alongside it as a second, clearly-labelled row rather than dropped.

**B3 — VERDICT GATE.** Checked every regenerated figure against whether it
makes a README **conclusion** false, not just a number stale. None do —
several are actually strengthened, not weakened:

- **Contamination** (the brief's own named example): under today's default
  (`STRICT_MUSIC=True`), contamination is smaller now (2.0%, 58 of 2,918)
  because strict filtering already removed the worst offenders before this
  estimate runs — strengthens "contamination is small," doesn't threaten
  it. Under `STRICT_MUSIC=False` (the regime the original 176/121 figures
  almost certainly came from), it reproduces to within one track (175 vs
  176, 120 vs 121, 5.6% exact). Neither reading breaks "upper bound, small,
  doesn't reach top-k."
- **Duration-merge false-positive rate**: 2 of 17 (11.8%) vs the published
  2 of 14 (14%) — the rate is *better* today, so "keep 3s tolerance despite
  two known false merges" is if anything more defensible, not less.
- **Best rank a removed song reaches**: 172, not 209 — still nowhere near
  top-20; "contamination sits in the tail" is unaffected.
- **Genre coverage**: 96.2% vs the published 95%, 36 tags vs 35 — both move
  in the direction that supports "coverage is real, resolution is the
  problem," not away from it.

**One judgment call, flagged rather than silently resolved either way:**
"every strategy scores 1.00" on the ungraded replay task (line 409) does
not reproduce under either plausible reading (0.60–0.75 at k=20,
`test_days=105`; 0.60–0.68 at defaults) — cheap to check, both tried,
neither gives 1.00. The paragraph's own structure already frames this as
"run as first specified" and immediately contrasts it with "the graded
version of that window," which *is* current and *does* reproduce exactly
(`eval_invariance_window.txt`). The surrounding conclusion — this ungraded
framing is uninteresting and not worth headlining, which is why the graded
version follows — does not obviously flip to false at 0.60–0.75 rather than
1.00, but it is a real drop, not a rounding difference, and this line sits
outside §1 so C2's blanket disclaimer does not cover it. Treated as
PAST-STATE, left and listed per C7's "PAST-STATE outside §1 → leave and
list" rule, **not** treated as a B3 stop — but surfaced explicitly here
rather than folded silently into the same bucket as the §1 figures, since
the call is closer than those.

**No STOP.** Proceeding to Part C.

---

## Part D — close-out

### Every figure changed: old → new → source

| figure | old | new | source |
|---|---|---|---|
| Directions count (opening) | "Five" | "Six" | `recency_exclusion.md:72` self-count + C3's new entry |
| Dev-split lift (§1.2) | +22.1% | +18.3% | `rediscovery_headline.md:99-105` |
| Duration-merge count (§1.6) | 14 further merges | 17 further merges | `reports/duration_merge_report.txt` |
| False-merge rate (§1.6) | 2 of 14 (14%) | 2 of 17 (12%) | `reports/duration_merge_report.txt` |
| Lost-at-0s-tolerance (§1.6) | six of the twelve | eight of the fifteen | `reports/duration_merge_report.txt` |
| "the honest summary" lift (§2) | +121% (×2 in one sentence) | +139.7% (×2) | `rediscovery_headline.md:116-119` |
| Recall@20 cap (§2) | ~4.4% | ~5.5% | `rediscovery_headline.md:86-92` |
| Reachable range (§2) | 296–496 | 212–365 | `rediscovery_headline.md:86-92` |
| §3 music plays | 10,539 (25.9%) | 10,319 (25.4%) | `reports/readme_facts.md` |
| Playlist title repeats (§4) | five more ×2 | eight more ×2 | `reports/readme_facts.md` |
| % played once, scoring para (§6) | 60% | 61.6% (raw frame, by instruction) | `reports/readme_facts.md` |
| Top-20 share, scoring para (§6) | 9.6% | 9.0% (raw frame, by instruction) | `reports/readme_facts.md` |
| half_life selected (§6) | 30 days | 14 days | `rediscovery_headline.md` / `config.py:63` |
| Genre tag count (§6) | 35 distinct tags | 36 distinct tags | `reports/readme_facts.md` |
| Genre coverage (§6) | 95% | 96.2% | `genre_coverage.md:41` |
| `normalise_title` status (§6) | "currently unfixed" | "since fixed" | CLAUDE.md State (2026-09-16), `normalise_title_fix.md` |
| `test_writer.py` count (§8) | 76 tests | 85 tests | `grep -c "def test_" tests/test_writer.py` |
| Total test count (§9, §10) | 337 tests (×2) | 538 tests (×2) | `pytest --collect-only -q` |
| `contamination.py` denominator | hardcoded "3,143" | interpolated, reads "2,918" today | Part A fix, `reports/contamination.txt` |

New content inserted, not a figure change: C2's §1 disclaimer paragraph;
C3's Recency exclusion entry; C4's dormancy-distribution follow-up
sentence; C5's eligibility-drift limitations bullet.

### Every item listed-not-fixed, grouped by reason

**PAST-STATE inside §1 — covered by C2's new disclaimer, left untouched:**
0.270→0.339 half-life-leak demo; the leaked-into-raw-pool table
(35/34/34/36/37); "70% of favourites surviving"; baseline nDCG
0.29–0.46→0.11–0.17; "3,570 tracks → 3,143 songs" and its three companion
figures (359 multi-upload, 102 distinct-song pairs, 7 cross-artist groups);
the §1.4 split table; "176 of 3,143" and "121 categoryId-alone"; "202
songs/220 plays/1.1 mean" (both occurrences); "pool shrinks
−123/−136/−163"; "best rank 209"; the pre-fix 0.3343/0.1466 pair.

**PAST-STATE outside §1 — not covered by C2, left and listed per C7:**
"every strategy scores 1.00" on the ungraded replay task (§2, close call —
see B3 discussion above); the raw-384-d clustering row (§6, kept as a
negative comparison, never was a current-pipeline output); "38 clusters
over 2,858 tracks, 39.6% outliers" and its companion table row "PCA 20-d →
38 clusters, 15.6% largest" (§6 — left as one unit; a partial swap would
pair the current cluster count, 37, with an unverified stale percentage
from the old 2,858-track run); "23 of 50 / 5 of 50" and "ten distinct
tracks across fifty-two slots" (§8, both already flagged in
`readme_audit.md` 2026-09-14 as describing the superseded top-N-by-score
writer, pre-FLOOR/LENGTH/GUARD/RANK/CEILING); "37 distinct songs → 48"
(§8, same superseded mechanism — confirmed by a bounded reconstruction
attempt in Part 0 that gave 47/50, not 37/48).

**NEEDS-NEW-CODE:** "369 of 970 test songs never seen in training" (§2) —
would need re-running `evaluate.split_frames` and diffing train/test
vocabularies; eval internals are explicitly out of scope.

**Out of scope (backfill_plan.md / genre_coverage.md regeneration
excluded):** "five of the ten qualifying clusters have no discriminative
genre" (§8) — not restated in `backfill_plan.md` at HEAD, and that report's
regeneration is explicitly excluded. All of §8's backfill worked examples
(Joji, T-Series) are CURRENT against `backfill_plan.md` as it stands, but
that report is itself flagged ANCHOR-DEPENDENT / INDETERMINATE by
`gate_drift_audit.md` row 7 — carried forward, not re-litigated, since
regenerating it is out of scope for this brief.

### Stale items found in CLAUDE.md (not edited, per instruction)

- **Decisions table, `STRICT_MUSIC = True` row:** "5.6% contamination; the
  permissive signal is categoryId (**121 of 127**), not playlists (5)."
  Same family as README's now-PAST-STATE §1.5 figures — this session's
  Part A work found the mechanism (canonicalisation drift plus
  `contamination.py` inheriting `STRICT_MUSIC`'s current default rather
  than the `False` it was almost certainly measured under; see the "3,143
  chain" section above). Not edited — CLAUDE.md is explicitly
  do-not-edit for this brief.
- **State section, "Dataset-scale figures" bullet (line ~195):** states
  the 3,143 canonical-song figure "is off by 225 and unreconciled through
  STRICT_MUSIC-off or any other filter variant tried." This session's Part
  0 work resolves the mechanism (225 = 3,143 − 2,918, a `STRICT_MUSIC`
  regime difference, not unexplained drift; the residual 3,143-vs-3,136
  gap under the closest same-regime reconstruction is attributable to two
  documented `normalise_title`/`strip_artist_from_title` fixes since). The
  word "unreconciled" is therefore itself now stale, though the surrounding
  facts (40,617 vs 40,619, 30,438 vs 30,440) are unaffected and still
  correctly described. Not edited.
- Historical test-count mentions elsewhere in CLAUDE.md (424, 467, 480,
  509, 513 tests at various dated commits) are **not** flagged as stale —
  each is explicitly tied to a specific past session/commit, which is the
  correct, self-consistent use of a point-in-time figure, unlike README's
  undated "337 tests" claim.

### Other literal-figure prints found in scripts/ during Part A

One found beyond `contamination.py:178` (fixed in Part A):
`scripts/ground_truth_audit.py:284` hardcodes "the 486" in a
`print(f"...")` banner describing the ground-truth pool size, immediately
followed by a dynamically-computed value on the same line
(`n_distinct_representatives`). Same defect *shape* as the fixed
`contamination.py` bug — a literal number in prose text sitting next to a
computed one — but not verified for staleness and not fixed; listed only,
per Part A's explicit "list them, fix none." (`lastfm_coverage.py:207`'s
"429" was checked and ruled out — it is an HTTP status code in "429/
rate-limited errors," not a stale data figure.)

### Full suite

Run to completion after Part C's edits (README/inventory changes only, no
code touched since Part A/B): **538 passed, 0 failed** (292.16s). Starting
count was 536; Part A's `tests/test_contamination.py` added 2 — matches
exactly, no regressions from Part C's documentation-only changes.
outside §1 so C2's blanket disclaimer does not cover it. Treated as
PAST-STATE, left and listed per C7's "PAST-STATE outside §1 → leave and
list" rule, **not** treated as a B3 stop — but surfaced explicitly here
rather than folded silently into the same bucket as the §1 figures, since
the call is closer than those.

**No STOP.** Proceeding to Part C.
