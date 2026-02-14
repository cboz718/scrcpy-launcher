# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cross-platform GUI launcher for [scrcpy](https://github.com/Genymobile/scrcpy), an Android screen mirroring tool. Single-file tkinter app with optional PyInstaller packaging. Supports Windows (.bat) and Mac/Linux (.sh) wrapper scripts.

## Commands

```bash
# Run from source
python launcher.pyw            # or double-click on Windows

# Build standalone exe (Windows)
build.bat                      # generates icon + runs PyInstaller
# Output: dist/scrcpy Launcher.exe

# Build deps (not needed for running from source)
pip install pyinstaller pillow
```

## Architecture

- **launcher.pyw** — Tkinter GUI (single file, no external deps beyond stdlib). Uses `.pyw` to suppress console window on Windows.
- **SCRIPT_DIR vs DATA_DIR vs OUTPUT_DIR** — When frozen on Windows, `SCRIPT_DIR` = exe's directory. On macOS `.app`, `SCRIPT_DIR` = `Contents/Resources/` inside the `.app` (scripts and configs bundled there by `build.sh`), `OUTPUT_DIR` = directory containing the `.app` (for Recordings/, Screenshots/). `DATA_DIR` = `sys._MEIPASS` temp dir (azure-theme, icon). When running from source, all three point to the same directory.
- **azure-theme/** — [Azure ttk theme](https://github.com/rdbende/Azure-ttk-theme) (dark mode), falls back to `clam` if missing. Loaded via `root.tk.call("source", azure_tcl)`.
- **build_icon.py** — Generates `launcher.ico` from the phone emoji using Pillow + Segoe UI Emoji font.
- **build.bat** — Runs `build_icon.py` then PyInstaller with `--onefile --noconsole --add-data azure-theme`.
- **env.sh** — Optional PATH configuration for macOS/Linux. Sourced with bash at startup; if absent or all-commented, launcher falls back to hardcoded well-known paths.
- **Scripts** — Wrapper scripts that call scrcpy with preset flags. All accept extra args via passthrough (`%*` on bat, `"$@"` on sh). Recordings save to `./Recordings/`.

## Scripts

| Windows | Mac/Linux | Purpose |
|---|---|---|
| `mirror.bat` | `mirror.sh` | Basic mirroring with `--show-touches --stay-awake` |
| `record_video.bat` | `record_video.sh` | Record to timestamped MP4 in `Recordings/` |
| `tcpip.bat` | `tcpip.sh` | Wireless mode via `--tcpip` |

## Launcher Features

- **Device detection** — Parses `adb devices -l` for serial, model, connection type
- **Launch options** — Checkboxes append flags: limit resolution, new display, screen off, always on top, no control, start app
- **Utilities** — Screenshot (save/clipboard), TCP/IP connect, pair device, install/uninstall APK, force stop, clear app data
- **Output log** — Scrollable text box captures stdout/stderr from all operations
- **State preservation** — Selected device and app persist across refreshes

## Development Patterns

- All subprocess calls use `**_POPEN_KWARGS` which adds `CREATE_NO_WINDOW` on Windows only
- Background operations use `threading.Thread(daemon=True)` + `root.after(0, ...)` for thread-safe tkinter updates
- `_get_selected_serial()` returns `None` (single device), a serial string (multi-device), or `False` (error/no device) — callers check `is False`
- Adding a new script: drop a `.bat` or `.sh` file in the directory — discovered automatically. To exclude a script, add its filename to `IGNORED_SCRIPTS` set.
- Adding a new launch checkbox: add `BooleanVar`, `Checkbutton`, and entry in `_get_launch_options()`
- Adding a new utility: add button in `__init__`, method follows the pattern of `_get_selected_serial()` → build cmd → thread → log output → refresh

## Prerequisites

**Runtime:**
- Python 3 with tkinter
- `scrcpy` and `adb` on PATH or in the same directory
- Android device connected via USB or paired for wireless debugging

**Build only (for packaging exe):**
- PyInstaller (`pip install pyinstaller`)
- Pillow (`pip install pillow`) — for icon generation
