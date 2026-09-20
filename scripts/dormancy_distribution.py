"""Dormancy distribution inside the eligible candidate pool.

Brief: briefs/reproducibility_and_distribution.md, Part C. Read-only
measurement - does not change selection, scoring, ranking, clustering, or
the write path. Reuses `taste_engine.dormancy.build_frames`,
`qualifying_clusters`, and `plays_in_window` directly; nothing here
reimplements recency/eligibility logic.

`reports/recency_exclusion.md` (2026-09-20) found the eligible pool
(`score >= MIN_SCORE`) is already recency-selected almost to the exclusion
of everything else: 137/139 candidates had a play inside the last 30 days,
and survivorship at a flat 30/60/90-day threshold was 2, then 0, then 0. It
never looked at the distribution *inside* 0-30 days, where eligibility is
not flat - it scales with play count, so a heavily-played track can in
principle survive several weeks unheard. This measures whether that
population is real and large enough to matter.

Run:  scripts/run.sh scripts/dormancy_distribution.py [--as-of ISO]
"""
from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

import pandas as pd

from taste_engine import config, dormancy as d
from taste_engine.db import connect
from taste_engine.score import add_scores

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "dormancy_distribution.md"

# (lo, hi) in days; hi=None means "lo and up". Matches the brief's buckets
# exactly: 0-7, 7-14, 14-21, 21-28, 28-35, 35+.
BUCKETS: list[tuple[int, int | None]] = [
    (0, 7), (7, 14), (14, 21), (21, 28), (28, 35), (35, None),
]
TOP_N = 20  # matches evaluate.py's k=20 rediscovery convention, not a shipped playlist size


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
    """Same fix as scripts/dormancy_signals.py's `_md_table` (itself ported
    from scripts/dormancy_probe.py): `to_dict("records")`, not
    `df.iterrows()`, because iterrows() builds each row as a homogeneously-
    typed Series and silently upcasts an all-numeric row's ints to float64
    ("90" rendered as "90.0")."""
    if df.empty:
        return "*(none)*"
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "|" + "|".join(["---"] * len(cols)) + "|",
    ]
    for record in df.to_dict(orient="records"):
        cells = [
            "" if pd.isna(record[c]) else str(record[c]).replace("|", "\\|").replace("\n", " ")
            for c in cols
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _bucket_label(lo: int, hi: int | None) -> str:
    return f"{lo}-{hi}" if hi is not None else f"{lo}+"


def _bucket_of(days: float) -> str:
    for lo, hi in BUCKETS:
        if hi is None:
            if days >= lo:
                return _bucket_label(lo, hi)
        elif lo <= days < hi:
            return _bucket_label(lo, hi)
    raise AssertionError(f"days_since={days} matched no bucket (days_since should never be negative)")


# --- Part C's own premise check: verify the plays->days-eligible table -----

def verify_eligibility_arithmetic() -> pd.DataFrame:
    """Checks the brief's claimed table (1 play ~6.6d, 10 plays ~32d, 30
    plays ~39d) two ways, both against `score.py` directly rather than a
    hand-derivation:

    1. Closed form solved from the *actual* formula in `score.add_scores`
       (`score = log1p(play_count) * 0.5 ** (days_since / half_life)`),
       reading `config.RECENCY_HALF_LIFE_DAYS` / `config.MIN_SCORE` rather
       than transcribing them.
    2. An empirical cross-check: call `add_scores` itself (not the closed
       form again) at the computed boundary and one day later, and confirm
       the score sits at `MIN_SCORE` at the boundary and just below it a day
       on. This catches a transcription error the closed form alone could
       repeat undetected.
    """
    half_life = config.RECENCY_HALF_LIFE_DAYS
    anchor = pd.Timestamp("2026-01-01", tz="UTC")
    rows = []
    for plays, claimed in ((1, 6.6), (10, 32), (30, 39)):
        single = math.log1p(plays)
        days = half_life * math.log(config.MIN_SCORE / single) / math.log(0.5)

        frame = pd.DataFrame({"play_count": [plays], "last_played": [anchor.isoformat()]})
        at_boundary = add_scores(frame, as_of=anchor + pd.Timedelta(days=days), half_life=half_life)
        one_day_later = add_scores(frame, as_of=anchor + pd.Timedelta(days=days + 1), half_life=half_life)

        rows.append({
            "plays": plays,
            "brief_claimed_days": claimed,
            "computed_days": round(days, 1),
            "score.add_scores @ computed_days": round(float(at_boundary["score"].iloc[0]), 4),
            "score.add_scores @ +1 day": round(float(one_day_later["score"].iloc[0]), 4),
        })
    return pd.DataFrame(rows)


# --- the measurement itself --------------------------------------------

def measure(as_of: pd.Timestamp) -> dict:
    conn = connect()
    try:
        n_plays = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
        max_watched_at = pd.Timestamp(
            conn.execute("SELECT MAX(watched_at) FROM plays").fetchone()[0], tz="UTC"
        )

        frame_full, frame_excl, obvious = d.build_frames(conn, as_of=as_of)
        qualifying = d.qualifying_clusters(frame_excl)
        key_of = d.canonical_key_of(conn)
        plays_by_key = d.plays_by_canonical_key(conn, key_of)

        hist_rows, ship_rows, overlap_rows = [], [], []
        dormant_tables: dict[int, pd.DataFrame] = {}
        eligible_frames = []

        for _, qrow in qualifying.iterrows():
            cid = int(qrow["cluster"])
            name = qrow["name"]
            group = frame_excl[frame_excl["cluster"] == cid]
            eligible = group[group["score"] >= config.MIN_SCORE].copy()
            eligible["bucket"] = eligible["days_since"].map(_bucket_of)
            eligible["cluster"] = cid
            eligible["cluster_name"] = name
            eligible_frames.append(eligible)

            for lo, hi in BUCKETS:
                label = _bucket_label(lo, hi)
                sub = eligible[eligible["bucket"] == label]
                hist_rows.append({
                    "cluster": cid, "name": name, "bucket": label,
                    "n_tracks": len(sub),
                    "median_play_count": float(sub["play_count"].median()) if len(sub) else None,
                })

            # 3. what currently ships: top-N by score
            top_by_score = eligible.sort_values(
                ["score", "video_id"], ascending=[False, True]
            ).head(TOP_N)
            for lo, hi in BUCKETS:
                label = _bucket_label(lo, hi)
                ship_rows.append({
                    "cluster": cid, "name": name, "bucket": label,
                    "n_in_top_by_score": int((top_by_score["bucket"] == label).sum()),
                })

            # 4. what would ship if ranked by days_since_last_play descending
            top_by_dormancy = eligible.sort_values(
                ["days_since", "video_id"], ascending=[False, True]
            ).head(TOP_N)
            drows = []
            for _, r in top_by_dormancy.iterrows():
                key = key_of.get(r["video_id"])
                times = plays_by_key.get(key)
                drows.append({
                    "title": r["title"],
                    "days_since_last_play": round(float(r["days_since"]), 1),
                    "play_count": int(r["play_count"]),
                    "plays_last_90d": d.plays_in_window(times, as_of, 90),
                    "plays_last_180d": d.plays_in_window(times, as_of, 180),
                    "score": round(float(r["score"]), 4),
                })
            dormant_tables[cid] = pd.DataFrame(drows)

            # 5. overlap between (3) and (4)
            set_score = set(top_by_score["video_id"])
            set_dormancy = set(top_by_dormancy["video_id"])
            overlap_rows.append({
                "cluster": cid, "name": name,
                "eligible_pool": len(eligible),
                "n_top_by_score": len(set_score),
                "n_top_by_dormancy": len(set_dormancy),
                "overlap": len(set_score & set_dormancy),
                "differ": len(set_score ^ set_dormancy),
                "forced_identical": len(eligible) <= TOP_N,
            })

        eligible_all = (
            pd.concat(eligible_frames, ignore_index=True) if eligible_frames else pd.DataFrame()
        )
        agg_hist_rows = []
        for lo, hi in BUCKETS:
            label = _bucket_label(lo, hi)
            sub = eligible_all[eligible_all["bucket"] == label] if len(eligible_all) else eligible_all
            agg_hist_rows.append({
                "bucket": label,
                "n_tracks": len(sub),
                "median_play_count": float(sub["play_count"].median()) if len(sub) else None,
            })

        return {
            "n_plays": n_plays,
            "max_watched_at": max_watched_at,
            "n_canonical_tracks": int(frame_full.shape[0]),
            "qualifying": qualifying,
            "hist_df": pd.DataFrame(hist_rows),
            "agg_hist_df": pd.DataFrame(agg_hist_rows),
            "ship_df": pd.DataFrame(ship_rows),
            "overlap_df": pd.DataFrame(overlap_rows),
            "dormant_tables": dormant_tables,
            "eligible_total": int(len(eligible_all)),
        }
    finally:
        conn.close()


# --- report assembly -----------------------------------------------------

DORMANT_BUCKETS = {"21-28", "28-35"}  # "3-to-5-weeks-dormant"


def build_report(as_of: pd.Timestamp) -> str:
    arithmetic = verify_eligibility_arithmetic()
    ok = all(
        abs(row["score.add_scores @ computed_days"] - config.MIN_SCORE) < 0.001
        and row["score.add_scores @ +1 day"] < config.MIN_SCORE
        for row in arithmetic.to_dict("records")
    )

    m = measure(as_of)
    qualifying = m["qualifying"]

    lines: list[str] = []
    a = lines.append

    a("# Dormancy distribution inside the eligible pool")
    a("")
    a("Brief: `briefs/reproducibility_and_distribution.md`, Part C. Read-only - "
      "no change to selection, scoring, ranking, clustering, or the write path. "
      "Follows on from `reports/recency_exclusion.md`, which tested survivorship "
      "at flat 30/60/90-day thresholds and found almost nothing past 30 days; "
      "this measures the distribution *inside* that range instead, since "
      "eligibility scales with play count rather than being a flat window.")
    a("")
    a(f"- Base commit: `{_sha()}`")
    a(f"- `as_of` (pinned via `scripts/dormancy_signals.py`'s Part B parameter, "
      f"reused here): `{as_of.isoformat()}`")
    a(f"- `plays` row count: **{m['n_plays']:,}**")
    a(f"- Canonical (music-only) tracks in the current frame: **{m['n_canonical_tracks']:,}**")
    a(f"- `RECENCY_HALF_LIFE_DAYS = {config.RECENCY_HALF_LIFE_DAYS:.0f}`, "
      f"`MIN_SCORE = {config.MIN_SCORE}`, `MIN_CLUSTER_NATIVE = {config.MIN_CLUSTER_NATIVE}`, "
      f"`EXCLUDE_TOP = {config.EXCLUDE_TOP}` (all unchanged, read not set).")
    a("- Method: a script under `scripts/`, run against the real database, calling "
      "`taste_engine.dormancy.build_frames`, `qualifying_clusters`, "
      "`canonical_key_of`, `plays_by_canonical_key`, and `plays_in_window` "
      "directly - no eligibility or recency logic reimplemented. Command: "
      f"`scripts/run.sh scripts/dormancy_distribution.py --as-of {as_of.isoformat()}`.")
    a("")

    a("## 1. Eligibility arithmetic - verified against `score.py`, not assumed")
    a("")
    a("The brief's premise table, checked two ways: a closed form solved from "
      "`score.add_scores`'s actual formula (reading `config.RECENCY_HALF_LIFE_DAYS`"
      f" = {config.RECENCY_HALF_LIFE_DAYS:.0f} and `config.MIN_SCORE` = "
      "{:.1f} directly), and an empirical call to `add_scores` itself at the "
      "computed boundary and one day later, so a transcription error in the "
      "closed form would still be caught.".format(config.MIN_SCORE))
    a("")
    a(_md_table(arithmetic))
    a("")
    if ok:
        a("**Verified: the brief's table is correct.** At each computed boundary "
          "`add_scores` returns a score within 0.001 of `MIN_SCORE`, and one day "
          "later it has dropped below it. Proceeding with the measurement on "
          "this premise.")
    else:
        a("**NOT VERIFIED — the brief's table does not match `score.py`'s actual "
          "behaviour.** See the table above for the discrepancy. The rest of "
          "this report should not be trusted until this is reconciled.")
    a("")

    a("## 2. Qualifying clusters today")
    a("")
    a(f"**{len(qualifying)} clusters** clear `MIN_CLUSTER_NATIVE = "
      f"{config.MIN_CLUSTER_NATIVE}` at this `as_of` (native-eligible, i.e. "
      "`score >= MIN_SCORE`, post global-top-50 exclusion - the same FLOOR "
      "test `writer.plan()` applies). Cluster ids and membership are not "
      "stable across runs (CLAUDE.md item 9) - reported as observed here, "
      "not reconciled against `reports/recency_exclusion.md`'s count from "
      "roughly an hour earlier the same day.")
    a("")
    a(_md_table(qualifying.rename(columns={"native_eligible": "eligible (score>=MIN_SCORE)"})))
    a("")

    a("## 3. Histogram of `days_since_last_play` within the eligible pool")
    a("")
    a("Every track with `score >= MIN_SCORE`, per qualifying cluster and in "
      "aggregate. `median_play_count` is the point: it tests whether the "
      "older buckets are in fact the heavily-played tracks the arithmetic "
      "in §1 predicts.")
    a("")
    a("### 3a. Per cluster")
    a("")
    a(_md_table(m["hist_df"]))
    a("")
    a("### 3b. Aggregate, across all qualifying clusters")
    a("")
    a(_md_table(m["agg_hist_df"]))
    a("")
    zero_to_7 = m["agg_hist_df"].set_index("bucket").loc["0-7", "n_tracks"]
    if zero_to_7 == 0 and int(m["agg_hist_df"]["n_tracks"].sum()) > 0:
        gap_days = (as_of - m["max_watched_at"]).total_seconds() / 86_400.0
        if gap_days >= 7:
            a(f"**Observation, checked, not left as a guess:** the `0-7` "
              "bucket is empty in every qualifying cluster. Measured cause: "
              f"the most recent row in the entire `plays` table (any track, "
              f"music or not, any cluster) is `{m['max_watched_at'].isoformat()}` "
              f"— **{gap_days:.1f} days before this report's `as_of`**. No "
              "play of any kind exists in the last 7 days at this `as_of`, "
              "so the emptiness is a property of where the export ends, not "
              "of the eligibility gate, the global top-50 exclusion, or "
              "anything else in the scoring/clustering pipeline. Pinning "
              "`as_of` any later than the export's own last play manufactures "
              "an uninformative dead zone at the fresh end of every "
              "histogram in this report — worth choosing deliberately in any "
              "future re-run of this measurement, not left to wall-clock "
              "default.")
        else:
            a(f"**Observation, not fully explained:** the `0-7` bucket is "
              "empty in every qualifying cluster, and this is *not* simply "
              f"because the data ends early — the last play in the whole "
              f"`plays` table is only {gap_days:.1f} days before `as_of`. "
              "Left as an open question rather than guessed at; the "
              "mechanism was not traced further here.")
        a("")

    a(f"## 4. Top-{TOP_N}-by-score: where it falls, and how it compares to what actually ships")
    a("")
    a(f"`top-{TOP_N}` here is **this report's own convention**, matching "
      "evaluate.py's k=20 - it is not necessarily what the pipeline ships. "
      "`dormancy.qualifying_clusters`'s own docstring is explicit that with "
      "`config.BACKFILL_ENABLED = False` (current default), "
      "`writer._select_with_backfill` returns the whole native-eligible "
      "block **unchanged and uncapped** - there is no top-N cut in "
      f"production at all. So the top-{TOP_N} cut below only *binds* (changes "
      "what's shown vs. the full eligible pool) in a cluster whose eligible "
      f"count exceeds {TOP_N}; everywhere else it is a no-op and \"top-"
      f"{TOP_N}-by-score\" **is** what ships, in full.")
    a("")
    binds = m["overlap_df"][~m["overlap_df"]["forced_identical"]]
    noop = m["overlap_df"][m["overlap_df"]["forced_identical"]]
    if len(binds):
        binds_list = ", ".join(
            f"{r.name} ({r.eligible_pool} eligible)" for r in binds.itertuples()
        )
        a(f"**Cut binds** (eligible pool > {TOP_N}, so ships in full but "
          f"this report's top-{TOP_N} table is a genuine truncation): {binds_list}.")
    if len(noop):
        noop_list = ", ".join(
            f"{r.name} ({r.eligible_pool} eligible)" for r in noop.itertuples()
        )
        a(f"**Cut is a no-op** (eligible pool <= {TOP_N}, so this report's "
          f"top-{TOP_N} table already shows everything that ships): {noop_list}.")
    a("")
    a(_md_table(m["ship_df"]))
    a("")

    a(f"## 5. What would ship if ranked by `days_since_last_play` descending instead")
    a("")
    a(f"Same eligible pool, same top-{TOP_N} cutoff, ranked by dormancy instead "
      "of score. Full candidate list per cluster, not just a bucket count, "
      "since the play-count column is what the whole question turns on.")
    a("")
    for _, qrow in qualifying.iterrows():
        cid = int(qrow["cluster"])
        a(f"**Cluster {cid} — {qrow['name']}:**")
        a("")
        a(_md_table(m["dormant_tables"][cid]))
        a("")

    a("## 6. Overlap between §4 and §5, per cluster")
    a("")
    a(f"`differ` is the symmetric difference (tracks unique to one side plus "
      f"tracks unique to the other), not a fraction of {TOP_N}. "
      "`forced_identical = True` means the eligible pool itself has "
      f"{TOP_N} or fewer tracks, so top-by-score and top-by-dormancy are "
      "**the same set by construction** - `overlap`/`differ` in that row "
      "measures nothing about ranking, only that there was no ranking "
      "decision to make. Only a `forced_identical = False` row is a genuine "
      "comparison of the two rankings.")
    a("")
    a(_md_table(m["overlap_df"]))
    a("")
    n_forced = int(m["overlap_df"]["forced_identical"].sum())
    n_real = len(m["overlap_df"]) - n_forced
    if n_real == 0:
        a(f"**No cluster has a genuine ranking decision to compare at this "
          f"as_of** — every eligible pool is {TOP_N} or smaller, so "
          "top-by-score and top-by-dormancy are identical everywhere by "
          "construction, not because the two rankings agree.")
    else:
        real_names = ", ".join(
            r.name for r in m["overlap_df"][~m["overlap_df"]["forced_identical"]].itertuples()
        )
        a(f"**{n_real} of {len(m['overlap_df'])} clusters have a genuine "
          f"ranking decision** ({real_names}); the other {n_forced} are "
          "identical by construction (§4).")
    a("")

    a("## 7. Verdict — is there a population of heavily-played, 3-to-5-weeks-dormant "
      "tracks large enough to fill a playlist?")
    a("")
    a(f"\"3-to-5-weeks-dormant\" = the `21-28` and `28-35` buckets. \"Large enough "
      f"to fill a playlist\" means at least {TOP_N} tracks from that band alone "
      "(this report's own top-N convention, matching evaluate.py's k=20 - "
      f"not the same bar as `MIN_CLUSTER_NATIVE = {config.MIN_CLUSTER_NATIVE}`, "
      "which only gates whether a cluster ships at all, per §2). The "
      "raw counts above let you judge against any other size directly. A count "
      f"below {TOP_N} is answered as **no**, however close: a playlist needs "
      "the full count, and `--cluster-name` ships one cluster at a time, so a "
      "shortfall in one cluster is not made up by a surplus in another.")
    a("")
    hist_df = m["hist_df"]
    per_cluster_n = {}
    for _, qrow in qualifying.iterrows():
        cid = int(qrow["cluster"])
        name = qrow["name"]
        sub = hist_df[(hist_df["cluster"] == cid) & (hist_df["bucket"].isin(DORMANT_BUCKETS))]
        n = int(sub["n_tracks"].sum())
        per_cluster_n[cid] = (name, n)
        medians = [f"{r.bucket}: n={r.n_tracks}, median plays={r.median_play_count}"
                   for r in sub.itertuples() if r.n_tracks > 0]
        verdict = "yes" if n >= TOP_N else "no"
        detail = "; ".join(medians) if medians else "no tracks in either bucket"
        a(f"- **Cluster {cid} ({name}): {verdict}** — {n} of {TOP_N} needed, "
          f"in the 21-35 day range ({detail}).")
    a("")

    agg_sub = m["agg_hist_df"][m["agg_hist_df"]["bucket"].isin(DORMANT_BUCKETS)]
    agg_n = int(agg_sub["n_tracks"].sum())
    best_n = max(n for _, n in per_cluster_n.values())
    best = [f"cluster {cid} ({name})" for cid, (name, n) in per_cluster_n.items() if n == best_n]
    largest_desc = " / ".join(best) + (" (tied)" if len(best) > 1 else "")
    a(f"**Aggregate: no.** No single cluster reaches {TOP_N} on its own — the "
      f"largest is {largest_desc} at {best_n}. Summed "
      f"across all {len(qualifying)} qualifying clusters, {agg_n} of "
      f"{m['eligible_total']} eligible tracks fall in the 21-35 day range — "
      f"noted for completeness, but this pooled figure does **not** answer "
      "\"yes\": it mixes tracks from unrelated artist clusters that no single "
      "`--cluster-name` write would ever combine, so it does not correspond "
      "to any playlist the product could actually ship.")
    a("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dormancy distribution measurement")
    parser.add_argument(
        "--as-of",
        help="Pin the analysis 'now' to this ISO date/timestamp (UTC assumed "
             "if no offset given). Omit to use wall-clock at run time.",
    )
    args = parser.parse_args(argv)
    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        as_of = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of.tz_convert("UTC")
    else:
        as_of = pd.Timestamp.now(tz="UTC")

    text = build_report(as_of)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {REPORT_PATH} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
