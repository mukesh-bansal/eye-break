#!/usr/bin/env python3
"""
Eye Break — menu bar app.

Always-on menu bar icon (top-right of screen). Click for: enable/disable,
test now, change interval / duration / hours, sound toggle, quit.

The popup itself lives in eye_break.py — this app only manages launchd and
the config file.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import rumps


INSTALL_DIR = Path.home() / "Library" / "EyeBreak"
CONFIG_FILE = INSTALL_DIR / "config.json"
LOG_FILE = INSTALL_DIR / "events.log"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
POPUP_PLIST = PLIST_DIR / "com.mukesh.eyebreak.plist"
LABEL = "com.mukesh.eyebreak"
USER_DOMAIN = f"gui/{os.getuid()}"

INTERVAL_OPTIONS = [5, 10, 15, 20, 30, 60]   # minutes (must divide 60 cleanly)
DURATION_OPTIONS = [15, 30, 45, 60, 90, 120]  # seconds
HOURS_PRESETS = [
    ("All day (0–24)", 0, 24),
    ("Awake (7–23)", 7, 23),
    ("Workday (9–18)", 9, 18),
    ("Long workday (8–22)", 8, 22),
]


# ─────────────────────────────────────────────────────────────────
# Notification helper
# ─────────────────────────────────────────────────────────────────
# rumps.notification raises if the host Python lacks an Info.plist
# CFBundleIdentifier (e.g. Anaconda's bare /bin/python3). Wrap so a
# notification failure never breaks a callback.

def _safe_notify(title, subtitle, message):
    try:
        rumps.notification(title, subtitle, message)
    except Exception:
        # Notifications are optional — silently swallow.
        pass


# ─────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "duration_seconds": 60,
    "interval_minutes": 10,
    "active_hours": {"start": 7, "end": 23},
    "play_sound": True,
}


def load_config():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        # ensure required keys exist
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(updates):
    """Merge `updates` into config.json. Read-modify-write to preserve unrelated keys."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    merged = {**existing, **updates}
    with open(CONFIG_FILE, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────
# launchd helpers
# ─────────────────────────────────────────────────────────────────

def find_python():
    """Return the same Python that's wired into the popup plist."""
    if not POPUP_PLIST.exists():
        return sys.executable
    txt = POPUP_PLIST.read_text()
    import re
    m = re.search(r'<string>(/[^<]*python3[^<]*)</string>', txt)
    return m.group(1) if m else sys.executable


def calendar_interval_entries(minutes):
    """Yield Minute values that fire every `minutes` on the wall clock,
    aligned to :00. Examples:
      10 -> 0, 10, 20, 30, 40, 50
       5 -> 0, 5, 10, 15, ..., 55
      15 -> 0, 15, 30, 45
      60 -> 0
    """
    if minutes <= 0 or minutes > 60 or 60 % minutes != 0:
        # fallback: every 10
        minutes = 10
    return list(range(0, 60, minutes))


def write_popup_plist(interval_minutes):
    """Regenerate the popup plist with calendar-aligned firing."""
    py = find_python()
    script = INSTALL_DIR / "eye_break.py"
    minutes = calendar_interval_entries(interval_minutes)
    minute_entries = "\n        ".join(
        f"<dict><key>Minute</key><integer>{m}</integer></dict>"
        for m in minutes
    )
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py}</string>
        <string>{script}</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        {minute_entries}
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{INSTALL_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{INSTALL_DIR}/stderr.log</string>
</dict>
</plist>
"""
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    POPUP_PLIST.write_text(plist)


def launchd_loaded():
    r = subprocess.run(
        ["launchctl", "print", f"{USER_DOMAIN}/{LABEL}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return r.returncode == 0


def launchd_load():
    subprocess.run(["launchctl", "bootout", USER_DOMAIN, str(POPUP_PLIST)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "bootstrap", USER_DOMAIN, str(POPUP_PLIST)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launchd_unload():
    subprocess.run(["launchctl", "bootout", USER_DOMAIN, str(POPUP_PLIST)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launchd_kickstart():
    subprocess.run(["launchctl", "kickstart", f"{USER_DOMAIN}/{LABEL}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def next_fire_time(interval_minutes, now=None):
    """When will the next popup fire, given calendar-aligned schedule?"""
    if now is None:
        now = datetime.now()
    minutes = calendar_interval_entries(interval_minutes)
    candidates = []
    for m in minutes:
        t = now.replace(minute=m, second=0, microsecond=0)
        if t <= now:
            t = t + timedelta(hours=1)
        candidates.append(t)
    return min(candidates)


# ─────────────────────────────────────────────────────────────────
# Menu bar app
# ─────────────────────────────────────────────────────────────────

class EyeBreakApp(rumps.App):
    def __init__(self):
        # The title (text shown in menu bar). We use an emoji so the icon is visible
        # without a custom .icns file.
        super().__init__("👁", quit_button=None)

        cfg = load_config()
        self._cfg = cfg

        # Build the menu items
        self.active_item = rumps.MenuItem("Eye Break is OFF", callback=self.toggle_active)
        self.next_item = rumps.MenuItem("Next popup: —")
        self.next_item.set_callback(None)  # display-only

        self.test_item = rumps.MenuItem("Test now (instant popup)", callback=self.test_now)

        self.interval_menu = rumps.MenuItem("Interval")
        for n in INTERVAL_OPTIONS:
            label = f"every {n} min"
            item = rumps.MenuItem(label, callback=self._mk_set_interval(n))
            if n == cfg["interval_minutes"]:
                item.state = 1
            self.interval_menu.add(item)

        self.duration_menu = rumps.MenuItem("Duration")
        for n in DURATION_OPTIONS:
            label = f"{n} sec on screen"
            item = rumps.MenuItem(label, callback=self._mk_set_duration(n))
            if n == cfg["duration_seconds"]:
                item.state = 1
            self.duration_menu.add(item)

        self.hours_menu = rumps.MenuItem("Active hours")
        for label, s, e in HOURS_PRESETS:
            item = rumps.MenuItem(label, callback=self._mk_set_hours(s, e))
            if cfg["active_hours"]["start"] == s and cfg["active_hours"]["end"] == e:
                item.state = 1
            self.hours_menu.add(item)

        self.sound_item = rumps.MenuItem("Sound on", callback=self.toggle_sound)

        self.log_item = rumps.MenuItem("Open log…", callback=self.open_log)
        self.config_item = rumps.MenuItem("Open config…", callback=self.open_config)
        self.quit_item = rumps.MenuItem("Quit menu bar app", callback=rumps.quit_application)

        # Assemble menu (rumps draws in order)
        self.menu = [
            self.active_item,
            self.next_item,
            None,
            self.test_item,
            None,
            self.interval_menu,
            self.duration_menu,
            self.hours_menu,
            self.sound_item,
            None,
            self.log_item,
            self.config_item,
            None,
            self.quit_item,
        ]

        self._refresh_state()

        # Update next-fire-time display every 30s
        self._timer = rumps.Timer(self._tick, 30)
        self._timer.start()

    # ── Reflective state ──

    def _refresh_state(self):
        cfg = load_config()
        self._cfg = cfg
        loaded = launchd_loaded()
        if loaded:
            self.active_item.title = "● Eye Break is ON  (click to disable)"
            self.title = "👁"
            self.next_item.title = (
                f"Next popup: {next_fire_time(cfg['interval_minutes']).strftime('%H:%M')}"
            )
        else:
            self.active_item.title = "○ Eye Break is OFF  (click to enable)"
            self.title = "👁︎"   # variant selector — looks slightly dimmer
            self.next_item.title = "Next popup: —  (disabled)"

        self.sound_item.title = f"Sound {'on' if cfg['play_sound'] else 'off'}"

        # Sync radio-style state on submenus
        for item in self.interval_menu.values():
            n = int(item.title.split()[1])
            item.state = 1 if n == cfg["interval_minutes"] else 0
        for item in self.duration_menu.values():
            n = int(item.title.split()[0])
            item.state = 1 if n == cfg["duration_seconds"] else 0
        for item in self.hours_menu.values():
            label = item.title
            for plabel, s, e in HOURS_PRESETS:
                if plabel == label:
                    item.state = 1 if (cfg["active_hours"]["start"] == s and cfg["active_hours"]["end"] == e) else 0
                    break

    def _tick(self, sender):
        self._refresh_state()

    # ── Callbacks ──

    def toggle_active(self, sender):
        # Wrap the whole flow so a notification or transient launchd failure
        # never locks the user out of toggling.
        try:
            if launchd_loaded():
                launchd_unload()
                _safe_notify("Eye Break", "Disabled", "Popups will not fire until re-enabled.")
            else:
                write_popup_plist(self._cfg["interval_minutes"])
                launchd_load()
                _safe_notify(
                    "Eye Break", "Enabled",
                    f"Next popup at {next_fire_time(self._cfg['interval_minutes']).strftime('%H:%M')}"
                )
        except Exception as e:
            # Surface failures via alert (synchronous) — never silently swallow.
            try:
                rumps.alert("Eye Break — toggle failed",
                            f"{type(e).__name__}: {e}\n\nCheck menu.stderr.log for details.")
            except Exception:
                pass
        finally:
            # ALWAYS refresh state so the menu reflects reality even on partial failure.
            self._refresh_state()

    def test_now(self, sender):
        if not launchd_loaded():
            rumps.alert("Eye Break is disabled",
                        "Enable from the menu first, then 'Test now' will fire a popup.")
            return
        launchd_kickstart()

    def _mk_set_interval(self, minutes):
        def cb(sender):
            self._cfg["interval_minutes"] = minutes
            save_config({"interval_minutes": minutes})
            write_popup_plist(minutes)
            if launchd_loaded():
                launchd_load()  # reload to pick up new schedule
            _safe_notify("Eye Break", "Interval changed",
                         f"Now every {minutes} min on the calendar")
            self._refresh_state()
        return cb

    def _mk_set_duration(self, seconds):
        def cb(sender):
            self._cfg["duration_seconds"] = seconds
            save_config({"duration_seconds": seconds})
            _safe_notify("Eye Break", "Duration changed", f"Popup stays {seconds}s")
            self._refresh_state()
        return cb

    def _mk_set_hours(self, start, end):
        def cb(sender):
            self._cfg["active_hours"] = {"start": start, "end": end}
            save_config({"active_hours": {"start": start, "end": end}})
            _safe_notify("Eye Break", "Active hours changed", f"{start:02d}:00 – {end:02d}:00")
            self._refresh_state()
        return cb

    def toggle_sound(self, sender):
        new = not self._cfg.get("play_sound", True)
        self._cfg["play_sound"] = new
        save_config({"play_sound": new})
        self._refresh_state()

    def open_log(self, sender):
        if LOG_FILE.exists():
            subprocess.run(["open", "-a", "Console", str(LOG_FILE)])
        else:
            rumps.alert("No log yet", "The log file will appear after the first popup fires.")

    def open_config(self, sender):
        if CONFIG_FILE.exists():
            subprocess.run(["open", "-e", str(CONFIG_FILE)])  # -e opens in TextEdit


def main():
    # Ensure config exists
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
    EyeBreakApp().run()


if __name__ == "__main__":
    main()
