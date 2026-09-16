# Evaluation verification — Part A (verify) + Part B (fix, where confirmed)

An external, read-only review with no project history produced five findings
against the embedding-mode comparison and its supporting measurements. Part A
verifies each independently against the actual code and data. Part B fixes
and re-measures only what Part A confirms. No code changed during Part A;
its verdicts were committed before Part B started.

Gate (brief §0): 467 tests passed (`bash scripts/run.sh -m pytest -q`,
157.6s), working tree clean at `becaa40`, which matched `origin/main` before
this brief's own commits.

## A1 — noise excluded from the ARI denominator: **CONFIRMED**

`cluster_eval.py:68`:

```python
scored = labelled[labelled["cluster"] >= 0]
...
predicted = scored["cluster"].tolist()
actual = [truth[v] for v in scored["video_id"]]
return {
    "n_eval": len(scored),
    ...
    "ari": float(adjusted_rand_score(actual, predicted)),
    "nmi": float(normalized_mutual_info_score(actual, predicted)),
    "purity": purity(predicted, actual),
    ...
}
```

Tracks HDBSCAN calls noise (`cluster == -1`) are removed at line 68, before
`predicted`/`actual` are built for ARI, NMI and purity. `n_eval` (line 82) is
`len(scored)` — **after** the filter, not before. It always has been: this is
the same quantity `reports/embedding_modes_remeasured.md` reports moving
234→237 across an unrelated NaN-guard fix, and the current measurement below
puts it at 238 for `title_artist` after the subsequent `normalise_title` fix.
`n_eval` has never meant "ground-truth tracks available" in this codebase; it
has always meant "ground-truth tracks HDBSCAN didn't call noise."

