#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -x .venv/bin/python ]]; then
  echo "[1/3] Creating virtual environment..."
  python3 -m venv .venv
else
  echo "[1/3] Reusing existing virtual environment..."
fi

if .venv/bin/python -c 'import numpy, cv2' >/dev/null 2>&1; then
  echo "[2/3] Core dependencies already available; skipping pip install."
else
  echo "[2/3] Installing core dependencies..."
  if compgen -G 'wheels/*' >/dev/null; then
    .venv/bin/python -m pip install --no-index --find-links wheels -r requirements-core.txt
  else
    .venv/bin/python -m pip install -r requirements-core.txt
  fi
fi

echo "[3/3] Starting CarMaker recorder CLI..."
exec .venv/bin/python run.py --config config.json
