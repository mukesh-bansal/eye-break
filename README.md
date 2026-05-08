# Eye Break

A macOS menubar-free background utility that pops a fullscreen reminder every N minutes to:

- 🚶 walk 2 minutes
- 👀 look 20 ft away
- 😌 close eyes 20 sec
- 🌿 breathe deeply
- ☀️ stand up + stretch
- 💚 future eyes thank you

The popup auto-dismisses after 60 seconds, or hit ESC / SPACE / RETURN / click anywhere to dismiss now.

## Install on this Mac

```bash
cd "AI Test/36_eye_break"
bash install.sh
```

To install on **any** Mac with one command (after the repo is on GitHub):

```bash
curl -fsSL https://raw.githubusercontent.com/mukesh-bansal/eye-break/main/install.sh | bash
```

Default schedule: **every 600 seconds (10 minutes)**. Override at install time:

```bash
EYE_BREAK_INTERVAL=900 bash install.sh   # every 15 minutes
```

## Test immediately

```bash
/usr/bin/python3 ~/Library/EyeBreak/eye_break.py
```

A fullscreen card pops up. Verifies the install before waiting 10 minutes.

## Configure

Edit `~/Library/EyeBreak/config.json` to change:

| Key | Default | What |
|---|---|---|
| `duration_seconds` | `60` | how long the popup stays before auto-dismiss |
| `headline` | `"STOP · EYE BREAK · 10 MIN"` | top line |
| `actions` | 6 actions | list of `[emoji, text]` pairs shown in 2-col grid |
| `active_hours.start` / `.end` | `7` / `23` | 24-hour clock; outside this range the popup is silently skipped |
| `play_sound` | `true` | play a chime when the popup opens |
| `sound_file` | `/System/Library/Sounds/Glass.aiff` | any `.aiff` / `.wav` macOS knows |
| `colors.*` | dark slate + cyan + yellow | any hex; full palette in `eye_break.py` |

After editing, no reinstall needed — the next firing reads the new config.

## Logs

```bash
tail -f ~/Library/EyeBreak/events.log
```

Events: `shown`, `dismissed reason=...`, `skipped reason=inactive_hours`, `skipped reason=already_showing`.

## Uninstall

```bash
bash ~/Library/EyeBreak/uninstall.sh
```

Or remove the launchd job manually:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.mukesh.eyebreak.plist
rm ~/Library/LaunchAgents/com.mukesh.eyebreak.plist
rm -rf ~/Library/EyeBreak
```

## What gets installed where

```
~/Library/LaunchAgents/com.mukesh.eyebreak.plist   (launchd job, fires every 10 min)
~/Library/EyeBreak/eye_break.py                    (the script)
~/Library/EyeBreak/uninstall.sh                    (for one-line uninstall)
~/Library/EyeBreak/config.json                     (your settings; created on first run)
~/Library/EyeBreak/events.log                      (history of every popup + dismiss)
~/Library/EyeBreak/stdout.log / stderr.log         (launchd captures)
```

## Design

- **Zero external dependencies.** Uses `/usr/bin/python3` + Tkinter — both ship with macOS.
- **Single-shot script.** launchd fires the script every N minutes; the script shows once, exits. No long-running daemon. If the script crashes, the next firing recovers automatically.
- **Lock file** prevents popup stacking if two firings overlap (slow disk, system load).
- **Active hours** (default 7am–11pm) silently skip popups outside.
- **Stale-lock cleanup** auto-removes locks older than 5 minutes (handles the "popup crashed before releasing lock" case).
- **Config is hot-reloaded** on every firing — change `config.json`, no reinstall needed.

## Known limitations

- macOS only (uses launchd + AppKit-flavored Tkinter).
- Does not detect "currently presenting / on a video call" — the popup will appear over Zoom. (Fix: add active hours like 8pm-9pm during meeting blocks; or hit ESC.)
- Multi-monitor: popup appears on the primary display only.
