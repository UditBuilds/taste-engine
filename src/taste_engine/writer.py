"""Phase 4 - write a playlist back to YouTube, inside the quota.

The cost model is the design:

    playlists.insert         50 units
    playlistItems.insert     50 units *per track*
    playlistItems.list        1 unit  (verification)

    a 50-track playlist  =  50 + 50x50 + 1  =  **2,551 units**

That is roughly a third of the 8,000-unit daily cap, so this can write about
one playlist a day and a mistake is expensive to undo. Three consequences,
all of them load-bearing rather than decorative:

* **Dry-run is the default.** `--commit` is required to spend anything.
* **Resume is not optional.** Quota can run out mid-playlist, so every accepted
  track is recorded as it lands and a re-run skips what is already there.
* **The write verifies itself.** `playlistItems.list` costs 1 unit against a
  2,550-unit write; not checking would be false economy.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config
from .embed import tidy_genres
from .quota import QuotaExceeded, QuotaLedger

CREATE_METHOD = "playlists.insert"
INSERT_METHOD = "playlistItems.insert"
LIST_METHOD = "playlistItems.list"
DELETE_METHOD = "playlists.delete"

STATUS_PENDING = "pending"
STATUS_PARTIAL = "partial"
STATUS_COMPLETE = "complete"
STATUS_MISMATCH = "mismatch"
STATUS_ROLLED_BACK = "rolled_back"


class WriteBlocked(RuntimeError):
    """The write cannot start or continue. Never raised mid-insert silently."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- planning ---------------------------------------------------------------

MODE_REDISCOVER = "rediscover"
MODE_TOP = "top"
MODES = (MODE_REDISCOVER, MODE_TOP)


def _target_length(native: int) -> int:
    """floor(native / (1 - MAX_BACKFILL_SHARE)) - the whole length rule.

    Backfill share is capped by construction: share = 1 - native/target, and
    target <= native/(1 - MAX_BACKFILL_SHARE) because floor() only ever
    rounds down, so share <= MAX_BACKFILL_SHARE always (equality exactly at
    native = MIN_CLUSTER_NATIVE with the shipped constants: 12 -> 16).
    """
    return math.floor(native / (1 - config.MAX_BACKFILL_SHARE))


def _modal_genre(genre_lists) -> tuple[str | None, int]:
    """(modal_genre, n_labeled) by plurality vote over tidied genre labels.

    Same definition reports/genre_coverage.md used: each labeled member votes
    once per distinct label it carries (`set(gl)`, so a track with the same
    label twice cannot inflate it), the label with the most votes wins.

    Ties are broken deterministically at SELECTION time - highest count
    first, then alphabetically-first label - via `min(counts.items(), key=
    lambda kv: (-kv[1], kv[0]))`. This deliberately does NOT use
    `Counter.most_common(1)`: that resolves a tie by dict-insertion order,
    which traces back to iterating `set(gl)` above, and Python randomises
    string hashing per process by default - so `most_common(1)`'s tie-break
    is not stable across process runs, only within one.

    FIXED 2026-09-14, per Udit, after being found live on this corpus, not
    hypothetical: two qualifying clusters carry an exact vote tie for the
    top spot, Metro Boomin ("hip hop" vs "pop", 26-26) and T-Series ("music
    of asia" vs "pop", 21-21). Before this fix, `_modal_genre` fed GUARD
    (`_select_with_backfill`, the actual `writer.plan()` / `--commit` path)
    a genre that depended on nothing more principled than the process's hash
    seed - confirmed empirically, 10 separate process runs split Metro
    Boomin's tie 5/5. See reports/backfill_plan.md's "Distance ranking"
    section for what each side of that tie used to ship. This fix's
    alphabetical rule happens to prefer "hip hop" and "music of asia" over
    "pop" for these two clusters (h, m < p) - a consequence of the rule, not
    a reason for it; the rule was fixed (highest count, then alphabetical)
    before checking what it would give either cluster.
    genre_coverage.md's "0 of 37 clusters ambiguous" is not contradicted by
    any of this - it defines ambiguous as "no label above 50% of labeled
    eligible members" (its line 117), which both labels clear simultaneously
    in an exact tie like this one, so that check was never designed to catch
    this case; it is a real gap in that check, not a wrong number there.

    `None, 0` when no member carries any label at all.
    """
    labeled = [gl for gl in genre_lists if gl]
    if not labeled:
        return None, 0
    counts: Counter[str] = Counter()
    for gl in labeled:
        counts.update(set(gl))
    modal_genre, _ = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return modal_genre, len(labeled)


