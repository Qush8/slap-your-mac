#!/usr/bin/env bash
# Fresh PyInstaller macOS bundle + readable zip under releases/ (xattr strip first).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/build_mac_app.sh"
xattr -cr "$ROOT/dist/SlapYourMac.app" 2>/dev/null || true
mkdir -p "$ROOT/releases"
rm -f "$ROOT/releases/SlapYourMac-mac.zip"
(cd "$ROOT/dist" && zip -rq "$ROOT/releases/SlapYourMac-mac.zip" SlapYourMac.app)
echo ""
echo "Friend-ready archive: $ROOT/releases/SlapYourMac-mac.zip"
