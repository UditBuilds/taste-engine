#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
VIRTUAL_ENV="$HOME/.venvs/taste-engine" uv pip install matplotlib nbformat ipykernel jupyter-client
