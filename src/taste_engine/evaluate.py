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


def _window_end(split_date: str, test_days: int | None) -> str | None:
    if not test_days:
        return None
    return (datetime.fromisoformat(split_date) + timedelta(days=test_days)).date().isoformat()


def split_frames(
    conn: sqlite3.Connection,
    split_date: str,
    half_life: float | None = None,
    cluster: bool = True,
    test_days: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Training frame scored as of the split, plus test-window play counts.

    `as_of=split_date` is the load-bearing detail: scoring the training window
    from today would leak the length of the test window into the recency term.
    """
    train = scored_tracks(
        conn, start=None, end=split_date, as_of=split_date, half_life=half_life
    )
    test = scored_tracks(
        conn, start=split_date, end=_window_end(split_date, test_days), as_of=None
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
) -> dict:
    split_date = split_date or config.EVAL_SPLIT_DATE
    k = k or config.EVAL_K
    names = strategies or list(STRATEGIES)

    train, test = split_frames(conn, split_date, half_life, test_days=test_days)
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
        "k": k,
        "half_life": half_life or config.RECENCY_HALF_LIFE_DAYS,
        "train_tracks": len(train),
        "train_plays": int(train["play_count"].sum()),
        "test_tracks": len(test_ids),
        "repeatable": len(repeatable),
        "cold_start": len(test_ids - candidates),
        "ceiling": round(ceiling, 4),
        "saturated": bool(baseline >= 1.0),
        "results": results,
    }


def sweep(
    conn: sqlite3.Connection,
    metric: str = "ndcg",
    half_lives: list[float] | None = None,
    split_date: str | None = None,
    k: int | None = None,
    test_days: int | None = None,
) -> pd.DataFrame:
    """Tune the decay against the hold-out, as section 7.1 asks.

    `most_played` is invariant to half-life, so its column doubles as a
    control: if it moves, something is leaking.
    """
    half_lives = half_lives or [7, 14, 30, 60, 90, 180, 365, 10_000]
    k = k or config.EVAL_K
    column = f"{metric}@{k}" if metric in ("ndcg", "precision") else metric
    rows = []
    for half_life in half_lives:
        report = evaluate(conn, split_date, k, half_life, test_days=test_days)
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
    horizon = f"{report['test_days']}d" if report["test_days"] else "to end of data"
    print(f"Temporal hold-out  train < {report['split_date']} <= test ({horizon})")
    print(f"  half-life         {report['half_life']:>8.0f} days")
    print(f"  train tracks      {report['train_tracks']:>8,} "
          f"({report['train_plays']:,} plays)")
    print(f"  test tracks       {report['test_tracks']:>8,}")
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


def main(argv: list[str] | None = None) -> int:
    from .db import connect

    parser = argparse.ArgumentParser(description="Temporal hold-out evaluation")
    parser.add_argument("--split", default=config.EVAL_SPLIT_DATE)
    parser.add_argument("-k", type=int, default=config.EVAL_K)
    parser.add_argument("--test-days", type=int, help="bound the test window")
    parser.add_argument("--half-life", type=float)
    parser.add_argument("--sweep-half-life", action="store_true")
    parser.add_argument("--sweep-splits", action="store_true")
    parser.add_argument(
        "--robustness", action="store_true",
        help="does the score beat the baseline at every split, or just one?",
    )
    parser.add_argument("--metric", default="ndcg", choices=["ndcg", "precision"])
    args = parser.parse_args(argv)

    conn = connect()
    try:
        _print_report(
            evaluate(conn, args.split, args.k, args.half_life, test_days=args.test_days)
        )

        if args.sweep_half_life:
            print(f"\n\nHalf-life sweep ({args.metric}@{args.k})")
            print(
                sweep(
                    conn, args.metric, split_date=args.split, k=args.k,
                    test_days=args.test_days,
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
