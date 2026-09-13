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
# canonical songs that picks 30 days, for +121% mean nDCG@20 over the
# most-played baseline, winning 3/3 held-out splits - an effect too large to
# ignore and, at n=3, too small a sample to certify (sign-test floor 0.125).
# Reproduce with: scripts/run.sh scripts/canonical_impact.py
RECENCY_HALF_LIFE_DAYS = 30.0

# --- evaluation ------------------------------------------------------------
# Temporal hold-out boundary: train strictly before, test on/after.
EVAL_SPLIT_DATE = "2026-06-01"
# k=50 over a 30-day horizon. The brief's precision@20 over the full remaining
# 105 days saturates: the baseline scores 1.00 there, which ranks nothing.
EVAL_K = 50
EVAL_TEST_DAYS = 30

# --- YouTube constants -----------------------------------------------------
MUSIC_CATEGORY_ID = "10"
