# `min_samples` sensitivity sweep

**Measurement only. `min_samples` is not changed; `config.py`/`embed.py` are
untouched.** This answers two questions: is the ARI metric stable enough to
compare embedding modes at all, and is `min_samples = 2` defensible for this
data. Both block the README rewrite; neither is decided here.

Gate: 480 tests passed before this brief started, tree clean at `f88a9a5`,
matching `origin/main`. **490 passing** after this brief's own 10 new tests
(`tests/test_min_samples_sweep.py`).

## 1. Method

**The perturbation.** The original 7-of-2,918-track change is not
reproducible on demand — it was a bug fix, already applied. The stand-in is
**random removal of 7 canonical tracks**, not text mutation (a corruption
designed to mimic the original would be unfalsifiable). 20 repetitions, seeds
1000–1019, `random.Random(seed).sample(...)` — deterministic per seed
(`tests/test_min_samples_sweep.py::TestDropIndices`).

**Paired design.** The same 20 drop-sets are reused across all 4
`min_samples` values and all 3 modes (12 cells), because every mode shares
the identical 2,918-row canonical track frame — only the embedding *text*
differs, never the row count or order. A difference in swing between cells
is therefore attributable to the parameter or the mode, not to which 7
tracks happened to get unlucky that repetition.

**Two different ARI quantities, not one — do not conflate them:**

- **swing** = `1 − adjusted_rand_score(original_labels_on_survivors,
  perturbed_labels)`. Purely structural: original vs. perturbed clustering,
  never touches ground truth. Reported as `1 − ARI` ("instability") rather
  than raw ARI because a *stable* clustering gives ARI near 1.0, and the
  brief's own predicted numbers ("negligible at 10") only parse as a
  quantity that shrinks toward zero as stability improves. This is the
  quantity the hypothesized mechanism (mutual reachability, MST,
  `eom` bridge-snapping) predicts directly — it is a claim about clustering
  *structure*, not about the metric's alignment with human playlists.
- **ARI-against-ground-truth** = the perturbed clustering's own
  `coherence_by_convention` ARI. A distribution of 20 raw values per cell,
  not a delta from the original.

Both are computed under all three noise conventions from the previous brief
(`cluster_eval.coherence_by_convention` / `_relabel_noise`, reused
unmodified). For the *structural* swing, which compares two clusterings
rather than one clustering against a fixed ground truth, "exclude" drops a
point if **either** side calls it noise; "single_cluster"/"singletons"
relabel each side's `-1` independently, exactly as `coherence_by_convention`
does for a single clustering
(`scripts/min_samples_sweep.py::stability_ari`).

**Embedding reuse.** MiniLM encodes each text independently (no
cross-attention across a batch), so a surviving track's vector does not
depend on which other tracks are in the corpus. Each mode's full
2,918-track corpus is embedded once — already cached on disk from prior
briefs — and a perturbation is applied by slicing rows out of that matrix,
never by re-embedding a shrunk corpus. Spot-checked directly: embedding a
50-text subset independently vs. slicing the same 50 rows out of the full
embedding agrees to 1.1×10⁻⁷ (float32 noise, not a real difference).

**Determinism, checked before reporting any numbers (§2a's own
requirement).** `cluster_embeddings` (PCA with `random_state=0`, then
HDBSCAN, which has no internal randomness) was run twice on the identical
vector matrix at `min_samples = 2` and again at `min_samples = 15` —
label arrays were `np.array_equal` both times, at both extremes. **No
nondeterminism found at fixed input.** (§11.7)

**What was run: the full grid, not reduced.** One cell (`title_artist`,
`min_samples = 2`, 20 reps) was timed first per §8: 9.4s. Extrapolated to
~115s for the full grid; the actual run took **149.5s** for all
4×3×20 = 240 perturbed clusterings plus 12 original clusterings, well within
budget. §8's fallback (cut to 10 reps) was **not needed** — every number
below is the full 20-repetition grid. (§11.6)

Raw per-repetition table (720 rows: 4 `min_samples` × 3 modes × 20 reps × 3
conventions): `reports/min_samples_sweep_raw.csv`.

