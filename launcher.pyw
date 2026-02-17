"""scrcpy Launcher GUI — lists connected Android devices and launches scrcpy wrapper scripts."""

import datetime
import os
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# When running as a PyInstaller frozen exe, sys._MEIPASS is the temp extraction
# dir (for bundled data like the theme), while the exe itself lives elsewhere.
# SCRIPT_DIR  = where .bat/.sh scripts and config files live
# DATA_DIR    = bundled data root (theme, icon)
# OUTPUT_DIR  = where user-facing output goes (Recordings/, Screenshots/)
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(sys.executable)
    if sys.platform == "darwin" and _exe_dir.endswith(".app/Contents/MacOS"):
        # macOS .app: scripts/configs bundled in Contents/Resources/,
        # user output (Recordings/, Screenshots/) goes alongside the .app.
        SCRIPT_DIR = os.path.join(os.path.dirname(_exe_dir), "Resources")
        OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_exe_dir)))
    else:
        SCRIPT_DIR = _exe_dir
        OUTPUT_DIR = _exe_dir
    DATA_DIR = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = SCRIPT_DIR
    OUTPUT_DIR = SCRIPT_DIR

IS_WINDOWS = sys.platform == "win32"

# macOS .app bundles don't inherit the user's shell PATH, so adb/scrcpy may not
# be found. Source env.sh if present; otherwise add well-known locations.

def _source_env_file(path):
    """Source a bash file and return the resulting PATH, or None on failure."""
    try:
        result = subprocess.run(
            ["bash", "-c", f'source "{path}" && printf "%s" "$PATH"'],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def _apply_fallback_paths():
    """Add well-known SDK/tool locations to PATH."""
    extra = [
        os.path.join(os.path.expanduser("~"), "Library", "Android", "sdk", "platform-tools"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        SCRIPT_DIR,
    ]
    current = os.environ.get("PATH", "")
    new = [p for p in extra if os.path.isdir(p) and p not in current]
    if new:
        os.environ["PATH"] = current + ":" + ":".join(new)


def _env_file_has_active_lines(path):
    """Return True if the file has any non-blank, non-comment lines."""
    try:
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    return True
    except Exception:
        pass
    return False


def _load_env_path():
    """Load PATH from env.sh if it has active lines; otherwise use fallbacks."""
    env_file = os.path.join(SCRIPT_DIR, "env.sh")
    if os.path.isfile(env_file) and _env_file_has_active_lines(env_file):
        sourced = _source_env_file(env_file)
        if sourced:
            os.environ["PATH"] = sourced
            return
    _apply_fallback_paths()


if not IS_WINDOWS:
    _load_env_path()

# Only pass creationflags on Windows; ignored on Mac/Linux
_POPEN_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}

SCRIPT_EXTENSIONS = (".bat", ".vbs") if IS_WINDOWS else (".sh",)


def parse_devices():
    """Run `adb devices -l` and return a list of (serial, display_label) tuples."""
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True, text=True, timeout=10,
            **_POPEN_KWARGS,
        )
    except FileNotFoundError:
        messagebox.showerror("Error", "adb not found. Make sure adb is on PATH or in the scrcpy directory.")
        return []
    except subprocess.TimeoutExpired:
        messagebox.showerror("Error", "adb timed out.")
        return []

    devices = []
    for line in result.stdout.splitlines():
        if not line.strip() or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue

        serial = parts[0]
        model = ""
        for token in parts[2:]:
            if token.startswith("model:"):
                model = token.split(":", 1)[1].replace("_", " ")
                break

        conn = "tcpip" if ":" in serial else "usb"
        label = f"{serial}  -  {model}  ({conn})" if model else f"{serial}  ({conn})"
        devices.append((serial, label))

    return devices


def label_for_script(filename):
    """Derive a button label from a script filename."""
    name, ext = os.path.splitext(filename)
    label = name.replace("_", " ").title()
    if ext.lower() == ".vbs":
        label += " (silent)"
    return label


