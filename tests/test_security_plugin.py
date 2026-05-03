"""
Tests for the SecurityPlugin — deterministic security scanners, no AI.

The scanners themselves are out-of-process binaries; we mock both
``shutil.which`` (to fake whether a tool is installed) and
``asyncio.create_subprocess_exec`` (to fake scanner output) so the tests
stay hermetic.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── src/ on path ────────────────────────────────────────────────────────────
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── Mock heavy optional deps (mirrors test_sweep.py) ────────────────────────
_mock_fp = MagicMock()
_mock_fp.parse = MagicMock(return_value=MagicMock(entries=[]))
sys.modules.setdefault("feedparser", _mock_fp)
sys.modules.setdefault("desktop_notifier", MagicMock())
for _mod in (
    "paramiko", "sgmllib3k", "vaderSentiment", "vaderSentiment.vaderSentiment",
    "aiosqlite", "aiohttp", "aiofiles",
    "apscheduler", "apscheduler.schedulers.asyncio",
    "apscheduler.triggers.cron", "apscheduler.triggers.interval",
    "apscheduler.triggers.date",
    "yaml",
    "typer",
    "rich", "rich.console", "rich.markdown", "rich.live", "rich.panel",
    "rich.text", "rich.prompt", "rich.table", "rich.logging",
    "sumy", "sumy.parsers", "sumy.parsers.plaintext",
    "sumy.nlp", "sumy.nlp.tokenizers", "sumy.nlp.stemmers",
    "sumy.summarizers", "sumy.summarizers.lex_rank", "sumy.summarizers.lsa",
    "sumy.summarizers.luhn", "sumy.summarizers.text_rank",
    "sumy.summarizers.edmundson", "sumy.utils",
    "nltk",
    "icalendar",
    "fitz",
    "docx",
    "PIL", "PIL.Image",
    "fastapi", "uvicorn",
):
    sys.modules.setdefault(_mod, MagicMock())

import rapidfuzz  # noqa: E402  - real install
from safestclaw.plugins.official.security import SCANNERS, SecurityPlugin  # noqa: E402


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _engine_with_paths(*paths: str):
    eng = MagicMock()
    eng.config = {"plugins": {"security": {"allowed_paths": list(paths)}}}
    return eng


def _fake_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# ─────────────────────────────────────────────────────────────────────────────
# on_load / config
# ─────────────────────────────────────────────────────────────────────────────

def test_on_load_uses_default_when_unconfigured():
    plugin = SecurityPlugin()
    eng = MagicMock()
    eng.config = {}
    plugin.on_load(eng)
    assert plugin._allowed_paths
    assert plugin._timeout == 120.0


def test_on_load_reads_config(tmp_path: Path):
    plugin = SecurityPlugin()
    eng = _engine_with_paths(str(tmp_path))
    eng.config["plugins"]["security"]["timeout"] = 5
    eng.config["plugins"]["security"]["max_output"] = 99
    plugin.on_load(eng)
    assert tmp_path.resolve() in plugin._allowed_paths
    assert plugin._timeout == 5.0
    assert plugin._max_output == 99


# ─────────────────────────────────────────────────────────────────────────────
# Path safety
# ─────────────────────────────────────────────────────────────────────────────

def test_path_outside_allowlist_is_rejected(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    other = tmp_path.parent / "elsewhere"
    other.mkdir(exist_ok=True)
    path, err = plugin._resolve_target(str(other))
    assert path is None
    assert "outside" in err


def test_path_inside_allowlist_is_accepted(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    sub = tmp_path / "proj"
    sub.mkdir()
    path, err = plugin._resolve_target(str(sub))
    assert err == ""
    assert path == sub


def test_missing_path_reports_error(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    path, err = plugin._resolve_target(str(tmp_path / "nope"))
    assert path is None
    assert "not found" in err


# ─────────────────────────────────────────────────────────────────────────────
# Subcommand routing
# ─────────────────────────────────────────────────────────────────────────────

def test_help_when_empty():
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths())
    out = run(plugin.execute(
        params={"raw_input": "security"},
        user_id="u", channel="cli", engine=MagicMock(),
    ))
    assert "security tools" in out
    assert "security scan" in out


def test_tools_listing_marks_missing(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", return_value=None):
        out = run(plugin.execute(
            params={"raw_input": "security tools"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    for key in SCANNERS:
        assert key in out
    assert "⬜" in out  # nothing installed


def test_tools_listing_marks_installed(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", side_effect=lambda n: "/usr/bin/" + n
               if n == "bandit" else None):
        out = run(plugin.execute(
            params={"raw_input": "security tools"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    # bandit installed, others not
    assert "✅" in out
    assert "⬜" in out


# ─────────────────────────────────────────────────────────────────────────────
# Scanner execution
# ─────────────────────────────────────────────────────────────────────────────

def test_scanner_missing_executable_returns_install_hint(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", return_value=None):
        out = run(plugin.execute(
            params={"raw_input": f"security bandit {tmp_path}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "not installed" in out
    assert "pip install bandit" in out


def test_scanner_runs_and_formats_clean_exit(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", return_value="/usr/bin/bandit"), \
         patch("asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_proc(b"No issues\n", b"", 0))):
        out = run(plugin.execute(
            params={"raw_input": f"security bandit {tmp_path}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "✅ bandit" in out
    assert "No issues" in out


def test_scanner_runs_and_marks_findings(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", return_value="/usr/bin/bandit"), \
         patch("asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_proc(b"Issue: B101\n", b"", 1))):
        out = run(plugin.execute(
            params={"raw_input": f"security bandit {tmp_path}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "🔎 bandit" in out
    assert "B101" in out


def test_pip_audit_does_not_require_path(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", return_value="/usr/bin/pip-audit"), \
         patch("asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_proc(b"No vulns\n", b"", 0))) as m:
        out = run(plugin.execute(
            params={"raw_input": "security pip-audit"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "pip-audit" in out
    # Confirm we ran pip-audit with no path appended
    args, _ = m.call_args
    assert args == ("pip-audit",)


def test_scan_aggregates_only_installed_scanners(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))

    def which(name):
        return "/usr/bin/" + name if name in ("bandit", "pip-audit") else None

    with patch("shutil.which", side_effect=which), \
         patch("asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_proc(b"clean\n", b"", 0))) as m:
        out = run(plugin.execute(
            params={"raw_input": f"security scan {tmp_path}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))

    assert "Ran 2 scanner(s)" in out
    assert m.await_count == 2


def test_scan_with_no_scanners_installed_lists_them(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    with patch("shutil.which", return_value=None):
        out = run(plugin.execute(
            params={"raw_input": f"security scan {tmp_path}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "No security scanners are installed" in out
    for key in SCANNERS:
        assert key in out


def test_scanner_timeout(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    plugin._timeout = 0.01

    proc = MagicMock()

    async def _hang(*_a, **_kw):
        await asyncio.sleep(1)

    proc.communicate = _hang
    proc.kill = MagicMock()

    with patch("shutil.which", return_value="/usr/bin/bandit"), \
         patch("asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=proc)):
        out = run(plugin.execute(
            params={"raw_input": f"security bandit {tmp_path}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "timed out" in out
    proc.kill.assert_called_once()


def test_path_outside_allowlist_blocks_scan(tmp_path: Path):
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    other = tmp_path.parent / "scan-blocked"
    other.mkdir(exist_ok=True)
    with patch("shutil.which", return_value="/usr/bin/bandit"), \
         patch("asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_proc())) as m:
        out = run(plugin.execute(
            params={"raw_input": f"security bandit {other}"},
            user_id="u", channel="cli", engine=MagicMock(),
        ))
    assert "outside" in out
    m.assert_not_called()
