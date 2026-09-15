# Last.fm tag coverage — measurement report

Scope: measurement only, per the brief. Nothing here changes clustering,
embeddings, scoring, evaluation, or the write path. This answers "is Last.fm
a usable genre signal for this library?" and nothing else.

## §0 — What the ARI ground-truth labels actually are

**Verbatim, from `cluster_eval.playlist_ground_truth()`:**

> `video_id -> playlist label`, for videos filed in exactly one playlist. [...]
> Labels are pseudonymised by default. Every metric here treats them as
> opaque group identifiers.

Mechanically:

```sql
SELECT video_id, MIN(playlist_name) AS name
FROM (SELECT DISTINCT playlist_name, video_id FROM playlist_tracks)
GROUP BY video_id
HAVING COUNT(*) = 1
```

...then pseudonymised through `redact.alias`.

**The ground truth is the user's own YouTube playlist filings — human
curation — not derived from track title or artist text, and not computed
from any embedding.** `playlist_tracks.playlist_name` comes straight from the
Takeout CSV filenames; nothing in `playlist_ground_truth()` touches `title`,
`channel`, or any artist-parsing function. So brief §0's literal conditional
— "if the labels are artist-derived" — does not hold: they are not
mechanically artist-derived. ARI is not measuring the clustering against a
re-derivation of the artist string.

**That doesn't fully settle the question, though.** The sharper version of
the worry is whether the *human's own playlists* are themselves
artist-dominated — which would make ARI reward artist-shaped clusters for a
softer reason: not circularity in the computation, but the user happening to
curate mostly one-artist playlists. That is measurable, and was measured
rather than assumed (`artist = embed.artist_from_channel(channel)` per
ground-truth video, grouped by playlist):

- Of the 37 ground-truth playlists that feed the current ARI computation
  (≥1 member with a channel-resolved artist), 15 (40.5%) are >80% one artist
  by member count — but **9 of those 15 are singleton playlists (n=1)**,
  where ">80% one artist" is tautological, not a finding.
- Restricted to the 20 playlists with ≥5 resolved members — a cutoff chosen
  only to exclude those tautological 1-4-track cases before looking at which
  side of 80% they landed on, not tuned afterward to the answer — **4 of 20
  (20%) are >80% one artist**: two are large enough to matter (n=24 at 92%,
  n=9 at 100%), two are small (n=5 at 100%, n=7 at 86%).
- By **track** share, which is what actually determines how much weight
  artist-dominated playlists carry in the ARI computation: only **58 of the
  438 ground-truth tracks (13.2%)** sit under a playlist label that is
  itself >80% one artist. The two largest playlists in the ground truth (85
  and 56 tracks) are 21% and 16% dominant-artist respectively — genuinely
  multi-artist collections, not disguised artist bins wearing a mood name.

**Answer: no, not meaningfully.** The ARI ground truth is overwhelmingly not
artist-dominated once degenerate small playlists are excluded from the
read. ARI's preference for `title_artist` embeddings is not explained by "the
metric secretly measures artist-shaped-ness because the labels themselves are
artist bins." That said, both things can be true at once: the ground truth
can be genuinely multi-artist while the *clusters being scored against it*
are still heavily artist-shaped (see item 9 below — 43.2% of the current 37
clusters are >80% one artist). ARI rewarding `title_artist` for aligning with
real human groupings on some tracks, while the resulting clusters over-fit to
artist identity elsewhere, is the more accurate characterization — consistent
with, not a reversal of, CLAUDE.md's open item #3 ("clusters are
artist-shaped, not mood-shaped").

**One more thing, found while answering this and too load-bearing to leave
out even though the brief didn't ask for it:** the ARI figures measured fresh
today do not match README. README's table (§1, "Does removing the artist
help?") reports `title_artist` at ARI 0.627 / NMI 0.627 / purity 0.668 /
coverage 53% / **45 clusters** / 44% noise. Running the *identical* function
(`cluster_eval.compare_modes`) against the current database, right now,
gives:

```
ARI 0.652   NMI 0.633   purity 0.679   coverage 53.4%   clusters 37   noise 45.2%   n_eval 234
```

