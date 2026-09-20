"""Generate (and execute) notebooks/01_eda.ipynb."""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "notebooks" / "01_eda.ipynb"

MD = new_markdown_cell
CODE = new_code_cell

cells = [
    MD(
        "# Exploratory analysis - 363 days of YouTube listening\n\n"
        "Everything here reads from `data/taste.db`, built by\n"
        "`python -m taste_engine.parse_takeout`. Nothing in this notebook calls\n"
        "the YouTube API, so it costs no quota to re-run.\n\n"
        "The questions it answers, in order:\n\n"
        "1. What is actually in the export, and what is broken about it?\n"
        "2. How concentrated is the listening?\n"
        "3. Which of the watched videos are music, and how confidently do we know?\n"
        "4. What structure does the library have?\n"
        "5. Does the model beat the most-played baseline?"
    ),
    CODE(
        "import sys, warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "sys.path.insert(0, '../src')\n\n"
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n\n"
        "from taste_engine.db import connect\n"
        "from taste_engine import classify, score, embed, evaluate, config\n\n"
        "plt.rcParams.update({'figure.figsize': (9, 3.4), 'axes.grid': True,\n"
        "                     'grid.alpha': .25, 'axes.spines.top': False,\n"
        "                     'axes.spines.right': False, 'font.size': 9})\n"
        "conn = connect()\n"
        "print('db:', config.DB_PATH)"
    ),
    MD("## 1. What is in the export"),
    CODE(
        "counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]\n"
        "          for t in ('plays', 'playlists', 'playlist_tracks', 'library_songs')}\n"
        "counts['unique videos'] = conn.execute(\n"
        "    'SELECT COUNT(DISTINCT video_id) FROM plays').fetchone()[0]\n"
        "counts['plays w/o channel'] = conn.execute(\n"
        "    'SELECT COUNT(*) FROM plays WHERE channel IS NULL').fetchone()[0]\n"
        "lo, hi = conn.execute('SELECT MIN(watched_at), MAX(watched_at) FROM plays').fetchone()\n"
        "print(pd.Series(counts).to_string())\n"
        "print(f'\\nrange: {lo[:10]} -> {hi[:10]}')"
    ),
    MD(
        "### The 12-month wall\n\n"
        "Auto-delete is on, so the history starts abruptly on 2025-09-14 and this\n"
        "dataset will never grow backwards. Any 'listening over time' chart has a\n"
        "hard left edge that is an artefact of Google's retention policy, not of\n"
        "the user's behaviour."
    ),
    CODE(
        "plays = pd.read_sql('SELECT video_id, watched_at, source FROM plays', conn)\n"
        "plays['day'] = pd.to_datetime(plays.watched_at, format='ISO8601', utc=True).dt.date\n"
        "daily = plays.groupby('day').size()\n\n"
        "ax = daily.plot(lw=.8, color='#444')\n"
        "daily.rolling(14).mean().plot(ax=ax, lw=2, color='#c0392b', label='14-day mean')\n"
        "ax.set_title(f'Plays per day  ({daily.sum():,} across {len(daily)} active days)')\n"
        "ax.set_xlabel(''); ax.legend(); plt.tight_layout(); plt.show()"
    ),
    MD(
        "### Playlist timestamps are not a signal\n\n"
        "53 of 58 playlists claim to have been created on one of two days in March\n"
        "2026 - a bulk import, not user behaviour - and the export restamped almost\n"
        "every `updated_at` to the export date. Playlist recency is therefore\n"
        "unusable, which is asserted in `tests/test_dataset_facts.py` so nothing\n"
        "downstream starts relying on it."
    ),
    MD(
        "Playlist titles are pseudonymised (`Playlist A`, `Playlist B`, ...) before\n"
        "they reach any output in this notebook. Every metric that uses them treats\n"
        "them as opaque group labels, so the real names add nothing to the analysis\n"
        "and this repo is public. Track, artist and cluster names are the substance\n"
        "and are shown as-is. The mapping is written to `data/playlist_aliases.json`,\n"
        "which is gitignored. See `taste_engine/redact.py`."
    ),
    CODE(
        "from taste_engine import redact\n"
        "pl = pd.read_sql('SELECT title, created_at, updated_at FROM playlists', conn)\n"
        "pl['label'] = redact.redact_series(pl.title, redact.aliases_for(conn))\n\n"
        "print('created_at:'); print(pl.created_at.str[:10].value_counts().to_string())\n"
        "print('\\nupdated_at:'); print(pl.updated_at.str[:10].value_counts().head(3).to_string())\n"
        "dupes = pl.label.value_counts()\n"
        "print(f'\\nduplicate playlist titles: {(dupes > 1).sum()} '\n"
        "      f'(e.g. {dupes.index[0]} x{dupes.iloc[0]})')"
    ),
    MD("## 2. How concentrated is the listening?"),
    CODE(
        "tracks = score.scored_tracks(conn)\n"
        "pc = tracks.play_count.sort_values(ascending=False).reset_index(drop=True)\n"
        "print(f'{len(pc):,} music tracks, {pc.sum():,} plays')\n"
        "for n in (20, 50, 100, 500):\n"
        "    print(f'  top {n:>3} tracks = {pc.head(n).sum() / pc.sum():>5.1%} of plays')\n"
        "print(f'  played exactly once: {(pc == 1).mean():.1%} of tracks')\n\n"
        "fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.2))\n"
        "a.loglog(range(1, len(pc) + 1), pc.values, lw=1.4, color='#c0392b')\n"
        "a.set(title='Play-count distribution (log-log)', xlabel='rank', ylabel='plays')\n"
        "b.plot(pc.cumsum().values / pc.sum(), lw=1.8, color='#2c3e50')\n"
        "b.set(title='Cumulative share of plays', xlabel='tracks (ranked)', ylabel='share')\n"
        "plt.tight_layout(); plt.show()"
    ),
    MD(
        "A 60% one-play rate is why `log1p` matters. Raw counts would let a handful\n"
        "of obsessively repeated tracks dominate every playlist; `log1p` keeps the\n"
        "gap meaningful without letting it crush the tail."
    ),
    MD(
        "## 3. Which videos are music?\n\n"
        "Five signals, none of which costs API quota. The union is the training set."
    ),
    CODE(
        "cov = classify.signal_coverage(conn)\n"
        "print(cov.to_string(index=False))\n\n"
        "ax = cov.iloc[:-1].plot.barh(x='signal', y='videos', legend=False,\n"
        "                             color='#2c3e50')\n"
        "ax.axvline(cov.videos.iloc[-1], color='#c0392b', ls='--',\n"
        "           label=f'union = {cov.videos.iloc[-1]:,}')\n"
        "ax.set(title='Unique videos matched per music signal', ylabel='')\n"
        "ax.legend(); plt.tight_layout(); plt.show()"
    ),
    MD(
        "The signals overlap heavily: they sum to 6,158 but the union is only 2,858.\n"
        "They also share a blind spot - an artist-owned channel with no `- Topic` or\n"
        "`VEVO` marker is invisible to all five. `videos.list` fixes that for 609\n"
        "units; see `taste_engine.resolve`."
    ),
    CODE(
        "if classify.has_metadata(conn):\n"
        "    t = classify.comparison_table(conn)\n"
        "    print(f\"agreement   {t['agreement_rate']:.1%}\")\n"
        "    print(f\"precision   {t['heuristic_precision']:.1%}\")\n"
        "    print(f\"recall      {t['heuristic_recall']:.1%}\")\n"
        "    print(t['confusion'])\n"
        "else:\n"
        "    print('No API metadata cached - heuristic labels only.')\n"
        "    print('Run: python -m taste_engine.resolve   (609 units)')"
    ),
    MD("## 4. What structure does the library have?"),
    CODE(
        "clustered = embed.cluster_tracks(tracks)\n"
        "summary = embed.cluster_summary(clustered)\n"
        "n = int(clustered.loc[clustered.cluster >= 0, 'cluster'].nunique())\n"
        "noise = (clustered.cluster == -1).mean()\n"
        "print(f'{n} clusters, {noise:.1%} outliers')\n"
        "summary[summary.cluster >= 0].head(15)"
    ),
    MD(
        "Two honest caveats.\n\n"
        "**These are artist clusters, not moods.** The embedding text is\n"
        "`\"{title} - {artist}\"`, so MiniLM keys heavily on the artist name. Genre\n"
        "is a decent proxy for mood, but a track that sounds nothing like the rest\n"
        "of an artist's catalogue still lands with them.\n\n"
        "**~40% of tracks are outliers.** Given 60% of tracks were played exactly\n"
        "once, that is closer to honest than alarming - HDBSCAN is refusing to\n"
        "invent a mood for a one-off listen, which is exactly why it was chosen\n"
        "over KMeans."
    ),
    MD(
        "### Is the artist the problem? Test it, do not assume it\n\n"
        "The obvious fix is to drop the artist and embed title plus genre. Scored\n"
        "against an **external** ground truth - the user's own 48 playlists,\n"
        "restricted to tracks filed in exactly one - it makes things worse.\n"
        "Silhouette would measure tidiness in the space the clustering was built\n"
        "from, which is circular; a human saying 'these belong together' is not."
    ),
    CODE(
        "from taste_engine import cluster_eval\n"
        "cluster_eval.compare_modes(conn, tracks)"
    ),
    MD(
        "Bare titles (`TBH`, `20 Min`, `Ready`) carry almost no semantic signal, so\n"
        "noise jumps and coverage collapses. Genre tags do help coverage - there\n"
        "are only 35 distinct ones, so the buckets are broad and cut across the\n"
        "finer distinctions the user actually drew. `coverage` is reported so a\n"
        "clustering cannot win by calling everything noise.\n\n"
        "Caveat: the ground truth is itself partly artist-shaped - several\n"
        "playlists are single-artist collections - so it rewards artist clustering\n"
        "to some degree by construction."
    ),
    CODE(
        "top = summary[summary.cluster >= 0].nlargest(12, 'plays')\n"
        "ax = top.plot.barh(x='name', y='plays', legend=False, color='#2c3e50')\n"
        "ax.set(title='Plays per cluster (top 12)', ylabel='')\n"
        "ax.invert_yaxis(); plt.tight_layout(); plt.show()"
    ),
    MD(
        "## 5. Does it beat the baseline?\n\n"
        "Temporal hold-out: train strictly before the split, test after. The model\n"
        "sees no test-window play - not for scoring, not for clustering.\n\n"
        "### Rediscovery - the task that matters\n\n"
        "Remove the training window's 50 most-played tracks from both the\n"
        "candidate pool and the ground truth, then ask what else gets played.\n"
        "'Name the tracks he plays most' *is* the baseline; a model that agrees\n"
        "with it has not recommended anything."
    ),
    CODE(
        "redis = evaluate.evaluate_rediscovery(conn, k=20,\n"
        "                                      test_days=config.EVAL_TEST_DAYS)\n"
        "print(f\"candidates {redis['candidates']:,} | reachable truth \"\n"
        "      f\"{redis['reachable']:,} | ceiling@20 {redis['ceiling']:.1%}\")\n"
        "redis['results']"
    ),
    MD(
        "`recall@20` is capped at the ceiling printed above - 20 picks against\n"
        "hundreds of reachable tracks - so it is for comparing strategies, not a\n"
        "headline. Note `hits` and `ndcg` can disagree: nDCG is graded by how many\n"
        "times a track was actually replayed, so a few heavy-rotation finds beat\n"
        "many marginal ones."
    ),
    CODE(
        "detail, summary_r = evaluate.rediscovery_robustness(\n"
        "    conn, k=20, test_days=config.EVAL_TEST_DAYS)\n"
        "summary_r"
    ),
    MD(
        "### Replay - the trivial task, shown for contrast\n\n"
        "Rank the whole catalogue by what gets played next. Run as originally\n"
        "specified (precision@20, full 105-day window) the **baseline scores\n"
        "1.00** - a track played 50 times in nine months is certain to recur in\n"
        "the next three. A metric that cannot go up cannot rank anything."
    ),
    CODE(
        "sat = evaluate.evaluate(conn, k=20, test_days=None)\n"
        "print(f\"precision@20, full 105-day window - saturated: {sat['saturated']}\")\n"
        "sat['results'][['strategy', 'hits', 'precision@20', 'ndcg@20']]"
    ),
    MD(
        "Shortening the horizon and raising k restores discrimination - and on\n"
        "this task the baseline is genuinely competitive, which is the point."
    ),
    CODE(
        "report = evaluate.evaluate(conn, test_days=config.EVAL_TEST_DAYS)\n"
        "print(f\"train < {report['split_date']} <= test ({report['test_days']}d), \"\n"
        "      f\"k={report['k']}, half-life={report['half_life']:.0f}d\")\n"
        "report['results']"
    ),
    MD(
        "### The result that does not flatter the model\n\n"
        "Over the *whole* catalogue, raw play count correlates better with future\n"
        "play volume than the recency-weighted score does - see the `spearman`\n"
        "column above. Recency helps at the head of the list, which is what a\n"
        "playlist draws from, and hurts in the tail. Both are true and both are\n"
        "reported."
    ),
    CODE("conn.close()\nprint('done')"),
]


