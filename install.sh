#!/usr/bin/env bash
# Eye Break — installer for macOS
# Idempotent: safe to run multiple times. Installs/refreshes everything.

set -euo pipefail

INSTALL_DIR="$HOME/Library/EyeBreak"
PLIST_PATH="$HOME/Library/LaunchAgents/com.mukesh.eyebreak.plist"
LABEL="com.mukesh.eyebreak"
INTERVAL_SECONDS="${EYE_BREAK_INTERVAL:-600}"   # default 10 min, override with env var

# 1. Pre-flight: macOS only
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: macOS only (detected $(uname -s))"
    exit 1
fi

# 2. Find a Python with a Tk that actually works on this macOS
# (the system /usr/bin/python3 ships Tk 8.5, which is broken on macOS 26+)
echo "Finding a Python with working Tk..."
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
    # Test: can the candidate import tkinter AND actually create a window?
    if "$cand" -c "import tkinter; r=tkinter.Tk(); r.withdraw(); r.destroy()" 2>/dev/null; then
        PYTHON3="$cand"
        TK_VER="$("$cand" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null)"
        echo "  ✓ Using $PYTHON3 (Tk $TK_VER)"
        break
    fi
done

if [[ -z "$PYTHON3" ]]; then
    echo ""
    echo "ERROR: no working Python found."
    echo ""
    echo "Eye Break needs a Python 3 with a working Tk on this macOS."
    echo "On macOS 26+, /usr/bin/python3's Tk 8.5 is broken. Pick one:"
    echo ""
    echo "  Option A — install Anaconda  (recommended, easiest):"
    echo "    https://www.anaconda.com/download (or 'brew install --cask anaconda')"
    echo ""
    echo "  Option B — brew Python with Tk:"
    echo "    brew install python-tk@3.13"
    echo ""
    echo "Then re-run this installer."
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
