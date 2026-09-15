"""Phase 3 - temporal hold-out evaluation.

Train on plays before the split date, test on plays after it. The model never
sees a play from the test window - not for scoring, not for clustering, not for
choosing a half-life.

**Why there are three metrics and not one.** The brief asked for precision@20
against a "20 most-played tracks" baseline. Run exactly as specified - train to
2026-06-01, test on the remaining 105 days - that baseline scores **1.00**. Not
because the model is good, but because a track played 50 times in nine months
is certain to be played again in the next three. A saturated metric cannot rank
anything, so it is reported and then set aside in favour of two that can:

* **precision@k** on a bounded test window. Shortening the horizon from 105
  days to 14-30 restores discrimination.
* **nDCG@k**, graded by how many times a track was actually replayed. Getting
  the heavy-rotation track into position 1 should beat getting it into
  position 40; binary precision cannot see that difference.
* **Spearman** between each strategy's ranking key and true test play counts,
  over the whole candidate set rather than the top k.

Run:  python -m taste_engine.evaluate
      python -m taste_engine.evaluate --test-days 30 -k 50 --sweep-half-life
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import config
from .embed import cluster_tracks
from .recommend import STRATEGIES, recommend
from .score import scored_tracks

# The column each strategy ranks by, for the whole-catalogue rank correlation.
# cluster_diverse interleaves clusters and induces no single global key.
RANK_KEYS: dict[str, tuple[str, bool] | None] = {
    "most_played": ("play_count", False),
    "score": ("score", False),
    "recency": ("days_since", True),
    "cluster_diverse": None,
}


def _window_end(
    split_date: str, test_days: int | None, test_end: str | None = None
) -> str | None:
    if test_days and test_end:
        raise ValueError("--test-days and --test-end are mutually exclusive")
    if test_end:
        return test_end
    if not test_days:
        return None
    return (datetime.fromisoformat(split_date) + timedelta(days=test_days)).date().isoformat()


def split_frames(
    conn: sqlite3.Connection,
    split_date: str,
    half_life: float | None = None,
    cluster: bool = True,
    test_days: int | None = None,
    canonical: bool = True,
    test_end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Training frame scored as of the split, plus test-window play counts.

    `as_of=split_date` is the load-bearing detail: scoring the training window
    from today would leak the length of the test window into the recency term.

    `test_end`, when given, bounds the test window at that absolute date
    instead of `test_days` after `split_date` — see `_window_end`.
    """
    train = scored_tracks(
        conn, start=None, end=split_date, as_of=split_date, half_life=half_life,
        canonical=canonical,
    )
    test = scored_tracks(
        conn, start=split_date, end=_window_end(split_date, test_days, test_end),
        as_of=None, canonical=canonical,
    )
    if cluster and not train.empty:
        train = cluster_tracks(train)
    return train, test