def _reduced_embeddings(real_frame: pd.DataFrame) -> np.ndarray:
    """PCA-reduced embedding per row of `real_frame`, positionally aligned.

    `embed.reduce_dims` fits a fresh PCA on whatever matrix it is given, so
    two calls over two different row-sets land in incomparable spaces - a
    centroid computed from one fit and a track vector from another would
    yield cosine distances that look fine but mean nothing. Every caller
    that needs centroids or individual track vectors to be comparable must
    go through this one function over the same `real_frame`, which is why
    `_cluster_centroids` sources from it rather than embedding on its own.

    Row `i` of the returned array corresponds to row `i` of
    `real_frame.reset_index(drop=True)` (`embed_text` is read via `list(...)`,
    which iterates in that same order).
    """
    from . import embed

    texts = list(real_frame["embed_text"])
    vectors = embed.embed_texts(texts, use_cache=True)
    return embed.reduce_dims(vectors)


def _cluster_centroids(
    real_frame: pd.DataFrame, reduced: np.ndarray | None = None
) -> dict[int, np.ndarray]:
    """Mean PCA-reduced embedding per real (non-noise) cluster.

    Sourced from `_reduced_embeddings` re-derived locally from the cached
    MiniLM embeddings already computed for this corpus - `embed_texts` keys
    its cache by the exact text list, so this is a cache hit (measured:
    ~0.05s for the full library), not a re-embed. That keeps the backfill's
    notion of "nearest" local to this function and `_reduced_embeddings`
    rather than threading reduced vectors through `recommend.build()`'s
    contract and every caller of it, `evaluate.py` included.

    `reduced` lets a caller that also needs individual track vectors (see
    `_distances_to_centroid`) pass in one shared `_reduced_embeddings` result
    instead of each computing its own: two separate calls would each fit a
    fresh PCA (`embed.reduce_dims` has no cache), landing centroids and
    per-track vectors in two different - and mutually incomparable - spaces.
    Passing the same array through is what makes "one fit" structural rather
    than merely true by coincidence of identical, deterministic inputs.
    """
    if reduced is None:
        reduced = _reduced_embeddings(real_frame)
    positions = np.asarray(real_frame["cluster"])
    centroids: dict[int, np.ndarray] = {}
    for cid in np.unique(positions):
        centroids[int(cid)] = reduced[positions == cid].mean(axis=0)
    return centroids


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = a / max(float(np.linalg.norm(a)), 1e-12)
    b_norm = b / max(float(np.linalg.norm(b)), 1e-12)
    return 1.0 - float(np.dot(a_norm, b_norm))


def _distances_to_centroid(
    real_frame: pd.DataFrame,
    candidate_ids: pd.Series,
    centroid: np.ndarray,
    reduced: np.ndarray | None = None,
) -> dict[str, float]:
    """Cosine distance from each of `candidate_ids`' own reduced embedding to
    `centroid`, in the same PCA-fitted space `_cluster_centroids` used to
    compute it - literally the same array when the caller passes `reduced`
    through from a single shared `_reduced_embeddings(real_frame)` call,
    rather than each function fitting its own PCA over the same rows.

    `candidate_ids` are `video_id`s, not positions - the candidate pool is an
    arbitrary, already-filtered subset of `real_frame` (post genre-guard), so
    row order cannot be assumed to match. Restricted to `candidate_ids` after
    reducing the *whole* `real_frame` rather than reducing just the pool,
    which is exactly the incomparable-PCA-fit trap `_reduced_embeddings`
    exists to avoid.
    """
    if reduced is None:
        reduced = _reduced_embeddings(real_frame)
    ids = list(real_frame["video_id"])
    wanted = set(candidate_ids)
    return {
        vid: _cosine_distance(vec, centroid)
        for vid, vec in zip(ids, reduced)
        if vid in wanted
    }