## 2. Secondary observations — the unperturbed clustering vs. `min_samples`

| mode | min_samples | noise | clusters | n_eval (exclude) | coverage | ARI (exclude) |
|---|---:|---:|---:|---:|---:|---:|
| `title_artist` | 2 | 44.8% | 37 | 238 | 54.3% | 0.6655 |
| `title_artist` | 5 | 56.0% | 26 | 188 | 42.9% | 0.7223 |
| `title_artist` | 10 | 56.1% | 16 | 187 | 42.7% | 0.5982 |
| `title_artist` | 15 | 61.0% | 15 | 168 | 38.4% | 0.6343 |
| `title` | 2 | 54.8% | 24 | 188 | 42.9% | 0.3707 |
| `title` | 5 | 67.3% | 10 | 125 | 28.5% | 0.3107 |
| `title` | 10 | 73.4% | 8 | 96 | 21.9% | 0.2292 |
| `title` | 15 | 77.2% | 8 | 82 | 18.7% | 0.1800 |
| `title_genre` | 2 | 36.0% | 25 | 314 | 71.7% | 0.3661 |
| `title_genre` | 5 | 46.7% | 17 | 263 | 60.0% | 0.5189 |
| `title_genre` | 10 | 59.5% | 14 | 197 | 45.0% | 0.6628 |
| `title_genre` | 15 | 59.8% | 10 | 190 | 43.4% | 0.6599 |

(coverage = `n_eval / 438`; 438 is the previous brief's shared ground-truth
pool, already 48 short of the 486 available ground-truth music tracks for
the unrelated canonical/raw-id reason — not fixed here, per §6. `min_samples
= 15` exceeds `embed.MIN_CLUSTER_SIZE` (8) — its core-distance neighbourhood
is larger than a cluster needs members, a different regime from 2/5/10, not
just a bigger number on the same knob; its row in every table here should be
read with that in mind.)

**(§4.1) Noise rate rises with `min_samples` for every mode, monotonically,
with no exception** — 44.8%→61.0% (`title_artist`), 54.8%→77.2% (`title`),
36.0%→59.8% (`title_genre`). This is mechanical and expected: a higher
`min_samples` raises the bar for what counts as a core point, so more points
fail to clear it.

**(§4.2) Cluster count falls with `min_samples` for every mode,
monotonically** — 37→15 (`title_artist`), 24→8 (`title`), 25→10
(`title_genre`). `title` and `title_genre` both bottom out to single digits
by `min_samples = 10`; `title_artist` stays highest throughout.

**(§4.3) Coverage falls as `min_samples` rises, for every mode — the
comparability problem gets worse, not better, exactly as anticipated.**
`title_artist` 54.3%→38.4%, `title` 42.9%→18.7%, `title_genre` 71.7%→43.4%.
Raising `min_samples` does not fix the previous brief's denominator-gap
finding (A1); it widens it. At `min_samples = 15`, `title`'s ARI is computed
on only 82 of 438 ground-truth tracks (18.7%) — a number too small to trust
regardless of what convention is used.

**(§4.4) The exclude-convention ARI itself is not monotonic in
`min_samples`, for any mode** — `title_artist`: 0.6655→0.7223→0.5982→0.6343;
`title`: falls monotonically 0.3707→0.1800 but off an ever-shrinking,
increasingly unreliable base (down to 82 tracks); `title_genre`: rises
monotonically 0.3661→0.6599. Three different shapes for three modes. This
alone is a reason `min_samples` cannot be tuned by watching this number go
up.

## 3. The swing — singletons convention (lead table, per §2b)

Mean / median / min / max / standard deviation of `1 − ARI(original, perturbed)`
across the 20 repetitions, per mode and `min_samples`:

