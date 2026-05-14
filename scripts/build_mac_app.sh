#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export COPYFILE_DISABLE=1

PYTHON="${PYTHON:-python3}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Creating .venv + installing runtime deps..."
  "$PYTHON" -m venv .venv
fi
# shellcheck source=/dev/null
source ".venv/bin/activate"

pip install -q -r requirements.txt
pip install -q -r requirements-build.txt
rm -rf build dist
pyinstaller slap-your-mac.spec
echo ""
echo "Built: $ROOT/dist/SlapYourMac.app"
echo "Drag it to Applications or zip dist/SlapYourMac.app for sharing."
