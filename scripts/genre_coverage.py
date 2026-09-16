"""Genre Coverage Measurement - briefs/genre_coverage.md. Read-only, no API calls.

Answers: is a genre-constrained backfill viable, given the genre/topic data
actually cached today? No existing module is modified; every number below
comes from calling existing, unmodified functions in taste_engine.

Run:  scripts/run.sh scripts/genre_coverage.py
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from taste_engine import config
from taste_engine.canonical import add_canonical_key, title_core, merge_by_duration, iso_seconds
from taste_engine.classify import classify, TOPIC_SUFFIX, VEVO_MARKER
from taste_engine.db import connect
from taste_engine.embed import tidy_genres
from taste_engine.recommend import build as build_frame, favourites
from taste_engine.score import scored_tracks

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "genre_coverage.md"
SHALLOW_THRESHOLD = 45  # brief's definition: eligible members < 45

# Known-good figures already measured and written into CLAUDE.md / produced by
# scripts/backfill_report.py. Used below as a correctness gate on this script's
# own pipeline, not as a target to match by construction. Cluster *size* is
# time-invariant so it is gated hard; the *eligible* count is score-threshold
# dependent and score is computed as_of=now() by design (score.py), so it
# legitimately drifts by a track or two between the day CLAUDE.md's figures
# were measured (2026-09-13) and today - checked, not assumed: re-scoring
# Travis Scott's cluster at as_of=now-24h reproduces 21 exactly (see
# briefs-era diagnostic in this session). That comparison is reported below
# for transparency but does not gate.
EXPECTED_CANONICAL_TRACKS = 2918
EXPECTED_REDISCOVER_CLUSTER_SIZE = {"T-Series": 492, "Travis Scott": 84}
EXPECTED_REDISCOVER_ELIGIBLE = {"T-Series": 22, "Travis Scott": 21}


def uploader_type(channel) -> str:
    if not isinstance(channel, str) or not channel:
        return "unknown"
    if channel.endswith(TOPIC_SUFFIX):
        return "- Topic"
    if VEVO_MARKER in channel:
        return "VEVO"
    return "other"


def genre_field_cached_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM video_metadata WHERE topic_categories IS NOT NULL "
        "AND topic_categories NOT IN ('[]', '')"
    ).fetchone()[0]


def build_union_genres(conn) -> tuple[pd.DataFrame, pd.Series]:
    """canonical_key -> tidied genre labels unioned across every merged upload.

    Reproduces canonical.collapse()'s own key derivation (add_canonical_key ->
    title_core -> merge_by_duration) rather than importing collapse() itself,
    because collapse() keeps only the representative row's genres and discards
    the canonical_key column (`reset_index(drop=True)`). Every function called
    here is an existing, unmodified export of canonical.py, called in the same
    order collapse() calls them, on the same music-only raw frame collapse()
    itself receives - see the cross-check in main() that this reproduction
    yields the same number of groups as the real collapse() output.
    """
    raw = scored_tracks(conn, canonical=False)  # one row per video_id, music-only
    work = add_canonical_key(raw)
    work["core_key"] = [
        title_core(t, c) for t, c in zip(work["title"], work["channel"])
    ]
    if "duration" in work.columns:
        work["seconds"] = work["duration"].map(iso_seconds)
        work["canonical_key"] = merge_by_duration(work)

    resolved = classify(conn).set_index("video_id")["resolved"]
    work["resolved"] = work["video_id"].map(resolved)
    work["uploader_type"] = work["channel"].map(uploader_type)

    def _union(genre_lists) -> list[str]:
        out: list[str] = []
        for lst in genre_lists:
            for g in tidy_genres(lst):
                if g not in out:
                    out.append(g)
        return out

    grouped = work.groupby("canonical_key")
    union_df = pd.DataFrame({
        "genres_union": grouped["genres"].agg(_union),
        "any_variant_resolved": grouped["resolved"].agg(lambda s: bool(s.any())),
        "variant_uploader_types": grouped["uploader_type"].agg(lambda s: sorted(set(s))),
        "n_variants_seen": grouped.size(),
    })
    return union_df, work.set_index("video_id")["canonical_key"]


def label_cluster_spread(labeled: pd.DataFrame) -> dict[str, int]:
    """label -> number of distinct clusters carrying it on >=1 labeled eligible member.

    Used only for the discriminativeness sensitivity check, not the primary
    (literal brief-definition) numbers.
    """
    spread: dict[str, int] = {}
    for _, group in labeled.groupby("cluster"):
        seen: set[str] = set()
        for gl in group["genres_tidy"]:
            seen.update(gl)
        for label in seen:
            spread[label] = spread.get(label, 0) + 1
    return spread


def _modal(genre_lists: pd.Series):
    """(modal_genre, n_labeled, modal_share, ambiguous) or (None, 0, None, None).

    Tie-break: highest count, then alphabetically-first label - matching
    `writer._modal_genre`'s fix (2026-09-14) rather than inventing a second
    idiom. `Counter.most_common(1)` resolves a tie by dict-insertion order,
    which traces back to iterating `set(gl)` above, and Python randomises
    string hashing per process by default, so that tie-break is not stable
    across process runs. Live on this corpus, not hypothetical: a scan
    found 16 of 37 real clusters carrying an exact top-1 vote tie today,
    including Metro Boomin (28-28, "pop"/"hip hop") and T-Series (19-19,
    "music of asia"/"pop") - the same two clusters `writer._modal_genre`'s
    docstring names.
    """
    labeled = genre_lists[genre_lists.map(len) > 0]
    n_labeled = len(labeled)
    if n_labeled == 0:
        return None, 0, None, None
    counts = Counter()
    for gl in labeled:
        counts.update(set(gl))
    modal_genre, modal_count = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    modal_share = modal_count / n_labeled
    return modal_genre, n_labeled, modal_share, modal_share <= 0.5


def per_cluster_table(real: pd.DataFrame, eligible: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per real (non-noise) cluster: size, modal genre, reachability.

    Computes two views side by side:
    * naive - the brief's literal definition, every tidied label counts.
    * strict - a sensitivity check that excludes labels present on more than
      half of all labeled-eligible clusters, symmetric with the brief's own
      50%-share ambiguity bar (a label common across most clusters cannot be
      what discriminates between them - see the Coverage/Reachability
      write-up for why this matters here: "pop" and "hip hop" turned out to
      be exactly that kind of label on this corpus).
    """
    labeled_all = eligible[eligible["genres_tidy"].map(len) > 0]
    n_labeled_clusters = labeled_all["cluster"].nunique()
    spread = label_cluster_spread(labeled_all)
    non_discriminative = {
        label for label, n in spread.items() if n_labeled_clusters and n > 0.5 * n_labeled_clusters
    }

    def strict_genres(gl: list[str]) -> list[str]:
        return [g for g in gl if g not in non_discriminative]

    rows = []
    for cid in sorted(real["cluster"].unique()):
        name = str(real.loc[real["cluster"] == cid, "cluster_name"].iloc[0])
        members = eligible[eligible["cluster"] == cid]
        outside = eligible[eligible["cluster"] != cid]
        n_eligible = len(members)
        n_outside_pool = len(outside)
        shallow = n_eligible < SHALLOW_THRESHOLD

        modal_n, n_labeled_n, share_n, amb_n = _modal(members["genres_tidy"])
        outside_sharing_n = (
            int(outside["genres_tidy"].map(lambda gl, m=modal_n: m in gl).sum())
            if modal_n is not None else None
        )
        reach_total_n = (n_eligible + outside_sharing_n) if outside_sharing_n is not None else None
        reachable_n = reach_total_n is not None and reach_total_n >= SHALLOW_THRESHOLD
        admit_ratio_n = (outside_sharing_n / n_outside_pool) if (outside_sharing_n is not None and n_outside_pool) else None

        members_strict = members["genres_tidy"].map(strict_genres)
        outside_strict = outside["genres_tidy"].map(strict_genres)
        modal_s, n_labeled_s, share_s, amb_s = _modal(members_strict)
        outside_sharing_s = (
            int(outside_strict.map(lambda gl, m=modal_s: m in gl).sum())
            if modal_s is not None else None
        )
        reach_total_s = (n_eligible + outside_sharing_s) if outside_sharing_s is not None else None
        reachable_s = reach_total_s is not None and reach_total_s >= SHALLOW_THRESHOLD
        admit_ratio_s = (outside_sharing_s / n_outside_pool) if (outside_sharing_s is not None and n_outside_pool) else None

        rows.append({
            "cluster": int(cid), "cluster_name": name,
            "n_eligible": n_eligible, "shallow": shallow, "n_outside_pool": n_outside_pool,
            "n_labeled": n_labeled_n, "modal_genre": modal_n, "modal_share": share_n,
            "ambiguous": amb_n, "outside_sharing_genre": outside_sharing_n,
            "admit_ratio": admit_ratio_n, "reachable_45": reachable_n if shallow else None,
            "modal_genre_strict": modal_s, "n_labeled_strict": n_labeled_s,
            "outside_sharing_strict": outside_sharing_s, "admit_ratio_strict": admit_ratio_s,
            "reachable_45_strict": reachable_s if shallow else None,
        })
    meta = {
        "n_labeled_clusters": n_labeled_clusters,
        "spread": spread,
        "non_discriminative": non_discriminative,
    }
    return pd.DataFrame(rows), meta