| mode | min_samples | mean | median | min | max | **std** | clusters (mean, perturbed) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `title_artist` | 2 | 0.0061 | 0.0050 | 0.0009 | 0.0186 | **0.0044** | 38.0 |
| `title_artist` | 5 | 0.0075 | 0.0064 | 0.0027 | 0.0164 | **0.0041** | 26.4 |
| `title_artist` | **10** | **0.1909** | **0.2699** | 0.0007 | 0.2767 | **0.1264** | 18.8 |
| `title_artist` | 15 | 0.0141 | 0.0099 | 0.0046 | 0.0577 | **0.0122** | 15.0 |
| `title` | 2 | 0.1641 | 0.1670 | 0.0132 | 0.3006 | **0.1107** | 28.2 |
| `title` | 5 | 0.0523 | 0.0277 | 0.0154 | 0.3067 | **0.0640** | 10.9 |
| `title` | 10 | 0.0524 | 0.0435 | 0.0171 | 0.2304 | **0.0453** | 8.2 |
| `title` | 15 | 0.0555 | 0.0445 | 0.0211 | 0.2254 | **0.0451** | 7.9 |
| `title_genre` | 2 | 0.0122 | 0.0095 | 0.0039 | 0.0365 | **0.0095** | 25.1 |
| `title_genre` | 5 | 0.0081 | 0.0080 | 0.0028 | 0.0172 | **0.0031** | 17.3 |
| `title_genre` | 10 | 0.0114 | 0.0102 | 0.0056 | 0.0204 | **0.0045** | 13.6 |
| `title_genre` | 15 | 0.0069 | 0.0054 | 0.0012 | 0.0224 | **0.0051** | 10.0 |

Appendix tables under "exclude" and "single cluster" are in §7 below; the
verdicts in §4–§5 use singletons as primary and note where another
convention disagrees.

### `title_artist` at `min_samples = 10` is not noisy — it is bimodal

Median (0.2699) sits *above* the mean (0.1909), and min (0.0007) and max
(0.2767) are nearly the full range apart with nothing continuous in
between. The raw per-repetition values, sorted:

```
0.0007  0.0018  0.0018  0.0029  0.0036  0.0054   <- 6 reps: same regime as the original (16 clusters)
0.2693  0.2697  0.2699  0.2699  0.2700  0.2703  0.2703  0.2716  0.2716  0.2717  0.2723  0.2729  0.2764  0.2767   <- 14 reps: a different regime (19-20 clusters)
```

Removing *any* 7 of 2,918 tracks (0.24%) has roughly a 70% chance of tipping
`title_artist`'s clustering at `min_samples = 10` from 16 clusters into a
19–20 cluster regime, and a 30% chance of leaving it alone. This is not
"more noise than usual" — it is a discrete regime switch sitting almost
exactly at this `min_samples` value for this mode, and it is the single
most direct evidence in this sweep for the external review's proposed
mechanism (a sparse MST bridge, once broken, reassigns a large part of the
hierarchy) — except it appears at a *middle* value, not at the lowest one,
which the review's own stated prediction did not anticipate. `title_artist`
is tight and stable at 2, 5, *and* 15; it is bimodal specifically at 10.

### `title` at `min_samples = 2` is tiered, not unimodal either

Sorted swing values fall into three visible bands: 6 reps at 0.013–0.025
(clusters 22–25, close to the original's 24), 7 reps at 0.14–0.17 (clusters
24–27), and 7 reps at 0.28–0.30 (clusters 32–36) — a cluster-count spread of
14 across repetitions, the widest of any cell measured. Unlike
`title_artist`'s clean binary split, this is a graded staircase, but it is
still structured, not smooth Gaussian-looking noise.

### `title_genre` never shows this pattern

Every `min_samples` value for `title_genre` gives a tight, low, apparently
unimodal spread (std 0.0031–0.0095, cluster-count spread ≤ 2 at every value)
— and at `min_samples = 15` specifically, cluster count is **identical
across all 20 repetitions** (spread of exactly 0), the only cell anywhere in
the grid where removing 7 tracks never changed the cluster count at all.
`title_genre` is the only one of the three modes whose clustering did not
destabilize sharply anywhere in this grid.

**(§4 secondary observation — do the three modes respond to `min_samples`
differently) Yes, dramatically, and not just in degree.** `title_artist` is
stable except for a sharp bimodal break at 10; `title` is graded/tiered and
worst at 2; `title_genre` is uniformly stable throughout. A single
"raise `min_samples` to N" recommendation cannot fix all three at once —
whatever N is chosen lands in a different part of each mode's own,
differently-shaped stability curve.