IGNORED_SCRIPTS = {"build.bat", "build.sh", "env.sh"}
CUSTOM_ARGS_FILE = "custom_args.txt"


def load_custom_args():
    """Load custom launch options from custom_args.txt.

    File format: one option per line as 'Label = --arg1 --arg2'.
    Blank lines and lines starting with # are ignored.
    Returns a list of (label, args_string) tuples.
    """
    path = os.path.join(SCRIPT_DIR, CUSTOM_ARGS_FILE)
    if not os.path.exists(path):
        return []
    custom = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("."):
                continue
            if "=" not in line:
                continue
            label, _, args = line.partition("=")
            label = label.strip()
            args = args.strip()
            if label and args:
                custom.append((label, args))
    return custom


def discover_scripts():
    """Find platform-appropriate launcher scripts in the script directory, sorted alphabetically."""
    return sorted(
        name for name in os.listdir(SCRIPT_DIR)
        if name.lower().endswith(SCRIPT_EXTENSIONS)
        and name.lower() not in IGNORED_SCRIPTS
    )


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("scrcpy Launcher")
        self.root.resizable(False, False)

        # Set window icon if available
        icon_ext = ".ico" if IS_WINDOWS else ".icns"
        icon_path = os.path.join(DATA_DIR, f"launcher{icon_ext}")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # Theme
        azure_tcl = os.path.join(DATA_DIR, "azure-theme", "azure.tcl")
        if os.path.exists(azure_tcl):
            root.tk.call("source", azure_tcl)
            root.tk.call("set_theme", "dark")
        else:
            ttk.Style().theme_use("clam")
        LOG_FONT = ("Consolas", 9) if IS_WINDOWS else ("Menlo", 10)
        self._log_font = LOG_FONT

        self.devices = []
        self.selected_serial = tk.StringVar()
        self.opt_limit_res = tk.BooleanVar()
        self.opt_new_display = tk.BooleanVar()
        self.opt_screen_off = tk.BooleanVar()
        self.opt_always_on_top = tk.BooleanVar()
        self.opt_no_control = tk.BooleanVar()
        self.opt_start_app = tk.BooleanVar()

        # --- Devices frame ---
        dev_frame = ttk.LabelFrame(root, text="Devices", padding=(8, 4))
        dev_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.device_inner = ttk.Frame(dev_frame)
        self.device_inner.pack(fill="x")

        btn_frame = ttk.Frame(dev_frame)
        btn_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_devices).pack(side="right")
        ttk.Button(btn_frame, text="Disconnect All", command=self.disconnect_all).pack(side="right", padx=(0, 4))

        # --- Scripts frame ---
        script_frame = ttk.LabelFrame(root, text="Launch", padding=8)
        script_frame.pack(fill="x", padx=10, pady=(4, 4))

        # Launch options
        opts_row1 = ttk.Frame(script_frame)
        opts_row1.pack(fill="x")
        ttk.Checkbutton(opts_row1, text="Limit Resolution",
                         variable=self.opt_limit_res).pack(side="left", padx=3)
        self.limit_res_entry = ttk.Entry(opts_row1, width=5)
        self.limit_res_entry.pack(side="left")
        self.limit_res_entry.insert(0, "1920")
        ttk.Checkbutton(opts_row1, text="New Display",
                         variable=self.opt_new_display).pack(side="left", padx=3)
        self.new_display_entry = ttk.Entry(opts_row1, width=10)
        self.new_display_entry.pack(side="left")
        self.new_display_entry.insert(0, "1920x1080")
        ttk.Checkbutton(opts_row1, text="Screen Off",
                         variable=self.opt_screen_off).pack(side="left", padx=3)
        ttk.Checkbutton(opts_row1, text="Always On Top",
                         variable=self.opt_always_on_top).pack(side="left", padx=3)
        ttk.Checkbutton(opts_row1, text="No Control",
                         variable=self.opt_no_control).pack(side="left", padx=3)

        # Custom args from custom_args.txt
        # Each entry is (BooleanVar, args_template, list_of_Entry)
        self.custom_args = []
        custom_entries = load_custom_args()
        if custom_entries:
            custom_row = ttk.Frame(script_frame)
            custom_row.pack(fill="x", pady=(2, 0))
            for label, args in custom_entries:
                var = tk.BooleanVar()
                ttk.Checkbutton(custom_row, text=label, variable=var).pack(side="left", padx=3)
                # One text box per {default} placeholder
                entries = []
                for match in re.finditer(r"\{(.+?)\}", args):
                    entry = ttk.Entry(custom_row, width=max(6, len(match.group(1)) + 2))
                    entry.pack(side="left", padx=(2, 0))
                    entry.insert(0, match.group(1))
                    entries.append(entry)
                self.custom_args.append((var, args, entries))

        opts_row2 = ttk.Frame(script_frame)
        opts_row2.pack(fill="x", pady=(2, 0))
        ttk.Checkbutton(opts_row2, text="Start App:", variable=self.opt_start_app).pack(side="left", padx=3)
        self.app_combo = ttk.Combobox(opts_row2, state="readonly", width=35)
        self.app_combo.pack(side="left", padx=(0, 4))
        self.app_combo.set("Select a package...")
        ttk.Button(opts_row2, text="Start Now", command=self.start_app).pack(side="left")

        ttk.Separator(script_frame, orient="horizontal").pack(fill="x", pady=(8, 4))

        scripts = discover_scripts()
        if not scripts:
            ttk.Label(script_frame, text="No scripts found in directory.").pack()
        else:
            row = ttk.Frame(script_frame)
            row.pack(pady=(4, 0))
            for name in scripts:
                label = label_for_script(name)
                ttk.Button(
                    row, text=label, width=14,
                    command=lambda n=name: self.on_launch(n),
                ).pack(side="left", padx=3, pady=2)

        # --- Utilities frame ---
        util_frame = ttk.LabelFrame(root, text="Utilities", padding=8)
        util_frame.pack(fill="x", padx=10, pady=(4, 4))

        util_row1 = ttk.Frame(util_frame)
        util_row1.pack(fill="x")
        ttk.Button(util_row1, text="Screenshot", width=14, command=self.take_screenshot).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row1, text="Copy Screenshot", width=14, command=self.copy_screenshot).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row1, text="Connect TCP/IP", width=14, command=self.connect_tcpip).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row1, text="Pair Device", width=14, command=self.pair_device).pack(side="left", padx=3, pady=2)

        util_row2 = ttk.Frame(util_frame)
        util_row2.pack(fill="x")
        ttk.Button(util_row2, text="Install APK", width=14, command=self.install_apk).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row2, text="Uninstall App", width=14, command=self.show_uninstall).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row2, text="Force Stop App", width=14, command=self.force_stop_app).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row2, text="Clear App Data", width=14, command=self.clear_app_data).pack(side="left", padx=3, pady=2)

        util_row3 = ttk.Frame(util_frame)
        util_row3.pack(fill="x")
        ttk.Button(util_row3, text="Nav Buttons On", width=14, command=self.enable_nav_buttons).pack(side="left", padx=3, pady=2)
        ttk.Button(util_row3, text="Nav Buttons Off", width=14, command=self.disable_nav_buttons).pack(side="left", padx=3, pady=2)

        # --- Output frame ---
        output_frame = ttk.LabelFrame(root, text="Output", padding=(8, 4))
        output_frame.pack(fill="both", padx=10, pady=(4, 10), expand=True)

        self.log_text = tk.Text(
            output_frame, height=12, width=70, state="disabled", wrap="word",
            font=self._log_font, bg="#1e1e1e", fg="#cccccc",
            insertbackground="#cccccc", selectbackground="#264f78",
            relief="flat", borderwidth=0, padx=6, pady=6,
        )
        scrollbar = ttk.Scrollbar(output_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.refresh_devices()

    def _append_log(self, text):
        """Append text to the output log."""
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _stream_output(self, proc, script_name):
        """Read process output in a background thread and push lines to the log."""
        for line in proc.stdout:
            self.root.after(0, self._append_log, line)
        proc.wait()
        self.root.after(0, self._append_log, f"--- {script_name} exited (code {proc.returncode}) ---\n\n")
        self.root.after(0, self.refresh_devices)

    def refresh_devices(self):
        previous = self.selected_serial.get()

        for w in self.device_inner.winfo_children():
            w.destroy()

        self.devices = parse_devices()
        self.selected_serial.set("")

        if not self.devices:
            ttk.Label(self.device_inner, text="No devices connected.").pack(anchor="w")
            return

        for serial, label in self.devices:
            ttk.Radiobutton(
                self.device_inner, text=label, variable=self.selected_serial,
                value=serial, command=self.load_packages,
            ).pack(fill="x")

        # Restore previous selection if still connected, otherwise pick first
        serials = [s for s, _ in self.devices]
        if previous in serials:
            self.selected_serial.set(previous)
        else:
            self.selected_serial.set(serials[0])
        self.load_packages()

    def _get_selected_serial(self):
        """Return the serial to use, or None for single-device. Shows warnings as needed."""
        if not self.devices:
            messagebox.showwarning("No devices", "No Android devices detected.\nConnect a device and click Refresh.")
            return False
        if len(self.devices) == 1:
            return None
        serial = self.selected_serial.get()
        if not serial:
            messagebox.showwarning("Select a device", "Multiple devices connected.\nPlease select one before launching.")
            return False
        return serial

    def disconnect_all(self):
        try:
            result = subprocess.run(
                ["adb", "disconnect"],
                capture_output=True, text=True, timeout=10,
                **_POPEN_KWARGS,
            )
            output = (result.stdout + result.stderr).strip()
            self._append_log(f">>> adb disconnect\n{output}\n\n")
        except Exception as e:
            self._append_log(f">>> adb disconnect\nError: {e}\n\n")
        self.refresh_devices()

    def connect_tcpip(self):
        serial = self._get_selected_serial()
        if serial is False:
            return
        # Use the selected serial for multi-device, or the single device's serial
        target = serial or self.devices[0][0]

        if ":" in target:
            messagebox.showinfo("Already wireless", f"{target} is already a TCP/IP connection.")
            return

        self._append_log(f">>> Connect {target} over TCP/IP\n")

        def _run():
            try:
                # Get the device's Wi-Fi IP
                ip_cmd = ["adb", "-s", target, "shell", "ip", "route"]
                ip_result = subprocess.run(
                    ip_cmd, capture_output=True, text=True, timeout=10, **_POPEN_KWARGS,
                )
                device_ip = None
                for line in ip_result.stdout.splitlines():
                    if "src" in line:
                        parts = line.strip().split()
                        idx = parts.index("src")
                        if idx + 1 < len(parts):
                            device_ip = parts[idx + 1]
                            break

                if not device_ip:
                    self.root.after(0, self._append_log, "Could not determine device IP. Is Wi-Fi connected?\n\n")
                    return

                self.root.after(0, self._append_log, f"Device IP: {device_ip}\n")

                # Switch device to TCP/IP mode
                tcpip_result = subprocess.run(
                    ["adb", "-s", target, "tcpip", "5555"],
                    capture_output=True, text=True, timeout=10, **_POPEN_KWARGS,
                )
                self.root.after(0, self._append_log, f"{tcpip_result.stdout.strip()}\n")

                # Give the device a moment to restart adbd
                import time
                time.sleep(2)

                # Connect over TCP/IP
                connect_result = subprocess.run(
                    ["adb", "connect", f"{device_ip}:5555"],
                    capture_output=True, text=True, timeout=10, **_POPEN_KWARGS,
                )
                self.root.after(0, self._append_log, f"{connect_result.stdout.strip()}\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def take_screenshot(self):
        serial = self._get_selected_serial()
        if serial is False:
            return

        screenshot_dir = os.path.join(OUTPUT_DIR, "Screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        cmd = ["adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += ["exec-out", "screencap", "-p"]

        self._append_log(f">>> Screenshot: {filename}\n")

        def _run():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, timeout=15, **_POPEN_KWARGS,
                )
                if result.returncode == 0 and result.stdout:
                    with open(filepath, "wb") as f:
                        f.write(result.stdout)
                    self.root.after(0, self._append_log, f"Saved to Screenshots/{filename}\n\n")
                else:
                    err = result.stderr.decode(errors="replace").strip()
                    self.root.after(0, self._append_log, f"Failed: {err}\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def copy_screenshot(self):
        serial = self._get_selected_serial()
        if serial is False:
            return

        cmd = ["adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += ["exec-out", "screencap", "-p"]

        self._append_log(">>> Copy screenshot to clipboard\n")

        def _run():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, timeout=15, **_POPEN_KWARGS,
                )
                if result.returncode != 0 or not result.stdout:
                    err = result.stderr.decode(errors="replace").strip()
                    self.root.after(0, self._append_log, f"Failed: {err}\n\n")
                    return

                # Write to temp file, copy to clipboard, then clean up
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(result.stdout)
                tmp.close()

                try:
                    if IS_WINDOWS:
                        # Use -File with a script block to avoid string interpolation issues
                        ps_script = (
                            "Add-Type -AssemblyName System.Windows.Forms\n"
                            "$img = [System.Drawing.Image]::FromFile($args[0])\n"
                            "[System.Windows.Forms.Clipboard]::SetImage($img)"
                        )
                        subprocess.run([
                            "powershell", "-NoProfile", "-Command", ps_script, tmp.name,
                        ], timeout=10, **_POPEN_KWARGS)
                    else:
                        subprocess.run([
                            "osascript", "-e",
                            f'set the clipboard to '
                            f'(read (POSIX file "{tmp.name}") as \u00ABclass PNGf\u00BB)',
                        ], timeout=10)
                    self.root.after(0, self._append_log, "Copied to clipboard\n\n")
                finally:
                    os.unlink(tmp.name)
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def install_apk(self):
        serial = self._get_selected_serial()
        if serial is False:
            return

        filepath = filedialog.askopenfilename(
            title="Select APK to install",
            filetypes=[("APK files", "*.apk"), ("All files", "*.*")],
        )
        if not filepath:
            return

        cmd = ["adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += ["install", "-r", filepath]

        filename = os.path.basename(filepath)
        self._append_log(f">>> Installing {filename}\n")

        def _run():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120, **_POPEN_KWARGS,
                )
                output = (result.stdout + result.stderr).strip()
                self.root.after(0, self._append_log, f"{output}\n\n")
            except subprocess.TimeoutExpired:
                self.root.after(0, self._append_log, "Install timed out.\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def show_uninstall(self):
        serial = self._get_selected_serial()
        if serial is False:
            return
        target = serial or self.devices[0][0]

        # Create popup window
        win = tk.Toplevel(self.root)
        win.title("Uninstall App")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Loading packages...").pack(padx=20, pady=(15, 5))

        combo = ttk.Combobox(win, state="readonly", width=40)
        combo.pack(padx=20, pady=5)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(padx=20, pady=(5, 15))
        uninstall_btn = ttk.Button(btn_frame, text="Uninstall", state="disabled")
        uninstall_btn.pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side="left")

        def _do_uninstall():
            package = combo.get()
            if not package:
                return
            if not messagebox.askyesno("Confirm uninstall", f"Uninstall {package}?", parent=win):
                return
            win.destroy()

            self._append_log(f">>> Uninstalling {package}\n")
            cmd = ["adb", "-s", target, "shell", "pm", "uninstall", package]

            def _run():
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30, **_POPEN_KWARGS,
                    )
                    output = (result.stdout + result.stderr).strip()
                    self.root.after(0, self._append_log, f"{output}\n\n")
                except Exception as e:
                    self.root.after(0, self._append_log, f"Error: {e}\n\n")
                self.root.after(0, self.refresh_devices)

            threading.Thread(target=_run, daemon=True).start()

        uninstall_btn.configure(command=_do_uninstall)

        self._append_log(f">>> Loading packages from {target}\n")

        def _load():
            try:
                result = subprocess.run(
                    ["adb", "-s", target, "shell", "pm", "list", "packages", "-3"],
                    capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                )
                packages = sorted(
                    line.replace("package:", "").strip()
                    for line in result.stdout.splitlines()
                    if line.startswith("package:")
                )

                def _update():
                    if packages:
                        combo["values"] = packages
                        combo.set(packages[0])
                        uninstall_btn.configure(state="normal")
                        self._append_log(f"Found {len(packages)} packages\n\n")
                    else:
                        combo.set("No packages found")
                        self._append_log("No third-party packages found.\n\n")

                self.root.after(0, _update)
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
                self.root.after(0, win.destroy)

        threading.Thread(target=_load, daemon=True).start()

    def force_stop_app(self):
        serial = self._get_selected_serial()
        if serial is False:
            return
        target = serial or self.devices[0][0]

        package = self.app_combo.get()
        if not package or package.startswith("Select") or package.startswith("No ") or package == "Loading...":
            messagebox.showwarning("No package", "No package selected.\nSelect one from the app list in the Launch section.")
            return

        self._append_log(f">>> Force stopping {package}\n")
        cmd = ["adb", "-s", target, "shell", "am", "force-stop", package]

        def _run():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                )
                output = (result.stdout + result.stderr).strip()
                self.root.after(0, self._append_log, f"{output or 'Done'}\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def clear_app_data(self):
        serial = self._get_selected_serial()
        if serial is False:
            return
        target = serial or self.devices[0][0]

        package = self.app_combo.get()
        if not package or package.startswith("Select") or package.startswith("No ") or package == "Loading...":
            messagebox.showwarning("No package", "No package selected.\nSelect one from the app list in the Launch section.")
            return

        if not messagebox.askyesno("Confirm clear data", f"Clear all data for {package}?\n\nThis will delete all app data, caches, and sign you out."):
            return

        self._append_log(f">>> Clearing data for {package}\n")
        cmd = ["adb", "-s", target, "shell", "pm", "clear", package]

        def _run():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                )
                output = (result.stdout + result.stderr).strip()
                self.root.after(0, self._append_log, f"{output}\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def pair_device(self):
        win = tk.Toplevel(self.root)
        win.title("Pair / Connect Device")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Device IP:").pack(padx=20, pady=(15, 2), anchor="w")
        ip_entry = ttk.Entry(win, width=30)
        ip_entry.pack(padx=20, pady=(0, 8))
        ip_entry.insert(0, "192.168.1.x")
        ip_entry.select_range(0, tk.END)
        ip_entry.focus_set()

        ttk.Label(win, text="Connect port:").pack(padx=20, pady=(0, 2), anchor="w")
        connect_port_entry = ttk.Entry(win, width=10)
        connect_port_entry.pack(padx=20, pady=(0, 8), anchor="w")

        sep = ttk.Separator(win, orient="horizontal")
        sep.pack(fill="x", padx=20, pady=(4, 8))

        ttk.Label(win, text="Pairing port (leave blank to skip pairing):").pack(padx=20, pady=(0, 2), anchor="w")
        pair_port_entry = ttk.Entry(win, width=10)
        pair_port_entry.pack(padx=20, pady=(0, 8), anchor="w")

        ttk.Label(win, text="Pairing code:").pack(padx=20, pady=(0, 2), anchor="w")
        code_entry = ttk.Entry(win, width=10)
        code_entry.pack(padx=20, pady=(0, 8), anchor="w")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(padx=20, pady=(0, 15))

        def _do_connect():
            ip = ip_entry.get().strip()
            connect_port = connect_port_entry.get().strip()
            pair_port = pair_port_entry.get().strip()
            code = code_entry.get().strip()

            if not ip or not connect_port:
                messagebox.showwarning("Missing info", "IP and connect port are required.", parent=win)
                return

            needs_pair = bool(pair_port and code)
            if pair_port and not code:
                messagebox.showwarning("Missing info", "Enter the pairing code for the pairing port.", parent=win)
                return

            win.destroy()

            def _run():
                try:
                    # Step 1: Pair (if pairing fields are filled)
                    if needs_pair:
                        pair_addr = f"{ip}:{pair_port}"
                        self.root.after(0, self._append_log, f">>> Pairing with {pair_addr}\n")
                        result = subprocess.run(
                            ["adb", "pair", pair_addr, code],
                            capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                        )
                        output = (result.stdout + result.stderr).strip()
                        self.root.after(0, self._append_log, f"{output}\n")

                        if result.returncode != 0 or "failed" in output.lower():
                            self.root.after(0, self._append_log, "Pairing failed, skipping connect.\n\n")
                            self.root.after(0, self.refresh_devices)
                            return

                    # Step 2: Connect
                    connect_addr = f"{ip}:{connect_port}"
                    self.root.after(0, self._append_log, f">>> Connecting to {connect_addr}\n")
                    result = subprocess.run(
                        ["adb", "connect", connect_addr],
                        capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                    )
                    output = (result.stdout + result.stderr).strip()
                    self.root.after(0, self._append_log, f"{output}\n\n")
                except Exception as e:
                    self.root.after(0, self._append_log, f"Error: {e}\n\n")
                self.root.after(0, self.refresh_devices)

            threading.Thread(target=_run, daemon=True).start()

        ttk.Button(btn_frame, text="Connect", command=_do_connect).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side="left")

    def load_packages(self):
        if not self.devices:
            return
        target = self.selected_serial.get() or self.devices[0][0]

        previous_pkg = self.app_combo.get()
        self._append_log(f">>> Loading packages from {target}\n")
        self.app_combo.set("Loading...")

        def _run():
            try:
                result = subprocess.run(
                    ["adb", "-s", target, "shell", "pm", "list", "packages", "-3"],
                    capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                )
                packages = sorted(
                    line.replace("package:", "").strip()
                    for line in result.stdout.splitlines()
                    if line.startswith("package:")
                )

                def _update():
                    if packages:
                        self.app_combo["values"] = packages
                        if previous_pkg in packages:
                            self.app_combo.set(previous_pkg)
                        else:
                            self.app_combo.set(packages[0])
                        self._append_log(f"Found {len(packages)} packages\n\n")
                    else:
                        self.app_combo["values"] = []
                        self.app_combo.set("No packages found")
                        self._append_log("No third-party packages found.\n\n")

                self.root.after(0, _update)
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")

        threading.Thread(target=_run, daemon=True).start()

    def start_app(self):
        serial = self._get_selected_serial()
        if serial is False:
            return
        target = serial or self.devices[0][0]

        package = self.app_combo.get()
        if not package or package.startswith("Select") or package.startswith("No ") or package == "Loading...":
            messagebox.showwarning("No package", "Load the package list first using 'Load Apps'\nin the Launch section.")
            return

        cmd = ["adb", "-s", target, "shell", "monkey", "-p", package,
               "-c", "android.intent.category.LAUNCHER", "1"]

        self._append_log(f">>> Starting {package}\n")

        def _run():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, **_POPEN_KWARGS,
                )
                output = (result.stdout + result.stderr).strip()
                self.root.after(0, self._append_log, f"{output}\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")
            self.root.after(0, self.refresh_devices)

        threading.Thread(target=_run, daemon=True).start()

    def _set_nav_overlay(self, enable_three_button):
        """Toggle between 3-button and gesture navigation via overlays."""
        serial = self._get_selected_serial()
        if serial is False:
            return
        target = serial or self.devices[0][0]

        if enable_three_button:
            disable = "com.android.internal.systemui.navbar.gestural"
            enable = "com.android.internal.systemui.navbar.threebutton"
            label = "3-button navigation"
        else:
            disable = "com.android.internal.systemui.navbar.threebutton"
            enable = "com.android.internal.systemui.navbar.gestural"
            label = "gesture navigation"

        self._append_log(f">>> Switching to {label}\n")

        def _run():
            try:
                for action, overlay in [("disable", disable), ("enable", enable)]:
                    result = subprocess.run(
                        ["adb", "-s", target, "shell", "cmd", "overlay", action, overlay],
                        capture_output=True, text=True, timeout=10, **_POPEN_KWARGS,
                    )
                    output = (result.stdout + result.stderr).strip()
                    if output:
                        self.root.after(0, self._append_log, f"{output}\n")
                self.root.after(0, self._append_log, f"Switched to {label}\n\n")
            except Exception as e:
                self.root.after(0, self._append_log, f"Error: {e}\n\n")

        threading.Thread(target=_run, daemon=True).start()

    def enable_nav_buttons(self):
        self._set_nav_overlay(True)

    def disable_nav_buttons(self):
        self._set_nav_overlay(False)

    def _get_launch_options(self):
        """Build extra args list from checked launch options."""
        args = []
        if self.opt_limit_res.get():
            res = self.limit_res_entry.get().strip() or "1920"
            args += [f"-m{res}", "--max-fps=60"]
        if self.opt_new_display.get():
            res = self.new_display_entry.get().strip() or "1920x1080"
            args.append(f"--new-display={res}")
        if self.opt_screen_off.get():
            args.append("--turn-screen-off")
        if self.opt_always_on_top.get():
            args.append("--always-on-top")
        if self.opt_no_control.get():
            args.append("--no-control")
        if self.opt_start_app.get():
            package = self.app_combo.get()
            if package and not package.startswith("Select") and not package.startswith("No ") and package != "Loading...":
                args.append(f"--start-app={package}")
            else:
                messagebox.showwarning("No package", "Start App is checked but no package is selected.\nLoad the package list first using 'Load Apps'.")
                return None
        for var, arg_template, entries in self.custom_args:
            if var.get():
                if entries:
                    resolved = arg_template
                    for entry in entries:
                        val = entry.get().strip()
                        resolved = re.sub(r"\{.+?\}", val, resolved, count=1)
                    args.extend(resolved.split())
                else:
                    args.extend(arg_template.split())
        return args

    def on_launch(self, script_name):
        serial = self._get_selected_serial()
        if serial is False:
            return

        options = self._get_launch_options()
        if options is None:
            return

        path = os.path.join(SCRIPT_DIR, script_name)
        extra_args = (["-s", serial] if serial else []) + options

        if script_name.lower().endswith(".vbs"):
            cmd = ["wscript", path] + extra_args
        elif script_name.lower().endswith(".sh"):
            cmd = ["bash", path] + extra_args
        else:
            cmd = [path] + extra_args

        self._append_log(f">>> {script_name} {' '.join(extra_args)}\n")

        try:
            proc = subprocess.Popen(
                cmd, cwd=OUTPUT_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, **_POPEN_KWARGS,
            )
            threading.Thread(target=self._stream_output, args=(proc, script_name), daemon=True).start()
        except Exception as e:
            self._append_log(f"Error launching {script_name}: {e}\n")


if __name__ == "__main__":
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()
