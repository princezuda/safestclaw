"""
Cross-platform installer for the SafestClaw web UI auto-start service.

Same shape as ``tick_scheduler``: ``install`` / ``uninstall`` /
``status`` register a service that launches ``safestclaw web`` at
login (or boot, on Linux when lingering is enabled) so the web UI
keeps serving without the user having to keep a terminal open.

  * Linux: a systemd *user* service in
    ``~/.config/systemd/user/safestclaw-web.service`` plus
    ``systemctl --user enable --now``. Lingering (``loginctl
    enable-linger``) is recommended separately if you need the
    service to survive logout — we don't toggle it for you.
  * macOS: a launchd agent at
    ``~/Library/LaunchAgents/com.safestclaw.web.plist`` loaded with
    ``launchctl``.
  * Windows: a Task Scheduler entry under a fixed task name, triggered
    on user logon.

We never silently overwrite — every install prints exactly what was
written and what command will run.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Don't rename these without a migration — old installs would leak.
_LINUX_UNIT_NAME = "safestclaw-web.service"
_MACOS_LABEL = "com.safestclaw.web"
_WINDOWS_TASK_NAME = "SafestClaw Web"


@dataclass
class ServiceStatus:
    """Result of inspecting / installing / uninstalling the service."""
    installed: bool
    detail: str


def _python_exe() -> str:
    return sys.executable or "python"


def _web_command(port: int) -> list[str]:
    """argv that the service will run."""
    return [_python_exe(), "-m", "safestclaw", "web", "--port", str(port)]


def _web_command_string(port: int) -> str:
    """Same command as a shell-friendly string for inspection / Windows."""
    return " ".join(f'"{p}"' if " " in p else p for p in _web_command(port))


# ──────────────────────────────────────────────────────────────────────
# Linux — systemd user service
# ──────────────────────────────────────────────────────────────────────


def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / _LINUX_UNIT_NAME


def _systemd_unit_body(port: int) -> str:
    exec_start = " ".join(_web_command(port))
    return (
        "[Unit]\n"
        "Description=SafestClaw Web UI\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True, text=True,
    )


def _linux_status() -> ServiceStatus:
    if not _systemd_unit_path().exists():
        return ServiceStatus(False, f"unit `{_LINUX_UNIT_NAME}` not installed")
    if shutil.which("systemctl") is None:
        return ServiceStatus(True, "unit file present but systemctl missing")
    res = _systemctl_user("is-active", _LINUX_UNIT_NAME)
    state = res.stdout.strip() or res.stderr.strip()
    return ServiceStatus(True, f"unit `{_LINUX_UNIT_NAME}` — {state}")


def _install_linux(port: int) -> ServiceStatus:
    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl not available on this system")
    unit = _systemd_unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(_systemd_unit_body(port))

    daemon_reload = _systemctl_user("daemon-reload")
    if daemon_reload.returncode != 0:
        raise RuntimeError(
            f"systemctl daemon-reload failed: {daemon_reload.stderr.strip()}"
        )
    enable = _systemctl_user("enable", "--now", _LINUX_UNIT_NAME)
    if enable.returncode != 0:
        raise RuntimeError(
            f"systemctl enable --now failed: {enable.stderr.strip()}"
        )
    return ServiceStatus(
        True,
        f"installed `{unit}` and started it via "
        f"`systemctl --user enable --now {_LINUX_UNIT_NAME}`. "
        f"For survival after logout, run "
        f"`loginctl enable-linger \"$USER\"` once.",
    )


def _uninstall_linux() -> ServiceStatus:
    unit = _systemd_unit_path()
    if shutil.which("systemctl"):
        _systemctl_user("disable", "--now", _LINUX_UNIT_NAME)
    if unit.exists():
        unit.unlink()
        if shutil.which("systemctl"):
            _systemctl_user("daemon-reload")
        return ServiceStatus(False, f"removed `{unit}`")
    return ServiceStatus(False, "no SafestClaw web unit to remove")


# ──────────────────────────────────────────────────────────────────────
# macOS — launchd user agent
# ──────────────────────────────────────────────────────────────────────


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_MACOS_LABEL}.plist"


def _launchd_plist_body(port: int) -> str:
    args_xml = "\n".join(
        f"        <string>{arg}</string>" for arg in _web_command(port)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        '    <key>Label</key>\n'
        f'    <string>{_MACOS_LABEL}</string>\n'
        '    <key>ProgramArguments</key>\n'
        '    <array>\n'
        f'{args_xml}\n'
        '    </array>\n'
        '    <key>RunAtLoad</key>\n'
        '    <true/>\n'
        '    <key>KeepAlive</key>\n'
        '    <true/>\n'
        '</dict>\n'
        '</plist>\n'
    )


def _macos_status() -> ServiceStatus:
    plist = _launchd_plist_path()
    if not plist.exists():
        return ServiceStatus(False, f"agent `{_MACOS_LABEL}` not installed")
    return ServiceStatus(True, f"agent `{_MACOS_LABEL}` installed at {plist}")


def _install_macos(port: int) -> ServiceStatus:
    if shutil.which("launchctl") is None:
        raise RuntimeError("launchctl not available on this system")
    plist = _launchd_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_launchd_plist_body(port))
    # Unload first if it was loaded — `load -w` won't replace an active agent.
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    res = subprocess.run(
        ["launchctl", "load", "-w", str(plist)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"launchctl load failed: {res.stderr.strip() or res.stdout.strip()}"
        )
    return ServiceStatus(True, f"installed `{plist}` and loaded it via launchctl")


def _uninstall_macos() -> ServiceStatus:
    plist = _launchd_plist_path()
    if shutil.which("launchctl"):
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    if plist.exists():
        plist.unlink()
        return ServiceStatus(False, f"removed `{plist}`")
    return ServiceStatus(False, "no SafestClaw web agent to remove")


# ──────────────────────────────────────────────────────────────────────
# Windows — Task Scheduler at logon
# ──────────────────────────────────────────────────────────────────────


def _win_status() -> ServiceStatus:
    if shutil.which("schtasks") is None:
        return ServiceStatus(False, "schtasks not available")
    res = subprocess.run(
        ["schtasks", "/Query", "/TN", _WINDOWS_TASK_NAME],
        capture_output=True, text=True,
    )
    if res.returncode == 0:
        return ServiceStatus(True, f"task `{_WINDOWS_TASK_NAME}` is registered")
    return ServiceStatus(False, f"task `{_WINDOWS_TASK_NAME}` not registered")


def _install_win(port: int) -> ServiceStatus:
    if shutil.which("schtasks") is None:
        raise RuntimeError("schtasks not available on this system")
    res = subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", _WINDOWS_TASK_NAME,
            "/TR", _web_command_string(port),
            "/SC", "ONLOGON",
            "/F",
        ],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"schtasks /Create failed: {res.stderr.strip() or res.stdout.strip()}"
        )
    # Kick it off now so the user doesn't have to log out / back in.
    subprocess.run(
        ["schtasks", "/Run", "/TN", _WINDOWS_TASK_NAME],
        capture_output=True, text=True,
    )
    return ServiceStatus(
        True,
        f"task `{_WINDOWS_TASK_NAME}` runs `{_web_command_string(port)}` "
        f"at user logon (and was started now).",
    )


def _uninstall_win() -> ServiceStatus:
    if shutil.which("schtasks") is None:
        return ServiceStatus(False, "schtasks not available")
    res = subprocess.run(
        ["schtasks", "/Delete", "/TN", _WINDOWS_TASK_NAME, "/F"],
        capture_output=True, text=True,
    )
    if res.returncode == 0:
        return ServiceStatus(False, f"removed task `{_WINDOWS_TASK_NAME}`")
    return ServiceStatus(
        False,
        f"could not remove task `{_WINDOWS_TASK_NAME}` (it may not exist)",
    )


# ──────────────────────────────────────────────────────────────────────
# Public API — platform dispatcher
# ──────────────────────────────────────────────────────────────────────


def status() -> ServiceStatus:
    """Is the web service currently installed?"""
    sys_name = platform.system()
    if sys_name == "Windows":
        return _win_status()
    if sys_name == "Darwin":
        return _macos_status()
    if sys_name == "Linux":
        return _linux_status()
    return ServiceStatus(False, f"unsupported platform: {sys_name}")


def install(port: int = 8771) -> ServiceStatus:
    """Register and start the web service. Idempotent."""
    sys_name = platform.system()
    if sys_name == "Windows":
        return _install_win(port)
    if sys_name == "Darwin":
        return _install_macos(port)
    if sys_name == "Linux":
        return _install_linux(port)
    raise RuntimeError(f"unsupported platform: {sys_name}")


def uninstall() -> ServiceStatus:
    """Stop and unregister the web service."""
    sys_name = platform.system()
    if sys_name == "Windows":
        return _uninstall_win()
    if sys_name == "Darwin":
        return _uninstall_macos()
    if sys_name == "Linux":
        return _uninstall_linux()
    raise RuntimeError(f"unsupported platform: {sys_name}")
