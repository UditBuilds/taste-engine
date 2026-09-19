"""Part D of briefs/portability_defects.md - measurement only.

README item 6's embedding-mode ARI table is stale for the third time: the
ground-truth pool moved 438 -> 480 on 2026-09-17 (reports/ground_truth_ids.md)
and Part A of this same brief (reports/nan_guard_fix.md) re-confirmed the
pool=480 table is unmoved by its own NaN-guard fixes. This re-measures all
three modes under all three noise conventions on the current pool, states
every denominator explicitly, and checks both pairwise gaps against the
structural noise band already measured in reports/min_samples_sweep.md - no
new clustering, no parameter changes, no convention chosen.

Run:  scripts/run.sh scripts/embedding_modes_pool480.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

from taste_engine.cluster_eval import canonical_ground_truth, coherence_by_convention
from taste_engine.db import connect
from taste_engine.embed import CORPUS_MODES, MIN_SAMPLES, cluster_tracks
from taste_engine.score import scored_tracks

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "embedding_modes_pool480.md"
CONVENTIONS = ("exclude", "single_cluster", "singletons")

EXPECTED_POOL = 480
EXPECTED_CONFLICTS = 3

# reports/min_samples_sweep.md §3 (singletons) and §7 (exclude, single_cluster):
# std(swing) at THIS project's own min_samples=2, for all three modes - not
# just the two "anchor" modes reused elsewhere (e.g.
# scripts/ground_truth_before_after.py's NOISE_BAND), because Part D also
# needs the title_genre-title gap, which that narrower dict cannot answer.
# Reused verbatim, not re-measured: swing is a structural quantity (original
# vs. perturbed clustering) that never touches ground truth, and re-running
# the sweep is explicitly out of scope for this brief.
SWING_STD_AT_MIN_SAMPLES_2 = {
    "exclude": {"title_artist": 0.0006, "title": 0.0440, "title_genre": 0.0015},
    "single_cluster": {"title_artist": 0.0077, "title": 0.0751, "title_genre": 0.0165},
    "singletons": {"title_artist": 0.0044, "title": 0.1107, "title_genre": 0.0095},
}


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def main() -> int:
    conn = connect()
    try:
        tracks = scored_tracks(conn)  # canonical=True, music_only=True, defaults
        truth, gt_stats = canonical_ground_truth(conn, tracks)

        gate_pool = gt_stats["denominator"] == EXPECTED_POOL
        gate_conflicts = gt_stats["conflicts_dropped"] == EXPECTED_CONFLICTS
        gate_min_samples = MIN_SAMPLES == 2
        print(f"[gate] ground-truth denominator == {EXPECTED_POOL}: "
              f"{'OK' if gate_pool else 'MISMATCH'} (got {gt_stats['denominator']})")
        print(f"[gate] conflicts dropped == {EXPECTED_CONFLICTS}: "
              f"{'OK' if gate_conflicts else 'MISMATCH'} (got {gt_stats['conflicts_dropped']})")
        print(f"[gate] embed.MIN_SAMPLES == 2: {'OK' if gate_min_samples else 'MISMATCH'} "
              f"(got {MIN_SAMPLES})")
        if not (gate_pool and gate_conflicts and gate_min_samples):
            print("\nRefusing to report: a correctness gate failed. Stopping.")
            return 1

        rows = []
        for mode in CORPUS_MODES:
            clustered = cluster_tracks(tracks, mode=mode)
            table = coherence_by_convention(clustered, truth)
            table.insert(0, "mode", mode)
            rows.append(table)
        full = pd.concat(rows, ignore_index=True)

        # cross-check against reports/ground_truth_ids.md's already-published
        # pool=480 "after" figures - independent measurement, not copied.
        published_exclude_ari = {"title_artist": 0.6561, "title": 0.3799, "title_genre": 0.3365}
        excl = full[full["convention"] == "exclude"].set_index("mode")
        cross_check_ok = all(
            abs(float(excl.loc[m, "ari"]) - published_exclude_ari[m]) < 0.001
            for m in CORPUS_MODES
        )
        print(f"[gate] exclude-convention ARI matches reports/ground_truth_ids.md's "
              f"published pool=480 figures to 3dp: {'OK' if cross_check_ok else 'MISMATCH'}")
        print()

        def gap_rows(mode_a: str, mode_b: str) -> list[dict]:
            out = []
            for convention in CONVENTIONS:
                sub = full[full["convention"] == convention].set_index("mode")
                gap = float(sub.loc[mode_a, "ari"] - sub.loc[mode_b, "ari"])
                std_a = SWING_STD_AT_MIN_SAMPLES_2[convention][mode_a]
                std_b = SWING_STD_AT_MIN_SAMPLES_2[convention][mode_b]
                worse_std = max(std_a, std_b)  # the harder bar to clear
                out.append({
                    "pair": f"{mode_a}-{mode_b}", "convention": convention, "gap": gap,
                    "leader": mode_a if gap > 0 else mode_b,
                    f"std_{mode_a}": std_a, f"std_{mode_b}": std_b,
                    "margin_vs_worse_std": (abs(gap) / worse_std) if worse_std else float("inf"),
                    "exceeds_both": abs(gap) > std_a and abs(gap) > std_b,
                })
            return out

        gap_ag = gap_rows("title_artist", "title_genre")
        gap_gt = gap_rows("title_genre", "title")

        rankings = {}
        for convention in CONVENTIONS:
            sub = full[full["convention"] == convention].set_index("mode")
            rankings[convention] = list(sub["ari"].sort_values(ascending=False).index)

        # ---- assemble report ----
        sha = git_sha()
        lines: list[str] = []
        lines.append("# Embedding-mode ARI, ground-truth pool 480\n")
        lines.append("Part D of `briefs/portability_defects.md` - measurement only. "
                      "README item 6's embedding-mode table has gone stale three times "
                      "(2026-09-15 canonical/strict-filter, 2026-09-16 `normalise_title` "
                      "fix, 2026-09-17 ground-truth pool 438->480); this re-measures it "
                      "on the current pool under all three noise conventions side by "
                      "side, gated on Part A's own before/after invariance check "
                      "(`reports/nan_guard_fix.md`) having found zero `embed_text` "
                      "change since. **No convention is picked here.**\n")

        lines.append("## Provenance\n")
        lines.append(f"- Commit: `{sha}`\n")
        lines.append(f"- Ground-truth pool: {gt_stats['denominator']} "
                      f"({gt_stats['conflicts_dropped']} canonical tracks dropped for "
                      f"conflicting playlist labels - `reports/ground_truth_audit.md`)\n")
        lines.append(f"- `embed.MIN_SAMPLES` = {MIN_SAMPLES} (shipped default, unchanged)\n")
        lines.append("- PCA `random_state=0`; HDBSCAN has no internal randomness given "
                      "fixed input (determinism checked in `reports/min_samples_sweep.md` "
                      "§1)\n")
        lines.append("- Date: 2026-09-19\n")
        lines.append(f"- Correctness gates: pool == {EXPECTED_POOL} "
                      f"({'OK' if gate_pool else 'MISMATCH'}), conflicts == "
                      f"{EXPECTED_CONFLICTS} ({'OK' if gate_conflicts else 'MISMATCH'}), "
                      f"exclude-convention ARI matches `reports/ground_truth_ids.md`'s "
                      f"published pool=480 figures ({'OK' if cross_check_ok else 'MISMATCH'})\n")

        lines.append("\n## 1. All three modes x all three conventions\n")
        lines.append("`n_eval` = this convention's actual ARI/NMI/purity denominator; "
                      "`total_labelled` = the ground-truth pool before this convention's "
                      "own noise handling (constant per row: 480). The two are equal for "
                      "`single_cluster`/`singletons` by construction and *not* equal for "
                      "`exclude` - both shown on every row so neither has to be inferred "
                      "from the other. This is the finding that started the convention "
                      "question: `title_artist` is graded on the smallest slice under "
                      "`exclude`.\n")
        lines.append("\n| mode | convention | n_eval | total_labelled | ari | nmi | purity |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for mode in CORPUS_MODES:
            for convention in CONVENTIONS:
                r = full[(full["mode"] == mode) & (full["convention"] == convention)].iloc[0]
                lines.append(
                    f"| {mode} | {convention} | {int(r['n_eval'])} | "
                    f"{int(r['total_labelled'])} | {r['ari']:.4f} | {r['nmi']:.4f} | "
                    f"{r['purity']:.4f} |"
                )

        lines.append("\n## 2. Pairwise gaps vs. the structural noise band "
                      "(`reports/min_samples_sweep.md`, `min_samples=2`)\n")
        lines.append("`std_X`/`std_Y` = std(swing) for each mode in the pair, at this "
                      "project's own `min_samples=2` (§3 singletons, §7 exclude/"
                      "single_cluster of that report - all three modes, not just the two "
                      "\"anchor\" ones a narrower reuse elsewhere covers). `margin` is the "
                      "gap divided by the *larger* (harder-to-clear) of the two stds; "
                      "`exceeds_both` requires the gap to beat both, independently.\n")
        lines.append("\n### `title_artist` − `title_genre`\n")
        lines.append("| convention | gap | leader | std(title_artist) | std(title_genre) | margin | exceeds both |")
        lines.append("|---|---:|---|---:|---:|---:|---|")
        for r in gap_ag:
            lines.append(
                f"| {r['convention']} | {r['gap']:.4f} | {r['leader']} | "
                f"{r['std_title_artist']:.4f} | {r['std_title_genre']:.4f} | "
                f"{r['margin_vs_worse_std']:.2f}x | {'yes' if r['exceeds_both'] else '**no**'} |"
            )
        lines.append("\n### `title_genre` − `title`\n")
        lines.append("| convention | gap | leader | std(title_genre) | std(title) | margin | exceeds both |")
        lines.append("|---|---:|---|---:|---:|---:|---|")
        for r in gap_gt:
            lines.append(
                f"| {r['convention']} | {r['gap']:.4f} | {r['leader']} | "
                f"{r['std_title_genre']:.4f} | {r['std_title']:.4f} | "
                f"{r['margin_vs_worse_std']:.2f}x | {'yes' if r['exceeds_both'] else '**no**'} |"
            )

        lines.append("\n## 3. Ranking per convention\n")
        lines.append("| convention | ranking (ARI, highest first) |")
        lines.append("|---|---|")
        for convention in CONVENTIONS:
            lines.append(f"| {convention} | {' > '.join(rankings[convention])} |")

        lines.append("\n## 4. What the README can and cannot defend, per convention\n")
        for convention in CONVENTIONS:
            r = rankings[convention]
            ag = next(x for x in gap_ag if x["convention"] == convention)
            gt = next(x for x in gap_gt if x["convention"] == convention)
            lines.append(f"\n**`{convention}`:** ranking is {' > '.join(r)}. "
                          f"`title_artist` {'beats' if ag['leader'] == 'title_artist' else 'loses to'} "
                          f"`title_genre` by {abs(ag['gap']):.4f} "
                          f"({'clears' if ag['exceeds_both'] else 'does NOT clear'} the noise band, "
                          f"{ag['margin_vs_worse_std']:.2f}x). "
                          f"`title_genre` {'beats' if gt['leader'] == 'title_genre' else 'loses to'} "
                          f"`title` by {abs(gt['gap']):.4f} "
                          f"({'clears' if gt['exceeds_both'] else 'does NOT clear'} the noise band, "
                          f"{gt['margin_vs_worse_std']:.2f}x).\n")

        ag_wins_artist = [r["convention"] for r in gap_ag if r["leader"] == "title_artist"]
        ag_clears = [r["convention"] for r in gap_ag if r["exceeds_both"]]
        gt_wins_genre = [r["convention"] for r in gap_gt if r["leader"] == "title_genre"]
        gt_wins_title = [r["convention"] for r in gap_gt if r["leader"] == "title"]
        gt_clears = [r["convention"] for r in gap_gt if r["exceeds_both"]]

        summary = (
            f"\n**Summary, not a recommendation, derived directly from the tables above "
            f"(every direction below is the computed `leader`, not an assumed one):** "
            f"`title_artist` beats `title_genre` under {', '.join(f'`{c}`' for c in ag_wins_artist)}"
            f"{' (all clearing the noise band)' if set(ag_wins_artist) <= set(ag_clears) else ''}; "
            f"under the remaining convention(s) "
            f"({', '.join(f'`{c}`' for c in CONVENTIONS if c not in ag_wins_artist)}) "
            f"`title_genre` leads instead (CLAUDE.md open item 10's known flip - see "
            f"`reports/ground_truth_ids.md`'s Q1 for that flip's own margin against the "
            f"worst-case noise band, thinner than the `min_samples=2` band used here). "
            f"For `title_genre` vs. `title`: `title_genre` leads under "
            f"{', '.join(f'`{c}`' for c in gt_wins_genre) if gt_wins_genre else '(none)'}, "
            f"clearing the noise band under "
            f"{', '.join(f'`{c}`' for c in gt_clears) if gt_clears else '(none)'} specifically; "
            f"`title` itself leads under "
            f"{', '.join(f'`{c}`' for c in gt_wins_title) if gt_wins_title else '(none)'} - "
            f"a direction the README's own historical framing (\"title_genre beats title\") "
            f"does not hold under at all, not just narrowly. This project has been burned "
            f"twice by a published table that outran the decision behind it (CLAUDE.md "
            f"items 6 and 9) - the convention choice is Udit's, made with this table in "
            f"hand, not assumed here a third time.\n"
        )
        lines.append(summary)

        report_text = "\n".join(lines)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report_text, encoding="utf-8")
        print(f"wrote {REPORT_PATH} ({len(report_text):,} bytes)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
