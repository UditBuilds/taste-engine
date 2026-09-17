"""Collapse multiple uploads of the same song into one canonical track.

YouTube carries the same recording many times over: the label's official
video, the auto-generated `- Topic` audio, a lyric video, an extended cut. Each
is a distinct `videoId`, so to everything upstream of here they are distinct
tracks. That is not a cosmetic problem — it corrupts the evaluation in two
directions at once:

* **nDCG is inflated.** Three uploads of one song that the user replays count
  as three separate hits, so a model that surfaces one song three times scores
  like a model that surfaced three songs.
* **The rediscovery hold-out leaks.** That task removes the top-50 most-played
  tracks precisely so the model cannot win by naming favourites. A song whose
  plays are split across four uploads may sit below the cutoff on every one of
  them — so a genuine favourite survives into the candidate pool, which is the
  one thing the hold-out exists to prevent.

**What is deliberately not merged:** remixes, covers, instrumentals and live
versions are different recordings and stay separate. Only packaging variants of
the same recording are collapsed.
"""
from __future__ import annotations

import re

import pandas as pd

from . import config
from .embed import artist_from_channel, normalise_title, strip_artist_from_title

# Packaging, not content. Safe to ignore when deciding "same song?".
VARIANT_WORDS = [
    r"official", r"audio", r"video", r"visuali[sz]er", r"lyrics?", r"lyric",
    r"hd", r"hq", r"4k", r"full", r"complete",
    r"extended", r"second half", r"long version", r"full version",
    r"slowed(?:\s*(?:down|\+?\s*reverb))?", r"sped\s*up", r"speed\s*up",
    r"reverb", r"bass\s*boosted", r"8d(?:\s*audio)?", r"nightcore",
    r"remaster(?:ed)?(?:\s*\d{4})?", r"\d{4}\s*remaster",
    r"explicit", r"clean", r"radio\s*edit", r"single\s*version",
    r"music\s*video", r"tiktok", r"loop(?:ed)?", r"perfectly",
]
RE_VARIANT = re.compile(r"\b(?:" + "|".join(VARIANT_WORDS) + r")\b", re.I)

# Featured artists move around between uploads of the same song.
# NOT `with`: a bracketed "(with Drake)" is already removed by RE_BRACKETS, so
# the only thing a bare `with` catches is ordinary English. It turned
# "Stay With Me" into "stay", which the duration pass then matched against
# The Kid LAROI's "STAY" - both 2:22, two entirely different songs.
RE_FEAT = re.compile(
    r"\b(?:feat|ft|featuring)\b\.?\s.*$", re.I
)
# Indian label uploads carry cast and film metadata after pipes:
#   "Lyrical: Chammak Challo | Ra One | ShahRukh Khan | Kareena Kapoor"
# while the auto-generated twin is just "Chammak Challo". Keeping the longest
# pipe segment recovers the song name, because the name is almost always the
# longest field and the rest are single names.
RE_PIPE = re.compile(r"\s*\|\s*")
# "Lyrical:", "Full Video:", "Song:" — publisher labels, not part of the name.
RE_LEADING_LABEL = re.compile(
    r"^\s*(?:lyrical|full\s+video|full\s+song|video\s+song|audio\s+song|"
    r"song|official\s+video|full)\s*:\s*",
    re.I,
)
# A film name glued to the front: "ANIMAL:Pehle Bhi Main", "Rockstar: Tum Ho".
RE_FILM_PREFIX = re.compile(r"^\s*[A-Za-z][A-Za-z0-9'&. ]{0,18}:\s*")


# "Jee Le Zaraa Song", "Tum Ho (Lyrical Video) Song" — a publisher suffix.
RE_TRAILING_SONG = re.compile(
    r"\s+(?:full\s+|video\s+|audio\s+|lyrical\s+)?song\s*$", re.I
)


