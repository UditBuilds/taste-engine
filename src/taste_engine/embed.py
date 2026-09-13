"""Phase 3 - embeddings and mood clustering.

Tracks are embedded as "{title} - {artist}" with `all-MiniLM-L6-v2`, which runs
locally and costs nothing. Embeddings are cached to `data/artifacts/` keyed by a
hash of the corpus, so re-clustering is instant.

Clustering uses **HDBSCAN**, which picks its own cluster count and labels
genuine outliers as noise rather than forcing every track into a group -
KMeans would need k up front and would assign every one-off track somewhere.

A deviation worth stating: this imports `sklearn.cluster.HDBSCAN` rather than
the standalone `hdbscan` package the brief named. It is the same algorithm
(upstreamed into scikit-learn by its author) and needs no C toolchain, which
matters on a machine without sudo.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# HDBSCAN degenerates in 384 dimensions: on this corpus it returned two
# clusters, one holding 78% of the library. Projecting to 20 principal
# components first is what makes the structure findable. Measured on the full
# 2,858-track set:
#
#   raw 384-d, mcs=12   ->  2 clusters, biggest 77.6%   (useless)
#   PCA 20-d,  mcs=8    -> 38 clusters, biggest 15.6%   (playlist-shaped)
#
# See scripts/cluster_sweep.py for the full grid.
PCA_COMPONENTS = 20
MIN_CLUSTER_SIZE = 8
MIN_SAMPLES = 2

# Release-furniture that carries no information about how a track sounds.
NOISE_PATTERNS = [
    r"\((?:official\s+)?(?:music\s+)?video\)",
    r"\[(?:official\s+)?(?:music\s+)?video\]",
    r"\((?:official\s+)?(?:audio|lyric[s]?|visualizer|hd|4k)\)",
    r"\[(?:official\s+)?(?:audio|lyric[s]?|visualizer|hd|4k)\]",
    r"\(official\)", r"\[official\]",
    r"\(prod\.?\s+by[^)]*\)",
    r"\(feat\.[^)]*\)", r"\[feat\.[^\]]*\]",
    r"\(ft\.[^)]*\)", r"\[ft\.[^\]]*\]",
    r"\bofficial\s+music\s+video\b", r"\bofficial\s+video\b", r"\bofficial\s+audio\b",
    r"\blyric[s]?\s+video\b", r"\bfull\s+video\b",
]
RE_NOISE = re.compile("|".join(NOISE_PATTERNS), re.I)
RE_SPACES = re.compile(r"\s{2,}")
RE_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def normalise_title(title: str | None) -> str:
    """Strip release furniture: '(Official Video)', '[Audio]', '(feat. X)'."""
    if not title:
        return ""
    text = RE_NOISE.sub(" ", str(title))
    text = text.replace("|", " ").strip(" -–—·|")
    return RE_SPACES.sub(" ", text).strip()


def artist_from_channel(channel: str | None) -> str:
    """Recover an artist name from a YouTube channel name.

    'PARTYNEXTDOOR - Topic' -> 'PARTYNEXTDOOR'
    'TravisScottVEVO'       -> 'Travis Scott'
    """
    if not channel:
        return ""
    name = str(channel).strip()
    if name.endswith(" - Topic"):
        return name[: -len(" - Topic")].strip()
    if "VEVO" in name:
        stem = name.replace("VEVO", "").strip()
        if stem and stem == stem.replace(" ", ""):  # run-together CamelCase
            stem = RE_CAMEL.sub(" ", stem)
        return stem.strip()
    return name


def build_corpus(df: pd.DataFrame) -> list[str]:
    """One embedding string per track."""
    texts = []
    for title, channel in zip(df["title"], df.get("channel", pd.Series([None] * len(df)))):
        clean_title = normalise_title(title)
        artist = artist_from_channel(channel)
        # Skip the artist when the title already leads with it.
        if artist and clean_title.lower().startswith(artist.lower()):
            texts.append(clean_title or artist)
        else:
            texts.append(f"{clean_title} - {artist}".strip(" -") or (clean_title or artist))
    return texts


def _cache_path(texts: list[str], model_name: str) -> Path:
    digest = hashlib.sha256(
        (model_name + "\x00" + "\x00".join(texts)).encode("utf-8")
    ).hexdigest()[:16]
    return config.ARTIFACTS_DIR / f"emb_{digest}.npy"


def embed_texts(
    texts: list[str],
    model_name: str = MODEL_NAME,
    use_cache: bool = True,
    show_progress: bool = False,
) -> np.ndarray:
    """Embed and L2-normalise, so Euclidean distance ranks like cosine."""
    cache = _cache_path(texts, model_name)
    if use_cache and cache.exists():
        return np.load(cache)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    vectors = model.encode(
        texts,
        batch_size=128,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=show_progress,
    )
    if use_cache:
        config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        np.save(cache, vectors)
    return vectors


def reduce_dims(vectors: np.ndarray, n_components: int = PCA_COMPONENTS) -> np.ndarray:
    """Project to `n_components` and re-normalise.

    Re-normalising after PCA keeps Euclidean distance ranking like cosine,
    which is the geometry MiniLM was trained for.
    """
    from sklearn.decomposition import PCA

    if n_components <= 0 or n_components >= vectors.shape[1]:
        return vectors
    n_components = min(n_components, vectors.shape[0], vectors.shape[1])
    reduced = PCA(n_components=n_components, random_state=0).fit_transform(vectors)
    norms = np.linalg.norm(reduced, axis=1, keepdims=True)
    return reduced / np.clip(norms, 1e-12, None)


def cluster_embeddings(
    vectors: np.ndarray,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    min_samples: int = MIN_SAMPLES,
    n_components: int = PCA_COMPONENTS,
) -> np.ndarray:
    """HDBSCAN labels; -1 means noise (a track that joins no mood)."""
    from sklearn.cluster import HDBSCAN

    reduced = reduce_dims(vectors, n_components)
    model = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        copy=True,
    )
    return model.fit_predict(reduced)


def name_cluster(frame: pd.DataFrame, max_artists: int = 3) -> str:
    """Name a cluster after the artists that dominate it."""
    artists = (
        frame["channel"].map(artist_from_channel).replace("", np.nan).dropna()
    )
    if artists.empty:
        return "Unnamed"
    top = artists.value_counts().head(max_artists)
    # A single artist owning most of the cluster is the whole story.
    if len(top) and top.iloc[0] / len(artists) > 0.6:
        return str(top.index[0])
    return " / ".join(str(a) for a in top.index)


def cluster_tracks(
    df: pd.DataFrame,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    min_samples: int = MIN_SAMPLES,
    model_name: str = MODEL_NAME,
    use_cache: bool = True,
    n_components: int = PCA_COMPONENTS,
) -> pd.DataFrame:
    """Embed, cluster, and attach `cluster` plus `cluster_name` columns."""
    out = df.copy().reset_index(drop=True)
    if out.empty:
        out["cluster"] = pd.Series(dtype="int64")
        out["cluster_name"] = pd.Series(dtype="object")
        return out

    texts = build_corpus(out)
    out["embed_text"] = texts
    vectors = embed_texts(texts, model_name=model_name, use_cache=use_cache)
    out["cluster"] = cluster_embeddings(
        vectors, min_cluster_size, min_samples, n_components
    )

    names = {
        label: name_cluster(group)
        for label, group in out[out["cluster"] >= 0].groupby("cluster")
    }
    names[-1] = "(outliers)"
    out["cluster_name"] = out["cluster"].map(names)
    return out


def cluster_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-cluster size, total score and headline track."""
    rows = []
    for label, group in df.groupby("cluster"):
        best = group.sort_values("score", ascending=False).iloc[0]
        rows.append(
            {
                "cluster": int(label),
                "name": group["cluster_name"].iloc[0],
                "tracks": len(group),
                "plays": int(group["play_count"].sum()),
                "mean_score": round(float(group["score"].mean()), 3),
                "top_track": str(best["title"])[:44],
            }
        )
    out = pd.DataFrame(rows).sort_values(
        ["cluster"], key=lambda s: s.map(lambda v: (v == -1, -v))
    )
    return out.reset_index(drop=True)


def main() -> int:
    from .db import connect
    from .score import scored_tracks

    conn = connect()
    try:
        tracks = scored_tracks(conn)
        print(f"embedding {len(tracks):,} tracks with {MODEL_NAME} ...", flush=True)
        clustered = cluster_tracks(tracks)
    finally:
        conn.close()

    n_clusters = int(clustered.loc[clustered["cluster"] >= 0, "cluster"].nunique())
    noise = int((clustered["cluster"] == -1).sum())
    print(f"\n{n_clusters} clusters, {noise:,} outliers "
          f"({noise / len(clustered):.1%} of tracks)\n")
    print(cluster_summary(clustered).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
