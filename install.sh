#!/usr/bin/env bash
# Eye Break — installer for macOS
# Idempotent: safe to run multiple times. Installs/refreshes everything.
#
# What it does:
#   1. Verifies macOS + finds a Python with PyObjC AppKit
#   2. Upgrades PyObjC to >=11 if needed (older versions crash on macOS 26)
#   3. pip-installs rumps (menu bar library)
#   4. Copies eye_break.py + eye_break_menu.py + uninstall.sh
#   5. Generates launchd plists:
#         com.mukesh.eyebreak       — popup, StartCalendarInterval, fires every N min
#         com.mukesh.eyebreak.menu  — menu bar app, KeepAlive, RunAtLoad
#   6. Loads both jobs, launches the menu bar icon immediately

set -euo pipefail

INSTALL_DIR="$HOME/Library/EyeBreak"
PLIST_DIR="$HOME/Library/LaunchAgents"
POPUP_PLIST="$PLIST_DIR/com.mukesh.eyebreak.plist"
MENU_PLIST="$PLIST_DIR/com.mukesh.eyebreak.menu.plist"
LABEL_POPUP="com.mukesh.eyebreak"
LABEL_MENU="com.mukesh.eyebreak.menu"
USER_DOMAIN="gui/$(id -u)"

# 1. Pre-flight: macOS only
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: macOS only (detected $(uname -s))"
    exit 1
fi

# 2. Find a Python with PyObjC AppKit
echo "Finding a Python with PyObjC AppKit..."
CANDIDATES=(
    "${EYE_BREAK_PYTHON:-}"
    "$HOME/anaconda3/bin/python3"
    "$HOME/miniconda3/bin/python3"
    "$HOME/miniforge3/bin/python3"
    "/opt/homebrew/bin/python3.13"
    "/opt/homebrew/bin/python3.12"
    "/opt/homebrew/bin/python3.11"
    "/usr/bin/python3"
)

PYTHON3=""
for cand in "${CANDIDATES[@]}"; do
    [[ -z "$cand" ]] && continue
    [[ ! -x "$cand" ]] && continue
    if "$cand" -c "from AppKit import NSApplication, NSWindow; from Foundation import NSObject" 2>/dev/null; then
        PYTHON3="$cand"
        echo "  ✓ Using $PYTHON3"
        break
    fi
done

if [[ -z "$PYTHON3" ]]; then
    echo ""
    echo "ERROR: no Python with PyObjC AppKit found."
    echo ""
    echo "Eye Break needs PyObjC. Easiest source: Anaconda or Miniconda."
    echo ""
    echo "  brew install --cask miniconda"
    echo "  ~/miniconda3/bin/pip install pyobjc rumps"
    echo ""
    echo "Then re-run this installer."
    exit 1
fi

# 2b. Ensure PyObjC version >= 11 (older versions crash on macOS 26+)
PYOBJC_VER="$("$PYTHON3" -c 'import objc; print(objc.__version__)' 2>/dev/null || echo 0)"
PYOBJC_MAJOR="$(echo "$PYOBJC_VER" | cut -d. -f1)"
if [[ -z "$PYOBJC_MAJOR" ]] || [[ "$PYOBJC_MAJOR" -lt 11 ]]; then
    echo "  ⚠  PyObjC $PYOBJC_VER detected (older versions crash on macOS 26)."
    echo "  Upgrading PyObjC..."
    "$PYTHON3" -m pip install --upgrade --quiet pyobjc 2>&1 | tail -3
    NEW_VER="$("$PYTHON3" -c 'import objc; print(objc.__version__)')"
    echo "  ✓ PyObjC upgraded to $NEW_VER"
fi

# 2c. Ensure rumps is available (menu bar library)
if ! "$PYTHON3" -c "import rumps" 2>/dev/null; then
    echo "  Installing rumps (menu bar library)..."
    "$PYTHON3" -m pip install --upgrade --quiet rumps 2>&1 | tail -3
    echo "  ✓ rumps installed"
fi

# 3. Locate source files (handle local clone or curl|bash via raw URL)
if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/eye_break.py" ]]; then
    SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SRC_MODE="local"
else
    SRC_MODE="remote"
    REPO_RAW="${EYE_BREAK_REPO_RAW:-https://raw.githubusercontent.com/mukesh-bansal/eye-break/main}"
    SRC_DIR="$(mktemp -d)"
    echo "Fetching files from $REPO_RAW ..."
    for f in eye_break.py eye_break_menu.py uninstall.sh; do
        curl -fsSL "$REPO_RAW/$f" -o "$SRC_DIR/$f"
    done
fi

# 4. Install files
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/eye_break.py"      "$INSTALL_DIR/eye_break.py"
cp "$SRC_DIR/eye_break_menu.py" "$INSTALL_DIR/eye_break_menu.py"
cp "$SRC_DIR/uninstall.sh"      "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/"eye_break*.py "$INSTALL_DIR/uninstall.sh"

# 5. Default config (don't overwrite if exists)
INTERVAL_DEFAULT="${EYE_BREAK_INTERVAL_MIN:-10}"
if [[ ! -f "$INSTALL_DIR/config.json" ]]; then
    cat > "$INSTALL_DIR/config.json" <<EOF
{
  "duration_seconds": 60,
  "interval_minutes": $INTERVAL_DEFAULT,
  "active_hours": {"start": 7, "end": 23},
  "play_sound": true
}
EOF
fi

# 6. Generate the popup launchd plist with calendar-aligned firing
mkdir -p "$PLIST_DIR"
INTERVAL_MIN="$("$PYTHON3" -c "import json; print(json.load(open('$INSTALL_DIR/config.json'))['interval_minutes'])")"
MINUTE_ENTRIES="$("$PYTHON3" -c "
m = $INTERVAL_MIN
if 60 % m != 0:
    m = 10
for v in range(0, 60, m):
    print(f'        <dict><key>Minute</key><integer>{v}</integer></dict>')
")"

cat > "$POPUP_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL_POPUP</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>$INSTALL_DIR/eye_break.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
$MINUTE_ENTRIES
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/stderr.log</string>
</dict>
</plist>
EOF

# 7. Generate the menu bar agent plist (KeepAlive, RunAtLoad)
cat > "$MENU_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL_MENU</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>$INSTALL_DIR/eye_break_menu.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/menu.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/menu.stderr.log</string>
</dict>
</plist>
EOF

# 8. Reload both launchd jobs
for plist in "$POPUP_PLIST" "$MENU_PLIST"; do
    launchctl bootout "$USER_DOMAIN" "$plist" 2>/dev/null || true
    launchctl bootstrap "$USER_DOMAIN" "$plist"
done

# Note: We DO load the popup job during install (so the user gets popups
# from the start). The menu bar app's "OFF" toggle unloads it.

echo ""
echo "✓ Eye Break installed."
echo "  Mode:        $SRC_MODE"
echo "  Files:       $INSTALL_DIR/"
echo "  Popup plist: $POPUP_PLIST"
echo "  Menu plist:  $MENU_PLIST"
echo "  Python:      $PYTHON3"
echo "  Schedule:    every $INTERVAL_MIN minutes on the wall clock"
echo "  Duration:    60s on screen"
echo "  Active:      7am – 11pm"
echo ""
echo "Look at your menu bar (top-right of screen). You should see a 👁 icon."
echo "Click it to: enable/disable, test now, change interval/duration/hours."
echo ""
echo "If you don't see the icon, check:  $INSTALL_DIR/menu.stderr.log"
