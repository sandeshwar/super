"""Native filesystem helpers for the local dashboard."""

from __future__ import annotations

import os
import platform
import subprocess
import shutil


def pick_directory(initial: str | None = None) -> str | None:
    """Open the OS folder picker. Returns an absolute path, or None if cancelled."""
    start = None
    if initial:
        cand = os.path.abspath(os.path.expanduser(initial))
        if os.path.isdir(cand):
            start = cand
    system = platform.system()
    if system == "Darwin":
        return _pick_macos(start)
    if system == "Linux":
        return _pick_linux(start)
    if system == "Windows":
        return _pick_windows(start)
    return _pick_tk(start)


def _pick_macos(start: str | None) -> str | None:
    # Native Choose Folder dialog via AppleScript.
    parts = ['choose folder with prompt "Select working directory"']
    if start:
        # Escape for AppleScript string
        esc = start.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'default location (POSIX file "{esc}")')
    script = f'POSIX path of ({" ".join(parts)})'
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    path = (r.stdout or "").strip().rstrip("/")
    return os.path.abspath(path) if path else None


def _pick_linux(start: str | None) -> str | None:
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title=Select working directory"]
        if start:
            cmd.append(f"--filename={start}/")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        path = (r.stdout or "").strip()
        return os.path.abspath(path) if path else None
    if shutil.which("kdialog"):
        cmd = ["kdialog", "--getexistingdirectory", start or os.path.expanduser("~")]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        path = (r.stdout or "").strip()
        return os.path.abspath(path) if path else None
    return _pick_tk(start)


def _pick_windows(start: str | None) -> str | None:
    # Prefer PowerShell FolderBrowserDialog — works without Tk.
    start_lit = (start or os.path.expanduser("~")).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = 'Select working directory'; "
        f"$d.SelectedPath = '{start_lit}'; "
        "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.SelectedPath }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _pick_tk(start)
    if r.returncode != 0:
        return None
    path = (r.stdout or "").strip().splitlines()
    path = path[-1].strip() if path else ""
    return os.path.abspath(path) if path else None


def _pick_tk(start: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        path = filedialog.askdirectory(
            title="Select working directory",
            initialdir=start or os.path.expanduser("~"),
            mustexist=True,
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    path = (path or "").strip()
    return os.path.abspath(path) if path else None