## 4. §11.3 — does the swing fall monotonically as `min_samples` rises? **Refuted, as a general pattern.**

The hypothesis's specific numeric prediction ("roughly 0.22 at 2, under 0.05
at 5, negligible at 10") does not match any of the three modes:

- **`title_artist`: the monotonic-decline prediction is refuted, but the
  underlying mechanism is not — it shows up at a value the prediction didn't
  name.** 0.0044 → 0.0041 → **0.1264** → 0.0122 (std). The *worst*
  instability is at `min_samples = 10`, not 2, and it is a sharp bimodal
  regime switch rather than a graded decline — a cleaner demonstration of a
  snappable MST bridge than a smooth one would have been, just not where
  the hypothesis expected to find it.
- **`title`: partially consistent, then stalls.** 0.1107 → 0.0640 → 0.0453 →
  0.0451. It is worst at 2, as predicted, and does fall — but it plateaus
  around 0.045 and never approaches "negligible"; `min_samples = 15` is
  barely different from `min_samples = 10`.
- **`title_genre`: the premise does not engage.** 0.0095 → 0.0031 → 0.0045 →
  0.0051. Already low at `min_samples = 2` — there is no large starting
  instability for the mechanism to explain away by smoothing.

**Verdict: the mechanism the external review proposed is real in at least
one place (`title_artist`'s bimodal break at 10 is the cleanest possible
demonstration of a bridge in the hierarchy being snappable by a handful of
points) but it is not the smooth, monotonically-decreasing function of
`min_samples` the stated prediction described, and it does not generalize
across modes.** Instability is mode-specific and can appear at a *middle*
value of `min_samples`, not concentrated at the smallest one. A single scalar
"raise it to 5" would have missed `title_artist`'s actual problem entirely
(5 is fine for `title_artist`; 10 is where it breaks).

## 5. §3/§11.4 — do the published gaps exceed the noise band?

Published ARI (current, exclude convention): `title_artist` 0.649,
`title_genre` 0.470, `title` 0.383. Gaps: 0.179 (`title_artist`–`title_genre`)
and 0.087 (`title_genre`–`title`).

Per §3, "the swing" is quantity (A) above (structural instability, not a
ground-truth delta) — comparing the gap against std(swing) at each anchor
mode and `min_samples`, all three conventions, all four values (48 cells
total; full table in `reports/min_samples_sweep_raw.csv`-derived output):

**47 of 48 cells: the gap exceeds std(swing).** The 0.179 gap exceeds
std(swing) in all 24 cells (every convention × every `min_samples` value),
by 1.42× at its own worst case up to 966× at its best; the 0.087 gap exceeds
it in 23 of 24 cells, by 1.16×–124×.

**The one exception, and it is the gap that already broke once:**

> **`title_genre`/`title` gap (0.087) vs. `title`'s own swing std (0.1107)
> at `min_samples = 2`, singletons convention: gap is 79% of the noise band
> — does NOT exceed it.**

This is the same pair whose ranking already flipped in production: the
7-track `normalise_title` fix moved `title_genre` ARI by −0.104 and swapped
its order with `title`. A gap of 0.087 sitting inside a measured noise band
of ±0.11 (one standard deviation, from a similarly-sized 7-track
perturbation) is a direct, independent confirmation that this specific
comparison was never resolvable at the current default — not a coincidence
being read into noise after the fact.

**This does not survive equally under every convention** — worth stating
plainly rather than picking the convention that gives the cleanest answer:

| convention | title_genre/title gap (0.087) vs `title`'s std(swing) at min_samples=2 | margin |
|---|---|---|
| exclude (currently published) | 0.0440 | gap is 2.0× the std — survives, narrowly |
| single_cluster | 0.0751 | gap is 1.16× the std — survives, very narrowly |
| singletons | 0.1107 | gap is 0.79× the std — **does not survive** |

