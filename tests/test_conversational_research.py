"""
Tests for conversational input handling: parser-level filler stripping,
generic engine-level friendly intros for every intent, plus the
ResearchAction's source-aware overrides.
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

import rapidfuzz  # noqa: E402

from safestclaw.actions.research import ResearchAction  # noqa: E402
from safestclaw.core.parser import (  # noqa: E402
    CommandParser,
    friendly_intro,
    is_conversational,
    normalize_text,
    strip_conversational,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# strip_conversational
# ─────────────────────────────────────────────────────────────────────────────

def test_strips_hey_buddy_and_id_like_to():
    assert strip_conversational(
        "hey man, id like to research arxiv quantum computing"
    ) == "research arxiv quantum computing"


def test_strips_chained_handoff_after_comma():
    """The headline case from the bug report."""
    assert strip_conversational(
        "hey man, id like to research, lets try arxiv quantum computing"
    ) == "research arxiv quantum computing"


def test_strips_can_you_please():
    assert strip_conversational(
        "can you please research arxiv transformers"
    ) == "research arxiv transformers"


def test_strips_lets_try_alone():
    assert strip_conversational(
        "lets try wolfram integrate x squared"
    ) == "wolfram integrate x squared"


def test_strips_maybe_and_how_about():
    assert strip_conversational("maybe arxiv transformers") == "arxiv transformers"
    assert strip_conversational(
        "how about scholar machine learning"
    ) == "scholar machine learning"


def test_strip_is_idempotent():
    once = strip_conversational(
        "hey claw, could you please research arxiv quantum"
    )
    assert strip_conversational(once) == once


def test_empty_input_unchanged():
    assert strip_conversational("") == ""


def test_falls_back_to_original_when_strip_empties_it():
    """If the input was nothing but fillers, don't return ''."""
    assert strip_conversational("hey man") == "hey man"


def test_normalize_text_runs_strip_first():
    out = normalize_text("hey claw, can you please summerize https://example.com")
    # "summerize" is also auto-corrected by COMMON_CORRECTIONS
    assert out.startswith("summarize")
    assert "https://example.com" in out
    assert "claw" not in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# CommandParser end-to-end
# ─────────────────────────────────────────────────────────────────────────────

