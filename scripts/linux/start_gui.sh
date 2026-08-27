#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -x .venv/bin/python ]]; then
  echo "[1/3] Creating virtual environment..."
  python3 -m venv .venv
else
  echo "[1/3] Reusing existing virtual environment..."
fi

if .venv/bin/python -c 'import numpy, cv2, PySide6' >/dev/null 2>&1; then
  echo "[2/3] Dependencies already available; skipping pip install."
else
  echo "[2/3] Installing GUI dependencies..."
  if compgen -G 'wheels/*' >/dev/null; then
    .venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt
  else
    .venv/bin/python -m pip install -r requirements.txt
  fi
fi

echo "[3/3] Starting CarMaker CameraRSI Recorder GUI..."
exec .venv/bin/python run_gui.py --config config.json
