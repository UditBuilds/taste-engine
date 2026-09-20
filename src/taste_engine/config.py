"""Paths and tunable parameters.

Every knob the model depends on lives here so the evaluation in `evaluate.py`
can sweep it without editing logic.
"""
from __future__ import annotations

import os
from datetime import timezone, timedelta
from pathlib import Path

# --- paths -----------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.environ.get("TASTE_DB", DATA_DIR / "taste.db"))
ARTIFACTS_DIR = DATA_DIR / "artifacts"

# Google Takeout lays the export out under this fixed subtree.
TAKEOUT_DIR = RAW_DIR / "Takeout" / "YouTube and YouTube Music"
WATCH_HISTORY_HTML = TAKEOUT_DIR / "history" / "watch-history.html"
PLAYLISTS_DIR = TAKEOUT_DIR / "playlists"
PLAYLISTS_CSV = PLAYLISTS_DIR / "playlists.csv"
LIBRARY_SONGS_CSV = TAKEOUT_DIR / "music (library and uploads)" / "music library songs.csv"

# --- time ------------------------------------------------------------------
# Takeout writes local wall-clock time with a bare abbreviation ("IST"), which
# is ambiguous globally. This export is from an Asia/Kolkata account.
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")

# --- OAuth (Phase 4 write-back) --------------------------------------------
# Desktop-app client downloaded from Google Cloud; never committed.
CREDENTIALS_PATH = Path(os.environ.get("YT_CREDENTIALS", REPO_ROOT / "credentials.json"))
TOKEN_PATH = Path(os.environ.get("YT_TOKEN", REPO_ROOT / "token.json"))
# Read+write. `youtube.readonly` cannot create playlists, so it is not enough.
OAUTH_SCOPES = ["https://www.googleapis.com/auth/youtube"]

# --- API quota -------------------------------------------------------------
# Google's per-project ceiling is 10,000 units/day and cannot be purchased.
QUOTA_HARD_LIMIT = 10_000
QUOTA_DAILY_CAP = int(os.environ.get("YT_DAILY_QUOTA_CAP", 8_000))

# Documented unit costs (https://developers.google.com/youtube/v3/determine_quota_cost)
QUOTA_COSTS = {
    "videos.list": 1,
    "channels.list": 1,
    "playlists.insert": 50,
    "playlists.delete": 50,
    "playlistItems.insert": 50,
    "playlistItems.list": 1,
    "search.list": 100,
}
VIDEOS_LIST_BATCH = 50  # max IDs accepted per videos.list call

# --- scoring ---------------------------------------------------------------
# Selected by NESTED tuning on the rediscovery task: swept on the two earliest
# usable splits, reported on three later ones the selection never saw. On
# canonical songs with non-music filtered it picks 14 days, for +128% mean
# nDCG@20 over the most-played baseline, winning 3/3 held-out splits - an
# effect too large to ignore and, at n=3, too small a sample to certify
# (sign-test floor 0.125).
# Reproduce with: scripts/run.sh scripts/canonical_impact.py
RECENCY_HALF_LIFE_DAYS = 14.0

# --- evaluation ------------------------------------------------------------
# Temporal hold-out boundary: train strictly before, test on/after.
EVAL_SPLIT_DATE = "2026-06-01"
# k=50 over a 30-day horizon. The brief's precision@20 over the full remaining
# 105 days saturates: the baseline scores 1.00 there, which ranks nothing.
EVAL_K = 50
EVAL_TEST_DAYS = 30
# k for the rediscovery task (evaluate_rediscovery and its callers) - distinct
# from EVAL_K, which is the replay task's k.
REDISCOVERY_K = 20
# How many favourites the rediscovery hold-out removes. The writer's
# `--mode rediscover` removes the same set, so the playlist the tool ships is
# the task the evaluation actually measures.
EXCLUDE_TOP = 50

# --- YouTube constants -----------------------------------------------------
MUSIC_CATEGORY_ID = "10"

# --- optional strict music filter (default OFF) -----------------------------
# Measured contamination in the music set is ~5.6%, and 121 of the 127
# title/duration-flagged songs were admitted by `categoryId` ALONE - guitar
# tutorials, movie promos and a 63-minute vlog, all uploaded by channels
# YouTube files under category 10. The heuristics admit 6 between them.
# Turning this on drops categoryId-only songs that look like non-songs.
# ON by default. It removes 202 songs (6.4%) carrying 220 plays - a mean of
# 1.1 plays each - and the headline is unchanged to four decimals. That null
# was verified rather than assumed: the evaluated pool does shrink, by 123-163
# songs at each held-out split, and the best rank any removed song reaches is
# 209 of ~2,000. The contamination is real and sits far below top-k.
# Reproduce: scripts/run.sh scripts/verify_strict_null.py
STRICT_MUSIC = True
STRICT_MAX_SECONDS = 15 * 60
STRICT_MIN_SECONDS = 45

# --- backfill master switch (Build Brief 5) ---------------------------------
# First live dry run (Joji's cluster) backfilled 3 Playboi Carti tracks and 1
# Don Toliver track, admitted by genre 'pop' at distances 0.55-0.70 - well
# inside the 1.0 ceiling below, so no threshold fixes this. Both backfill
# signals measure the wrong quantity: topicCategories tags 'pop' on 2,176 of
# 2,918 canonical tracks and 'hip hop' on 1,695 (not discriminative - see
# reports/backfill_plan.md), and the embedding space is a sentence-
# transformer over title+artist text, not audio. Off by default until one of
# those inputs improves; `--backfill` re-enables it for a single run
# (writer.plan(..., backfill=True)). FLOOR still applies either way - see
# writer._select_with_backfill.
BACKFILL_ENABLED = False

