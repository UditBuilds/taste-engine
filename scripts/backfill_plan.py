"""Backfill dry-run plan - briefs/backfill_constraint.md, briefs/backfill_rank.md.

FLOOR (`config.MIN_CLUSTER_NATIVE`), LENGTH (`config.MAX_BACKFILL_SHARE`
formula), GUARD (genre match) and RANK (distance to the requesting cluster's
own centroid, ascending) are implemented in `writer.py`/`config.py` and
exercised here exactly as `writer.plan(mode="rediscover")` runs them for
every cluster that clears the floor - this script adds no new selection
logic of its own for the real plan.

The "before" (score-ranked) distinct-backfill-track figures quoted below are
not re-derived by this script: they come from
`scripts/compare_backfill_ranking.py`, which replays the old ranking rule
inline against this same real dataset (a frozen replica - the old ranking
itself is gone, not kept around as a permanent code path in `writer.py`) and
compares it against this script's own `writer.plan()`-based numbers. Run
that script to reproduce the before-figure directly rather than trusting the
constant hardcoded below.

One thing it does add, report-only, never fed back into `writer.plan()`:
alongside each cluster's real (naive) admit count, it also computes what a
STRICT guard would have admitted - the same one `reports/genre_coverage.md`'s
own script (`scripts/genre_coverage.py`) explored, excluding genre labels
that touch more than half of labeled real clusters (e.g. "pop", "hip hop")
because a label that common cannot be what discriminates a cluster's sound
from its neighbours'. Approved by Udit (2026-09-14): report both, implement
neither branch - the shipped guard stays naive.

`reports/genre_coverage.md`'s per-cluster table used the favourites-INCLUDED
pool. `writer.plan(mode="rediscover")` - the writer's default, and the only
mode this script exercises - excludes the top-`config.EXCLUDE_TOP` favourites
*before* computing per-cluster eligibility. This script computes both pools
fresh (not by re-reading genre_coverage.md's numbers) so it can name exactly
which clusters that distinction moves.

No API calls, no --commit: writer.plan() is pure computation over the local
database and cached embeddings. Re-clustering is not cached across calls, so
this makes one `writer.plan()` call per cluster clearing the floor (~1-8s
each depending on whether the embedding model is already warm) - background
this if running it interactively.

Run:  scripts/run.sh scripts/backfill_plan.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from taste_engine import config, writer
from taste_engine.db import connect
from taste_engine.embed import tidy_genres
from taste_engine.recommend import build as build_frame, favourites

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "backfill_plan.md"
NON_DISCRIMINATIVE_SHARE = 0.5  # same bar genre_coverage.md used


def _native_per_cluster(frame: pd.DataFrame) -> pd.Series:
    real = frame[frame["cluster"] >= 0]
    eligible = real[real["score"] >= config.MIN_SCORE]
    return eligible.groupby("cluster").size()


def _label_spread(eligible: pd.DataFrame) -> tuple[dict[str, int], int]:
    """label -> count of distinct clusters where >=1 labeled eligible member
    carries it, and the number of such labeled clusters overall. Same
    definition as reports/genre_coverage.md's `label_cluster_spread`,
    computed here on the rediscover (favourites-excluded) pool instead of
    genre_coverage.md's favourites-included one, since that is the pool
    writer.plan() actually runs the guard against.
    """
    labeled = eligible[eligible["genres"].map(lambda g: len(tidy_genres(g)) > 0)]
    n_labeled_clusters = labeled["cluster"].nunique()
    spread: dict[str, int] = {}
    for _, group in labeled.groupby("cluster"):
        seen: set[str] = set()
        for gl in group["genres"]:
            seen.update(tidy_genres(gl))
        for label in seen:
            spread[label] = spread.get(label, 0) + 1
    return spread, n_labeled_clusters


def _strict_admit(
    eligible: pd.DataFrame, cluster: int, native_count: int, target_length: int,
    non_discriminative: set[str],
) -> tuple[str | None, int]:
    """Shadow-only: what a STRICT guard would admit, capped at the same
    deficit the real (naive) plan used. Never read by writer.plan() - report
    only, per Udit's approved addition (2026-09-14)."""
    deficit = target_length - native_count
    if deficit <= 0:
        return None, 0

    def _strict_genres(g) -> list[str]:
        return [x for x in tidy_genres(g) if x not in non_discriminative]

    native = eligible[eligible["cluster"] == cluster]
    modal, _ = writer._modal_genre(native["genres"].map(_strict_genres))
    if modal is None:
        return None, 0
    outside = eligible[eligible["cluster"] != cluster]
    admit = int(outside["genres"].map(lambda g: modal in _strict_genres(g)).sum())
    return modal, min(admit, deficit)


