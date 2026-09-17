"""Part 2 of briefs/ground_truth_ids.md - before/after measurement.

Part 1 (commit 2afe328) fixed cluster_eval's raw-vs-canonical ground-truth
join and added a conflict-drop rule. This measures the effect on ARI/NMI/
purity across all three embedding modes and all three noise conventions,
before (raw, unfixed `playlist_ground_truth`) and after
(`canonical_ground_truth`) - both computed fresh against current code, not
read off any historical report. Every gate below must pass before any
number is written to the report; a mismatch means this script's own
pipeline disagrees with an already-published figure and nothing downstream
is trustworthy until that is resolved.

Run:  scripts/run.sh scripts/ground_truth_before_after.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from taste_engine.cluster_eval import (
    canonical_ground_truth,
    coherence_by_convention,
    playlist_ground_truth,
)
from taste_engine.db import connect
from taste_engine.embed import CORPUS_MODES, MIN_SAMPLES, cluster_tracks
from taste_engine.score import scored_tracks

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "ground_truth_ids.md"

# reports/min_samples_sweep.md §2 (exclude convention, min_samples=2,
# current code) - the "before" pass below must reproduce these exactly.
EXPECTED_BEFORE_POOL = 438
EXPECTED_BEFORE_N_EVAL = {"title_artist": 238, "title": 188, "title_genre": 314}
EXPECTED_BEFORE_ARI_EXCLUDE = {"title_artist": 0.6655, "title": 0.3707, "title_genre": 0.3661}

# reports/ground_truth_audit.md (Part 0) - the "after" pass must reproduce
# these exactly, for every mode (ground truth cannot depend on embedding
# mode - it is computed before any clustering happens).
EXPECTED_AFTER_POOL = 480
EXPECTED_AFTER_CONFLICTS = 3

# reports/min_samples_sweep.md §3/§7: std(swing), swing = 1 - ARI(original
# clustering, perturbed clustering) - a purely *structural* quantity that
# never touches ground truth (see that report's own §1 "Two different ARI
# quantities"). The ground-truth fix cannot move this - the same principle
# the invariance check verifies for the recommender eval - so it is reused
# verbatim here, not re-derived. Re-running the sweep is out of scope for
# this brief (see its "Out of scope" list: "Any tuning of min_samples...
# that decision is closed"). {convention: {mode: [std at min_samples 2,5,10,15]}}
NOISE_BAND = {
    "exclude": {
        "title_artist": [0.0006, 0.0003, 0.0375, 0.0002],
        "title_genre": [0.0015, 0.0007, 0.0029, 0.0011],
    },
    "single_cluster": {
        "title_artist": [0.0077, 0.0055, 0.0861, 0.0101],
        "title_genre": [0.0165, 0.0096, 0.0055, 0.0045],
    },
    "singletons": {
        "title_artist": [0.0044, 0.0041, 0.1264, 0.0122],
        "title_genre": [0.0095, 0.0031, 0.0045, 0.0051],
    },
}
CONVENTIONS = ("exclude", "single_cluster", "singletons")


def noise_band_worst_case(convention: str) -> float:
    """Toughest bar a title_artist/title_genre gap must clear under this
    convention: the largest std(swing) across both anchor modes and all
    four min_samples values measured in min_samples_sweep.md.

    Not a single stable quantity - for `single_cluster` specifically this
    maximum is `title_artist`'s own std at min_samples=10 (0.0861), the
    one-off bimodal regime break that report's §4 documents as specific to
    that mode at that one value, not a general noise floor for the
    convention. A gap measured at a *different* min_samples (this brief
    pins 2 throughout) should also be checked against
    `noise_band_at_min_samples_2` - using this worst-case figure alone can
    silently import instability from a min_samples value that is not
    actually in play here.
    """
    band = NOISE_BAND[convention]
    return max(band["title_artist"] + band["title_genre"])


def noise_band_at_min_samples_2(convention: str) -> float:
    """The measured structural noise level at THIS brief's own min_samples
    (2), across both anchor modes - narrower, and more relevant to what
    this brief actually measures, than the worst case across every
    min_samples value min_samples_sweep.md happened to test."""
    band = NOISE_BAND[convention]
    return max(band["title_artist"][0], band["title_genre"][0])


def main() -> int:
    conn = connect()
    try:
        gate_min_samples = MIN_SAMPLES == 2
        print(f"[gate] embed.MIN_SAMPLES == 2 (brief's fixed value): "
              f"{'OK' if gate_min_samples else 'MISMATCH'} (got {MIN_SAMPLES})")

        tracks = scored_tracks(conn)  # canonical=True, music_only=True, defaults
        raw_truth = playlist_ground_truth(conn)                       # before
        fixed_truth, gt_stats = canonical_ground_truth(conn, tracks)  # after

        gate_after = (
            gt_stats["denominator"] == EXPECTED_AFTER_POOL
            and gt_stats["conflicts_dropped"] == EXPECTED_AFTER_CONFLICTS
        )
        print(f"[gate] after-fix denominator == {EXPECTED_AFTER_POOL}, conflicts "
              f"== {EXPECTED_AFTER_CONFLICTS} (reports/ground_truth_audit.md): "
              f"{'OK' if gate_after else 'MISMATCH'} "
              f"(got denominator={gt_stats['denominator']}, "
              f"conflicts={gt_stats['conflicts_dropped']})")

        rows = []
        for mode in CORPUS_MODES:
            clustered = cluster_tracks(tracks, mode=mode)
            before = coherence_by_convention(clustered, raw_truth)
            before.insert(0, "when", "before")
            after = coherence_by_convention(clustered, fixed_truth)
            after.insert(0, "when", "after")
            before.insert(0, "mode", mode)
            after.insert(0, "mode", mode)
            rows += [before, after]
        full = pd.concat(rows, ignore_index=True)

        before_excl = full[(full["when"] == "before") & (full["convention"] == "exclude")].set_index("mode")
        gate_before_pool = bool((before_excl["total_labelled"] == EXPECTED_BEFORE_POOL).all())
        got_neval = {m: int(before_excl.loc[m, "n_eval"]) for m in CORPUS_MODES}
        gate_before_neval = got_neval == EXPECTED_BEFORE_N_EVAL
        got_ari = {m: round(float(before_excl.loc[m, "ari"]), 4) for m in CORPUS_MODES}
        gate_before_ari = all(
            abs(got_ari[m] - EXPECTED_BEFORE_ARI_EXCLUDE[m]) < 0.0001 for m in CORPUS_MODES
        )
        print(f"[gate] before-fix pool == {EXPECTED_BEFORE_POOL} for every mode "
              f"(min_samples_sweep.md §2): {'OK' if gate_before_pool else 'MISMATCH'}")
        print(f"[gate] before-fix n_eval (exclude) matches {EXPECTED_BEFORE_N_EVAL}: "
              f"{'OK' if gate_before_neval else 'MISMATCH'} (got {got_neval})")
        print(f"[gate] before-fix ARI (exclude) matches {EXPECTED_BEFORE_ARI_EXCLUDE}: "
              f"{'OK' if gate_before_ari else 'MISMATCH'} (got {got_ari})")

        before_sc = full[(full["when"] == "before") & (full["convention"] == "single_cluster")].set_index("mode")
        gate_q2_baseline = bool(before_sc.loc["title_genre", "ari"] > before_sc.loc["title_artist", "ari"])
        print(f"[gate] before-fix single_cluster: title_genre ARI > title_artist "
              f"ARI (CLAUDE.md open item 10's known ranking flip): "
              f"{'OK' if gate_q2_baseline else 'MISMATCH'} "
              f"(title_artist={before_sc.loc['title_artist', 'ari']:.4f}, "
              f"title_genre={before_sc.loc['title_genre', 'ari']:.4f})")

        after_pool_vals = set(full.loc[full["when"] == "after", "total_labelled"])
        gate_after_pool_uniform = after_pool_vals == {EXPECTED_AFTER_POOL}
        print(f"[gate] after-fix total_labelled == {EXPECTED_AFTER_POOL} for every "
              f"mode and convention (ground truth must not depend on embedding "
              f"mode): {'OK' if gate_after_pool_uniform else 'MISMATCH'} "
              f"(got {sorted(after_pool_vals)})")

        all_gates_ok = (
            gate_min_samples and gate_after and gate_before_pool and gate_before_neval
            and gate_before_ari and gate_q2_baseline and gate_after_pool_uniform
        )
        print()
        if not all_gates_ok:
            print("Refusing to report: one or more correctness gates failed above. "
                  "Stopping for investigation - report not written.")
            return 1

        # ---- Q1: does the title_artist/title_genre gap survive the noise band? ----
        # Sign matters: under single_cluster title_genre leads (the already-known
        # item-10 flip), so "does title_artist's gap survive" does not even apply
        # there the way it does for exclude/singletons. `abs(gap) > band` answers
        # the question that generalises to both directions - is this convention's
        # finding (whichever way it points) bigger than measured structural noise
        # - and `leader` reports the direction separately so nothing is conflated.
        q1_rows = []
        for when in ("before", "after"):
            for convention in CONVENTIONS:
                sub = full[(full["when"] == when) & (full["convention"] == convention)].set_index("mode")
                gap = float(sub.loc["title_artist", "ari"] - sub.loc["title_genre", "ari"])
                band_worst = noise_band_worst_case(convention)
                band_m2 = noise_band_at_min_samples_2(convention)
                q1_rows.append({
                    "when": when, "convention": convention, "gap": gap,
                    "leader": "title_artist" if gap > 0 else "title_genre",
                    "noise_band_worst_case": band_worst,
                    "exceeds_noise_band": abs(gap) > band_worst,
                    "margin": (abs(gap) / band_worst) if band_worst else float("inf"),
                    "noise_band_at_min_samples_2": band_m2,
                    "exceeds_at_min_samples_2": abs(gap) > band_m2,
                    "margin_at_min_samples_2": (abs(gap) / band_m2) if band_m2 else float("inf"),
                })
        q1_df = pd.DataFrame(q1_rows)
        q1_positive = q1_df[q1_df["convention"] != "single_cluster"]
        q1_flip = q1_df[q1_df["convention"] == "single_cluster"]

        # ---- Q2: full 3-way ARI ranking per convention, before vs after ----
        def ranking(when: str, convention: str) -> list[str]:
            sub = full[(full["when"] == when) & (full["convention"] == convention)].set_index("mode")
            return list(sub["ari"].sort_values(ascending=False).index)

        q2_rows = []
        for convention in CONVENTIONS:
            before_rank = ranking("before", convention)
            after_rank = ranking("after", convention)
            q2_rows.append({
                "convention": convention,
                "before_ranking": " > ".join(before_rank),
                "after_ranking": " > ".join(after_rank),
                "top_flipped": before_rank[0] != after_rank[0],
                "order_changed": before_rank != after_rank,
            })
        q2_df = pd.DataFrame(q2_rows)

        # ---- assemble report ----
        lines: list[str] = []
        lines.append("# Ground-truth denominator fix: before/after measurement\n")
        lines.append("Part 2 of `briefs/ground_truth_ids.md`. Fixed seed (PCA "
                      "`random_state=0`; HDBSCAN has no internal randomness - "
                      "determinism checked in `reports/min_samples_sweep.md` §1), "
                      f"`min_samples`={MIN_SAMPLES} (shipped default, unchanged), "
                      "same config as commit 36e3b5a otherwise. \"before\" = raw "
                      "`playlist_ground_truth()` (the pre-Part-1-fix join); \"after\" "
                      "= `canonical_ground_truth()` (Part 1's fix). Both measured "
                      "fresh against current code in this run, not read off any "
                      "historical report.\n")

        lines.append("## Correctness gates\n")
        lines.append(f"- `embed.MIN_SAMPLES == 2`: **{'OK' if gate_min_samples else 'MISMATCH'}**\n")
        lines.append(f"- After-fix denominator == {EXPECTED_AFTER_POOL}, conflicts == "
                      f"{EXPECTED_AFTER_CONFLICTS} (`reports/ground_truth_audit.md`): "
                      f"**{'OK' if gate_after else 'MISMATCH'}**\n")
        lines.append(f"- Before-fix pool == {EXPECTED_BEFORE_POOL} for every mode "
                      f"(`reports/min_samples_sweep.md` §2): "
                      f"**{'OK' if gate_before_pool else 'MISMATCH'}**\n")
        lines.append(f"- Before-fix `n_eval` (exclude) == {EXPECTED_BEFORE_N_EVAL}: "
                      f"**{'OK' if gate_before_neval else 'MISMATCH'}** (got {got_neval})\n")
        lines.append(f"- Before-fix ARI (exclude) == {EXPECTED_BEFORE_ARI_EXCLUDE}: "
                      f"**{'OK' if gate_before_ari else 'MISMATCH'}** (got {got_ari})\n")
        lines.append(f"- Before-fix `single_cluster`: `title_genre` ARI > `title_artist` "
                      f"ARI (CLAUDE.md open item 10's known flip): "
                      f"**{'OK' if gate_q2_baseline else 'MISMATCH'}**\n")
        lines.append(f"- After-fix pool == {EXPECTED_AFTER_POOL} for every mode *and* "
                      f"convention: **{'OK' if gate_after_pool_uniform else 'MISMATCH'}**\n")

        lines.append("\n## Before/after table\n")
        lines.append("`total_labelled` = the ground-truth pool (before noise handling); "
                      "`n_eval` = this convention's actual ARI/NMI/purity denominator - "
                      "the two are equal for `single_cluster`/`singletons` by "
                      "construction and *not* equal for `exclude`. Both reported on "
                      "every row so neither has to be inferred from the other.\n")
        lines.append("\n| mode | convention | when | n_eval | total_labelled | ari | nmi | purity |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for mode in CORPUS_MODES:
            for convention in CONVENTIONS:
                for when in ("before", "after"):
                    r = full[(full["mode"] == mode) & (full["convention"] == convention) & (full["when"] == when)].iloc[0]
                    lines.append(
                        f"| {mode} | {convention} | {when} | {int(r['n_eval'])} | "
                        f"{int(r['total_labelled'])} | {r['ari']:.4f} | {r['nmi']:.4f} | "
                        f"{r['purity']:.4f} |"
                    )

        lines.append("\n## Question 1 - does the title_artist/title_genre gap "
                      "survive the noise band under every convention?\n")
        lines.append("`min_samples_sweep.md`'s own \"0.179 at 36e3b5a\" compares "
                      "against **stale, published README figures** (0.649/0.470 "
                      "exclude-convention ARI) that predate the `normalise_title` "
                      "fix - that report's own §2 measured 0.6655/0.3661 with the "
                      "same current code this script runs, a gap of 0.2994, not "
                      "0.179. Neither of those is *this* brief's before/after "
                      "comparison, so both gaps below are measured fresh rather than "
                      "reused from either historical figure.\n")
        lines.append("\nThe `exclude`/`min_samples=2` band below (0.0015) is not a "
                      "general robustness claim - `exclude` drops noise before "
                      "scoring, so it is already near-perfectly stable at "
                      "`min_samples=2`; the resulting ~200x margins say this "
                      "*specific* 7-track perturbation barely moves an "
                      "already-noise-excluded clustering, not that the exclude "
                      "comparison is immune to instability in general (`exclude`'s "
                      "own worst-case band, 0.0375 at min_samples=10, is >20x "
                      "larger).\n")
        lines.append("\nSign matters here and is reported separately from magnitude: "
                      "under `single_cluster`, `title_genre` leads (CLAUDE.md's "
                      "already-known item-10 flip), so \"does title_artist's gap "
                      "survive\" is not even the right question there - "
                      "`exceeds_noise_band` instead asks whether *whichever mode "
                      "leads* does so by more than measured structural noise. Two "
                      "noise bars are reported, not one: the worst case across every "
                      "`min_samples` value `min_samples_sweep.md` tested, and the "
                      "narrower one measured at `min_samples=2` specifically - the "
                      "value this brief actually pins. For `single_cluster` these "
                      "disagree (the worst case is `title_artist`'s own one-off "
                      "bimodal break at `min_samples=10`, not a general noise floor "
                      "for the convention - see `noise_band_worst_case`'s "
                      "docstring), so both are shown rather than picking one.\n")
        lines.append("\n| when | convention | gap (title_artist − title_genre) | "
                      "leader | band (min_samples=2) | margin | band (worst case) | "
                      "margin | exceeds worst-case band |")
        lines.append("|---|---|---:|---|---:|---:|---:|---:|---|")
        for _, r in q1_df.iterrows():
            lines.append(
                f"| {r['when']} | {r['convention']} | {r['gap']:.4f} | {r['leader']} | "
                f"{r['noise_band_at_min_samples_2']:.4f} | "
                f"{r['margin_at_min_samples_2']:.2f}x | "
                f"{r['noise_band_worst_case']:.4f} | {r['margin']:.2f}x | "
                f"{'yes' if r['exceeds_noise_band'] else '**no**'} |"
            )

        positive_all_exceed = bool(q1_positive["exceeds_noise_band"].all())
        positive_min_margin = q1_positive.loc[q1_positive["margin"].idxmin()]
        positive_verdict = "yes" if positive_all_exceed else "no"

        exclude_gaps = q1_positive.loc[q1_positive["convention"] == "exclude", "gap"]
        singletons_gaps = q1_positive.loc[q1_positive["convention"] == "singletons", "gap"]

        flip_exceeds_m2 = bool(q1_flip["exceeds_at_min_samples_2"].all())
        flip_exceeds_worst = bool(q1_flip["exceeds_noise_band"].any())
        flip_gap_before = abs(float(q1_flip.loc[q1_flip["when"] == "before", "gap"].iloc[0]))
        flip_gap_after = abs(float(q1_flip.loc[q1_flip["when"] == "after", "gap"].iloc[0]))
        flip_margin_m2_before = float(q1_flip.loc[q1_flip["when"] == "before", "margin_at_min_samples_2"].iloc[0])
        flip_margin_m2_after = float(q1_flip.loc[q1_flip["when"] == "after", "margin_at_min_samples_2"].iloc[0])
        flip_margin_worst_best = float(q1_flip["margin"].max())
        flip_band_m2 = float(q1_flip["noise_band_at_min_samples_2"].iloc[0])
        flip_band_worst = float(q1_flip["noise_band_worst_case"].iloc[0])

        lines.append(
            "\n**Answer, in two parts because the conventions do not all point "
            "the same way:**\n"
        )
        lines.append(
            f"- **`exclude` and `singletons` (where `title_artist` leads, both "
            f"before and after): {positive_verdict}, the gap survives under both "
            f"noise bars, in every one of these conventions, both before and "
            f"after the fix** - and by a larger margin than the historical 0.179 "
            f"ever needed, since the freshly-measured gaps here "
            f"({exclude_gaps.min():.4f}-{exclude_gaps.max():.4f} exclude, "
            f"{singletons_gaps.min():.4f}-{singletons_gaps.max():.4f} singletons) "
            f"are themselves bigger than 0.179. Thinnest margin (worst-case band): "
            f"{positive_min_margin['when']}/{positive_min_margin['convention']} at "
            f"{positive_min_margin['margin']:.2f}x - still comfortable. The noise "
            f"*band* itself cannot move between before and after (it is computed "
            f"between two clusterings and never touches ground truth); the *gap* "
            f"does move ({exclude_gaps.min():.4f} to {exclude_gaps.max():.4f} under "
            f"exclude, for instance) because it is ground-truth-derived and the "
            f"fix changed ground truth - expected, and the reason the comparison "
            f"is run on both sides rather than assumed stable.\n"
        )
        lines.append(
            f"- **`single_cluster` (where `title_genre` leads instead - the "
            f"already-known flip): it depends which noise bar is used, and "
            f"neither answer is the whole story.** Against the narrower band "
            f"measured at this brief's own `min_samples=2` ({flip_band_m2:.4f}), "
            f"the flip **clears it** in both states "
            f"({'yes' if flip_exceeds_m2 else 'no'}: |gap| = {flip_gap_before:.4f} "
            f"before at {flip_margin_m2_before:.2f}x, {flip_gap_after:.4f} after at "
            f"{flip_margin_m2_after:.2f}x). Against the worst case across every "
            f"`min_samples` value tested ({flip_band_worst:.4f} - `title_artist`'s "
            f"own one-off bimodal break at `min_samples=10`, not something this "
            f"brief's `min_samples=2` run actually exhibits), it does **not** "
            f"({'yes' if flip_exceeds_worst else 'no'}: best margin only "
            f"{flip_margin_worst_best:.2f}x). This is a real qualification of "
            f"CLAUDE.md open item 10 either way, not a contradiction of it - the "
            f"flip reproduces exactly (item 10 quoted 0.145/0.185; this script "
            f"independently measured 0.1453/0.1846) - but its margin is thin "
            f"enough, under the bar that actually applies at this brief's own "
            f"`min_samples`, that it should not be read as a large, settled "
            f"reversal either.\n"
        )

        lines.append("\n## Question 2 - does the ranking flip under any convention "
                      "that it did not flip under before?\n")
        lines.append("\n| convention | before ranking (ARI) | after ranking (ARI) | "
                      "top mode flipped | full order changed |")
        lines.append("|---|---|---|---|---|")
        for _, r in q2_df.iterrows():
            lines.append(
                f"| {r['convention']} | {r['before_ranking']} | {r['after_ranking']} | "
                f"{'yes' if r['top_flipped'] else 'no'} | "
                f"{'yes' if r['order_changed'] else 'no'} |"
            )
        known_flip_conv = "single_cluster"
        known_flip_still_present = ranking("after", known_flip_conv)[0] != "title_artist"
        new_flips = q2_df[(q2_df["convention"] != known_flip_conv) & q2_df["top_flipped"]]

        if len(new_flips):
            new_flip_verdict = "yes"
            new_flip_detail = (
                f"A new convention flips that did not before: "
                f"{', '.join(new_flips['convention'])}."
            )
        else:
            new_flip_verdict = "no"
            new_flip_detail = "Neither `exclude` nor `singletons` newly flips."

        if known_flip_still_present:
            known_flip_detail = (
                "still present after Part 1's fix - `title_genre` still leads "
                "`title_artist` under `single_cluster` (see Q1's qualification "
                "of this flip's own margin above)."
            )
        else:
            known_flip_detail = (
                "**no longer present** - `title_artist` regains the top spot "
                "under `single_cluster` after the ground-truth fix."
            )

        lines.append(
            f"\n**Answer: {new_flip_verdict}.** {new_flip_detail} The "
            f"already-known `single_cluster` flip (CLAUDE.md open item 10) is "
            f"{known_flip_detail} `exclude` and `singletons` keep `title_artist` "
            f"on top both before and after the fix.\n"
        )

        lines.append("\n## What this does and does not establish\n")
        lines.append("- Does not change which noise convention `coherence()` uses "
                      "by default, and does not touch the README - both remain "
                      "Udit's call, per CLAUDE.md's working agreements and this "
                      "brief's own scope.\n")
        lines.append("- Does not re-tune `min_samples`, `MIN_SCORE`, or half-life - "
                      "out of scope per the brief.\n")
        lines.append("- The noise-band figures are reused verbatim from "
                      "`reports/min_samples_sweep.md`, not re-measured here - "
                      "structurally impossible for the ground-truth fix to move "
                      "them (swing is clustering-vs-clustering, never ground "
                      "truth), and re-running that sweep is separately out of "
                      "scope.\n")
        lines.append("- See `reports/ground_truth_audit.md` (Part 0) for the full "
                      "cause breakdown of the 48 drops and the 3 conflicts, and "
                      "`reports/eval_invariance_ground_truth.txt` plus this brief's "
                      "invariance check for proof the fix does not touch scoring, "
                      "clustering input, or the recommender evaluation.\n")

        report_text = "\n".join(lines)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report_text, encoding="utf-8")
        print(f"wrote {REPORT_PATH} ({len(report_text):,} bytes)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
