# Ground-truth canonical/raw ID mismatch - Part 0 diagnosis

Brief: `briefs/ground_truth_ids.md`. Read-only measurement; no pipeline code changed. New code: `scripts/ground_truth_audit.py`. Baseline: commit 36e3b5a (490 tests passing).

## Mechanism

`cluster_eval.coherence()`'s `labelled = clustered[clustered["video_id"].isin(truth)]` intersects `clustered["video_id"]` - canonical **representative** ids, one per `canonical.collapse()` group, from `scored_tracks(canonical=True)` - against `playlist_ground_truth()`'s keys, which are always **raw** `playlist_tracks.video_id` values and are never canonicalised. A raw id that is a losing duplicate in its own canonical group (i.e. some *other* upload of the same song was chosen as the representative) vanishes from `clustered` entirely - not reassigned to its surviving twin, just gone. `embed.cluster_tracks()` never drops rows (`out = df.copy().reset_index(drop=True)`, no dropna/filtering), so this is pure ID-level set logic, independent of embedding mode or clustering parameters - no embedding model was loaded to produce anything below.

## Correctness gate

- Re-derived raw -> representative mapping (same functions `canonical.collapse()` calls, same order, same input population) reproduces its real representative-id set exactly: **OK** (2,918 ids).


## Item 1 - total / join / drop