def _pre_ceiling_candidates(
    rediscover_frame: pd.DataFrame, cluster: int, modal_genre: str
) -> list[tuple[str, str, float]]:
    """Every genre-matching candidate and its distance, ignoring
    MAX_BACKFILL_DISTANCE entirely - a shadow computation in the same spirit
    as `_strict_admit` above, reaching into writer's private helpers
    (`_reduced_embeddings`, `_cluster_centroids`, `_distances_to_centroid`)
    directly rather than through `writer.plan()`, since `plan()` now applies
    the ceiling and so never returns what it excluded. Report-only: never
    fed back into `writer.plan()`. Used to say plainly what the ceiling
    actually dropped, with a real measured distance, not a number carried
    over from a run before the ceiling existed.
    """
    real = rediscover_frame[rediscover_frame["cluster"] >= 0]
    eligible = real[real["score"] >= config.MIN_SCORE]
    outside = eligible[eligible["cluster"] != cluster].copy()
    outside["genres_tidy"] = outside["genres"].map(tidy_genres)
    mask = outside["genres_tidy"].map(lambda gl: modal_genre in gl).astype(bool)
    matching = outside[mask]
    if matching.empty:
        return []
    reduced = writer._reduced_embeddings(real)
    centroid = writer._cluster_centroids(real, reduced)[cluster]
    distances = writer._distances_to_centroid(real, matching["video_id"], centroid, reduced)
    out = [
        (str(r["title"]), str(r["video_id"]), distances[str(r["video_id"])])
        for _, r in matching.iterrows()
    ]
    return sorted(out, key=lambda t: t[2])


def _fmt_genre(g: str | None) -> str:
    return repr(g) if g else "none"


