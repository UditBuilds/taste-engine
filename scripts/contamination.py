"""How much of the "music" set is not music, and which signal let it in?

The README defends `is_music` as the union of heuristics and `categoryId`. That
claim only stands if the union is not admitting substantial non-music, so this
measures it rather than asserting it.

`categoryId` is used as the reference label where YouTube provides one. It is
not ground truth — §5 documents 53 cases where it is wrong — but it is the only
independent label available, and for *finding* contamination it is the right
direction: a song the heuristics admit and categoryId rejects is exactly the
population worth inspecting.

Run:  scripts/run.sh scripts/contamination.py
"""
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd

from taste_engine.classify import HEURISTIC_SIGNALS, SIGNAL_LABELS
from taste_engine.db import connect
from taste_engine.score import scored_tracks

SAMPLE_N = 100
SEED = 0

# Title/duration patterns that are not songs. Used only to *flag* rows for
# inspection and to sanity-check the categoryId signal, never to relabel.
NOT_A_SONG = re.compile(
    r"\b(tutorial|lesson|how to|guitar (chords|lesson)|karaoke|"
    r"full (movie|episode|album)|episode|webseries|web series|podcast|"
    r"interview|reaction|vlog|gameplay|trailer|dialogue|speech|"
    r"non stop|jukebox|mashup of|all songs|audio ?book)\b",
    re.I,
)


def iso_seconds(duration):
    if not isinstance(duration, str):
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return None
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


conn = connect()
songs = scored_tracks(conn)          # canonical, music-labelled
meta = pd.read_sql(
    "SELECT video_id, category_id, duration, title AS api_title FROM video_metadata",
    conn,
)
songs = songs.merge(meta, on="video_id", how="left")
# `scored_tracks` drops the per-signal flags; re-attach them for the
# representative upload of each canonical song.
from taste_engine.classify import classify

sig_cols = ["video_id"] + [c for c in HEURISTIC_SIGNALS]
songs = songs.merge(
    classify(conn)[sig_cols].drop_duplicates("video_id"),
    on="video_id", how="left", suffixes=("", "_sig"),
)
for c in HEURISTIC_SIGNALS:
    src = c + "_sig" if c + "_sig" in songs.columns else c
    songs[c] = songs[src].fillna(False).astype(bool)
songs["seconds"] = songs["duration"].map(iso_seconds)
songs["api_says_music"] = songs["category_id"].eq("10")
songs["api_resolved"] = songs["category_id"].notna()
songs["suspicious_title"] = songs["title"].fillna("").map(
    lambda t: bool(NOT_A_SONG.search(str(t)))
)
# A song is 2-8 minutes. Twenty minutes is a mix, a set or a tutorial.
songs["over_15min"] = songs["seconds"].fillna(0) > 15 * 60
songs["under_45s"] = (songs["seconds"].fillna(999) < 45) & songs["seconds"].notna()

total = len(songs)
print("=" * 78)
print(f"1. THE MUSIC SET — {total:,} canonical songs")
print("=" * 78)
resolved = songs[songs["api_resolved"]]
print(f"  resolved by the API        {len(resolved):>6,}")
print(f"  categoryId == 10 (music)   {int(songs.api_says_music.sum()):>6,}  "
      f"({songs.api_says_music.mean():.1%})")
print(f"  categoryId says NOT music  "
      f"{int((~songs.api_says_music & songs.api_resolved).sum()):>6,}")
print(f"  unresolved (deleted etc.)  {int((~songs.api_resolved).sum()):>6,}")

print("\n" + "=" * 78)
print("2. WHICH SIGNAL ADMITS NON-MUSIC?")
print("=" * 78)
print("  'only signal' = songs this signal alone admitted; without it they")
print("  would not be in the set at all. That is where a permissive rule shows.\n")
rows = []
for sig in HEURISTIC_SIGNALS:
    if sig not in songs.columns:
        continue
    fired = songs[songs[sig]]
    others = [s for s in HEURISTIC_SIGNALS if s != sig and s in songs.columns]
    alone = fired[~fired[others].any(axis=1) & ~fired["api_says_music"]]
    bad = fired[fired["api_resolved"] & ~fired["api_says_music"]]
    rows.append({
        "signal": SIGNAL_LABELS[sig],
        "songs": len(fired),
        "api_not_music": len(bad),
        "pct_bad": round(len(bad) / len(fired) * 100, 1) if len(fired) else 0.0,
        "only_signal": len(alone),
        "suspicious_title": int(fired["suspicious_title"].sum()),
        "over_15min": int(fired["over_15min"].sum()),
    })
