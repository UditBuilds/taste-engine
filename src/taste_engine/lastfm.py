"""Last.fm tag coverage - measurement only (reports/lastfm_coverage.md).

Two per-track signals already exist and are both weak: title+artist text
(embed.py) and YouTube topicCategories (classify.py's genres - 'pop' alone
covers 75% of canonical tracks, not discriminative). Last.fm's crowd-sourced
track tags are finer-grained and not derived from the artist name string;
this module measures whether they are usable on this library. It does not
feed embeddings, clustering, scoring, or the write path.

Auth: an API key in the query string (LASTFM_API_KEY from .env). No OAuth,
no signing, read-only methods only - track.getTopTags, falling back to
artist.getTopTags when the track-level lookup misses.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import config
from .canonical import RE_FEAT
from .embed import artist_from_channel, strip_artist_from_title

API_BASE = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = "taste-engine-lastfm-coverage/1 (measurement script; see CLAUDE.md)"

# Conservative: the brief asks for ~5 req/s. Retry reuses writer.py's own
# backoff constants (see call_with_retry's docstring for why it cannot reuse
# writer._call_with_retry itself).
MAX_REQUESTS_PER_SECOND = 5.0


class MissingLastfmKey(RuntimeError):
    pass


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(config.REPO_ROOT / ".env")


def get_api_key() -> str:
    _load_dotenv()
    key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not key:
        raise MissingLastfmKey(
            "LASTFM_API_KEY is not set.\n"
            "  1. https://www.last.fm/api/account/create -> create an API account\n"
            "  2. cp .env.example .env (if not already) and put the key in "
            "LASTFM_API_KEY\n"
            "track.getTopTags/artist.getTopTags are read-only and need only this "
            "key - no OAuth, no signing."
        )
    return key


# --- artist/track resolution -------------------------------------------
# "Use the canonical layer's existing artist field where it is populated" -
# there is no single such field (reports/lastfm_coverage.md SECTION 4 says
# so plainly). Three real signals exist, in descending reliability, and this
# is the priority order used:
#
#  1. library_songs.artists - a real Takeout-sourced artist string, present
#     for only ~4% of canonical tracks (by representative video_id) but the
#     highest quality when it is there. Never seen by embed.py/canonical.py.
#  2. A *recognisably artist-encoding* channel name - "X - Topic" or a VEVO
#     channel - via embed.artist_from_channel. Handles "PIXELATED KISSES"
#     from "Joji - Topic".
#  3. A leading "Artist - Track" prefix parsed off the raw title. Handles
#     "Joji - Past Won't Leave My Bed (Official Video)" uploaded to a
#     channel that is neither of the above.
#  4. The raw channel name, taken as-is, only once (3) has failed to find a
#     dash to split on. embed.artist_from_channel falls back to returning
#     the channel name unchanged for any channel it does not recognise, and
#     classify.py already documents real cases where that is correct - an
#     artist's own plainly-named channel with no Topic/VEVO marker ("Don
#     Toliver has 230 plays on a channel named simply 'Don Toliver'"). It is
#     also sometimes wrong (a compilation/reuploader channel is not an
#     artist name); that imprecision is accepted here on the same terms
#     classify.py already accepts it, and shows up honestly in the coverage
#     report's failure breakdown rather than being hidden.
#
# Priority (1) before (2): a channel can recognisably encode an artist and
# still be wrong for a collaboration/compilation track that library_songs
# names more precisely (e.g. "Drake; 21 Savage; Travis Scott").

RE_LEADING_ARTIST = re.compile(r"^\s*([^-]{1,80}?)\s+-\s+(.+)$")


def _clean(value) -> str:
    """Normalise a pandas cell to a stripped str; NaN/None become "".

    pandas stores a missing value as float('nan'), which is truthy in plain
    Python (`bool(float('nan'))` is True). embed.artist_from_channel has no
    NaN guard, so an unsanitised NaN channel comes back as the *string*
    'nan' rather than "no channel" (confirmed: 9 of 2,918 canonical tracks
    have a NaN channel - see reports/lastfm_coverage.md). Fixing that
    upstream in embed.py is out of scope for this brief (SECTION 7), so
    every input to resolve_artist_track is normalised here instead, before
    it ever reaches that function.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN is the only float != itself
        return ""
    return str(value).strip()


def _channel_recognisably_encodes_artist(channel: str | None) -> bool:
    """True only for the two conventions embed.artist_from_channel actually
    recognises ("X - Topic", VEVO) - as opposed to its bare fallback of
    returning any other channel name unchanged, which is not a reliable
    artist signal and must not be preferred over title-parsing.
    """
    if not channel:
        return False
    name = str(channel).strip()
    return name.endswith(" - Topic") or "VEVO" in name


