"""min_samples sensitivity sweep - measurement only, briefs/min_samples_sweep.md.

Answers two questions with one run, neither of which changes `min_samples`:

1. Is the ARI metric stable enough to compare embedding modes at all? A fix
   that changed the embedding text of 7 of 2,918 tracks (0.24%) moved
   `title_genre` ARI by -0.104 and swapped its ranking with `title` - a swing
   bigger than the 0.087 gap between them. Nobody had ever measured whether
   that swing is typical or a fluke.
2. Is `min_samples = 2` defensible? An external review proposed a mechanism:
   at `min_samples = 2` the core distance is just distance-to-nearest-point,
   mutual reachability stays close to raw Euclidean distance, and with
   `cluster_selection_method = "eom"` a handful of points can snap a sparse
   bridge in the minimum spanning tree and reassign large parts of the
   hierarchy. Prediction: the instability falls monotonically as
   `min_samples` rises. That is falsifiable, and is what this script tests.

**The perturbation.** The original 7-track change is not reproducible on
demand - it was a bug fix, already applied. The stand-in is random removal of
7 canonical tracks (not text mutation, which would require inventing a
corruption that mimics the original and is therefore unfalsifiable), repeated
20 times with different, recorded seeds so the output is a distribution.

**The two reported ARI quantities are different things - do not conflate
them.** Per `(min_samples, mode)`, for each of the 20 repetitions:

  (A) "the swing" - `adjusted_rand_score` between the *original* clustering
      (restricted to the 2,911 surviving tracks) and the *perturbed*
      clustering. Purely structural: does not touch ground truth at all.
      This is what the single-linkage-chaining mechanism above predicts
      directly, and reported here as **1 - ARI** ("instability"), because a
      *stable* clustering gives ARI near 1.0 and the brief's own predicted
      numbers ("negligible at 10") only make sense as a quantity that shrinks
      as clustering stabilises.
  (B) "ARI against ground truth" - the perturbed clustering's own
      `coherence_by_convention` ARI. A distribution of raw values across the
      20 repetitions, not a delta from the original.

Both are computed under all three noise conventions from the previous brief
(`cluster_eval.coherence_by_convention`): exclude, single cluster,
singletons. `_relabel_noise` is reused unmodified for "single_cluster" and
"singletons"; "exclude" (for a *pair* of clusterings rather than one against
a fixed ground truth) drops a point if *either* side calls it noise, since
the whole point of "exclude" is to only score points both sides confidently
placed.

**Paired design.** The same 20 drop-sets (by `video_id` index into the
canonical 2,918-track frame, which is identical across all three modes) are
reused across every `min_samples` value and every mode, so a difference in
swing between cells is attributable to the parameter or the mode, not to
which 7 tracks happened to get unlucky that repetition.

**Embedding reuse.** MiniLM encodes each text independently (no
cross-attention across a batch), so a surviving track's embedding vector
does not depend on which other tracks are in the corpus. Each mode's full
2,918-track corpus is embedded once (already on disk from prior briefs; see
`embed.embed_texts`'s content-hash cache) and a perturbation is applied by
slicing rows out of that matrix, never by re-embedding a shrunk corpus.
Spot-checked: embedding a 50-text subset directly vs. slicing the same 50
rows from the full embedding agrees to 1.1e-7 (float32 noise, not a real
difference).

This script changes no HDBSCAN default. `config.py`/`embed.MIN_SAMPLES` are
not touched.

PARTIALLY STALE if re-run (2026-09-17): this script still calls
`playlist_ground_truth()` directly, the pre-fix raw ground truth - see
`reports/ground_truth_audit.md`. Only the "ARI-against-ground-truth"
quantity (§8) is affected; the "swing" quantity this script's own headline
(§3-§5) is built on is structural (clustering vs. clustering) and never
touches ground truth at all, so it is unaffected and was reused as-is by
`reports/ground_truth_ids.md`.

Run:  scripts/run.sh scripts/min_samples_sweep.py
      scripts/run.sh scripts/min_samples_sweep.py --reps 10   # if 20 is slow
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

from taste_engine.cluster_eval import (
    NOISE_CONVENTIONS,
    _relabel_noise,
    coherence_by_convention,
    playlist_ground_truth,
)
from taste_engine.db import connect
from taste_engine.embed import (
    CORPUS_MODES,
    MIN_CLUSTER_SIZE,
    PCA_COMPONENTS,
    build_corpus,
    cluster_embeddings,
    embed_texts,
)
from taste_engine.score import scored_tracks

MIN_SAMPLES_VALUES = (2, 5, 10, 15)
N_DROP = 7
N_REPS = 20
SEED_BASE = 1000  # arbitrary; only its fixedness matters, not its value
REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"


def drop_indices(n_total: int, n_drop: int, seed: int) -> list[int]:
    """Deterministic: the same (n_total, n_drop, seed) always drops the same
    indices, sorted so downstream boolean masking is order-independent."""
    rng = random.Random(seed)
    return sorted(rng.sample(range(n_total), n_drop))


def stability_ari(
    labels_a: list[int], labels_b: list[int], convention: str
) -> tuple[float, int]:
    """ARI between two clusterings of the *same* point set, under one noise
    convention. Returns (ari, n_scored).

    "exclude" drops a point if *either* labelling calls it noise - scoring a
    point only both sides confidently placed is the same philosophy
    `coherence()` applies to a single clustering against ground truth,
    extended to a pair. "single_cluster"/"singletons" reuse `_relabel_noise`
    independently on each side, exactly as `coherence_by_convention` does.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("labels_a and labels_b must be the same length")
    if convention == "exclude":
        mask = [(a >= 0 and b >= 0) for a, b in zip(labels_a, labels_b)]
        a_f = [a for a, m in zip(labels_a, mask) if m]
        b_f = [b for b, m in zip(labels_b, mask) if m]
        if len(a_f) < 2:
            return 0.0, len(a_f)
        return float(adjusted_rand_score(a_f, b_f)), len(a_f)
    a_conv = _relabel_noise(list(labels_a), convention)
    b_conv = _relabel_noise(list(labels_b), convention)
    return float(adjusted_rand_score(a_conv, b_conv)), len(labels_a)


