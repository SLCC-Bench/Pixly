#!/usr/bin/env bash
# Build Pixly.app and a drag-to-Applications DMG without an Apple Developer ID.
# Uses ad-hoc code signing (codesign -s -) so the bundle is locally consistent;
# users still Right-click → Open the first time (Gatekeeper).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: This script must run on macOS." >&2
  exit 1
fi

ARCH="$(uname -m)"
echo "==> Pixly macOS installer build (${ARCH})"

if [[ ! -d .venv ]]; then
  echo "==> Creating virtual environment"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing dependencies"
pip install -q --upgrade pip
pip install -q -r requirements-build.txt

VERSION="$(python -c "from screen_gif_recorder import __version__; print(__version__)")"
APP_NAME="Pixly"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="Pixly-${VERSION}-macOS-${ARCH}.dmg"
DMG_PATH="dist/${DMG_NAME}"

echo "==> Cleaning previous build"
rm -rf build dist
mkdir -p dist

echo "==> Running PyInstaller"
pyinstaller pixly.spec --noconfirm

if [[ ! -d "$APP_PATH" ]]; then
  echo "error: ${APP_PATH} was not created." >&2
  exit 1
fi

echo "==> Ad-hoc signing (no Developer ID)"
ENTITLEMENTS="packaging/entitlements.plist"
if [[ -f "$ENTITLEMENTS" ]]; then
  codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP_PATH" || \
    codesign --force --deep --sign - "$APP_PATH"
else
  codesign --force --deep --sign - "$APP_PATH"
fi

echo "==> Verifying signature"
codesign --verify --verbose=2 "$APP_PATH" || true

echo "==> Creating DMG"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp -R "$APP_PATH" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp packaging/INSTALL.txt "$STAGE/"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "Pixly ${VERSION}" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

xattr -cr "$APP_PATH" "$DMG_PATH" 2>/dev/null || true

echo ""
echo "Done."
echo "  App:  ${ROOT}/${APP_PATH}"
echo "  DMG:  ${ROOT}/${DMG_PATH}"
echo ""
echo "Distribute the DMG. Recipients should:"
echo "  1. Open the DMG and drag Pixly to Applications"
echo "  2. Right-click Pixly → Open (first launch)"
echo "  3. Grant Screen Recording (and Microphone / Accessibility if prompted)"
