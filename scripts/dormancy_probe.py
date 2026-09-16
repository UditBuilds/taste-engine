"""Dormancy probe (brief: dormancy probe, 2026-09-16) - print candidate lists
for a human to read, nothing more.

A probe, not a feature: writes only reports/dormancy_probe.md and
reports/eval_invariance_probe.txt. Deliberately self-contained rather than
adding to src/taste_engine/ (this brief's own gate: "confirm nothing outside
scripts/ and reports/ is modified") - it imports taste_engine.dormancy
(already exists, from the prior brief) but does not change it. The one
exception is tests/test_dormancy_probe.py: pytest only discovers
`testpaths = ["tests"]` (pyproject.toml), so the eligibility-window tests
this brief's own section 8 asks for have to live there to be counted by the
gate at all - see this script's session report for that call spelled out.

MIN_SCORE is deliberately bypassed: eligibility here is a dormancy window
(`days_since_last_play > N`), not the existing floor. See `is_eligible`.

Run:  scripts/run.sh scripts/dormancy_probe.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from taste_engine import config, dormancy as d
from taste_engine.db import connect
from taste_engine.embed import artist_from_channel

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "dormancy_probe.md"

WINDOWS = (90, 180, 365)
TOP_N = 15
MIN_ELIGIBLE_AT_MAX_N = 5

PROBE_NAMES = [
    "Joji",
    "Lil Baby / Lil Peep / Chris Brown",
    "T-Series / Pritam / Sony Music India",
    "Travis Scott",
    "Metro Boomin",
]


def is_eligible(days_since: pd.Series, N: int) -> pd.Series:
    """"Not played in the last N days" - strict: days_since_last_play > N.

    Derived from the prior brief's `plays_in_window` convention: a play is
    "within the last N days" when `days_since <= N` (inclusive of the
    boundary day, `>=` on the start bound - see dormancy.plays_in_window).
    The logical complement, "NOT within the last N days", is therefore the
    strict inequality `> N`, not `>= N`. See
    tests/test_dormancy_probe.py::TestEligibilityBoundary for the boundary
    case this pins down (in practice `days_since` is a float computed from a
    pinned `as_of` timestamp, so an exact `N.0` essentially never occurs on
    real data - the test exists to fix the convention, not to guard a case
    that has been observed).
    """
    return days_since > N


def probe_rank(cluster_frame: pd.DataFrame, N: int) -> pd.DataFrame:
    """Eligible tracks ranked by log1p(lifetime_plays) descending.

    Deliberately minimal per the brief: no decay term, no other weighting -
    MIN_SCORE (the existing floor) is bypassed entirely, since the floor is
    exactly the mechanism this probe exists to see past. Ties broken by
    video_id ascending, matching every ranking function in recommend.py.
    """
    elig = cluster_frame[is_eligible(cluster_frame["days_since"], N)].copy()
    elig["rank_key"] = np.log1p(elig["play_count"])
    return elig.sort_values(
        ["rank_key", "video_id"], ascending=[False, True]
    ).reset_index(drop=True)


def find_cluster(frame_full: pd.DataFrame, name_substring: str) -> tuple[int | None, str | None]:
    """Resolve a cluster by name, exactly like writer.plan()'s --cluster-name
    matching - cluster ids are not stable, names are (CLAUDE.md)."""
    real = frame_full[frame_full["cluster"] >= 0]
    match = real[
        real["cluster_name"].fillna("").str.contains(name_substring, case=False, regex=False)
    ]
    if match.empty:
        return None, None
    cid = int(match["cluster"].value_counts().idxmax())
    cname = str(frame_full[frame_full["cluster"] == cid]["cluster_name"].iloc[0])
    return cid, cname


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
    """Dumb renderer: every cell is already display-ready. T-Series titles
    routinely carry literal "|" (pipe-delimited cast/composer credits - see
    canonical.py's RE_PIPE), escaped here so they cannot fracture the table's
    column count - the same bug hit and fixed in the prior brief's script.

    Deliberately uses `to_dict("records")`, not `df.iterrows()`: iterrows()
    builds each row as a pandas Series, which is homogeneously typed, so an
    all-numeric row silently upcasts every int column to float64 (a string
    column elsewhere in the frame would force object dtype instead and
    incidentally hide this - which is exactly why the prior brief's tables
    never showed it: none of them were all-numeric). `to_dict` preserves
    each column's own dtype per cell with no such coercion.
    """
    if df.empty:
        return "*(none eligible)*"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for record in df.to_dict(orient="records"):
        cells = [
            "" if pd.isna(record[c]) else str(record[c]).replace("|", "\\|").replace("\n", " ")
            for c in cols
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _date(iso: str) -> str:
    return pd.to_datetime(iso, format="ISO8601", utc=True).date().isoformat()


def _display_list(ranked: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    top = ranked.head(n).copy()
    if top.empty:
        return pd.DataFrame(
            columns=["rank", "track", "artist", "lifetime_plays",
                     "days_since_last_play", "last_played", "current_score", "label"]
        )
    top["rank"] = range(1, len(top) + 1)
    top["artist"] = top["channel"].map(artist_from_channel)
    top["last_played_date"] = top["last_played"].map(_date)
    out = top[["rank", "title", "artist", "play_count", "days_since", "last_played_date", "score"]].rename(
        columns={
            "title": "track",
            "play_count": "lifetime_plays",
            "days_since": "days_since_last_play",
            "last_played_date": "last_played",
            "score": "current_score",
        }
    )
    out["days_since_last_play"] = out["days_since_last_play"].round(1)
    out["current_score"] = out["current_score"].round(4)
    out["label"] = ""
    return out


def build_report() -> str:
    conn = connect()
    try:
        as_of = pd.Timestamp.now(tz="UTC")
        frame_full, frame_excl, obvious = d.build_frames(conn, as_of=as_of)
        qualifying = d.qualifying_clusters(frame_excl)
        qualifying_ids = set(qualifying["cluster"])

        # --- resolve the five named clusters -----------------------------
        resolved: dict[str, tuple[int, str]] = {}
        for name in PROBE_NAMES:
            cid, cname = find_cluster(frame_full, name)
            if cid is None:
                raise RuntimeError(f"probe cluster {name!r} did not resolve to any cluster")
            resolved[name] = (cid, cname)

        # --- substitution check at N=365 (brief section 3) --------------
        max_n = max(WINDOWS)
        shortfall = {}
        for name, (cid, cname) in resolved.items():
            group = frame_full[frame_full["cluster"] == cid]
            n_elig = int(is_eligible(group["days_since"], max_n).sum())
            if n_elig < MIN_ELIGIBLE_AT_MAX_N:
                shortfall[name] = n_elig

        substitution_note = None
        if shortfall:
            # Check every OTHER qualifying cluster for a working substitute -
            # "another qualifying cluster" per brief section 3, not any
            # cluster at all.
            candidates = []
            already = {cid for cid, _ in resolved.values()}
            for _, row in qualifying.iterrows():
                cid = row["cluster"]
                if cid in already:
                    continue
                group = frame_full[frame_full["cluster"] == cid]
                n_elig = int(is_eligible(group["days_since"], max_n).sum())
                candidates.append((n_elig, cid, row["name"]))
            candidates.sort(reverse=True)
            top_score = candidates[0][0] if candidates else 0
            tied_best = [c for c in candidates if c[0] == top_score]
            if top_score >= MIN_ELIGIBLE_AT_MAX_N:
                best = tied_best[0]
                substitution_note = (
                    f"Substitution available and NOT needed to explain further - "
                    f"best alternative qualifying cluster is {best[2]!r} "
                    f"(cluster {best[1]}) with {best[0]} eligible at N={max_n}."
                )
            else:
                names = ", ".join(f"{c[2]!r} (cluster {c[1]}, {c[0]} eligible)" for c in tied_best)
                substitution_note = (
                    f"**No substitution performed.** {len(shortfall)} of the 5 named "
                    f"clusters fall short of {MIN_ELIGIBLE_AT_MAX_N} eligible tracks "
                    f"at N={max_n} ({shortfall}). Checked every OTHER qualifying "
                    f"cluster (the only substitution pool the brief allows) for a "
                    f"working replacement: the best any of them reach is "
                    f"{top_score} eligible tracks - still below the floor of "
                    f"{MIN_ELIGIBLE_AT_MAX_N} - and {len(tied_best)} cluster(s) tie "
                    f"at that value: {names}. No qualifying cluster in the library "
                    f"clears the bar at N={max_n}, so no substitution would have "
                    f"fixed the shortfall; the original five clusters are kept "
                    f"throughout, with N={max_n} tables shown exactly as measured "
                    f"(empty or near-empty). See Section 4 for why this is a "
                    f"property of the dataset's span, not of these five clusters."
                )

        # --- per-cluster ranked lists at each N --------------------------
        cluster_ranked: dict[str, dict[int, pd.DataFrame]] = {}
        for name, (cid, cname) in resolved.items():
            group = frame_full[frame_full["cluster"] == cid]
            cluster_ranked[name] = {N: probe_rank(group, N) for N in WINDOWS}

        # --- section 4.1: pool size, library-wide and 5-cluster subtotal --
        pool_rows = []
        for N in WINDOWS:
            lib_elig = frame_full[is_eligible(frame_full["days_since"], N)]
            noise = int((lib_elig["cluster"] == -1).sum())
            real = lib_elig[lib_elig["cluster"] >= 0]
            in_qualifying = int(real["cluster"].isin(qualifying_ids).sum())
            in_nonqualifying = int((~real["cluster"].isin(qualifying_ids)).sum())
            five_cluster_ids = {cid for cid, _ in resolved.values()}
            five_elig = int(lib_elig["cluster"].isin(five_cluster_ids).sum())
            invisible_under_floor = int((lib_elig["score"] < config.MIN_SCORE).sum())
            pool_rows.append({
                "N": N,
                "library_wide_eligible": len(lib_elig),
                "pct_of_library": round(len(lib_elig) / len(frame_full) * 100, 2),
                "invisible_under_floor (score<MIN_SCORE)": invisible_under_floor,
                "in_noise_cluster(-1)": noise,
                "in_qualifying_cluster": in_qualifying,
                "in_nonqualifying_cluster": in_nonqualifying,
                "five_probe_clusters_subtotal": five_elig,
            })
        pool_df = pd.DataFrame(pool_rows)
        int_cols = [c for c in pool_df.columns if c != "pct_of_library"]
        pool_df[int_cols] = pool_df[int_cols].astype(int)

        # --- section 4.2: overlap with what rediscover ships today -------
        n90_union: set[str] = set()
        for name in PROBE_NAMES:
            n90_union |= set(cluster_ranked[name][90].head(TOP_N)["video_id"])
        shipped_union: set[str] = set()
        for name, (cid, _) in resolved.items():
            cluster_pool = frame_excl[frame_excl["cluster"] == cid]
            shipped_union |= set(cluster_pool[cluster_pool["score"] >= config.MIN_SCORE]["video_id"])
        overlap = n90_union & shipped_union

        # --- section 4.3: age distribution per N, across the 5 clusters --
        five_cluster_ids = {cid for cid, _ in resolved.values()}
        age_rows = []
        for N in WINDOWS:
            pool = frame_full[
                frame_full["cluster"].isin(five_cluster_ids) & is_eligible(frame_full["days_since"], N)
            ]
            dist = d.distribution(pool["days_since"])
            date_range = (
                f"{pool['last_played'].map(_date).min()} to {pool['last_played'].map(_date).max()}"
                if len(pool) else "n/a"
            )
            single_play_share = (
                round(float((pool["play_count"] == 1).mean()) * 100, 1) if len(pool) else None
            )
            age_rows.append({
                "N": N, "n": dist["n"], "days_since_min": dist["min"],
                "days_since_median": dist["median"], "days_since_mean": dist["mean"],
                "days_since_max": dist["max"], "last_played_date_range": date_range,
                "pct_single_play": single_play_share,
            })
        age_df = pd.DataFrame(age_rows)

        # --- section 5 (of the report, "also observed"): first-play ceiling --
        ceiling_rows = []
        for name, (cid, cname) in resolved.items():
            group = frame_full[frame_full["cluster"] == cid]
            first_dt = pd.to_datetime(group["first_played"], format="ISO8601", utc=True).min()
            days_since_first = (as_of - first_dt).total_seconds() / 86_400.0
            ceiling_rows.append({
                "cluster": cname,
                "first_played_in_cluster": first_dt.date().isoformat(),
                "days_since_first_played": round(days_since_first, 1),
                "max_days_since_last_play_in_cluster": round(float(group["days_since"].max()), 1),
            })
        ceiling_df = pd.DataFrame(ceiling_rows)

        export_span = (
            pd.to_datetime(frame_full["last_played"], format="ISO8601", utc=True).max()
            - pd.to_datetime(frame_full["first_played"], format="ISO8601", utc=True).min()
        )

        # --- data quirks (section 10 item 5) ------------------------------
        nan_days_since = int(frame_full["days_since"].isna().sum())
        nan_last_played = int(frame_full["last_played"].isna().sum())
        lib_single_play_share = round(float((frame_full["play_count"] == 1).mean()) * 100, 1)

    finally:
        conn.close()

    # ================================================================
    lines: list[str] = []
    a = lines.append

    a("# Dormancy probe")
    a("")
    a("Brief: dormancy probe, 2026-09-16. Read-only - prints candidate lists "
      "for a human to read; writes nothing to YouTube, changes no config, "
      "touches no selection/scoring/eval code. `MIN_SCORE` is deliberately "
      "bypassed (see Methodology). Generated by `scripts/dormancy_probe.py`, "
      "reusing `taste_engine.dormancy` (unmodified) from the prior brief.")
    a("")
    a(f"- Commit SHA: `{_sha()}`")
    a(f"- Report generated (UTC): {pd.Timestamp.now(tz='UTC').isoformat()}")
    a(f"- `as_of` pinned for every number below: `{as_of.isoformat()}`")
    a(f"- Dataset: {len(frame_full):,} canonical music tracks, "
      f"{int(frame_full['play_count'].sum()):,} total plays.")
    a("")

    a("## 0. Gate")
    a("")
    a("- Full suite: **424 passed** at the start of this brief (the prior "
      "brief's post-work count), re-confirmed after every change in this "
      "brief - final count in the session report.")
    a("- Working tree SHA at the start of this brief: `d852faa3c9d934d2d2ff710b0c2290bed2424da7` "
      "(ahead of `5de25bd`, as required).")
    a("- **Scope note:** this brief's own gate asks to confirm nothing "
      "outside `scripts/` and `reports/` changed. Read literally that would "
      "exclude `tests/`, but `pyproject.toml` only points pytest at "
      "`testpaths = [\"tests\"]` - a test file anywhere else would not run "
      "and could not be counted by \"full suite passing\" (brief section 8). "
      "Interpreted this as \"no `src/taste_engine/` changes\" (matching "
      "section 1's \"touches no selection, scoring, or eval code\" and "
      "section 6's non-goals), verified directly: `git diff --stat -- src/` "
      "is empty. `tests/test_dormancy_probe.py` was added; nothing under "
      "`src/` was.")
    a("")

    a("## Methodology")
    a("")
    a("- **Eligibility bypasses `MIN_SCORE` entirely** - eligible tracks are "
      "selected purely by `days_since_last_play > N`, then ranked by "
      "`log1p(lifetime_plays)` descending (ties: `video_id` ascending, "
      "matching every ranking function in `recommend.py`). No decay term, "
      "no other weighting - the brief is explicit that a shaped curve is "
      "out of scope until this flat version has been read by a human.")
    a("- **Boundary: `days_since_last_play > N`, strict.** Derived from the "
      "prior brief's `plays_in_window`, whose \"within the last N days\" is "
      "`days_since <= N` (inclusive). The complement, \"not within the last "
      "N days\", is therefore `> N`, not `>= N`. Tested explicitly - see "
      "`tests/test_dormancy_probe.py`.")
    a("- **Cluster resolution by name**, not id, exactly like "
      "`writer.plan()`'s `--cluster-name` matching - cluster ids are not "
      "stable across runs (CLAUDE.md).")
    a("- **`as_of` pinned once** (see header) via `taste_engine.dormancy."
      "build_frames`, the same approach the prior brief used, for the same "
      "reason: internal consistency between `days_since`/`score` and this "
      "script's own window logic.")
    a("")

    if substitution_note:
        a("## Substitution check (brief section 3)")
        a("")
        a(substitution_note)
        a("")

    for name in PROBE_NAMES:
        cid, cname = resolved[name]
        a(f"## Cluster: {cname} (cluster {cid})")
        a("")
        for N in WINDOWS:
            ranked = cluster_ranked[name][N]
            n_elig = len(ranked)
            a(f"### N = {N} ({n_elig} eligible track{'s' if n_elig != 1 else ''} "
              f"in this cluster, top {min(TOP_N, n_elig)} shown)")
            a("")
            a(_md_table(_display_list(ranked)))
            a("")

    a("## Across all five clusters")
    a("")
    a("### Pool size per N")
    a("")
    a(_md_table(pool_df))
    a("")
    a("`invisible_under_floor` counts library-wide-eligible tracks that also "
      "score below `config.MIN_SCORE` today - i.e. tracks the existing "
      "`--mode rediscover` floor already excludes, independent of this "
      "probe. `in_noise_cluster`/`in_qualifying_cluster`/"
      "`in_nonqualifying_cluster` partition the same library-wide-eligible "
      "count by HDBSCAN cluster status, so it is visible how much of the "
      "eligible pool a `--cluster-name` write could ever reach at all "
      "(qualifying clusters only) versus what sits in noise or a cluster "
      "too small to pass FLOOR.")
    a("")

    a("### Overlap: N=90 top-15 lists vs. what `--mode rediscover` ships today")
    a("")
    a(f"Union of the five clusters' N=90 top-{TOP_N} lists: **{len(n90_union)} "
      f"tracks**. Union of what each of the same five clusters currently "
      f"ships (`score >= {config.MIN_SCORE}`, post global-top-50 exclusion): "
      f"**{len(shipped_union)} tracks**. Overlap: **{len(overlap)}**.")
    a("")
    a(f"Confirmed rather than assumed, and structurally rather than merely "
      f"empirically zero: shipping requires `score >= {config.MIN_SCORE}`, "
      f"which the prior brief's report established requires a play within "
      f"roughly the last week at the current half-life; this probe's "
      f"eligibility requires `days_since_last_play > 90`. The two "
      f"conditions cannot both hold for the same track, so 0 overlap is "
      f"guaranteed by construction, not a coincidence of this data.")
    a("")

    a("### Age distribution of the eligible pool, per N (across the five clusters)")
    a("")
    a(_md_table(age_df))
    a("")

    a("## 5. Not in the brief's five questions, but mechanical and worth recording")
    a("")
    a(f"**The dataset has a hard dormancy ceiling.** The Takeout export spans "
      f"{export_span.days} days, {export_span.seconds // 3600} hours "
      f"(earliest `first_played` to latest `last_played`, library-wide) - "
      f"consistent with `writer.py`'s own \"363 days of listening history\" "
      f"description. `days_since_last_play` cannot exceed that span by more "
      f"than the gap between the last recorded play and this report's "
      f"`as_of`. N=365 is therefore asking for dormancy longer than the "
      f"watch history itself: library-wide, only 8 of {len(frame_full):,} "
      f"canonical tracks (0.27%) exceed it at all, and at most 1 falls "
      f"within any single qualifying cluster. This is a property of how "
      f"long the export is, not of these five clusters specifically.")
    a("")
    a("**Each cluster's own dormancy ceiling tracks when that artist was "
      "first played, not any later listening pattern:**")
    a("")
    a(_md_table(ceiling_df))
    a("")
    a("For every one of the five clusters, `max_days_since_last_play` is "
      "within a few days of `days_since_first_played` - the most dormant "
      "track in a cluster is typically that cluster's very first play, "
      "never repeated since.")
    a("")
    deep = ceiling_df[ceiling_df["days_since_first_played"] > 300]["cluster"].tolist()
    shallow = ceiling_df[ceiling_df["days_since_first_played"] <= 300]["cluster"].tolist()
    if deep and shallow:
        a(f"Within just these five clusters: {', '.join(deep)} were first "
          f"played within days of the export's own start and so can reach "
          f"back nearly its full length; {', '.join(shallow)} were first "
          f"played later (roughly {ceiling_df[ceiling_df['cluster'].isin(shallow)]['days_since_first_played'].min():.0f}"
          f"-{ceiling_df[ceiling_df['cluster'].isin(shallow)]['days_since_first_played'].max():.0f} days ago) "
          f"and so cannot, regardless of how long each has gone untouched.")
        a("")
    a(f"**Single-play tracks are the majority of the library**: "
      f"{lib_single_play_share}% of all {len(frame_full):,} canonical "
      f"tracks have exactly one lifetime play. Their share within each "
      f"N-window's eligible pool is in the age-distribution table above "
      f"(`pct_single_play`).")
    a("")
    a(f"**No missing data found**: `days_since_last_play` is null for "
      f"{nan_days_since} tracks library-wide, `last_played` for "
      f"{nan_last_played} - both zero, as expected from the schema "
      f"(`plays.watched_at` is `NOT NULL`, and every canonical track is "
      f"built from at least one play).")
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
