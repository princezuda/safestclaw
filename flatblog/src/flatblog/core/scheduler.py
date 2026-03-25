"""Topic rotation state + system scheduler (cron on Linux/macOS, Task Scheduler on Windows)."""
from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_IS_WINDOWS = platform.system() == "Windows"
_TASK_NAME  = "FlatblogRun"


STATE_DIR = Path.home() / ".flatblog" / "state"
CRON_MARKER = "# flatblog-cron"


def next_topic(topics: list[str], schedule_name: str = "default") -> str:
    """Return the next topic in the rotation and advance the index."""
    if not topics:
        return ""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = STATE_DIR / f"{schedule_name}-topics.json"
    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}
    idx = state.get("index", 0) % len(topics)
    topic = topics[idx]
    state["index"] = (idx + 1) % len(topics)
    state["last_topic"] = topic
    state["last_run"] = datetime.now().isoformat()
    state_path.write_text(json.dumps(state, indent=2))
    return topic


def topic_state(schedule_name: str = "default") -> dict[str, Any]:
    state_path = STATE_DIR / f"{schedule_name}-topics.json"
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {}


# ── Cron management ────────────────────────────────────────────────────────


def parse_schedule(text: str) -> tuple[int | None, int, int | None]:
    """Parse 'daily 9am', 'weekly monday 9am', etc. → (hour, minute, dow)."""
    text = text.lower()
    dow_map = {
        "monday": 1, "mon": 1, "tuesday": 2, "tue": 2,
        "wednesday": 3, "wed": 3, "thursday": 4, "thu": 4,
        "friday": 5, "fri": 5, "saturday": 6, "sat": 6, "sunday": 0, "sun": 0,
    }
    day_of_week: int | None = None
    for name, num in dow_map.items():
        if name in text:
            day_of_week = num
            break

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None, 0, None

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return hour, minute, day_of_week


def describe_schedule(cron_expr: str) -> str:
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr
    minute, hour = parts[0], parts[1]
    dow = parts[4]
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    h, m = int(hour), int(minute)
    t = f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    if dow == "*":
        return f"Every day at {t}"
    return f"Every {days[int(dow)]} at {t}"


def install_schedule(root: Path, schedule_text: str, target: str = "") -> str:
    """Install a system scheduler entry (cron on Linux/macOS, Task Scheduler on Windows)."""
    if _IS_WINDOWS:
        return _install_windows(root, schedule_text, target)
    return _install_cron(root, schedule_text, target)


# Keep old name as alias
def install_cron(root: Path, schedule_text: str, target: str = "") -> str:
    return install_schedule(root, schedule_text, target)


def remove_schedule() -> str:
    if _IS_WINDOWS:
        return _remove_windows()
    return _remove_cron()


def remove_cron() -> str:
    return remove_schedule()


def status_schedule() -> str:
    if _IS_WINDOWS:
        return _status_windows()
    return _status_cron()


def status_cron() -> str:
    return status_schedule()


# ── Linux / macOS — crontab ────────────────────────────────────────────────────

def _install_cron(root: Path, schedule_text: str, target: str = "") -> str:
    hour, minute, dow = parse_schedule(schedule_text)
    if hour is None:
        return "Could not parse schedule. Use e.g. 'daily 9am' or 'weekly monday 9am'."

    cron_expr = f"{minute} {hour} * * {dow if dow is not None else '*'}"
    python = sys.executable
    target_arg = f" --target {target}" if target else ""
    log = Path.home() / ".flatblog" / "cron.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"cd {root.resolve()} && "
        f"{python} -m flatblog run{target_arg} "
        f">> {log} 2>&1"
    )
    line = f"{cron_expr} {cmd} {CRON_MARKER}"

    ok = _write_crontab(line)
    desc = describe_schedule(cron_expr)
    if ok:
        return (
            f"Cron job installed: {desc} ({cron_expr})\n"
            f"Log: {log}\n\n"
            f"flatblog does NOT need to be running — system cron\n"
            f"fires a one-shot process at the scheduled time.\n\n"
            f"  flatblog daemon status   — show jobs\n"
            f"  flatblog daemon remove   — uninstall"
        )
    return (
        f"Could not write crontab automatically.\n\n"
        f"Add this line manually with `crontab -e`:\n\n  {line}"
    )