def _select_with_backfill(
    frame: pd.DataFrame, cluster: int
) -> tuple[pd.DataFrame, int, list[tuple[int, str, int]], str | None, int]:
    """Fill a cluster's native tracks up to a genre-guarded target length.

    FLOOR is enforced by the caller (`plan()`) before this runs. LENGTH:
    target = `_target_length(native)`. GUARD: a backfill candidate must carry
    the cluster's modal genre among its own tidied genre labels - this FILTERS
    the candidate pool and never changes. RANK: within that filtered pool,
    individual candidates are ranked by cosine distance (in the same
    PCA-reduced embedding space HDBSCAN clustered in) to the *requesting*
    cluster's own centroid, ascending - not by score, and not by nearest
    *whole cluster* (`_clusters_by_distance`, briefs/backfill_rank.md's
    predecessor, was too coarse: it made every cluster's backfill identical
    to every other cluster's, since ranking a candidate's *own* cluster
    rather than the candidate itself throws away all per-track information).
    Ties: (distance asc, score desc, video_id asc). CEILING: a candidate at
    or above `config.MAX_BACKFILL_DISTANCE` is dropped outright, even when it
    is the only genre match - see that constant's comment for why 1.0 is a
    geometric bound (cosine distance > 1.0 is negative similarity), not a
    value tuned to any specific track. No modal genre (native block entirely
    unlabeled), no genre-matching candidates, or no candidate under the
    ceiling all resolve the same way: fewer tracks, never a track the guard
    or the ceiling would otherwise have refused.

    Returns `(tracks, native_count, backfill_summary, modal_genre,
    target_length)`, where `backfill_summary` is one `(cluster_id,
    cluster_name, n_taken)` per outside cluster actually drawn from, grouped
    in the order its tracks first appear in the distance-ranked backfill
    block - empty when the cluster had enough on its own.
    """
    real = frame[frame["cluster"] >= 0]
    eligible = real[real["score"] >= config.MIN_SCORE]

    def _ranked(pool: pd.DataFrame) -> pd.DataFrame:
        return pool.sort_values(["score", "video_id"], ascending=[False, True])

    native = _ranked(eligible[eligible["cluster"] == cluster])
    native_count = len(native)
    target_length = _target_length(native_count)
    deficit = target_length - native_count
    if deficit <= 0:
        picked = native.reset_index(drop=True)
        picked["distance"] = float("nan")
        return picked, native_count, [], None, target_length

    modal_genre, _ = _modal_genre(native["genres"].map(tidy_genres))

    summary: list[tuple[int, str, int]] = []
    if modal_genre is None:
        backfill = native.iloc[0:0].copy()
        backfill["distance"] = pd.Series(dtype="float64")
    else:
        outside = eligible[eligible["cluster"] != cluster].copy()
        outside["genres_tidy"] = outside["genres"].map(tidy_genres)
        # .astype(bool): a *zero-length* pool (single-cluster frame, nothing
        # outside to backfill from) makes .map() return dtype=object rather
        # than bool - pandas then treats an empty object-dtype mask as an
        # (empty) list of column labels, not an all-false row mask, and
        # silently returns a same-row, zero-COLUMN frame. Cast explicitly so
        # this stays a row mask no matter how many rows it started from.
        mask = outside["genres_tidy"].map(lambda gl: modal_genre in gl).astype(bool)
        matching = outside[mask]
        if matching.empty:
            backfill = matching.copy()
            backfill["distance"] = pd.Series(dtype="float64")
        else:
            # One shared PCA fit for both the centroid and the individual
            # candidate vectors - see _reduced_embeddings's docstring for why
            # two separate calls here would silently land them in different,
            # incomparable spaces.
            reduced = _reduced_embeddings(real)
            centroid = _cluster_centroids(real, reduced)[cluster]
            distances = _distances_to_centroid(real, matching["video_id"], centroid, reduced)
            matching = matching.copy()
            matching["distance"] = matching["video_id"].map(distances)
            # CEILING: dropped before ranking, not truncated after - a
            # candidate at or above config.MAX_BACKFILL_DISTANCE is never a
            # candidate at all, so it can't be admitted even as the sole
            # genre match with nothing to rank against.
            matching = matching[matching["distance"] < config.MAX_BACKFILL_DISTANCE]
            backfill = matching.sort_values(
                ["distance", "score", "video_id"], ascending=[True, False, True]
            ).head(deficit)
        for other, take in backfill.groupby("cluster", sort=False):
            summary.append((int(other), str(take["cluster_name"].iloc[0]), len(take)))

    native = native.copy()
    native["distance"] = float("nan")
    picked = pd.concat([native, backfill]).reset_index(drop=True)
    return picked, native_count, summary, modal_genre, target_length