The cluster count (37, not 45) matches this brief's own "current 37 clusters"
framing — reassuring for §5 item 9 below — but it means README's ARI table is
stale relative to the database it currently describes, most likely for the
same reason already logged against the §1.4 split table in CLAUDE.md's open
items ("predates the strict filter; caveated in place rather than re-run").
This brief is measurement-only and explicitly excludes updating the README,
so this is reported here, not fixed.

## Observed Last.fm response schema

Confirmed live, before the parser was finalised (`lastfm._parse_toptags`),
by calling `track.getTopTags` for `artist=Joji, track=SLOW DANCING IN THE
DARK` (a known-good track), a gibberish artist/track pair, and
`artist.getTopTags` for `artist=Joji`. Not assumed from documentation.

**Success** (`track.getTopTags` and `artist.getTopTags` share the shape):

```json
{
  "toptags": {
    "tag": [
      {"count": 100, "name": "alternative rnb", "url": "https://www.last.fm/tag/alternative+rnb"},
      {"count": 64,  "name": "joji",             "url": "..."},
      {"count": 24,  "name": "Joji eu te amo",   "url": "..."}
    ],
    "@attr": {"artist": "Joji", "track": "SLOW DANCING IN THE DARK"}
  }
}
```

**Error** (a not-found lookup, and API-level errors generally): **HTTP 200**,
with the error carried in the JSON body, not the status code:

```json
{"error": 6, "message": "Track not found", "links": []}
```

