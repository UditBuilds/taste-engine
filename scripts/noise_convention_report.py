"""B1 — the embedding-mode comparison under all three noise conventions.

reports/eval_verification.md (A1) confirms `cluster_eval.coherence()` excludes
HDBSCAN noise before computing ARI/NMI/purity, and that the excluded share
ranges 42.9%-71.7% of the same ground truth across the three modes - a
different, self-selected subset per mode. This does not change that default;
it reports the same comparison under `coherence_by_convention()`'s other two
conventions (noise as one cluster, noise as singletons) so the choice is
visible instead of implicit. No HDBSCAN parameter changes.

Run:  scripts/run.sh scripts/noise_convention_report.py
"""
from __future__ import annotations

import pandas as pd

from taste_engine.cluster_eval import coherence_by_convention, playlist_ground_truth
from taste_engine.db import connect
from taste_engine.embed import CORPUS_MODES, cluster_tracks
from taste_engine.score import scored_tracks


def main() -> int:
    conn = connect()
    try:
        tracks = scored_tracks(conn)
        truth = playlist_ground_truth(conn)

        rows = []
        for mode in CORPUS_MODES:
            clustered = cluster_tracks(tracks, mode=mode)
            table = coherence_by_convention(clustered, truth)
            table.insert(0, "mode", mode)
            rows.append(table)
    finally:
        conn.close()

    full = pd.concat(rows, ignore_index=True)
    print(full.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    print("\nRanking check, by metric and convention "
          "(first place only, ties noted):")
    for metric in ("ari", "nmi", "purity"):
        print(f"\n  {metric.upper()}")
        for convention in ("exclude", "single_cluster", "singletons"):
            sub = full[full["convention"] == convention].set_index("mode")[metric]
            winner = sub.idxmax()
            ordered = sub.sort_values(ascending=False)
            print(f"    {convention:<15} winner={winner:<12} "
                  f"({', '.join(f'{m}={v:.3f}' for m, v in ordered.items())})")

    ari_winners = {
        c: full[full["convention"] == c].set_index("mode")["ari"].idxmax()
        for c in ("exclude", "single_cluster", "singletons")
    }
    survives = len(set(ari_winners.values())) == 1
    print(f"\nARI winner is the same mode under all three conventions: {survives}")
    print(f"  {ari_winners}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
