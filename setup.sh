#!/usr/bin/env bash
# setup.sh — one-shot environment setup for DSEL demo
#
# What this does:
#   1. Creates a Python virtualenv and installs dependencies
#   2. Shallow-clones FreeCAD (the demo corpus) into ./freecad-src
#   3. Indexes FreeCAD into .cis/index.db using the hashing embedding backend
#      (no GPU / no model download required — deterministic bag-of-words)
#
# Run once per machine. After this, `python demo.py` works offline.
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# Optional env overrides:
#   FREECAD_CLONE_DIR   path to clone FreeCAD into  (default: ./freecad-src)
#   CIS_DATA_DIR        path for index.db            (default: ./.cis)
#   PYTHON              python binary to use         (default: python3)

set -euo pipefail

PYTHON="${PYTHON:-python3}"
FREECAD_CLONE_DIR="${FREECAD_CLONE_DIR:-./freecad-src}"
CIS_DATA_DIR="${CIS_DATA_DIR:-./.cis}"
VENV_DIR="./venv"

echo "[setup] Using Python: $($PYTHON --version)"

# 1. Virtualenv
if [ ! -d "$VENV_DIR" ]; then
    echo "[setup] Creating virtualenv at $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
echo "[setup] Installing dependencies (this may take a minute)..."
pip install --quiet --upgrade pip
# Core deps only — torch/sentence-transformers are optional (we use the hashing backend)
pip install --quiet networkx tree-sitter pynput

# 2. Clone FreeCAD
if [ ! -d "$FREECAD_CLONE_DIR/.git" ]; then
    echo "[setup] Cloning FreeCAD (shallow, ~200 MB)..."
    git clone --depth=1 https://github.com/FreeCAD/FreeCAD.git "$FREECAD_CLONE_DIR"
else
    echo "[setup] FreeCAD already cloned at $FREECAD_CLONE_DIR, skipping."
fi

# 3. Index into SQLite
mkdir -p "$CIS_DATA_DIR"
echo "[setup] Indexing FreeCAD source → $CIS_DATA_DIR/index.db"
echo "        (454 K artifacts, takes ~5–15 min depending on hardware)"

CIS_EMBEDDING_BACKEND=hashing \
CIS_DATA_DIR="$CIS_DATA_DIR" \
CIS_REPOSITORY_PATH="$FREECAD_CLONE_DIR" \
CIS_REPOSITORY_NAME=freecad \
    "$PYTHON" -m src.ingestion.cli

echo ""
echo "[setup] Done. Run the demo with:"
echo "        source $VENV_DIR/bin/activate && python demo.py"
