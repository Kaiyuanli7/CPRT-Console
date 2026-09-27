"""Auto-update on macOS via launchd (runs `cli.py scheduled`).

With the daily scan on, launchd starts the job every day at the chosen time: the Copart scan runs daily and the
full update on the chosen weekday. If the Mac is asleep at that time, macOS runs the job when it wakes.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from . import paths, settings as settings_mod

LABEL = "com.cprtconsole.weekly"


def supported() -> bool:
    return sys.platform == "darwin"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build_plist(s: dict) -> dict:
    log = str(paths.data_path("logs", "scheduled.log"))
    when = {"Hour": int(s["schedule_hour"]), "Minute": int(s["schedule_minute"])}
    if not s.get("scan_daily"):
        when = {"Weekday": int(s["schedule_weekday"]), **when}
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(paths.ROOT / "cli.py"), "scheduled"],
        "WorkingDirectory": str(paths.ROOT),
        "EnvironmentVariables": {"CPRT_DATA_DIR": str(paths.DATA), "PYTHONUNBUFFERED": "1"},
        "StartCalendarInterval": when,
        "StandardOutPath": log, "StandardErrorPath": log, "RunAtLoad": False,
    }


def protected_folder_warning() -> str | None:
    home = Path.home()
    for name in ("Downloads", "Desktop", "Documents"):
        try:
            paths.ROOT.relative_to(home / name)
        except ValueError:
            continue
        return (f"This folder is inside {name}. macOS blocks background tasks from reading {name}, so "
                f"move the whole cprt-console folder to your home folder ({home}) before turning this on.")
    return None


def _launchctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(s: dict) -> str:
    if not supported():
        raise RuntimeError("Automatic weekly updates are only available on macOS.")
    p = plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    uninstall(quiet=True)
    with open(p, "wb") as f:
        plistlib.dump(build_plist(s), f)
    domain = f"gui/{os.getuid()}"
    res = _launchctl("bootstrap", domain, str(p))
    if res.returncode != 0:
        res = _launchctl("load", "-w", str(p))
        if res.returncode != 0:
            raise RuntimeError(f"macOS refused the schedule: {res.stderr.strip() or res.stdout.strip()}")
    return f"Auto-update is on: {settings_mod.schedule_summary(s)}."


def uninstall(quiet: bool = False) -> str:
    p = plist_path()
    if supported():
        _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
        if p.exists():
            _launchctl("unload", str(p))
    if p.exists():
        p.unlink()
    return "Weekly auto-update turned off."


def status(s: dict) -> dict:
    installed = plist_path().exists()
    return {"supported": supported(), "installed": installed,
            "when": settings_mod.schedule_summary(s), "warning": protected_folder_warning()}


def notify(title: str, message: str) -> None:
    """macOS notification banner; silently does nothing elsewhere."""
    if not supported():
        return
    safe = lambda x: x.replace('"', "'")[:200]  # noqa: E731
    subprocess.run(["osascript", "-e", f'display notification "{safe(message)}" with title "{safe(title)}"'],
                   capture_output=True)
