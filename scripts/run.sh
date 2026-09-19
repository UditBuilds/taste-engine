#!/usr/bin/env bash
# Thin wrapper: run anything inside the project venv from WSL.
#   scripts/run.sh -m taste_engine.parse_takeout
#   scripts/run.sh -m pytest -q
set -euo pipefail
VENV="$HOME/.venvs/taste-engine"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO"
exec "$VENV/bin/python" "$@"
