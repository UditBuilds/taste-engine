#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
VENV="$HOME/.venvs/taste-engine"
cd /mnt/c/Users/uditk/Projects/taste-engine
VIRTUAL_ENV="$VENV" uv pip install -e . --no-deps
"$VENV/bin/python" -c "import taste_engine, sys; print('taste_engine', taste_engine.__version__, 'on', sys.version.split()[0])"
