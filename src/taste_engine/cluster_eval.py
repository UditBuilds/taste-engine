"""Compare clusterings against an external ground truth.

Silhouette scores measure how tidy a clustering looks in the space it was
built from, which is circular. The user's own **48 hand-curated playlists** are
a genuine external label: they are a human saying "these belong together". A
clustering that recovers them is coherent in the sense that matters for
generating playlists.

Restricted to tracks appearing in exactly one playlist, so a track filed in two
of them cannot be counted as a disagreement when the model puts it in one. That
restriction is enforced on raw upload ids (`playlist_ground_truth()`); a second
one is enforced after canonicalisation (`canonical_ground_truth()`) - two raw
ids can each individually satisfy "exactly one playlist" and still disagree
once merged into one canonical track, and the whole track is dropped rather
than resolved by a tiebreak. See `canonical_ground_truth()`'s docstring and
`reports/ground_truth_audit.md`.

Playlist titles are pseudonymised before they reach any output - every metric
here treats them as opaque group labels, so the real names add nothing. See
`redact.py`.

Run:  python -m taste_engine.cluster_eval
"""
from __future__ import annotations

import sqlite3

import pandas as pd
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from .embed import CORPUS_MODES, cluster_tracks
from .redact import alias, aliases_for


def playlist_ground_truth(
    conn: sqlite3.Connection, redacted: bool = True
) -> dict[str, str]:
    """video_id -> playlist label, for videos filed in exactly one playlist.

    Labels are pseudonymised by default. Every metric here treats them as
    opaque group identifiers, so the real titles add nothing and several are
    personal - see `redact.py`. Pass `redacted=False` for local inspection.
    """
    rows = conn.execute(
        """
        SELECT video_id, MIN(playlist_name) AS name
        FROM (SELECT DISTINCT playlist_name, video_id FROM playlist_tracks)
        GROUP BY video_id
        HAVING COUNT(*) = 1
        """
    ).fetchall()
    truth = {r[0]: r[1] for r in rows}
    if not redacted:
        return truth
    mapping = aliases_for(conn)
    return {vid: alias(name, mapping) for vid, name in truth.items()}


def _drop_conflicts(
    raw_truth: dict[str, str], rep_map: dict[str, str]
) -> tuple[dict[str, str], dict]:
    """Pure core of `canonical_ground_truth()`: no DB, no I/O.

    `raw_truth`: raw video_id -> playlist label
    (`playlist_ground_truth()`'s shape). `rep_map`: raw video_id ->
    representative video_id (`canonical.raw_to_canonical_map()`'s shape) -
    only ids present in both are addressable; a `raw_truth` id absent from
    `rep_map` (not part of the population `collapse()` received, i.e. not
    is_music) is silently out of scope here, exactly as it already is for
    `coherence()`'s coverage/n_eval today.

    Groups raw ids by representative; a representative whose raw
    ground-truth members carry more than one distinct label is dropped
    entirely rather than resolved by any tiebreak (see
    `canonical_ground_truth()`'s docstring for why).
    """
    by_representative: dict[str, dict[str, str]] = {}
    for raw_id, label in raw_truth.items():
        rep = rep_map.get(raw_id)
        if rep is None:
            continue
        by_representative.setdefault(rep, {})[raw_id] = label

    truth: dict[str, str] = {}
    conflict_detail = []
    for rep, members in sorted(by_representative.items()):
        labels = sorted(set(members.values()))
        if len(labels) > 1:
            conflict_detail.append({
                "representative_id": rep,
                "labels": labels,
                "raw_ids": sorted(members),
            })
            continue
        truth[rep] = labels[0]

    stats = {
        "raw_ground_truth": len(raw_truth),
        "denominator": len(truth),
        "conflicts_dropped": len(conflict_detail),
        "conflict_detail": conflict_detail,
    }
    return truth, stats