def resolve_artist_track(
    title: str | None, channel: str | None, library_artist: str | None = None
) -> tuple[str, str]:
    """(artist, track) candidates, furniture and feat. clauses still attached.

    Callers apply `strip_release_furniture` (always) and `strip_feat`
    (second-pass only) to the track half before querying - kept as separate
    steps so each is independently testable and so pass 1 vs pass 2 stay
    distinguishable (SECTION 4 of the brief).
    """
    raw_title = _clean(title)
    channel = _clean(channel) or None
    library_artist = _clean(library_artist) or None

    if library_artist:
        # "; "-joined, up to 7 columns (db.py) - first is the lead artist,
        # same "first segment" convention canonical.strip_pipe_metadata uses.
        primary = library_artist.split(";")[0].strip()
        if primary:
            track = strip_artist_from_title(raw_title, primary)
            return primary, (track or raw_title).strip()

    if _channel_recognisably_encodes_artist(channel):
        channel_artist = artist_from_channel(channel)
        track = strip_artist_from_title(raw_title, channel_artist)
        return channel_artist, track.strip()

    m = RE_LEADING_ARTIST.match(raw_title)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    fallback_artist = artist_from_channel(channel) if channel else ""  # last resort
    if fallback_artist:
        track = strip_artist_from_title(raw_title, fallback_artist)
        return fallback_artist, track.strip()

    return "", raw_title


# Exactly the brief's list (SECTION 4), parenthesised or bracketed, nothing
# broader. Deliberately narrower than embed.normalise_title, which also
# strips feat./ft. unconditionally - reusing that would make the brief's
# two-pass feat comparison unmeasurable, since pass 1 would already have
# stripped it.
_FURNITURE_PHRASES = [
    r"official\s+music\s+video",
    r"official\s+video",
    r"official\s+audio",
    r"official\s+visuali[sz]er",
    r"visuali[sz]er",
    r"lyric\s+video",
    r"audio",
]
RE_FURNITURE = re.compile(
    r"[\(\[]\s*(?:" + "|".join(_FURNITURE_PHRASES) + r")\s*[\)\]]", re.I
)
RE_SPACES = re.compile(r"\s{2,}")


def strip_release_furniture(text: str) -> str:
    """Strip (Official Video)/(Official Music Video)/(Official Audio)/
    (Visualizer)/(Official Visualizer)/(Lyric Video)/(Audio) and their [...]
    equivalents. Leaves feat./ft. alone - see strip_feat.
    """
    if not text:
        return ""
    out = RE_FURNITURE.sub(" ", str(text))
    out = RE_SPACES.sub(" ", out)
    return out.strip(" -–—·|").strip()


def strip_feat(text: str) -> str:
    """Second-pass only: drop a trailing feat./ft./featuring clause.

    Reuses canonical.RE_FEAT rather than a second regex - see its comment
    for why it strips to end-of-string rather than just the clause.
    """
    if not text:
        return text
    out = RE_FEAT.sub(" ", text)
    out = RE_SPACES.sub(" ", out)
    return out.strip(" -–—·|").strip()


# --- HTTP transport + retry ----------------------------------------------

def _http_get(url: str, timeout: float = 15.0) -> tuple[int, str]:
    """One physical GET. Raises urllib.error.HTTPError/URLError as-is."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.status, resp.read().decode("utf-8")


def _is_retryable(exc: Exception) -> bool:
    """429 and 5xx, plus anything that never reached Last.fm.

    Mirrors writer._call_with_retry's shape - same jittered-exponential
    formula, same config.WRITE_RETRY_* constants - but cannot reuse that
    function: it is welded to YouTube's QuotaLedger (ledger.check/spend,
    config.QUOTA_COSTS keyed by YouTube method names, which raises
    UnknownMethod for anything else), and Last.fm is rate-limited, not
    quota-metered, so there is no ledger to charge here. The retryable set
    also differs on purpose: config.WRITE_RETRYABLE_STATUSES has no 429,
    and this brief requires 429 handling.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    return False


