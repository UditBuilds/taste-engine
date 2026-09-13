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
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from . import config
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


def plan(
    conn: sqlite3.Connection,
    cluster: int | None = None,
    limit: int = 50,
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

    excluded_count = 0
    if tracks is None:
        from .recommend import build, favourites

        frame = build(conn, half_life=half_life)
        if mode == MODE_REDISCOVER:
            # Global, before the cluster filter - the eval excludes the
            # library's favourites, not each cluster's.
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
            frame = frame[frame["cluster"] == cluster]
            if frame.empty:
                raise WriteBlocked(
                    f"cluster {cluster} has no tracks"
                    + (" left after excluding favourites" if excluded_count else "")
                )
        frame = frame.sort_values(["score", "video_id"], ascending=[False, True])
        tracks = frame.head(limit).reset_index(drop=True)

    name = "playlist"
    if cluster is not None and "cluster_name" in tracks.columns and len(tracks):
        name = str(tracks["cluster_name"].iloc[0])

    n = len(tracks)
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
        f"  tracks     {p['count']}",
        "",
        "  quota cost",
        f"    {CREATE_METHOD:<24}{p['breakdown'][CREATE_METHOD]:>7,}",
        f"    {INSERT_METHOD:<24}{p['breakdown'][INSERT_METHOD]:>7,}"
        f"   ({p['count']} x {config.QUOTA_COSTS[INSERT_METHOD]})",
        f"    {LIST_METHOD:<24}{p['breakdown'][LIST_METHOD]:>7,}   (verification)",
        f"    {'TOTAL':<24}{p['units']:>7,}",
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
    for i, row in p["tracks"].iterrows():
        title = str(row.get("title") or row["video_id"])[:58]
        score = row.get("score")
        lines.append(
            f"  {i + 1:>3}. {title:<58} {score:.3f}" if score is not None
            else f"  {i + 1:>3}. {title}"
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


def _is_quota_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status == 403 and "quota" in str(exc).lower()


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
            ledger.check(CREATE_METHOD)
        except QuotaExceeded as exc:
            _set(conn, row_id, status=STATUS_PENDING)
            raise WriteBlocked(f"not enough quota to create the playlist: {exc}") from None
        with ledger.spend(CREATE_METHOD, note=f"playlist row {row_id}"):
            created = service.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {"title": p["title"], "description": p["description"]},
                    "status": {"privacyStatus": row["privacy"]},
                },
            ).execute()
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
            ledger.check(INSERT_METHOD)
        except QuotaExceeded as exc:
            stopped = str(exc)
            break
        try:
            with ledger.spend(INSERT_METHOD, note=f"row {row_id} pos {position}"):
                item = _insert_track(service, playlist_id, track.video_id, position)
        except Exception as exc:  # noqa: BLE001
            if _is_quota_error(exc):
                stopped = f"API returned quotaExceeded: {exc}"
                break
            _set(conn, row_id, status=STATUS_PARTIAL, written=written,
                 units_spent=units)
            raise

        units += config.QUOTA_COSTS[INSERT_METHOD]
        written += 1
        # Record immediately: this row is what makes a resume correct.
        conn.execute(
            "INSERT OR REPLACE INTO written_tracks "
            "(playlist_row, video_id, position, item_id, written_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (row_id, track.video_id, position, (item or {}).get("id"), _now()),
        )
        conn.commit()
        _set(conn, row_id, written=written, units_spent=units)

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

    try:
        ledger.check(LIST_METHOD)
    except QuotaExceeded:
        return {"checked": False, "reason": "no quota left to verify"}

    remote = 0
    page = None
    with ledger.spend(LIST_METHOD, note=f"verify row {row_id}"):
        response = service.playlistItems().list(
            part="id", playlistId=row["playlist_id"], maxResults=50
        ).execute()
    remote += len(response.get("items", []))
    page = response.get("nextPageToken")

    while page:
        try:
            ledger.check(LIST_METHOD)
        except QuotaExceeded:
            return {"checked": False, "reason": "quota ran out mid-verification"}
        with ledger.spend(LIST_METHOD, note=f"verify row {row_id}"):
            response = service.playlistItems().list(
                part="id", playlistId=row["playlist_id"], maxResults=50,
                pageToken=page,
            ).execute()
        remote += len(response.get("items", []))
        page = response.get("nextPageToken")

    expected = int(row["written"])
    ok = remote == expected
    if not ok:
        _set(conn, row_id, status=STATUS_MISMATCH)
    return {"checked": True, "remote": remote, "expected": expected, "match": ok}


def rollback(conn: sqlite3.Connection, service, ledger: QuotaLedger, row_id: int) -> dict:
    """Delete the remote playlist and forget its tracks. Costs 50 units."""
    row = get_row(conn, row_id)
    playlist_id = row["playlist_id"]

    deleted = False
    if playlist_id:
        ledger.check(DELETE_METHOD)
        with ledger.spend(DELETE_METHOD, note=f"rollback row {row_id}"):
            service.playlists().delete(id=playlist_id).execute()
        deleted = True

    conn.execute("DELETE FROM written_tracks WHERE playlist_row = ?", (row_id,))
    _set(conn, row_id, status=STATUS_ROLLED_BACK, written=0, playlist_id=None)
    conn.commit()
    return {"row_id": row_id, "deleted_remote": deleted, "playlist_id": playlist_id}
