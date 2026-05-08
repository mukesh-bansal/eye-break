#!/usr/bin/env bash
# Eye Break — installer for macOS
# Idempotent: safe to run multiple times. Installs/refreshes everything.
#
# What it does:
#   1. Verifies macOS + finds a Python with PyObjC (native AppKit, works on macOS 26+)
#   2. Installs eye_break.py (the popup) + eyebreak (the CLI) + uninstall.sh
#   3. Generates ~/Library/LaunchAgents/com.mukesh.eyebreak.plist
#   4. Loads launchd and runs `eyebreak status`
#   5. Symlinks `eyebreak` into PATH so you can just type `eyebreak` from anywhere

set -euo pipefail

INSTALL_DIR="$HOME/Library/EyeBreak"
PLIST_PATH="$HOME/Library/LaunchAgents/com.mukesh.eyebreak.plist"
LABEL="com.mukesh.eyebreak"
INTERVAL_SECONDS="${EYE_BREAK_INTERVAL:-600}"

# 1. Pre-flight: macOS only
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: macOS only (detected $(uname -s))"
    exit 1
fi

# 2. Find a Python with PyObjC AppKit (need this for native UI on macOS 26+)
echo "Finding a Python with PyObjC AppKit..."
CANDIDATES=(
    "${EYE_BREAK_PYTHON:-}"
    "$HOME/anaconda3/bin/python3"
    "$HOME/miniconda3/bin/python3"
    "$HOME/miniforge3/bin/python3"
    "/opt/homebrew/bin/python3.13"
    "/opt/homebrew/bin/python3.12"
    "/opt/homebrew/bin/python3.11"
    "/usr/local/bin/python3.13"
    "/usr/local/bin/python3.12"
    "/usr/local/bin/python3.11"
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
    echo "Eye Break uses native macOS AppKit (the only thing that works reliably on macOS 26)."
    echo "The cleanest source of PyObjC is Anaconda or Miniconda:"
    echo ""
    echo "  brew install --cask miniconda"
    echo "  ~/miniconda3/bin/pip install pyobjc"
    echo ""
    echo "Or with brew Python:"
    echo "  brew install python@3.13"
    echo "  /opt/homebrew/bin/pip3.13 install pyobjc"
    echo ""
    echo "Then re-run this installer."
    exit 1
fi

# 2b. Ensure PyObjC version >= 11 (older versions crash on macOS 26+)
PYOBJC_VER="$("$PYTHON3" -c 'import objc; print(objc.__version__)' 2>/dev/null || echo 0)"
PYOBJC_MAJOR="$(echo "$PYOBJC_VER" | cut -d. -f1)"
if [[ -z "$PYOBJC_MAJOR" ]] || [[ "$PYOBJC_MAJOR" -lt 11 ]]; then
    echo "  ⚠  PyObjC $PYOBJC_VER detected (older versions crash on macOS 26)."
    echo "  Upgrading to latest PyObjC..."
    "$PYTHON3" -m pip install --upgrade --quiet pyobjc 2>&1 | tail -3 || {
        echo "  ✗ pip install failed. Run manually:"
        echo "    $PYTHON3 -m pip install --upgrade pyobjc"
        exit 1
    }
    NEW_VER="$("$PYTHON3" -c 'import objc; print(objc.__version__)')"
    echo "  ✓ Upgraded PyObjC to $NEW_VER"
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
    curl -fsSL "$REPO_RAW/eye_break.py" -o "$SRC_DIR/eye_break.py"
    curl -fsSL "$REPO_RAW/eyebreak"     -o "$SRC_DIR/eyebreak"
    curl -fsSL "$REPO_RAW/uninstall.sh" -o "$SRC_DIR/uninstall.sh"
fi

# 4. Install files
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/eye_break.py" "$INSTALL_DIR/eye_break.py"
cp "$SRC_DIR/eyebreak"     "$INSTALL_DIR/eyebreak"
cp "$SRC_DIR/uninstall.sh" "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/eye_break.py" "$INSTALL_DIR/eyebreak" "$INSTALL_DIR/uninstall.sh"

# 5. Generate the launchd plist
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>$INSTALL_DIR/eye_break.py</string>
    </array>
    <key>StartInterval</key>
    <integer>$INTERVAL_SECONDS</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/stderr.log</string>
</dict>
</plist>
EOF

# 6. Reload launchd
USER_DOMAIN="gui/$(id -u)"
launchctl bootout "$USER_DOMAIN" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "$USER_DOMAIN" "$PLIST_PATH"
launchctl enable "$USER_DOMAIN/$LABEL" 2>/dev/null || true

# 7. Symlink `eyebreak` into PATH for convenience
SYMLINK_DIRS=("/opt/homebrew/bin" "/usr/local/bin")
SYMLINKED=""
for d in "${SYMLINK_DIRS[@]}"; do
    if [[ -d "$d" && -w "$d" ]]; then
        ln -sf "$INSTALL_DIR/eyebreak" "$d/eyebreak"
        SYMLINKED="$d/eyebreak"
        break
    fi
done

# 8. Done — show status
echo ""
echo "✓ Eye Break installed."
echo "  Mode:     $SRC_MODE"
echo "  Files:    $INSTALL_DIR/"
echo "  Plist:    $PLIST_PATH"
echo "  Schedule: every $INTERVAL_SECONDS seconds ($((INTERVAL_SECONDS / 60)) min)"
echo "  Python:   $PYTHON3"
if [[ -n "$SYMLINKED" ]]; then
    echo "  CLI:      $SYMLINKED  (run: 'eyebreak help')"
else
    echo "  CLI:      $INSTALL_DIR/eyebreak  (add $INSTALL_DIR to PATH for convenience)"
fi
echo ""
echo "  Try it now:    eyebreak now"
echo "  See status:    eyebreak status"
echo "  Help:          eyebreak help"
echo ""