def canonical_ground_truth(
    conn: sqlite3.Connection, tracks: pd.DataFrame, redacted: bool = True
) -> tuple[dict[str, str], dict]:
    """Ground truth keyed by canonical (representative) video_id, not raw.

    `playlist_ground_truth()`'s keys are raw `playlist_tracks.video_id`
    values; `tracks` (from `scored_tracks(canonical=True)`) is keyed by the
    canonical representative id `canonical.collapse()` picked for each song.
    `coherence()`'s join (`clustered["video_id"].isin(truth)`) silently
    dropped every raw ground-truth id that lost its own group's
    representative slot to a different upload - 48 of 486 ground-truth music
    tracks, measured in `reports/ground_truth_audit.md`. This maps raw ids to
    their representative *before* the join, so the join direction is
    raw -> canonical - the direction `clustered` is already keyed in - not
    the reverse.

    Canonicalising can put two different playlists' raw ids onto the same
    representative: "filed in exactly one playlist" is enforced by
    `playlist_ground_truth()` at the raw-upload level, and two independent
    uploads of the *same recording*, each individually satisfying that on
    its own, can still disagree once merged - the user filed the same song
    into two playlists without the two uploads ever being recognised as one
    until now. This is a **data-quality property of the source data**
    (duplicate uploads, independently catalogued into different playlists),
    **not a canonicalisation over-merge**: `reports/ground_truth_audit.md`
    (Item 3) checked every conflict found on this data and confirmed each is
    one song filed twice, not two different songs wrongly fused. Rather than
    pick a winner (by play count, recency, or any other tiebreak - which
    would assert a single label the source data does not actually agree on),
    the whole canonical track is dropped from ground truth. No winner is
    picked and none should be added later without re-opening that finding.

    Returns `(truth, stats)`. `stats` always carries `raw_ground_truth`
    (`playlist_ground_truth()`'s own count), `denominator` (`len(truth)`,
    i.e. after the conflict-drop - the number to report as "the ground-truth
    denominator"), `conflicts_dropped` (count of canonical tracks dropped)
    and `conflict_detail` (one dict per dropped track: representative id,
    labels, member raw ids), so a caller never has to infer the denominator
    or the drop count from anything else.
    """
    from .canonical import raw_to_canonical_map
    from .score import scored_tracks

    raw_truth = playlist_ground_truth(conn, redacted=redacted)
    raw = scored_tracks(conn, canonical=False)
    rep_map = raw_to_canonical_map(raw)

    # `rep_map`'s values must be exactly the ids `tracks` carries. Built from
    # a different population (e.g. a date-windowed or music_only=False
    # `tracks`), this mapping would point ground truth at ids `tracks` does
    # not have - the membership lookup below would then silently drop those
    # ground-truth rows instead of failing loudly, which is the exact
    # silent-wrong-number failure mode this project is organised against.
    canon_id_set = set(tracks["video_id"])
    if set(rep_map.values()) != canon_id_set:
        raise RuntimeError(
            "canonical_ground_truth(): raw_to_canonical_map(scored_tracks("
            "canonical=False)) does not produce the same representative-id "
            "set as tracks['video_id']. `tracks` must be built with the "
            "same as_of/window/music_only as the default scored_tracks(conn,"
            " canonical=False) call this function makes internally."
        )

    return _drop_conflicts(raw_truth, rep_map)


def purity(labels: list[int], truth: list[str]) -> float:
    """Fraction of tracks whose cluster is dominated by their own playlist."""
    frame = pd.DataFrame({"cluster": labels, "truth": truth})
    if frame.empty:
        return 0.0
    majority = frame.groupby("cluster")["truth"].agg(
        lambda s: s.value_counts().iloc[0]
    )
    return float(majority.sum() / len(frame))


def coherence(clustered: pd.DataFrame, truth: dict[str, str]) -> dict:
    """Agreement between a clustering and the user's playlist filing."""
    labelled = clustered[clustered["video_id"].isin(truth)]
    total_labelled = len(labelled)
    scored = labelled[labelled["cluster"] >= 0]

    n_clusters = int(clustered.loc[clustered["cluster"] >= 0, "cluster"].nunique())
    noise = float((clustered["cluster"] == -1).mean())

    if len(scored) < 2:
        return {
            "n_eval": len(scored), "total_labelled": total_labelled,
            "coverage": 0.0, "ari": 0.0, "nmi": 0.0,
            "purity": 0.0, "clusters": n_clusters, "noise": noise,
        }

    predicted = scored["cluster"].tolist()
    actual = [truth[v] for v in scored["video_id"]]
    return {
        "n_eval": len(scored),
        # The ground-truth pool this row's n_eval/coverage were computed
        # from, reported explicitly rather than left for the reader to back
        # out of coverage - see reports/ground_truth_audit.md for why that
        # matters (pool and n_eval are not the same number once noise is
        # excluded, and conflating them produces a wrong denominator).
        "total_labelled": total_labelled,
        # What fraction of ground-truth tracks got a real cluster at all. A
        # clustering that calls everything noise must not look good here.
        "coverage": len(scored) / total_labelled if total_labelled else 0.0,
        "ari": float(adjusted_rand_score(actual, predicted)),
        "nmi": float(normalized_mutual_info_score(actual, predicted)),
        "purity": purity(predicted, actual),
        "clusters": n_clusters,
        "noise": noise,
    }


NOISE_CONVENTIONS = ("exclude", "single_cluster", "singletons")


def _relabel_noise(predicted: list[int], convention: str) -> list[int]:
    """Remap HDBSCAN's -1 noise label under an explicit convention.

    * "single_cluster" leaves -1 as-is: every noise point gets the *same*
      label, so a mode is scored as if all its unassigned tracks belonged to
      one (likely very heterogeneous) group.
    * "singletons" gives every noise point its own fresh label, so no two
      noise points can ever be scored as "agreeing" with each other - each
      one is simply a cluster of one.
    """
    if convention == "single_cluster":
        return list(predicted)
    if convention == "singletons":
        next_id = (max(predicted) if predicted else -1) + 1
        out = []
        for p in predicted:
            if p >= 0:
                out.append(p)
            else:
                out.append(next_id)
                next_id += 1
        return out
    raise ValueError(
        f"convention must be 'single_cluster' or 'singletons', got {convention!r}"
    )