def strip_pipe_metadata(raw: str) -> str:
    """Recover the song name from a label upload's title.

    **First segment, not longest.** Taking the longest looked reasonable and is
    wrong on this corpus, because a cast or composer credit is often longer
    than the song name:

        "Sheila Ki Jawani" Full Song | Tees Maar Khan | Katrina Kaif,
        Akshay Kumar | Vishal Dadlani, Sunidhi Chauhan
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ longest segment

    That is not merely a miss: it fused "Pink Lips" with "BABY DOLL", two
    different songs whose longest segment was the same composer credit. The
    convention these uploads follow puts the song name first, so the first
    segment is used, falling back to the longest only when the first is a
    single word.
    """
    parts = [p.strip() for p in RE_PIPE.split(str(raw)) if p.strip()]
    if len(parts) > 1:
        raw = parts[0] if len(parts[0].split()) >= 2 else max(parts, key=len)
    raw = RE_LEADING_LABEL.sub("", str(raw))
    raw = RE_FILM_PREFIX.sub("", raw)

    # Only when something substantial survives: "Love Song" and "Sad Song" are
    # titles, "Jee Le Zaraa Song" is a title plus a publisher suffix. Two
    # remaining words is the line.
    trimmed = RE_TRAILING_SONG.sub("", raw)
    if trimmed is not raw and len(trimmed.split()) >= 2:
        raw = trimmed
    return raw.strip()


RE_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")
RE_NONWORD = re.compile(r"[^a-z0-9\s]")
RE_SPACES = re.compile(r"\s+")

# Things that genuinely make a recording different. If one of these appears,
# the track keeps its own identity.
RE_DISTINCT = re.compile(
    r"\b(remix|cover|instrumental|karaoke|live|acoustic|demo|mashup|"
    r"sped\s*up\s*remix|edit\s*by|vs\.?|solo|unplugged|reprise|orchestral|symphony)\b",
    re.I,
)


def canonical_key(title: str | None, channel: str | None = None) -> str:
    """A key that is equal for two uploads of the same recording.

    **The artist is part of the key.** Keying on title alone over-merges badly:
    on this library it fused "Die For You" by Joji with "Die For You" by The
    Weeknd, "Falling" by Harry Styles with "Falling" by Trevor Daniel, and 102
    other distinct-song pairs. The two failure modes are not symmetric — an
    over-merge sums the play counts of different songs and puts the wrong track
    in a playlist, while an under-merge just leaves a duplicate, which is the
    problem we already had. So the key is conservative.

    The cost is real and measured: an upload credited to a featured artist's
    channel will not merge with the same song on the lead artist's. That is
    accepted.

    Returns "" when the title is unusable, which callers treat as "do not
    merge" rather than "merge everything with no title".
    """
    # NaN is truthy, so `if not title` is not enough: a float NaN would
    # stringify to "nan" and silently merge every untitled track into one song.
    if title is None or title != title:
        return ""
    raw = str(title).strip()
    if not raw or raw.lower() == "nan":
        return ""
    # Captured before the pipe strip rewrites `raw`: a "(Live)" or "(Remix)"
    # marker can sit in a segment the strip discards, and searching the
    # shortened string afterwards would lose it.
    distinct_match = RE_DISTINCT.search(raw)

    raw = strip_pipe_metadata(raw)
    text = normalise_title(raw)
    text = strip_artist_from_title(text, artist_from_channel(channel))
    text = RE_BRACKETS.sub(" ", text)

    # RE_FEAT strips to end-of-string, which is right for "Song ft. Guest" and
    # wrong for "Artist ft. Guest - Song" — standard VEVO naming, where the
    # feature clause sits in the *artist* half and the song name follows a
    # dash. Left unguarded this returned "" for "The Weeknd ft. Future -
    # Double Fantasy", so every such track fell back to its video id and could
    # never merge with its own duplicates.
    without_feature = RE_FEAT.sub(" ", text)
    if len(without_feature.strip()) < 2 and " - " in text:
        without_feature = text.rsplit(" - ", 1)[-1]
    text = without_feature

    text = RE_VARIANT.sub(" ", text)
    text = RE_NONWORD.sub(" ", text.lower())
    text = RE_SPACES.sub(" ", text).strip()

    if len(text) < 2:
        return ""

    artist = artist_from_channel(channel)
    artist = RE_NONWORD.sub(" ", str(artist).lower())
    artist = RE_SPACES.sub(" ", artist).strip()

    marker = ""
    if distinct_match:
        # A remix/cover/live version keeps its own identity, tagged so it
        # cannot collide with the studio recording.
        marker = "|" + distinct_match.group(0).lower().strip()
    return (f"{artist}|{text}" if artist else f"?|{text}") + marker


