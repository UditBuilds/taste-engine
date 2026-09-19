"""Sweep clustering configs and report structure quality."""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from taste_engine.db import connect
from taste_engine.embed import build_corpus, embed_texts
from taste_engine.score import scored_tracks

conn = connect()
tracks = scored_tracks(conn)
conn.close()
texts = build_corpus(tracks)
X = embed_texts(texts)
print(f"{X.shape[0]:,} tracks, {X.shape[1]} dims\n")

def describe(labels, data):
    n = len({l for l in labels if l >= 0})
    noise = int((labels == -1).sum())
    if n == 0:
        return dict(clusters=0, noise_pct=100.0, biggest_pct=0.0, sil=float("nan"))
    sizes = pd.Series(labels[labels >= 0]).value_counts()
    sil = float("nan")
    if n > 1:
        mask = labels >= 0
        try:
            sil = silhouette_score(data[mask], labels[mask])
        except Exception:
            pass
    return dict(
        clusters=n,
        noise_pct=round(noise / len(labels) * 100, 1),
        biggest_pct=round(sizes.iloc[0] / len(labels) * 100, 1),
        median_size=int(sizes.median()),
        sil=round(sil, 3) if sil == sil else None,
    )

rows = []
# 1. raw 384-d
for mcs in (5, 8, 12, 20, 40):
    lab = HDBSCAN(min_cluster_size=mcs, min_samples=3, copy=True).fit_predict(X)
    rows.append({"config": f"raw384 mcs={mcs}", **describe(lab, X)})

# 2. PCA reductions
for dims in (10, 20, 40):
    Xp = PCA(n_components=dims, random_state=0).fit_transform(X)
    Xp = Xp / np.linalg.norm(Xp, axis=1, keepdims=True)
    for mcs in (8, 15, 25):
        lab = HDBSCAN(min_cluster_size=mcs, min_samples=3, copy=True).fit_predict(Xp)
        rows.append({"config": f"pca{dims} mcs={mcs}", **describe(lab, Xp)})

# 3. precomputed cosine on raw
D = (1.0 - X @ X.T).astype(np.float64)
np.fill_diagonal(D, 0.0)
D[D < 0] = 0.0
for mcs in (8, 15, 25):
    lab = HDBSCAN(min_cluster_size=mcs, min_samples=3, metric="precomputed",
                  copy=True).fit_predict(D)
    rows.append({"config": f"cosine mcs={mcs}", **describe(lab, X)})

df = pd.DataFrame(rows)
print(df.to_string(index=False))
print("\nWant: several clusters, biggest_pct well under ~40, noise_pct under ~35.")