Under the convention this project's own previous brief argued is the more
defensible one for cross-mode comparison (singletons — see
`reports/eval_verification.md`, B1), this specific gap does not survive. Under
the currently-published convention (exclude), it survives, but only by a
factor of 2 — not the kind of margin that should be read as comfortable.

**The `title_artist`/`title_genre` gap (0.179) is a different story: it
survives everywhere, including its own worst case.** Even at `title_artist`'s
bimodal min_samples=10 break (std = 0.1264, the largest instability measured
anywhere in this sweep), 0.179 still exceeds it — by 1.42×, the thinnest
margin this gap ever has, but still on the right side of the line. The
`title_artist`-vs-`title_genre` comparison is not put in doubt by anything
measured here. **The `title_genre`-vs-`title` comparison is.**

## 6. Invariance check (§7)

Re-ran the pinned eval (`--split 2026-06-01 --test-end 2026-07-01 -k 50
--half-life 14`) after writing and running the sweep script. Diffed against
the previous brief's captured snapshot (`score`/`most_played`/
`cluster_diverse`/`recency`: hits 31/32/25/22, ndcg@50 0.5506/0.5421/0.3360/
0.3088, identical `train_tracks`/`test_tracks`/`cold_start`) — **byte-identical**,
confirmed with `diff`. Saved to `reports/eval_invariance_minsamples.txt`.
The sweep did not touch `config.py`, `embed.MIN_SAMPLES`, or any code path
the pinned eval calls — expected, and confirmed rather than assumed.

## 7. Appendix — exclude and single-cluster conventions

### Exclude (currently published convention)

| mode | min_samples | swing mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| `title_artist` | 2 | 0.0008 | 0.0007 | 0.0000 | 0.0021 | 0.0006 |
| `title_artist` | 5 | 0.0002 | 0.0000 | 0.0000 | 0.0011 | 0.0003 |
| `title_artist` | 10 | 0.0559 | 0.0790 | 0.0000 | 0.0825 | 0.0375 |
| `title_artist` | 15 | 0.0001 | 0.0000 | 0.0000 | 0.0004 | 0.0002 |
| `title` | 2 | 0.0593 | 0.0615 | 0.0000 | 0.1122 | 0.0440 |
| `title` | 5 | 0.0104 | 0.0030 | 0.0000 | 0.1050 | 0.0231 |
| `title` | 10 | 0.0064 | 0.0005 | 0.0000 | 0.0463 | 0.0106 |
| `title` | 15 | 0.0051 | 0.0031 | 0.0000 | 0.0316 | 0.0075 |
| `title_genre` | 2 | 0.0008 | 0.0000 | 0.0000 | 0.0043 | 0.0015 |
| `title_genre` | 5 | 0.0008 | 0.0013 | 0.0000 | 0.0017 | 0.0007 |
| `title_genre` | 10 | 0.0034 | 0.0023 | 0.0000 | 0.0091 | 0.0029 |
| `title_genre` | 15 | 0.0017 | 0.0019 | 0.0000 | 0.0038 | 0.0011 |

Same qualitative story as singletons (`title_artist`'s spike at 10 shows up
here too, at a smaller absolute scale because "exclude" drops both sides'
noise before scoring, which removes most of the points whose reassignment
drives the singletons-convention swing).

### Single cluster

| mode | min_samples | swing mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| `title_artist` | 2 | 0.0255 | 0.0233 | 0.0145 | 0.0435 | 0.0077 |
| `title_artist` | 5 | 0.0172 | 0.0172 | 0.0072 | 0.0291 | 0.0055 |
| `title_artist` | 10 | 0.1353 | 0.1892 | 0.0043 | 0.1970 | 0.0861 |
| `title_artist` | 15 | 0.0182 | 0.0152 | 0.0067 | 0.0505 | 0.0101 |
| `title` | 2 | 0.1341 | 0.1304 | 0.0300 | 0.2456 | 0.0751 |
| `title` | 5 | 0.0587 | 0.0348 | 0.0193 | 0.2317 | 0.0501 |
| `title` | 10 | 0.0557 | 0.0419 | 0.0225 | 0.1702 | 0.0370 |
| `title` | 15 | 0.0463 | 0.0372 | 0.0226 | 0.1395 | 0.0280 |
| `title_genre` | 2 | 0.0223 | 0.0173 | 0.0085 | 0.0673 | 0.0165 |
| `title_genre` | 5 | 0.0186 | 0.0161 | 0.0072 | 0.0545 | 0.0096 |
| `title_genre` | 10 | 0.0172 | 0.0165 | 0.0086 | 0.0285 | 0.0055 |
| `title_genre` | 15 | 0.0101 | 0.0105 | 0.0037 | 0.0200 | 0.0045 |

