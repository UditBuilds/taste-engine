"""Dormancy signal measurement - which signal predicts "forgotten"?

`--mode rediscover` only excludes the library's GLOBAL top-50 most-played
tracks before ranking within a cluster (see `recommend.favourites`). The
suspicion this measures: that exclusion does almost nothing at cluster
granularity, so a cluster's shipped tracks are dominated by whichever signal
correlates with "the model still ranks it highly" - possibly just recent or
heavy play, which is what rediscovery is supposed to avoid shipping.

Read-only w.r.t. every table `db.py` defines: this module only reads `plays`,
`written_playlists` and `written_tracks`, and gets everything else (canonical
grouping, clustering, scoring) from the existing read-only functions in
canonical.py/score.py/embed.py/recommend.py. Nothing here is read by
scoring/clustering/selection/write-path - see scripts/dormancy_signals.py and
reports/dormancy_signals.md. Same status as `lastfm.py` (Phase 5): a
measurement-only module, not wired into the pipeline.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from . import canonical as canon
from . import config
from .embed import cluster_tracks
from .recommend import favourites
from .score import scored_tracks

SIGNAL_COLUMNS = (
    "days_since_last_play",
    "plays_last_30d",
    "plays_last_90d",
    "plays_last_180d",
    "plays_lifetime",
    "share_of_cluster_plays",
    "score_percentile_within_cluster",
    "current_score",
    "months_active",
)


# --- canonical-key plumbing -------------------------------------------------

def canonical_key_of(conn: sqlite3.Connection) -> pd.Series:
    """video_id -> canonical_key, indexed by video_id.

    Replicates `canonical.collapse()`'s pre-groupby key computation exactly
    (`add_canonical_key`, then the duration/genre merge pass) so a shipped
    *representative* video_id can be traced back to every constituent upload
    it was summed from - `collapse()` itself discards that mapping once it
    groups. `canonical.py` is only ever called here, never modified: this is
    the same sequence `collapse()` runs internally, just stopped one step
    early so the per-video_id key survives.
    """
    video_df = scored_tracks(conn, canonical=False, music_only=True)
    work = canon.add_canonical_key(video_df)
    channels = work.get("channel", pd.Series([None] * len(work), index=work.index))
    work["core_key"] = [
        canon.title_core(t, c) for t, c in zip(work["title"], channels)
    ]
    if "duration" in work.columns:
        work["seconds"] = work["duration"].map(canon.iso_seconds)
        work["canonical_key"] = canon.merge_by_duration(work)
    return pd.Series(work["canonical_key"].values, index=work["video_id"].values)


def plays_by_canonical_key(
    conn: sqlite3.Connection, key_of: pd.Series
) -> dict[str, pd.Series]:
    """canonical_key -> sorted UTC Timestamps, pooled across every
    constituent video_id `canonical.collapse()` would sum into that key -
    not just the shipped representative's own uploads."""
    raw = pd.read_sql("SELECT video_id, watched_at FROM plays", conn)
    raw["canonical_key"] = raw["video_id"].map(key_of)
    raw = raw.dropna(subset=["canonical_key"])
    raw["watched_dt"] = pd.to_datetime(raw["watched_at"], format="ISO8601", utc=True)
    return {
        key: group["watched_dt"].sort_values().reset_index(drop=True)
        for key, group in raw.groupby("canonical_key")
    }


# --- date-window maths (unit tested directly against the boundary - brief section 8) --

def plays_in_window(play_times: pd.Series | None, as_of: pd.Timestamp, days: int) -> int:
    """Count of timestamps with `as_of - days <= t <= as_of` (both ends inclusive).

    Matches `score.aggregate_plays`'s `>=` convention on the start bound. A
    play landing exactly on the boundary (`as_of - days`) counts; one a
    second earlier does not. See
    tests/test_dormancy.py::TestPlaysInWindowBoundary.
    """
    if play_times is None or len(play_times) == 0:
        return 0
    cutoff = as_of - pd.Timedelta(days=days)
    return int(((play_times >= cutoff) & (play_times <= as_of)).sum())


def months_active(play_times: pd.Series | None) -> float:
    """Span from first to last play, in months (days / 30.44). 0.0 when 0-1 plays."""
    if play_times is None or len(play_times) == 0:
        return 0.0
    span_days = (play_times.max() - play_times.min()).total_seconds() / 86_400.0
    return round(span_days / 30.44, 1)


# --- the live pipeline, with `as_of` pinned once for internal consistency --

