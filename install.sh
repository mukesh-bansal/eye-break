#!/usr/bin/env bash
# Eye Break — installer for macOS
# Idempotent: safe to run multiple times. Installs/refreshes everything.

set -euo pipefail

INSTALL_DIR="$HOME/Library/EyeBreak"
PLIST_PATH="$HOME/Library/LaunchAgents/com.mukesh.eyebreak.plist"
LABEL="com.mukesh.eyebreak"
INTERVAL_SECONDS="${EYE_BREAK_INTERVAL:-600}"   # default 10 min, override with env var
PYTHON3="/usr/bin/python3"

# 1. Pre-flight: macOS only
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: macOS only (detected $(uname -s))"
    exit 1
fi

# 2. Pre-flight: system Python 3 with Tkinter
if ! "$PYTHON3" -c "import tkinter" 2>/dev/null; then
    echo "ERROR: $PYTHON3 cannot import tkinter"
    echo "Try: xcode-select --install"
    exit 1
fi

# 3. Locate source files (handle both local clone and curl|bash via raw URL)
if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "$(dirname "${BASH_SOURCE[0]}")/eye_break.py" ]]; then
    SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SRC_MODE="local"
else
    # Running via curl|bash — fetch from GitHub
    SRC_MODE="remote"
    REPO_RAW="${EYE_BREAK_REPO_RAW:-https://raw.githubusercontent.com/mukesh-bansal/eye-break/main}"
    SRC_DIR="$(mktemp -d)"
    echo "Fetching files from $REPO_RAW ..."
    curl -fsSL "$REPO_RAW/eye_break.py" -o "$SRC_DIR/eye_break.py"
    curl -fsSL "$REPO_RAW/uninstall.sh" -o "$SRC_DIR/uninstall.sh"
fi

# 4. Create install dir and copy files
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/eye_break.py" "$INSTALL_DIR/eye_break.py"
chmod +x "$INSTALL_DIR/eye_break.py"
cp "$SRC_DIR/uninstall.sh" "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/uninstall.sh"

# 5. Generate the launchd plist (with absolute paths for THIS user)
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

# 6. Reload launchd: bootout-then-bootstrap is the modern (macOS 12+) idiom
USER_DOMAIN="gui/$(id -u)"
launchctl bootout "$USER_DOMAIN" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "$USER_DOMAIN" "$PLIST_PATH"
launchctl enable "$USER_DOMAIN/$LABEL"

# 7. Status
echo ""
echo "✓ Eye Break installed."
echo "  Mode:     $SRC_MODE"
echo "  Files:    $INSTALL_DIR/"
echo "  Plist:    $PLIST_PATH"
echo "  Schedule: every $INTERVAL_SECONDS seconds"
echo "  Logs:     $INSTALL_DIR/events.log  (also stdout.log / stderr.log)"
echo ""
echo "  Test now:    $PYTHON3 $INSTALL_DIR/eye_break.py"
echo "  Edit config: $INSTALL_DIR/config.json"
echo "  Uninstall:   bash $INSTALL_DIR/uninstall.sh"
echo ""