`title_artist`'s spike at `min_samples = 10` is convention-independent — it
shows up in all three conventions, at magnitudes consistent with each
convention's own scale. This rules out "an artifact of how noise is scored"
as the explanation; the underlying clustering itself is bimodal there.

## 8. ARI-against-ground-truth distribution (quantity B, §2's second bullet)

Reported because §2 asks for it explicitly — not used as the noise band for
§3/§5's gap comparison (see §5's framing note). Singletons convention, mean
/ std across the 20 perturbed runs, alongside the *unperturbed* original's
own value for reference. The perturbed rows' denominator (`n_eval`) is not
438 like §2's unperturbed rows — dropping 7 random tracks removes an average
of 0.9 ground-truth tracks along with them, so `n_eval` averages **437.1**
across every mode and `min_samples` (identical everywhere, since which
ground-truth tracks survive depends only on the drop-set, never on mode or
`min_samples`). The difference is far too small to explain anything reported
here, but the two tables are not reading identical denominators and this is
why:

| mode | min_samples | original ARI | perturbed mean | perturbed std |
|---|---:|---:|---:|---:|
| `title_artist` | 2 | 0.4394 | 0.4353 | 0.0058 |
| `title_artist` | 5 | 0.4111 | 0.4113 | 0.0069 |
| `title_artist` | 10 | 0.3515 | 0.3684 | 0.0124 |
| `title_artist` | 15 | 0.3235 | 0.3157 | 0.0121 |
| `title` | 2 | 0.1992 | 0.2158 | 0.0218 |
| `title` | 5 | 0.1059 | 0.1091 | 0.0073 |
| `title` | 10 | 0.0566 | 0.0566 | 0.0039 |
| `title` | 15 | 0.0335 | 0.0356 | 0.0051 |
| `title_genre` | 2 | 0.2827 | 0.2856 | 0.0030 |
| `title_genre` | 5 | 0.3879 | 0.3880 | 0.0023 |
| `title_genre` | 10 | 0.4397 | 0.4429 | 0.0046 |
| `title_genre` | 15 | 0.4604 | 0.4604 | 0.0021 |

`title_artist`'s bimodal break at `min_samples = 10` is visible here too —
its own ARI-vs-truth mean (0.3684) sits noticeably above the unperturbed
original's value (0.3515), pulled up by the ~70% of repetitions that landed
in the alternate 19–20-cluster regime.

## 9. What this does and does not establish

- Does not recommend a value for `min_samples`. Does not change the default.
- Establishes that the embedding-mode ARI comparison's two closest results
  (`title_genre` vs. `title`, published gap 0.087) sit inside a measured
  noise band at the current default (`min_samples = 2`) under the more
  defensible of the two conventions this project has argued about, and only
  narrowly survive under the currently-published one.
- Establishes that the largest gap (`title_artist` vs. `title_genre`, 0.179)
  is robust to this specific noise source at every `min_samples` value and
  every convention tested.
- Establishes that `min_samples` sensitivity is not a single number to tune
  against — it is mode-specific, non-monotonic, and can appear as a sharp
  regime break at a middle value rather than a smooth decline from the
  smallest one. Raising `min_samples` uniformly would not have been a safe
  default change without measuring where each mode's own break point sits,
  which this sweep is the first time anyone has done.
- Raising `min_samples` does not fix the ground-truth coverage problem from
  the previous brief — it makes it worse (§2, §4.3).

Whether and how to change `min_samples`, and which noise convention to
adopt, remain open decisions for a separate brief, per this one's own scope.
