#!/usr/bin/env bash
# Creates the Python 3.11 venv for taste-engine.
# venv lives on the WSL native filesystem (fast); code lives on /mnt/c (visible from Windows).
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
VENV="$HOME/.venvs/taste-engine"

uv python install 3.11
uv venv --python 3.11 "$VENV"
# CPU-only torch: the embedding workload is ~3k short strings, GPU buys nothing
# and this avoids a ~2GB CUDA download.
VIRTUAL_ENV="$VENV" uv pip install \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match \
  pandas lxml numpy scikit-learn pytest python-dotenv \
  google-api-python-client google-auth-oauthlib google-auth-httplib2 \
  sentence-transformers

"$VENV/bin/python" -c "import sys,pandas,lxml,sklearn,numpy; print('python', sys.version.split()[0]); print('pandas', pandas.__version__); print('sklearn', sklearn.__version__)"
echo "SETUP_OK $VENV"