def title_core(title, channel=None) -> str:
    """The song name with the artist removed - deliberately NOT a merge key.

    Merging on this alone fuses different songs that share a title. The
    duration pass uses it only to decide which keys are *worth comparing*;
    runtime then decides whether they are the same recording.
    """
    key = canonical_key(title, channel)
    if not key:
        return ""
    _, _, rest = key.partition("|")
    return rest


def add_canonical_key(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    channels = out.get("channel", pd.Series([None] * len(out), index=out.index))
    out["canonical_key"] = [
        canonical_key(t, c) for t, c in zip(out["title"], channels)
    ]
    # An unusable key must never merge rows together.
    blank = out["canonical_key"] == ""
    out.loc[blank, "canonical_key"] = "vid:" + out.loc[blank, "video_id"].astype(str)
    return out


RE_ISO = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def iso_seconds(duration):
    """'PT3M21S' -> 201. None when the runtime is unknown."""
    if not isinstance(duration, str):
        return None
    m = RE_ISO.fullmatch(duration)
    if not m:
        return None
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    total = h * 3600 + mi * 60 + s
    return total or None


def merge_by_duration(work: pd.DataFrame, tolerance: int | None = None) -> pd.Series:
    """Second pass: same song name, different artist attribution, same runtime.

    The artist-keyed rule under-merges by design, and the shape of the misses
    is systematic: a label uploads under its own channel (`T-Series`) while the
    auto-generated `- Topic` twin sits under the composer, so the two never
    share an artist. Runtime settles it - two different songs called "Raabta"
    do not agree to the second, while an upload and its twin do.

    Only keys that already share an artist-stripped title are compared, and a
    missing runtime never merges: unknown is not a match.

    **Genre breaks the ties runtime cannot.** Two different songs can share a
    title and agree on runtime by coincidence - Imagine Dragons' "Demons" is
    2:58 and Joji's is 2:57. `topicDetails.topicCategories` is an independent
    signal, so a merge is refused when both sides carry genre labels and those
    labels are disjoint. An absent genre set is treated as unknown rather than
    as disagreement: refusing to merge on missing data would throw away the
    label/Topic pairs this pass exists to find.
    """
    tolerance = config.DURATION_MERGE_TOLERANCE_S if tolerance is None else tolerance
    keys = work["canonical_key"].copy()
    if "seconds" not in work.columns:
        return keys

    from .embed import tidy_genres

    has_genres = "genres" in work.columns
    agg = {"seconds": ("seconds", "first"), "core": ("core_key", "first")}
    if has_genres:
        agg["genres"] = ("genres", "first")

    # One representative runtime per existing key: the most-played upload's.
    rep = (
        work.sort_values(["play_count", "video_id"], ascending=[False, True])
        .dropna(subset=["seconds"])
        .groupby("canonical_key")
        .agg(**agg)
    )
    rep["gset"] = (
        rep["genres"].map(lambda g: frozenset(tidy_genres(g)))
        if has_genres
        else [frozenset()] * len(rep)
    )

    remap: dict[str, str] = {}
    for core, group in rep[rep["core"] != ""].groupby("core"):
        if len(group) < 2:
            continue
        ordered = group.sort_values("seconds")
        cluster_head, previous, head_genres = None, None, frozenset()
        for key, row in ordered.iterrows():
            genres = row["gset"]
            close = previous is not None and row["seconds"] - previous <= tolerance
            # Unknown genres cannot contradict; only two populated, disjoint
            # sets are evidence of two different songs.
            contradicts = bool(genres) and bool(head_genres) and not (genres & head_genres)
            if close and not contradicts:
                remap[key] = cluster_head
            else:
                cluster_head, head_genres = key, genres
            previous = row["seconds"]
    return keys.map(lambda k: remap.get(k, k))


def _canonicalise(df: pd.DataFrame) -> pd.DataFrame:
    """First half of `collapse()`: derive each row's final `canonical_key`.

    Split out so `raw_to_canonical_map()` can expose the raw id -> group
    mapping for every input row, not just the survivors `collapse()` itself
    keeps after `grouped.head(1)` discards the rest.
    """
    work = add_canonical_key(df)
    work["core_key"] = [
        title_core(t, c)
        for t, c in zip(
            work["title"],
            work.get("channel", pd.Series([None] * len(work), index=work.index)),
        )
    ]
    if "duration" in work.columns:
        work["seconds"] = work["duration"].map(iso_seconds)
        work["canonical_key"] = merge_by_duration(work)
    return work


def raw_to_canonical_map(df: pd.DataFrame) -> dict[str, str]:
    """video_id -> the representative video_id `collapse()` would keep for it.

    `collapse()`'s return value keeps one row per `canonical_key` group (the
    representative) and discards the rest. A caller that needs to know what a
    *specific* raw upload canonicalises to - not just the final collapsed
    frame - needs this instead: every `video_id` in `df` is a key here,
    mapped to its group's representative, including representatives
    themselves (mapped to their own id).

    Same derivation `collapse()` uses (`_canonicalise`, then the identical
    sort + `groupby().first()` `collapse()` uses for `grouped.head(1)`), so
    the two agree by construction rather than by coincidence.
    """
    if df.empty:
        return {}
    work = _canonicalise(df)
    ordered = work.sort_values(
        ["canonical_key", "play_count", "video_id"], ascending=[True, False, True]
    )
    rep_by_key = ordered.groupby("canonical_key", sort=False)["video_id"].first()
    return dict(zip(work["video_id"], work["canonical_key"].map(rep_by_key)))


def collapse(df: pd.DataFrame) -> pd.DataFrame:
    """One row per song. Play counts sum; the most-played upload represents it.

    The representative must be a real `video_id` — the writer inserts it.
    """
    if df.empty:
        return df.assign(variants=pd.Series(dtype="int64"))

    work = _canonicalise(df)
    work = work.sort_values(
        ["canonical_key", "play_count", "video_id"], ascending=[True, False, True]
    )

    grouped = work.groupby("canonical_key", sort=False)
    representative = grouped.head(1).set_index("canonical_key")

    totals = grouped.agg(
        play_count=("play_count", "sum"),
        variants=("video_id", "size"),
        last_played=("last_played", "max"),
        first_played=("first_played", "min"),
    )

    out = representative.drop(
        columns=[c for c in ("play_count", "last_played", "first_played")
                 if c in representative.columns]
    ).join(totals)

    if "is_music" in work.columns:
        out["is_music"] = grouped["is_music"].any()
    return out.reset_index(drop=True)


def collapse_report(df: pd.DataFrame) -> dict:
    """How much merging happened, and where it might have gone too far."""
    work = add_canonical_key(df)
    sizes = work.groupby("canonical_key").size()
    multi = sizes[sizes > 1]

    biggest_key = sizes.idxmax()
    biggest = work[work["canonical_key"] == biggest_key]

    # A group spanning several channel-derived artists is where a bad merge
    # would show up, so it is surfaced rather than buried.
    def artists(group):
        return {
            artist_from_channel(c)
            for c in group.get("channel", pd.Series(dtype=object)).dropna()
        }

    cross = []
    for key, group in work[work["canonical_key"].isin(multi.index)].groupby(
        "canonical_key"
    ):
        names = {a for a in artists(group) if a}
        if len(names) > 1:
            cross.append({"key": key, "artists": sorted(names), "n": len(group)})

    return {
        "rows_in": len(work),
        "rows_out": int(sizes.size),
        "collapsed": len(work) - int(sizes.size),
        "groups_with_duplicates": int(multi.size),
        "largest_group": int(sizes.max()),
        "largest_group_key": str(biggest_key),
        "largest_group_titles": list(biggest["title"].astype(str))[:8],
        "cross_artist_groups": sorted(cross, key=lambda g: -g["n"])[:10],
        "cross_artist_count": len(cross),
    }