def call_with_retry(fn):
    """Jittered exponential backoff, identical formula to
    writer._call_with_retry (config.WRITE_RETRY_ATTEMPTS/_INITIAL_DELAY_S/
    _MAX_DELAY_S) - see _is_retryable for why it is reimplemented, not
    imported.
    """
    delay = config.WRITE_RETRY_INITIAL_DELAY_S
    for attempt in range(1, config.WRITE_RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - decide retry/raise, never swallow
            if not _is_retryable(exc) or attempt == config.WRITE_RETRY_ATTEMPTS:
                raise
        time.sleep(delay * (0.5 + random.random()))
        delay = min(delay * 2, config.WRITE_RETRY_MAX_DELAY_S)


class RateLimiter:
    """Caps physical calls to `per_second`, sleeping as needed. Not thread-safe."""

    def __init__(self, per_second: float = MAX_REQUESTS_PER_SECOND):
        self.min_interval = 1.0 / per_second
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


# --- API calls -------------------------------------------------------------
# Response shape confirmed against a live call before this was finalised -
# see reports/lastfm_coverage.md SECTION "observed response schema".

class LastfmResult:
    """One classified API outcome, ready to write to track_tag_lookups/track_tags."""

    __slots__ = ("status", "tags", "error_detail")

    def __init__(self, status: str, tags: list[tuple[str, int]] | None = None,
                 error_detail: str | None = None):
        self.status = status  # 'ok_tags' | 'ok_zero_tags' | 'not_found' | 'error'
        self.tags = tags or []
        self.error_detail = error_detail


def _parse_toptags(body: str, root_key: str) -> LastfmResult:
    """Classify a track.getTopTags/artist.getTopTags JSON body.

    Last.fm returns HTTP 200 with an `{"error": N, "message": ...}` body for
    a not-found lookup (error 6) as well as for other API-level errors, so
    the error/not-found distinction is made from the body, not the status
    code - confirmed by the live probe, not assumed.
    """
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        return LastfmResult("error", error_detail=f"unparseable response: {exc}")

    if "error" in payload:
        code = payload.get("error")
        message = str(payload.get("message", ""))
        if code == 6:
            return LastfmResult("not_found", error_detail=f"{code}: {message}")
        return LastfmResult("error", error_detail=f"{code}: {message}")

    root = payload.get(root_key, {})
    raw_tags = root.get("tag", [])
    if isinstance(raw_tags, dict):  # a single tag comes back as an object, not a list
        raw_tags = [raw_tags]
    tags = []
    for t in raw_tags:
        name = str(t.get("name", "")).strip()
        if not name:
            continue
        try:
            weight = int(t.get("count", 0))
        except (TypeError, ValueError):
            weight = 0
        tags.append((name, weight))

    return LastfmResult("ok_tags" if tags else "ok_zero_tags", tags=tags)


def fetch_track_tags(
    artist: str, track: str, api_key: str, limiter: RateLimiter
) -> LastfmResult:
    params = {
        "method": "track.getTopTags", "artist": artist, "track": track,
        "autocorrect": "1", "api_key": api_key, "format": "json",
    }
    url = API_BASE + "?" + urllib.parse.urlencode(params)

    def _do():
        limiter.wait()
        return _http_get(url)

    try:
        _status, body = call_with_retry(_do)
    except Exception as exc:  # noqa: BLE001 - classify, never crash the run
        return LastfmResult("error", error_detail=f"{type(exc).__name__}: {exc}")
    return _parse_toptags(body, "toptags")


def fetch_artist_tags(artist: str, api_key: str, limiter: RateLimiter) -> LastfmResult:
    params = {
        "method": "artist.getTopTags", "artist": artist,
        "autocorrect": "1", "api_key": api_key, "format": "json",
    }
    url = API_BASE + "?" + urllib.parse.urlencode(params)

    def _do():
        limiter.wait()
        return _http_get(url)

    try:
        _status, body = call_with_retry(_do)
    except Exception as exc:  # noqa: BLE001 - classify, never crash the run
        return LastfmResult("error", error_detail=f"{type(exc).__name__}: {exc}")
    return _parse_toptags(body, "toptags")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- track pool + DB orchestration -----------------------------------------

def canonical_track_pool(conn):
    """One row per canonical song: canonical_id (representative video_id),
    title, channel, library_artist. Same population README's headline
    figures use - see reports/lastfm_coverage.md SECTION 0.

    `library_artist` is joined from `library_songs.artists` on the
    representative video_id only - it will miss a track whose library entry
    survives under a different (non-representative) upload in the same
    canonical group. Measured at ~4% coverage either way; see the report.
    """
    from .score import scored_tracks

    tracks = scored_tracks(conn)
    pool = tracks.rename(columns={"video_id": "canonical_id"})[
        ["canonical_id", "title", "channel"]
    ].reset_index(drop=True)

    lib = dict(conn.execute("SELECT video_id, artists FROM library_songs").fetchall())
    pool["library_artist"] = pool["canonical_id"].map(lib)
    return pool


def _existing_status(conn, canonical_id: str, source: str, variant: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM track_tag_lookups "
        "WHERE canonical_id = ? AND source = ? AND query_variant = ?",
        (canonical_id, source, variant),
    ).fetchone()
    return row[0] if row else None


def _load_artist_cache(conn, variant: str) -> dict[str, LastfmResult]:
    """Pre-seed the in-run artist-fallback cache from any prior run's rows,
    keyed by lowercased artist, so re-running the script - or a later track
    by the same artist in this same run - does not re-hit the API. Without
    this a shallow, mostly-unmatched cluster (T-Series: 492 tracks) would
    fetch the same artist fallback hundreds of times.
    """
    cache: dict[str, LastfmResult] = {}
    for artist, status, error_detail, canonical_id in conn.execute(
        "SELECT query_artist, status, error_detail, canonical_id FROM track_tag_lookups "
        "WHERE source = 'artist' AND query_variant = ? ORDER BY fetched_at",
        (variant,),
    ).fetchall():
        key = artist.lower()
        if key in cache:
            continue
        if status in ("ok_tags", "ok_zero_tags"):
            tag_rows = conn.execute(
                "SELECT tag, weight FROM track_tags WHERE canonical_id = ? AND source = 'artist'",
                (canonical_id,),
            ).fetchall()
            cache[key] = LastfmResult(status, tags=[(t, w) for t, w in tag_rows])
        else:
            cache[key] = LastfmResult(status, error_detail=error_detail)
    return cache


def _store(conn, canonical_id, source, variant, query_artist, query_track,
           result: LastfmResult) -> None:
    fetched = now_iso()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO track_tag_lookups "
            "(canonical_id, source, query_variant, status, query_artist, query_track, "
            " error_detail, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (canonical_id, source, variant, result.status, query_artist or "",
             query_track, result.error_detail, fetched),
        )
        for tag, weight in result.tags:
            conn.execute(
                "INSERT OR REPLACE INTO track_tags "
                "(canonical_id, tag, weight, source, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (canonical_id, tag, weight, source, fetched),
            )