def _remove_cron() -> str:
    lines = _read_crontab()
    filtered = [l for l in lines if CRON_MARKER not in l]
    _set_crontab(filtered)
    removed = len(lines) - len(filtered)
    return f"Removed {removed} flatblog cron job(s)."


def _status_cron() -> str:
    lines = [l for l in _read_crontab() if CRON_MARKER in l]
    if not lines:
        return "No flatblog cron jobs installed.\n  flatblog daemon daily 9am"
    out = ["Installed flatblog cron jobs:", ""]
    for line in lines:
        parts = line.split()
        if len(parts) >= 5:
            expr = " ".join(parts[:5])
            out.append(f"  {describe_schedule(expr)}  ({expr})")
    return "\n".join(out)


def _read_crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def _set_crontab(lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    subprocess.run(["crontab", "-"], input=text, text=True, capture_output=True)


def _write_crontab(new_line: str) -> bool:
    try:
        existing = [l for l in _read_crontab() if CRON_MARKER not in l]
        existing.append(new_line)
        _set_crontab(existing)
        return True
    except Exception:
        return False


# ── Windows — Task Scheduler ───────────────────────────────────────────────────

def _install_windows(root: Path, schedule_text: str, target: str = "") -> str:
    hour, minute, dow = parse_schedule(schedule_text)
    if hour is None:
        return "Could not parse schedule. Use e.g. 'daily 9am' or 'weekly monday 9am'."

    python   = sys.executable
    cfg_path = root / "config.yaml"
    target_arg = f" --config \"{cfg_path}\"" + (f" --target {target}" if target else "")
    log      = Path.home() / ".flatblog" / "task.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    # Wrap in a cmd /c so we can redirect output to log
    task_cmd = (
        f'cmd /c "cd /d "{root.resolve()}" && '
        f'"{python}" -m flatblog run{target_arg} >> "{log}" 2>&1"'
    )
    start_time = f"{hour:02d}:{minute:02d}"

    days_map = {1: "MON", 2: "TUE", 3: "WED", 4: "THU", 5: "FRI", 6: "SAT", 0: "SUN"}

    base_args = [
        "schtasks", "/create",
        "/tn", _TASK_NAME,
        "/tr", task_cmd,
        "/st", start_time,
        "/f",                    # overwrite if exists
        "/rl", "HIGHEST",        # run with highest available privilege
    ]

    if dow is not None:
        args = base_args + ["/sc", "weekly", "/d", days_map[dow]]
        desc = describe_schedule(f"{minute} {hour} * * {dow}")
    else:
        args = base_args + ["/sc", "daily"]
        desc = describe_schedule(f"{minute} {hour} * * *")

    try:
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            return (
                f"Task Scheduler job installed: {desc}\n"
                f"Task name: {_TASK_NAME}\n"
                f"Log: {log}\n\n"
                f"flatblog does NOT need to be running — Windows Task Scheduler\n"
                f"fires a one-shot process at the scheduled time.\n\n"
                f"  flatblog daemon status   — show job\n"
                f"  flatblog daemon remove   — uninstall"
            )
        return (
            f"schtasks failed (code {r.returncode}):\n{r.stderr.strip()}\n\n"
            f"Run manually in an elevated PowerShell:\n"
            f"  schtasks /create /tn \"{_TASK_NAME}\" /tr \"{task_cmd}\" "
            f"/sc {'weekly /d ' + days_map.get(dow,'MON') if dow is not None else 'daily'} "
            f"/st {start_time} /f"
        )
    except FileNotFoundError:
        return "schtasks not found. Are you on Windows?"


def _remove_windows() -> str:
    try:
        r = subprocess.run(
            ["schtasks", "/delete", "/tn", _TASK_NAME, "/f"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return f"Task Scheduler job '{_TASK_NAME}' removed."
        return f"Could not remove task: {r.stderr.strip()}"
    except FileNotFoundError:
        return "schtasks not found."


def _status_windows() -> str:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", _TASK_NAME, "/fo", "LIST"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            return f"Windows Task Scheduler — {_TASK_NAME}:\n\n{r.stdout.strip()}"
        return f"No Task Scheduler job found for '{_TASK_NAME}'.\n  flatblog daemon daily 9am"
    except FileNotFoundError:
        return "schtasks not found."