def build_frames(
    conn: sqlite3.Connection, as_of: pd.Timestamp, half_life: float | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, set[str]]:
    """(frame_full, frame_excl, global_favourites).

    The exact `recommend.build()` / `writer.plan()` pipeline (canonical,
    clustered, scored: cluster first, exclude the global top-50 after,
    matching `writer.plan()`'s mode=rediscover order) - except `as_of` is
    pinned explicitly rather than left to default to whatever
    `datetime.now()` resolves to at the moment each internal call happens to
    run. `recommend.build()` does not expose that parameter; this script
    needs one frozen "now" so `days_since`/`score` and this module's own
    `plays_last_Nd` windows agree on what "now" means. The only deviation
    from calling `recommend.build()` directly.
    """
    train = scored_tracks(conn, as_of=as_of, half_life=half_life)
    frame_full = cluster_tracks(train)
    obvious = favourites(frame_full, config.EXCLUDE_TOP)
    frame_excl = frame_full[~frame_full["video_id"].isin(obvious)].reset_index(drop=True)
    return frame_full, frame_excl, obvious


def qualifying_clusters(frame_excl: pd.DataFrame) -> pd.DataFrame:
    """Clusters clearing `config.MIN_CLUSTER_NATIVE` on native-eligible
    (`score >= config.MIN_SCORE`) members, post global-top-50 exclusion - the
    exact FLOOR check `writer.plan()` applies for a `--cluster-name` write
    today.

    `cluster_pool_size` is every post-exclusion member of the cluster,
    regardless of score - i.e. `native_eligible` plus whatever falls below
    `MIN_SCORE`. With `config.BACKFILL_ENABLED = False` (current default),
    `native_eligible` is also exactly what ships: see
    `writer._select_with_backfill`, which returns the native block unchanged
    and uncapped when backfill is off. So for every row here,
    "shipped" == "native_eligible" and "below_floor" ==
    `cluster_pool_size - native_eligible" - there is no third, shipped-but-
    not-eligible group to report.
    """
    real = frame_excl[frame_excl["cluster"] >= 0]
    rows = []
    for cid, group in real.groupby("cluster"):
        eligible = group[group["score"] >= config.MIN_SCORE]
        if len(eligible) >= config.MIN_CLUSTER_NATIVE:
            rows.append(
                {
                    "cluster": int(cid),
                    "name": str(group["cluster_name"].iloc[0]),
                    "native_eligible": len(eligible),
                    "cluster_pool_size": len(group),
                }
            )
    out = pd.DataFrame(
        rows, columns=["cluster", "name", "native_eligible", "cluster_pool_size"]
    )
    return out.sort_values("cluster").reset_index(drop=True)


def top50_overlap_by_cluster(
    frame_full: pd.DataFrame, global_favourites: set[str], cluster_ids: list[int]
) -> pd.DataFrame:
    """How many of each cluster's tracks (pre-exclusion, any score) sit in
    the library-wide top-50 by play count - the direct measurement of how
    much `--mode rediscover`'s exclusion removes per cluster (brief section
    4 item 3)."""
    real = frame_full[frame_full["cluster"] >= 0]
    rows = []
    for cid in cluster_ids:
        group = real[real["cluster"] == cid]
        rows.append(
            {
                "cluster": int(cid),
                "name": str(group["cluster_name"].iloc[0]) if len(group) else "",
                "cluster_size": len(group),
                "in_global_top50": int(group["video_id"].isin(global_favourites).sum()),
            }
        )
    return pd.DataFrame(rows)


def window_played_counts(shipped: pd.DataFrame, windows=(30, 90, 180)) -> dict[int, int]:
    """Of a cluster's shipped tracks, how many had >=1 play inside each window."""
    return {d: int((shipped[f"plays_last_{d}d"] > 0).sum()) for d in windows}


def distribution(values: pd.Series) -> dict:
    if values.empty:
        return {"n": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "n": int(len(values)),
        "min": round(float(values.min()), 1),
        "median": round(float(values.median()), 1),
        "mean": round(float(values.mean()), 1),
        "max": round(float(values.max()), 1),
    }


# --- shipped-track ground truth ---------------------------------------------

def shipped_video_ids(conn: sqlite3.Connection, row_id: int) -> list[str]:
    """The exact, ordered video_ids YouTube actually accepted for a
    `written_playlists` row - ground truth from `written_tracks`, not a
    re-run of the pipeline. The pipeline can drift (cluster ids are
    reassigned whenever the input set changes; see CLAUDE.md's "Cluster ids
    are not identifiers" and rows 1-4 of `written_playlists`, where
    T-Series's cluster id moved 11 -> 10 -> 11 across writes), so re-deriving
    "what would ship" today is not the same question as "what did ship" for
    a specific playlist a human then listened to and judged.
    """
    rows = conn.execute(
        "SELECT video_id FROM written_tracks WHERE playlist_row = ? ORDER BY position",
        (row_id,),
    ).fetchall()
    return [r[0] for r in rows]


# --- per-track signal table --------------------------------------------------

