"""
Tests for the new calendar subcommand routing, CalDAV plumbing, and the
FastMCP plugin / bridge.

The repo's CI environment doesn't ship every optional dependency, so we
mock heavy modules before importing SafestClaw, mirroring test_sweep.py.
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

# ── Mock heavy optional deps ────────────────────────────────────────────────
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

# rapidfuzz needs real ints
import rapidfuzz  # noqa: E402  - real install

from safestclaw.actions.calendar import CalendarAction  # noqa: E402
from safestclaw.core import mcp_server  # noqa: E402
from safestclaw.core.parser import CommandParser  # noqa: E402
from safestclaw.plugins.official.fastmcp_server import FastMCPPlugin  # noqa: E402


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Calendar subcommand parser
# ─────────────────────────────────────────────────────────────────────────────

def test_subcommand_default_today():
    sub, arg = CalendarAction._parse_subcommand("")
    assert sub == "today"
    assert arg == ""


def test_subcommand_explicit_today():
    sub, arg = CalendarAction._parse_subcommand("calendar today")
    assert sub == "today"


def test_subcommand_upcoming_with_days():
    sub, arg = CalendarAction._parse_subcommand("calendar upcoming 14")
    assert sub == "upcoming"
    assert arg == "14"


def test_subcommand_week():
    sub, _ = CalendarAction._parse_subcommand("calendar week")
    assert sub == "week"


def test_subcommand_import_path():
    sub, arg = CalendarAction._parse_subcommand("calendar import ~/cal.ics")
    assert sub == "import"
    assert arg == "~/cal.ics"


def test_subcommand_sync():
    sub, _ = CalendarAction._parse_subcommand("calendar sync")
    assert sub == "sync"


def test_subcommand_calendars_listing():
    sub, _ = CalendarAction._parse_subcommand("calendar calendars")
    assert sub == "calendars"


def test_subcommand_tomorrow_aliased_to_upcoming_one():
    sub, arg = CalendarAction._parse_subcommand("calendar tomorrow")
    assert sub == "upcoming"
    assert arg == "1"


def test_subcommand_strips_filler_words():
    sub, _ = CalendarAction._parse_subcommand("show me my upcoming events")
    assert sub == "upcoming"


# ─────────────────────────────────────────────────────────────────────────────
# Parser still routes calendar intent
# ─────────────────────────────────────────────────────────────────────────────

def test_parser_routes_calendar_today():
    parser = CommandParser()
    result = parser.parse("calendar today")
    assert result.intent == "calendar"
    assert result.params.get("subcommand") == "today"


def test_parser_routes_calendar_upcoming_with_arg():
    parser = CommandParser()
    result = parser.parse("calendar upcoming 14")
    assert result.intent == "calendar"
    assert result.params.get("subcommand") == "upcoming"
    assert result.params.get("argument") == "14"


def test_parser_routes_calendar_sync():
    parser = CommandParser()
    result = parser.parse("calendar sync")
    assert result.intent == "calendar"
    assert result.params.get("subcommand") == "sync"


# ─────────────────────────────────────────────────────────────────────────────
# Calendar execute() — sync path returns helpful message when not configured
# ─────────────────────────────────────────────────────────────────────────────

def _fake_engine(memory_value=None):
    eng = MagicMock()
    eng.memory.get = AsyncMock(return_value=memory_value)
    eng.memory.set = AsyncMock(return_value=None)
    eng.config = {}
    return eng


def test_execute_sync_not_configured_returns_helpful_message():
    action = CalendarAction()
    eng = _fake_engine()

    with patch("safestclaw.actions.calendar.HAS_ICALENDAR", True), \
         patch("safestclaw.actions.calendar.HAS_CALDAV", True), \
         patch("safestclaw.actions.calendar.CalendarParser"):
        result = run(action.execute(
            params={"raw_input": "calendar sync"},
            user_id="u1",
            channel="cli",
            engine=eng,
        ))

    assert "CalDAV not configured" in result


def test_execute_sync_missing_caldav_dep():
    action = CalendarAction()
    eng = _fake_engine()
    eng.config = {
        "actions": {
            "calendar": {
                "caldav": {
                    "url": "https://example.com/dav",
                    "username": "u",
                    "password": "p",
                }
            }
        }
    }

    with patch("safestclaw.actions.calendar.HAS_ICALENDAR", True), \
         patch("safestclaw.actions.calendar.HAS_CALDAV", False), \
         patch("safestclaw.actions.calendar.CalendarParser"):
        result = run(action.execute(
            params={"raw_input": "calendar sync"},
            user_id="u1",
            channel="cli",
            engine=eng,
        ))

    assert "CalDAV support not installed" in result


def test_execute_calendars_lists_when_configured():
    action = CalendarAction()
    eng = _fake_engine()
    eng.config = {
        "actions": {
            "calendar": {
                "caldav": {
                    "url": "https://example.com/dav",
                    "username": "u",
                    "password": "p",
                }
            }
        }
    }

    fake_client = MagicMock()
    fake_client.list_calendars.return_value = ["work", "personal"]

    with patch("safestclaw.actions.calendar.HAS_ICALENDAR", True), \
         patch("safestclaw.actions.calendar.HAS_CALDAV", True), \
         patch("safestclaw.actions.calendar.CalendarParser"), \
         patch.object(CalendarAction, "_build_caldav_client",
                      return_value=fake_client):
        result = run(action.execute(
            params={"raw_input": "calendar calendars"},
            user_id="u1",
            channel="cli",
            engine=eng,
        ))

    assert "work" in result and "personal" in result


# ─────────────────────────────────────────────────────────────────────────────
# MCP module
# ─────────────────────────────────────────────────────────────────────────────

def test_build_mcp_server_raises_without_fastmcp():
    with patch("safestclaw.core.mcp_server.HAS_FASTMCP", False):
        try:
            mcp_server.build_mcp_server(MagicMock())
        except ImportError as e:
            assert "fastmcp" in str(e).lower()
        else:
            raise AssertionError("expected ImportError")


def test_build_mcp_server_registers_tools_when_fastmcp_present():
    fake_mcp = MagicMock()
    fake_mcp.tool = MagicMock(return_value=lambda fn: fn)

    fake_engine = MagicMock()
    fake_engine.actions = {
        "summarize": lambda **_: "ok",
        "crawl": lambda **_: "ok",
        "help": lambda **_: "ok",  # excluded
    }
    fake_engine.parser.intents = {}

    with patch("safestclaw.core.mcp_server.HAS_FASTMCP", True), \
         patch("safestclaw.core.mcp_server.FastMCP",
               return_value=fake_mcp):
        mcp = mcp_server.build_mcp_server(fake_engine, server_name="t")

    assert mcp is fake_mcp
    # mcp.tool() called for each non-excluded action + run_command
    tool_names = [
        call.kwargs.get("name") for call in fake_mcp.tool.call_args_list
    ]
    assert "summarize" in tool_names
    assert "crawl" in tool_names
    assert "help" not in tool_names
    assert "run_command" in tool_names


# ─────────────────────────────────────────────────────────────────────────────
# FastMCPPlugin
# ─────────────────────────────────────────────────────────────────────────────

def test_plugin_status_disabled_by_default():
    plugin = FastMCPPlugin()
    fake_engine = MagicMock()
    fake_engine.config = {}
    fake_engine.actions = {"summarize": lambda **_: "x"}
    plugin.on_load(fake_engine)
    status = plugin._status()
    # Either "disabled in config" or "FastMCP is not installed"
    assert "disabled" in status or "not installed" in status


def test_plugin_help_lists_subcommands():
    plugin = FastMCPPlugin()
    h = plugin._help()
    for cmd in ("mcp status", "mcp start", "mcp stop", "mcp tools"):
        assert cmd in h


def test_plugin_refuses_stdio_inside_chat():
    plugin = FastMCPPlugin()
    fake_engine = MagicMock()
    fake_engine.config = {"plugins": {"fastmcp": {"enabled": True}}}
    fake_engine.actions = {"summarize": lambda **_: "x"}
    plugin.on_load(fake_engine)
    with patch("safestclaw.core.mcp_server.HAS_FASTMCP", True):
        result = run(plugin._start_server(transport="stdio"))
    assert "stdio" in result.lower()
    assert "refusing" in result.lower() or "subprocess" in result.lower()


def test_plugin_execute_dispatches_to_handlers():
    plugin = FastMCPPlugin()
    fake_engine = MagicMock()
    fake_engine.config = {}
    fake_engine.actions = {"summarize": lambda **_: "x"}
    plugin.on_load(fake_engine)

    # status
    out = run(plugin.execute(
        params={"raw_input": "mcp status"},
        user_id="u",
        channel="cli",
        engine=fake_engine,
    ))
    assert "MCP plugin" in out or "not installed" in out

    # tools
    out = run(plugin.execute(
        params={"raw_input": "mcp tools"},
        user_id="u",
        channel="cli",
        engine=fake_engine,
    ))
    assert "summarize" in out

    # help
    out = run(plugin.execute(
        params={"raw_input": "mcp"},
        user_id="u",
        channel="cli",
        engine=fake_engine,
    ))
    assert "mcp status" in out
