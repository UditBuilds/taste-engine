#!/usr/bin/env bash
# Thin wrapper: run anything inside the project venv from WSL.
#   scripts/run.sh -m taste_engine.parse_takeout
#   scripts/run.sh -m pytest -q
set -euo pipefail
VENV="$HOME/.venvs/taste-engine"
REPO="/mnt/c/Users/uditk/Projects/taste-engine"
cd "$REPO"
exec "$VENV/bin/python" "$@"
