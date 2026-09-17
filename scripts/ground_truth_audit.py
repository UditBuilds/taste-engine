"""Part 0 of briefs/ground_truth_ids.md - read-only diagnosis, no pipeline code changed.

`cluster_eval.coherence()` intersects `clustered["video_id"]` (canonical
representative ids, from `scored_tracks(canonical=True)`) against
`playlist_ground_truth()`'s keys (raw `playlist_tracks.video_id`, never
canonicalised). `reports/eval_verification.md` (A3) already confirmed this
silently drops 48 of 486 ground-truth-and-music raw ids. This script re-derives
`canonical.collapse()`'s own raw -> representative mapping - the same
functions it calls, in the same order, on the same population - and joins it
against ground truth to classify every drop by cause, and to check whether
canonicalising ground truth in place (Part 1's proposed fix) would make any
one canonical track carry two different playlists' labels at once.

Row membership of `clustered` does not depend on embedding mode:
`embed.cluster_tracks()` attaches `cluster`/`cluster_name` columns to a copy
of its input without ever dropping a row (`out = df.copy().reset_index(drop=True)`,
confirmed by reading the function - no dropna, no row filtering). So this
whole diagnosis is pure ID-level set logic; no embedding model is loaded and
no clustering runs.

Run:  scripts/run.sh scripts/ground_truth_audit.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from taste_engine.canonical import add_canonical_key, iso_seconds, merge_by_duration, title_core
from taste_engine.classify import classify
from taste_engine.cluster_eval import playlist_ground_truth
from taste_engine.db import connect
from taste_engine.embed import artist_from_channel
from taste_engine.redact import alias, aliases_for
from taste_engine.score import scored_tracks

REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "ground_truth_audit.md"

EXPECTED_DROP = 48
EXPECTED_GROUND_TRUTH_AND_MUSIC = 486


def build_raw_to_representative(conn) -> tuple[pd.DataFrame, dict[str, str]]:
    """Reproduce canonical.collapse()'s own raw video_id -> representative id map.

    Same functions `collapse()` calls (`add_canonical_key`, `title_core`,
    `merge_by_duration`), in the same order, on the same music-only raw frame
    it receives (`scored_tracks(canonical=False)`) - not a reimplementation.
    Returns the per-row working frame (one row per raw video_id, carrying its
    final `canonical_key`) and the key -> representative-video_id lookup.
    """
    raw = scored_tracks(conn, canonical=False)
    work = add_canonical_key(raw)
    work["core_key"] = [
        title_core(t, c) for t, c in zip(work["title"], work["channel"])
    ]
    if "duration" in work.columns:
        work["seconds"] = work["duration"].map(iso_seconds)
        work["canonical_key"] = merge_by_duration(work)

    ordered = work.sort_values(
        ["canonical_key", "play_count", "video_id"], ascending=[True, False, True]
    )
    rep_by_key = ordered.groupby("canonical_key", sort=False)["video_id"].first().to_dict()
    return work, rep_by_key


def main() -> int:
    conn = connect()
    try:
        # ---- reproduce collapse()'s own mapping, gated against its real output ----
        work, rep_by_key = build_raw_to_representative(conn)
        raw_to_rep = dict(zip(work["video_id"], work["canonical_key"].map(rep_by_key)))

        canonical_tracks = scored_tracks(conn, canonical=True)
        real_representative_ids = set(canonical_tracks["video_id"])
        derived_representative_ids = set(rep_by_key.values())
        gate_ok = derived_representative_ids == real_representative_ids
        print(f"[gate] re-derived representative-id set matches "
              f"scored_tracks(canonical=True) exactly: {'OK' if gate_ok else 'MISMATCH'} "
              f"({len(derived_representative_ids):,} derived vs "
              f"{len(real_representative_ids):,} real)")
        if not gate_ok:
            only_derived = derived_representative_ids - real_representative_ids
            only_real = real_representative_ids - derived_representative_ids
            print(f"  only in derived: {len(only_derived)}; only in real: {len(only_real)}")
            print("\nRefusing to report: re-derivation does not match collapse()'s real "
                  "output 1:1. Stopping for investigation - no report written.")
            return 1

        # ---- ground truth: raw video_id -> playlist name, exactly-one-playlist only ----
        truth_raw = playlist_ground_truth(conn, redacted=False)
        alias_map = aliases_for(conn)
        truth_redacted = {vid: alias(name, alias_map) for vid, name in truth_raw.items()}

        is_music_raw_ids = set(work["video_id"])  # the population collapse() actually receives
        n_total_ground_truth = len(truth_raw)
        ground_truth_and_music = set(truth_raw) & is_music_raw_ids
        n_ground_truth_and_music = len(ground_truth_and_music)

        # ---- item 1: join / drop, against the real, currently-shipped path ----
        clustered_ids = real_representative_ids  # == scored_tracks(canonical=True)["video_id"]
        # "Drop" is only a meaningful, non-trivial outcome within the
        # is_music-eligible ground-truth population: a ground-truth row that
        # isn't music was never going to reach `clustered` regardless of ID
        # form, and folding it into "drop" would conflate two unrelated
        # exclusions (is_music filtering vs. the raw/canonical ID mismatch
        # this brief investigates).
        joined = {v for v in ground_truth_and_music if v in clustered_ids}
        dropped = {v for v in ground_truth_and_music if v not in clustered_ids}
        assert joined | dropped == ground_truth_and_music
        assert not (joined & dropped)

        print(f"\nground-truth rows (filed in exactly one playlist): "
              f"{n_total_ground_truth:,}")
        print(f"  not music at all pre-collapse (never reaches `clustered` "
              f"regardless of ID form): {n_total_ground_truth - n_ground_truth_and_music:,}")
        print(f"  is_music pre-collapse (the addressable population): "
              f"{n_ground_truth_and_music:,}")
        print(f"    joined (own id is its group's representative):        "
              f"{len(joined):,}")
        print(f"    dropped (own id lost the representative slot):        "
              f"{len(dropped):,}")

        gt_music_matches = n_ground_truth_and_music == EXPECTED_GROUND_TRUTH_AND_MUSIC
        drop_matches = len(dropped) == EXPECTED_DROP
        print(f"\n[confirm] ground-truth-and-music == {EXPECTED_GROUND_TRUTH_AND_MUSIC} "
              f"(reports/eval_verification.md A3): "
              f"{'OK' if gt_music_matches else 'MISMATCH'} (got {n_ground_truth_and_music})")
        print(f"[confirm] drop count == {EXPECTED_DROP} "
              f"(reports/eval_verification.md A3 / this brief): "
              f"{'OK' if drop_matches else 'MISMATCH'} (got {len(dropped)})")

        # ---- item 2: cause breakdown for the drops ----
        vm_ids = {r[0] for r in conn.execute("SELECT video_id FROM video_metadata")}
        title_by_raw = work.set_index("video_id")["title"]

        causes: dict[str, list[str]] = {
            "raw_in_video_metadata_no_canonical_mapping": [],
            "truth_stores_canonical_lookup_uses_raw": [],
            "truth_stores_raw_lookup_uses_canonical": [],
            "id_absent_from_library_entirely": [],
            "other": [],
        }
        detail_rows = []
        for vid in sorted(dropped):
            rep = raw_to_rep.get(vid)
            rep_is_self = rep == vid
            rep_in_clustered = rep in clustered_ids if rep is not None else False

            if rep is None:
                # Structurally unreachable: every row entering `work` gets a
                # canonical_key via add_canonical_key's own fallback
                # ("vid:<id>" when the title is unusable), so every id in
                # `work` (which `dropped` is a subset of, by construction) has
                # *some* key and therefore *some* representative. Kept as an
                # explicit, checked bucket rather than assumed empty.
                bucket = "raw_in_video_metadata_no_canonical_mapping"
            elif rep_is_self and rep_in_clustered:
                # Own id IS its group's representative and that representative
                # DID reach `clustered` - by this script's own "dropped"
                # definition that combination cannot occur (contradiction);
                # kept as a checked bucket, not assumed impossible.
                bucket = "other"
            elif rep_is_self and not rep_in_clustered:
                # Own id is its own representative, yet still missing from
                # `clustered` - would implicate something downstream of
                # canonicalisation (e.g. cluster_tracks dropping rows), not
                # the raw/canonical mismatch. embed.cluster_tracks() never
                # drops rows (read, not assumed), so this should be empty.
                bucket = "other"
            elif not rep_in_clustered:
                # Lost the representative slot to `rep`, but `rep` itself
                # never reached `clustered` either - points at a bug upstream
                # of this drop, not a plain raw-vs-canonical mismatch.
                bucket = "other"
            else:
                # The mechanism: ground truth stores vid (a raw upload id);
                # `clustered` only ever carries one representative id per
                # canonical_key group; vid lost that slot to `rep`.
                bucket = "truth_stores_raw_lookup_uses_canonical"

            causes[bucket].append(vid)
            detail_rows.append({
                "video_id": vid,
                "playlist": truth_redacted.get(vid, "?"),
                "title": title_by_raw.get(vid),
                "in_video_metadata": vid in vm_ids,
                "representative_id": rep,
                "representative_title": title_by_raw.get(rep) if rep else None,
                "representative_in_video_metadata": (rep in vm_ids) if rep else None,
                "bucket": bucket,
            })
        detail = pd.DataFrame(detail_rows)

        # "ground truth stores a canonical ID where the lookup uses a raw ID"
        # and "ID absent from the library entirely" describe outcomes, not
        # mechanisms this drop-scoped loop can classify a row into (see the
        # report for the reasoning); left at 0 and explained rather than
        # silently omitted.
        print("\ncause breakdown (48 drops):")
        for cause, ids in causes.items():
            print(f"  {cause:<45} {len(ids):>3}")

        # ---- item 3: conflicts after mapping every is_music ground-truth row ----
        # Scope: ALL is_music ground-truth rows (486), not just the 48 drops -
        # a conflict needs two DIFFERENT raw ids sharing one representative,
        # and one of the two can perfectly well be a "joined" id (its own
        # representative) while the other is a "dropped" duplicate that
        # merged into it. Restricting to the 48 would miss exactly that case.
        gt_music_df = pd.DataFrame(
            {"video_id": sorted(ground_truth_and_music)}
        )
        gt_music_df["playlist"] = gt_music_df["video_id"].map(truth_redacted)
        gt_music_df["representative_id"] = gt_music_df["video_id"].map(raw_to_rep)

        conflict_groups = []
        for rep_id, group in gt_music_df.groupby("representative_id"):
            labels = sorted(set(group["playlist"]))
            if len(labels) > 1:
                rep_row = canonical_tracks[canonical_tracks["video_id"] == rep_id]
                if len(rep_row):
                    rtitle = str(rep_row["title"].iloc[0])
                    rchannel = rep_row["channel"].iloc[0] if "channel" in rep_row.columns else None
                else:
                    rtitle = title_by_raw.get(rep_id)
                    rchannel = work.set_index("video_id")["channel"].get(rep_id)
                conflict_groups.append({
                    "representative_id": rep_id,
                    "title": rtitle,
                    "artist": artist_from_channel(rchannel),
                    "labels": labels,
                    "member_ids": sorted(group["video_id"]),
                })
        conflict_groups.sort(key=lambda g: g["representative_id"])

        print(f"\ncanonical tracks with >1 distinct playlist label after "
              f"raw->canonical mapping: {len(conflict_groups)}")
        for g in conflict_groups:
            print(f"  {g['representative_id']}  {g['title']!r} - {g['artist']!r}  "
                  f"labels={g['labels']}  members={g['member_ids']}")

        # ---- item 4: recoverable vs genuinely unmatchable, of the 48 ----
        conflicted_rep_ids = {g["representative_id"] for g in conflict_groups}
        recoverable, unmatchable = [], []
        for vid in sorted(dropped):
            rep = raw_to_rep.get(vid)
            rep_ok = rep is not None and rep in clustered_ids
            if rep_ok and rep not in conflicted_rep_ids:
                recoverable.append(vid)
            else:
                unmatchable.append(vid)
        print(f"\nof the {len(dropped)} drops: {len(recoverable)} recoverable "
              f"(maps to a real, non-conflicting canonical track); "
              f"{len(unmatchable)} genuinely unmatchable "
              f"(no representative reaches `clustered`, or the mapping "
              f"collides with another playlist's label)")

        # ---- projected post-Part-1 denominator ----
        # `438 (joined) + 44 (recoverable)` is NOT the post-fix count: Part 1's
        # rule (brief, Part 1 item 2) drops the whole CANONICAL TRACK on a
        # label conflict, not just the losing raw id - and two of the three
        # conflict groups' representative id is *itself* a currently-joined
        # ground-truth id (gHb6AEwNFBU, h35g2e9aIIk below), so fixing the join
        # would also remove rows the eval already counts today. Computed
        # directly from `gt_music_df` (the full 486, not just the 48) rather
        # than derived by arithmetic from the join/drop counts above, so a
        # same-playlist collision (two raw ids, one label, one representative
        # - invisible to the >1-label conflict check) is not missed either.
        n_distinct_representatives = int(gt_music_df["representative_id"].nunique())
        rep_groups = gt_music_df.groupby("representative_id")
        multi_member_reps = {rep: g for rep, g in rep_groups if len(g) > 1}
        same_label_collisions = {
            rep: g for rep, g in multi_member_reps.items()
            if len(set(g["playlist"])) == 1
        }
        n_same_label_collision_rows = sum(
            len(g) - 1 for g in same_label_collisions.values()
        )
        joined_ids = {v for v in ground_truth_and_music if raw_to_rep.get(v) == v}
        conflicted_joined_ids = sorted(joined_ids & conflicted_rep_ids)
        projected_denominator = n_distinct_representatives - len(conflict_groups)

        print(f"\ndistinct canonical tracks reached by the 486 (raw->canonical, "
              f"before any conflict rule): {n_distinct_representatives}")
        print(f"  same-label collisions (2+ raw ids, 1 playlist, 1 representative - "
              f"invisible to the conflict check): {len(same_label_collisions)} group(s), "
              f"{n_same_label_collision_rows} redundant row(s)")
        print(f"  currently-joined ids that sit inside a conflicted group and would "
              f"be REMOVED (not merely unrecovered) by Part 1's drop rule: "
              f"{conflicted_joined_ids}")
        print(f"  projected post-Part-1 denominator "
              f"(distinct representatives - conflicted groups dropped whole): "
              f"{n_distinct_representatives} - {len(conflict_groups)} = "
              f"{projected_denominator}")

        # ---- write the report ----
        lines: list[str] = []
        lines.append("# Ground-truth canonical/raw ID mismatch - Part 0 diagnosis\n")
        lines.append("Brief: `briefs/ground_truth_ids.md`. Read-only measurement; no "
                      "pipeline code changed. New code: `scripts/ground_truth_audit.py`. "
                      "Baseline: commit 36e3b5a (490 tests passing).\n")

        lines.append("## Mechanism\n")
        lines.append("`cluster_eval.coherence()`'s `labelled = clustered[clustered[\"video_id\"]"
                      ".isin(truth)]` intersects `clustered[\"video_id\"]` - canonical "
                      "**representative** ids, one per `canonical.collapse()` group, from "
                      "`scored_tracks(canonical=True)` - against `playlist_ground_truth()`'s "
                      "keys, which are always **raw** `playlist_tracks.video_id` values and "
                      "are never canonicalised. A raw id that is a losing duplicate in its "
                      "own canonical group (i.e. some *other* upload of the same song was "
                      "chosen as the representative) vanishes from `clustered` entirely - not "
                      "reassigned to its surviving twin, just gone. `embed.cluster_tracks()` "
                      "never drops rows (`out = df.copy().reset_index(drop=True)`, no "
                      "dropna/filtering), so this is pure ID-level set logic, independent of "
                      "embedding mode or clustering parameters - no embedding model was "
                      "loaded to produce anything below.\n")

        lines.append("## Correctness gate\n")
        lines.append(f"- Re-derived raw -> representative mapping (same functions "
                      f"`canonical.collapse()` calls, same order, same input population) "
                      f"reproduces its real representative-id set exactly: "
                      f"**{'OK' if gate_ok else 'MISMATCH'}** "
                      f"({len(derived_representative_ids):,} ids).\n")

        lines.append("\n## Item 1 - total / join / drop\n")
        lines.append("| population | count |")
        lines.append("|---|---|")
        lines.append(f"| ground-truth rows (filed in exactly one playlist) | "
                      f"{n_total_ground_truth:,} |")
        lines.append(f"| \N{RIGHTWARDS ARROW} not music at all pre-collapse "
                      f"(irrelevant to this join) | "
                      f"{n_total_ground_truth - n_ground_truth_and_music:,} |")
        lines.append(f"| \N{RIGHTWARDS ARROW} is_music pre-collapse "
                      f"(the addressable population) | {n_ground_truth_and_music:,} |")
        lines.append(f"| &nbsp;&nbsp;&nbsp;&nbsp;joined (own id is its group's "
                      f"representative) | {len(joined):,} |")
        lines.append(f"| &nbsp;&nbsp;&nbsp;&nbsp;**dropped** (own id lost the "
                      f"representative slot) | **{len(dropped):,}** |")
        lines.append(f"\n`ground-truth-and-music` matches "
                      f"`reports/eval_verification.md` (A3)'s independently-measured "
                      f"{EXPECTED_GROUND_TRUTH_AND_MUSIC}: "
                      f"**{'confirmed' if gt_music_matches else 'MISMATCH - see above'}**. "
                      f"Drop count matches the brief's expected 48: "
                      f"**{'confirmed' if drop_matches else 'MISMATCH - see above'}**.\n")
        lines.append("\nThe 6,470-vs-486 gap above is a different, much larger population "
                      "(most playlist tracks simply are not classified as music at all) and "
                      "is unaffected by anything in this brief - it is reported only so "
                      "\"total ground-truth rows\" is not left for the reader to reconcile "
                      "against \"48\" themselves.\n")

        lines.append("\n## Item 2 - cause breakdown of the 48 drops\n")
        lines.append("| cause | count |")
        lines.append("|---|---|")
        cause_labels = {
            "raw_in_video_metadata_no_canonical_mapping":
                "raw video ID exists in `video_metadata` but has no canonical mapping",
            "truth_stores_canonical_lookup_uses_raw":
                "ground truth stores a canonical ID where the lookup uses a raw ID",
            "truth_stores_raw_lookup_uses_canonical":
                "ground truth stores a raw ID where the lookup uses a canonical ID",
            "id_absent_from_library_entirely":
                "ID absent from the library entirely",
            "other": "other (see below)",
        }
        for cause, ids in causes.items():
            lines.append(f"| {cause_labels[cause]} | {len(ids)} |")

        lines.append("\n**All 48 are one mechanism**, `truth_stores_raw_lookup_uses_canonical`: "
                      "ground truth is *always* a raw `playlist_tracks.video_id` (the schema "
                      "has no other form to store), and the lookup (`clustered[\"video_id\"]`) "
                      "*always* carries canonical representative ids. A \"drop\" is exactly "
                      "the case where a raw id's own canonical group picked a *different* "
                      "member as representative. The other three named buckets are 0 for "
                      "structural reasons, checked rather than assumed:\n")
        lines.append("- **\"no canonical mapping\"**: every row that reaches "
                      "`canonical.collapse()`'s input gets a `canonical_key` unconditionally - "
                      "`add_canonical_key` falls back to `\"vid:\" + video_id` when a title "
                      "produces no usable key, which maps the row to itself, not to nothing. "
                      "There is no code path that leaves a row keyless.\n")
        lines.append("- **\"ground truth stores a canonical ID\"**: `playlist_ground_truth()` "
                      "reads `playlist_tracks.video_id` directly with no canonicalisation "
                      "step anywhere in its query - ground truth cannot store a canonical id "
                      "even by coincidence in a way that would matter here, since the 438 "
                      "cases where a ground-truth raw id *equals* its group's representative "
                      "are exactly the successful joins, not a drop cause.\n")
        lines.append("- **\"ID absent from the library entirely\"**: every id counted as a "
                      "\"drop\" is, by this script's own definition, a member of "
                      "`is_music_raw_ids` - the same population `canonical.collapse()` "
                      "receives - so it was watched (present in `plays`) and classified "
                      "`is_music`. It may or may not have its own `video_metadata` row (see "
                      "the per-row detail below), but that is orthogonal to *why* it is "
                      "missing from `clustered`: its representative's presence, not its own "
                      "metadata, is what `clustered` membership depends on.\n")
        lines.append(f"- **\"other\"**: {len(causes['other'])}. Reserved for a representative "
                      f"that itself fails to reach `clustered`, or a self-contradictory case "
                      f"caught by this script's own gates; see the loop's inline comments in "
                      f"`scripts/ground_truth_audit.py` for exactly which condition routes "
                      f"here.\n")

        n_dropped_no_metadata = int((~detail["in_video_metadata"]).sum()) if len(detail) else 0
        lines.append(f"\n**Context, not a cause bucket**: of the 48 dropped raw ids, "
                      f"{n_dropped_no_metadata} have no `video_metadata` row at all (is_music "
                      f"via heuristics only - `in_playlist`/`in_library`/`- Topic` channel/"
                      f"VEVO/music.youtube.com); {len(detail) - n_dropped_no_metadata} do. "
                      f"Metadata presence does not change whether the drop happens.\n")

        lines.append("\n**Per-row detail:**\n")
        lines.append("| raw video_id | playlist | title | in video_metadata | "
                      "representative id | representative title |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in detail.sort_values(["playlist", "video_id"]).iterrows():
            lines.append(
                f"| {r['video_id']} | {r['playlist']} | "
                f"{str(r['title'])[:60]} | {'yes' if r['in_video_metadata'] else 'no'} | "
                f"{r['representative_id']} | {str(r['representative_title'])[:60]} |"
            )

        lines.append("\n## Item 3 - conflicting canonical tracks after raw -> canonical mapping\n")
        lines.append(f"Scope: all {n_ground_truth_and_music} is_music ground-truth rows (not "
                      f"just the 48 drops - a conflict needs two *different* raw ids sharing "
                      f"one representative, and one side of that pair can be a \"joined\" id).\n")
        lines.append(f"\n**{len(conflict_groups)} canonical track(s) receive more than one "
                      f"distinct playlist label.**\n")
        if conflict_groups:
            lines.append("| canonical (representative) video_id | title | artist | "
                          "conflicting playlists | raw member ids |")
            lines.append("|---|---|---|---|---|")
            for g in conflict_groups:
                lines.append(
                    f"| {g['representative_id']} | {str(g['title'])[:60]} | "
                    f"{g['artist'] or '(unknown)'} | {', '.join(g['labels'])} | "
                    f"{', '.join(g['member_ids'])} |"
                )
        else:
            lines.append("None found. \"Filed in exactly one playlist\" was enforced at the "
                          "raw ID level (`playlist_ground_truth`'s `HAVING COUNT(*) = 1`); "
                          "empirically, canonicalisation does not currently merge raw ids "
                          "carrying two different playlists' labels into one representative "
                          "on this data - checked over the full 486, not assumed.\n")

        lines.append("\n## Item 4 - recoverable vs genuinely unmatchable\n")
        lines.append(f"Of the 48 drops: **{len(recoverable)} recoverable** (the raw id's "
                      f"representative exists in `clustered` and carries no conflicting "
                      f"playlist label - Part 1 mapping raw ground truth to its canonical id "
                      f"would attach it cleanly); **{len(unmatchable)} genuinely unmatchable** "
                      f"(representative absent from `clustered`, or the mapping collides with "
                      f"another playlist's label per Item 3).\n")
        if unmatchable:
            lines.append("\nUnmatchable ids:\n")
            for vid in unmatchable:
                rep = raw_to_rep.get(vid)
                reason = (
                    "representative not in `clustered`" if rep not in clustered_ids
                    else f"representative {rep} carries a conflicting label"
                )
                lines.append(f"- `{vid}` ({truth_redacted.get(vid, '?')}): {reason}\n")

        zero_cost_groups = [
            g for g in conflict_groups
            if g["representative_id"] not in conflicted_joined_ids
        ]
        zero_cost_note = (
            f"The remaining {len(zero_cost_groups)} group(s) "
            f"(`{'`, `'.join(g['representative_id'] for g in zero_cost_groups)}`) "
            f"cost nothing beyond drops already counted unmatchable above - neither "
            f"member was ever a currently-joined ground-truth id."
            if zero_cost_groups else
            "Every conflict group above costs a currently-joined row."
        )
        lines.append(f"\n**`438 + 44 = {438 + len(recoverable)}` is NOT the post-fix "
                      f"denominator - do not sum those two numbers.** Part 1's conflict rule "
                      f"(brief, Part 1 item 2) drops the whole *canonical track* on a label "
                      f"conflict, not just the losing raw id. {len(conflicted_joined_ids)} of "
                      f"the {len(conflict_groups)} Item-3 conflict group(s) have a "
                      f"representative id that is *itself* a currently-joined ground-truth id "
                      f"(**`{'`, `'.join(conflicted_joined_ids)}`**) - fixing the join and "
                      f"then applying the conflict rule would *remove* "
                      f"{'those rows' if len(conflicted_joined_ids) != 1 else 'that row'} from "
                      f"ground truth, not merely fail to add them. {zero_cost_note}\n")
        lines.append(f"\nMeasured directly over the full 486 (not derived by arithmetic from "
                      f"the counts above, so an invisible same-label collision is not missed "
                      f"either - two raw ids, one playlist, one representative would reduce "
                      f"the denominator without tripping the >1-label conflict check): "
                      f"**{n_distinct_representatives}** distinct canonical tracks are reached "
                      f"by the 486 ground-truth-and-music raw ids once each is mapped to its "
                      f"representative. "
                      f"{'No same-label collisions beyond the conflicted groups exist.' if not same_label_collisions else f'{len(same_label_collisions)} same-label collision group(s) account for {n_same_label_collision_rows} further redundant row(s), listed below.'}\n")
        if same_label_collisions:
            lines.append("\n| representative id | playlist | member raw ids |")
            lines.append("|---|---|---|")
            for rep, g in sorted(same_label_collisions.items()):
                lines.append(f"| {rep} | {g['playlist'].iloc[0]} | "
                              f"{', '.join(sorted(g['video_id']))} |")
        lines.append(f"\n**Projected post-Part-1 labelled pool** (distinct representatives, "
                      f"minus the {len(conflict_groups)} conflicted groups Part 1 drops "
                      f"whole): {n_distinct_representatives} − {len(conflict_groups)} = "
                      f"**{projected_denominator}**. This is a projection for Part 2 to verify "
                      f"against `cluster_eval`'s own reported figures once Part 1 ships, not a "
                      f"number this read-only script asserts as final.\n")
        lines.append("\n**This 438/480 is `total_labelled` (the labelled pool `coherence()` "
                      "builds *before* any noise convention is applied), not the `n_eval` "
                      "`coherence()` actually reports today.** The shipped default "
                      "(`\"exclude\"` convention) then drops HDBSCAN noise from that pool, and "
                      "the result is smaller and **mode-dependent** - per "
                      "`reports/eval_verification.md` (A1), today's `n_eval` off the current "
                      "438-track pool is `title_artist`=238, `title`=188, `title_genre`=314, "
                      "not 438 for any of them. The same split will apply post-fix: 480 is the "
                      "new *pool* size, and each mode's actual post-fix `n_eval` under "
                      "`\"exclude\"` will be some smaller, mode-specific subset of it - `480` "
                      "flat only holds for the two noise-inclusive conventions "
                      "(`single_cluster`/`singletons`), where `n_eval` equals the pool by "
                      "construction. Part 2's before/after table must report the pool *and* "
                      "each mode-and-convention's own `n_eval` as separate columns, not use "
                      "480 as a stand-in for both.\n")

        lines.append("\n## Answer\n")
        conflict_verdict = (
            "this is the real risk Part 1 must handle with an explicit drop rule, "
            "per the brief." if conflict_groups else
            "none, on this data today, though Part 1 should still implement the "
            "conflict rule defensively rather than assume this stays true."
        )
        conflicted_joined_note = (
            f"`{'`, `'.join(conflicted_joined_ids)}`" if conflicted_joined_ids else "none"
        )
        lines.append(f"Drop confirmed at **{len(dropped)}** "
                      f"({'matches' if drop_matches else 'DOES NOT MATCH'} the brief's "
                      f"expected {EXPECTED_DROP}). All 48 share one cause: ground truth is "
                      f"raw-id-only and the collapsed frame is representative-id-only, with "
                      f"no ID-level ambiguity found in the other three hypothesised causes. "
                      f"{len(conflict_groups)} label conflict(s) would arise from a naive "
                      f"raw->canonical remap of ground truth - {conflict_verdict} "
                      f"Applying that drop rule costs more than the 48 alone: it also removes "
                      f"**{len(conflicted_joined_ids)}** id(s) currently counted as *joined* "
                      f"({conflicted_joined_note}), so today's 438 does not survive unchanged "
                      f"either. Today's labelled pool is 438; the projected pool after Part "
                      f"1's fix is **{projected_denominator}** ({n_distinct_representatives} "
                      f"distinct canonical tracks reached by the 486, minus the "
                      f"{len(conflict_groups)} conflicted groups dropped whole) - up from 438, "
                      f"but by less than the naive `438 + 44` sum would suggest. This is the "
                      f"*pool*, not `coherence()`'s actual `n_eval` - under the shipped "
                      f"`\"exclude\"` convention that is a smaller, mode-dependent subset "
                      f"(today: 238/188/314 for title_artist/title/title_genre, per "
                      f"eval_verification.md A1), so Part 2 must report pool and per-mode "
                      f"`n_eval` as separate figures rather than let either be inferred from "
                      f"the other.\n")
        lines.append("\n**STOP HERE per the brief - Part 1 not started.**\n")

        report_text = "\n".join(lines)
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report_text, encoding="utf-8")
        print(f"\nwrote {REPORT_PATH} ({len(report_text):,} bytes)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
