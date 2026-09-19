# Embedding-mode ARI, ground-truth pool 480

Part D of `briefs/portability_defects.md` - measurement only. README item 6's embedding-mode table has gone stale three times (2026-09-15 canonical/strict-filter, 2026-09-16 `normalise_title` fix, 2026-09-17 ground-truth pool 438->480); this re-measures it on the current pool under all three noise conventions side by side, gated on Part A's own before/after invariance check (`reports/nan_guard_fix.md`) having found zero `embed_text` change since. **No convention is picked here.**

## Provenance

- Commit: `4edbc6fa261e70bc581c6178d9dd00210c2376d1`

- Ground-truth pool: 480 (3 canonical tracks dropped for conflicting playlist labels - `reports/ground_truth_audit.md`)

- `embed.MIN_SAMPLES` = 2 (shipped default, unchanged)

- PCA `random_state=0`; HDBSCAN has no internal randomness given fixed input (determinism checked in `reports/min_samples_sweep.md` §1)

- Date: 2026-09-19

- Correctness gates: pool == 480 (OK), conflicts == 3 (OK), exclude-convention ARI matches `reports/ground_truth_ids.md`'s published pool=480 figures (OK)


## 1. All three modes x all three conventions

`n_eval` = this convention's actual ARI/NMI/purity denominator; `total_labelled` = the ground-truth pool before this convention's own noise handling (constant per row: 480). The two are equal for `single_cluster`/`singletons` by construction and *not* equal for `exclude` - both shown on every row so neither has to be inferred from the other. This is the finding that started the convention question: `title_artist` is graded on the smallest slice under `exclude`.


| mode | convention | n_eval | total_labelled | ari | nmi | purity |
|---|---|---:|---:|---:|---:|---:|
| title_artist | exclude | 261 | 480 | 0.6561 | 0.6259 | 0.6743 |
| title_artist | single_cluster | 480 | 480 | 0.1415 | 0.4107 | 0.4417 |
| title_artist | singletons | 480 | 480 | 0.4140 | 0.6394 | 0.8229 |
| title | exclude | 197 | 480 | 0.3799 | 0.4530 | 0.4772 |
| title | single_cluster | 480 | 480 | 0.0314 | 0.2294 | 0.2875 |
| title | singletons | 480 | 480 | 0.1933 | 0.5827 | 0.7854 |
| title_genre | exclude | 340 | 480 | 0.3365 | 0.4331 | 0.3912 |
| title_genre | single_cluster | 480 | 480 | 0.1683 | 0.3347 | 0.3375 |
| title_genre | singletons | 480 | 480 | 0.2539 | 0.5118 | 0.5687 |

## 2. Pairwise gaps vs. the structural noise band (`reports/min_samples_sweep.md`, `min_samples=2`)

`std_X`/`std_Y` = std(swing) for each mode in the pair, at this project's own `min_samples=2` (§3 singletons, §7 exclude/single_cluster of that report - all three modes, not just the two "anchor" ones a narrower reuse elsewhere covers). `margin` is the gap divided by the *larger* (harder-to-clear) of the two stds; `exceeds_both` requires the gap to beat both, independently.


### `title_artist` − `title_genre`

| convention | gap | leader | std(title_artist) | std(title_genre) | margin | exceeds both |
|---|---:|---|---:|---:|---:|---|
| exclude | 0.3196 | title_artist | 0.0006 | 0.0015 | 213.06x | yes |
| single_cluster | -0.0268 | title_genre | 0.0077 | 0.0165 | 1.62x | yes |
| singletons | 0.1601 | title_artist | 0.0044 | 0.0095 | 16.85x | yes |

### `title_genre` − `title`

| convention | gap | leader | std(title_genre) | std(title) | margin | exceeds both |
|---|---:|---|---:|---:|---:|---|
| exclude | -0.0433 | title | 0.0015 | 0.0440 | 0.99x | **no** |
| single_cluster | 0.1368 | title_genre | 0.0165 | 0.0751 | 1.82x | yes |
| singletons | 0.0606 | title_genre | 0.0095 | 0.1107 | 0.55x | **no** |

## 3. Ranking per convention

