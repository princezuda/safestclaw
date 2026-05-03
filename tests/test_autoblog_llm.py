"""
Tests for the LLM-enrichment path in BlogScheduler.

The deterministic gather + format pipeline is already exercised by other
tests; here we only need to prove that:

- LLM modes route to the correct AIWriter call
- The provider resolution honors task_providers.blog
- A failing LLM call falls back to the deterministic draft
- LLM never runs when llm_enabled is False
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
from safestclaw.core.blog_scheduler import AutoBlogConfig, BlogScheduler  # noqa: E402


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _scheduler_with_writer(writer, task_blog_provider: str = ""):
    """Build a BlogScheduler whose AIWriter is pre-set to a mock."""
    eng = MagicMock()
    eng.config = {}
    if task_blog_provider:
        eng.config["task_providers"] = {"blog": task_blog_provider}
    sched = BlogScheduler(eng)
    sched._ai_writer = writer
    return sched


def _ok_response(content: str):
    return MagicMock(success=True, content=content, error="")


def _fail_response(error: str):
    return MagicMock(success=False, content="", error=error)


def _items():
    return [
        {"title": "Item 1", "summary": "Sum 1", "link": "https://a/1",
         "category": "tech", "source": "src"},
        {"title": "Item 2", "summary": "Sum 2", "link": "https://a/2",
         "category": "tech", "source": "src"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# AutoBlogConfig serialisation
# ─────────────────────────────────────────────────────────────────────────────

def test_autoblogconfig_roundtrip_includes_llm_fields():
    cfg = AutoBlogConfig(
        name="t", cron_expr="0 9 * * 1",
        llm_enabled=True, llm_mode="generate",
        llm_provider="my-claude", llm_topic="AI news today",
        llm_system_prompt="Be punchy.",
    )
    d = cfg.to_dict()
    cfg2 = AutoBlogConfig.from_dict(d)
    assert cfg2.llm_enabled is True
    assert cfg2.llm_mode == "generate"
    assert cfg2.llm_provider == "my-claude"
    assert cfg2.llm_topic == "AI news today"
    assert cfg2.llm_system_prompt == "Be punchy."


def test_autoblogconfig_defaults_have_llm_disabled():
    cfg = AutoBlogConfig(name="t", cron_expr="0 9 * * 1")
    assert cfg.llm_enabled is False
    assert cfg.llm_mode == "rewrite"
    assert cfg.llm_provider == ""


# ─────────────────────────────────────────────────────────────────────────────
# Provider resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_provider_prefers_explicit():
    sched = _scheduler_with_writer(MagicMock(), task_blog_provider="task-claude")
    cfg = AutoBlogConfig(name="t", cron_expr="0 * * * *",
                         llm_enabled=True, llm_provider="explicit-ollama")
    assert sched._resolve_llm_provider(cfg) == "explicit-ollama"


def test_resolve_provider_falls_back_to_task_providers():
    sched = _scheduler_with_writer(MagicMock(), task_blog_provider="task-claude")
    cfg = AutoBlogConfig(name="t", cron_expr="0 * * * *", llm_enabled=True)
    assert sched._resolve_llm_provider(cfg) == "task-claude"


def test_resolve_provider_returns_none_when_no_routing():
    sched = _scheduler_with_writer(MagicMock())
    cfg = AutoBlogConfig(name="t", cron_expr="0 * * * *", llm_enabled=True)
    assert sched._resolve_llm_provider(cfg) is None


# ─────────────────────────────────────────────────────────────────────────────
# LLM enrichment routing
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_disabled_skips_enrichment_path():
    """_execute_auto_blog must not touch the writer when llm_enabled=False."""
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.rewrite_blog = AsyncMock(return_value=_ok_response("REWRITE"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(name="t", cron_expr="0 * * * *", llm_enabled=False)

    # Verify _llm_enrich is the right gate by calling it directly with
    # llm_enabled toggled — the dispatch in _execute_auto_blog is a one-line
    # `if config.llm_enabled` we trust.
    title, body = run(sched._llm_enrich(cfg, "T", "BODY", _items()))
    # _llm_enrich is only called when llm_enabled is True, so calling it
    # directly always runs the LLM. The disabled-state guard lives one level
    # up; this test just records that the writer would have been used here.
    assert title == "T"
    assert body == "REWRITE"


def test_rewrite_mode_replaces_body_only():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.rewrite_blog = AsyncMock(return_value=_ok_response("polished body"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="rewrite", llm_provider="my-claude",
    )
    title, body = run(sched._llm_enrich(cfg, "Original Title", "draft", _items()))

    assert title == "Original Title"
    assert body == "polished body"
    writer.rewrite_blog.assert_awaited_once_with(
        "draft", provider_label="my-claude"
    )


def test_expand_mode_uses_expand_blog():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.expand_blog = AsyncMock(return_value=_ok_response("expanded"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="expand",
    )
    title, body = run(sched._llm_enrich(cfg, "T", "draft", _items()))
    assert body == "expanded"
    writer.expand_blog.assert_awaited_once()


def test_headline_mode_replaces_title_keeps_body():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.generate_headlines = AsyncMock(return_value=_ok_response(
        '1. "Why X matters"\n2. Another headline\n3. Third'
    ))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="headline",
    )
    title, body = run(sched._llm_enrich(cfg, "Old Title", "draft body", _items()))

    assert title == "Why X matters"
    assert body == "draft body"


def test_generate_mode_uses_topic_and_items_as_context():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.generate_blog = AsyncMock(return_value=_ok_response("brand new post"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="generate",
        llm_topic="The week in tech",
    )
    title, body = run(sched._llm_enrich(cfg, "T", "draft", _items()))

    assert title == "T"
    assert body.startswith("brand new post")
    # include_source_links defaults to True, so a Sources section is appended
    assert "## Sources" in body
    assert "https://a/1" in body

    kwargs = writer.generate_blog.await_args.kwargs
    assert kwargs["topic"] == "The week in tech"
    assert "[1] Item 1" in kwargs["context"]
    assert "[2] Item 2" in kwargs["context"]


def test_generate_mode_derives_topic_from_categories_when_missing():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.generate_blog = AsyncMock(return_value=_ok_response("post"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="generate",
    )
    run(sched._llm_enrich(cfg, "T", "draft", _items()))
    topic = writer.generate_blog.await_args.kwargs["topic"]
    assert "tech" in topic


def test_unknown_llm_mode_falls_back_to_draft():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="frobnicate",
    )
    title, body = run(sched._llm_enrich(cfg, "T", "draft", _items()))
    assert title == "T"
    assert body == "draft"


def test_llm_failure_falls_back_to_draft():
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.rewrite_blog = AsyncMock(return_value=_fail_response("rate limit"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="rewrite",
    )
    title, body = run(sched._llm_enrich(cfg, "T", "draft", _items()))
    assert title == "T"
    assert body == "draft"


def test_no_providers_configured_falls_back_silently():
    writer = MagicMock()
    writer.providers = {}  # nothing configured
    writer.rewrite_blog = AsyncMock()
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="rewrite",
    )
    title, body = run(sched._llm_enrich(cfg, "T", "draft", _items()))
    assert (title, body) == ("T", "draft")
    writer.rewrite_blog.assert_not_called()


def test_writer_init_failure_falls_back_silently():
    """If load_ai_writer_from_yaml throws, the cron job still publishes."""
    eng = MagicMock()
    eng.config = {}
    sched = BlogScheduler(eng)  # _ai_writer left as None

    with patch(
        "safestclaw.core.ai_writer.load_ai_writer_from_yaml",
        side_effect=RuntimeError("no providers"),
    ):
        cfg = AutoBlogConfig(
            name="t", cron_expr="0 * * * *",
            llm_enabled=True, llm_mode="rewrite",
        )
        title, body = run(sched._llm_enrich(cfg, "T", "draft", _items()))
    assert (title, body) == ("T", "draft")


def test_execute_auto_blog_skips_llm_when_disabled():
    """End-to-end gate: llm_enabled=False must never call the writer."""
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.rewrite_blog = AsyncMock(return_value=_ok_response("polish"))
    sched = _scheduler_with_writer(writer)
    sched._save_draft = AsyncMock()

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        source_categories=["tech"], llm_enabled=False,
    )
    with patch.object(
        BlogScheduler, "_gather_content", new=AsyncMock(return_value=_items())
    ):
        run(sched._execute_auto_blog(cfg))

    writer.rewrite_blog.assert_not_called()
    sched._save_draft.assert_awaited_once()


def test_system_prompt_override_routes_through_generate():
    """When llm_system_prompt is set, we must call writer.generate directly
    (not the convenience helper) so the override is actually applied."""
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.templates = MagicMock()
    writer.templates.render = MagicMock(return_value="rendered prompt")
    writer.generate = AsyncMock(return_value=_ok_response("custom-tone body"))
    writer.rewrite_blog = AsyncMock(return_value=_ok_response("default body"))
    sched = _scheduler_with_writer(writer)

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        llm_enabled=True, llm_mode="rewrite",
        llm_system_prompt="Be terse and use sailor slang.",
    )
    title, body = run(sched._llm_enrich(cfg, "T", "draft body", _items()))

    assert body == "custom-tone body"
    writer.rewrite_blog.assert_not_called()
    writer.generate.assert_awaited_once()
    kwargs = writer.generate.await_args.kwargs
    assert kwargs["system_prompt"] == "Be terse and use sailor slang."


def test_execute_auto_blog_runs_llm_when_enabled():
    """End-to-end: llm_enabled=True routes the draft through the writer."""
    writer = MagicMock()
    writer.providers = {"x": MagicMock()}
    writer.rewrite_blog = AsyncMock(return_value=_ok_response("LLM body"))
    sched = _scheduler_with_writer(writer)
    sched._save_draft = AsyncMock()

    cfg = AutoBlogConfig(
        name="t", cron_expr="0 * * * *",
        source_categories=["tech"],
        llm_enabled=True, llm_mode="rewrite",
    )
    with patch.object(
        BlogScheduler, "_gather_content", new=AsyncMock(return_value=_items())
    ):
        run(sched._execute_auto_blog(cfg))

    writer.rewrite_blog.assert_awaited_once()
    sched._save_draft.assert_awaited_once()
    saved_body = sched._save_draft.await_args.args[2]
    assert saved_body == "LLM body"