def track_signal_table(
    video_ids: list[str],
    frame_full: pd.DataFrame,
    key_of: pd.Series,
    plays_by_key: dict[str, pd.Series],
    as_of: pd.Timestamp,
    labels: dict[str, str] | None = None,
    cluster_pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One row per video_id, every signal in `SIGNAL_COLUMNS`, plus a label.

    `cluster_pool` is the denominator for `share_of_cluster_plays` and
    `score_percentile_within_cluster`. Defaults to the current cluster of
    `video_ids[0]` within `frame_full` (pre-exclusion, i.e. every track in
    that cluster regardless of score) when not given explicitly.

    Raises rather than silently producing NaNs if a shipped video_id cannot
    be found in `frame_full` - a shipped track missing from the current
    canonical/music universe is a data-integrity problem, not a 0.
    """
    lookup = frame_full.set_index("video_id")
    missing = [v for v in video_ids if v not in lookup.index]
    if missing:
        raise ValueError(
            f"shipped video_id(s) not found in the current canonical frame: {missing}"
        )
    if cluster_pool is None:
        cid = lookup.loc[video_ids[0], "cluster"]
        cluster_pool = frame_full[frame_full["cluster"] == cid]

    cluster_scores = cluster_pool["score"]
    cluster_total_plays = cluster_pool["play_count"].sum()

    rows = []
    for rank, vid in enumerate(video_ids, start=1):
        r = lookup.loc[vid]
        key = key_of.get(vid)
        times = plays_by_key.get(key)
        rows.append(
            {
                "rank": rank,
                "video_id": vid,
                "title": r["title"],
                "label": (labels or {}).get(vid, "unlabelled"),
                "days_since_last_play": round(float(r["days_since"]), 1),
                "plays_last_30d": plays_in_window(times, as_of, 30),
                "plays_last_90d": plays_in_window(times, as_of, 90),
                "plays_last_180d": plays_in_window(times, as_of, 180),
                "plays_lifetime": int(r["play_count"]),
                "share_of_cluster_plays": (
                    round(float(r["play_count"]) / cluster_total_plays, 4)
                    if cluster_total_plays
                    else 0.0
                ),
                "score_percentile_within_cluster": (
                    round(float((cluster_scores <= r["score"]).sum()) / len(cluster_scores) * 100, 1)
                    if len(cluster_scores)
                    else 0.0
                ),
                "current_score": round(float(r["score"]), 4),
                "months_active": months_active(times),
                "current_cluster": int(r["cluster"]),
                "n_plays_recorded": int(len(times)) if times is not None else 0,
            }
        )
    return pd.DataFrame(rows)


# --- separation (threshold-free, no p-value - brief section 3) -------------

def rank_separation(values: pd.Series, is_forgotten: pd.Series) -> dict:
    """P(a random "forgotten" track's value > a random "still in rotation"
    track's value) - Mann-Whitney U / (n_pos * n_neg). A threshold-free
    concordance measure, not a fitted cutoff: it is the fraction of
    (forgotten, rotation) pairs the signal orders "the expected way", summed
    over every possible threshold at once, so no single cutoff is chosen or
    reported. 1.0/0.0 = perfectly separated (one direction or the other);
    0.5 = no separation. Deliberately returns no p-value - n=11 is too small
    for one to mean anything here (brief section 3).
    """
    values = pd.Series(values).reset_index(drop=True).astype(float)
    is_forgotten = pd.Series(is_forgotten).reset_index(drop=True).astype(bool)
    forgotten = values[is_forgotten]
    rotation = values[~is_forgotten]
    n_f, n_r = len(forgotten), len(rotation)
    if n_f == 0 or n_r == 0:
        return {
            "auc": float("nan"), "n_forgotten": n_f, "n_rotation": n_r,
            "concordant": 0.0, "pairs": 0,
        }
    concordant = 0.0
    for f in forgotten:
        concordant += float((rotation < f).sum()) + 0.5 * float((rotation == f).sum())
    pairs = n_f * n_r
    return {
        "auc": concordant / pairs, "n_forgotten": n_f, "n_rotation": n_r,
        "concordant": concordant, "pairs": pairs,
    }


def separation_summary(
    table: pd.DataFrame, positive_labels: set[str], label_col: str = "label"
) -> pd.DataFrame:
    """Rank every signal in `SIGNAL_COLUMNS` by how cleanly it separates
    `label_col in positive_labels` from the rest. See `rank_separation` for
    what "separates" means here (no threshold, no p-value).
    """
    is_positive = table[label_col].isin(positive_labels)
    rows = []
    for col in SIGNAL_COLUMNS:
        stats = rank_separation(table[col], is_positive)
        auc = stats["auc"]
        strength = max(auc, 1 - auc) if auc == auc else float("nan")
        if auc != auc:
            direction = "n/a"
        elif auc > 0.5:
            direction = "higher in positive group"
        elif auc < 0.5:
            direction = "lower in positive group"
        else:
            direction = "no direction"
        rows.append(
            {
                "signal": col,
                "auc": round(auc, 3) if auc == auc else None,
                "separation": round(strength, 3) if strength == strength else None,
                "direction": direction,
                "concordant_pairs": stats["concordant"],
                "total_pairs": stats["pairs"],
                "n_positive": stats["n_forgotten"],
                "n_other": stats["n_rotation"],
            }
        )
    return pd.DataFrame(rows).sort_values(
        "separation", ascending=False, na_position="last"
    ).reset_index(drop=True)