def plan(
    conn: sqlite3.Connection,
    cluster: int | None = None,
    limit: int | None = None,
    half_life: float | None = None,
    tracks: pd.DataFrame | None = None,
    mode: str = MODE_REDISCOVER,
    exclude_top: int | None = None,
    cluster_name: str | None = None,
) -> dict:
    """Choose the tracks and price the write. Spends nothing.

    `mode` decides which task the playlist is actually doing:

    * **rediscover** (default) removes the library's most-played songs first,
      exactly as `evaluate.rediscovery_split` does, so the playlist is drawn
      from the pool the evaluation scores. Both call `recommend.favourites`.
    * **top** ranks everything, favourites included. That is the *replay*
      task - the one the README argues is trivial and that the most-played
      baseline wins - so it is available but not the default.

    Shipping `top` while reporting a rediscovery number would mean the
    evaluation and the product were measuring different things.
    """
    if mode not in MODES:
        raise WriteBlocked(f"unknown mode {mode!r}; choose from {list(MODES)}")
    if limit is not None and (cluster is not None or cluster_name):
        raise WriteBlocked(
            "--limit does not apply to a cluster-scoped write: playlist "
            "length is computed from cluster depth (config.MIN_CLUSTER_NATIVE "
            "/ config.MAX_BACKFILL_SHARE), not requested. Drop --limit, or "
            "drop --cluster/--cluster-name for a plain top-N playlist."
        )

    excluded_count = 0
    requested_cluster_name = None
    native_count = None
    modal_genre = None
    target_length = None
    backfill_summary: list[tuple[int, str, int]] = []
    if tracks is None:
        from .recommend import build, favourites

        frame = build(conn, half_life=half_life)
        if mode == MODE_REDISCOVER:
            # Global, before the cluster filter - the eval excludes the
            # library's favourites, not each cluster's. This is also the
            # pool backfill draws from: filtering once, up front, means a
            # backfilled track can no more be a favourite than a native one.
            obvious = favourites(frame, exclude_top)
            excluded_count = len(obvious)
            frame = frame[~frame["video_id"].isin(obvious)]
        if cluster_name:
            # Cluster ids are reassigned whenever the input set changes -
            # enabling STRICT_MUSIC moved this library's Hindi-film cluster
            # from 24 to 11. Names are derived from top artists and are stable,
            # so they are the safer handle for anything written down.
            match = frame[
                frame["cluster_name"].fillna("").str.contains(
                    cluster_name, case=False, regex=False
                )
                & (frame["cluster"] >= 0)
            ]
            if match.empty:
                raise WriteBlocked(f"no cluster matching name {cluster_name!r}")
            cluster = int(match["cluster"].value_counts().idxmax())
        if cluster is not None:
            cluster_frame = frame[frame["cluster"] == cluster]
            if cluster_frame.empty:
                raise WriteBlocked(
                    f"cluster {cluster} has no tracks"
                    + (" left after excluding favourites" if excluded_count else "")
                )
            # Pinned before backfill can touch row 0: a shallow cluster with
            # zero eligible tracks of its own would otherwise title the
            # playlist after whichever neighbour it borrowed from first.
            requested_cluster_name = str(cluster_frame["cluster_name"].iloc[0])
            native_eligible = len(
                cluster_frame[cluster_frame["score"] >= config.MIN_SCORE]
            )
            if native_eligible < config.MIN_CLUSTER_NATIVE:
                raise WriteBlocked(
                    f"cluster {cluster} ({requested_cluster_name!r}) has "
                    f"{native_eligible} eligible tracks, below the floor of "
                    f"{config.MIN_CLUSTER_NATIVE} (config.MIN_CLUSTER_NATIVE) "
                    "- no playlist generated"
                )
            tracks, native_count, backfill_summary, modal_genre, target_length = (
                _select_with_backfill(frame, cluster)
            )
        else:
            effective_limit = 50 if limit is None else limit
            frame = frame.sort_values(["score", "video_id"], ascending=[False, True])
            tracks = frame.head(effective_limit).reset_index(drop=True)

    name = "playlist"
    if cluster is not None:
        name = requested_cluster_name or name
    elif "cluster_name" in tracks.columns and len(tracks):
        name = str(tracks["cluster_name"].iloc[0])

    n = len(tracks)
    backfilled_count = n - native_count if native_count is not None else 0
    costs = config.QUOTA_COSTS
    units = costs[CREATE_METHOD] + costs[INSERT_METHOD] * n + costs[LIST_METHOD]
    return {
        "cluster": cluster,
        "mode": mode,
        "excluded_favourites": excluded_count,
        "title": f"taste-engine: {name}"
        + (" (rediscover)" if mode == MODE_REDISCOVER else ""),
        "description": (
            "Generated by taste-engine from 363 days of listening history, "
            "ranked by log1p(play count) x recency decay"
            + (
                f", with the {excluded_count} most-played songs excluded so the "
                "playlist matches the rediscovery task the model is evaluated on"
                if mode == MODE_REDISCOVER
                else ", favourites included"
            )
            + ". https://github.com/UditBuilds/taste-engine"
        ),
        "tracks": tracks,
        "count": n,
        "units": units,
        "native_count": native_count,
        "backfilled_count": backfilled_count,
        "backfill_by_cluster": backfill_summary,
        "modal_genre": modal_genre,
        "target_length": target_length,
        "shortfall": max(0, target_length - n) if target_length is not None else 0,
        "breakdown": {
            CREATE_METHOD: costs[CREATE_METHOD],
            INSERT_METHOD: costs[INSERT_METHOD] * n,
            LIST_METHOD: costs[LIST_METHOD],
        },
    }


