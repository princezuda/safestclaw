"""
Tests for the AIWriter provider cascade (try other providers when one
hits an auth/quota/network failure) and the ml_fallback helpers used
when every provider gives up.
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
    "yaml",
    "typer",
    "rich", "rich.console", "rich.markdown", "rich.live", "rich.panel",
    "rich.text", "rich.prompt", "rich.table", "rich.logging",
    "icalendar",
    "fitz",
    "docx",
    "PIL", "PIL.Image",
    "fastapi", "uvicorn",
):
    sys.modules.setdefault(_mod, MagicMock())

import rapidfuzz  # noqa: E402

# sumy isn't installable on every CI environment (tied to old docopt),
# so stub the Summarizer so the ml_fallback tests verify the
# orchestration logic without needing the real extractive backend.
_FakeSummarizer = MagicMock()
_FakeSummarizer.summarize = MagicMock(
    side_effect=lambda text, sentences=5, *a, **kw: " ".join(
        text.split(".")[:sentences]
    )[:600]
)
_FakeSummarizer.get_keywords = MagicMock(
    side_effect=lambda text, top_n=5, *a, **kw: [
        w.lower() for w in (text.split() or [""])[:top_n]
    ]
)
sys.modules.setdefault("safestclaw.core.summarizer", MagicMock(
    Summarizer=MagicMock(return_value=_FakeSummarizer),
))

from safestclaw.core import ml_fallback  # noqa: E402
from safestclaw.core.ai_writer import (  # noqa: E402
    AIProvider,
    AIProviderConfig,
    AIResponse,
    AIWriter,
    classify_exception_kind,
    classify_http_error,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# classify_http_error / classify_exception_kind
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,body,expected", [
    (401, "", "auth"),
    (403, "permission denied", "auth"),
    (403, "insufficient quota", "quota"),
    (403, "billing required", "quota"),
    (429, "", "rate_limit"),
    (402, "payment required", "quota"),
    (500, "", "server"),
    (502, "", "server"),
    (200, "", "other"),
])
def test_classify_http_error(status, body, expected):
    assert classify_http_error(status, body) == expected


def test_classify_exception_kind_network():
    class ConnectError(Exception):
        pass
    assert classify_exception_kind(ConnectError("dns")) == "network"
    assert classify_exception_kind(TimeoutError("slow")) == "network"
    assert classify_exception_kind(ConnectionError("nope")) == "network"
    assert classify_exception_kind(ValueError("bug")) == "other"


# ─────────────────────────────────────────────────────────────────────────────
# AIWriter cascade
# ─────────────────────────────────────────────────────────────────────────────

def _writer_with_two_providers():
    cloud = AIProviderConfig(
        provider=AIProvider.ANTHROPIC, api_key="sk-ant-x",
        model="claude-x", label="cloud",
    )
    local = AIProviderConfig(
        provider=AIProvider.OLLAMA, api_key="", model="llama3",
        endpoint="http://localhost:11434/api/chat", label="local",
    )
    return AIWriter(providers=[cloud, local])


def test_cascade_uses_first_when_it_works():
    w = _writer_with_two_providers()
    ok = AIResponse(content="hi", provider="anthropic", model="claude-x")
    fallback = AsyncMock(return_value=ok)
    with patch.object(AIWriter, "_generate_once", new=fallback):
        result = run(w.generate("hello"))
    assert result.content == "hi"
    assert fallback.await_count == 1


def test_cascade_falls_through_on_auth_error():
    w = _writer_with_two_providers()
    bad = AIResponse(
        content="", provider="anthropic", model="claude-x",
        error="HTTP 401: bad key", error_kind="auth",
    )
    good = AIResponse(content="from local", provider="ollama", model="llama3")
    fallback = AsyncMock(side_effect=[bad, good])
    with patch.object(AIWriter, "_generate_once", new=fallback):
        result = run(w.generate("hello"))
    assert result.content == "from local"
    assert result.provider == "ollama"
    assert fallback.await_count == 2


def test_cascade_returns_last_error_when_all_fail():
    w = _writer_with_two_providers()
    bad1 = AIResponse(
        content="", provider="anthropic", model="claude-x",
        error="HTTP 401", error_kind="auth",
    )
    bad2 = AIResponse(
        content="", provider="ollama", model="llama3",
        error="connection refused", error_kind="network",
    )
    fallback = AsyncMock(side_effect=[bad1, bad2])
    with patch.object(AIWriter, "_generate_once", new=fallback):
        result = run(w.generate("hello"))
    assert result.error == "connection refused"
    assert result.error_kind == "network"
    assert fallback.await_count == 2


def test_cascade_does_not_retry_for_non_retryable_kind():
    w = _writer_with_two_providers()
    bad = AIResponse(
        content="", provider="anthropic", model="claude-x",
        error="bad input", error_kind="other",
    )
    fallback = AsyncMock(return_value=bad)
    with patch.object(AIWriter, "_generate_once", new=fallback):
        result = run(w.generate("hello"))
    assert result.error_kind == "other"
    assert fallback.await_count == 1


def test_cascade_order_puts_local_after_cloud():
    w = _writer_with_two_providers()
    order = w._cascade_order()
    assert order.index("cloud") < order.index("local")


def test_no_provider_returns_auth_error():
    w = AIWriter(providers=[])
    result = run(w.generate("hello"))
    assert result.error_kind == "auth"
    assert "No AI provider" in result.error


# ─────────────────────────────────────────────────────────────────────────────
# ml_fallback
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE = (
    "Quantum computers use qubits to perform calculations. "
    "Unlike classical bits, qubits can exist in superpositions of 0 and 1. "
    "This enables certain algorithms to run exponentially faster. "
    "Shor's algorithm, for example, can factor large numbers efficiently. "
    "Grover's algorithm provides a quadratic speedup for unstructured search."
)


def test_fallback_rewrite_returns_non_empty_text():
    out = ml_fallback.fallback_rewrite(SAMPLE)
    assert out.strip()
    # Result should be a subset of the input sentences
    assert "qubits" in out.lower() or "quantum" in out.lower()


def test_fallback_rewrite_handles_empty():
    assert ml_fallback.fallback_rewrite("").strip() == ""


def test_fallback_expand_includes_tldr_and_keywords():
    out = ml_fallback.fallback_expand(SAMPLE)
    assert "TL;DR" in out
    assert "Key points" in out
    assert SAMPLE in out


def test_fallback_headlines_returns_numbered_list():
    out = ml_fallback.fallback_headlines(SAMPLE)
    assert "1." in out
    # At least 2 candidates
    assert "\n2." in out


def test_fallback_headlines_empty_input():
    assert ml_fallback.fallback_headlines("") == ""


def test_fallback_excerpt_respects_max_chars():
    out = ml_fallback.fallback_excerpt(SAMPLE, max_chars=80)
    assert len(out) <= 80


def test_fallback_seo_has_all_fields():
    out = ml_fallback.fallback_seo(SAMPLE)
    for marker in ("Meta title:", "Meta description:", "Tags", "URL slug:"):
        assert marker in out


def test_fallback_generate_blog_uses_topic_and_context():
    out = ml_fallback.fallback_generate_blog(
        topic="The Week in Quantum",
        context=SAMPLE,
    )
    assert "# The Week in Quantum" in out
    assert "## Overview" in out
    assert "Sources covered" in out
    # Local-fallback notice appears
    assert "without an LLM" in out


def test_offline_ml_banner_includes_reason():
    out = ml_fallback.offline_ml_banner("HTTP 401")
    assert "HTTP 401" in out
    assert out.endswith("\n\n")