def precision_at_k(recommended: list[str], actual: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return len([v for v in recommended[:k] if v in actual]) / k


def ndcg_at_k(recommended: list[str], relevance: dict[str, float], k: int) -> float:
    """Graded nDCG - relevance is the track's true test-window play count."""
    if k <= 0:
        return 0.0
    gains = [relevance.get(v, 0.0) for v in recommended[:k]]
    dcg = sum(g / np.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(g / np.log2(i + 2) for i, g in enumerate(ideal))
    return float(dcg / idcg) if idcg else 0.0


def evaluate(
    conn: sqlite3.Connection,
    split_date: str | None = None,
    k: int | None = None,
    half_life: float | None = None,
    strategies: list[str] | None = None,
    test_days: int | None = None,
    canonical: bool = True,
    test_end: str | None = None,
) -> dict:
    split_date = split_date or config.EVAL_SPLIT_DATE
    k = k or config.EVAL_K
    names = strategies or list(STRATEGIES)

    train, test = split_frames(
        conn, split_date, half_life, test_days=test_days, canonical=canonical,
        test_end=test_end,
    )
    if train.empty or test.empty:
        raise ValueError(f"empty train or test window at split {split_date}")

    test_ids = set(test["video_id"])
    relevance = dict(zip(test["video_id"], test["play_count"].astype(float)))

    candidates = set(train["video_id"])
    repeatable = candidates & test_ids
    ceiling = min(k, len(repeatable)) / k

    truth = train.merge(
        test[["video_id", "play_count"]].rename(columns={"play_count": "test_plays"}),
        on="video_id",
        how="left",
    )
    truth["test_plays"] = truth["test_plays"].fillna(0.0)

    rows = []
    for name in names:
        ids = recommend(train, n=k, strategy=name)["video_id"].tolist()
        key = RANK_KEYS.get(name)
        if key:
            column, ascending = key
            signal = -truth[column] if ascending else truth[column]
            spearman = float(signal.corr(truth["test_plays"], method="spearman"))
        else:
            spearman = float("nan")
        rows.append(
            {
                "strategy": name,
                "hits": len([v for v in ids if v in test_ids]),
                f"precision@{k}": round(precision_at_k(ids, test_ids, k), 4),
                f"ndcg@{k}": round(ndcg_at_k(ids, relevance, k), 4),
                "spearman": round(spearman, 4) if spearman == spearman else None,
            }
        )

    results = pd.DataFrame(rows).sort_values(f"ndcg@{k}", ascending=False)
    baseline = results.set_index("strategy").loc["most_played", f"precision@{k}"]

    return {
        "split_date": split_date,
        "test_days": test_days,
        "test_end": test_end,
        "k": k,
        "half_life": half_life or config.RECENCY_HALF_LIFE_DAYS,
        "train_tracks": len(train),
        "train_plays": int(train["play_count"].sum()),
        "test_tracks": len(test_ids),
        "test_plays": int(test["play_count"].sum()),
        "repeatable": len(repeatable),
        "cold_start": len(test_ids - candidates),
        "ceiling": round(ceiling, 4),
        "saturated": bool(baseline >= 1.0),
        "results": results,
    }


def rediscovery_split(
    conn: sqlite3.Connection,
    split_date: str,
    half_life: float | None = None,
    exclude_top: int = 50,
    test_days: int | None = None,
    cluster: bool = True,
    canonical: bool = True,
    test_end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, set[str]]:
    """Hold out the obvious favourites, then ask what else gets played.

    The replay task is rigged in the baseline's favour by construction: a
    track played 50 times in nine months will be played again, and naming it
    is not a recommendation. Removing the training window's top `exclude_top`
    tracks from both the candidate pool and the ground truth leaves the
    question the product actually has to answer - what does he come back to
    that he was not already hammering?
    """
    train, test = split_frames(
        conn, split_date, half_life, cluster=cluster, test_days=test_days,
        canonical=canonical, test_end=test_end,
    )
    # Shared with the writer's `--mode rediscover`, so the playlist that ships
    # is drawn from the same pool this scores. See `recommend.favourites`.
    from .recommend import favourites

    obvious = favourites(train, exclude_top)
    candidates = train[~train["video_id"].isin(obvious)].reset_index(drop=True)
    truth = test[~test["video_id"].isin(obvious)].reset_index(drop=True)
    return candidates, truth, obvious


def evaluate_rediscovery(
    conn: sqlite3.Connection,
    split_date: str | None = None,
    k: int = 20,
    half_life: float | None = None,
    strategies: list[str] | None = None,
    exclude_top: int = 50,
    test_days: int | None = None,
    canonical: bool = True,
    test_end: str | None = None,
) -> dict:
    """recall@k and nDCG@k on the non-obvious tracks.

    `recall@k` is measured against *reachable* truth - test tracks that appear
    in the candidate pool at all. A track first played after the split cannot
    be retrieved by any strategy, so counting it as a miss would measure the
    catalogue, not the ranking.
    """
    split_date = split_date or config.EVAL_SPLIT_DATE
    names = strategies or list(STRATEGIES)

    # Clustering is only needed by cluster_diverse; skipping it when that
    # strategy is not requested makes a half-life sweep tractable.
    candidates, truth, obvious = rediscovery_split(
        conn, split_date, half_life, exclude_top, test_days,
        cluster="cluster_diverse" in names, canonical=canonical, test_end=test_end,
    )
    if candidates.empty or truth.empty:
        raise ValueError(f"empty candidate or truth set at split {split_date}")

    truth_ids = set(truth["video_id"])
    reachable = truth_ids & set(candidates["video_id"])
    relevance = dict(zip(truth["video_id"], truth["play_count"].astype(float)))
    # Only reachable tracks can contribute to the ideal ordering.
    reachable_relevance = {v: relevance[v] for v in reachable}

    ceiling = min(k, len(reachable)) / len(reachable) if reachable else 0.0

    rows = []
    for name in names:
        ids = recommend(candidates, n=k, strategy=name)["video_id"].tolist()
        hits = [v for v in ids if v in reachable]
        rows.append(
            {
                "strategy": name,
                "hits": len(hits),
                f"recall@{k}": round(len(hits) / len(reachable), 4) if reachable else 0.0,
                f"precision@{k}": round(precision_at_k(ids, reachable, k), 4),
                f"ndcg@{k}": round(ndcg_at_k(ids, reachable_relevance, k), 4),
            }
        )

    return {
        "task": "rediscovery",
        "split_date": split_date,
        "test_days": test_days,
        "test_end": test_end,
        "k": k,
        "exclude_top": exclude_top,
        "half_life": half_life or config.RECENCY_HALF_LIFE_DAYS,
        "excluded": len(obvious),
        "candidates": len(candidates),
        "truth": len(truth_ids),
        "reachable": len(reachable),
        "ceiling": round(ceiling, 4),
        "results": pd.DataFrame(rows).sort_values(f"ndcg@{k}", ascending=False),
    }


def rediscovery_robustness(
    conn: sqlite3.Connection,
    splits: list[str] | None = None,
    k: int = 20,
    half_life: float | None = None,
    exclude_top: int = 50,
    test_days: int | None = None,
    min_reachable: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The rediscovery comparison at every usable split."""
    splits = splits or [
        "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01",
    ]
    strategies = list(STRATEGIES)
    rows = []
    for split in splits:
        try:
            report = evaluate_rediscovery(
                conn, split, k, half_life, strategies=strategies,
                exclude_top=exclude_top, test_days=test_days
            )
        except ValueError:
            continue
        if report["reachable"] < min_reachable:
            continue
        r = report["results"].set_index("strategy")
        record = {"split": split, "reachable": report["reachable"]}
        for name in r.index:
            record[f"{name}_ndcg"] = r.loc[name, f"ndcg@{k}"]
            record[f"{name}_recall"] = r.loc[name, f"recall@{k}"]
        rows.append(record)

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, detail

    summary = pd.DataFrame(
        [
            {
                "strategy": name,
                f"mean_ndcg@{k}": detail[f"{name}_ndcg"].mean(),
                f"mean_recall@{k}": detail[f"{name}_recall"].mean(),
                "beats_baseline": int(
                    (detail[f"{name}_ndcg"] > detail["most_played_ndcg"]).sum()
                ),
                "splits": len(detail),
            }
            for name in STRATEGIES
            if f"{name}_ndcg" in detail.columns
        ]
    ).sort_values(f"mean_ndcg@{k}", ascending=False)
    return detail, summary


def rediscovery_half_life_sweep(
    conn: sqlite3.Connection,
    half_lives: list[float] | None = None,
    k: int = 20,
    exclude_top: int = 50,
    test_days: int | None = None,
) -> pd.DataFrame:
    """Tune the decay on the task the product is actually for.

    The replay task is the wrong thing to tune against: it rewards agreeing
    with the most-played baseline, which is the behaviour rediscovery is trying
    to avoid. `most_played` is invariant to half-life, so its column is a
    control - if it moves, something is leaking.
    """
    half_lives = half_lives or [7, 14, 30, 60, 90, 180, 365]
    rows = []
    for half_life in half_lives:
        detail, _ = rediscovery_robustness(
            conn, k=k, half_life=half_life, exclude_top=exclude_top,
            test_days=test_days,
        )
        if detail.empty:
            continue
        rows.append(
            {
                "half_life": half_life,
                "splits": len(detail),
                "wins": int((detail["score_ndcg"] > detail["most_played_ndcg"]).sum()),
                "mean_ndcg": detail["score_ndcg"].mean(),
                "worst_lift": (
                    (detail["score_ndcg"] - detail["most_played_ndcg"])
                    / detail["most_played_ndcg"]
                ).min(),
                "baseline_ndcg": detail["most_played_ndcg"].mean(),
            }
        )
    return pd.DataFrame(rows)


MONTHLY_SPLITS = [
    "2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01",
    "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01",
]


def nested_rediscovery(
    conn: sqlite3.Connection,
    splits: list[str] | None = None,
    half_lives: list[float] | None = None,
    k: int = 20,
    exclude_top: int = 50,
    test_days: int | None = None,
    min_reachable: int = 20,
    canonical: bool = True,
) -> dict:
    """Select the half-life on early splits, report on later ones it never saw.

    Tuning a hyperparameter on the same splits you then report is selection
    bias: it turns the reported lift into an upper bound rather than an
    estimate. This splits the timeline in two - the earlier months choose the
    half-life, the later months score it, and the later months are never
    consulted during selection.

    With a handful of held-out splits this cannot establish significance. It
    can establish whether the effect survives honest tuning at all, which is
    the question.
    """
    splits = splits or MONTHLY_SPLITS
    half_lives = half_lives or [7, 14, 30, 60, 90, 180, 365]
    test_days = test_days if test_days is not None else config.EVAL_TEST_DAYS

    # Keep only splits with enough reachable truth to discriminate. Done once,
    # at a fixed half-life, so the usable set cannot depend on the tuning.
    usable = []
    for split in splits:
        try:
            probe = evaluate_rediscovery(
                conn, split, k, half_life=30, strategies=["most_played"],
                exclude_top=exclude_top, test_days=test_days, canonical=canonical,
            )
        except ValueError:
            continue
        if probe["reachable"] >= min_reachable:
            usable.append({"split": split, "reachable": probe["reachable"]})

    if len(usable) < 4:
        return {"status": "too few usable splits", "usable": usable}

    cut = len(usable) // 2
    dev = [u["split"] for u in usable[:cut]]
    held = [u["split"] for u in usable[cut:]]

    def _score(split_list, half_life):
        rows = []
        for split in split_list:
            report = evaluate_rediscovery(
                conn, split, k, half_life, strategies=["most_played", "score"],
                exclude_top=exclude_top, test_days=test_days, canonical=canonical,
            )
            r = report["results"].set_index("strategy")
            rows.append(
                {
                    "split": split,
                    "baseline": r.loc["most_played", f"ndcg@{k}"],
                    "score": r.loc["score", f"ndcg@{k}"],
                }
            )
        return pd.DataFrame(rows)

    # --- selection, on dev only ---
    dev_rows = []
    for half_life in half_lives:
        frame = _score(dev, half_life)
        dev_rows.append(
            {
                "half_life": half_life,
                "mean_baseline": frame["baseline"].mean(),
                "mean_score": frame["score"].mean(),
                "wins": int((frame["score"] > frame["baseline"]).sum()),
                "splits": len(frame),
            }
        )
    dev_table = pd.DataFrame(dev_rows)
    dev_table["lift"] = (
        dev_table["mean_score"] - dev_table["mean_baseline"]
    ) / dev_table["mean_baseline"]
    chosen = float(
        dev_table.sort_values(["wins", "mean_score"], ascending=False).iloc[0]["half_life"]
    )

    # --- reporting, on held-out splits the selection never touched ---
    held_frame = _score(held, chosen)
    held_frame["lift"] = (
        held_frame["score"] - held_frame["baseline"]
    ) / held_frame["baseline"]
    held_frame["win"] = held_frame["score"] > held_frame["baseline"]

    mean_base = held_frame["baseline"].mean()
    mean_score = held_frame["score"].mean()
    wins = int(held_frame["win"].sum())
    n = len(held_frame)

    # Sign test against a coin flip.
    p_value = sum(
        _n_choose_k(n, i) for i in range(wins, n + 1)
    ) / (2 ** n) if n else 1.0
    # The best p this many splits can possibly produce - a clean sweep. At n=3
    # that is 0.125, so "not significant" there means "this sample size cannot
    # certify anything", not "no effect". Reporting the floor stops a large,
    # consistent lift being written off as a null result.
    p_floor = 1 / (2 ** n) if n else 1.0
    underpowered = p_floor >= 0.05

    return {
        "status": "ok",
        "usable_splits": usable,
        "dev_splits": dev,
        "held_out_splits": held,
        "dev_table": dev_table,
        "chosen_half_life": chosen,
        "held_out": held_frame,
        "mean_baseline": mean_base,
        "mean_score": mean_score,
        "lift": (mean_score - mean_base) / mean_base if mean_base else 0.0,
        "wins": wins,
        "n": n,
        "sign_test_p": p_value,
        "p_floor": p_floor,
        "underpowered": underpowered,
        "significant": bool(p_value < 0.05),
        "verdict": _verdict(wins, n, p_value, p_floor, mean_base, mean_score),
    }


def _verdict(wins: int, n: int, p: float, p_floor: float, base: float, score: float) -> str:
    """Say what the numbers support - no more, and no less.

    Three outcomes worth distinguishing, because collapsing them into
    significant/not-significant misreports two of them:
      * certified improvement
      * a consistent, possibly large lift that this n cannot certify
      * no improvement
    """
    lift = (score - base) / base if base else 0.0
    if p < 0.05:
        return (
            f"Improvement over the most-played baseline: {lift:+.0%}, "
            f"{wins}/{n} splits, sign-test p = {p:.3f}."
        )
    if wins == n and p_floor >= 0.05:
        need = 5  # 1/2**5 = 0.031, the first n whose clean sweep clears 0.05
        return (
            f"Lift of {lift:+.0%} winning {wins}/{n} splits, but NOT statistically "
            f"established: with {n} held-out splits a clean sweep gives "
            f"p = {p_floor:.3f}, so no result at this sample size can reach "
            f"p < 0.05. At least {need} held-out splits would be needed. "
            "The effect is consistent and large; the evidence is thin."
        )
    return (
        f"No significant improvement over the most-played baseline "
        f"({lift:+.0%}, {wins}/{n} splits, p = {p:.3f})."
    )


def _n_choose_k(n: int, k: int) -> int:
    from math import comb

    return comb(n, k)


def sweep(
    conn: sqlite3.Connection,
    metric: str = "ndcg",
    half_lives: list[float] | None = None,
    split_date: str | None = None,
    k: int | None = None,
    test_days: int | None = None,
    test_end: str | None = None,
) -> pd.DataFrame:
    """Tune the decay against the hold-out, as section 7.1 asks.

    `most_played` is invariant to half-life, so its column doubles as a
    control: if it moves, something is leaking.

    Single split (`split_date`, fixed across the sweep) - `test_end` is
    coherent here, unlike the multi-split sweeps below.
    """
    half_lives = half_lives or [7, 14, 30, 60, 90, 180, 365, 10_000]
    k = k or config.EVAL_K
    column = f"{metric}@{k}" if metric in ("ndcg", "precision") else metric
    rows = []
    for half_life in half_lives:
        report = evaluate(conn, split_date, k, half_life, test_days=test_days, test_end=test_end)
        record = {"half_life": half_life}
        for _, r in report["results"].iterrows():
            record[r["strategy"]] = r[column]
        rows.append(record)
    return pd.DataFrame(rows)


def sweep_splits(
    conn: sqlite3.Connection,
    splits: list[str],
    k: int | None = None,
    test_days: int | None = None,
) -> pd.DataFrame:
    """The same comparison at several boundaries.

    One split on 363 days of data is a single sample; a result that holds at
    only one boundary is not a result.
    """
    k = k or config.EVAL_K
    rows = []
    for split in splits:
        try:
            report = evaluate(conn, split, k, test_days=test_days)
        except ValueError:
            continue
        record = {"split": split, "test_tracks": report["test_tracks"]}
        for _, r in report["results"].iterrows():
            record[r["strategy"]] = r[f"ndcg@{k}"]
        rows.append(record)
    return pd.DataFrame(rows)


def robustness(
    conn: sqlite3.Connection,
    half_lives: list[float] | None = None,
    splits: list[str] | None = None,
    k: int | None = None,
    test_days: int | None = None,
    min_test_tracks: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Does the score beat the baseline at *every* split, or just one?

    Selecting a half-life by its best single score is test-set fitting. This
    picks on consistency instead: the setting that never loses beats the
    setting that sometimes wins big.

    Splits whose test window holds fewer than `k` tracks are dropped - they are
    ceiling-limited and cannot separate two strategies.
    """
    half_lives = half_lives or [7, 30, 90, 180]
    splits = splits or [
        "2026-02-01", "2026-03-01", "2026-04-01",
        "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01",
    ]
    k = k or config.EVAL_K
    test_days = test_days or config.EVAL_TEST_DAYS
    min_test_tracks = k if min_test_tracks is None else min_test_tracks

    rows = []
    for split in splits:
        for half_life in half_lives:
            try:
                report = evaluate(conn, split, k, half_life, test_days=test_days)
            except ValueError:
                continue
            if report["test_tracks"] < min_test_tracks:
                continue  # ceiling-limited, cannot discriminate
            r = report["results"].set_index("strategy")
            rows.append(
                {
                    "split": split,
                    "half_life": half_life,
                    "test_tracks": report["test_tracks"],
                    "base_ndcg": r.loc["most_played", f"ndcg@{k}"],
                    "score_ndcg": r.loc["score", f"ndcg@{k}"],
                    "base_precision": r.loc["most_played", f"precision@{k}"],
                    "score_precision": r.loc["score", f"precision@{k}"],
                }
            )

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, detail
    detail["ndcg_lift"] = (detail.score_ndcg - detail.base_ndcg) / detail.base_ndcg
    detail["win"] = detail.score_ndcg > detail.base_ndcg

    summary = (
        detail.groupby("half_life")
        .agg(
            splits=("win", "size"),
            wins=("win", "sum"),
            mean_lift=("ndcg_lift", "mean"),
            worst_lift=("ndcg_lift", "min"),
            mean_precision=("score_precision", "mean"),
            base_precision=("base_precision", "mean"),
        )
        .reset_index()
    )
    return detail, summary


def _print_report(report: dict) -> None:
    k = report["k"]
    if report.get("test_end"):
        horizon = f"to {report['test_end']}"
    elif report["test_days"]:
        horizon = f"{report['test_days']}d"
    else:
        horizon = "to end of data"
    print(f"Temporal hold-out  train < {report['split_date']} <= test ({horizon})")
    print(f"  half-life         {report['half_life']:>8.0f} days")
    print(f"  train tracks      {report['train_tracks']:>8,} "
          f"({report['train_plays']:,} plays)")
    print(f"  test tracks       {report['test_tracks']:>8,} "
          f"({report['test_plays']:,} plays)")
    print(f"  seen in train     {report['repeatable']:>8,} "
          f"(cold start: {report['cold_start']:,})")
    print(f"  ceiling@{k}{'':<8}{report['ceiling']:>8.1%}")
    print()
    print(report["results"].to_string(index=False))

    results = report["results"].set_index("strategy")
    pcol, ncol = f"precision@{k}", f"ndcg@{k}"
    print()
    if report["saturated"]:
        print(f"  WARNING: precision@{k} is saturated - the baseline scores "
              f"{results.loc['most_played', pcol]:.0%}.")
        print("  Shorten the horizon (--test-days) or raise k for a usable "
              "comparison; rank the strategies on nDCG meanwhile.")

    base_n = results.loc["most_played", ncol]
    best = results[ncol].idxmax()
    if best == "most_played":
        print(f"  Baseline wins on nDCG@{k} ({base_n:.3f}). Reported as such.")
    else:
        lift = (results.loc[best, ncol] - base_n) / base_n if base_n else float("inf")
        print(f"  Best on nDCG@{k}: {best} at {results.loc[best, ncol]:.3f} "
              f"vs {base_n:.3f} baseline ({lift:+.1%}).")


def _print_rediscovery(report: dict) -> None:
    k = report["k"]
    print(f"Rediscovery  train < {report['split_date']} <= test, "
          f"top-{report['exclude_top']} favourites removed")
    print(f"  candidates        {report['candidates']:>8,} "
          f"(excluded {report['excluded']})")
    print(f"  truth             {report['truth']:>8,} "
          f"(reachable: {report['reachable']:,})")
    print(f"  ceiling@{k}{'':<8}{report['ceiling']:>8.1%}  "
          f"(k={k} picks from {report['reachable']:,} reachable)")
    print()
    print(report["results"].to_string(index=False))

    results = report["results"].set_index("strategy")
    ncol = f"ndcg@{k}"
    base = results.loc["most_played", ncol]
    best = results[ncol].idxmax()
    print()
    if best == "most_played":
        print(f"  Baseline still wins on {ncol} ({base:.3f}). "
              "The model does not rediscover better than play count.")
    else:
        lift = (results.loc[best, ncol] - base) / base if base else float("inf")
        print(f"  Best on {ncol}: {best} at {results.loc[best, ncol]:.3f} "
              f"vs {base:.3f} baseline ({lift:+.1%}).")


def main(argv: list[str] | None = None) -> int:
    from .db import connect

    parser = argparse.ArgumentParser(description="Temporal hold-out evaluation")
    parser.add_argument("--split", default=config.EVAL_SPLIT_DATE)
    parser.add_argument("-k", type=int, default=config.EVAL_K)
    window_group = parser.add_mutually_exclusive_group()
    window_group.add_argument(
        "--test-days", type=int,
        help="bound the test window (relative, days after --split)",
    )
    window_group.add_argument(
        "--test-end",
        help="bound the test window at this absolute, exclusive end date "
             "(YYYY-MM-DD) instead of a relative --test-days offset",
    )
    parser.add_argument(
        "--rediscovery", action="store_true",
        help="score the non-obvious tracks instead of replay",
    )
    parser.add_argument(
        "--exclude-top", type=int, default=50,
        help="favourites removed from the rediscovery candidate pool",
    )
    parser.add_argument(
        "--both", action="store_true", help="print replay and rediscovery side by side"
    )
    parser.add_argument("--half-life", type=float)
    parser.add_argument("--sweep-half-life", action="store_true")
    parser.add_argument("--sweep-splits", action="store_true")
    parser.add_argument(
        "--robustness", action="store_true",
        help="does the score beat the baseline at every split, or just one?",
    )
    parser.add_argument("--metric", default="ndcg", choices=["ndcg", "precision"])
    args = parser.parse_args(argv)

    if args.test_end and (
        args.rediscovery or args.both or args.sweep_splits or args.robustness
    ):
        parser.error(
            "--test-end pins a single absolute window and cannot be applied across "
            "the independent, hardcoded splits that --rediscovery/--both (the "
            "'across splits' table), --sweep-splits, and --robustness each sweep - "
            "every split would get a different, inconsistent window width instead "
            "of the uniform one --test-days gives them. Use --test-days for a "
            "multi-split run, or drop those flags for a single-split one."
        )

    conn = connect()
    try:
        if args.rediscovery or args.both:
            _print_rediscovery(
                evaluate_rediscovery(
                    conn, args.split, 20, args.half_life,
                    exclude_top=args.exclude_top, test_days=args.test_days,
                )
            )
            detail, summary = rediscovery_robustness(
                conn, k=20, half_life=args.half_life,
                exclude_top=args.exclude_top, test_days=args.test_days,
            )
            if not detail.empty:
                print("\n\nRediscovery across splits")
                print(summary.to_string(index=False,
                                        float_format=lambda v: f"{v:.4f}"))
            if args.both:
                print("\n" + "=" * 72 + "\n")

        if not args.rediscovery or args.both:
            _print_report(
                evaluate(conn, args.split, args.k, args.half_life,
                         test_days=args.test_days, test_end=args.test_end)
            )

        if args.sweep_half_life:
            print(f"\n\nHalf-life sweep ({args.metric}@{args.k})")
            print(
                sweep(
                    conn, args.metric, split_date=args.split, k=args.k,
                    test_days=args.test_days, test_end=args.test_end,
                ).to_string(index=False)
            )

        if args.robustness:
            detail, summary = robustness(conn, k=args.k, test_days=args.test_days)
            print(f"\n\nRobustness: nDCG@{args.k} at every usable split")
            print(detail.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
            print("\nPer half-life, across splits:")
            print(summary.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

        if args.sweep_splits:
            print(f"\n\nSplit-date robustness (ndcg@{args.k})")
            print(
                sweep_splits(
                    conn,
                    ["2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01",
                     "2026-06-01", "2026-07-01"],
                    args.k,
                    test_days=args.test_days,
                ).to_string(index=False)
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
