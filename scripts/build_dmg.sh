#!/usr/bin/env bash
# Build Nibble.app with py2app, ad-hoc sign it, and wrap it in a drag-to-Applications DMG.
#
#   scripts/build_dmg.sh        -> dist/Nibble.app and dist/Nibble.dmg
#
# Builds with python.org's Python 3.13 (universal2) in its own environment,
# build/venv-macos, with the versions pinned in uv.lock. uv's own Pythons can't
# be bundled by py2app (zlib is built in, and py2app expects a separate file).
# Set NIBBLE_BUILD_PYTHON to use a different framework Python.
#
# There's no Developer ID, so the app is ad-hoc signed and not notarized: see
# "Install" in the README for the one-time Gatekeeper step.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
PYTHON="${NIBBLE_BUILD_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}"
VENV="$ROOT/build/venv-macos"
APP="$ROOT/dist/Nibble.app"
DMG="$ROOT/dist/Nibble.dmg"
STAGE="$ROOT/build/dmg"
LOG="$ROOT/build/codesign.log"

if [ ! -x "$PYTHON" ]; then
    echo "Needs python.org's Python 3.13 (universal2 installer from python.org) at $PYTHON" >&2
    exit 1
fi

echo "==> Cleaning the previous build"
rm -rf "$ROOT/build/py2app" "$STAGE" "$APP" "$DMG"
mkdir -p "$ROOT/build"

echo "==> Build environment ($("$PYTHON" -V), $VENV)"
UV_PROJECT_ENVIRONMENT="$VENV" uv sync --locked --no-editable --python "$PYTHON" --python-preference only-system

echo "==> Building Nibble.app"
(cd packaging/macos && "$VENV/bin/python" setup.py py2app --dist-dir "$ROOT/dist" --bdist-base "$ROOT/build/py2app")

echo "==> Ad-hoc signing"
# Inside out, rather than codesign --deep: every binary, then each embedded
# framework as a bundle, then the app itself.
MACHO=()
while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then
        MACHO+=("$f")
    fi
done < <(find "$APP/Contents" -type f -print0)
codesign --force --sign - "${MACHO[@]}" 2>"$LOG" || { cat "$LOG"; exit 1; }
for fw in "$APP"/Contents/Frameworks/*.framework; do
    codesign --force --sign - "$fw" 2>>"$LOG" || { cat "$LOG"; exit 1; }
done
echo "    signed ${#MACHO[@]} binaries"
codesign --force --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> Architectures"
# Intel Macs are only supported if every binary has x86_64 (and Apple Silicon needs arm64).
SINGLE=0
for f in "${MACHO[@]}"; do
    archs=$(lipo -archs "$f")
    if [[ " $archs " != *" x86_64 "* || " $archs " != *" arm64 "* ]]; then
        echo "    not universal ($archs): ${f#"$APP/"}"
        SINGLE=$((SINGLE + 1))
    fi
done
echo "    $(( ${#MACHO[@]} - SINGLE )) of ${#MACHO[@]} binaries are universal (x86_64 + arm64)"

echo "==> Making the DMG"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/Nibble.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname Nibble -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG"
hdiutil verify "$DMG"

echo "==> Done"
echo "    $APP"
echo "    $DMG"
