"""Recency-based exclusion for rediscover - feasibility measurement.

reports/recency_exclusion.md closed this direction at its own section 2
feasibility gate: the MIN_SCORE eligibility floor is already close to a
recency filter (a lone play decays below it in ~6.6 days at the current
half-life), so a downstream "exclude recently-played tracks" filter has
almost nothing left to remove. That report was originally produced by an
ad hoc script kept out of scripts/ ("never meant to be a permanent
artifact" - its own words). briefs/finish_regeneration.md Part B commits
it for real, since the report has since been regenerated more than once
against a moving as_of and a hand-copied one-off script does not survive
that.

Prints the same tables reports/recency_exclusion.md documents by hand: the
per-cluster candidate/survivor counts at 30/60/90-day exclusion thresholds,
and the aggregate reconfirmation figure. Deliberately does NOT write
reports/recency_exclusion.md - that report stays a hand-maintained
document; this script makes its numbers reproducible, not automatically
republished.

Method: taste_engine.dormancy.build_frames, qualifying_clusters,
canonical_key_of, plays_by_canonical_key, and plays_in_window, called
directly - no recency logic reimplemented here, matching
reports/recency_exclusion.md's own Method section.

Run:  scripts/run.sh scripts/recency_exclusion.py
"""
from __future__ import annotations

import argparse

import pandas as pd

from taste_engine import config, dormancy as d
from taste_engine.db import connect
from taste_engine.score import last_played_at

THRESHOLDS = (30, 60, 90)


def compute(as_of: pd.Timestamp | None = None) -> dict:
    """Every figure reports/recency_exclusion.md's sections 3 and 5 need, at
    a given as_of. Returns a dict rather than printing directly.

    Defaults to the dataset's own last recorded play (`MAX(watched_at)`,
    via `score.last_played_at`) - the same default `dormancy_signals.py`
    and `dormancy_probe.py` use, for the same reason: wall-clock drifts the
    eligibility gate every day that passes without a new Takeout import.
    """
    conn = connect()
    try:
        if as_of is None:
            as_of = pd.Timestamp(last_played_at(conn))
        elif as_of.tzinfo is None:
            as_of = as_of.tz_localize("UTC")
        else:
            as_of = as_of.tz_convert("UTC")

        plays_row_count = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
        frame_full, frame_excl, obvious = d.build_frames(conn, as_of=as_of)
        canonical_n = len(frame_full)

        qualifying = d.qualifying_clusters(frame_excl)
        key_of = d.canonical_key_of(conn)
        plays_by_key = d.plays_by_canonical_key(conn, key_of)

        rows = []
        survivors_by_threshold = {t: 0 for t in THRESHOLDS}
        total_candidates = 0

        for _, row in qualifying.iterrows():
            cid = row["cluster"]
            group = frame_excl[frame_excl["cluster"] == cid]
            candidates = group[group["score"] >= config.MIN_SCORE]
            n_candidates = len(candidates)
            total_candidates += n_candidates

            survivor_counts = {}
            for t in THRESHOLDS:
                n_survivors = sum(
                    1 for vid in candidates["video_id"]
                    if d.plays_in_window(plays_by_key.get(key_of.get(vid)), as_of, t) == 0
                )
                survivor_counts[t] = n_survivors
                survivors_by_threshold[t] += n_survivors

            rows.append({
                "cluster": int(cid),
                "name": row["name"],
                "cluster_pool_size": int(row["cluster_pool_size"]),
                "candidates_today": n_candidates,
                "survivors_30d": survivor_counts[30],
                "survivors_60d": survivor_counts[60],
                "survivors_90d": survivor_counts[90],
            })

        per_cluster = pd.DataFrame(
            rows,
            columns=["cluster", "name", "cluster_pool_size", "candidates_today",
                     "survivors_30d", "survivors_60d", "survivors_90d"],
        )
        clusters_clearing_floor = {
            t: (
                int((per_cluster[f"survivors_{t}d"] >= config.MIN_CLUSTER_NATIVE).sum())
                if not per_cluster.empty else 0
            )
            for t in THRESHOLDS
        }

        survivors_30 = survivors_by_threshold[30]
        played_30 = total_candidates - survivors_30

        return {
            "as_of": as_of,
            "plays_row_count": plays_row_count,
            "canonical_n": canonical_n,
            "per_cluster": per_cluster,
            "survivors_by_threshold": survivors_by_threshold,
            "clusters_clearing_floor": clusters_clearing_floor,
            "total_candidates": total_candidates,
            "played_30": played_30,
        }
    finally:
        conn.close()


def render(result: dict) -> str:
    lines: list[str] = []
    a = lines.append

    a("=== Provenance ===")
    a(f"as_of: {result['as_of'].isoformat()}")
    a(f"plays row count: {result['plays_row_count']}")
    a(f"canonical (music-only) tracks in frame: {result['canonical_n']}")
    a("")
    a("=== Section 3: per-cluster table ===")
    a(result["per_cluster"].to_string(index=False))
    a("")
    a("=== Section 3: aggregate ===")
    n_clusters = len(result["per_cluster"])
    for t in THRESHOLDS:
        a(
            f"{t}d: clusters clearing MIN_CLUSTER_NATIVE({config.MIN_CLUSTER_NATIVE}) = "
            f"{result['clusters_clearing_floor'][t]} of {n_clusters}; "
            f"total survivor pool = {result['survivors_by_threshold'][t]}"
        )
    a("")
    a("=== Section 5: reconfirmation ===")
    total = result["total_candidates"]
    played = result["played_30"]
    pct = (played / total) if total else float("nan")
    a(f"{played} of {total} ({pct:.1%}) played within the last 30 days")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recency-based exclusion feasibility (reports/recency_exclusion.md)"
    )
    parser.add_argument(
        "--as-of",
        help="Pin the analysis 'now' to this ISO date/timestamp (UTC assumed "
             "if no offset is given) instead of the dataset's own last "
             "recorded play. Omit to default to MAX(watched_at).",
    )
    args = parser.parse_args(argv)
    as_of = pd.Timestamp(args.as_of) if args.as_of else None

    result = compute(as_of=as_of)
    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
