"""
Tests for the connectivity helper, the engine-level offline-pin
shortcut, and the research action's offline fallbacks.

Network IO is fully mocked — no real HTTP probes happen.
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

from safestclaw.core import connectivity  # noqa: E402
from safestclaw.core.connectivity import (  # noqa: E402
    ConnectivityChecker,
    ConnectivityState,
    parse_offline_intent,
    with_network_fallback,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def reset_singleton():
    connectivity._reset_checker_for_tests()
    yield
    connectivity._reset_checker_for_tests()


# ─────────────────────────────────────────────────────────────────────────────
# parse_offline_intent
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "i'm offline", "im offline", "go offline", "offline mode",
    "no internet", "i'm on a plane",
])
def test_parse_offline_intent_offline(text):
    assert parse_offline_intent(text) == "offline"


@pytest.mark.parametrize("text", [
    "i'm online", "go online", "back online", "use online",
])
def test_parse_offline_intent_online(text):
    assert parse_offline_intent(text) == "online"


@pytest.mark.parametrize("text", ["", "summarize this", "publish blog"])
def test_parse_offline_intent_none(text):
    assert parse_offline_intent(text) is None


# ─────────────────────────────────────────────────────────────────────────────
# Pinned-offline path skips probes entirely
# ─────────────────────────────────────────────────────────────────────────────

def test_pinned_offline_returns_false_without_probing():
    c = ConnectivityChecker(timeout=0.01)
    c.set_offline_pinned(True)
    # Patch _probe to detect any sneaky probing
    c._probe = AsyncMock(side_effect=AssertionError("should not probe"))
    assert run(c.is_online()) is False


def test_unpin_clears_cache_and_reprobes():
    c = ConnectivityChecker()
    c.set_offline_pinned(True)
    assert c._state and c._state.pinned_offline is True

    # When unpinning, cache is wiped so the next is_online forces a probe
    c.set_offline_pinned(False)
    assert c._state is None


# ─────────────────────────────────────────────────────────────────────────────
# Probe caching
# ─────────────────────────────────────────────────────────────────────────────

def test_probe_runs_once_within_cache_window():
    c = ConnectivityChecker(cache_seconds=60)
    probe = AsyncMock(return_value=(True, ""))
    c._probe = probe

    run(c.is_online())
    run(c.is_online())
    run(c.is_online())
    assert probe.await_count == 1


def test_force_skips_cache():
    c = ConnectivityChecker(cache_seconds=60)
    probe = AsyncMock(return_value=(True, ""))
    c._probe = probe

    run(c.is_online())
    run(c.is_online(force=True))
    assert probe.await_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# with_network_fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_uses_online_when_reachable():
    c = ConnectivityChecker()
    c._probe = AsyncMock(return_value=(True, ""))

    online_fn = AsyncMock(return_value="online-result")
    offline_fn = AsyncMock(return_value="offline-result")

    result, mode = run(with_network_fallback(c, online_fn, offline_fn))
    assert result == "online-result"
    assert mode == "online"
    offline_fn.assert_not_called()


def test_fallback_uses_offline_when_pinned():
    c = ConnectivityChecker()
    c.set_offline_pinned(True)

    online_fn = AsyncMock(return_value="online-result")
    offline_fn = AsyncMock(return_value="offline-result")

    result, mode = run(with_network_fallback(c, online_fn, offline_fn))
    assert result == "offline-result"
    assert mode == "offline"
    online_fn.assert_not_called()


def test_fallback_recovers_when_online_call_throws_network_error():
    c = ConnectivityChecker()
    c._probe = AsyncMock(return_value=(True, ""))

    online_fn = AsyncMock(side_effect=ConnectionError("DNS fail"))
    offline_fn = AsyncMock(return_value="offline-result")

    result, mode = run(with_network_fallback(c, online_fn, offline_fn))
    assert mode == "offline"
    assert result == "offline-result"
    # Cache invalidated so next call re-probes
    assert c._state is None


def test_fallback_propagates_non_network_exception():
    c = ConnectivityChecker()
    c._probe = AsyncMock(return_value=(True, ""))

    online_fn = AsyncMock(side_effect=ValueError("logic bug"))
    offline_fn = AsyncMock(return_value="offline-result")

    with pytest.raises(ValueError):
        run(with_network_fallback(c, online_fn, offline_fn))


# ─────────────────────────────────────────────────────────────────────────────
# Engine: "i'm offline" / "i'm online" toggle
# ─────────────────────────────────────────────────────────────────────────────

def test_engine_handles_offline_intent_and_pins():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    eng.parser = MagicMock()
    eng.memory = MagicMock()
    # Mock chat_setup so it never claims setup is needed (tested elsewhere).
    eng.chat_setup = MagicMock()
    eng.chat_setup.needs_setup = MagicMock(return_value=False)

    out = run(eng.handle_message(
        text="i'm offline",
        channel="cli",
        user_id="u",
    ))
    assert "offline mode on" in out.lower()
    assert connectivity.get_checker().is_offline_pinned() is True


def test_engine_handles_online_intent_when_reachable():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    eng.parser = MagicMock()
    eng.memory = MagicMock()
    # Mock chat_setup so it never claims setup is needed (tested elsewhere).
    eng.chat_setup = MagicMock()
    eng.chat_setup.needs_setup = MagicMock(return_value=False)

    # Pre-pin so we can verify unpin
    connectivity.get_checker().set_offline_pinned(True)

    with patch.object(
        ConnectivityChecker, "is_online",
        new=AsyncMock(return_value=True),
    ):
        out = run(eng.handle_message(
            text="i'm online", channel="cli", user_id="u",
        ))
    assert "back online" in out.lower()
    assert connectivity.get_checker().is_offline_pinned() is False


def test_engine_handles_online_intent_when_still_unreachable():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    eng.parser = MagicMock()
    eng.memory = MagicMock()
    # Mock chat_setup so it never claims setup is needed (tested elsewhere).
    eng.chat_setup = MagicMock()
    eng.chat_setup.needs_setup = MagicMock(return_value=False)
    connectivity.get_checker().set_offline_pinned(True)

    with patch.object(
        ConnectivityChecker, "is_online",
        new=AsyncMock(return_value=False),
    ):
        out = run(eng.handle_message(
            text="go online", channel="cli", user_id="u",
        ))
    assert "still can't reach" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Research action: offline fallback paths
# ─────────────────────────────────────────────────────────────────────────────

from safestclaw.actions.research import ResearchAction  # noqa: E402


def test_research_arxiv_offline_returns_helpful_message():
    ra = ResearchAction()
    ra._initialize = MagicMock()
    connectivity.get_checker().set_offline_pinned(True)

    out = run(ra._search_arxiv("quantum", "u"))
    assert "Can't reach **arXiv**" in out
    assert "i'm online" in out.lower()


def test_research_arxiv_falls_back_on_connection_error():
    ra = ResearchAction()
    connectivity.get_checker()._probe = AsyncMock(return_value=(True, ""))

    with patch(
        "safestclaw.actions.research.search_arxiv",
        new=AsyncMock(side_effect=ConnectionError("DNS")),
    ):
        out = run(ra._search_arxiv("quantum", "u"))
    assert "Can't reach **arXiv**" in out


def test_research_scholar_offline():
    ra = ResearchAction()
    connectivity.get_checker().set_offline_pinned(True)
    out = run(ra._search_scholar("quantum", "u"))
    assert "Semantic Scholar" in out
    assert "offline" in out.lower() or "can't reach" in out.lower()


def test_research_wolfram_offline():
    ra = ResearchAction()
    connectivity.get_checker().set_offline_pinned(True)
    eng = MagicMock()
    eng.config = {"apis": {"wolfram_alpha": ""}}
    out = run(ra._search_wolfram("integrate x^2", "u", eng))
    assert "Wolfram Alpha" in out


def test_research_start_offline_short_circuits():
    ra = ResearchAction()
    connectivity.get_checker().set_offline_pinned(True)
    eng = MagicMock()
    eng.config = {"apis": {}}

    # search_all should never be invoked when offline
    with patch(
        "safestclaw.actions.research.search_all",
        new=AsyncMock(side_effect=AssertionError("should not be called")),
    ):
        out = run(ra._start_research("quantum", "u", eng))
    assert "arXiv, Semantic Scholar, and Wolfram Alpha" in out


def test_local_results_match_previous_session():
    """Offline fallback surfaces previous session sources whose title
    or summary mentions the new query."""
    from safestclaw.actions.research import ResearchSession, ResearchSource
    ra = ResearchAction()
    sess = ResearchSession(topic="prior")
    sess.sources.append(ResearchSource(
        title="Quantum advantage in NISQ devices",
        summary="An overview of quantum supremacy claims.",
        source_type="arxiv",
        url="https://arxiv.org/abs/0000.0000",
    ))
    ra._sessions["alice"] = sess

    out = ra._local_results_for("quantum")
    assert "Quantum advantage" in out


def test_local_results_empty_when_no_match():
    ra = ResearchAction()
    assert ra._local_results_for("nothing-matches-this") == ""
