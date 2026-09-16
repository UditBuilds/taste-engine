"""Compare clusterings against an external ground truth.

Silhouette scores measure how tidy a clustering looks in the space it was
built from, which is circular. The user's own **48 hand-curated playlists** are
a genuine external label: they are a human saying "these belong together". A
clustering that recovers them is coherent in the sense that matters for
generating playlists.

Restricted to tracks appearing in exactly one playlist, so a track filed in two
of them cannot be counted as a disagreement when the model puts it in one.

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
            "n_eval": len(scored), "coverage": 0.0, "ari": 0.0, "nmi": 0.0,
            "purity": 0.0, "clusters": n_clusters, "noise": noise,
        }

    predicted = scored["cluster"].tolist()
    actual = [truth[v] for v in scored["video_id"]]
    return {
        "n_eval": len(scored),
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
                {"convention": c, "n_eval": total_labelled, "ari": 0.0,
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
        "ari": float(adjusted_rand_score(actual_excl, pred_excl)) if len(pred_excl) >= 2 else 0.0,
        "nmi": float(normalized_mutual_info_score(actual_excl, pred_excl)) if len(pred_excl) >= 2 else 0.0,
        "purity": purity(pred_excl, actual_excl),
    }]

    for convention in ("single_cluster", "singletons"):
        pred_conv = _relabel_noise(predicted_full, convention)
        rows.append({
            "convention": convention,
            "n_eval": total_labelled,
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
    """Score every embedding strategy against the playlist ground truth."""
    truth = playlist_ground_truth(conn)
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
        truth = playlist_ground_truth(conn)
        overlap = len(set(tracks["video_id"]) & set(truth))
        print(f"{len(tracks):,} music tracks; {len(truth):,} videos filed in exactly "
              f"one playlist; {overlap:,} overlap\n")
        table = compare_modes(conn, tracks)
    finally:
        conn.close()

    print(table.to_string(index=False))
    print("\nari/nmi: agreement with the user's own playlist filing "
          "(ari is chance-corrected).")
    print("coverage: share of ground-truth tracks given a real cluster, "
          "not marked noise.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
