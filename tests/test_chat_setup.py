"""
Tests for the channel-agnostic ChatSetup walkthrough.

The flow has to work over CLI, web UI, and Telegram — anything that
dispatches through engine.handle_message — so it's exercised here at
the ChatSetup level (no rich.prompt, no real LLM installs).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── src/ on path ────────────────────────────────────────────────────────────
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Pop any mocked yaml from earlier test files — chat_setup writes real
# config files via the rich-wizard helpers and we want to verify that.
for _name in list(sys.modules):
    if _name == "yaml" or _name.startswith("yaml."):
        sys.modules.pop(_name, None)
import yaml as _real_yaml  # noqa: E402

# ── Mock heavy optional deps (mirrors test_sweep.py) ────────────────────────
_mock_fp = MagicMock()
_mock_fp.parse = MagicMock(return_value=MagicMock(entries=[]))
sys.modules.setdefault("feedparser", _mock_fp)
sys.modules.setdefault("desktop_notifier", MagicMock())
for _mod in (
    "paramiko", "sgmllib3k", "vaderSentiment", "vaderSentiment.vaderSentiment",
    "aiosqlite", "aiofiles",
    "apscheduler", "apscheduler.schedulers.asyncio",
    "apscheduler.triggers.cron", "apscheduler.triggers.interval",
    "apscheduler.triggers.date",
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

# Patch yaml inside setup_wizard so its _mark_completed call uses real yaml.
import safestclaw.core.setup_wizard as _wizard_mod  # noqa: E402
_wizard_mod.yaml = _real_yaml

from safestclaw.core.chat_setup import ChatSetup  # noqa: E402


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# needs_setup
# ─────────────────────────────────────────────────────────────────────────────

def test_needs_setup_when_no_config(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    assert cs.needs_setup() is True


def test_needs_setup_when_flag_missing(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text("safestclaw:\n  language: en\n")
    cs = ChatSetup(p)
    assert cs.needs_setup() is True


def test_needs_setup_false_when_completed(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text("safestclaw:\n  setup_completed: true\n")
    cs = ChatSetup(p)
    assert cs.needs_setup() is False


# ─────────────────────────────────────────────────────────────────────────────
# Welcome → mode prompt
# ─────────────────────────────────────────────────────────────────────────────

def test_first_message_returns_welcome_then_prompts_mode(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    out = run(cs.handle("hi", "u"))
    assert "Welcome to SafestClaw" in out
    # Subsequent message should re-prompt with the same options if
    # the user types something unrelated:
    out2 = run(cs.handle("hello", "u"))
    assert "1" in out2 or "didn't catch" in out2


# ─────────────────────────────────────────────────────────────────────────────
# Mode 1 (local-only) → marks setup complete
# ─────────────────────────────────────────────────────────────────────────────

def test_mode_local_only_marks_complete(tmp_path: Path):
    p = tmp_path / "config.yaml"
    cs = ChatSetup(p)
    run(cs.handle("hi", "u"))               # welcome → mode
    out = run(cs.handle("1", "u"))           # mode → local-only
    assert "Local-only mode" in out
    assert cs.needs_setup() is False
    raw = _real_yaml.safe_load(p.read_text())
    assert raw.get("safestclaw", {}).get("setup_completed") is True


# ─────────────────────────────────────────────────────────────────────────────
# Mode 4 (skip) — also marks complete so we stop asking
# ─────────────────────────────────────────────────────────────────────────────

def test_mode_skip_marks_complete(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    run(cs.handle("hi", "u"))
    out = run(cs.handle("4", "u"))
    assert "edit" in out.lower() or "config" in out.lower()
    assert cs.needs_setup() is False


def test_skip_keyword_at_welcome_dismisses(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    out = run(cs.handle("skip", "u"))
    assert "skipped setup" in out.lower()
    assert cs.needs_setup() is False


# ─────────────────────────────────────────────────────────────────────────────
# Mode 2 (cloud) → pick provider → key
# ─────────────────────────────────────────────────────────────────────────────

def test_cloud_flow_full(tmp_path: Path):
    p = tmp_path / "config.yaml"
    cs = ChatSetup(p)

    # welcome → mode prompt
    run(cs.handle("hi", "u"))
    # pick cloud
    out = run(cs.handle("2", "u"))
    assert "Pick a cloud provider" in out

    # pick the first provider (anthropic)
    out = run(cs.handle("1", "u"))
    assert "API key" in out

    # paste a key — patch setup_with_key so we don't write a real provider
    with patch(
        "safestclaw.core.llm_installer.setup_with_key",
        return_value="Saved Anthropic provider.",
    ):
        out = run(cs.handle("sk-ant-FAKE-KEY", "u"))
    assert "Setup complete" in out
    assert cs.needs_setup() is False


def test_cloud_flow_skip_at_key_step(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    run(cs.handle("hi", "u"))
    run(cs.handle("2", "u"))
    run(cs.handle("1", "u"))
    out = run(cs.handle("skip", "u"))
    assert "skipped" in out.lower()
    assert cs.needs_setup() is False


def test_cloud_pick_invalid_index_reprompts(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    run(cs.handle("hi", "u"))
    run(cs.handle("2", "u"))
    out = run(cs.handle("99", "u"))
    assert "Pick a number" in out
    # Still in cloud_pick state — config not marked complete yet
    assert cs.needs_setup() is True


# ─────────────────────────────────────────────────────────────────────────────
# Mode 3 (hybrid) → local + cloud
# ─────────────────────────────────────────────────────────────────────────────

def test_hybrid_flow_local_then_cloud(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    run(cs.handle("hi", "u"))
    out = run(cs.handle("3", "u"))
    # Hybrid jumps straight to local model selection (step 1)
    assert "Pick a local Ollama model" in out
    assert "step 1/2" in out

    with patch(
        "safestclaw.core.llm_installer.setup_local",
        new=AsyncMock(return_value="Installed Ollama and llama3.1."),
    ):
        out = run(cs.handle("2", "u"))
    # After local install the wizard finishes (we run cloud step only when
    # the user re-engages — keep the chat flow lean). Confirm setup is done.
    assert "Setup complete" in out
    assert cs.needs_setup() is False


def test_hybrid_local_skip_continues(tmp_path: Path):
    cs = ChatSetup(tmp_path / "config.yaml")
    run(cs.handle("hi", "u"))
    run(cs.handle("3", "u"))
    out = run(cs.handle("skip", "u"))
    assert "skipped local" in out.lower()
    assert cs.needs_setup() is False


# ─────────────────────────────────────────────────────────────────────────────
# Engine integration
# ─────────────────────────────────────────────────────────────────────────────

def test_engine_routes_to_chat_setup_when_incomplete(tmp_path: Path):
    """A real engine instance should pre-route through ChatSetup when
    setup_completed isn't set."""
    from safestclaw.core.engine import SafestClaw

    eng = SafestClaw.__new__(SafestClaw)
    eng.parser = MagicMock()
    eng.memory = MagicMock()
    eng.chat_setup = ChatSetup(tmp_path / "config.yaml")

    out = run(eng.handle_message(
        text="hi", channel="cli", user_id="u",
    ))
    assert "Welcome to SafestClaw" in out


def test_engine_skips_chat_setup_once_completed(tmp_path: Path):
    """After setup is complete the engine should fall through to normal
    routing instead of replaying the wizard."""
    from safestclaw.core.engine import SafestClaw

    p = tmp_path / "config.yaml"
    p.write_text("safestclaw:\n  setup_completed: true\n")

    eng = SafestClaw.__new__(SafestClaw)
    eng.parser = MagicMock()
    parsed = MagicMock()
    parsed.intent = None
    parsed.params = {}
    eng.parser.parse = MagicMock(return_value=parsed)
    eng.parser.is_chain = MagicMock(return_value=False)
    eng.memory = MagicMock()
    eng.memory.store_message = AsyncMock()
    eng.memory.get = AsyncMock(return_value=None)
    eng.memory.set = AsyncMock()
    eng.actions = {}
    eng.nlu = None
    eng.chat_setup = ChatSetup(p)

    out = run(eng.handle_message(
        text="weather", channel="cli", user_id="u",
    ))
    # Hit the "I didn't understand" / nlu fallback path, not the wizard
    assert "Welcome to SafestClaw" not in out
