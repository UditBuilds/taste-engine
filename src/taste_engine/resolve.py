"""Phase 2 - fetch authoritative video metadata, cheaply and once.

`videos.list` costs **1 unit per call and accepts 50 IDs**, so all 30,440
unique history videos resolve for 609 units - under 7% of a day's quota. Every
response is cached in `video_metadata`, including misses (`found = 0`), so a
deleted video is never paid for twice.

Auth note, and a deviation from the original brief: `videos.list` returns
*public* data, so it needs only an **API key**. OAuth is required solely for
Phase 4, which writes to the user's own account. Setting up a key is a
one-minute job against an OAuth consent screen's several, so resolution uses a
key and the OAuth flow is deferred to `writer.py`.

Run:  python -m taste_engine.resolve --dry-run
      python -m taste_engine.resolve
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from . import config
from .db import connect
from .quota import QuotaExceeded, QuotaLedger

API_SERVICE = "youtube"
API_VERSION = "v3"
PARTS = "snippet,topicDetails,contentDetails"
METHOD = "videos.list"


class MissingCredentials(RuntimeError):
    pass


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(config.REPO_ROOT / ".env")


def get_api_key() -> str:
    _load_dotenv()
    key = os.environ.get("YT_API_KEY", "").strip()
    if not key:
        raise MissingCredentials(
            "YT_API_KEY is not set.\n"
            "  1. https://console.cloud.google.com/apis/library/youtube.googleapis.com "
            "-> Enable\n"
            "  2. APIs & Services -> Credentials -> Create credentials -> API key\n"
            "  3. cp .env.example .env  and put the key in YT_API_KEY\n"
            "Resolution needs only a key; OAuth is required for write-back."
        )
    return key


def build_service(api_key: str | None = None):
    from googleapiclient.discovery import build

    return build(
        API_SERVICE,
        API_VERSION,
        developerKey=api_key or get_api_key(),
        cache_discovery=False,
    )


# --- what still needs fetching ---------------------------------------------

def pending_video_ids(conn: sqlite3.Connection) -> list[str]:
    """History videos with no cached metadata, most-played first.

    Ordering by play count means an interrupted run still resolves the videos
    that matter most to the model.
    """
    rows = conn.execute(
        """
        SELECT p.video_id
        FROM plays p
        LEFT JOIN video_metadata m ON m.video_id = p.video_id
        WHERE m.video_id IS NULL
        GROUP BY p.video_id
        ORDER BY COUNT(*) DESC
        """
    ).fetchall()
    return [r[0] for r in rows]


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def plan(conn: sqlite3.Connection, ledger: QuotaLedger, limit: int | None = None) -> dict:
    """Cost a resolution run without spending anything."""
    pending = pending_video_ids(conn)
    if limit is not None:
        pending = pending[:limit]
    calls = -(-len(pending) // config.VIDEOS_LIST_BATCH)
    units = ledger.cost_of(METHOD, calls)
    return {
        "pending": len(pending),
        "batch_size": config.VIDEOS_LIST_BATCH,
        "calls": calls,
        "units": units,
        "remaining_before": ledger.remaining(),
        "affordable": units <= ledger.remaining(),
        "cached": conn.execute("SELECT COUNT(*) FROM video_metadata").fetchone()[0],
    }


# --- persistence ------------------------------------------------------------

def _row_from_item(item: dict) -> tuple:
    snippet = item.get("snippet", {}) or {}
    topics = item.get("topicDetails", {}) or {}
    content = item.get("contentDetails", {}) or {}
    return (
        item["id"],
        1,
        snippet.get("title"),
        snippet.get("channelId"),
        snippet.get("channelTitle"),
        snippet.get("categoryId"),
        snippet.get("publishedAt"),
        content.get("duration"),
        json.dumps(topics.get("topicCategories", []) or []),
        json.dumps(snippet.get("tags", []) or []),
        datetime.now(timezone.utc).isoformat(),
    )


def _missing_row(video_id: str) -> tuple:
    """Deleted or private. Cached so we never pay to look it up again."""
    return (
        video_id, 0, None, None, None, None, None, None,
        json.dumps([]), json.dumps([]),
        datetime.now(timezone.utc).isoformat(),
    )


_INSERT = (
    "INSERT OR REPLACE INTO video_metadata "
    "(video_id, found, title, channel_id, channel_title, category_id, "
    " published_at, duration, topic_categories, tags, fetched_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def resolve(
    conn: sqlite3.Connection,
    ledger: QuotaLedger,
    limit: int | None = None,
    service=None,
    verbose: bool = True,
) -> dict:
    """Resolve pending videos in batches of 50, stopping cleanly on quota."""
    pending = pending_video_ids(conn)
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        return {"requested": 0, "found": 0, "missing": 0, "units": 0, "stopped": None}

    service = service or build_service()
    videos = service.videos()

    found = missing = units = 0
    stopped = None

    for batch in _chunks(pending, config.VIDEOS_LIST_BATCH):
        try:
            ledger.check(METHOD)
        except QuotaExceeded as exc:
            stopped = str(exc)
            break

        request = videos.list(part=PARTS, id=",".join(batch), maxResults=50)
        try:
            with ledger.spend(METHOD, note=f"resolve x{len(batch)}"):
                response = request.execute()
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is quota
            if _is_quota_error(exc):
                stopped = f"API returned quotaExceeded: {exc}"
                break
            raise

        units += 1
        items = response.get("items", [])
        returned = {item["id"] for item in items}

        rows = [_row_from_item(item) for item in items]
        rows += [_missing_row(vid) for vid in batch if vid not in returned]

        # Commit per batch: an interrupted run keeps everything already bought.
        with conn:
            conn.executemany(_INSERT, rows)

        found += len(items)
        missing += len(batch) - len(items)

        if verbose and units % 25 == 0:
            print(
                f"  {found + missing:>6,}/{len(pending):,} resolved "
                f"({units} units, {ledger.remaining():,} left today)",
                flush=True,
            )

    return {
        "requested": len(pending),
        "found": found,
        "missing": missing,
        "units": units,
        "stopped": stopped,
    }


def _is_quota_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 403:
        return "quota" in str(exc).lower()
    return False


# --- CLI --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="resolve at most N videos")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the cost and exit without calling"
    )
    parser.add_argument("--cap", type=int, help="override the daily quota cap")
    args = parser.parse_args(argv)

    conn = connect()
    try:
        ledger = QuotaLedger(conn, daily_cap=args.cap)
        estimate = plan(conn, ledger, args.limit)

        print("videos.list resolution plan")
        print(f"  already cached     {estimate['cached']:>8,}")
        print(f"  still pending      {estimate['pending']:>8,}")
        print(f"  calls (@50 ids)    {estimate['calls']:>8,}")
        print(f"  quota cost         {estimate['units']:>8,} units")
        print(f"  remaining today    {estimate['remaining_before']:>8,}")

        if estimate["pending"] == 0:
            print("\nNothing to resolve.")
            return 0
        if args.dry_run:
            print("\nDry run - nothing fetched.")
            return 0
        if not estimate["affordable"]:
            print("\nRefusing to start: the full run exceeds today's remaining quota.")
            print("Re-run with --limit to resolve a slice, or wait for the reset.")
            return 1

        try:
            result = resolve(conn, ledger, args.limit)
        except MissingCredentials as exc:
            print(f"\n{exc}", file=sys.stderr)
            return 2

        print(f"\n  found              {result['found']:>8,}")
        print(f"  deleted/private    {result['missing']:>8,}")
        print(f"  units spent        {result['units']:>8,}")
        if result["stopped"]:
            print(f"\nStopped early: {result['stopped']}")
            print("Progress is saved - re-run after the quota resets.")
        print()
        print(ledger.report())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
