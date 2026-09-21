# Listening test: does cluster shape affect rediscovery?

**Date run:** 2026-09-16
**Written up:** 2026-09-19
**Status:** two arms completed, one arm written but never marked. Reported as incomplete rather than dropped.

---

## 1. Hypothesis

Playlists generated from single-artist clusters would surface fewer genuinely forgotten tracks than playlists from mixed clusters, because an artist-shaped cluster is effectively just that artist's back catalogue ranked by familiarity.

If true, the fix would be to make clusters less artist-shaped — which was the direction the surrounding work was already pursuing (Last.fm tag enrichment, the embedding-mode ARI remeasure).

**The hypothesis was proposed by the assistant, not the user. It was wrong.**

---

## 2. Protocol

Playlists were written live to the author's real YouTube account through the tool's own write path — not simulated, not dry-run. Each track was then played and marked into exactly one of three categories:

| mark | meaning |
|---|---|
| forgot & glad | had genuinely forgotten it, and wanted it back |
| forgot for a reason | had genuinely forgotten it, and it deserved to stay forgotten |
| never left rotation | still actively listened to — a selection failure for a rediscovery tool |

"Genuinely forgotten" = the first two categories combined. That is the number reported below.

The marking was done by the author, in one sitting per playlist, in playlist order.

---

## 3. Results

| cluster | shape | tracks | marked | genuinely forgotten |
|---|---|---:|---:|---|
| Joji | single-artist | 12 | 11 | **7 of 11** (4 of them "glad") |
| Lil Baby / Lil Peep / Chris Brown | mixed | 13 | 13 | **3 of 13** |
| T-Series / Pritam / Sony Music India | mixed, multi-language | 21 | 0 | not completed |

**On the mixed arm's shape:** the assistant initially read this cluster as Lil Peep–dominated with a misleading three-name label, and was corrected by the author's own count — 5 Lil Peep and 2 Lil Baby of 13, so maximum artist share is roughly 38%, well under the 80% threshold used elsewhere in this project. It is genuinely mixed. The comparison is valid.

**On the third arm:** written and verified, never marked. A listening-fatigue confound was identified before it was run — 21 tracks against the other arms' 12 and 13, with late-position tracks being exactly where rediscoveries were expected — and the arm was deliberately scheduled separately for that reason. It was not returned to.

---

## 4. What this refutes

The single-artist cluster surfaced more forgotten tracks than the mixed one, not fewer. The hypothesis is refuted by its own test.

More usefully, it rules out the direction rather than just the hypothesis: if cluster shape were the variable, making clusters less artist-shaped would improve rediscovery. It isn't, so it wouldn't. The Last.fm enrichment and the embedding-mode work being pursued at the time would not have fixed the problem they were aimed at.

---

## 5. What it pointed at instead

With cluster shape eliminated, the remaining explanation is selection.

`--mode rediscover` excludes the author's **global** top-50 most-played tracks. That exclusion barely operates at cluster level: the mixed cluster carries roughly 250 plays spread across 48 tracks, so few or none of its entries appear in a global top-50, nothing is filtered, and the playlist ships the cluster's most-played tracks — precisely the ones still in rotation.

This is corroborated by the dormancy-signal measurement (`reports/dormancy_signals.md`, computed 2026-09-16): across all 10 qualifying clusters, 197 of 198 shipped tracks (99.5%) had been played within the previous 30 days.

The underlying mechanism is in the scoring itself. With `MIN_SCORE = 0.5` and a 14-day half-life, a single play falls below threshold in about 6.6 days, so the score is a recency measure far more than a dormancy one.

---

## 6. Limitations

- **Two completed arms.** Not a powered comparison. It refutes a directional claim; it does not quantify an effect.
- **One rater, unblinded, self-marked.** The rater proposed neither hypothesis but knew which arm was which while marking.
- **No pre-registered threshold.** No "forgotten rate below X kills the hypothesis" was written down before the test. The refutation rests on the direction of the difference, not on clearing a stated bar.
- **Marks are not stored per-track in this repository.** Joji's are recorded as counts plus partial per-track detail; the mixed arm's as a count only. Twenty-four tracks carry human judgments in total.
- **Single library, single listener.** As with everything else in this project.

---

## 7. Consequence

Cluster shape was removed from the list of things worth changing. Attention moved to the selection rule and the scoring half-life, and — together with the dormancy probe (`reports/dormancy_probe.md`) and the genre-coverage measurement (`reports/genre_coverage.md`), contributed to `BACKFILL_ENABLED` being set to `False`.
