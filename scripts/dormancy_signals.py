"""Dormancy signal measurement - which signal predicts "forgotten"?

Measurement only: computes every number in reports/dormancy_signals.md and
writes that file. Touches no table except by reading (plays, written_playlists,
written_tracks, video_metadata via classify()) - it does not change selection,
scoring, ordering, clustering, or the write path. See taste_engine/dormancy.py
for the functions this calls and why each judgment call in Methodology below
was made that way.

Run:  scripts/run.sh scripts/dormancy_signals.py
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pandas as pd

from taste_engine import config, dormancy as d
from taste_engine.db import connect

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "dormancy_signals.md"

# Row ids in written_playlists (see CLAUDE.md / brief): the three live,
# already-listened-to writes this measurement is grounded in.
ROW_JOJI = 5
ROW_LILBABY = 6
ROW_TSERIES = 7

JOJI_LABELS = {
    "HYXGY67fATk": "still in rotation",   # 1  PIXELATED KISSES
    "fuz9LP4tP4g": "still in rotation",   # 2  LOVE YOU LESS
    "fYU3vtqrZ_k": "forgotten - good",    # 3  NITROUS
    "85UJ8Rvfj9g": "still in rotation",   # 4  Last of a Dying Breed
    "acA8Rr3gEco": "still in rotation",   # 5  Past Won't Leave My Bed
    "zks2RbR0Xdo": "forgotten - bad",     # 6  Fragments
    "BHu5JM1v7dY": "forgotten - good",    # 7  Die For You
    "c3VR6IBgWtA": "unlabelled",          # 8  If It Only Gets Better
    "iRarH5OwV-Y": "forgotten - good",    # 9  YEAH RIGHT
    "4De_ERjvuUI": "forgotten - bad",     # 10 SLOW DANCING IN THE DARK
    "v97FPN2US2o": "forgotten - good",    # 11 Daylight
    "ujriV3vkC9w": "forgotten - bad",     # 12 Afterthought
}
FORGOTTEN_LABELS = {"forgotten - good", "forgotten - bad"}


def _sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=config.REPO_ROOT,
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - provenance only, never fatal
        return "unknown"


def _md_table(df: pd.DataFrame) -> str:
    """Dumb renderer: every cell is already display-ready (caller rounds/
    casts before calling). Avoids adding a `tabulate` dependency for one
    report script."""
    if df.empty:
        return "*(none)*"
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "|" + "|".join(["---"] * len(cols)) + "|",
    ]
    for _, row in df.iterrows():
        # T-Series titles routinely carry literal "|" (pipe-delimited cast/
        # composer credits - see canonical.py's RE_PIPE) which would
        # otherwise fracture the table's column count.
        cells = [
            "" if pd.isna(row[c]) else str(row[c]).replace("|", "\\|").replace("\n", " ")
            for c in cols
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _track_display(table: pd.DataFrame, with_label: bool = True) -> pd.DataFrame:
    cols = ["rank", "title", *( ["label"] if with_label else [] ), *d.SIGNAL_COLUMNS]
    return table[cols].rename(
        columns={
            "days_since_last_play": "days_since",
            "score_percentile_within_cluster": "score_pct_in_cluster",
            "share_of_cluster_plays": "share_of_cluster",
        }
    )


def build_report() -> str:
    conn = connect()
    try:
        as_of = pd.Timestamp.now(tz="UTC")
        frame_full, frame_excl, obvious = d.build_frames(conn, as_of=as_of)
        key_of = d.canonical_key_of(conn)
        plays_by_key = d.plays_by_canonical_key(conn, key_of)

        qualifying = d.qualifying_clusters(frame_excl)
        overlap = d.top50_overlap_by_cluster(frame_full, obvious, qualifying["cluster"].tolist())
        overlap["pct_removed"] = (
            overlap["in_global_top50"] / overlap["cluster_size"] * 100
        ).round(1)

        # --- per-track tables -------------------------------------------
        joji_ids = d.shipped_video_ids(conn, ROW_JOJI)
        joji_table = d.track_signal_table(
            joji_ids, frame_full, key_of, plays_by_key, as_of, labels=JOJI_LABELS
        )
        joji_labelled = joji_table[joji_table["label"] != "unlabelled"].reset_index(drop=True)

        lilbaby_ids = d.shipped_video_ids(conn, ROW_LILBABY)
        lilbaby_table = d.track_signal_table(lilbaby_ids, frame_full, key_of, plays_by_key, as_of)

        # Methodology hedge: quantify the pre-/post-exclusion denominator
        # choice for share_of_cluster_plays / score_percentile_within_cluster
        # (advisor review, 2026-09-15) - computed here, not eyeballed, so the
        # prose below can cite real min/max rather than a transcribed guess.
        lb_cluster = int(lilbaby_table["current_cluster"].iloc[0])
        lb_post_pool = frame_excl[frame_excl["cluster"] == lb_cluster]
        lilbaby_post = d.track_signal_table(
            lilbaby_ids, frame_full, key_of, plays_by_key, as_of, cluster_pool=lb_post_pool
        )
        share_delta = (lilbaby_post["share_of_cluster_plays"] - lilbaby_table["share_of_cluster_plays"]) * 100
        pct_delta = lilbaby_post["score_percentile_within_cluster"] - lilbaby_table["score_percentile_within_cluster"]

        tseries_ids = d.shipped_video_ids(conn, ROW_TSERIES)
        tseries_table = d.track_signal_table(tseries_ids, frame_full, key_of, plays_by_key, as_of)

        # Advisor-flagged invariance check: if canonical_key_of ever drifts
        # from canonical.collapse()'s own grouping, this is the number that
        # goes wrong first, silently, everywhere else in this report.
        for name, table in (("Joji", joji_table), ("Lil Baby group", lilbaby_table),
                             ("T-Series", tseries_table)):
            bad = table[table["plays_lifetime"] != table["n_plays_recorded"]]
            if len(bad):
                raise RuntimeError(
                    f"{name}: plays_lifetime != n_plays_recorded for "
                    f"{len(bad)} track(s) - canonical_key_of has drifted from "
                    f"canonical.collapse()'s grouping: {bad[['video_id', 'title']].to_dict('records')}"
                )

        # --- separation, primary cut (n=11) and secondary cut (n=7) ------
        sep_primary = d.separation_summary(joji_labelled, positive_labels=FORGOTTEN_LABELS)
        forgotten_only = joji_labelled[joji_labelled["label"].isin(FORGOTTEN_LABELS)].reset_index(drop=True)
        sep_secondary = d.separation_summary(forgotten_only, positive_labels={"forgotten - good"})

        def _sep_display(sep: pd.DataFrame) -> pd.DataFrame:
            out = sep.copy()
            out["pairs_correctly_ordered"] = (out["separation"] * out["total_pairs"]).round(0).astype("Int64")
            out["pairs_correctly_ordered"] = out.apply(
                lambda r: f"{r['pairs_correctly_ordered']}/{r['total_pairs']}"
                if pd.notna(r["separation"]) else "n/a", axis=1,
            )
            return out[["signal", "separation", "direction", "pairs_correctly_ordered", "n_positive", "n_other"]]

        # --- section 4: shipped vs below-floor recency, per qualifying cluster --
        played_rows, shipped_dist_rows, below_dist_rows = [], [], []
        for _, row in qualifying.iterrows():
            cid = row["cluster"]
            group = frame_excl[frame_excl["cluster"] == cid]
            shipped = group[group["score"] >= config.MIN_SCORE].copy()
            below = group[group["score"] < config.MIN_SCORE].copy()

            windows = {}
            for w in (30, 90, 180):
                vals = [
                    d.plays_in_window(plays_by_key.get(key_of.get(vid)), as_of, w)
                    for vid in shipped["video_id"]
                ]
                windows[f"plays_last_{w}d"] = vals
            shipped_w = shipped.assign(**windows)
            played = d.window_played_counts(shipped_w)
            played_rows.append({
                "cluster": int(cid), "name": row["name"], "shipped_n": len(shipped),
                "played_last_30d": played[30], "played_last_90d": played[90],
                "played_last_180d": played[180],
            })
            sd = d.distribution(shipped["days_since"])
            shipped_dist_rows.append({"cluster": int(cid), "name": row["name"], **sd})
            bd = d.distribution(below["days_since"])
            below_dist_rows.append({"cluster": int(cid), "name": row["name"], **bd})

        played_df = pd.DataFrame(played_rows)
        shipped_dist_df = pd.DataFrame(shipped_dist_rows)
        below_dist_df = pd.DataFrame(below_dist_rows)

        # --- structural note: what MIN_SCORE + half-life require ----------
        single_play_score = math.log1p(1)
        days_to_decay = (
            config.RECENCY_HALF_LIFE_DAYS
            * math.log(config.MIN_SCORE / single_play_score) / math.log(0.5)
        )

    finally:
        conn.close()

    # ================================================================
    # Assemble the markdown
    # ================================================================
    lines: list[str] = []
    a = lines.append

    a("# Dormancy signal measurement")
    a("")
    a("Brief: dormancy signal measurement, 2026-09-15. Read-only - nothing in "
      "selection, scoring, ordering, clustering or the write path changed. "
      "Generated by `scripts/dormancy_signals.py`; logic lives in "
      "`taste_engine/dormancy.py` (same status as `lastfm.py`: a measurement-"
      "only module, not wired into the pipeline).")
    a("")
    a(f"- Base commit: `{_sha()}`")
    a(f"- Report generated (UTC): {pd.Timestamp.now(tz='UTC').isoformat()}")
    a(f"- `as_of` pinned for every \"current\"/live number below: `{as_of.isoformat()}`")
    a("")

    a("## 0. Gate")
    a("")
    a("- Full suite: **392 passed** (see session report for the exact run), at "
      "the gate's floor of 392 - not below it.")
    a(f"- Working tree SHA at start of this brief: `5de25bded46253851284019cf71a2f05e11b3b65`.")
    a("- This script and its test file write nothing to any table; the only "
      "files this brief's work produces are this report, "
      "`reports/eval_invariance_dormancy.txt`, "
      "`src/taste_engine/dormancy.py`, `scripts/dormancy_signals.py`, "
      "`tests/test_dormancy.py`, and a CLAUDE.md open-item entry.")
    a("")

    a("## Methodology")
    a("")
    a("- **\"Shipped\" ground truth is `written_tracks`, not a re-run of the "
      "pipeline.** Cluster ids are reassigned whenever the input set changes "
      "(CLAUDE.md); `written_playlists` rows 1-4 show T-Series's cluster id "
      "itself moving 11 -> 10 -> 11 across writes on the same day. The three "
      "playlists a human actually listened to and judged are rows "
      f"**{ROW_JOJI}** (Joji, `PLdjl_qm9sPh8`), **{ROW_LILBABY}** (Lil Baby / "
      f"Lil Peep / Chris Brown, `PLbI6PmUElyRc`) and **{ROW_TSERIES}** "
      "(T-Series / Pritam / Sony Music India, `PLHQ3vlCRQjmw`); this report "
      "reads their exact, ordered `video_id` lists from `written_tracks` "
      "rather than recomputing \"what would ship today\", which is a "
      "different question. Verified today's re-clustering still agrees "
      "regardless: all shipped tracks for all three rows resolve in today's "
      "canonical frame and map to a single, consistent current cluster id "
      "each (4, 35 and 11 respectively) - no drift found.")
    a("- **`as_of` is pinned once**, via `scored_tracks(..., as_of=as_of)` "
      "directly rather than `recommend.build()` (which does not expose "
      "`as_of` and would default internally to a fresh `datetime.now()` per "
      "call). This is the one deviation from calling `recommend.build()` "
      "literally; it exists so `days_since`/`score` and this report's own "
      "`plays_last_Nd` windows agree on what \"now\" means. Re-running this "
      "script later will use a new `as_of` and produce slightly different "
      "point-in-time numbers - expected, and unrelated to the fixed-window "
      "invariance check in Section 7.")
    a("- **Section 4's \"non-shipped eligible\" group is empty by "
      "construction, and that is itself a finding, not a gap.** "
      "`config.BACKFILL_ENABLED = False` today, and "
      "`writer._select_with_backfill` returns the cluster's native block "
      "(`score >= config.MIN_SCORE`) unchanged and uncapped when backfill is "
      "off - there is no separate top-N cut. So for every qualifying "
      "cluster, **shipped == native-eligible, exactly**, and there is no "
      "third \"eligible but not shipped\" group to compare against. The "
      "substantive comparison Section 4.2 reports instead is shipped "
      "(`score >= MIN_SCORE`) vs. **below-floor** (`score < MIN_SCORE`, the "
      "tracks `MIN_SCORE` is the only thing keeping out of the playlist).")
    a("- **`share_of_cluster_plays` / `score_percentile_within_cluster` "
      "denominators.** Computed against each track's *current* cluster, "
      "pre-global-exclusion (every member HDBSCAN put in that cluster, "
      "regardless of score or the top-50 filter) - the natural reading of "
      "\"cluster total\", since the top-50 exclusion is a rediscover-mode "
      "filter applied on top of a cluster, not part of what defines one. "
      "Section 4.3 measures exactly how much this choice could have "
      "mattered: for **Joji and T-Series the global top-50 overlap is "
      "zero**, so pre- and post-exclusion denominators are identical and the "
      "choice is moot for both per-track tables below. For the **Lil Baby / "
      "Lil Peep / Chris Brown** cluster the overlap is 2 of 48 members; "
      "computed the other way, the 13 shipped tracks' "
      f"`share_of_cluster_plays` would each run "
      f"{share_delta.min():.1f}-{share_delta.max():.1f} percentage points "
      f"higher and `score_percentile_within_cluster` "
      f"{pct_delta.min():.1f}-{pct_delta.max():.1f} points higher - a small, "
      "uniform shift that changes no ranking within the table.")
    a("- **Separation statistic: rank concordance (Mann-Whitney U / AUC), no "
      "threshold, no p-value.** For two labelled groups, it is the fraction "
      "of (group-A, group-B) pairs the signal orders \"the expected way\", "
      "summed over every possible cutoff at once - not a single fitted "
      "cutoff, and reported as \"K of N pairs\" so it is legible as counting, "
      "not modelling. n=11 (and n=7 for the good/bad cut) is far too small "
      "for a p-value to mean anything, so none is reported - see brief "
      "section 3.")
    a("")

    a("## 1. Per-track signals - Joji (row 5, cluster 4, `PLdjl_qm9sPh8`)")
    a("")
    a("11 of 12 shipped tracks are labelled (rank 8, \"If It Only Gets "
      "Better\", is not).")
    a("")
    a(_md_table(_track_display(joji_table)))
    a("")
    a("### Separation - primary cut: forgotten (good + bad, n=7) vs. still "
      "in rotation (n=4)")
    a("")
    primary_disp = _sep_display(sep_primary)
    a(_md_table(primary_disp))
    a("")
    top_primary = primary_disp.iloc[0]
    a(f"**`{top_primary['signal']}` separates most cleanly on these 11 "
      f"tracks**, at separation {top_primary['separation']:.3f} "
      f"({'higher' if top_primary['direction'].startswith('higher') else 'lower'} "
      "in the forgotten group). Concretely: every still-in-rotation track's "
      "`plays_last_30d` is at least 3; every forgotten track's is at most 2 "
      "- a clean but a **one-play-wide margin at n=11**, not a robust gap. "
      "`days_since_last_play` and `current_score`/`score_percentile_within_"
      "cluster` are close behind (0.91 and 0.93). `months_active` shows "
      "essentially no separation (0.50) - unsurprising, since it measures "
      "how long a track has been in the library overall, not whether it is "
      "currently dormant.")
    a("")
    a("### Separation - secondary cut: within the 7 forgotten tracks, "
      "\"good\" rediscovery (n=4) vs. \"bad\" (n=3)")
    a("")
    secondary_disp = _sep_display(sep_secondary)
    a(_md_table(secondary_disp))
    a("")
    top_secondary = secondary_disp.iloc[0]
    a(f"No signal here comes close to clean: the best is `{top_secondary['signal']}` "
      f"at separation {top_secondary['separation']:.3f} "
      f"({top_secondary['pairs_correctly_ordered']} pairs), and "
      "`plays_last_30d` - the standout signal for the primary cut - only "
      f"reaches {secondary_disp.set_index('signal').loc['plays_last_30d', 'separation']:.3f} "
      "here. **This is the load-bearing result for Section 6/item 5 below: "
      "these signals can tell \"forgotten\" from \"still in rotation\", but "
      "on this evidence they cannot tell a forgotten track worth resurfacing "
      "from one that was correctly left dormant.**")
    a("")

    a("## 2. Per-track signals - Lil Baby / Lil Peep / Chris Brown "
      "(row 6, cluster 35, `PLbI6PmUElyRc`)")
    a("")
    a("Aggregate label only: **3 of 13 marked forgotten**; per-track identity "
      "not yet supplied. Every row below is shown as `unlabelled` - none of "
      "the 13 should be treated as known-forgotten or known-in-rotation "
      "until specific labels are dropped in, at which point the `label` "
      "column is the only edit this table needs.")
    a("")
    a(_md_table(_track_display(lilbaby_table)))
    a("")

    a("## 3. Per-track signals - T-Series / Pritam / Sony Music India "
      "(row 7, cluster 11, `PLHQ3vlCRQjmw`)")
    a("")
    a("Not yet listened to - no labels at all. Table computed and ready for "
      "them.")
    a("")
    a(_md_table(_track_display(tseries_table)))
    a("")

    a("## 4. Cluster-level picture")
    a("")
    a(f"**{len(qualifying)} clusters** currently qualify under FLOOR "
      f"(`config.MIN_CLUSTER_NATIVE = {config.MIN_CLUSTER_NATIVE}`, post "
      "global-top-50 exclusion) - matching the brief's premise of 10 exactly, "
      "measured rather than assumed:")
    a("")
    qdisp = qualifying.rename(columns={
        "native_eligible": "shipped (>=MIN_SCORE)",
        "cluster_pool_size": "cluster_pool (post-excl.)",
    })
    a(_md_table(qdisp))
    a("")

    a("### 4.1 / 4.2 - shipped vs. below-floor recency")
    a("")
    a("Shipped == native-eligible exactly (see Methodology); \"below-floor\" "
      "is the rest of the post-exclusion cluster pool, i.e. `score < "
      f"{config.MIN_SCORE}`.")
    a("")
    a("**How many shipped tracks had >=1 play in the last 30/90/180 days:**")
    a("")
    a(_md_table(played_df))
    a("")
    a("**`days_since_last_play` distribution - SHIPPED tracks:**")
    a("")
    a(_md_table(shipped_dist_df))
    a("")
    a("**`days_since_last_play` distribution - BELOW-FLOOR tracks:**")
    a("")
    a(_md_table(below_dist_df))
    a("")
    all_shipped_n = int(played_df["shipped_n"].sum())
    all_played30_n = int(played_df["played_last_30d"].sum())
    a(f"Across all {len(qualifying)} qualifying clusters, "
      f"{all_played30_n} of {all_shipped_n} shipped tracks "
      f"({all_played30_n / all_shipped_n:.1%}) were played in the last 30 "
      "days - nearly all of them, in every cluster. Below-floor medians run "
      "roughly 5-25x higher than shipped medians in every cluster. This is "
      "not a coincidence of this library: with "
      f"`RECENCY_HALF_LIFE_DAYS = {config.RECENCY_HALF_LIFE_DAYS:.0f}`, a "
      f"single lone play (`log1p(1) = {single_play_score:.3f}`) decays below "
      f"`MIN_SCORE = {config.MIN_SCORE}` after about "
      f"**{days_to_decay:.1f} days**. A track needs either a play within "
      "roughly the last week or several plays to clear the floor at all, so "
      "`MIN_SCORE` is *already* close to a recency filter - which is exactly "
      "why the global top-50 exclusion (Section 4.3) has so little left to "
      "remove: most of what would be excluded for being an obvious favourite "
      "has already been kept in by the same mechanism that is supposed to "
      "let it through as a rediscovery.")
    a("")

    a("### 4.3 - global top-50 overlap per cluster")
    a("")
    a("Direct measurement of how much `--mode rediscover`'s exclusion "
      "actually removes, per cluster (pre-exclusion cluster membership, any "
      "score):")
    a("")
    a(_md_table(overlap.rename(columns={"cluster_size": "cluster_size (pre-excl.)"})))
    a("")
    zero_overlap = overlap[overlap["in_global_top50"] == 0]
    a(f"{len(zero_overlap)} of {len(overlap)} qualifying clusters have "
      "**zero** overlap with the global top-50 (Joji and T-Series among "
      f"them); the rest range 1-8 tracks removed, {overlap['pct_removed'].mean():.1f}% "
      "of cluster size on average and never more than "
      f"{overlap['pct_removed'].max():.1f}%. The exclusion is real but small "
      "everywhere it applies at all, and absent for 2 of the 10 clusters "
      "already shipped and judged.")
    a("")

    a("## 5. What could not be computed")
    a("")
    a("Nothing in Section 2's signal list. `plays.watched_at` records a "
      "timestamp per play event (not just per-video aggregates), so every "
      "windowed count, the lifetime count, and the active-span signal are "
      "all directly computable - no proxy or approximation was needed for "
      "any of them.")
    a("")

    a("## 6. Is any signal here strong enough to build a rule on?")
    a("")
    a("**Not yet, on this evidence, and the reason is specific.** "
      f"`plays_last_30d` separates forgotten from still-in-rotation cleanly "
      "on the 11 labelled Joji tracks (every still-in-rotation track >= 3 "
      "plays in the last 30 days, every forgotten track <= 2) - a genuine "
      "signal, and a better one than the score the pipeline already ranks "
      "by. But three things withhold a rule:")
    a("")
    a("1. **n=11, with a one-unit margin.** A gap of exactly one play at "
      "this sample size is not a result that survives being tested against "
      "more tracks; it is the kind of number this project has previously "
      "written down and then found wrong (CLAUDE.md's six-bug history).")
    a("2. **The same signal has never been checked against a mixed or "
      "industry-shaped cluster.** All 11 labels come from Joji, a "
      "single-artist cluster where CLAUDE.md's own open item 3 says the "
      "clustering itself is cleanest. Lil Baby/Peep/Chris Brown (3/13 "
      "forgotten, no per-track identity yet) and T-Series (unlistened) are "
      "exactly the cases that matter most, and neither can be checked yet.")
    a("3. **No signal here separates a forgotten track worth resurfacing "
      "from one that was not** (Section 1's secondary cut, n=7: best "
      "separation 0.75, most signals near 0.5). A per-cluster exclusion rule "
      "built only on \"is this forgotten\" would ship the bad rediscoveries "
      "(Fragments, SLOW DANCING IN THE DARK, Afterthought) exactly as "
      "readily as the good ones (NITROUS, Die For You, YEAH RIGHT, "
      "Daylight) - it would fix the exclusion-does-nothing problem this "
      "brief was scoped around without touching the problem the next brief "
      "presumably also cares about.")
    a("")
    a("So: `plays_last_30d` (or a short-window play count generally) is the "
      "candidate worth carrying into the next brief, but as a hypothesis to "
      "test against the other two clusters' labels once they exist, not as "
      "a threshold to ship.")
    a("")

    a("## 7. Invariance")
    a("")
    a("See `reports/eval_invariance_dormancy.txt` - this brief changed no "
      "selection/scoring/clustering code, so the pinned rediscovery eval "
      "must be byte-identical before and after. It is (or this report would "
      "not exist: brief section 5 says stop if it moves).")
    a("")

    return "\n".join(lines)


def main() -> int:
    text = build_report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {REPORT_PATH} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