class OutputWouldBeStripped(RuntimeError):
    """Writing now would silently discard already-committed cell outputs."""


def _cell_outputs_exist(path: Path) -> bool:
    """True if `path` exists and already has at least one executed code cell.

    Used to refuse the write that stripped 15 cells of committed output from
    notebooks/01_eda.ipynb - a run of this script without --execute, which
    was only caught by `git diff`, not by anything in this script.
    """
    if not path.exists():
        return False
    old = nbf.read(path, as_version=4)
    return any(c.get("cell_type") == "code" and c.get("outputs") for c in old["cells"])


def build(out: Path = OUT, execute: bool = False, allow_output_loss: bool = False) -> Path:
    if not execute and not allow_output_loss and _cell_outputs_exist(out):
        raise OutputWouldBeStripped(
            f"{out} already has cell outputs; writing without --execute would "
            "blank them. Pass --execute to regenerate outputs, or "
            "--allow-output-loss to write without them anyway."
        )

    nb = new_notebook(cells=cells)
    nb.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        }
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, out)
    print(f"wrote {out} ({len(cells)} cells)")

    if execute:
        from nbclient import NotebookClient

        nb = nbf.read(out, as_version=4)
        client = NotebookClient(
            nb, timeout=1800, kernel_name="python3",
            resources={"metadata": {"path": str(out.parent)}},
        )
        client.execute()
        nbf.write(nb, out)
        print("executed and saved with outputs")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        build(execute="--execute" in argv, allow_output_loss="--allow-output-loss" in argv)
    except OutputWouldBeStripped as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
