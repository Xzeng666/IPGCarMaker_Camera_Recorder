#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p wheels
python3 -m pip download -r requirements-build.txt -d wheels
echo "Offline wheelhouse prepared in: $PWD/wheels"