def run_coverage_fetch(
    conn,
    api_key: str,
    *,
    variant: str = "feat_kept",
    only_canonical_ids=None,
    limiter: RateLimiter | None = None,
    progress_every: int = 200,
) -> dict:
    """Fetch and cache track-level tags, falling back to artist-level, for
    every canonical track not yet attempted under this (source, variant).
    Idempotent: a canonical_id already in track_tag_lookups for this
    (source, variant) is skipped, not re-fetched - that is the whole
    cache-hit story.
    """
    limiter = limiter or RateLimiter()
    pool = canonical_track_pool(conn)
    if only_canonical_ids is not None:
        pool = pool[pool["canonical_id"].isin(set(only_canonical_ids))]

    artist_cache = _load_artist_cache(conn, variant)
    counts: dict[str, int] = {"skipped_cached": 0, "artist_calls_saved_by_cache": 0}

    def bump(key):
        counts[key] = counts.get(key, 0) + 1

    total = len(pool)
    for i, row in enumerate(pool.itertuples(index=False), start=1):
        canonical_id, title, channel = row.canonical_id, row.title, row.channel
        library_artist = getattr(row, "library_artist", None)

        if _existing_status(conn, canonical_id, "track", variant) is not None:
            counts["skipped_cached"] += 1
            continue

        artist, track = resolve_artist_track(title, channel, library_artist)
        track_query = strip_release_furniture(track)
        if variant == "feat_stripped":
            track_query = strip_feat(track_query)

        if not artist or not track_query:
            _store(conn, canonical_id, "track", variant, artist, track_query,
                   LastfmResult("unresolved", error_detail="empty artist or track after parsing"))
            bump("track_unresolved")
            if progress_every and i % progress_every == 0:
                print(f"  {i:,}/{total:,} canonical tracks processed", flush=True)
            continue

        result = fetch_track_tags(artist, track_query, api_key, limiter)
        _store(conn, canonical_id, "track", variant, artist, track_query, result)
        bump(f"track_{result.status}")

        if result.status in ("not_found", "error") and \
                _existing_status(conn, canonical_id, "artist", variant) is None:
            key = artist.lower()
            cached = artist_cache.get(key)
            if cached is not None:
                counts["artist_calls_saved_by_cache"] += 1
                aresult = cached
            else:
                aresult = fetch_artist_tags(artist, api_key, limiter)
                artist_cache[key] = aresult
            _store(conn, canonical_id, "artist", variant, artist, None, aresult)
            bump(f"artist_{aresult.status}")

        if progress_every and i % progress_every == 0:
            print(f"  {i:,}/{total:,} canonical tracks processed", flush=True)

    return counts