def render_plan(p: dict, ledger: QuotaLedger | None = None) -> str:
    lines = [
        f"DRY RUN - nothing will be written without --commit",
        "",
        f"  playlist   {p['title']}",
        f"  privacy    private",
        f"  mode       {p.get('mode', MODE_REDISCOVER)}"
        + (f"   ({p['excluded_favourites']} most-played songs excluded, "
           "matching the eval)" if p.get("excluded_favourites") else ""),
    ]
    if p.get("target_length") is not None:
        lines.append(
            f"  length     {p['target_length']} = floor({p['native_count']} native / "
            f"(1 - {config.MAX_BACKFILL_SHARE}))"
        )
        lines.append(
            f"  modal genre {p['modal_genre']!r}" if p["modal_genre"]
            else "  modal genre none - native block carries no genre label"
        )
    lines.append(
        f"  tracks     {p['count']}"
        + (f"   ({p['shortfall']} short of the {p['target_length']} target - "
           "not enough genre-matching backfill material, guard not relaxed)"
           if p.get("shortfall") else "")
    )
    if p.get("native_count") is not None:
        n_neighbours = len(p["backfill_by_cluster"])
        lines.append(
            f"  provenance {p['native_count']} native, {p['backfilled_count']} "
            f"backfilled from {n_neighbours} neighbouring "
            f"cluster{'s' if n_neighbours != 1 else ''}"
        )
        for cid, cname, count in p["backfill_by_cluster"]:
            lines.append(f"             {count:>3} from cluster {cid} ({cname})")
    lines += [
        "",
        "  quota cost",
        f"    {CREATE_METHOD:<24}{p['breakdown'][CREATE_METHOD]:>7,}",
        f"    {INSERT_METHOD:<24}{p['breakdown'][INSERT_METHOD]:>7,}"
        f"   ({p['count']} x {config.QUOTA_COSTS[INSERT_METHOD]})",
        f"    {LIST_METHOD:<24}{p['breakdown'][LIST_METHOD]:>7,}   (verification)",
        f"    {'TOTAL':<24}{p['units']:>7,}   (floor - a retry can add up to "
        f"{(config.WRITE_RETRY_ATTEMPTS - 1) * config.QUOTA_COSTS[INSERT_METHOD]}/track)",
    ]
    if ledger is not None:
        remaining = ledger.remaining()
        lines += [
            f"    {'remaining today':<24}{remaining:>7,}",
            f"    {'after this write':<24}{remaining - p['units']:>7,}",
        ]
        if p["units"] > remaining:
            lines.append("\n  REFUSED: this exceeds today's remaining quota.")
    lines.append("")
    requested_cluster = p.get("cluster")
    for i, row in p["tracks"].iterrows():
        title = str(row.get("title") or row["video_id"])[:58]
        score = row.get("score")
        tag = ""
        if requested_cluster is not None and row.get("cluster") != requested_cluster:
            genre = p.get("modal_genre")
            via = row.get("cluster_name", row.get("cluster"))
            distance = row.get("distance")
            dist_part = (
                f", d={distance:.3f}" if distance is not None and not pd.isna(distance) else ""
            )
            tag = (
                f"  [backfill: {genre} via {via}{dist_part}]" if genre
                else f"  [backfill: {via}{dist_part}]"
            )
        lines.append(
            f"  {i + 1:>3}. {title:<58} {score:.3f}{tag}" if score is not None
            else f"  {i + 1:>3}. {title}{tag}"
        )
    return "\n".join(lines)