api_only = songs[songs["api_says_music"] & ~songs[list(HEURISTIC_SIGNALS)].any(axis=1)]
rows.append({
    "signal": "categoryId == 10 only",
    "songs": len(api_only), "api_not_music": 0, "pct_bad": 0.0,
    "only_signal": len(api_only),
    "suspicious_title": int(api_only["suspicious_title"].sum()),
    "over_15min": int(api_only["over_15min"].sum()),
})
print(pd.DataFrame(rows).to_string(index=False))

print("\n" + "=" * 78)
print("3. WHICH PLAYLISTS CONTRIBUTE NON-MUSIC?")
print("=" * 78)
from taste_engine.redact import alias, aliases_for

mapping = aliases_for(conn)
pl = pd.read_sql(
    "SELECT DISTINCT playlist_name, video_id FROM playlist_tracks", conn
)
bad_ids = set(songs.loc[songs["api_resolved"] & ~songs["api_says_music"], "video_id"])
all_ids = set(songs["video_id"])
grp = (
    pl[pl.video_id.isin(all_ids)]
    .assign(bad=lambda d: d.video_id.isin(bad_ids))
    .groupby("playlist_name")
    .agg(songs_in_set=("video_id", "size"), api_not_music=("bad", "sum"))
)
grp["pct"] = (grp.api_not_music / grp.songs_in_set * 100).round(1)
grp = grp[grp.songs_in_set >= 5].sort_values("pct", ascending=False).head(10)
grp.index = [alias(n, mapping) for n in grp.index]
print(grp.to_string())

print("\n" + "=" * 78)
print(f"4. RANDOM SAMPLE OF {SAMPLE_N}, MOST SUSPICIOUS FIRST")
print("=" * 78)
sample = songs.sample(min(SAMPLE_N, total), random_state=SEED).copy()
sample["sig"] = sample.apply(
    lambda r: "".join([
        "T" if r.get("topic_channel") else ".",
        "V" if r.get("vevo_channel") else ".",
        "H" if r.get("music_host") else ".",
        "P" if r.get("in_playlist") else ".",
        "L" if r.get("in_library") else ".",
        "A" if r.get("api_says_music") else ("-" if r.get("api_resolved") else "?"),
    ]),
    axis=1,
)
sample["flag_score"] = (
    (~sample.api_says_music & sample.api_resolved).astype(int) * 2
    + sample.suspicious_title.astype(int) * 2
    + sample.over_15min.astype(int)
    + sample.under_45s.astype(int)
)
out = sample.sort_values("flag_score", ascending=False)
n_flagged = int((out.flag_score > 0).sum())
print(f"  flagged by at least one signal: {n_flagged}/{len(out)}")
print("  flags = Topic Vevo Host Playlist Library Api  (A=music, -=not, ?=unresolved)\n")
for _, r in out.head(25).iterrows():
    mins = f"{int(r.seconds // 60)}m" if r.seconds == r.seconds and r.seconds else "  ?"
    print(f"  {r['sig']}  {mins:>4}  {str(r['title'])[:58]}")
print("\n" + "=" * 78)
print("5. CONTAMINATION ESTIMATE OVER ALL 3,143 SONGS")
print("=" * 78)
not_song = songs["suspicious_title"] | songs["over_15min"]
api_bad = songs["api_resolved"] & ~songs["api_says_music"]
combined = not_song | api_bad
print(f"  categoryId says not music        {int(api_bad.sum()):>5,}  "
      f"({api_bad.mean():.1%})")
print(f"  title looks like a non-song      "
      f"{int(songs.suspicious_title.sum()):>5,}  ({songs.suspicious_title.mean():.1%})")
print(f"  longer than 15 minutes           {int(songs.over_15min.sum()):>5,}  "
      f"({songs.over_15min.mean():.1%})")
print(f"  shorter than 45 seconds          {int(songs.under_45s.sum()):>5,}  "
      f"({songs.under_45s.mean():.1%})")
print(f"  ANY of the above                 {int(combined.sum()):>5,}  "
      f"({combined.mean():.1%})  <- upper bound")
print()
print("  Of the songs flagged by title or duration, how many did each")
print("  signal admit *alone*:")
for sig in HEURISTIC_SIGNALS:
    others = [s2 for s2 in HEURISTIC_SIGNALS if s2 != sig]
    alone = songs[sig] & ~songs[others].any(axis=1) & ~songs["api_says_music"]
    print(f"    {SIGNAL_LABELS[sig]:<32}{int((alone & not_song).sum()):>4}")
api_alone = songs["api_says_music"] & ~songs[list(HEURISTIC_SIGNALS)].any(axis=1)
print(f"    {'categoryId == 10 alone':<32}{int((api_alone & not_song).sum()):>4}"
      "   <- the permissive one")

path = REPO_ROOT / "data" / "contamination_sample.csv"
out[["video_id", "title", "channel", "sig", "seconds", "category_id",
     "flag_score"]].to_csv(path, index=False)
print(f"\n  full sample written to {path} (gitignored)")

conn.close()