**Was this deliberate?** Line 68 was introduced with the file itself
(`36a561e`, "Add rediscovery eval and clustering comparison") and never
touched again except for pseudonymisation (`f46dc24`). That commit's message
shows the author was aware noise rates differ by mode — it reports "noise
40%" vs "noise 62%" for the two variants measured at the time — and added the
`coverage` metric specifically so "a clustering cannot win by labelling
everything noise" (same phrase survives in the current README, line 708).
That is a real, deliberate mitigation, but it is a **disclosure**, not a
**correction**: `coverage` is printed in an adjacent column and the prose
still declares a winner by comparing raw ARI head-to-head ("ARI 0.649 against
0.470... and 0.383", README line 664) with no adjustment for the fact that
the three numbers are computed over different subsets of the same 438-track
ground truth. No comment or docstring anywhere considers, let alone rejects,
treating noise as its own cluster or as singletons.

**Per-mode denominator gap** (current HEAD, `becaa40`; reproduces the
currently-correct-but-not-yet-published 0.665/0.371/0.366 from CLAUDE.md's
open item 6, confirming this session's measurement matches the live code):

| mode | ground truth in this clustering (`total_labelled`) | ARI denominator (`n_eval`) | gap | noise | coverage | ARI |
|---|---:|---:|---:|---:|---:|---:|
| `title_artist` | 438 | 238 | 200 | 44.8% | 54.3% | 0.665 |
| `title` | 438 | 188 | 250 | 54.8% | 42.9% | 0.371 |
| `title_genre` | 438 | 314 | 124 | 36.0% | 71.7% | 0.366 |

All three modes share the same 438-track ground-truth pool (see A3.1 below —
it is already 48 short of the 486 ground-truth tracks that are actually
music, for an unrelated reason, so 438 is not itself a clean number, but it
*is* the same 438 for all three modes and so does not confound this specific
comparison). Against that shared base, the ARI denominator ranges from 42.9%
to 71.7% depending on mode. The winning mode, `title_artist`, is graded on
the **smallest** slice of the three (238 of 438); the third-place mode,
`title_genre`, is graded on the **largest** (314 of 438) — 76 more
ground-truth tracks than `title_artist` gets scored on, entirely because
`title_genre` happens to leave fewer of them as noise.

**Verdict on the methodology question.** The code implements "exclude noise
entirely," one of the three defensible conventions listed in the brief, and
discloses the resulting coverage gap rather than hiding it. But the
comparison as published is not valid *under its own convention*: excluding
noise only stays fair across a comparison if the excluded share is
comparable across the things being compared, and here it ranges over a
29-point spread (42.9%–71.7%). Reporting coverage next to the number lets a
careful reader notice the gap; it does not correct for it, and the README's
prose does not ask the reader to. B1 recomputes under the two alternative
conventions to see whether the ranking is an artifact of which tracks each
mode happened to leave un-noised.

## A2 — playlist membership leaks across the split: **CONFIRMED** (mechanism); **measured impact: zero, at every split tested**

`classify.py:76`:

```python
df["in_playlist"] = df["video_id"].isin(playlist_ids)
```

`playlist_ids` (line 67–69) is `SELECT DISTINCT video_id FROM playlist_tracks`
— no date condition, confirmed exactly as claimed. `playlist_tracks.added_at`
exists in the schema and is populated (`db.py:48`, `parse_takeout.py:158`),
so a date filter is possible; the column is simply never read by `classify.py`.

**Severity — reaches row membership, not embedding text.** `in_playlist` is
one of five `HEURISTIC_SIGNALS` ORed into `heuristic_music`, which feeds
`is_music` two ways: directly (`is_music = api_music | heuristic_music`,
line 171) and indirectly, since `STRICT_MUSIC`'s `_looks_like_non_song`
(line 206) exempts any row with `heuristic` true from its bad-title/duration
check regardless of which signal made it true. `scored_tracks()`
(`score.py:113-115`) filters `labels[labels["is_music"]]` **before** merging
with the date-windowed play aggregate, and `evaluate.split_frames`
(`evaluate.py:86-88`) calls `embed.cluster_tracks(train)` directly on that
filtered frame. So an undated `in_playlist` changes **which rows enter the
frame that gets embedded and clustered** for a temporal hold-out — which
changes the PCA/HDBSCAN geometry every other track in `train` is placed
into, not only the leaking track's own label. It does not, however, reach
`embed.build_corpus`'s embedding *text*: `in_playlist` plays no part in what
string a track is embedded as, only in whether the row is present at all.
That is the precise version of "reaches the corpus": row membership, not
corpus text.

**This does not touch A1.** `cluster_eval.compare_modes` — the function
behind the published embedding-mode ARI table — calls `scored_tracks(conn)`
with no date arguments at all (confirmed: its only two call sites,
`cluster_eval.py:131` and `scripts/build_notebook.py:178`, never pass a
split). The embedding-mode comparison has no temporal split to leak across.
A2 is entirely about `evaluate.py`'s replay/rediscovery/nested hold-out, a
separate measurement from the one A1 concerns. The external review's framing
— that both findings jointly invalidate "the embedding-mode comparison" — is
wrong about A2's half; see item 5 in the closing list below.

**Is this the same leak `f46dc24` fixed?** No. That commit's leak was a
tie-break bug in `evaluate.py`/`recommend.py`'s hold-out *selection*
(`most_played`'s top-50 cutoff depended on half-life because ties at the
cutoff broke on scan order, not on `video_id`) — a sorting bug in a
different file, fixed by breaking ties on `video_id`. It never touched
`classify.py` or `in_playlist`. Confirmed by reading `f46dc24`'s full diff:
its only change to files this brief concerns is pseudonymisation in
`cluster_eval.py`, unrelated to the tie-break fix itself.

**Quantification (direct DB query).** Videos first played before
`2026-06-01` whose *earliest* playlist add is on or after `2026-06-01`:
**44**. (A looser count — any playlist-add row on/after the split,
regardless of an earlier add to a different playlist — gives 76; the extra
32 already had `in_playlist = True` before the split via another playlist,
so they carry no incremental leak. 44 is the number that answers "how many
tracks became playlist members only after the split.")

**Measured impact on the pinned eval and on every nested-eval split.**
Undated `in_playlist` can only change `is_music` two ways, and both were
checked, not assumed:

1. *Rescue via the union*: `in_playlist` is the *only* true heuristic signal
   and the track is not `api_music`, so `is_music` is entirely dependent on
   it. Five such videos exist in the whole database (all five are visibly
   non-music — e.g. "Why You Should Fear TYPE-7 CIVILIZATION?" — filed in a
   playlist for reasons unrelated to this brief). Intersected with the
   per-split "leaked" sets across all nine `MONTHLY_SPLITS`
   (`evaluate.py:379-382`, 2025-12-01 through 2026-08-01): **0 overlap at
   every split**, pinned split included.
2. *Rescue from the strict filter*: `in_playlist` is the only true heuristic
   signal, the track *is* `api_music`, and it would trip
   `_looks_like_non_song`'s bad-title/duration check if `heuristic` were
   correctly `False` pre-split. 205 such videos exist database-wide (a real,
   currently-live mechanism, just not one that interacts with the leak).
   Intersected with the same nine per-split leaked sets: **0 overlap at
   every split**, pinned split included.

Directly confirmed a third way: diffing `scored_tracks(conn, end="2026-06-01",
as_of="2026-06-01", canonical=True)`'s `train` frame against the 44 leaked
video_ids gives an empty intersection, canonical and non-canonical alike.

**Verdict:** the code defect is real — `in_playlist` genuinely carries no
date condition and genuinely reaches which rows get clustered, exactly as
claimed — but on this dataset, at this pinned split and at all eight other
splits this project's own nested-tuning evaluation walks, zero tracks'
`is_music` status or corpus membership is actually determined by the leak.
B2 fixes it anyway (per brief: the §A2.4 count is non-zero, so the gate is
met, and an undated global in a temporal hold-out is wrong regardless of
today's data), and reports the honest before/after: expected to be
byte-identical at the pinned split, because this section already
establishes that zero tracks change membership there.

## A3 — three smaller findings

### `cluster_eval.py:66` — canonical/raw id mismatch: **CONFIRMED**

```python
labelled = clustered[clustered["video_id"].isin(truth)]
```

`truth` (`playlist_ground_truth`) holds raw `playlist_tracks.video_id`
values. `clustered` comes from `scored_tracks(conn)`, canonical by default —
`canonical.collapse()` keeps exactly one representative `video_id` per
canonical-key group (`grouped.head(1)`, the most-played upload) and discards
the rest, summing play counts into the survivor. A ground-truth track filed
under a losing duplicate's `video_id` is therefore invisible to `clustered`
no matter how the merge went, and silently drops out of `labelled` — not
reassigned to its surviving twin, just gone.

Measured: 6,470 raw video_ids are ground truth (exactly one playlist); 3,365
raw video_ids are music (pre-collapse); the overlap — ground-truth tracks
that are music at all — is **486**. Of those 486, **48 (9.9%)** are
non-representative duplicates that canonical collapse drops entirely, never
reaching `clustered`. Only the remaining **438** reach `coherence()` — the
same 438 that grounds A1's table above.

### `redact.py:74` — alias rebuild scrambles existing mappings: **CONFIRMED** (mechanism); **no evidence it has fired on a published figure**

```python
missing = [n for n in names if n is not None and n not in mapping]
if missing:
    mapping = build_aliases(list(mapping) + names)
```

`build_aliases` sorts its **entire** input alphabetically and assigns labels
by sorted position (`PREFIX + _label(i)`). When any new name appears, the
call above rebuilds the label for **every** name, not just the new one — so
a new name that sorts before an existing one shifts every label after it.
Worked example: mapping `{"Chill": "Playlist A", "Zen": "Playlist B"}`, a
third playlist named "Beats" appears; sorted order becomes `["Beats",
"Chill", "Zen"]`, so "Chill" moves from `Playlist A` to `Playlist B` and
"Zen" from `Playlist B` to `Playlist C`. The docstring's "stable across
runs" claim (`build_aliases`'s own docstring, line 41) holds only for names
that never gain a new, alphabetically-earlier sibling.

Whether this **has** corrupted a published figure: no direct evidence found,
and `data/playlist_aliases.json` is gitignored with no history to audit, so
this is circumstantial, not a proof. What was checked: the current mapping
covers all 52 current distinct playlist/title names with zero missing and
zero stale keys — the signature of a single clean build, not a mapping that
has survived a name-set change. The file's mtime (2026-09-13 09:48) is about
two hours after the raw Takeout source's own mtime (2026-09-13 07:40) on the
same day `redact.py` was first committed (`f46dc24`, 15:33) — consistent
with one build, done once, that has not needed to add a name since. This
does not rule out a rebuild in a session predating this repo's git history
of the alias file (there is none to check), but there is no positive
evidence one occurred. Because ARI/NMI/purity are computed on group
*identity*, not the display string, a rescramble by itself would not move
any of those numbers within a single run — it would only make a "Playlist
K" mentioned in one report refer to a different real playlist than the same
label in a later one, the same class of trap CLAUDE.md already documents for
HDBSCAN cluster ids.

### `resolve.py:198` — a missing id caches as permanently deleted: **CONFIRMED**

```python
def pending_video_ids(conn):
    ...
    LEFT JOIN video_metadata m ON m.video_id = p.video_id
    WHERE m.video_id IS NULL
```

Any video_id with an existing `video_metadata` row — `found=0` or `found=1`
alike — is permanently excluded from `pending`. `_missing_row`'s own comment
says as much: "Cached so we never pay to look it up again." There is no
retry path anywhere in `resolve.py` for a `found=0` row. Currently **2,307**
rows have `found=0` (28,133 have `found=1`; 2,307+28,133=30,440, the full
resolved set). This matches CLAUDE.md's own already-published figures
exactly (609 units, 28,133 found), so it is not an anomalous or growing
number — it is what the original resolve run measured and reported as
"not found," consistent with genuinely deleted/private videos rather than a
visibly erratic rate. Whether any specific row is a false negative from a
transient `videos.list` omission cannot be determined without spending API
quota to re-query it; not attempted here — out of scope for a verification
brief, and the brief does not ask for it.

### `track_tag_lookups` status breakdown

```
ok_zero_tags   2247
ok_tags         872
not_found       654
unresolved       11
```

**No `error` rows exist in the table** (0 of 3,784). The cache-conflation
mechanism the reviewer describes is nonetheless real in the code:
`run_coverage_fetch`'s cache-read check (`lastfm.py:480`,
`_existing_status(...) is not None: skip`) does not distinguish `status =
'error'` from any other terminal status, so a persisted `error` row —
possible per `LastfmResult`'s own docstring (`'ok_tags' | 'ok_zero_tags' |
'not_found' | 'error'`) and written on an unparseable response, an API-level
error payload, or a raised exception (`lastfm.py:301,308,344,362`) — would
be skipped forever, never retried. That mechanism exists but did not fire on
this data: with zero `error` rows currently cached, the measured 21.9%
match rate (`reports/lastfm_coverage.md`) was not computed over any
error-poisoned subset. The reviewer's inference ("that conclusion was drawn
on partly poisoned data") does not hold against the actual table, though the
underlying code smell — an `error` result cached exactly as permanently as a
success — is real and would matter on a future run that hit one. Per the
brief's non-goals, this is reported, not fixed, and no Last.fm fetch was
re-run.

## Summary of verdicts

| # | finding | verdict | fix in this brief? |
|---|---|---|---|
| A1 | noise excluded from ARI denominator | confirmed | B1 (measure only, no default change) |
| A2 | `in_playlist` leaks across the split | confirmed (mechanism); zero measured impact at all 9 splits | B2 (fix + re-measure) |
| A3.1 | canonical/raw id mismatch drops 48 ground-truth tracks | confirmed | no (non-goal) |
| A3.2 | alias rebuild scrambles labels | confirmed (mechanism); no evidence it fired | no (non-goal) |
| A3.3 | `found=0` caches a permanent miss | confirmed | no (non-goal) |
| — | Last.fm `error` rows poison the match-rate conclusion | mechanism confirmed; **zero rows affected, conclusion stands** | no (non-goal, no re-fetch) |