This confirms the not-found/error distinction has to be made from the body,
not the HTTP status - `_parse_toptags` already did this (written against
Last.fm's long-documented convention, ahead of this probe), and this probe
is what turns that from an assumption into a checked fact. No parser change
was needed after seeing the real response.

**What `count` means:** not a raw listener/scrobble count. The known-good
track's top tag carries `count: 100`, and the artist-level call for the same
artist has **two different tags both at `count: 100`** ("rnb" and "Lo-Fi").
Two unrelated tags tying at exactly the round number 100 is the signature of
a **0-100 relative weight, normalised to that item's own top tag** - not an
absolute count, which would have no reason to cap or to tie like that. Tag
weight percentiles below are reported on this basis: as a per-track/per-artist
relative-popularity score, not a cross-track-comparable listener count. (The
full fetch below also reports the observed max across all ~2,918 tracks; if
it is ever measured above 100 this reading is wrong and that is stated
plainly rather than quietly kept.)

One thing NOT directly observed in this probe and worth flagging rather than
silently trusting: Last.fm's JSON output is known to collapse a one-item
`tag` list to a bare object instead of a 1-element array (an artifact of the
API's XML-native format). `_parse_toptags` defends against this
(`isinstance(raw_tags, dict)`), but today's probe never happened to return
exactly one tag, so that branch is defensive, not confirmed live. If it is
never exercised in the full run, it is simply unreached code, not a wrong
assumption - and `tests/test_lastfm.py::test_single_tag_comes_back_as_object_not_list`
covers it either way.

**`count`, fully confirmed against the whole fetch, not just the probe:**
across all 5,719 track-level and 1,040 artist-level tag rows written by the
full run below, `MIN(weight) = 1`, `MAX(weight) = 100`, and **zero rows
exceed 100**. That confirms the reading above rather than just supporting
it: this is a 0-100 relative weight, normalised per item, not a raw
scrobble/listener count.

## Storage design

`track_tags` uses the brief's schema exactly as given (§3): `(canonical_id,
tag, weight, source, fetched_at)`, PK `(canonical_id, tag, source)`.

`canonical_id` is the **representative `video_id`** that `canonical.collapse()`
picks for a song - the same id `video_metadata`/`written_playlists`/
`written_tracks` already use, so it joins onto everything else in the
database without translation. The known limitation: a re-collapse can shift
which upload is representative if relative play counts change, which would
orphan old `track_tags` rows under the old id. Accepted for a measurement
snapshot; `written_playlists` already accepts the same class of drift for
the same reason (it persists `planned_ids` rather than re-deriving them).

The lookup-attempt record is a separate table, `track_tag_lookups`, keyed
`(canonical_id, source, query_variant)` with a `status` column (`ok_tags` /
`ok_zero_tags` / `not_found` / `error` / `unresolved`) rather than a sentinel
row inside `track_tags` - a zero-tag track needs a row to exist with *no*
matching `track_tags` rows, and a sentinel tag (e.g. `__no_tags__`) would
have polluted every tag-frequency query in sections 5-8 below with a fake
entry to filter back out. `query_variant` (`feat_kept` / `feat_stripped`)
exists specifically so the two-pass comparison in §4 of the brief has
somewhere to write both attempts without one overwriting the other.
Artist-level fallback calls are deduped by artist (not by track) at fetch
time - an in-run cache seeded from any prior run's rows in this same table -
rather than by a third table; see `lastfm._load_artist_cache`.

Migration: both tables were added as new `CREATE TABLE IF NOT EXISTS` blocks
in `db.py`'s existing `SCHEMA` string, the same mechanism every other table
in this repo was introduced with. No guarded migration (`_migrate_phase4`'s
pattern) was needed - that machinery exists for a table whose *shape*
changed after it already held data, and these are new tables with nothing
to reshape.

## Matching (brief §4) - what "the canonical layer's existing artist field" actually is

There is no single such field. Three real signals exist, and
`lastfm.resolve_artist_track` uses them in this priority:

1. **`library_songs.artists`** - a real Takeout-sourced artist string
   (`"; "`-joined). Present for only **118/2,918 canonical tracks (4.0%)**
   by representative video_id (checked by direct join; a track whose library
   entry survives under a different, non-representative upload in the same
   canonical group would be missed by this check and is not separately
   measured). Never consulted by `embed.py`/`canonical.py`. Low coverage,
   highest quality when present - e.g. `"Drake; 21 Savage; Travis Scott"` -
   so it is checked first and only overrides when non-empty.
2. A channel name that **recognisably encodes an artist** - ends `" -
   Topic"`, or contains `"VEVO"` - via `embed.artist_from_channel`. Handles
   `"PIXELATED KISSES"` from `"Joji - Topic"`.
3. A leading `"Artist - Track"` prefix parsed off the raw title. Handles
   `"Joji - Past Won't Leave My Bed (Official Video)"` uploaded to a channel
   that is neither of the above.
4. The raw channel name, unchanged, only once (3) finds no dash. This is
   `embed.artist_from_channel`'s own bare fallback, accepted here on the same
   terms `classify.py` already accepts it elsewhere (real artist-owned
   channels with no Topic/VEVO marker exist - "Don Toliver has 230 plays on
   a channel named simply 'Don Toliver'" - and a compilation/reuploader
   channel is sometimes wrong under the same rule; both outcomes are folded
   into the failure breakdown honestly, not hidden).

**A genuine bug was found and fixed in this priority chain while building
it, not in `embed.py` itself (out of scope - see the note below):**
`embed.artist_from_channel` has no NaN guard, and a pandas-missing channel
is `float('nan')`, which is *truthy* in plain Python
(`bool(float('nan')) is True`). An earlier version of this matching code
checked channel truthiness directly and got the literal string `'nan'` back
as an "artist" for any track with a missing channel - confirmed on real
data: a 20-track smoke test produced query strings like `artist='nan',
track='Travis Scott - MY EYES'` for videos on `TravisScottVEVO`, because a
`library_songs`-join miss came back as pandas `NaN`, not `None`, and
`if library_artist:` is `True` for `NaN`. Fixed with an explicit `_clean()`
normaliser ahead of every input to `resolve_artist_track`
(`tests/test_lastfm.py::test_nan_channel_and_library_artist_are_treated_as_missing`
is the regression test). This is fixed **only in this brief's own module**.

**Separately, and left unfixed because it is out of this brief's scope
(§7 - clustering/embeddings are off-limits): the same underlying bug exists
in `embed.py` and `canonical.py` today.** `artist_from_channel(float('nan'))`
returns `'nan'` there too, unguarded. Measured impact: **9 of 2,918
canonical tracks** have a NaN channel. `embed.build_corpus()` calls
`artist_from_channel` unconditionally for every mode, so all 9 get corrupted
embedding text - 7 of them (where the title is *also* NaN, since
`embed.normalise_title` has the identical truthy-NaN gap) collapse to the
literal 3-character embedding text `'nan'` for all seven, identically; the
other 2 produce text like `'Spotify It Gets You Bebo Spills the Tea - nan'`.
`canonical.canonical_key()` is less exposed: it already guards NaN
*titles* explicitly (`if title is None or title != title: return ""`, with
a comment naming this exact failure mode), which happens to short-circuit 7
of the 9 rows before the bad artist string is used; only the 2 real-title
rows reach a `"nan|..."` canonical-key prefix. This is reported here because
it is real, measured, and feeds the clustering embedding text the README's
ARI table depends on - but per SECTION 7, it is not fixed, and no
clustering was re-run to measure its downstream effect on cluster
assignment.

**Two-pass feat./ft. comparison (brief §4):** pass 1 (`feat_kept`) left
`feat.`/`ft.`/`featuring` clauses in the track query; pass 2
(`feat_stripped`) re-queried, feat-stripped, **only the 290 canonical
tracks whose track-level pass-1 lookup was `not_found`** (a track that
already succeeded is never re-queried). Result: **0 of those 290 (0.0%)
gained a track-level match from stripping feat.** Pass 2 is a clean, measured
null on this library, not a small unmeasured effect being rounded away.

## 3. Match rate - track level

Full run: 2,918 canonical tracks, both passes complete, zero API errors
(see item 10).

**640 of 2,918 canonical tracks (21.9%) have at least one track-level tag**
(pass 1 `feat_kept`: 627 fresh + 13 carried over from an earlier smoke test
on the same real database, verified identical methodology; pass 2
`feat_stripped` added 0 more - see above). This is the headline number: **not
viable as a standalone track-level signal at face value** - see the zero-tag
breakdown in item 10, which is the more informative way to read this same
21.9%.

## 4. Match rate - artist-level fallback (reported separately, not merged)

**118 of 2,918 canonical tracks (4.0%)** gained a *real* artist-level tag
(`feat_kept`; `feat_stripped`'s fallback: 114/2,918 = 3.9%, almost entirely
the same tracks re-attempted, not new coverage). Relative to the population
that actually needed the fallback (290 track-level misses, `feat_kept`):
**251/290 (86.6%) resolved to a known Last.fm artist at all** (tags or
confirmed zero), and **118/290 (40.7%) of those misses got a real
artist-level tag**. Read together with item 10: most track-level "not found"
cases are not "Last.fm doesn't know this artist" - the artist is usually
findable; the specific track title is what fails to match or carries no tags.

## 5. Tag-weight distribution

```
             p1   p5  p10  p25  p50  p75  p90  p95  p99   min  max
track         1    1    1    3   11   48  100  100  100     1  100
artist        1    1    1    2    9   45  100  100  100     1  100
```
5,719 track-level tag rows, 1,040 artist-level tag rows. Confirmed (item 2):
weight never exceeds 100 anywhere in the corpus - a 0-100 per-item relative
weight, not a comparable-across-tracks listener count. Any floor chosen
later from this should be read as "top N% of *that track's own* tags," not
as an absolute popularity cutoff comparable between tracks.

## 6. Top 30 tags by track coverage

| tag | tracks | % of library |
|---|---:|---:|
| rap | 220 | 7.5% |
| Hip-Hop | 195 | 6.7% |
| trap | 194 | 6.6% |
| pop | 180 | 6.2% |
| rnb | 166 | 5.7% |
| hip hop | 128 | 4.4% |
| pop rap | 120 | 4.1% |
| indie | 111 | 3.8% |
| alternative | 105 | 3.6% |
| rock | 92 | 3.2% |
| alternative rnb | 82 | 2.8% |
| cloud rap | 80 | 2.7% |
| 2010s | 65 | 2.2% |
| Southern Hip Hop | 61 | 2.1% |
| alternative rock | 61 | 2.1% |
| indie pop | 53 | 1.8% |
| Drake | 51 | 1.7% |
| Love | 49 | 1.7% |
| dream pop | 46 | 1.6% |
| electronic | 46 | 1.6% |
| indie rock | 45 | 1.5% |
| american | 43 | 1.5% |
| soul | 43 | 1.5% |
| emo rap | 41 | 1.4% |
| british | 38 | 1.3% |
| synthpop | 34 | 1.2% |
| The Weeknd | 32 | 1.1% |
| love at first listen | 32 | 1.1% |
| sad | 32 | 1.1% |
| dance | 31 | 1.1% |

**Not case/hyphenation-normalised, and that measurably fragments the count**:
`Hip-Hop` (195) and `hip hop` (128) are the same tag under different casing/
punctuation and are counted separately here, as observed - combined they
would be 323 tracks (11.1%), not either individual figure. This is reported
as an observed property of the raw tag namespace, not corrected, per the
brief's "do not apply a stoplist yet."

## 7. Junk-tag inventory (observed, not filtered)

Built from the top 100 tags by coverage. Categories found, with examples:

- **Decade/year tags** (the brief's own `00s` example, confirmed present at
  15 tracks): `2010s`(65) `2020s`(21) `2024`(21) `2018`(20) `2016`(19)
  `2019`(18) `2015`(16) `2017`(16) `00s`(15) `10s`(15) `2020`(15) `2013`(14)
  `90s`(13) `2011`(11) `2022`(11) - **15 distinct tags**, the single largest
  junk category by tag count in the top 100.
- **Artist name used as its own tag** (redundant with the artist field,
  contributes nothing genre-wise): `Drake`(51) `The Weeknd`(32)
  `travis scott`(25) `Kanye West`(14) `don toliver`(13) `kendrick lamar`(12)
  `Lana Del Rey`(10).
- **Demographic/nationality tags** (same kind as the brief's `male
  vocalists` example, both confirmed present): `american`(43) `british`(38)
  `female vocalists`(29) `Canadian`(25) `male vocalists`(12).
- **Personal listening-habit / reaction tags** (the brief's `favourites`/
  `awesome` category): `love at first listen`(32) `beautiful`(27)
  `my top songs`(26, a Last.fm personal-list name, not a tag at all)
  `special`(12) `amazing`(7).
- **A venue/station identifier**, not a genre or mood by any reading:
  `WSUM 91.7 FM Madison`(16) - a college radio station's call sign.

**Checked for the brief's own literal example terms:** `'00s'` (15 tracks),
`'male vocalists'` (12), `'female vocalists'` (29), `'beautiful'` (27),
`'amazing'` (7) all appear. `'seen live'` and `'favourites'`/`'favorites'`
do **not** appear anywhere in this library's fetched tags (0 tracks) -
reported because their absence is also a fact, not because it was expected.

**Not junk** (kept out of the inventory above, on the brief's own framing
that genre *or mood* is usable): `Love`(49), `sad`(32), `chill`(24),
`melancholy`(10) read as legitimate mood tags, not sentiment noise -
judgment call, stated so it can be overridden.

## 8. Share of library under the single most common usable tag

**`rap`, 220/2,918 = 7.5%.** It is both the single highest-coverage tag
observed and unambiguously usable (not in the junk inventory above) - no
substitution was needed. **7.5% is far below the 75% `pop` gets from
YouTube topicCategories** - a 10x difference in concentration, which is the
number this brief exists to produce. Caveat carried over from item 6: this
is the raw-string figure. If `Hip-Hop`/`hip hop` were case-folded together
first, that combined tag (323/2,918 = 11.1%) would displace `rap` as the
single largest - still 7x below `pop`'s 75%, so the qualitative finding is
unchanged either way, but 7.5% is not artificially the *lowest possible*
reading of "most common tag."

## 9. Single-artist cluster rate - current clustering, zero Last.fm data

Computed against the CURRENT title_artist clustering (measured fresh this
session, not assumed - see the ARI drift note in SECTION 0: it is 37
clusters today, not the 45 in the README's stale table, and the brief's own
"current 37 clusters" framing matches what was actually measured).

- Clusters: 37. Noise share: 45.2%.
- Cluster members with a channel-resolved artist: 1,598/1,598 (100% -
  every real-cluster member happened to resolve one). Denominator convention
  matches `embed.name_cluster`'s own: members with no resolvable artist are
  dropped from both numerator and denominator rather than counted as
  "not dominant," so a cluster's rate is never depressed by unresolvable
  members it otherwise wouldn't be.
- **Clusters where one artist is >80% of members: 16/37 = 43.2%.**
  Top examples: Post Malone (100%, n=8), Young Thug (100%, n=11), Kanye West
  (100%, n=8), Future (98%, n=86), Drake (95%, n=93), Kendrick Lamar (94%,
  n=16), The Weeknd (91%, n=81), Justin Bieber (91%, n=11).

This is the baseline any follow-up genre/mood-clustering work should be
judged against: **43.2% single-artist**, not the 0% a mood-shaped clustering
would produce, and not 100% either - a real, substantial, but not total
artist-shaping problem.

## 10. Failure breakdown

| status | track / feat_kept | track / feat_stripped (290 retried) |
|---|---:|---:|
| ok_tags | 640 | 0 |
| ok_zero_tags | 1,979 | 2 |
| not_found | 290 | 286 |
| unresolved (no artist parsed, not queried) | 9 | 2 |
| error | 0 | 0 |

**The dominant outcome is not "not found" - it's "found, zero tags": 1,979
of 2,918 tracks (67.8%)** are matched by Last.fm's `autocorrect` (the
artist+track pair resolves to a real catalog entry) but carry no
community-contributed tags at all. Only 299 of 2,918 (10.2%: 290 not_found +
9 unresolved) are genuinely absent from or unqueryable against Last.fm's
catalog. **The bottleneck is tag density on matched tracks, not catalog
coverage** - worth stating precisely because "21.9% match rate" alone reads
like a matching-quality problem, and it mostly isn't one.

- **Zero API errors of any kind across 3,784 total lookup attempts**
  (track + artist, both variants) - no 429s, no 5xx, nothing the retry
  logic needed to recover from. `call_with_retry`'s backoff path exists and
  is tested (`tests/test_lastfm.py::TestRetry`) but was never exercised
  live in this run.
- **Artist found but track not found** (derived, not a stored status - a
  join between the two lookup rows for the same canonical track):
  **251 of the 290** `feat_kept` track-level misses. The complementary
  39 (`artist_not_found` in the raw counts) are cases where neither the
  track nor the artist resolves on Last.fm at all.
- The 9 `unresolved` (`feat_kept`) are exactly the 9 NaN-channel canonical
  tracks from the matching-bug note above, now correctly excluded from
  querying Last.fm with a garbage `"nan"` artist rather than corrupting the
  match-rate numbers the way the pre-fix code would have.

## Assessment

**No - or more precisely, not as a track-level signal, and only
provisionally as an artist-level one.** 21.9% track-level match rate is not
usable as a per-track genre/mood signal for this library: it would leave
78% of tracks with nothing, and the shortfall is not a matching-quality
problem to fix (86.6% of track-level misses do resolve a known artist) - it
is that two-thirds of the whole library (67.8%) is catalogued on Last.fm but
un-tagged by its community. No amount of better title-parsing moves that
number; it is a property of Last.fm's tag data on this specific set of
mostly-personal-library tracks, not of this pipeline.

What is real and worth keeping: for the 21.9% (640 tracks) that do have
tags, the tags themselves are the finer-grained signal hoped for - `lo-fi`,
`cloud rap`, `dream pop`, `shoegaze`, `chipmunk soul`, `bedroom pop` all
appear, none of which YouTube's topicCategories has any equivalent for - and
the concentration is genuinely far lower than YouTube's (`rap` at 7.5% vs
`pop` at 75%, item 8). The artist-level fallback (4.0% headline, 40.7% of
misses) is a weaker, coarser version of the same genuinely-more-granular
signal and could plausibly backstop the ~78% track-level gap for some
purpose, at the cost of being an artist-wide label rather than a per-track
one - which reintroduces exactly the artist-shapedness problem this brief
exists to get away from (SECTION 0, item 9: 43.2% of current clusters are
already single-artist).

If the follow-up decision is "build a fuller genre signal on top of Last.fm
tags," the honest framing is: usable for ~22% of tracks outright, a
same-artist-wide proxy for another ~4-9% depending on tolerance for
artist-level granularity, and no signal at all - track or artist - for the
remaining ~70%. Whether that's worth building on depends entirely on
whether the follow-up brief's use case can tolerate a signal that thin, or
needs a fallback for the majority case regardless.