| convention | ranking (ARI, highest first) |
|---|---|
| exclude | title_artist > title > title_genre |
| single_cluster | title_genre > title_artist > title |
| singletons | title_artist > title_genre > title |

## 4. What the README can and cannot defend, per convention


**`exclude`:** ranking is title_artist > title > title_genre. `title_artist` beats `title_genre` by 0.3196 (clears the noise band, 213.06x). `title_genre` loses to `title` by 0.0433 (does NOT clear the noise band, 0.99x).


**`single_cluster`:** ranking is title_genre > title_artist > title. `title_artist` loses to `title_genre` by 0.0268 (clears the noise band, 1.62x). `title_genre` beats `title` by 0.1368 (clears the noise band, 1.82x).


**`singletons`:** ranking is title_artist > title_genre > title. `title_artist` beats `title_genre` by 0.1601 (clears the noise band, 16.85x). `title_genre` beats `title` by 0.0606 (does NOT clear the noise band, 0.55x).


**Summary, not a recommendation, derived directly from the tables above (every direction below is the computed `leader`, not an assumed one):** `title_artist` beats `title_genre` under `exclude`, `singletons` (all clearing the noise band); under the remaining convention(s) (`single_cluster`) `title_genre` leads instead (CLAUDE.md open item 10's known flip - see `reports/ground_truth_ids.md`'s Q1 for that flip's own margin against the worst-case noise band, thinner than the `min_samples=2` band used here). For `title_genre` vs. `title`: `title_genre` leads under `single_cluster`, `singletons`, clearing the noise band under `single_cluster` specifically; `title` itself leads under `exclude` - a direction the README's own historical framing ("title_genre beats title") does not hold under at all, not just narrowly. This project has been burned twice by a published table that outran the decision behind it (CLAUDE.md items 6 and 9) - the convention choice is Udit's, made with this table in hand, not assumed here a third time.

## 5. Is the `single_cluster` ARI flip a real reversal, or an ARI-specific artifact?

`briefs/close_convention_decision.md`. Everything in this section is derived from §1's table above - no new measurement, no re-clustering. Three checks were run against §1's own numbers, independently, before anything below was written; all three passed.

### 5.1 The metric-by-metric picture under `single_cluster`

| metric | title_artist | title_genre | leader |
|---|---:|---:|---|
| ARI | 0.1415 | 0.1683 | title_genre |
| NMI | 0.4107 | 0.3347 | title_artist |
| purity | 0.4417 | 0.3375 | title_artist |

### 5.2 Verified: how many of the 9 metric x convention cells does `title_artist` lead?

Computed directly from §1's table, all 3 metrics x all 3 conventions, `title_artist` vs. `title_genre`: **8 of 9**. The sole exception is ARI under `single_cluster` - the cell in 5.1 above. Every other cell (ARI under `exclude` and `singletons`; NMI and purity under all three conventions, including `single_cluster` itself) has `title_artist` leading.

### 5.3 A candidate mechanism - unverified reasoning, not a measured result

The following is offered as an explanation, not established by anything measured in this report or elsewhere: ARI is computed over agreeing and disagreeing *pairs* of points, so collapsing every noise point into one cluster (the `single_cluster` convention) creates a penalty that grows quadratically with how many tracks that mode left unplaced. `title_artist` leaves the most tracks unplaced of the two modes in this comparison - 261 of 480 graded under `exclude` (219 unplaced), against `title_genre`'s 340 graded (140 unplaced) - so it absorbs the largest share of that quadratic penalty specifically on the one metric (ARI) that is pairwise-defined. NMI and purity are not computed the same way and do not carry this penalty in the same form, which is offered as a candidate explanation for why they do not flip. This mechanism has not been isolated or tested independently of this correlational reading of §1's existing numbers.

### 5.4 What this does and does not establish

This shows the `single_cluster` ARI flip is not a consistent reversal across metrics - it is the one dissenting cell out of nine. It does **not** prove `title_artist` is better than `title_genre` under `single_cluster` on ARI specifically: on that one metric, under that one convention, `title_genre` genuinely leads (0.1683 vs. 0.1415), and that is not in dispute.

### 5.5 Where the convention decision itself is recorded

This section states a finding about the data only. The decision of which noise convention the evaluation uses by default is recorded in `CLAUDE.md`'s Decisions table and open item 10, not here.
