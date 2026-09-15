## Brief read: rewrite README §8's "Backfill" subsection

Verified against the current code (not just the briefs' stated intent — `writer.py`'s `_target_length`, `_modal_genre`, `_select_with_backfill`, and `plan()`'s FLOOR check, all read directly) and `reports/backfill_plan.md`. One correction to my own assumption going in: `evaluate.py`'s imports contain no `writer` reference at all — re-verified by grep just now, not just carried forward from the old paragraph's claim.

## Scope

The brief's title and "what the section must describe" are about the **Backfill subsection only** (currently lines 822–875, right before `## 9. Layout`). Two explicit, narrow exceptions reach outside it: any `--limit`+`--cluster` example anywhere in Quickstart/§8, and test counts "wherever stated." Everything else in §8 ("The first live write," "The two write modes") is untouched — the audit calls parts of "The two write modes" incomplete, but that's not "stale," and the brief doesn't name it.

**Lines I will touch** (current numbering, verified fresh — all shifted +15 from the audit's numbers due to my earlier §2 edit):
- **36** (Quickstart step 6): drop `--limit 45` from the cluster-write example — that flag now hard-errors there.
- **709**: "53 tests" → **76** (measured just now: `pytest --collect-only tests/test_writer.py`, not the audit's stale 72).
- **785–786** (§8 command block): drop `--limit 50` from both cluster-write lines, same reason as line 36.
- **822–875**: the entire "### Backfill" subsection — full rewrite per below.
- **897, 919** (§9 Layout, §10 Running it): "301 tests" → **337** (this session's own measured count, matches the brief's stated figure).

**Left alone, deliberately:**
- Line 759, "289 tests passed" — CLAUDE.md is explicit this is a correct historical statement about 2026-09-13 and must not be "corrected."
- "The two write modes" (799–820) and "The first live write" (754–796) prose — not flagged as stale, not named in "also fix."

**Flagging, not fixing:** §10 line 916, `python -m taste_engine.evaluate --both --test-days 30 # both tasks, §2`, is now stale for a reason this brief's audit couldn't have caught — I changed §2's actual pinned reproducing command in the *previous* brief, to `--split 2026-06-01 --test-end 2026-07-01 -k 50 --half-life 14`, no `--both`. That's outside §8, not named in "also fix," and touching §2-adjacent things isn't this brief's job — noting it for a future pass rather than fixing it now.

## The rewritten Backfill subsection — content plan

**Five rules**, each with its constant and a one-line mechanism statement, sourced from `config.py` + `writer.py`:

| rule | threshold | behavior |
|---|---|---|
| FLOOR | `MIN_CLUSTER_NATIVE=12` | below it, `WriteBlocked` — no playlist at all. 27 of 37 real clusters currently fall below it (`reports/backfill_plan.md`, "Skipped: below the floor") |
| LENGTH | `target = floor(native/(1-MAX_BACKFILL_SHARE))`, share=0.25 | derived from native count, never requested |
| GUARD | modal genre (plurality vote over tidied labels, tie broken by highest-count-then-alphabetical) | candidate must carry it; not enough matches → short, never relaxed |
| RANK | cosine distance to the *requesting* cluster's own centroid, ascending | not score, not nearest-whole-cluster; tie-break (distance asc, score desc, video_id asc) |
| CEILING | `MAX_BACKFILL_DISTANCE=1.0` | candidate at/beyond it refused outright, even as the sole genre match — distance >1.0 is negative cosine similarity |

Plus one line that any of FLOOR/GUARD/CEILING running dry returns the playlist **short**, never relaxes a rule (`shortfall` field in `writer.plan()`'s output).

**Worked example — T-Series / Pritam / Sony Music India**, replacing the old two-cluster table (brief says use this one only). Every number from `reports/backfill_plan.md`'s "Per-cluster dry-run plan" and "Distance ranking" sections:
native 22 (clears FLOOR) → target 29 (`floor(22/0.75)`) → modal genre `'music of asia'` (won a 21–21 tie against `'pop'` on this exact cluster, per "Genre tie-break") → exactly one outside candidate anywhere in the eligible pool carries it: Doja Cat – "Streets (Official Video)" → refused at distance **1.1166**, past the 1.0 ceiling → **0 backfilled, final 22, short by 7**, 1,151 quota units.

**Invariance-check paragraph**, kept but rewritten: the structural claim ("`evaluate.py` never imports `writer`") stays — I just independently re-verified it — but the old "stashed the backfill code, re-ran, restored" methodology description is specific to the *old*, now-deleted mechanism (that's what CLAUDE.md's own state notes describe). For the current mechanism I'll cite what actually exists: `reports/eval_invariance_backfill.txt`, one recorded run of `--both --test-days 30` against current code. I will **not** claim "byte-identical" for the current mechanism specifically — that would need a second run I haven't done and this docs-only brief doesn't ask for; I'll only claim what the architecture and that one recorded run actually support.

**Placeholder**: `<!-- CONCLUSION: Udit writes this -->` goes where the old "musically sensible... T-Series it plainly is not... not a bug to tune away" paragraph (848–862) currently sits — that entire paragraph is the interpretive content the brief reserves for you, not refreshed numbers.

Kept verbatim, unmoved: the closing line "No test in the suite makes a live API call; `tests/fake_youtube.py` stands in." — general to §8, not stale, not backfill-specific.

Nothing here characterizes the mechanism as refined/improved/iterated — table above is thresholds and behavior only.

Say go and I'll write it.
