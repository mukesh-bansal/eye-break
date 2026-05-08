#!/usr/bin/env python3
"""
Eye Break — fullscreen reminder using native macOS AppKit (PyObjC).
Triggered by launchd. Black background, rainbow-block corner frame,
centered SF Mono text — matches the original Claude Code "STOP · EYE BREAK"
banner, scaled to fullscreen.

Requires PyObjC (ships with Anaconda / miniconda; pip-installable on brew).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

INSTALL_DIR = Path.home() / "Library" / "EyeBreak"
CONFIG_FILE = INSTALL_DIR / "config.json"
LOG_FILE = INSTALL_DIR / "events.log"
LOCK_FILE = INSTALL_DIR / "showing.lock"

DEFAULT_CONFIG = {
    "duration_seconds": 60,
    "headline": "STOP · EYE BREAK",
    "interval_label": "10 MIN",            # shown next to the headline
    "actions": [
        ["\U0001F6B6", "walk 2 min"],
        ["\U0001F440", "look 20 ft away"],
        ["\U0001F60C", "close eyes 20s"],
        ["\U0001F3A4", "voice next round"],
        ["\U0001F33F", "breathe"],
        ["☀️", "stand up"],
        ["\U0001F49A", "future eyes thank you"],
    ],
    "active_hours": {"start": 7, "end": 23},
    "play_sound": True,
    "sound_file": "/System/Library/Sounds/Glass.aiff",
    "colors": {
        "background": "#000000",
        "text": "#FFFFFF",
        "muted": "#94A3B8",
        "headline": "#FACC15",
        "accent": "#22D3EE",
        "rule": "#FFFFFF",
        # Corner blocks (matches the reference frame)
        "block_red": "#DC2626",
        "block_orange": "#F97316",
        "block_yellow": "#FACC15",
        "block_green": "#22C55E",
        "block_blue": "#3B82F6",
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
        merged = {**DEFAULT_CONFIG, **user_cfg}
        merged["colors"] = {**DEFAULT_CONFIG["colors"], **user_cfg.get("colors", {})}
        merged["active_hours"] = {**DEFAULT_CONFIG["active_hours"], **user_cfg.get("active_hours", {})}
        if "actions" in user_cfg:
            merged["actions"] = user_cfg["actions"]
        return merged
    except Exception as e:
        log(f"config_error err={e}")
        return DEFAULT_CONFIG


def in_active_hours(cfg):
    h = time.localtime().tm_hour
    return cfg["active_hours"]["start"] <= h < cfg["active_hours"]["end"]


def already_showing():
    if not LOCK_FILE.exists():
        return False
    try:
        pid = int(LOCK_FILE.read_text().strip())
    except (ValueError, OSError):
        LOCK_FILE.unlink(missing_ok=True)
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
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
        subprocess.Popen(["/usr/bin/afplay", sound],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# AppKit imports + module-level Objective-C class (must be at module scope)
if sys.platform == "darwin":
    from AppKit import (
        NSApplication, NSApp, NSApplicationActivationPolicyRegular,
        NSWindow, NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
        NSScreen, NSColor, NSView, NSTextField, NSFont, NSFontWeightBold,
        NSScreenSaverWindowLevel, NSTextAlignmentCenter, NSTextAlignmentLeft,
        NSEvent, NSEventMaskKeyDown, NSEventMaskLeftMouseDown,
    )
    from Foundation import NSObject, NSTimer

    class TimerHandler(NSObject):
        # PyObjC NSObject subclasses allow plain Python attrs after .alloc().init()
        def tick_(self, timer):
            remaining = getattr(self, "remaining", 0) - 1
            self.remaining = remaining
            if remaining <= 0:
                _stop_app()
                return
            label = getattr(self, "label", None)
            if label is not None:
                label.setStringValue_(_countdown_text(remaining))


def _countdown_text(remaining):
    return f"auto-dismiss in {remaining}s   ·   ESC, SPACE, RETURN, or CLICK to dismiss"


def _stop_app():
    NSApp.stop_(None)
    from AppKit import NSEvent
    from Foundation import NSPoint
    e = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
        14, NSPoint(0, 0), 0, 0, 0, None, 0, 0, 0
    )
    NSApp.postEvent_atStart_(e, True)


def _hex_color(hex_str, alpha=1.0):
    h = hex_str.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return NSColor.colorWithRed_green_blue_alpha_(r, g, b, alpha)


def _color_block(rect, hex_str):
    v = NSView.alloc().initWithFrame_(rect)
    v.setWantsLayer_(True)
    v.layer().setBackgroundColor_(_hex_color(hex_str).CGColor())
    return v


def _label(frame, text, font, color, align=None):
    if align is None:
        align = NSTextAlignmentCenter
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setStringValue_(text)
    f.setBordered_(False)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(False)
    f.setTextColor_(color)
    f.setFont_(font)
    f.setAlignment_(align)
    return f


def _mono_font(size, bold=False):
    """SF Mono — falls back gracefully on older macOS."""
    name = "SF Mono"
    f = NSFont.fontWithName_size_(name, size)
    if f is None:
        # Fallback: monospaced system font
        f = NSFont.monospacedSystemFontOfSize_weight_(
            size, NSFontWeightBold if bold else 0.0
        )
    elif bold:
        bold_f = NSFont.fontWithName_size_("SF Mono Bold", size)
        if bold_f is not None:
            f = bold_f
    return f


def show_break_native(cfg):
    colors = cfg["colors"]

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    screen = NSScreen.mainScreen()
    sf = screen.frame()
    sw, sh = sf.size.width, sf.size.height

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        sf, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False,
    )
    window.setBackgroundColor_(_hex_color(colors["background"]))
    window.setLevel_(NSScreenSaverWindowLevel + 1)
    window.setOpaque_(True)
    window.setHasShadow_(False)

    content = NSView.alloc().initWithFrame_(sf)
    content.setWantsLayer_(True)
    content.layer().setBackgroundColor_(_hex_color(colors["background"]).CGColor())
    window.setContentView_(content)

    # ── Corner-block frame ──
    # Each corner: 3 horizontal blocks (red/orange/yellow) + 2 vertical blocks (green, blue) below
    # Mirrored at bottom. White horizontal rule connects the top three rows of corner blocks.
    BS = 56          # block size (px)
    GAP = 8          # gap between blocks
    INSET = 56       # inset from screen edge
    RULE_H = 4       # horizontal rule thickness

    # ─── TOP ROW ─── (three blocks left, three blocks right, rule connecting)
    # Top y for the first row of squares — aligned with the top of the screen
    top_y = sh - INSET - BS

    # Top-left: red, orange, yellow (left → right, in that order)
    tl_colors = [colors["block_red"], colors["block_orange"], colors["block_yellow"]]
    tl_xs = [INSET + i * (BS + GAP) for i in range(3)]
    for x, c in zip(tl_xs, tl_colors):
        content.addSubview_(_color_block(((x, top_y), (BS, BS)), c))

    # Top-right: yellow, orange, red (mirror)
    tr_colors = [colors["block_yellow"], colors["block_orange"], colors["block_red"]]
    tr_xs = [sw - INSET - (3 - i) * (BS + GAP) + GAP for i in range(3)]
    for x, c in zip(tr_xs, tr_colors):
        content.addSubview_(_color_block(((x, top_y), (BS, BS)), c))

    # White horizontal rule between top blocks (centered vertically through them)
    rule_top_y = top_y + (BS - RULE_H) / 2
    rule_left = tl_xs[-1] + BS + GAP
    rule_right = tr_xs[0] - GAP
    rule_top_w = rule_right - rule_left
    if rule_top_w > 0:
        content.addSubview_(_color_block(((rule_left, rule_top_y), (rule_top_w, RULE_H)), colors["rule"]))

    # ─── TOP CORNER VERTICAL STACK ─── (green, then blue, below the top row)
    # Left column (single block per row, aligned to left-edge of the leftmost top block)
    green_y = top_y - (BS + GAP)
    blue_y = green_y - (BS + GAP)
    content.addSubview_(_color_block(((INSET, green_y), (BS, BS)), colors["block_green"]))
    content.addSubview_(_color_block(((INSET, blue_y), (BS, BS)), colors["block_blue"]))
    # Right column
    right_x = sw - INSET - BS
    content.addSubview_(_color_block(((right_x, green_y), (BS, BS)), colors["block_green"]))
    content.addSubview_(_color_block(((right_x, blue_y), (BS, BS)), colors["block_blue"]))

    # ─── BOTTOM ROW ─── (mirrors top)
    bot_y = INSET
    # Bottom-left: red, orange, yellow
    bl_colors = [colors["block_red"], colors["block_orange"], colors["block_yellow"]]
    bl_xs = [INSET + i * (BS + GAP) for i in range(3)]
    for x, c in zip(bl_xs, bl_colors):
        content.addSubview_(_color_block(((x, bot_y), (BS, BS)), c))
    # Bottom-right
    br_colors = [colors["block_yellow"], colors["block_orange"], colors["block_red"]]
    br_xs = [sw - INSET - (3 - i) * (BS + GAP) + GAP for i in range(3)]
    for x, c in zip(br_xs, br_colors):
        content.addSubview_(_color_block(((x, bot_y), (BS, BS)), c))
    # Bottom rule
    rule_bot_y = bot_y + (BS - RULE_H) / 2
    rule_bot_left = bl_xs[-1] + BS + GAP
    rule_bot_right = br_xs[0] - GAP
    rule_bot_w = rule_bot_right - rule_bot_left
    if rule_bot_w > 0:
        content.addSubview_(_color_block(((rule_bot_left, rule_bot_y), (rule_bot_w, RULE_H)), colors["rule"]))

    # Bottom corner vertical stack (blue, green — going UP from bottom row)
    blue_b_y = bot_y + (BS + GAP)
    green_b_y = blue_b_y + (BS + GAP)
    content.addSubview_(_color_block(((INSET, blue_b_y), (BS, BS)), colors["block_blue"]))
    content.addSubview_(_color_block(((INSET, green_b_y), (BS, BS)), colors["block_green"]))
    content.addSubview_(_color_block(((right_x, blue_b_y), (BS, BS)), colors["block_blue"]))
    content.addSubview_(_color_block(((right_x, green_b_y), (BS, BS)), colors["block_green"]))

    # ─── CENTER CONTENT ───
    center_y = sh / 2
    text_color = _hex_color(colors["text"])
    headline_color = _hex_color(colors["headline"])
    muted_color = _hex_color(colors["muted"])

    # Headline:  🚨 ⚡ STOP · EYE BREAK · 10 MIN ⚡ 🚨
    headline_text = f"\U0001F6A8  ⚡  {cfg['headline']}  ·  {cfg.get('interval_label', '10 MIN')}  ⚡  \U0001F6A8"
    headline_font = _mono_font(48, bold=True)
    h_label = _label(((0, center_y + 100), (sw, 80)), headline_text, headline_font, headline_color)
    content.addSubview_(h_label)

    # Actions in a 3-row x 2-col grid (or as configured)
    actions = cfg["actions"]
    text_font = _mono_font(28)
    row_h = 56
    rows_needed = (len(actions) + 1) // 2
    grid_top_y = center_y + 30
    grid_left_pad = 0.18
    col_w = sw * (1 - 2 * grid_left_pad) / 2
    for i, item in enumerate(actions):
        emoji = item[0] if isinstance(item, (list, tuple)) and len(item) >= 1 else "•"
        text = item[1] if isinstance(item, (list, tuple)) and len(item) >= 2 else str(item)
        row = i // 2
        col = i % 2
        x = sw * grid_left_pad + col * col_w
        y = grid_top_y - row * row_h - 32
        # combined emoji + text with mono font
        line_text = f"{emoji}  {text}"
        line_label = _label(((x, y), (col_w, 44)), line_text, text_font, text_color, NSTextAlignmentLeft)
        content.addSubview_(line_label)

    # Countdown footer
    countdown = _label(
        ((0, center_y - 220), (sw, 28)),
        _countdown_text(cfg["duration_seconds"]),
        _mono_font(15),
        muted_color,
    )
    content.addSubview_(countdown)

    # ── Footer hint: how to skip ──
    hint = _label(
        ((0, 12), (sw, 22)),
        "press ESC or SPACE to skip · you'll be asked to confirm",
        _mono_font(13),
        muted_color,
    )
    content.addSubview_(hint)

    # ── Timer ──
    # Strong refs in a list so Python doesn't GC them while AppKit holds them.
    _retained = []
    handler = TimerHandler.alloc().init()
    handler.remaining = cfg["duration_seconds"]
    handler.label = countdown
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0, handler, b"tick:", None, True
    )
    _retained.append(handler)
    _retained.append(timer)

    # ── Skip-with-confirmation handler ──
    # ESC / SPACE / RETURN → show NSAlert. If user confirms skip, stop the app.
    # If they cancel, popup keeps running.
    from AppKit import NSAlert, NSAlertFirstButtonReturn

    def confirm_skip():
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Are you sure you want to skip?")
        alert.setInformativeText_(
            "Take 60 seconds for your eyes:\n"
            "  ·  Inhale 4 sec through nose\n"
            "  ·  Hold 4 sec\n"
            "  ·  Exhale 6 sec through mouth\n"
            "  ·  Look 20 ft away while breathing\n\n"
            "This break is for future-you. Honor it."
        )
        # First button is the default (ENTER). We make it the "stay" option
        # so reflexive ENTER-mashing doesn't skip the break.
        alert.addButtonWithTitle_("I'll take the break")
        alert.addButtonWithTitle_("Skip anyway")
        # Bring the alert above the fullscreen popup
        alert.window().setLevel_(NSScreenSaverWindowLevel + 2)
        response = alert.runModal()
        if response != NSAlertFirstButtonReturn:
            # Skip anyway
            log("dismissed reason=skip_confirmed")
            _stop_app()
        else:
            log("skip_cancelled")
            # Return to popup. Window may need to be refocused.
            window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)

    def key_handler(event):
        if event.keyCode() in (53, 49, 36):  # ESC, SPACE, RETURN
            confirm_skip()
            return None  # consume
        return event

    km = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        NSEventMaskKeyDown, key_handler
    )
    _retained.extend([km, key_handler, confirm_skip])

    # Hold strong refs at module level (extra-safe — PyObjC GC is finicky)
    show_break_native._retained = _retained

    log(f"shown duration={cfg['duration_seconds']}")
    play_chime(cfg)
    NSApp.activateIgnoringOtherApps_(True)
    window.makeKeyAndOrderFront_(None)
    NSApp.run()


def main():
    cfg = load_config()
    if not in_active_hours(cfg):
        log("skipped reason=inactive_hours")
        return
    if already_showing():
        log("skipped reason=already_showing")
        return
    acquire_lock()
    try:
        show_break_native(cfg)
    finally:
        release_lock()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"fatal err={e!r}")
        raise