def _noise_and_clusters(labels: np.ndarray) -> tuple[float, int]:
    noise = float((labels == -1).mean())
    n_clusters = int(len(set(labels[labels >= 0])))
    return noise, n_clusters


def run_sweep(
    min_samples_values=MIN_SAMPLES_VALUES,
    modes=CORPUS_MODES,
    n_reps: int = N_REPS,
    n_drop: int = N_DROP,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (original_stats, rep_stats) - see module docstring for the
    (A)/(B) quantities `rep_stats` carries per repetition."""
    conn = connect()
    try:
        tracks = scored_tracks(conn)
        truth = playlist_ground_truth(conn)
    finally:
        conn.close()

    video_ids = tracks["video_id"].tolist()
    n_total = len(video_ids)
    seeds = [SEED_BASE + i for i in range(n_reps)]
    # Mode-independent: every mode shares the same 2,918-row track frame:
    # only the embedding *text* differs, never the row count or order.
    drop_sets = {seed: drop_indices(n_total, n_drop, seed) for seed in seeds}

    original_rows = []
    rep_rows = []

    for mode in modes:
        texts = build_corpus(tracks, mode=mode)
        vectors = embed_texts(texts)  # cached on disk; see module docstring

        for min_samples in min_samples_values:
            t_cell = time.time()
            original_labels = cluster_embeddings(
                vectors, min_cluster_size=MIN_CLUSTER_SIZE,
                min_samples=min_samples, n_components=PCA_COMPONENTS,
            )
            orig_noise, orig_clusters = _noise_and_clusters(original_labels)
            original_df = pd.DataFrame(
                {"video_id": video_ids, "cluster": original_labels}
            )
            orig_conv_table = coherence_by_convention(original_df, truth)

            for _, row in orig_conv_table.iterrows():
                original_rows.append({
                    "mode": mode, "min_samples": min_samples,
                    "convention": row["convention"],
                    "noise": orig_noise, "clusters": orig_clusters,
                    "ari_vs_truth": row["ari"], "n_eval": int(row["n_eval"]),
                })

            for seed in seeds:
                drop = drop_sets[seed]
                keep_mask = np.ones(n_total, dtype=bool)
                keep_mask[drop] = False
                perturbed_vectors = vectors[keep_mask]
                perturbed_video_ids = [
                    v for v, k in zip(video_ids, keep_mask) if k
                ]
                perturbed_labels = cluster_embeddings(
                    perturbed_vectors, min_cluster_size=MIN_CLUSTER_SIZE,
                    min_samples=min_samples, n_components=PCA_COMPONENTS,
                )
                pert_noise, pert_clusters = _noise_and_clusters(perturbed_labels)
                perturbed_df = pd.DataFrame(
                    {"video_id": perturbed_video_ids, "cluster": perturbed_labels}
                )
                pert_conv_table = coherence_by_convention(perturbed_df, truth)

                original_labels_on_survivors = original_labels[keep_mask]
                for convention in NOISE_CONVENTIONS:
                    swing_ari, swing_n = stability_ari(
                        list(original_labels_on_survivors),
                        list(perturbed_labels),
                        convention,
                    )
                    gt_row = pert_conv_table.set_index("convention").loc[convention]
                    rep_rows.append({
                        "mode": mode, "min_samples": min_samples,
                        "convention": convention, "seed": seed,
                        "swing_ari": swing_ari,
                        "swing_instability": 1.0 - swing_ari,
                        "swing_n": swing_n,
                        "ari_vs_truth": float(gt_row["ari"]),
                        "n_eval": int(gt_row["n_eval"]),
                        "noise": pert_noise, "clusters": pert_clusters,
                    })
            print(
                f"  mode={mode:<12} min_samples={min_samples:<3} "
                f"({time.time() - t_cell:.1f}s for {n_reps} reps)",
                flush=True,
            )

    return pd.DataFrame(original_rows), pd.DataFrame(rep_rows)


def summarise(rep_stats: pd.DataFrame) -> pd.DataFrame:
    """mean/median/min/max/std of the swing and of ARI-vs-truth, per
    (mode, min_samples, convention), plus mean noise/clusters across reps."""
    grouped = rep_stats.groupby(["mode", "min_samples", "convention"])
    out = grouped.agg(
        swing_mean=("swing_instability", "mean"),
        swing_median=("swing_instability", "median"),
        swing_min=("swing_instability", "min"),
        swing_max=("swing_instability", "max"),
        swing_std=("swing_instability", "std"),
        ari_raw_mean=("swing_ari", "mean"),
        gt_ari_mean=("ari_vs_truth", "mean"),
        gt_ari_median=("ari_vs_truth", "median"),
        gt_ari_min=("ari_vs_truth", "min"),
        gt_ari_max=("ari_vs_truth", "max"),
        gt_ari_std=("ari_vs_truth", "std"),
        n_eval_mean=("n_eval", "mean"),
        noise_mean=("noise", "mean"),
        clusters_mean=("clusters", "mean"),
        reps=("seed", "count"),
    ).reset_index()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=N_REPS)
    parser.add_argument(
        "--out", default=str(REPORT_DIR / "min_samples_sweep_raw.csv"),
        help="where to save the full per-repetition table",
    )
    args = parser.parse_args(argv)

    t0 = time.time()
    original_stats, rep_stats = run_sweep(n_reps=args.reps)
    print(f"\ntotal sweep time: {time.time() - t0:.1f}s")

    rep_stats.to_csv(args.out, index=False)
    print(f"raw per-repetition table saved to {args.out}\n")

    summary = summarise(rep_stats)
    pd.set_option("display.width", 200)
    print("=" * 100)
    print("ORIGINAL (unperturbed) clustering, per mode/min_samples/convention")
    print("=" * 100)
    print(original_stats.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\n" + "=" * 100)
    print("SWEEP SUMMARY - swing = 1 - ARI(original-on-survivors, perturbed); "
          "gt_ari = perturbed clustering's own ARI vs ground truth")
    print("=" * 100)
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\n" + "=" * 100)
    print("PUBLISHED GAP vs SWING (singletons convention, exclude/single_cluster in appendix above)")
    print("=" * 100)
    published_ari = {"title_artist": 0.649, "title_genre": 0.470, "title": 0.383}
    gaps = [("title_artist", "title_genre"), ("title_genre", "title")]
    for convention in NOISE_CONVENTIONS:
        sub = summary[summary["convention"] == convention].set_index(
            ["mode", "min_samples"]
        )
        print(f"\n  convention={convention}")
        for a, b in gaps:
            gap = abs(published_ari[a] - published_ari[b])
            for ms in MIN_SAMPLES_VALUES:
                for m in (a, b):
                    if (m, ms) not in sub.index:
                        continue
                    std = sub.loc[(m, ms), "swing_std"]
                    verdict = "EXCEEDS noise" if gap > std else "within noise band"
                    print(f"    gap({a},{b})={gap:.3f} vs {m}'s "
                          f"swing_std={std:.4f} at min_samples={ms}: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
