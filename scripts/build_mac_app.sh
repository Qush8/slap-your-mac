#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export COPYFILE_DISABLE=1

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source ".venv/bin/activate"
else
  echo "Create a venv first: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

pip install -q -r requirements-build.txt
rm -rf build dist
pyinstaller slap-your-mac.spec
echo ""
echo "Built: $ROOT/dist/SlapYourMac.app"
echo "Drag it to Applications or zip dist/SlapYourMac.app for sharing."