def main() -> int:
    conn = connect()
    try:
        frame = build_frame(conn)
        real_clusters = sorted(int(c) for c in frame.loc[frame["cluster"] >= 0, "cluster"].unique())
        names = {
            cid: str(frame.loc[frame["cluster"] == cid, "cluster_name"].iloc[0])
            for cid in real_clusters
        }

        # ---- the two pools, and which clusters clear the floor under each ----
        native_included = _native_per_cluster(frame)

        obvious = favourites(frame, config.EXCLUDE_TOP)
        rediscover_frame = frame[~frame["video_id"].isin(obvious)]
        native_excluded = _native_per_cluster(rediscover_frame)

        cleared_included = {
            c for c in real_clusters if native_included.get(c, 0) >= config.MIN_CLUSTER_NATIVE
        }
        cleared_excluded = {
            c for c in real_clusters if native_excluded.get(c, 0) >= config.MIN_CLUSTER_NATIVE
        }
        pushed_below = sorted(cleared_included - cleared_excluded)
        # A "0 pushed below" is ambiguous on its own: it could mean exclusion
        # genuinely never crosses the boundary, or that it silently isn't
        # being applied to Pool B at all. Distinguish them: does exclusion
        # measurably move anyone's native count, even without crossing 12?
        moved = {
            c: (native_included.get(c, 0), native_excluded.get(c, 0))
            for c in cleared_included
            if native_included.get(c, 0) != native_excluded.get(c, 0)
        }

        print(f"clusters clearing MIN_CLUSTER_NATIVE={config.MIN_CLUSTER_NATIVE}:")
        print(f"  favourites-included pool   {len(cleared_included)} of {len(real_clusters)}")
        print(f"  favourites-excluded pool   {len(cleared_excluded)} of {len(real_clusters)}"
              "   <- writer.plan()'s real operating pool")
        print(f"  pushed below the floor by exclusion: {len(pushed_below)}")
        for cid in pushed_below:
            print(f"      {names[cid]!r}: included={native_included.get(cid, 0)} "
                  f"excluded={native_excluded.get(cid, 0)}")
        print(f"  exclusion is not a no-op: {len(moved)} of {len(cleared_included)} "
              "clusters clearing the floor under the included pool had their "
              "native count measurably reduced by favourites exclusion, just "
              "not below 12 for any of them" if moved else
              "  WARNING: favourites exclusion changed nobody's native count at "
              "all, including clusters that clear the floor - verify it is "
              "actually being applied before trusting the '0 pushed below' result")
        for cid in sorted(moved):
            print(f"      {names[cid]!r}: included={moved[cid][0]} -> excluded={moved[cid][1]}")
        print()

        # ---- non-discriminative labels, on the real (rediscover) pool ----
        rediscover_real = rediscover_frame[rediscover_frame["cluster"] >= 0]
        rediscover_eligible = rediscover_real[rediscover_real["score"] >= config.MIN_SCORE]
        spread, n_labeled_clusters = _label_spread(rediscover_eligible)
        non_discriminative = {
            label for label, n in spread.items()
            if n_labeled_clusters and n > NON_DISCRIMINATIVE_SHARE * n_labeled_clusters
        }
        print(f"non-discriminative labels (touch >{NON_DISCRIMINATIVE_SHARE:.0%} of "
              f"{n_labeled_clusters} labeled clusters): "
              + (", ".join(sorted(non_discriminative)) or "none"))
        print()

        # ---- per qualifying cluster: the real plan, plus the strict shadow ----
        rows = []
        backfill_provenance: dict[int, list[tuple[str, str, float, str]]] = {}
        mismatches = []
        for cid in sorted(cleared_excluded):
            p = writer.plan(conn, cluster=cid, mode="rediscover")
            if p["native_count"] != native_excluded.get(cid, 0):
                mismatches.append(
                    f"{names[cid]!r}: plan()={p['native_count']} "
                    f"script={native_excluded.get(cid, 0)}"
                )
            strict_modal, strict_admit = _strict_admit(
                rediscover_eligible, cid, p["native_count"], p["target_length"],
                non_discriminative,
            )
            # naive_matched: genre-guard-only admit count, ignoring the
            # ceiling - capped at deficit exactly like _strict_admit caps
            # strict_admit, so the two columns in "Naive vs strict genre
            # guard" below compare guard to guard. naive_admit (below) stays
            # post-ceiling: it's what actually ships, used in the *other*
            # table. The two agree except where the ceiling changed
            # anything (T-Series, this run) - conflating them there would
            # make the naive guard look stricter than the strict guard,
            # which is backwards by construction.
            deficit = p["target_length"] - p["native_count"]
            naive_matched = 0
            if p["modal_genre"] and deficit > 0:
                naive_matched = min(
                    len(_pre_ceiling_candidates(rediscover_frame, cid, p["modal_genre"])),
                    deficit,
                )
            rows.append({
                "cluster": cid, "name": names[cid], "native": p["native_count"],
                "target_length": p["target_length"],
                "naive_modal": p["modal_genre"], "naive_admit": p["backfilled_count"],
                "naive_matched": naive_matched,
                "strict_modal": strict_modal, "strict_admit": strict_admit,
                "final_count": p["count"], "shortfall": p["shortfall"],
                "units": p["units"],
            })
            if p["backfilled_count"]:
                tracks = p["tracks"]
                backfilled = tracks[tracks["cluster"] != cid]
                backfill_provenance[cid] = [
                    (str(r["title"]), p["modal_genre"], float(r["distance"]), str(r["video_id"]))
                    for _, r in backfilled.iterrows()
                ]

        # ---- distance ranking: distinct-track differentiation, briefs/backfill_rank.md ----
        all_backfill_ids = [
            vid for tracks in backfill_provenance.values() for *_, vid in tracks
        ]
        all_distances = [
            d for tracks in backfill_provenance.values() for _, _, d, _ in tracks
        ]
        distinct_after = len(set(all_backfill_ids))
        largest_after = max((len(t) for t in backfill_provenance.values()), default=0)
        # Reproduce with scripts/compare_backfill_ranking.py - not
        # re-derived by this script; see the module docstring.
        DISTINCT_BEFORE = 11
        SLOTS_BEFORE = 52
        LARGEST_BEFORE = 8

        # Searched over every QUALIFYING cluster (cleared_excluded), not just
        # backfill_provenance's keys - MAX_BACKFILL_DISTANCE can legitimately
        # leave T-Series with zero admitted backfill (its one candidate,
        # Doja Cat, sits at distance 1.1166 >= the 1.0 ceiling), and that is
        # a real, reportable outcome, not "not computable".
        t_series_cid = next(
            (cid for cid in cleared_excluded if "t-series" in names[cid].lower()), None
        )
        t_series_distances = sorted(
            d for _, _, d, _ in backfill_provenance.get(t_series_cid, [])
        )
        doja_cat = next(
            ((title, d) for title, _, d, _ in backfill_provenance.get(t_series_cid, [])
             if "doja cat" in title.lower()),
            None,
        )

        # Is Doja Cat's distance the single worst admitted anywhere, and by
        # how much - the fact the distance-ceiling decision actually turned
        # on. Computed from backfill_provenance, not eyeballed off the table
        # below. With MAX_BACKFILL_DISTANCE=1.0 now enforced (Doja Cat's
        # 1.1166 >= 1.0), Doja Cat itself no longer appears in
        # backfill_provenance at all - this is measured separately, straight
        # off T-Series's own genre-guard admit count and eligible pool,
        # rather than found in the (now ceiling-filtered) provenance data.
        t_series_row = next((r for r in rows if r["cluster"] == t_series_cid), None)
        # naive_admit==0 alone is ambiguous - it's also what a genuine
        # genre-guard miss looks like (0 candidates ever matched, ceiling
        # irrelevant). Disambiguate by actually recomputing the pre-ceiling
        # candidate pool: only a NON-empty pre-ceiling pool with a post-
        # ceiling admit of 0 means the ceiling is what did the excluding.
        t_series_pre_ceiling = (
            _pre_ceiling_candidates(rediscover_frame, t_series_cid, t_series_row["naive_modal"])
            if t_series_row and t_series_row["naive_modal"] else []
        )
        ceiling_excluded_t_series_only_match = bool(
            t_series_row and t_series_row["naive_admit"] == 0 and t_series_pre_ceiling
        )

        all_with_context = [
            (title, cname, d, cid)
            for cid, tracks in backfill_provenance.items()
            for title, _genre, d, _vid in tracks
            for cname in [names[cid]]
        ]
        ceiling_note = None
        if doja_cat is not None and all_with_context:
            ranked_desc = sorted(all_with_context, key=lambda t: t[2], reverse=True)
            worst = ranked_desc[0]
            is_worst = worst[2] == doja_cat[1]
            second = ranked_desc[1] if len(ranked_desc) > 1 else None
            ceiling_note = {
                "is_global_max": is_worst,
                "second_title": second[0] if second else None,
                "second_cluster": second[1] if second else None,
                "second_distance": second[2] if second else None,
                "n_t_series_candidates": len(t_series_distances),
            }

        def _median(xs: list[float]) -> float | None:
            if not xs:
                return None
            s = sorted(xs)
            mid = len(s) // 2
            return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

        print(f"distinct backfill tracks: before(score-ranked)={DISTINCT_BEFORE} of "
              f"{SLOTS_BEFORE} slots, largest single={LARGEST_BEFORE}  ->  "
              f"after(distance-ranked)={distinct_after} of {len(all_backfill_ids)} "
              f"slots, largest single={largest_after}")
        if all_distances:
            print(f"distance distribution (all admitted backfill, n={len(all_distances)}): "
                  f"min={min(all_distances):.4f} median={_median(all_distances):.4f} "
                  f"max={max(all_distances):.4f}")
        if t_series_cid is not None:
            print(f"T-Series distances ({len(t_series_distances)} admitted): "
                  + ", ".join(f"{d:.4f}" for d in t_series_distances))
            print(f"T-Series admits Doja Cat: {'yes' if doja_cat else 'no'}"
                  + (f", distance={doja_cat[1]:.4f}" if doja_cat else ""))
            if ceiling_note and ceiling_note["is_global_max"]:
                print(f"  Doja Cat's distance is the MAXIMUM of all "
                      f"{len(all_distances)} admitted distances this run. Next-"
                      f"highest: {ceiling_note['second_distance']:.4f} "
                      f"({ceiling_note['second_title']!r}, {ceiling_note['second_cluster']}). "
                      f"T-Series has exactly {ceiling_note['n_t_series_candidates']} "
                      "genre-matching candidate(s) in the whole eligible pool, so "
                      "there is nothing else for it to rank against.")
            elif ceiling_excluded_t_series_only_match:
                excluded_desc = "; ".join(
                    f"{title!r} at {d:.4f}" for title, _vid, d in t_series_pre_ceiling
                )
                print(f"  MAX_BACKFILL_DISTANCE={config.MAX_BACKFILL_DISTANCE} excluded "
                      f"every genre-matching candidate T-Series had ({excluded_desc or 'none found'}): "
                      f"0 backfilled instead of {len(t_series_pre_ceiling)}, final "
                      f"playlist {t_series_row['final_count']} tracks instead of "
                      f"{t_series_row['final_count'] + len(t_series_pre_ceiling)}.")
        else:
            print("T-Series: not computable - no cluster in this run's qualifying "
                  "pool (cleared_excluded) matched 't-series'")
        print()

        if mismatches:
            print("WARNING - native count mismatch between this script and "
                  "writer.plan() (investigate before trusting the table below):")
            for m in mismatches:
                print(f"  {m}")
            print()

        skipped = sorted(set(real_clusters) - cleared_excluded)

        # ---- quota ----
        total_units = sum(r["units"] for r in rows)
        exceeds_cap = total_units > config.QUOTA_DAILY_CAP
        affordable = 0
        running = 0
        for r in sorted(rows, key=lambda r: r["units"]):
            if running + r["units"] > config.QUOTA_DAILY_CAP:
                break
            running += r["units"]
            affordable += 1

        print(f"qualifying clusters: {len(rows)}   skipped (below floor): {len(skipped)}")
        print(f"total quota to write every qualifying cluster today: "
              f"{total_units:,} units (cap {config.QUOTA_DAILY_CAP:,})")
        print(f"exceeds the daily cap: {'yes' if exceeds_cap else 'no'}")
        print(f"could write {affordable} of {len(rows)} today, cheapest-first, "
              f"without exceeding the cap")

        # ---- assemble the report ----
        lines = []
        lines.append("# Backfill Plan - Floor, Length, Genre Guard, Distance Rank\n")
        lines.append("Briefs: `briefs/backfill_constraint.md` (floor, length, guard), "
                      "`briefs/backfill_rank.md` (distance ranking within the "
                      "guarded pool). Dry-run only, no API calls, no `--commit`. "
                      "Script: `scripts/backfill_plan.py`. Rules implemented in "
                      "`writer.py`/`config.py` "
                      f"(`MIN_CLUSTER_NATIVE={config.MIN_CLUSTER_NATIVE}`, "
                      f"`MAX_BACKFILL_SHARE={config.MAX_BACKFILL_SHARE}`).\n")

        lines.append("## Which pool clears the floor\n")
        lines.append(
            "`writer.plan(mode=\"rediscover\")` - the writer's default, and the "
            f"only mode this report exercises - excludes the top-"
            f"{config.EXCLUDE_TOP} favourites *before* computing per-cluster "
            "eligibility. `reports/genre_coverage.md`'s per-cluster table used "
            "the favourites-included pool, so it does not say how many clusters "
            "clear the floor under the pool `writer.plan()` actually runs "
            "against. Both are computed fresh here, not read from that report.\n"
        )
        lines.append(f"- Favourites-included pool: **{len(cleared_included)} of "
                      f"{len(real_clusters)}** real clusters clear "
                      f"`MIN_CLUSTER_NATIVE={config.MIN_CLUSTER_NATIVE}`.\n")
        lines.append(f"- Favourites-excluded (rediscover) pool - the real operating "
                      f"pool: **{len(cleared_excluded)} of {len(real_clusters)}** clear it.\n")
        lines.append(f"- Pushed below the floor by favourites exclusion (cleared "
                      f"under favourites-included, do not clear under "
                      f"favourites-excluded): **{len(pushed_below)}**"
                      + ("\n" if pushed_below else " - none.\n"))
        if pushed_below:
            lines.append("\n| cluster | favourites-included native | "
                          "favourites-excluded native |")
            lines.append("|---|---|---|")
            for cid in pushed_below:
                lines.append(f"| {names[cid]} | {native_included.get(cid, 0)} | "
                              f"{native_excluded.get(cid, 0)} |")
        lines.append(
            f"\nA count of 0 is ambiguous on its own - it could mean exclusion "
            f"never crosses the boundary, or that exclusion silently is not "
            f"being applied to the favourites-excluded pool at all. It is the "
            f"former: exclusion measurably reduces the native count of "
            f"**{len(moved)} of {len(cleared_included)}** clusters that clear "
            f"the floor under the favourites-included pool - it simply does "
            f"not cross {config.MIN_CLUSTER_NATIVE} for any of them.\n"
            if moved else
            "\n**WARNING: favourites exclusion changed nobody's native count "
            "at all** - verify it is actually being applied before trusting "
            "the '0 pushed below' result above.\n"
        )
        if moved:
            lines.append("\n| cluster | favourites-included native | "
                          "favourites-excluded native |")
            lines.append("|---|---|---|")
            for cid in sorted(moved):
                lines.append(f"| {names[cid]} | {moved[cid][0]} | {moved[cid][1]} |")
        lines.append("\nAll numbers below use the favourites-excluded (rediscover) "
                      "pool.\n")

        lines.append("\n## Naive vs strict genre guard (report only)\n")
        lines.append(
            "The shipped GUARD is naive: a backfill candidate matches if it "
            "carries the cluster's modal genre at all. Approved as an "
            "additional report-only comparison (2026-09-14): what a STRICT "
            "guard would have admitted instead, excluding labels that touch "
            f"more than {NON_DISCRIMINATIVE_SHARE:.0%} of labeled real clusters "
            "in this pool - the same sensitivity check `scripts/genre_coverage.py` "
            "ran, since a label that common cannot be what discriminates a "
            "cluster's sound from its neighbours'. **Neither the length nor the "
            "shipped selection reads this column; it never feeds back into "
            "`writer.plan()`.** Both columns below are guard-only (genre "
            "match, capped at deficit) with **no distance ceiling applied to "
            "either** - naive vs strict is a guard-to-guard comparison, so "
            "conflating one side with the post-ceiling shipped count would "
            "make the naive guard look stricter than it is by construction "
            "(it never can be - naive matches a superset of what strict "
            "matches). Where the ceiling actually cuts a cluster's backfill "
            "is reported below, in Distance ranking, and in the *next* "
            "table's `backfilled` column, which does reflect it.\n"
        )
        lines.append(f"Non-discriminative labels found (touch >"
                      f"{NON_DISCRIMINATIVE_SHARE:.0%} of {n_labeled_clusters} "
                      "labeled clusters): " + (", ".join(sorted(non_discriminative)) or "none") + "\n")
        lines.append("\n| cluster | native | naive modal | naive admit "
                      "(guard only) | strict modal | strict admit |")
        lines.append("|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['name']} | {r['native']} | {_fmt_genre(r['naive_modal'])} | "
                f"{r['naive_matched']} | {_fmt_genre(r['strict_modal'])} | "
                f"{r['strict_admit']} |"
            )

        lines.append("\n## Per-cluster dry-run plan (naive guard - what ships)\n")
        lines.append(
            "`backfilled` here is the actual shipped count: guard **and** "
            "the `MAX_BACKFILL_DISTANCE` ceiling both applied, exactly what "
            "`writer.plan()` returns. It can be lower than the guard-only "
            "`naive admit` column in the table above - see Distance ranking "
            "below for which clusters (if any) that ceiling affected.\n"
        )
        lines.append("| cluster | native | backfilled | final length | target | "
                      "modal genre | short by | quota units |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['name']} | {r['native']} | {r['naive_admit']} | "
                f"{r['final_count']} | {r['target_length']} | "
                f"{_fmt_genre(r['naive_modal'])} | {r['shortfall'] or '-'} | "
                f"{r['units']:,} |"
            )

        lines.append("\n## Distance ranking (briefs/backfill_rank.md)\n")
        lines.append(
            "The genre GUARD above is unchanged - it still only filters the "
            "candidate pool. What changed is how that filtered pool is "
            "ranked: by cosine distance (in the PCA-reduced embedding space "
            "HDBSCAN clustered in) to the *requesting* cluster's own "
            "centroid, ascending, tie-broken (distance asc, score desc, "
            "video_id asc) - not by global score, which was identical for "
            "every cluster and is what made backfill collapse onto the same "
            "handful of tracks. `_clusters_by_distance` (nearest whole "
            "cluster) is not restored.\n"
        )
        lines.append(
            f"- Distinct backfill tracks: **before** (score-ranked) "
            f"**{DISTINCT_BEFORE}** distinct filling {SLOTS_BEFORE} slots "
            f"across {len(rows)} playlists, largest single playlist "
            f"{LARGEST_BEFORE} - **after** (distance-ranked) "
            f"**{distinct_after}** distinct filling {len(all_backfill_ids)} "
            f"slots, largest single playlist {largest_after}. (The brief's "
            "own recollection was \"10 distinct ... 52 slots\"; the "
            f"before-figure measured here is {DISTINCT_BEFORE}, not 10 - "
            "reproduce it with `scripts/compare_backfill_ranking.py`.)\n"
        )
        if all_distances:
            lines.append(
                f"- Distance distribution across all {len(all_distances)} "
                f"admitted backfill tracks: min **{min(all_distances):.4f}**, "
                f"median **{_median(all_distances):.4f}**, max "
                f"**{max(all_distances):.4f}**.\n"
            )
        else:
            lines.append("- Distance distribution: not computable - no cluster "
                          "backfilled anything this run.\n")
        if t_series_cid is not None:
            if t_series_distances:
                lines.append(
                    f"- T-Series distance distribution ({len(t_series_distances)} "
                    f"admitted): min **{min(t_series_distances):.4f}**, median "
                    f"**{_median(t_series_distances):.4f}**, max "
                    f"**{max(t_series_distances):.4f}**. Every admitted distance, "
                    "ascending: " + ", ".join(f"{d:.4f}" for d in t_series_distances) + "\n"
                )
            else:
                lines.append(
                    "- T-Series distance distribution: not computable - T-Series "
                    "admitted 0 backfill tracks this run "
                    + (f"(MAX_BACKFILL_DISTANCE={config.MAX_BACKFILL_DISTANCE} "
                       "excluded its only genre-matching candidate - see below)"
                       if ceiling_excluded_t_series_only_match else "") + ".\n"
                )
            lines.append(
                f"- T-Series still admits Doja Cat: **{'yes' if doja_cat else 'no'}**"
                + (f", at distance **{doja_cat[1]:.4f}**." if doja_cat else ".") + "\n"
            )
            if ceiling_note and ceiling_note["is_global_max"]:
                lines.append(
                    f"- That distance is the **maximum of all {len(all_distances)} "
                    "admitted backfill distances this run** - not just high for "
                    f"T-Series. The next-highest anywhere is "
                    f"**{ceiling_note['second_distance']:.4f}** "
                    f"({ceiling_note['second_title']!r}, admitted into "
                    f"{ceiling_note['second_cluster']}'s playlist). T-Series has "
                    f"exactly **{ceiling_note['n_t_series_candidates']}** "
                    "genre-matching candidate in the whole eligible pool, so "
                    "distance ranking has nothing to choose between - the guard "
                    "admits it regardless of how far it is, because there is no "
                    "alternative to rank it against. A distance ceiling set "
                    f"anywhere in ({ceiling_note['second_distance']:.4f}, "
                    f"{doja_cat[1]:.4f}] would remove this one track and only "
                    "this one track across the entire run, turning T-Series's "
                    "playlist one track shorter; a ceiling at or below "
                    f"{ceiling_note['second_distance']:.4f} would start "
                    "cutting into other clusters' backfill too. Whether to add "
                    "one is Udit's call, per the brief.\n"
                )
            elif ceiling_excluded_t_series_only_match:
                excluded_desc = "; ".join(
                    f"**{title}** at distance **{d:.4f}**"
                    for title, _vid, d in t_series_pre_ceiling
                )
                lines.append(
                    f"- **MAX_BACKFILL_DISTANCE={config.MAX_BACKFILL_DISTANCE} now "
                    "excludes every genre-matching candidate T-Series had** "
                    f"(recomputed directly, ignoring the ceiling, for this "
                    f"report: {excluded_desc or 'none found'}). T-Series's "
                    f"final playlist is **{t_series_row['final_count']} tracks** "
                    f"this run, {len(t_series_pre_ceiling)} fewer than the "
                    f"{t_series_row['final_count'] + len(t_series_pre_ceiling)} it "
                    "would have reached without the ceiling. This is the ceiling "
                    "doing exactly what it was added to do: T-Series had exactly "
                    "one genre-matching candidate anywhere in its eligible pool, "
                    "so distance ranking had nothing to choose between, and the "
                    "guard would have admitted it regardless of how far it sat - "
                    "the ceiling is the only thing that can refuse it.\n"
                )
        else:
            lines.append("- T-Series: not computable - no cluster in this run's "
                          "qualifying pool matched 't-series'.\n")

        lines.append("\n### Backfill provenance (native cluster -> admitting genre, distance)\n")
        if backfill_provenance:
            for cid, tracks in backfill_provenance.items():
                lines.append(f"\n**{names[cid]}**\n")
                for title, genre, distance, _vid in sorted(tracks, key=lambda t: t[2]):
                    lines.append(
                        f"- {title[:70]}  -  admitted by genre `{genre}`, "
                        f"distance {distance:.4f}"
                    )
        else:
            lines.append("\nNo qualifying cluster backfilled anything.\n")

        lines.append("\n## Skipped: below the floor\n")
        lines.append(f"{len(skipped)} of {len(real_clusters)} real clusters have "
                      f"fewer than {config.MIN_CLUSTER_NATIVE} eligible native "
                      "tracks in the favourites-excluded pool and generate no "
                      "playlist at all.\n")
        if skipped:
            lines.append("\n| cluster | native (favourites-excluded) |")
            lines.append("|---|---|")
            for cid in skipped:
                lines.append(f"| {names[cid]} | {native_excluded.get(cid, 0)} |")

        lines.append("\n## Quota\n")
        lines.append(f"- Qualifying clusters: **{len(rows)}** of {len(real_clusters)}.\n")
        lines.append(f"- Total quota to write every qualifying cluster's playlist "
                      f"today: **{total_units:,} units** (breakdown per cluster in "
                      "the table above; each is `50 + 50*count + 1`).\n")
        lines.append(f"- Daily cap: {config.QUOTA_DAILY_CAP:,} units. "
                      f"**Exceeds the cap: {'yes' if exceeds_cap else 'no'}.**\n")
        lines.append(f"- Cheapest-first, {affordable} of {len(rows)} of these "
                      "playlists could actually be written today without "
                      "breaching the cap; the rest would need another day (or "
                      "several - see CLAUDE.md's cost model: this can write "
                      "roughly one such playlist a day).\n")
        if mismatches:
            lines.append("\n**WARNING - native-count mismatch between this "
                          "script's own pool computation and `writer.plan()` for "
                          "at least one cluster (investigate before trusting the "
                          "tables above):**\n")
            for m in mismatches:
                lines.append(f"- {m}\n")

        report_text = "\n".join(lines)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report_text)
        print(f"\nFull report written to {REPORT_PATH}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
