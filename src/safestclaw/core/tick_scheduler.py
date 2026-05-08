"""
Cross-platform installer for the Telegram-tick scheduled task.

Lets a user run ``safestclaw telegram-tick --install`` once and have
the OS run the tick every N minutes from then on. State that lets us
find / remove our entry later:

  * Linux & macOS: appends a line to the user's crontab tagged with a
    fixed marker comment.
  * Windows: creates a Task Scheduler entry under a fixed task name
    via ``schtasks``.

We never write the cron / scheduler state silently — every install
prints exactly what was registered, and uninstall is the reverse.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Tag used to find/remove our crontab entry later. Don't change it
# without writing a migration — old installs would leak.
_CRON_MARKER = "safestclaw-telegram-tick"
# Windows Task Scheduler task name. Same caveat — don't rename casually.
_WINDOWS_TASK_NAME = "SafestClaw Telegram Tick"


@dataclass
class ScheduleStatus:
    """Result of inspecting / installing / uninstalling the schedule."""
    installed: bool
    detail: str  # human-readable line(s) describing the current state


def _python_exe() -> str:
    """Best-effort path to the Python interpreter running SafestClaw."""
    return sys.executable or "python"


def _tick_command() -> str:
    """The exact command line cron / Task Scheduler will run."""
    # `python -m safestclaw telegram-tick` works whether SafestClaw was
    # installed via pip, pipx, or a venv — the active interpreter knows
    # where its own site-packages are.
    return f'"{_python_exe()}" -m safestclaw telegram-tick'


# ──────────────────────────────────────────────────────────────────────
# POSIX (Linux + macOS) — crontab
# ──────────────────────────────────────────────────────────────────────


def _read_crontab() -> list[str]:
    """Return the user's current crontab lines, or [] if none."""
    if shutil.which("crontab") is None:
        raise RuntimeError(
            "`crontab` not available on this system. Install cron, or "
            "install the schedule manually."
        )
    res = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True,
    )
    # `crontab -l` exits 1 with "no crontab" when the user has none.
    if res.returncode == 0:
        return res.stdout.splitlines()
    return []


def _write_crontab(lines: list[str]) -> None:
    """Replace the user's crontab with the given lines."""
    body = "\n".join(lines).rstrip() + "\n"
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
    proc.communicate(body.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"crontab install failed (exit {proc.returncode})")


def _cron_status() -> ScheduleStatus:
    try:
        lines = _read_crontab()
    except RuntimeError as e:
        return ScheduleStatus(False, str(e))
    matches = [ln for ln in lines if _CRON_MARKER in ln]
    if matches:
        return ScheduleStatus(True, "\n".join(matches))
    return ScheduleStatus(False, "no SafestClaw cron entry")


def _install_cron(interval_minutes: int) -> ScheduleStatus:
    cmd = _tick_command()
    schedule = f"*/{interval_minutes} * * * *"
    new_line = f"{schedule} {cmd}  # {_CRON_MARKER}"

    lines = _read_crontab()
    # Strip any prior SafestClaw entry so reinstalling is idempotent.
    lines = [ln for ln in lines if _CRON_MARKER not in ln]
    lines.append(new_line)
    _write_crontab(lines)
    return ScheduleStatus(True, new_line)


def _uninstall_cron() -> ScheduleStatus:
    lines = _read_crontab()
    kept = [ln for ln in lines if _CRON_MARKER not in ln]
    if len(kept) == len(lines):
        return ScheduleStatus(False, "no SafestClaw cron entry to remove")
    _write_crontab(kept)
    return ScheduleStatus(False, "removed SafestClaw cron entry")


# ──────────────────────────────────────────────────────────────────────
# Windows — schtasks
# ──────────────────────────────────────────────────────────────────────


def _win_status() -> ScheduleStatus:
    if shutil.which("schtasks") is None:
        return ScheduleStatus(False, "`schtasks` not available")
    res = subprocess.run(
        ["schtasks", "/Query", "/TN", _WINDOWS_TASK_NAME],
        capture_output=True, text=True,
    )
    if res.returncode == 0:
        return ScheduleStatus(True, f"task `{_WINDOWS_TASK_NAME}` is registered")
    return ScheduleStatus(False, f"task `{_WINDOWS_TASK_NAME}` not registered")


def _install_win(interval_minutes: int) -> ScheduleStatus:
    if shutil.which("schtasks") is None:
        raise RuntimeError("`schtasks` not available on this system")

    # /F overwrites if it already exists, so this is idempotent.
    res = subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", _WINDOWS_TASK_NAME,
            "/TR", _tick_command(),
            "/SC", "MINUTE",
            "/MO", str(interval_minutes),
            "/F",
        ],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"schtasks /Create failed: {res.stderr.strip() or res.stdout.strip()}"
        )
    return ScheduleStatus(
        True,
        f"task `{_WINDOWS_TASK_NAME}` runs `{_tick_command()}` every "
        f"{interval_minutes} minute(s)",
    )


def _uninstall_win() -> ScheduleStatus:
    if shutil.which("schtasks") is None:
        return ScheduleStatus(False, "`schtasks` not available")
    res = subprocess.run(
        ["schtasks", "/Delete", "/TN", _WINDOWS_TASK_NAME, "/F"],
        capture_output=True, text=True,
    )
    if res.returncode == 0:
        return ScheduleStatus(False, f"removed task `{_WINDOWS_TASK_NAME}`")
    return ScheduleStatus(
        False,
        f"could not remove task `{_WINDOWS_TASK_NAME}` "
        f"(it may not have been registered)",
    )


# ──────────────────────────────────────────────────────────────────────
# Public API — platform dispatcher
# ──────────────────────────────────────────────────────────────────────


def status() -> ScheduleStatus:
    """Is the tick currently scheduled?"""
    if platform.system() == "Windows":
        return _win_status()
    return _cron_status()


def install(interval_minutes: int = 2) -> ScheduleStatus:
    """Register the OS-level schedule. Idempotent — replaces any prior entry."""
    if interval_minutes < 1:
        raise ValueError("interval_minutes must be >= 1")
    if platform.system() == "Windows":
        return _install_win(interval_minutes)
    return _install_cron(interval_minutes)


def uninstall() -> ScheduleStatus:
    """Remove our scheduled task, if it exists."""
    if platform.system() == "Windows":
        return _uninstall_win()
    return _uninstall_cron()