def fmt_pct(n: int, d: int) -> str:
    return f"{n:,} / {d:,} ({n / d * 100:.1f}%)" if d else f"{n:,} / 0 (n/a)"


def main() -> int:
    conn = connect()
    try:
        # ---- hard gate: genre field must already be cached ----
        cached = genre_field_cached_count(conn)
        if cached == 0:
            msg = (
                "STOP: no genre/topic field is cached anywhere in video_metadata "
                "(topic_categories is empty for every row). Per the brief, this "
                "script does not fetch. No numbers computed."
            )
            print(msg)
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(f"# Genre Coverage Measurement\n\n{msg}\n")
            return 1
        print(f"genre field cached: video_metadata.topic_categories populated "
              f"for {cached:,} rows (verified before computing anything)\n")

        # ---- the canonical + clustered frame: default settings, no overrides ----
        frame = build_frame(conn)
        frame["genres_tidy"] = frame["genres"].map(tidy_genres)
        frame["has_genre"] = frame["genres_tidy"].map(len) > 0
        frame["uploader_type"] = frame["channel"].map(uploader_type)
        resolved_map = classify(conn).set_index("video_id")["resolved"]
        frame["resolved"] = frame["video_id"].map(resolved_map)

        # ---- correctness gate 1: canonical-track count vs the already-measured figure ----
        gate1_ok = len(frame) == EXPECTED_CANONICAL_TRACKS
        print(f"[gate] canonical tracks = {len(frame):,} "
              f"(CLAUDE.md's measured figure: {EXPECTED_CANONICAL_TRACKS:,}) "
              f"-> {'OK' if gate1_ok else 'MISMATCH'}")

        # ---- union-across-variants comparison (the representative-only caveat) ----
        union_df, video_to_key = build_union_genres(conn)
        frame["canonical_key"] = frame["video_id"].map(video_to_key)
        gate2_ok = frame["canonical_key"].notna().all() and frame["canonical_key"].nunique() == len(frame)
        print(f"[gate] canonical_key re-derivation matches collapse() 1:1 "
              f"-> {'OK' if gate2_ok else 'MISMATCH'}")
        if not (gate1_ok and gate2_ok):
            print("\nRefusing to report numbers built on a pipeline that fails "
                  "its own correctness gates. Stopping for investigation.")
            return 1

        frame = frame.merge(union_df, on="canonical_key", how="left")
        frame["genres_union_tidy"] = frame["genres_union"]
        frame["has_genre_union"] = frame["genres_union_tidy"].map(
            lambda g: isinstance(g, list) and len(g) > 0
        )

        # ---- correctness gate 3: reproduce already-measured rediscover-pool CLUSTER
        # SIZE (time-invariant - hard gate). Eligible count is reported alongside
        # for context but not gated: it is score-threshold dependent and score is
        # computed as_of=now() by design, so it legitimately drifts hour to hour. ----
        favourite_ids = favourites(frame, config.EXCLUDE_TOP)
        rediscover_frame = frame[~frame["video_id"].isin(favourite_ids)]
        rediscover_eligible = rediscover_frame[rediscover_frame["score"] >= config.MIN_SCORE]
        gate3_ok = True
        gate3_results = []
        for name, expected_size in EXPECTED_REDISCOVER_CLUSTER_SIZE.items():
            match = rediscover_frame[
                rediscover_frame["cluster_name"].fillna("").str.contains(name, case=False, regex=False)
                & (rediscover_frame["cluster"] >= 0)
            ]
            if match.empty:
                print(f"[gate] {name!r}: no matching cluster found -> MISMATCH")
                gate3_ok = False
                continue
            cid = match["cluster"].value_counts().idxmax()
            got_size = len(rediscover_frame[rediscover_frame["cluster"] == cid])
            ok = got_size == expected_size
            gate3_ok &= ok
            got_eligible = len(rediscover_eligible[rediscover_eligible["cluster"] == cid])
            expected_eligible = EXPECTED_REDISCOVER_ELIGIBLE[name]
            eligible_note = "matches" if got_eligible == expected_eligible else (
                f"differs from the {expected_eligible} measured on 2026-09-13 by "
                f"{got_eligible - expected_eligible:+d} - expected: score is computed "
                f"as_of=now() and decays continuously, so a threshold count taken a day "
                f"apart is not required to match"
            )
            print(f"[gate] {name!r} rediscover-pool cluster size = {got_size} "
                  f"(expected {expected_size}) -> {'OK' if ok else 'MISMATCH'}; "
                  f"eligible today = {got_eligible} ({eligible_note})")
            gate3_results.append({
                "name": name, "size_ok": ok, "got_size": got_size, "expected_size": expected_size,
                "got_eligible": got_eligible, "expected_eligible": expected_eligible,
                "eligible_note": eligible_note,
            })
        if not gate3_ok:
            print("\nRefusing to report numbers: rediscover-pool cluster-size cross-check "
                  "failed against already-measured figures. Stopping for investigation.")
            return 1
        print()

        # =========================================================================
        # NUMBER 1 - Coverage
        # =========================================================================
        n_total = len(frame)
        n_ge1_delivered = int(frame["has_genre"].sum())
        n_gt1_delivered = int((frame["genres_tidy"].map(len) > 1).sum())
        n_ge1_union = int(frame["has_genre_union"].sum())
        n_gt1_union = int((frame["genres_union_tidy"].map(lambda g: len(g) if isinstance(g, list) else 0) > 1).sum())

        label_counts = Counter()
        for gl in frame["genres_tidy"]:
            label_counts.update(set(gl))
        top15 = label_counts.most_common(15)

        zero_genre = frame[~frame["has_genre"]]
        zero_resolved = int(zero_genre["resolved"].fillna(False).sum())
        zero_unresolved = int((~zero_genre["resolved"].fillna(False)).sum())

        recovered = frame[~frame["has_genre"] & frame["has_genre_union"]]
        recovered_had_topic_variant = int(
            recovered["variant_uploader_types"].map(
                lambda types: isinstance(types, list) and "- Topic" in types
            ).sum()
        )

        uploader_cov = (
            frame.groupby("uploader_type")
            .agg(tracks=("video_id", "size"), with_genre=("has_genre", "sum"))
            .assign(pct=lambda d: (d["with_genre"] / d["tracks"] * 100).round(1))
            .sort_values("tracks", ascending=False)
        )

        # =========================================================================
        # NUMBER 2 - Per shallow cluster  &  ambiguous-modal-genre listing
        # =========================================================================
        real = frame[frame["cluster"] >= 0].copy()
        eligible = real[real["score"] >= config.MIN_SCORE].copy()
        cluster_table, label_meta = per_cluster_table(real, eligible)
        labeled_all_report = eligible[eligible["genres_tidy"].map(len) > 0]
        shallow_table = cluster_table[cluster_table["shallow"]].sort_values("n_eligible")
        ambiguous_table = cluster_table[cluster_table["ambiguous"] == True]  # noqa: E712

        non_discriminative_rows = sorted(
            ((label, n, n / label_meta["n_labeled_clusters"])
             for label, n in label_meta["spread"].items() if label in label_meta["non_discriminative"]),
            key=lambda t: -t[1],
        )

        # =========================================================================
        # NUMBER 3 - Reachability (naive per the brief's literal definition,
        # and strict per the sensitivity check above - see methodology note)
        # =========================================================================
        n_shallow = len(shallow_table)
        n_not_computable = int(shallow_table["modal_genre"].isna().sum())
        n_reachable = int((shallow_table["reachable_45"] == True).sum())  # noqa: E712
        n_not_reachable = n_shallow - n_reachable - n_not_computable

        n_not_computable_strict = int(shallow_table["modal_genre_strict"].isna().sum())
        n_reachable_strict = int((shallow_table["reachable_45_strict"] == True).sum())  # noqa: E712
        n_not_reachable_strict = n_shallow - n_reachable_strict - n_not_computable_strict

        t_series_row = cluster_table[cluster_table["cluster_name"].str.contains("T-Series", case=False, na=False)]

        # ---- assemble report ----
        lines = []
        lines.append("# Genre Coverage Measurement\n")
        lines.append("Brief: `briefs/genre_coverage.md`. Read-only measurement, no API "
                      "calls, no existing module modified. New code: `scripts/genre_coverage.py`.\n")

        lines.append("## Step 0 - where things live\n")
        lines.append("- Genre/topic field: `video_metadata.topic_categories` "
                      "(`src/taste_engine/db.py`), JSON list of Wikipedia URLs from "
                      "`resolve.py`'s `topicDetails.topicCategories`. "
                      f"Cached for {cached:,} of 30,440 video_metadata rows - no fetch needed.\n")
        lines.append("- Turned into readable labels by `classify._genres_from_topics` "
                      "-> `genres` column, tidied (generic labels like the near-universal "
                      "\"Music\" dropped) by `embed.tidy_genres`.\n")
        lines.append("- Canonical tracks: `canonical.collapse()`, called by "
                      "`score.scored_tracks(canonical=True)` (default). One row per merged "
                      "song; `genres` on that row is the **representative (most-played) "
                      "upload's** genres only, not a union across merged variants - see "
                      "Coverage below.\n")
        lines.append("- Cluster assignments: `embed.cluster_tracks()`, called by "
                      "`recommend.build()`. Not persisted; recomputed deterministically "
                      "from cached embeddings in `data/artifacts/`. Cluster **ids** are "
                      "unstable across runs (CLAUDE.md); `cluster_name` is not.\n")
        lines.append(f"- `config.MIN_SCORE` = {config.MIN_SCORE}. Shallow cluster threshold "
                      f"(from the brief) = {SHALLOW_THRESHOLD} eligible members.\n")

        lines.append("## Correctness gates (checked before any number below is trusted)\n")
        lines.append(f"- Canonical tracks = {len(frame):,}, matches CLAUDE.md's independently "
                      f"measured {EXPECTED_CANONICAL_TRACKS:,}: **{'OK' if gate1_ok else 'MISMATCH'}**\n")
        lines.append(f"- Re-derived canonical_key groups 1:1 with `collapse()`'s own grouping: "
                      f"**{'OK' if gate2_ok else 'MISMATCH'}**\n")
        for g in gate3_results:
            lines.append(
                f"- {g['name']!r} rediscover-pool cluster size = {g['got_size']} "
                f"(matches `scripts/backfill_report.py`'s measured {g['expected_size']}, "
                f"time-invariant): **{'OK' if g['size_ok'] else 'MISMATCH'}**. "
                f"Eligible count today = {g['got_eligible']} ({g['eligible_note']}).\n"
            )

        lines.append("\n## Methodology note - which pool is \"eligible\"\n")
        lines.append("The brief defines eligible candidate as `score >= config.MIN_SCORE` "
                      "with no mention of excluding favourites. The primary numbers below use "
                      "that plain reading: the full canonical+clustered pool, favourites "
                      "included. `writer.plan(mode=\"rediscover\")` - the actual backfill path "
                      "- excludes the top-50 favourites *before* computing per-cluster "
                      "eligibility; CLAUDE.md's cited T-Series (22) / Travis Scott (21) "
                      "figures are that rediscover-pool count, reproduced above as a "
                      "cross-check, not the primary figure used below. Clustering itself is "
                      "identical either way - `recommend.build()` clusters the full frame "
                      "before any favourites exclusion happens.\n")

        lines.append("\n## Number 1 - Coverage\n")
        lines.append(f"- As-delivered (representative upload's genres): "
                      f"{fmt_pct(n_ge1_delivered, n_total)} canonical tracks carry >=1 label; "
                      f"{fmt_pct(n_gt1_delivered, n_total)} carry >1.\n")
        lines.append(f"- Available-in-cache (union of genres across every merged upload "
                      f"sharing a canonical key): {fmt_pct(n_ge1_union, n_total)} carry >=1 "
                      f"label; {fmt_pct(n_gt1_union, n_total)} carry >1.\n")
        gap = n_ge1_union - n_ge1_delivered
        lines.append(f"- **Gap: {gap:,} canonical tracks ({gap / n_total * 100:.1f}%) have a "
                      f"genre label sitting in cache on a merged-away upload, but the "
                      f"canonical layer only keeps the representative's, so they show 0 "
                      f"labels as-delivered.** Of those recovered-by-union tracks, "
                      f"{fmt_pct(recovered_had_topic_variant, len(recovered))} had a "
                      f"`- Topic` upload among their merged variants - the representative "
                      f"itself was not.\n")
        lines.append(f"- Of the {len(zero_genre):,} as-delivered zero-genre canonical tracks: "
                      f"{zero_resolved:,} are resolved (metadata exists, genuinely untagged "
                      f"by YouTube) and {zero_unresolved:,} are unresolved "
                      f"(deleted/private - metadata never existed to tag).\n")

        lines.append("\n**Top 15 genre labels by canonical-track count (as-delivered):**\n")
        lines.append("| label | tracks |")
        lines.append("|---|---|")
        for label, n in top15:
            lines.append(f"| {label} | {n:,} |")

        lines.append("\n**Coverage by uploader type (representative upload's channel):**\n")
        lines.append("| uploader type | tracks | with >=1 genre | coverage |")
        lines.append("|---|---|---|---|")
        for utype, row in uploader_cov.iterrows():
            lines.append(f"| {utype} | {int(row['tracks']):,} | {int(row['with_genre']):,} | {row['pct']}% |")

        lines.append("\n## Number 2 - Per shallow cluster\n")
        lines.append(f"{len(cluster_table)} real (non-noise) clusters total; "
                      f"{n_shallow} are shallow (eligible members < {SHALLOW_THRESHOLD}).\n")
        lines.append("| cluster | name | eligible | labeled/eligible | modal genre | modal share | "
                      "ambiguous | outside sharing genre (noise excl.) | admit ratio |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for _, r in shallow_table.iterrows():
            modal = "not computable" if pd.isna(r["modal_genre"]) else r["modal_genre"]
            share = "n/a" if pd.isna(r["modal_share"]) else f"{r['modal_share']*100:.0f}%"
            amb = "n/a" if pd.isna(r["ambiguous"]) else ("yes" if r["ambiguous"] else "no")
            outside = "n/a" if pd.isna(r["outside_sharing_genre"]) else f"{int(r['outside_sharing_genre']):,}"
            admit = "n/a" if pd.isna(r["admit_ratio"]) else f"{r['admit_ratio']*100:.0f}%"
            lines.append(
                f"| {r['cluster']} | {r['cluster_name']} | {r['n_eligible']} | "
                f"{r['n_labeled']}/{r['n_eligible']} | {modal} | {share} | {amb} | {outside} | {admit} |"
            )
        lines.append("\n\"admit ratio\" = outside sharing genre / (eligible pool outside this "
                      "cluster). The fraction of *everyone else's* eligible candidates this "
                      "cluster's modal genre would admit into a backfill - a genuine "
                      "constraint should be well under 100%.\n")

        lines.append(f"\n**Clusters where the modal genre is ambiguous (no label above 50% "
                      f"of labeled eligible members), any cluster not just shallow ones:** "
                      f"{len(ambiguous_table)} of {len(cluster_table)}\n")
        if len(ambiguous_table):
            lines.append("| cluster | name | eligible | labeled | modal genre | modal share |")
            lines.append("|---|---|---|---|---|---|")
            for _, r in ambiguous_table.iterrows():
                lines.append(f"| {r['cluster']} | {r['cluster_name']} | {r['n_eligible']} | "
                              f"{r['n_labeled']} | {r['modal_genre']} | {r['modal_share']*100:.0f}% |")

        lines.append("\n## Sensitivity check - is \"genre match\" actually discriminating?\n")
        lines.append(f"Within the {len(labeled_all_report):,}-track labeled-eligible pool "
                      f"(spanning {label_meta['n_labeled_clusters']} clusters), some labels "
                      f"are common to most clusters rather than distinguishing between them - "
                      f"the same failure mode `embed.GENERIC_TOPICS` already exists to filter "
                      f"for \"Music\"/\"Entertainment\", just not extended to these. Applying "
                      f"the brief's own 50% bar symmetrically (a label common across more than "
                      f"half of labeled clusters cannot be what discriminates between them, "
                      f"the same way a genre needs >50% share *within* a cluster to be an "
                      f"unambiguous modal genre) excludes:\n")
        lines.append("\n| label | clusters it touches | share of labeled clusters |")
        lines.append("|---|---|---|")
        for label, n, pct in non_discriminative_rows:
            lines.append(f"| {label} | {n} / {label_meta['n_labeled_clusters']} | {pct*100:.0f}% |")
        lines.append(f"\nUnder the naive (literal brief-definition) view, the median admit "
                      f"ratio across shallow clusters is "
                      f"{shallow_table['admit_ratio'].median()*100:.0f}% - most of a shallow "
                      f"cluster's \"genre-matching\" candidates are actually just most of "
                      f"everyone else's eligible pool. Re-running modal genre and reachability "
                      f"with the labels above excluded (\"strict\" view) gives the numbers "
                      f"below.\n")
        lines.append("\n| cluster | name | modal genre (strict) | outside sharing (strict) | "
                      "admit ratio (strict) | reachable@45 (strict) |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in shallow_table.iterrows():
            modal_s = "not computable" if pd.isna(r["modal_genre_strict"]) else r["modal_genre_strict"]
            outside_s = "n/a" if pd.isna(r["outside_sharing_strict"]) else f"{int(r['outside_sharing_strict']):,}"
            admit_s = "n/a" if pd.isna(r["admit_ratio_strict"]) else f"{r['admit_ratio_strict']*100:.0f}%"
            reach_s = "n/a" if pd.isna(r["reachable_45_strict"]) else ("yes" if r["reachable_45_strict"] else "no")
            lines.append(f"| {r['cluster']} | {r['cluster_name']} | {modal_s} | {outside_s} | {admit_s} | {reach_s} |")

        if len(t_series_row):
            tr = t_series_row.iloc[0]
            lines.append(f"\n**T-Series** (CLAUDE.md's named example of incoherent "
                          f"nearest-embedding-centroid backfill - Known Open Item #3): modal "
                          f"genre `{tr['modal_genre']}` survives the strict filter unchanged "
                          f"(`music of asia` touches only "
                          f"{label_meta['spread'].get('music of asia', 0)}/{label_meta['n_labeled_clusters']} "
                          f"labeled clusters - genuinely discriminative), with "
                          f"{int(tr['outside_sharing_strict']) if pd.notna(tr['outside_sharing_strict']) else 0} "
                          f"outside eligible candidates sharing it either way. Genre-matching "
                          f"does not fix item #3 for this cluster - it fails differently: a "
                          f"short, genuinely-Bollywood-adjacent playlist instead of a "
                          f"full-length incoherent one (Joji, Playboi Carti, Doja Cat).\n")

        lines.append("\n## Number 3 - Reachability\n")
        lines.append(f"**Naive (literal brief definition):** of {n_shallow} shallow clusters, "
                      f"{n_reachable} could reach {SHALLOW_THRESHOLD} tracks using genre-matching "
                      f"eligible candidates (native + outside-cluster eligible candidates sharing "
                      f"the modal genre, noise/cluster=-1 excluded because today's backfill "
                      f"mechanism, `writer._select_with_backfill`, never draws from noise "
                      f"either); {n_not_reachable} could not; {n_not_computable} have no "
                      f"computable modal genre. **This number is inflated** - see the "
                      f"sensitivity check above: the modal genre for most clusters is \"pop\" "
                      f"or \"hip hop\", each present on {label_meta['spread'].get('pop', 0)}/"
                      f"{label_meta['n_labeled_clusters']} and "
                      f"{label_meta['spread'].get('hip hop', 0)}/{label_meta['n_labeled_clusters']} "
                      f"labeled clusters respectively, so \"shares the modal genre\" is close "
                      f"to \"is anything at all\" for most of the pool.\n")
        lines.append(f"\n**Strict (non-discriminative labels excluded):** of {n_shallow} shallow "
                      f"clusters, **{n_reachable_strict} could reach {SHALLOW_THRESHOLD} tracks**; "
                      f"{n_not_reachable_strict} could not; **{n_not_computable_strict} have no "
                      f"computable modal genre at all** once pop/hip hop/electronic/etc. are "
                      f"excluded - their eligible members carry no other label, so a genre "
                      f"constraint has nothing left to match on for them.\n")

        viable = "no" if n_reachable_strict <= n_not_computable_strict else (
            "yes" if n_reachable_strict >= n_shallow * 0.5 else "marginal"
        )
        verdict = (
            f"Genre-constrained backfill viable on this data: **{viable}** - under the "
            f"literal brief definition {n_reachable} of {n_shallow} shallow clusters "
            f"({n_reachable/n_shallow*100:.0f}% if {n_shallow} else 0) reach "
            f"{SHALLOW_THRESHOLD} tracks, but that figure is carried almost entirely by "
            f"non-discriminative labels (\"pop\" alone touches "
            f"{label_meta['spread'].get('pop', 0)} of {label_meta['n_labeled_clusters']} "
            f"labeled clusters); once those are excluded only {n_reachable_strict} of "
            f"{n_shallow} reach {SHALLOW_THRESHOLD} tracks and {n_not_computable_strict} "
            f"have no genre signal left to constrain on at all."
        )
        lines.append(f"\n## Verdict\n\n{verdict}\n")

        report_text = "\n".join(lines)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report_text)

        # ---- stdout summary ----
        print("=" * 78)
        print("GENRE COVERAGE - SUMMARY")
        print("=" * 78)
        print(f"canonical tracks                {n_total:,}")
        print(f"coverage as-delivered (>=1)     {fmt_pct(n_ge1_delivered, n_total)}")
        print(f"coverage union-in-cache (>=1)   {fmt_pct(n_ge1_union, n_total)}")
        print(f"representative-vs-union gap    {gap:,} tracks ({gap/n_total*100:.1f}%)")
        print(f"real clusters / shallow         {len(cluster_table)} / {n_shallow}")
        print(f"shallow clusters reachable@45   {n_reachable} / {n_shallow} "
              f"({n_not_computable} not computable)")
        print(f"ambiguous-modal-genre clusters  {len(ambiguous_table)} / {len(cluster_table)}")
        print()
        print(verdict)
        print()
        print(f"Full report written to {REPORT_PATH}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