def coherence_by_convention(
    clustered: pd.DataFrame, truth: dict[str, str]
) -> pd.DataFrame:
    """ARI/NMI/purity under all three ways of scoring HDBSCAN noise.

    `coherence()` implements "exclude" only: noise is dropped before
    ARI/NMI/purity are computed, and `n_eval` shrinks with it. That is a
    defensible convention on its own, but comparing modes on excluded-noise
    ARI is only a fair comparison if the excluded share is similar across
    the modes being compared - see reports/eval_verification.md (A1) for a
    case where it ranges 42.9%-71.7% of the same ground truth. This function
    does not replace `coherence()` or change its default; it is an explicit,
    side-by-side alternative so the choice of convention is visible instead
    of implicit.
    """
    labelled = clustered[clustered["video_id"].isin(truth)]
    total_labelled = len(labelled)
    if total_labelled < 2:
        return pd.DataFrame(
            [
                {"convention": c, "n_eval": total_labelled,
                 "total_labelled": total_labelled, "ari": 0.0,
                 "nmi": 0.0, "purity": 0.0}
                for c in NOISE_CONVENTIONS
            ]
        )

    actual_full = [truth[v] for v in labelled["video_id"]]
    predicted_full = labelled["cluster"].tolist()

    mask = [p >= 0 for p in predicted_full]
    actual_excl = [a for a, m in zip(actual_full, mask) if m]
    pred_excl = [p for p, m in zip(predicted_full, mask) if m]
    rows = [{
        "convention": "exclude",
        "n_eval": len(pred_excl),
        # Constant across all three rows - the pool before this convention's
        # own noise handling, not this row's own n_eval. Reported on every
        # row (not just once) so a reader never has to look at a different
        # row to know what n_eval is a fraction of.
        "total_labelled": total_labelled,
        "ari": float(adjusted_rand_score(actual_excl, pred_excl)) if len(pred_excl) >= 2 else 0.0,
        "nmi": float(normalized_mutual_info_score(actual_excl, pred_excl)) if len(pred_excl) >= 2 else 0.0,
        "purity": purity(pred_excl, actual_excl),
    }]

    for convention in ("single_cluster", "singletons"):
        pred_conv = _relabel_noise(predicted_full, convention)
        rows.append({
            "convention": convention,
            "n_eval": total_labelled,
            "total_labelled": total_labelled,
            "ari": float(adjusted_rand_score(actual_full, pred_conv)),
            "nmi": float(normalized_mutual_info_score(actual_full, pred_conv)),
            "purity": purity(pred_conv, actual_full),
        })
    return pd.DataFrame(rows)


def compare_modes(
    conn: sqlite3.Connection,
    tracks: pd.DataFrame,
    modes: tuple[str, ...] = CORPUS_MODES,
) -> pd.DataFrame:
    """Score every embedding strategy against the playlist ground truth.

    Ground truth is `canonical_ground_truth(conn, tracks)` - raw ids mapped
    to canonical, conflicting canonical tracks dropped (see its docstring) -
    not the raw `playlist_ground_truth()`. The conflict-drop count is global,
    not per-mode, so it is not a column here; `main()` reports it once,
    alongside this table, via its own `canonical_ground_truth()` call.
    """
    truth, _stats = canonical_ground_truth(conn, tracks)
    has_genres = (
        "genres" in tracks.columns
        and tracks["genres"].map(lambda g: bool(g) if isinstance(g, (list, tuple)) else False).any()
    )

    rows = []
    for mode in modes:
        if mode == "title_genre" and not has_genres:
            rows.append({
                "mode": mode, "status": "needs resolve.py (no genres cached)",
                "n_eval": 0, "coverage": 0.0, "ari": None, "nmi": None,
                "purity": None, "clusters": 0, "noise": None,
            })
            continue
        clustered = cluster_tracks(tracks, mode=mode)
        rows.append({"mode": mode, "status": "ok", **coherence(clustered, truth)})
    return pd.DataFrame(rows)


def main() -> int:
    from .db import connect
    from .score import scored_tracks

    conn = connect()
    try:
        tracks = scored_tracks(conn)
        truth, stats = canonical_ground_truth(conn, tracks)
        print(
            f"{len(tracks):,} music tracks; "
            f"{stats['raw_ground_truth']:,} raw videos filed in exactly one "
            f"playlist; ground-truth denominator after raw->canonical "
            f"mapping: {stats['denominator']:,} "
            f"({stats['conflicts_dropped']} canonical track(s) dropped for "
            f"carrying conflicting playlist labels - duplicate uploads of "
            f"one song filed into two playlists, not a canonicalisation "
            f"over-merge; see reports/ground_truth_audit.md)\n"
        )
        table = compare_modes(conn, tracks)
    finally:
        conn.close()

    print(table.to_string(index=False))
    print("\nari/nmi: agreement with the user's own playlist filing "
          "(ari is chance-corrected).")
    print("coverage: share of ground-truth tracks given a real cluster, "
          "not marked noise.")
    print("total_labelled: the ground-truth pool this row's n_eval/coverage "
          "were computed from - not the same number as n_eval once noise is "
          "excluded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
