"""
Opt-in integration tests for the SecurityPlugin.

Each test is gated on the relevant scanner being on PATH so the suite
stays green on machines that don't have these tools installed. Run on
CI by ``pip install bandit`` (etc.) first.

These complement test_security_plugin.py, which exercises plumbing with
mocks; the integration tests verify that the plugin actually invokes the
real scanner, forwards the right argv, and surfaces real findings.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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

import rapidfuzz  # noqa: E402
from safestclaw.plugins.official.security import SecurityPlugin  # noqa: E402


# A textbook bandit finding: subprocess call with shell=True (B602).
VULN_PY = textwrap.dedent(
    """
    import subprocess


    def run(cmd):
        subprocess.call(cmd, shell=True)
    """
).strip()


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _engine_with_paths(*paths: str):
    eng = MagicMock()
    eng.config = {"plugins": {"security": {"allowed_paths": list(paths)}}}
    return eng


@pytest.mark.skipif(
    shutil.which("bandit") is None,
    reason="bandit not installed; run `pip install bandit` to enable",
)
def test_real_bandit_detects_shell_true(tmp_path: Path):
    """End-to-end: real bandit binary against a B602 fixture."""
    fixture = tmp_path / "vuln.py"
    fixture.write_text(VULN_PY)

    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))

    output = run(plugin.execute(
        params={"raw_input": f"security bandit {tmp_path}"},
        user_id="u",
        channel="cli",
        engine=MagicMock(),
    ))

    # The plugin should have run bandit (header line) …
    assert "bandit" in output
    # … forwarded the path correctly so bandit actually scanned the fixture …
    # … and surfaced the canonical B602 finding in some form.
    assert (
        "B602" in output
        or "shell=True" in output
        or "subprocess_popen_with_shell_equals_true" in output
    ), f"bandit output didn't contain expected B602 finding:\n{output}"


@pytest.mark.skipif(
    shutil.which("bandit") is None,
    reason="bandit not installed",
)
def test_real_bandit_clean_file_has_no_findings(tmp_path: Path):
    """Sanity check: bandit on a clean file yields no B-code in output."""
    fixture = tmp_path / "clean.py"
    fixture.write_text("x = 1\nprint(x)\n")

    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))

    output = run(plugin.execute(
        params={"raw_input": f"security bandit {tmp_path}"},
        user_id="u",
        channel="cli",
        engine=MagicMock(),
    ))

    # No bandit issue identifiers should appear.
    for marker in ("B602", "B101", "Issue: ["):
        assert marker not in output, (
            f"bandit reported a finding on a clean file:\n{output}"
        )


@pytest.mark.skipif(
    shutil.which("pip-audit") is None,
    reason="pip-audit not installed; run `pip install pip-audit` to enable",
)
def test_real_pip_audit_runs(tmp_path: Path):
    """End-to-end: pip-audit at least executes and returns a parseable banner."""
    plugin = SecurityPlugin()
    plugin.on_load(_engine_with_paths(str(tmp_path)))
    plugin._timeout = 60

    output = run(plugin.execute(
        params={"raw_input": "security pip-audit"},
        user_id="u",
        channel="cli",
        engine=MagicMock(),
    ))

    assert "pip-audit" in output
    # pip-audit either reports vulnerabilities or "No known vulnerabilities";
    # either is a successful run for our purposes.
    lower = output.lower()
    assert (
        "no known vulnerabilities" in lower
        or "name" in lower  # tabular header
        or "vulnerab" in lower
    ), f"pip-audit output didn't look like a real run:\n{output}"
