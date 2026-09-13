"""Compare clusterings against an external ground truth.

Silhouette scores measure how tidy a clustering looks in the space it was
built from, which is circular. The user's own **48 hand-curated playlists** are
a genuine external label: they are a human saying "these belong together". A
clustering that recovers them is coherent in the sense that matters for
generating playlists.

Restricted to tracks appearing in exactly one playlist, so a track filed under
both "Chill" and "Heartbreak Hindi" cannot be counted as a disagreement when
the model puts it in one of them.

Run:  python -m taste_engine.cluster_eval
"""
from __future__ import annotations

import sqlite3

import pandas as pd
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from .embed import CORPUS_MODES, cluster_tracks


def playlist_ground_truth(conn: sqlite3.Connection) -> dict[str, str]:
    """video_id -> playlist name, for videos filed in exactly one playlist."""
    rows = conn.execute(
        """
        SELECT video_id, MIN(playlist_name) AS name
        FROM (SELECT DISTINCT playlist_name, video_id FROM playlist_tracks)
        GROUP BY video_id
        HAVING COUNT(*) = 1
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


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
