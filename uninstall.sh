#!/usr/bin/env bash
# Eye Break — uninstaller. Removes launchd job and all installed files.

set -euo pipefail

INSTALL_DIR="$HOME/Library/EyeBreak"
PLIST_PATH="$HOME/Library/LaunchAgents/com.mukesh.eyebreak.plist"
LABEL="com.mukesh.eyebreak"
USER_DOMAIN="gui/$(id -u)"

echo "Uninstalling Eye Break..."

launchctl bootout "$USER_DOMAIN" "$PLIST_PATH" 2>/dev/null || true
launchctl unload "$PLIST_PATH" 2>/dev/null || true

rm -f "$PLIST_PATH"

if [[ -d "$INSTALL_DIR" ]]; then
    if [[ "${KEEP_LOGS:-0}" == "1" ]]; then
        find "$INSTALL_DIR" -mindepth 1 -not -name "*.log" -delete 2>/dev/null || true
        echo "  Logs preserved at $INSTALL_DIR (run with KEEP_LOGS=0 to remove)"
    else
        rm -rf "$INSTALL_DIR"
    fi
fi

echo "✓ Uninstalled."
