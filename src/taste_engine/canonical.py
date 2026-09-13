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
RE_FEAT = re.compile(
    r"\b(?:feat|ft|featuring|with|w)\b\.?\s.*$", re.I
)
RE_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")
RE_NONWORD = re.compile(r"[^a-z0-9\s]")
RE_SPACES = re.compile(r"\s+")

# Things that genuinely make a recording different. If one of these appears,
# the track keeps its own identity.
RE_DISTINCT = re.compile(
    r"\b(remix|cover|instrumental|karaoke|live|acoustic|demo|mashup|"
    r"sped\s*up\s*remix|edit\s*by|vs\.?)\b",
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
    distinct_marker = bool(RE_DISTINCT.search(raw))

    text = normalise_title(raw)
    text = strip_artist_from_title(text, artist_from_channel(channel))
    text = RE_BRACKETS.sub(" ", text)
    text = RE_FEAT.sub(" ", text)
    text = RE_VARIANT.sub(" ", text)
    text = RE_NONWORD.sub(" ", text.lower())
    text = RE_SPACES.sub(" ", text).strip()

    if len(text) < 2:
        return ""

    artist = artist_from_channel(channel)
    artist = RE_NONWORD.sub(" ", str(artist).lower())
    artist = RE_SPACES.sub(" ", artist).strip()

    key = f"{artist}|{text}" if artist else f"?|{text}"
    # A remix/cover/live version keeps its own identity, tagged so it cannot
    # collide with the studio recording.
    if distinct_marker:
        key += "|" + RE_DISTINCT.search(raw).group(0).lower().strip()
    return key


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


def collapse(df: pd.DataFrame) -> pd.DataFrame:
    """One row per song. Play counts sum; the most-played upload represents it.

    The representative must be a real `video_id` — the writer inserts it.
    """
    if df.empty:
        return df.assign(variants=pd.Series(dtype="int64"))

    work = add_canonical_key(df)
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