# --- backfill floor, length and genre guard (Build Brief 4) -----------------
# A --cluster-name request can run out of eligible material long before a
# fixed-size playlist fills: measured on this library, T-Series (492 tracks)
# has only 22 scoring >= 0.5 after the rediscovery favourites exclusion, and
# Travis Scott (84 tracks) has 21 - see scripts/backfill_report.py. Padding
# with material the model itself scores below this floor would be the writer
# contradicting the ranker. The earlier fix backfilled from the nearest
# cluster by embedding centroid, which pulled musically unrelated tracks
# (T-Series padded with Travis Scott) - see briefs/backfill_constraint.md.
# Replaced by three rules, implemented entirely in writer.py:
#   FLOOR  - a cluster with fewer than MIN_CLUSTER_NATIVE eligible members
#            generates no playlist at all, rather than a thin one.
#   LENGTH - target length = floor(native / (1 - MAX_BACKFILL_SHARE)), so the
#            backfill share is capped by construction, never by truncating a
#            fixed request after the fact.
#   GUARD  - a backfill candidate must share a tidied genre label
#            (embed.tidy_genres) with the cluster's modal genre; if not
#            enough such candidates exist the playlist comes back short - the
#            guard is never relaxed to hit length.
# Reachability under this rule is measured in reports/backfill_plan.md.
MIN_SCORE = 0.5
MIN_CLUSTER_NATIVE = 12
MAX_BACKFILL_SHARE = 0.25

# --- backfill ranking and ceiling (briefs/backfill_rank.md) -----------------
# GUARD (above) only filters the candidate pool by genre; it never said which
# genre-matching candidate to prefer, and score ranked what was left - but
# score does not depend on which cluster is asking, so every shallow
# cluster's backfill collapsed onto the same handful of globally top-scored
# tracks (measured: 10 distinct tracks filling 52 slots across ten
# playlists, several byte-identical - reports/backfill_plan.md). RANK
# replaces score with cosine distance to the *requesting* cluster's own
# centroid (writer._select_with_backfill), ascending. That needs no constant
# here - it is a sort order, not a threshold.
#
# MAX_BACKFILL_DISTANCE is the one threshold RANK does need. Cosine distance
# ranges 0 (identical direction) to 2 (opposite direction); distance > 1.0
# means negative cosine similarity - the candidate points AWAY from the
# cluster's centroid, not merely far from it. That is a geometric bound, not
# a value tuned to exclude any specific track: it was fixed before measuring
# which tracks it would affect, and deliberately left at 1.0 rather than
# moved to the 0.738/1.117 gap reports/backfill_plan.md found between the
# next-worst admitted distance anywhere (0.7380) and T-Series's only
# candidate (Doja Cat, distance 1.1166, the sole genre match in its entire
# eligible pool).
#
# T-Series's modal genre (writer._modal_genre) is an exact 21-21 vote tie
# between "music of asia" and "pop" - found 2026-09-14 when it, and a sibling
# tie on Metro Boomin, made _modal_genre's tie-break depend on Python's
# per-process string hash seed (Counter.most_common(1)'s insertion-order tie
# resolving via a Python set's seed-dependent iteration order). Fixed the
# same day: _modal_genre now breaks ties deterministically at selection time
# (highest count, then alphabetically-first label), independent of hash seed
# - see its docstring. "music of asia" < "pop" alphabetically, so T-Series
# deterministically lands on "music of asia" and Doja Cat really is its only
# genre-matching candidate, not one of two live outcomes. Re-verified 10/10
# process runs stable post-fix. See reports/backfill_plan.md's "Genre
# tie-break" section for the full before/after.
#
# A candidate at or above the ceiling is dropped outright; the playlist
# comes back SHORT rather than relaxing it, exactly like GUARD does when
# nothing matches genre at all.
MAX_BACKFILL_DISTANCE = 1.0

# --- write-back retry policy -------------------------------------------------
# First live write (2026-09-13): playlistItems.insert returned 409
# SERVICE_UNAVAILABLE on the second insert. The error path only handled 403
# quotaExceeded, so it reached _insert_track as an unhandled traceback - 289
# tests passed because every mock only ever simulated the failure we predicted.
# Retried: 409, 500, 502, 503, 504, and socket/connection-level errors (the
# request never reached Google, so quota.py's own refund rule applies).
# Never retried: 403 quotaExceeded (no amount of waiting creates quota) or 401
# (an expired/revoked token needs a human, not a delay).
WRITE_RETRY_ATTEMPTS = 5
WRITE_RETRY_INITIAL_DELAY_S = 1.0
WRITE_RETRY_MAX_DELAY_S = 16.0
WRITE_RETRYABLE_STATUSES = {409, 500, 502, 503, 504}

# --- duration-based second-pass merge ---------------------------------------
# The artist-keyed canonical rule is conservative and under-merges when a label
# uploads a song under its own channel while the `- Topic` twin sits under the
# composer. Runtime settles it: two different songs called "Raabta" do not
# share a runtime to the second; a T-Series upload and its Topic twin do.
DURATION_MERGE_TOLERANCE_S = 3