# --- bookkeeping ------------------------------------------------------------

def _create_row(conn: sqlite3.Connection, p: dict, privacy: str = "private") -> int:
    cur = conn.execute(
        "INSERT INTO written_playlists "
        "(playlist_id, title, description, cluster, privacy, status, planned, "
        " planned_ids, written, units_spent, created_at, updated_at) "
        "VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
        (p["title"], p["description"], p["cluster"], privacy, STATUS_PENDING,
         p["count"], json.dumps(list(p["tracks"]["video_id"])), _now(), _now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def plan_from_row(conn: sqlite3.Connection, row_id: int) -> dict:
    """Rebuild the exact plan a row was created with, for --resume.

    Re-running the recommender would be close but not guaranteed identical;
    resuming into a *different* track list would silently produce a playlist
    that matches neither plan.
    """
    row = get_row(conn, row_id)
    ids = json.loads(row["planned_ids"] or "[]")
    if not ids:
        raise WriteBlocked(
            f"row {row_id} has no stored track list; it predates planned_ids "
            "and cannot be resumed safely"
        )
    titles = dict(
        conn.execute(
            "SELECT video_id, MAX(title) FROM plays WHERE video_id IN "
            f"({','.join('?' * len(ids))}) GROUP BY video_id", ids
        ).fetchall()
    )
    tracks = pd.DataFrame(
        {"video_id": ids, "title": [titles.get(v, v) for v in ids]}
    )
    costs = config.QUOTA_COSTS
    n = len(tracks)
    return {
        "cluster": row["cluster"],
        "title": row["title"],
        "description": row["description"],
        "tracks": tracks,
        "count": n,
        "units": costs[CREATE_METHOD] + costs[INSERT_METHOD] * n + costs[LIST_METHOD],
        "breakdown": {
            CREATE_METHOD: costs[CREATE_METHOD],
            INSERT_METHOD: costs[INSERT_METHOD] * n,
            LIST_METHOD: costs[LIST_METHOD],
        },
    }


def _set(conn: sqlite3.Connection, row_id: int, **fields) -> None:
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE written_playlists SET {assignments} WHERE id = ?",
        (*fields.values(), row_id),
    )
    conn.commit()


def get_row(conn: sqlite3.Connection, row_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM written_playlists WHERE id = ?", (row_id,)
    ).fetchone()
    if row is None:
        raise WriteBlocked(f"no written_playlists row with id {row_id}")
    return row


def already_written(conn: sqlite3.Connection, row_id: int) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT video_id FROM written_tracks WHERE playlist_row = ?", (row_id,)
        )
    }


def list_written(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT id, status, written, planned, privacy, title, playlist_id, "
        "units_spent, updated_at FROM written_playlists ORDER BY id",
        conn,
    )


# --- the write ---------------------------------------------------------------

def _insert_track(service, playlist_id: str, video_id: str, position: int):
    return service.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "position": position,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()


def _status_of(exc: Exception) -> int | None:
    return getattr(getattr(exc, "resp", None), "status", None)


def _is_quota_error(exc: Exception) -> bool:
    return _status_of(exc) == 403 and "quota" in str(exc).lower()