def test_parser_routes_conversational_research_to_research_intent():
    parser = CommandParser()
    cases = [
        "hey man, id like to research, lets try arxiv quantum computing",
        "can you research arxiv quantum computing please",
        "id love to look up papers on transformers",
        "please summarize https://example.com",
    ]
    expected = ["research", "research", "research", "summarize"]
    for text, want in zip(cases, expected, strict=True):
        result = parser.parse(text)
        assert result.intent == want, (
            f"{text!r} routed to {result.intent}, expected {want}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ResearchAction source detection
# ─────────────────────────────────────────────────────────────────────────────

def test_detect_source_arxiv():
    ra = ResearchAction()
    assert ra._detect_source("research arxiv quantum") == "arxiv"
    assert ra._detect_source("arxiv.org transformers") == "arxiv"


def test_detect_source_prefers_longest_alias():
    """'semantic scholar' should beat a stray 'scholar'."""
    ra = ResearchAction()
    assert ra._detect_source("semantic scholar machine learning") == "scholar"


def test_detect_source_wolfram_alpha():
    ra = ResearchAction()
    assert ra._detect_source("research wolfram alpha integrate") == "wolfram"
    assert ra._detect_source("wolfram integrate x^2") == "wolfram"


def test_detect_source_none_when_absent():
    ra = ResearchAction()
    assert ra._detect_source("research quantum computing") is None


def test_detect_source_word_boundary():
    """'scholarly' must not match the 'scholar' alias."""
    ra = ResearchAction()
    assert ra._detect_source("scholarly papers on quantum") is None


# ─────────────────────────────────────────────────────────────────────────────
# Query extraction
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_query_strict_form():
    ra = ResearchAction()
    assert ra._extract_query(
        "research arxiv quantum computing", "arxiv"
    ) == "quantum computing"


def test_extract_query_strips_leading_verb_and_source():
    ra = ResearchAction()
    assert ra._extract_query(
        "arxiv quantum computing", "arxiv"
    ) == "quantum computing"


def test_extract_query_strips_connectives():
    ra = ResearchAction()
    assert ra._extract_query(
        "research about quantum on arxiv", "arxiv"
    ) == "quantum"


def test_extract_query_handles_semantic_scholar():
    ra = ResearchAction()
    assert ra._extract_query(
        "research semantic scholar deep learning", "scholar"
    ) == "deep learning"


# ─────────────────────────────────────────────────────────────────────────────
# Conversational-acknowledgment heuristic
# ─────────────────────────────────────────────────────────────────────────────

def test_is_conversational_detects_politeness():
    ra = ResearchAction()
    assert ra._is_conversational(
        "hey man, id like to research arxiv quantum"
    )
    assert ra._is_conversational("can you please research transformers")


def test_is_conversational_false_for_strict_form():
    ra = ResearchAction()
    assert not ra._is_conversational("research arxiv quantum")
    assert not ra._is_conversational("research scholar transformers")


def test_with_ack_prepends_intro_when_conversational():
    ra = ResearchAction()
    out = ra._with_ack("arxiv", "quantum computing", "results body", True)
    assert out.startswith("On it — searching arXiv for **quantum computing**")
    assert "results body" in out


def test_with_ack_passthrough_when_not_conversational():
    ra = ResearchAction()
    out = ra._with_ack("arxiv", "quantum computing", "results body", False)
    assert out == "results body"


def test_with_ack_skips_when_query_empty():
    ra = ResearchAction()
    out = ra._with_ack("arxiv", "", "results body", True)
    assert out == "results body"


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end via execute()
# ─────────────────────────────────────────────────────────────────────────────

def _engine_for_research():
    eng = MagicMock()
    eng.config = {}
    eng.memory = MagicMock()
    eng.memory.get = AsyncMock(return_value=None)
    eng.memory.set = AsyncMock(return_value=None)
    return eng


def test_execute_conversational_arxiv_routes_and_acks():
    """The user types a sentence; we should call _search_arxiv with the
    extracted topic and prepend a friendly intro to the result."""
    ra = ResearchAction()
    arxiv_mock = AsyncMock(return_value="ARXIV_RESULTS")

    with patch.object(ra, "_search_arxiv", new=arxiv_mock), \
         patch.object(ra, "_initialize"):
        out = run(ra.execute(
            params={"raw_input":
                "hey man, id like to research arxiv quantum computing"},
            user_id="u",
            channel="cli",
            engine=_engine_for_research(),
        ))
        assert "ARXIV_RESULTS" in out
        assert out.startswith("On it — searching arXiv for **quantum computing**")
        arxiv_mock.assert_awaited_once_with("quantum computing", "u")


def test_execute_strict_form_skips_intro():
    """Power user form: terse output, no intro."""
    ra = ResearchAction()
    with patch.object(ra, "_search_arxiv",
                      new=AsyncMock(return_value="ARXIV_RESULTS")), \
         patch.object(ra, "_initialize"):
        out = run(ra.execute(
            params={"raw_input": "research arxiv quantum computing"},
            user_id="u",
            channel="cli",
            engine=_engine_for_research(),
        ))
        assert out == "ARXIV_RESULTS"


def test_execute_chained_handoff_routes_through_arxiv():
    """The exact phrasing from the bug report."""
    ra = ResearchAction()
    cleaned = strip_conversational(
        "hey man, id like to research, lets try arxiv quantum computing"
    )
    assert cleaned == "research arxiv quantum computing"

    arxiv_mock = AsyncMock(return_value="ARXIV_RESULTS")
    with patch.object(ra, "_search_arxiv", new=arxiv_mock), \
         patch.object(ra, "_initialize"):
        # The action's own strip_conversational call cleans the raw input;
        # the source-aware routing must still catch arxiv + the topic when
        # passed either the cleaned form or the original sentence.
        out = run(ra.execute(
            params={"raw_input":
                "hey man, id like to research, lets try arxiv quantum computing"},
            user_id="u",
            channel="cli",
            engine=_engine_for_research(),
        ))
        arxiv_mock.assert_awaited_once_with("quantum computing", "u")
        assert "ARXIV_RESULTS" in out


# ─────────────────────────────────────────────────────────────────────────────
# Engine-level generic acknowledgment (applies to every intent)
# ─────────────────────────────────────────────────────────────────────────────

def test_friendly_intro_table_covers_common_intents():
    for intent in (
        "blog", "autoblog", "calendar", "news", "weather",
        "summarize", "research", "security", "shell",
        "reminder", "publish",
    ):
        assert friendly_intro(intent), f"no intro for {intent}"


def test_friendly_intro_falls_back_for_unknown_intent():
    assert friendly_intro("frobnicate") == "On it — running frobnicate…"


def test_friendly_intro_empty_for_help():
    """Help is already chatty; don't double-decorate it."""
    assert friendly_intro("help") == ""


def test_is_conversational_module_helper():
    assert is_conversational("hey claw, can you publish my blog")
    assert is_conversational("let's go autoblog")
    assert is_conversational("hey lets publish this blog")
    assert not is_conversational("publish blog")
    assert not is_conversational("autoblog list")


def test_engine_acknowledge_publish_blog_command():
    """Smoke test: 'hey lets publish this blog' triggers a friendly
    engine-level intro for the publish/blog intent."""
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    decorated = eng._maybe_acknowledge(
        "hey lets publish this blog",
        "publish",
        "✓ posted to my-wordpress",
    )
    assert decorated.startswith("On it — publishing that for you…")
    assert "✓ posted to my-wordpress" in decorated


def test_engine_acknowledge_autoblog_command():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    decorated = eng._maybe_acknowledge(
        "let's go autoblog",
        "autoblog",
        "weekly-tech: 0 9 * * 1 (tech, ai)",
    )
    assert decorated.startswith("Got it — wiring up the auto-blog…")


def test_engine_acknowledge_skips_strict_form():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    decorated = eng._maybe_acknowledge(
        "publish blog", "publish", "✓ posted",
    )
    assert decorated == "✓ posted"


def test_engine_acknowledge_skips_when_response_already_acked():
    """The research action wraps its own source-aware ack ('On it —
    searching arXiv for X'). The engine must not double-wrap."""
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    response = "On it — searching arXiv for **quantum**…\n\nresults"
    decorated = eng._maybe_acknowledge(
        "hey claw, search arxiv for quantum",
        "research",
        response,
    )
    assert decorated == response  # no double-wrap


def test_engine_acknowledge_skips_help():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    decorated = eng._maybe_acknowledge(
        "hey can you show me help", "help", "[help text]",
    )
    assert decorated == "[help text]"


def test_engine_acknowledge_skips_empty_response():
    from safestclaw.core.engine import SafestClaw
    eng = SafestClaw.__new__(SafestClaw)
    assert eng._maybe_acknowledge("hey can you", "blog", "") == ""


def test_execute_conversational_default_research_acks():
    """No source mentioned → default multi-source path, also gets an ack."""
    ra = ResearchAction()
    sr_mock = AsyncMock(return_value="ALL_RESULTS")
    with patch.object(ra, "_start_research", new=sr_mock), \
         patch.object(ra, "_initialize"):
        out = run(ra.execute(
            params={"raw_input": "hey, can you look up transformer models"},
            user_id="u",
            channel="cli",
            engine=_engine_for_research(),
        ))
        assert "ALL_RESULTS" in out
        assert out.startswith("On it — searching arXiv, Semantic Scholar")
        args, _ = sr_mock.await_args
        assert args[0] == "transformer models"
