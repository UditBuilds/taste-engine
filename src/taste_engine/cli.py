"""Command line for Phase 4.

    taste-engine write --cluster 3 --limit 50            # dry run
    taste-engine write --cluster 3 --limit 50 --commit   # writes
    taste-engine write --cluster-name "Joji" --backfill  # backfill for one run
    taste-engine write --resume 2 --commit               # continues a partial
    taste-engine write --rollback 2                      # deletes it (50 units)
    taste-engine written                                 # what exists
    taste-engine clusters                                # pick a --cluster

Dry run is the default everywhere. Nothing contacts YouTube, and nothing costs
quota, until `--commit` is passed.
"""
from __future__ import annotations

import argparse
import sys

from . import writer
from .db import connect
from .quota import QuotaExceeded, QuotaLedger


def _service():
    from .auth import build_service

    return build_service()


def cmd_write(args) -> int:
    conn = connect()
    try:
        ledger = QuotaLedger(conn, daily_cap=args.cap)

        if args.backfill and (args.resume is not None or args.rollback is not None):
            raise writer.WriteBlocked(
                "--backfill has no effect with --resume/--rollback: neither "
                "recomputes cluster selection, so the flag would silently do "
                "nothing. Drop --backfill."
            )

        # --- rollback -------------------------------------------------------
        if args.rollback is not None:
            row = writer.get_row(conn, args.rollback)
            print(f"Will DELETE playlist {row['playlist_id']} ({row['title']!r}) "
                  f"and forget {row['written']} tracks. Cost: 50 units "
                  "(more if a transient API error forces a retry).")
            if not args.commit:
                print("\nDry run - pass --commit to actually delete.")
                return 0
            result = writer.rollback(conn, _service(), ledger, args.rollback)
            if result["already_absent"]:
                print(f"Playlist {result['playlist_id']} was already gone; "
                      f"row {result['row_id']} marked rolled_back.")
            else:
                print(f"Deleted {result['playlist_id']}; row {result['row_id']} "
                      "marked rolled_back.")
            return 0

        # --- plan -----------------------------------------------------------
        if args.resume is not None:
            plan = writer.plan_from_row(conn, args.resume)
            done = writer.already_written(conn, args.resume)
            outstanding = plan["count"] - len(done)
            print(f"Resuming row {args.resume}: {len(done)} of {plan['count']} "
                  f"already written, {outstanding} outstanding "
                  f"({outstanding * 50} units).")
        else:
            plan = writer.plan(
                conn, cluster=args.cluster, limit=args.limit,
                half_life=args.half_life, mode=args.mode,
                exclude_top=args.exclude_top, cluster_name=args.cluster_name,
                backfill=True if args.backfill else None,
            )

        if not args.commit:
            print(writer.render_plan(plan, ledger))
            print("\nNothing written. Re-run with --commit to write it.")
            return 0

        if plan["units"] > ledger.remaining() and args.resume is None:
            print(f"Refusing: needs {plan['units']:,} units, "
                  f"{ledger.remaining():,} left today.", file=sys.stderr)
            return 1

        # --- write ----------------------------------------------------------
        service = _service()
        if args.resume is None:
            from .auth import authorised_channel

            ledger.charge("channels.list", note="identity check")
            who = authorised_channel(service)
            print(f"Writing to: {who['title']} ({who['id']})")

        report = writer.execute_write(
            conn, service, ledger, plan, row_id=args.resume,
            privacy="public" if args.public else "private",
        )

        print()
        print(f"  playlist    {report['url']}")
        print(f"  row id      {report['row_id']}")
        print(f"  written     {report['written']} of {report['planned']}")
        if report["skipped_already_present"]:
            print(f"  skipped     {report['skipped_already_present']} already present")
        print(f"  units       {report['units_spent']:,} "
              f"(remaining today {ledger.remaining():,})")
        print(f"  status      {report['status']}")

        verified = report.get("verified")
        if verified and verified.get("checked"):
            mark = "OK" if verified["match"] else "MISMATCH"
            print(f"  verified    {mark} - YouTube holds {verified['remote']}, "
                  f"expected {verified['expected']}")
        elif verified:
            print(f"  verified    not checked ({verified.get('reason')})")

        if report["stopped"]:
            print(f"\nStopped early: {report['stopped']}")
            print(f"Resume with:  taste-engine write --resume {report['row_id']} --commit")
            return 1
        if report["status"] == writer.STATUS_MISMATCH:
            return 1
        return 0
    except writer.WriteBlocked as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return 1
    except QuotaExceeded as exc:
        print(f"quota: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - last resort: never a raw traceback here.
        # writer.py already converts every insert/create/delete/verify failure
        # into a persisted partial + a WriteBlocked/QuotaExceeded above; this
        # is defense in depth for anything that isn't. Ctrl-C must still work,
        # so this is Exception, not BaseException.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def cmd_written(args) -> int:
    conn = connect()
    try:
        rows = writer.list_written(conn)
        if rows.empty:
            print("No playlists written yet.")
            return 0
        print(rows.to_string(index=False))
        print(f"\nquota today: {QuotaLedger(conn).remaining():,} units remaining")
    finally:
        conn.close()
    return 0


def cmd_clusters(args) -> int:
    from .embed import cluster_summary
    from .recommend import build

    conn = connect()
    try:
        df = build(conn)
    finally:
        conn.close()
    summary = cluster_summary(df)
    print(summary[summary.cluster >= 0].to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taste-engine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    w = sub.add_parser("write", help="write a playlist back to YouTube")
    w.add_argument("--cluster", type=int, help="cluster id (NOT stable across runs)")
    w.add_argument(
        "--cluster-name", metavar="TEXT",
        help="select the cluster by artist name, e.g. --cluster-name 'Travis "
             "Scott'. Preferred over --cluster: ids are reassigned whenever the "
             "song set changes.",
    )
    w.add_argument(
        "--limit", type=int, default=None,
        help="tracks for a non-cluster write (default 50). Not valid "
             "together with --cluster/--cluster-name: a cluster's playlist "
             "length is computed from cluster depth, not requested.",
    )
    w.add_argument("--half-life", type=float, help="override the recency half-life")
    w.add_argument(
        "--mode", choices=list(writer.MODES), default=writer.MODE_REDISCOVER,
        help="rediscover (default): exclude the library's most-played songs, "
             "matching the evaluated task. top: rank everything, favourites "
             "included - the replay task the baseline wins.",
    )
    w.add_argument(
        "--exclude-top", type=int,
        help="how many favourites --mode rediscover removes (default 50, "
             "the same number the eval holds out)",
    )
    w.add_argument(
        "--backfill", action="store_true",
        help="enable backfill for this run, overriding "
             "config.BACKFILL_ENABLED=False. Only valid with "
             "--cluster/--cluster-name, and not with --resume/--rollback.",
    )
    w.add_argument("--resume", type=int, metavar="ROW", help="continue a partial write")
    w.add_argument("--rollback", type=int, metavar="ROW", help="delete a written playlist")
    w.add_argument("--cap", type=int, help="override the daily quota cap")
    w.add_argument(
        "--commit", action="store_true",
        help="actually write; without this everything is a dry run",
    )
    w.add_argument(
        "--public", action="store_true",
        help="create the playlist public (default: private)",
    )
    w.set_defaults(func=cmd_write)

    sub.add_parser("written", help="list playlists this tool has written").set_defaults(
        func=cmd_written
    )
    sub.add_parser("clusters", help="list clusters to pick a --cluster id").set_defaults(
        func=cmd_clusters
    )

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