def _is_retryable(exc: Exception) -> bool:
    """409/500/502/503/504 and anything that never reached Google.

    403 quotaExceeded and 401 are deliberately excluded even though neither
    appears in `WRITE_RETRYABLE_STATUSES`: no delay creates quota, and no
    delay refreshes a token a human hasn't reauthorised.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return _status_of(exc) in config.WRITE_RETRYABLE_STATUSES


def _call_with_retry(fn, *, ledger: QuotaLedger, method: str, note: str):
    """Call `fn()`, retrying transient failures with jittered backoff.

    Every physical attempt is charged before it runs, success or not:
    `quota.py`'s own rule is that a response Google sent back - even an
    error - has already been billed, so a retry that skipped paying for its
    earlier attempts would under-count real spend, the direction that risks
    overrunning the actual daily cap rather than just this ledger's copy of
    it. A socket/connection error that never reached Google is the one case
    `QuotaLedger.spend` refunds on its own.

    `QuotaExceeded` (this ledger's own pre-flight guard, not an API response)
    propagates on the first attempt it appears - retrying it would just spend
    down quota `check()` already said we don't have.
    """
    delay = config.WRITE_RETRY_INITIAL_DELAY_S
    for attempt in range(1, config.WRITE_RETRY_ATTEMPTS + 1):
        ledger.check(method)
        try:
            with ledger.spend(method, note=f"{note} try {attempt}"):
                return fn()
        except Exception as exc:  # noqa: BLE001 - decide retry/raise, never swallow
            if not _is_retryable(exc) or attempt == config.WRITE_RETRY_ATTEMPTS:
                raise
        time.sleep(delay * (0.5 + random.random()))
        delay = min(delay * 2, config.WRITE_RETRY_MAX_DELAY_S)


def execute_write(
    conn: sqlite3.Connection,
    service,
    ledger: QuotaLedger,
    p: dict,
    row_id: int | None = None,
    verify_after: bool = True,
    privacy: str = "private",
) -> dict:
    """Create (or resume) the playlist and insert every outstanding track.

    Returns a report; raises only for conditions that make progress
    impossible. Quota exhaustion is *not* an exception - it is a partial
    result, persisted and reported.
    """
    tracks = p["tracks"]

    if row_id is None:
        row_id = _create_row(conn, p, privacy=privacy)
    row = get_row(conn, row_id)

    if row["status"] == STATUS_ROLLED_BACK:
        raise WriteBlocked(f"playlist row {row_id} was rolled back; start a new write")

    playlist_id = row["playlist_id"]
    units = int(row["units_spent"])

    # --- create the remote playlist, unless resuming one that exists ---
    if not playlist_id:
        try:
            created = _call_with_retry(
                lambda: service.playlists().insert(
                    part="snippet,status",
                    body={
                        "snippet": {"title": p["title"], "description": p["description"]},
                        "status": {"privacyStatus": row["privacy"]},
                    },
                ).execute(),
                ledger=ledger, method=CREATE_METHOD, note=f"playlist row {row_id}",
            )
        except QuotaExceeded as exc:
            _set(conn, row_id, status=STATUS_PENDING)
            raise WriteBlocked(f"not enough quota to create the playlist: {exc}") from None
        except Exception as exc:  # noqa: BLE001 - creation failed even after retries
            _set(conn, row_id, status=STATUS_PENDING)
            raise WriteBlocked(
                f"could not create the playlist for row {row_id}: {exc}"
            ) from exc
        playlist_id = created["id"]
        units += config.QUOTA_COSTS[CREATE_METHOD]
        _set(conn, row_id, playlist_id=playlist_id, units_spent=units,
             status=STATUS_PARTIAL)

    # --- insert whatever is still missing ---
    done = already_written(conn, row_id)
    outstanding = [
        (i, r) for i, r in enumerate(tracks.itertuples())
        if r.video_id not in done
    ]
    skipped = len(tracks) - len(outstanding)

    written = len(done)
    stopped = None
    for position, track in outstanding:
        try:
            item = _call_with_retry(
                lambda: _insert_track(service, playlist_id, track.video_id, position),
                ledger=ledger, method=INSERT_METHOD, note=f"row {row_id} pos {position}",
            )
            # Record immediately, before bumping the counters below: a resume
            # reads written_tracks (not this row's `written` column), so the
            # two must never be allowed to say something different happened.
            conn.execute(
                "INSERT OR REPLACE INTO written_tracks "
                "(playlist_row, video_id, position, item_id, written_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (row_id, track.video_id, position, (item or {}).get("id"), _now()),
            )
            conn.commit()
            units += config.QUOTA_COSTS[INSERT_METHOD]
            written += 1
            _set(conn, row_id, written=written, units_spent=units)
        except QuotaExceeded as exc:
            stopped = str(exc)
            break
        except Exception as exc:  # noqa: BLE001 - any insert failure ends the write
            # cleanly rather than crashing: retries exhausted, a non-retryable
            # status, or something wholly unanticipated all land here and
            # leave a resumable partial through the status update below,
            # exactly like quota exhaustion always has. General, not
            # quota-specific - that generality is the fix.
            stopped = (
                f"API returned quotaExceeded: {exc}" if _is_quota_error(exc)
                else f"insert of {track.video_id} at position {position} failed: {exc}"
            )
            break

    complete = written >= len(tracks)
    _set(conn, row_id,
         status=STATUS_COMPLETE if complete else STATUS_PARTIAL,
         written=written, units_spent=units)

    report = {
        "row_id": row_id,
        "playlist_id": playlist_id,
        "url": f"https://www.youtube.com/playlist?list={playlist_id}",
        "planned": len(tracks),
        "written": written,
        "skipped_already_present": skipped,
        "units_spent": units,
        "stopped": stopped,
        "status": STATUS_COMPLETE if complete else STATUS_PARTIAL,
        "verified": None,
    }

    if complete and verify_after:
        report["verified"] = verify(conn, service, ledger, row_id)
        report["status"] = get_row(conn, row_id)["status"]
    return report


def verify(conn: sqlite3.Connection, service, ledger: QuotaLedger, row_id: int) -> dict:
    """Ask YouTube how many items the playlist actually holds.

    One unit against a 2,550-unit write. A write that reports success without
    checking has not finished.
    """
    row = get_row(conn, row_id)
    if not row["playlist_id"]:
        raise WriteBlocked(f"row {row_id} has no remote playlist to verify")

    remote = 0
    page = None
    try:
        while True:
            response = _call_with_retry(
                lambda: service.playlistItems().list(
                    part="id", playlistId=row["playlist_id"], maxResults=50,
                    **({"pageToken": page} if page else {}),
                ).execute(),
                ledger=ledger, method=LIST_METHOD, note=f"verify row {row_id}",
            )
            remote += len(response.get("items", []))
            page = response.get("nextPageToken")
            if not page:
                break
    except QuotaExceeded:
        reason = "no quota left to verify" if remote == 0 else "quota ran out mid-verification"
        return {"checked": False, "reason": reason}
    except Exception as exc:  # noqa: BLE001 - a failed verification isn't a failed write
        return {"checked": False, "reason": f"verification call failed: {exc}"}

    expected = int(row["written"])
    ok = remote == expected
    if not ok:
        _set(conn, row_id, status=STATUS_MISMATCH)
    return {"checked": True, "remote": remote, "expected": expected, "match": ok}


def rollback(conn: sqlite3.Connection, service, ledger: QuotaLedger, row_id: int) -> dict:
    """Delete the remote playlist and forget its tracks.

    Costs 50 units per attempt - more if a transient error forces a retry.
    """
    row = get_row(conn, row_id)
    playlist_id = row["playlist_id"]

    deleted = False
    already_absent = False
    if playlist_id:
        try:
            _call_with_retry(
                lambda: service.playlists().delete(id=playlist_id).execute(),
                ledger=ledger, method=DELETE_METHOD, note=f"rollback row {row_id}",
            )
            deleted = True
        except Exception as exc:  # noqa: BLE001
            if _status_of(exc) == 404:
                # Already gone - a prior attempt, or deleted by hand. The
                # local row is still junk either way; finish clearing it
                # rather than erroring out over a playlist that no longer
                # exists on either side.
                already_absent = True
            else:
                raise

    conn.execute("DELETE FROM written_tracks WHERE playlist_row = ?", (row_id,))
    _set(conn, row_id, status=STATUS_ROLLED_BACK, written=0, playlist_id=None)
    conn.commit()
    return {
        "row_id": row_id,
        "deleted_remote": deleted,
        "playlist_id": playlist_id,
        "already_absent": already_absent,
    }