| population | count |
|---|---|
| ground-truth rows (filed in exactly one playlist) | 6,470 |
| → not music at all pre-collapse (irrelevant to this join) | 5,984 |
| → is_music pre-collapse (the addressable population) | 486 |
| &nbsp;&nbsp;&nbsp;&nbsp;joined (own id is its group's representative) | 438 |
| &nbsp;&nbsp;&nbsp;&nbsp;**dropped** (own id lost the representative slot) | **48** |

`ground-truth-and-music` matches `reports/eval_verification.md` (A3)'s independently-measured 486: **confirmed**. Drop count matches the brief's expected 48: **confirmed**.


The 6,470-vs-486 gap above is a different, much larger population (most playlist tracks simply are not classified as music at all) and is unaffected by anything in this brief - it is reported only so "total ground-truth rows" is not left for the reader to reconcile against "48" themselves.


## Item 2 - cause breakdown of the 48 drops

| cause | count |
|---|---|
| raw video ID exists in `video_metadata` but has no canonical mapping | 0 |
| ground truth stores a canonical ID where the lookup uses a raw ID | 0 |
| ground truth stores a raw ID where the lookup uses a canonical ID | 48 |
| ID absent from the library entirely | 0 |
| other (see below) | 0 |

**All 48 are one mechanism**, `truth_stores_raw_lookup_uses_canonical`: ground truth is *always* a raw `playlist_tracks.video_id` (the schema has no other form to store), and the lookup (`clustered["video_id"]`) *always* carries canonical representative ids. A "drop" is exactly the case where a raw id's own canonical group picked a *different* member as representative. The other three named buckets are 0 for structural reasons, checked rather than assumed:

- **"no canonical mapping"**: every row that reaches `canonical.collapse()`'s input gets a `canonical_key` unconditionally - `add_canonical_key` falls back to `"vid:" + video_id` when a title produces no usable key, which maps the row to itself, not to nothing. There is no code path that leaves a row keyless.

- **"ground truth stores a canonical ID"**: `playlist_ground_truth()` reads `playlist_tracks.video_id` directly with no canonicalisation step anywhere in its query - ground truth cannot store a canonical id even by coincidence in a way that would matter here, since the 438 cases where a ground-truth raw id *equals* its group's representative are exactly the successful joins, not a drop cause.

- **"ID absent from the library entirely"**: every id counted as a "drop" is, by this script's own definition, a member of `is_music_raw_ids` - the same population `canonical.collapse()` receives - so it was watched (present in `plays`) and classified `is_music`. It may or may not have its own `video_metadata` row (see the per-row detail below), but that is orthogonal to *why* it is missing from `clustered`: its representative's presence, not its own metadata, is what `clustered` membership depends on.

- **"other"**: 0. Reserved for a representative that itself fails to reach `clustered`, or a self-contradictory case caught by this script's own gates; see the loop's inline comments in `scripts/ground_truth_audit.py` for exactly which condition routes here.


**Context, not a cause bucket**: of the 48 dropped raw ids, 0 have no `video_metadata` row at all (is_music via heuristics only - `in_playlist`/`in_library`/`- Topic` channel/VEVO/music.youtube.com); 48 do. Metadata presence does not change whether the drop happens.


**Per-row detail:**

| raw video_id | playlist | title | in video_metadata | representative id | representative title |
|---|---|---|---|---|---|
| ZkJHEUKtvXI | Playlist A | No Idea | yes | _r-nPqWGG6c | Don Toliver - No Idea [Official Music Video] |
| tDm5zslFXwc | Playlist AF | W.D.Y.W.F.M? | yes | Oq-xMg1xbic | The Neighbourhood - W.D.Y.W.F.M? (Official Audio) |
| nOj6d-HOw2w | Playlist AG | Hips Don't Lie | yes | DUT5rEU6pqM | Shakira - Hips Don't Lie (featuring Wyclef Jean) (Official 4 |
| 3CfAjPE3Hm8 | Playlist AH | BACK TO THE BASICS | yes | G8w42dfxNg8 | Future - BACK TO THE BASICS (Official Music Video) |
| IzSPUtqQcCg | Playlist AH | SOS | yes | GpDhsfSQVeE | SZA - SOS (Lyric Video) |
| uWdHM3-2cpU | Playlist AH | Trance | yes | gHb6AEwNFBU | Trance |
| 82gK651sca8 | Playlist AJ | Double Fantasy | yes | dMoFcvfd5t4 | The Weeknd ft. Future - Double Fantasy (Official Music Video |
| U2TPS-9oMtc | Playlist AJ | Stargirl Interlude | yes | TkxVOa6u59M | The Weeknd - Stargirl Interlude (Audio) ft. Lana Del Rey |
| ZtEtKXhhtS4 | Playlist AJ | Call Out My Name | yes | M4ZoCHID9GI | The Weeknd - Call Out My Name (Official Video) |
| qPRNIHxLhmc | Playlist AJ | I Feel It Coming | yes | qFLhGq0060w | The Weeknd - I Feel It Coming ft. Daft Punk (Official Video) |
| ygTZZpVkmKg | Playlist AN | The Weeknd - After Hours (Audio) | yes | WxYgXmZ9xh8 | After Hours |
| i_UmZww2H58 | Playlist AW | Kaise Hua | yes | WKv07mnKVEE | Kaise Hua (From "Kabir Singh") |
| pI2vTj8Au7Y | Playlist AW | Tu Har Lamha | yes | 0lH2MHzarGA | Tu Har Lamha (From "Khamoshiyan") |
| y12BRDS1CHI | Playlist AW | Woh Lamhe Woh Baatein (From "Zeher") | yes | -xjhuuVXcF0 | Woh Lamhe Woh Baatein |
| C0PTIqB4RI0 | Playlist AY | Fair Trade | yes | THVbtGqEO1o | Drake - Fair Trade (Audio) ft. Travis Scott |
| k2pwvr8p4vM | Playlist AY | BUTTERFLY EFFECT | yes | _EyZUTDAH0U | Travis Scott - BUTTERFLY EFFECT (Official Video) |
| 12NrPQ9cxyg | Playlist E | Not You Too | yes | ZX_mvoY_Hg0 | Drake - Not You Too (Audio) ft. Chris Brown |
| 1OZnXQQPBU0 | Playlist E | House Of Balloons / Glass Table Girls | yes | 8ex38L8xtNI | The Weeknd - House Of Balloons / Glass Table Girls |
| JKlYOUfviXM | Playlist E | Take Me To Church | yes | PVjiKRfKpPI | Hozier - Take Me To Church |
| KIXP--0-Tac | Playlist E | No Pole | yes | fCeiUX59_FM | Don Toliver - No Pole [Official Visualizer] |
| WrZnk3rtcVw | Playlist E | Dreamin | yes | QHx1-CM1nvk | PARTYNEXTDOOR - Dreamin (Official Audio) |
| 3J4F0mWitrA | Playlist I | DA WIZARD | yes | z4-H1RSSJ4A | DA WIZARD |
| kPpm2p_xQ40 | Playlist I | THANK GOD | yes | UVtTc4zqbxQ | Travis Scott - THANK GOD (Official Audio) |
| tBfWb5IrbOI | Playlist I | 90210 | yes | h35g2e9aIIk | 90210 |
| zIuZhdJVWIs | Playlist I | TELEKINESIS | yes | xl5LunV-OkU | Travis Scott - TELEKINESIS (Official Audio) ft. SZA, Future |
| 2EZVebJGc1Q | Playlist M | 24 | yes | -G3mOwOAwT8 | Money Man - 24 (Official Video) ft. Lil Baby |
| LoD-c5eEA38 | Playlist M | XO Tour Llif3 | yes | k5PO17AC3Kg | XO Tour Llif3 |
| zRCYSzfFDuU | Playlist M | Sweater Weather (Slowed Down) | yes | cULQhvuq1Zc | Sweater Weather |
| jOF8gqpoPgs | Playlist Q | No Lie | yes | GzU8KqOY8YA | Sean Paul - No Lie ft. Dua Lipa |
| 2gEZyHMr-X4 | Playlist S | U Are My High | yes | isWT4n8Hk1U | DJ Snake - U Are My High (Feat. Future) [Official Visualizer |
| 3Hm7C7RCwMw | Playlist S | bando - sped up + reverb | yes | XfLrK3lqplU | bando (sped up + reverb) |
| 6bxrMPrHQBM | Playlist S | Snow in Skyami | yes | SRIc1RSp2nY | Future - Snow in Skyami (Official Audio) |
| 9-dEHfSCZUQ | Playlist S | Which One | yes | 7hdk4ddEtlI | Which One |
| R0cE4B1U8Zk | Playlist S | You Da Baddest | yes | 2DBBb3_p8eg | Future - You Da Baddest (Official Music Video) ft. Nicki Min |
| TKto7Z_HH_I | Playlist S | Dobro Vecer | yes | ds_M4gTLo9s | Farazi - Dobro Vecer (Remastered) |
| YfqJktv2nuA | Playlist S | Pal Pal (with Talwiinder) | yes | RLsYNh7GN-k | Pal Pal |
| bU9kTNlGk0g | Playlist S | Last of a Dying Breed | yes | 85UJ8Rvfj9g | Joji - Last of a Dying Breed (Visualizer) |
| g1zVw8drM5k | Playlist S | Whisper My Name | yes | YhUqxWR4mnE | Drake - Whisper My Name |
| mckg2Eo51Qo | Playlist S | Virginia Beach | yes | k20wnICXpps | Drake - Virginia Beach (Audio) |
| o-Mxt-G8WPs | Playlist S | Burning Bridges | yes | bpD-JVy2zV4 | Drake - Burning Bridges |
| vJx7fpvu45M | Playlist S | KRYPTONITE | yes | jcYzPd9mej0 | Don Toliver - KRYPTONITE [Official Audio] |
| vOn0z0IRVN8 | Playlist S | Love Hurts | yes | 1VGbnKGRxMc | Love Hurts (Single Edit) |
| x-Hbx9_QMZU | Playlist S | California Girls | yes | owxHUouEIBU | Future - California Girls (Official Music Video) |
| y9qO_xgE34Q | Playlist S | WAIT FOR U | yes | rP09GUQFDFk | Future - WAIT FOR U (Official Music Video) ft. Drake, Tems |
| 48ydDUQ16RE | Playlist X | Unforgettable | yes | CTFtOOh47oo | French Montana - Unforgettable ft. Swae Lee |
| 8ijJP_rG45U | Playlist X | 24 | yes | -G3mOwOAwT8 | Money Man - 24 (Official Video) ft. Lil Baby |
| USo0sAaJKR0 | Playlist X | Hotline Bling | yes | uxpDa-c-4Mc | Drake - Hotline Bling |
| YZLJ_GWJ5Ag | Playlist X | Laugh Now Cry Later | yes | JFm7YDVlqnI | Drake - Laugh Now Cry Later (Official Music Video) ft. Lil D |

## Item 3 - conflicting canonical tracks after raw -> canonical mapping

Scope: all 486 is_music ground-truth rows (not just the 48 drops - a conflict needs two *different* raw ids sharing one representative, and one side of that pair can be a "joined" id).


**3 canonical track(s) receive more than one distinct playlist label.**

| canonical (representative) video_id | title | artist | conflicting playlists | raw member ids |
|---|---|---|---|---|
| -G3mOwOAwT8 | Money Man - 24 (Official Video) ft. Lil Baby | Money Man | Playlist M, Playlist X | 2EZVebJGc1Q, 8ijJP_rG45U |
| gHb6AEwNFBU | Trance | Metro Boomin | Playlist AH, Playlist E | gHb6AEwNFBU, uWdHM3-2cpU |
| h35g2e9aIIk | 90210 | Travis Scott | Playlist I, Playlist S | h35g2e9aIIk, tBfWb5IrbOI |

## Item 4 - recoverable vs genuinely unmatchable

Of the 48 drops: **44 recoverable** (the raw id's representative exists in `clustered` and carries no conflicting playlist label - Part 1 mapping raw ground truth to its canonical id would attach it cleanly); **4 genuinely unmatchable** (representative absent from `clustered`, or the mapping collides with another playlist's label per Item 3).


Unmatchable ids:

- `2EZVebJGc1Q` (Playlist M): representative -G3mOwOAwT8 carries a conflicting label

- `8ijJP_rG45U` (Playlist X): representative -G3mOwOAwT8 carries a conflicting label

- `tBfWb5IrbOI` (Playlist I): representative h35g2e9aIIk carries a conflicting label

- `uWdHM3-2cpU` (Playlist AH): representative gHb6AEwNFBU carries a conflicting label


**`438 + 44 = 482` is NOT the post-fix denominator - do not sum those two numbers.** Part 1's conflict rule (brief, Part 1 item 2) drops the whole *canonical track* on a label conflict, not just the losing raw id. 2 of the 3 Item-3 conflict group(s) have a representative id that is *itself* a currently-joined ground-truth id (**`gHb6AEwNFBU`, `h35g2e9aIIk`**) - fixing the join and then applying the conflict rule would *remove* those rows from ground truth, not merely fail to add them. The remaining 1 group(s) (`-G3mOwOAwT8`) cost nothing beyond drops already counted unmatchable above - neither member was ever a currently-joined ground-truth id.


Measured directly over the full 486 (not derived by arithmetic from the counts above, so an invisible same-label collision is not missed either - two raw ids, one playlist, one representative would reduce the denominator without tripping the >1-label conflict check): **483** distinct canonical tracks are reached by the 486 ground-truth-and-music raw ids once each is mapped to its representative. No same-label collisions beyond the conflicted groups exist.


**Projected post-Part-1 labelled pool** (distinct representatives, minus the 3 conflicted groups Part 1 drops whole): 483 − 3 = **480**. This is a projection for Part 2 to verify against `cluster_eval`'s own reported figures once Part 1 ships, not a number this read-only script asserts as final.


**This 438/480 is `total_labelled` (the labelled pool `coherence()` builds *before* any noise convention is applied), not the `n_eval` `coherence()` actually reports today.** The shipped default (`"exclude"` convention) then drops HDBSCAN noise from that pool, and the result is smaller and **mode-dependent** - per `reports/eval_verification.md` (A1), today's `n_eval` off the current 438-track pool is `title_artist`=238, `title`=188, `title_genre`=314, not 438 for any of them. The same split will apply post-fix: 480 is the new *pool* size, and each mode's actual post-fix `n_eval` under `"exclude"` will be some smaller, mode-specific subset of it - `480` flat only holds for the two noise-inclusive conventions (`single_cluster`/`singletons`), where `n_eval` equals the pool by construction. Part 2's before/after table must report the pool *and* each mode-and-convention's own `n_eval` as separate columns, not use 480 as a stand-in for both.


## Answer

Drop confirmed at **48** (matches the brief's expected 48). All 48 share one cause: ground truth is raw-id-only and the collapsed frame is representative-id-only, with no ID-level ambiguity found in the other three hypothesised causes. 3 label conflict(s) would arise from a naive raw->canonical remap of ground truth - this is the real risk Part 1 must handle with an explicit drop rule, per the brief. Applying that drop rule costs more than the 48 alone: it also removes **2** id(s) currently counted as *joined* (`gHb6AEwNFBU`, `h35g2e9aIIk`), so today's 438 does not survive unchanged either. Today's labelled pool is 438; the projected pool after Part 1's fix is **480** (483 distinct canonical tracks reached by the 486, minus the 3 conflicted groups dropped whole) - up from 438, but by less than the naive `438 + 44` sum would suggest. This is the *pool*, not `coherence()`'s actual `n_eval` - under the shipped `"exclude"` convention that is a smaller, mode-dependent subset (today: 238/188/314 for title_artist/title/title_genre, per eval_verification.md A1), so Part 2 must report pool and per-mode `n_eval` as separate figures rather than let either be inferred from the other.


**STOP HERE per the brief - Part 1 not started.**
