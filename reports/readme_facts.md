# README facts - figures with no existing script

Part B2 of `briefs/readme_final.md`. Every row is a plain read-only query against the current `data/taste.db`, run through existing, unmodified functions. No config left toggled after this script returns (STRICT_MUSIC is reset to its default).

| figure | value | query |
|---|---|---|
| canonical songs / plays, STRICT_MUSIC=False | 3,119 songs / 10,539 plays | `score.scored_tracks(conn, canonical=True) with config.STRICT_MUSIC=False; len(df), df.play_count.sum()` |
| canonical songs / plays, STRICT_MUSIC=True | 2,918 songs / 10,319 plays | `score.scored_tracks(conn, canonical=True) with config.STRICT_MUSIC=True; len(df), df.play_count.sum()` |
| playlist titles repeated x3 / x2 | 1 title(s) x3, 8 title(s) x2 | `Counter(title for title, in SELECT title FROM playlists); count values == 3, count values == 2` |
| canonical: % played exactly once | 61.8% | `scored_tracks(canonical=True); (play_count == 1).mean()` |
| canonical: top-20 share of plays | 11.7% | `scored_tracks(canonical=True); sorted play_count.head(20).sum() / play_count.sum()` |
| raw (uncollapsed): % played exactly once | 61.6% | `scored_tracks(canonical=False); (play_count == 1).mean() - the frame the '115 plays / 5.75x / 1.57x' paragraph is actually on` |
| raw (uncollapsed): top-20 share of plays | 9.0% | `scored_tracks(canonical=False); sorted play_count.head(20).sum() / play_count.sum()` |
| distinct genre labels, raw (untidied topicCategories) | 36 | `scored_tracks(canonical=True)['genres']; size of the union of every row's raw label list` |
| distinct genre labels, tidied (generic labels dropped) | 32 | `scored_tracks(canonical=True)['genres'].map(embed.tidy_genres); size of the union across all rows` |
| tests/ total collected | 538 tests collected in 2.43s | `pytest --collect-only -q; last non-blank stdout line` |
| tests/test_writer.py test count | 85 | `grep -c "def test_" tests/test_writer.py` |
