# Ground-truth denominator fix: before/after measurement

Part 2 of `briefs/ground_truth_ids.md`. Fixed seed (PCA `random_state=0`; HDBSCAN has no internal randomness - determinism checked in `reports/min_samples_sweep.md` §1), `min_samples`=2 (shipped default, unchanged), same config as commit 36e3b5a otherwise. "before" = raw `playlist_ground_truth()` (the pre-Part-1-fix join); "after" = `canonical_ground_truth()` (Part 1's fix). Both measured fresh against current code in this run, not read off any historical report.

## Correctness gates

- `embed.MIN_SAMPLES == 2`: **OK**

- After-fix denominator == 480, conflicts == 3 (`reports/ground_truth_audit.md`): **OK**

- Before-fix pool == 438 for every mode (`reports/min_samples_sweep.md` §2): **OK**

- Before-fix `n_eval` (exclude) == {'title_artist': 238, 'title': 188, 'title_genre': 314}: **OK** (got {'title_artist': 238, 'title': 188, 'title_genre': 314})

- Before-fix ARI (exclude) == {'title_artist': 0.6655, 'title': 0.3707, 'title_genre': 0.3661}: **OK** (got {'title_artist': 0.6655, 'title': 0.3707, 'title_genre': 0.3661})

- Before-fix `single_cluster`: `title_genre` ARI > `title_artist` ARI (CLAUDE.md open item 10's known flip): **OK**

- After-fix pool == 480 for every mode *and* convention: **OK**


## Before/after table

`total_labelled` = the ground-truth pool (before noise handling); `n_eval` = this convention's actual ARI/NMI/purity denominator - the two are equal for `single_cluster`/`singletons` by construction and *not* equal for `exclude`. Both reported on every row so neither has to be inferred from the other.


| mode | convention | when | n_eval | total_labelled | ari | nmi | purity |
|---|---|---|---:|---:|---:|---:|---:|
| title_artist | exclude | before | 238 | 438 | 0.6655 | 0.6377 | 0.6849 |
| title_artist | exclude | after | 261 | 480 | 0.6561 | 0.6259 | 0.6743 |
| title_artist | single_cluster | before | 438 | 438 | 0.1453 | 0.4192 | 0.4315 |
| title_artist | single_cluster | after | 480 | 480 | 0.1415 | 0.4107 | 0.4417 |
| title_artist | singletons | before | 438 | 438 | 0.4394 | 0.6524 | 0.8288 |
| title_artist | singletons | after | 480 | 480 | 0.4140 | 0.6394 | 0.8229 |
| title | exclude | before | 188 | 438 | 0.3707 | 0.4537 | 0.4628 |
| title | exclude | after | 197 | 480 | 0.3799 | 0.4530 | 0.4772 |
| title | single_cluster | before | 438 | 438 | 0.0350 | 0.2354 | 0.2763 |
| title | single_cluster | after | 480 | 480 | 0.0314 | 0.2294 | 0.2875 |
| title | singletons | before | 438 | 438 | 0.1992 | 0.5854 | 0.7694 |
| title | singletons | after | 480 | 480 | 0.1933 | 0.5827 | 0.7854 |
| title_genre | exclude | before | 314 | 438 | 0.3661 | 0.4452 | 0.3949 |
| title_genre | exclude | after | 340 | 480 | 0.3365 | 0.4331 | 0.3912 |
| title_genre | single_cluster | before | 438 | 438 | 0.1846 | 0.3502 | 0.3333 |
| title_genre | single_cluster | after | 480 | 480 | 0.1683 | 0.3347 | 0.3375 |
| title_genre | singletons | before | 438 | 438 | 0.2827 | 0.5249 | 0.5662 |
| title_genre | singletons | after | 480 | 480 | 0.2539 | 0.5118 | 0.5687 |

## Question 1 - does the title_artist/title_genre gap survive the noise band under every convention?

`min_samples_sweep.md`'s own "0.179 at 36e3b5a" compares against **stale, published README figures** (0.649/0.470 exclude-convention ARI) that predate the `normalise_title` fix - that report's own §2 measured 0.6655/0.3661 with the same current code this script runs, a gap of 0.2994, not 0.179. Neither of those is *this* brief's before/after comparison, so both gaps below are measured fresh rather than reused from either historical figure.


The `exclude`/`min_samples=2` band below (0.0015) is not a general robustness claim - `exclude` drops noise before scoring, so it is already near-perfectly stable at `min_samples=2`; the resulting ~200x margins say this *specific* 7-track perturbation barely moves an already-noise-excluded clustering, not that the exclude comparison is immune to instability in general (`exclude`'s own worst-case band, 0.0375 at min_samples=10, is >20x larger).


Sign matters here and is reported separately from magnitude: under `single_cluster`, `title_genre` leads (CLAUDE.md's already-known item-10 flip), so "does title_artist's gap survive" is not even the right question there - `exceeds_noise_band` instead asks whether *whichever mode leads* does so by more than measured structural noise. Two noise bars are reported, not one: the worst case across every `min_samples` value `min_samples_sweep.md` tested, and the narrower one measured at `min_samples=2` specifically - the value this brief actually pins. For `single_cluster` these disagree (the worst case is `title_artist`'s own one-off bimodal break at `min_samples=10`, not a general noise floor for the convention - see `noise_band_worst_case`'s docstring), so both are shown rather than picking one.


| when | convention | gap (title_artist − title_genre) | leader | band (min_samples=2) | margin | band (worst case) | margin | exceeds worst-case band |
|---|---|---:|---|---:|---:|---:|---:|---|
| before | exclude | 0.2994 | title_artist | 0.0015 | 199.58x | 0.0375 | 7.98x | yes |
| before | single_cluster | -0.0392 | title_genre | 0.0165 | 2.38x | 0.0861 | 0.46x | **no** |
| before | singletons | 0.1567 | title_artist | 0.0095 | 16.49x | 0.1264 | 1.24x | yes |
| after | exclude | 0.3196 | title_artist | 0.0015 | 213.06x | 0.0375 | 8.52x | yes |
| after | single_cluster | -0.0268 | title_genre | 0.0165 | 1.62x | 0.0861 | 0.31x | **no** |
| after | singletons | 0.1601 | title_artist | 0.0095 | 16.85x | 0.1264 | 1.27x | yes |

**Answer, in two parts because the conventions do not all point the same way:**

- **`exclude` and `singletons` (where `title_artist` leads, both before and after): yes, the gap survives under both noise bars, in every one of these conventions, both before and after the fix** - and by a larger margin than the historical 0.179 ever needed, since the freshly-measured gaps here (0.2994-0.3196 exclude, 0.1567-0.1601 singletons) are themselves bigger than 0.179. Thinnest margin (worst-case band): before/singletons at 1.24x - still comfortable. The noise *band* itself cannot move between before and after (it is computed between two clusterings and never touches ground truth); the *gap* does move (0.2994 to 0.3196 under exclude, for instance) because it is ground-truth-derived and the fix changed ground truth - expected, and the reason the comparison is run on both sides rather than assumed stable.

- **`single_cluster` (where `title_genre` leads instead - the already-known flip): it depends which noise bar is used, and neither answer is the whole story.** Against the narrower band measured at this brief's own `min_samples=2` (0.0165), the flip **clears it** in both states (yes: |gap| = 0.0392 before at 2.38x, 0.0268 after at 1.62x). Against the worst case across every `min_samples` value tested (0.0861 - `title_artist`'s own one-off bimodal break at `min_samples=10`, not something this brief's `min_samples=2` run actually exhibits), it does **not** (no: best margin only 0.46x). This is a real qualification of CLAUDE.md open item 10 either way, not a contradiction of it - the flip reproduces exactly (item 10 quoted 0.145/0.185; this script independently measured 0.1453/0.1846) - but its margin is thin enough, under the bar that actually applies at this brief's own `min_samples`, that it should not be read as a large, settled reversal either.


## Question 2 - does the ranking flip under any convention that it did not flip under before?


| convention | before ranking (ARI) | after ranking (ARI) | top mode flipped | full order changed |
|---|---|---|---|---|
| exclude | title_artist > title > title_genre | title_artist > title > title_genre | no | no |
| single_cluster | title_genre > title_artist > title | title_genre > title_artist > title | no | no |
| singletons | title_artist > title_genre > title | title_artist > title_genre > title | no | no |

**Answer: no.** Neither `exclude` nor `singletons` newly flips. The already-known `single_cluster` flip (CLAUDE.md open item 10) is still present after Part 1's fix - `title_genre` still leads `title_artist` under `single_cluster` (see Q1's qualification of this flip's own margin above). `exclude` and `singletons` keep `title_artist` on top both before and after the fix.


## What this does and does not establish

- Does not change which noise convention `coherence()` uses by default, and does not touch the README - both remain Udit's call, per CLAUDE.md's working agreements and this brief's own scope.

- Does not re-tune `min_samples`, `MIN_SCORE`, or half-life - out of scope per the brief.

- The noise-band figures are reused verbatim from `reports/min_samples_sweep.md`, not re-measured here - structurally impossible for the ground-truth fix to move them (swing is clustering-vs-clustering, never ground truth), and re-running that sweep is separately out of scope.

- See `reports/ground_truth_audit.md` (Part 0) for the full cause breakdown of the 48 drops and the 3 conflicts, and `reports/eval_invariance_ground_truth.txt` plus this brief's invariance check for proof the fix does not touch scoring, clustering input, or the recommender evaluation.
