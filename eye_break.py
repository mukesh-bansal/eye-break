#!/usr/bin/env python3
"""
Eye Break — fullscreen reminder to stand up, walk, look away, breathe.
Triggered by launchd on a fixed interval. Single-shot: shows the popup,
auto-dismisses after a configured duration, exits.

No external dependencies. Uses /usr/bin/python3 + Tkinter (built into macOS).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import tkinter as tk

INSTALL_DIR = Path.home() / "Library" / "EyeBreak"
CONFIG_FILE = INSTALL_DIR / "config.json"
LOG_FILE = INSTALL_DIR / "events.log"
LOCK_FILE = INSTALL_DIR / "showing.lock"

DEFAULT_CONFIG = {
    "duration_seconds": 60,
    "headline": "STOP · EYE BREAK · 10 MIN",
    "actions": [
        ("\U0001F6B6", "walk 2 minutes"),
        ("\U0001F440", "look 20 ft away"),
        ("\U0001F60C", "close eyes 20 sec"),
        ("\U0001F33F", "breathe deeply"),
        ("☀️", "stand up + stretch"),
        ("\U0001F49A", "future eyes thank you"),
    ],
    "active_hours": {"start": 7, "end": 23},  # 24h, inclusive start, exclusive end
    "play_sound": True,
    "sound_file": "/System/Library/Sounds/Glass.aiff",
    "colors": {
        "background": "#0F172A",
        "card": "#1E293B",
        "border": "#22D3EE",
        "headline": "#FACC15",
        "text": "#F1F5F9",
        "accent": "#22D3EE",
        "muted": "#94A3B8",
    },
}


def log(msg):
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")


def load_config():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE) as f:
            user_cfg = json.load(f)
        # Merge with defaults — let user config override
        merged = {**DEFAULT_CONFIG, **user_cfg}
        merged["colors"] = {**DEFAULT_CONFIG["colors"], **user_cfg.get("colors", {})}
        merged["active_hours"] = {**DEFAULT_CONFIG["active_hours"], **user_cfg.get("active_hours", {})}
        # actions need re-tupling if loaded from JSON
        if "actions" in user_cfg:
            merged["actions"] = [tuple(a) if isinstance(a, list) else a for a in user_cfg["actions"]]
        return merged
    except Exception as e:
        log(f"config_error fallback_to_defaults err={e}")
        return DEFAULT_CONFIG


def in_active_hours(cfg):
    now = time.localtime()
    h = now.tm_hour
    return cfg["active_hours"]["start"] <= h < cfg["active_hours"]["end"]


def already_showing():
    """Skip if another popup is currently on screen.

    PID-based: read the PID from the lock and check if the process is alive.
    A stale lock (process died without releasing) is auto-cleared.
    """
    if not LOCK_FILE.exists():
        return False
    try:
        pid = int(LOCK_FILE.read_text().strip())
    except (ValueError, OSError):
        LOCK_FILE.unlink(missing_ok=True)
        return False
    # os.kill(pid, 0) raises ProcessLookupError if pid is dead.
    try:
        os.kill(pid, 0)
        return True  # process alive — popup is up
    except ProcessLookupError:
        LOCK_FILE.unlink(missing_ok=True)
        return False
    except PermissionError:
        # Some other user owns this PID — almost certainly not us. Treat as stale.
        LOCK_FILE.unlink(missing_ok=True)
        return False


def acquire_lock():
    LOCK_FILE.write_text(str(os.getpid()))


def release_lock():
    LOCK_FILE.unlink(missing_ok=True)


def play_chime(cfg):
    if not cfg.get("play_sound", True):
        return
    sound = cfg.get("sound_file", "/System/Library/Sounds/Glass.aiff")
    if not Path(sound).exists():
        return
    try:
        subprocess.Popen(
            ["/usr/bin/afplay", sound],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        log(f"sound_error err={e}")


def bring_to_front():
    """Force Python's window to the front on macOS."""
    try:
        subprocess.Popen(
            [
                "/usr/bin/osascript",
                "-e",
                'tell application "System Events" to set frontmost of every process whose unix id is {pid} to true'.format(
                    pid=os.getpid()
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def show_break(cfg):
    colors = cfg["colors"]

    root = tk.Tk()
    root.title("Eye Break")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg=colors["background"])
    root.lift()
    root.focus_force()

    dismissed = {"by": None}

    def dismiss(reason):
        if dismissed["by"]:
            return
        dismissed["by"] = reason
        log(f"dismissed reason={reason}")
        try:
            root.destroy()
        except Exception:
            pass

    root.bind("<Escape>", lambda e: dismiss("escape"))
    root.bind("<space>", lambda e: dismiss("space"))
    root.bind("<Return>", lambda e: dismiss("return"))
    root.bind("<Button-1>", lambda e: dismiss("click"))

    # Outer card with cyan border
    border = tk.Frame(root, bg=colors["border"], padx=4, pady=4)
    border.place(relx=0.5, rely=0.5, anchor="center")

    card = tk.Frame(border, bg=colors["card"], padx=80, pady=60)
    card.pack()

    # Top accent line
    tk.Frame(card, bg=colors["accent"], height=4, width=600).pack(pady=(0, 30))

    # Headline (yellow, bold, large)
    tk.Label(
        card,
        text=cfg["headline"],
        font=("Helvetica Neue", 42, "bold"),
        fg=colors["headline"],
        bg=colors["card"],
    ).pack(pady=(0, 8))

    # Subhead
    tk.Label(
        card,
        text="future-you needs this — 60 seconds, max",
        font=("Helvetica Neue", 16, "italic"),
        fg=colors["muted"],
        bg=colors["card"],
    ).pack(pady=(0, 36))

    # Actions in a 2-col grid
    actions_frame = tk.Frame(card, bg=colors["card"])
    actions_frame.pack(pady=(0, 36))

    actions = cfg["actions"]
    cols = 2
    for i, item in enumerate(actions):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            emoji, text = item
        else:
            emoji, text = "•", str(item)
        row, col = divmod(i, cols)
        cell = tk.Frame(actions_frame, bg=colors["card"], padx=24, pady=10)
        cell.grid(row=row, column=col, sticky="w")
        tk.Label(
            cell,
            text=emoji,
            font=("Helvetica Neue", 32),
            fg=colors["text"],
            bg=colors["card"],
        ).pack(side="left", padx=(0, 14))
        tk.Label(
            cell,
            text=text,
            font=("Helvetica Neue", 22),
            fg=colors["text"],
            bg=colors["card"],
        ).pack(side="left")

    # Bottom accent line
    tk.Frame(card, bg=colors["accent"], height=2, width=600).pack(pady=(0, 24))

    # Countdown + dismiss hints
    countdown_var = tk.StringVar()

    def fmt(remaining):
        return f"auto-dismiss in {remaining}s   •   ESC, SPACE, RETURN, or CLICK to dismiss now"

    countdown_var.set(fmt(cfg["duration_seconds"]))
    tk.Label(
        card,
        textvariable=countdown_var,
        font=("Helvetica Neue", 14),
        fg=colors["accent"],
        bg=colors["card"],
    ).pack()

    def tick(remaining):
        if dismissed["by"]:
            return
        if remaining <= 0:
            dismiss("timeout")
            return
        countdown_var.set(fmt(remaining))
        root.after(1000, lambda: tick(remaining - 1))

    log(f"shown duration={cfg['duration_seconds']}")
    play_chime(cfg)
    bring_to_front()
    tick(cfg["duration_seconds"])
    root.mainloop()


def main():
    cfg = load_config()

    # Skip silently outside active hours
    if not in_active_hours(cfg):
        log("skipped reason=inactive_hours")
        return

    # Skip if already showing (prevents stacking on slow systems)
    if already_showing():
        log("skipped reason=already_showing")
        return

    acquire_lock()
    try:
        show_break(cfg)
    finally:
        release_lock()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"fatal err={e}")
        raise
