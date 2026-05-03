"""
Tests for the localhost WebChannel.

We exercise the FastAPI app directly through the test client rather than
booting uvicorn — that keeps the suite fast and avoids socket usage.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Evict mock pollution from earlier test files (test_sweep.py installs
# MagicMock("fastapi") via sys.modules.setdefault). The web channel needs
# the real package, so make sure imports below resolve to the genuine
# fastapi/uvicorn/starlette installs.
for _name in list(sys.modules):
    if _name == "fastapi" or _name.startswith("fastapi."):
        sys.modules.pop(_name, None)
    if _name == "uvicorn" or _name.startswith("uvicorn."):
        sys.modules.pop(_name, None)
    if _name == "starlette" or _name.startswith("starlette."):
        sys.modules.pop(_name, None)

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
):
    sys.modules.setdefault(_mod, MagicMock())

# fastapi/uvicorn/httpx are real installs in the test env. If fastapi is
# not present the entire test module is skipped.
fastapi = pytest.importorskip("fastapi")
testclient_mod = pytest.importorskip("fastapi.testclient")
TestClient = testclient_mod.TestClient

import rapidfuzz  # noqa: E402
from safestclaw.channels.web import WebChannel  # noqa: E402


def _make_engine(handle_response: str = "ok"):
    eng = MagicMock()
    eng.config = {"safestclaw": {"name": "SafestClaw"}}
    eng.actions = {
        "summarize": lambda **_: "x",
        "calendar": lambda **_: "x",
        "help": lambda **_: "x",
    }
    eng.channels = {}

    pat = MagicMock()
    pat.examples = ["calendar today"]
    pat.keywords = ["calendar", "schedule"]
    eng.parser = MagicMock()
    eng.parser.intents = {"calendar": pat}

    eng.handle_message = AsyncMock(return_value=handle_response)
    eng.get_help = MagicMock(return_value="help text")
    eng.memory = MagicMock()
    eng.memory.get_history = AsyncMock(return_value=[
        {"text": "hello", "channel": "web"},
    ])
    return eng


# ─────────────────────────────────────────────────────────────────────────────
# Construction guards
# ─────────────────────────────────────────────────────────────────────────────

def test_refuses_non_loopback_bind():
    eng = _make_engine()
    with pytest.raises(ValueError):
        WebChannel(eng, host="0.0.0.0")


def test_accepts_loopback_aliases():
    eng = _make_engine()
    for host in ("127.0.0.1", "localhost", "::1"):
        ch = WebChannel(eng, host=host)
        assert ch.host == host


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def test_index_serves_html():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>SafestClaw</title>" in r.text


def test_health_endpoint():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["name"] == "SafestClaw"
    assert j["actions"] == 3


def test_actions_endpoint_lists_all_actions():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.get("/api/actions")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()["actions"]]
    assert names == ["calendar", "help", "summarize"]
    cal = next(a for a in r.json()["actions"] if a["name"] == "calendar")
    assert cal["examples"] == ["calendar today"]


def test_help_endpoint_returns_engine_help():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.get("/api/help")
    assert r.status_code == 200
    assert r.json()["help"] == "help text"


def test_message_dispatches_to_engine():
    eng = _make_engine(handle_response="weather: 22°C")
    client = TestClient(WebChannel(eng).app)
    r = client.post("/api/message", json={"text": "weather"})
    assert r.status_code == 200
    assert r.json()["response"] == "weather: 22°C"
    eng.handle_message.assert_awaited_once()
    kwargs = eng.handle_message.await_args.kwargs
    assert kwargs["text"] == "weather"
    assert kwargs["channel"] == "web"
    assert kwargs["user_id"] == "web_user"


def test_message_uses_supplied_user_id():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.post("/api/message",
                    json={"text": "hi", "user_id": "alice"})
    assert r.status_code == 200
    assert eng.handle_message.await_args.kwargs["user_id"] == "alice"


def test_message_rejects_empty_body():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.post("/api/message", json={"text": "  "})
    assert r.status_code == 400
    assert r.json()["detail"] == "Missing 'text'"


def test_message_engine_failure_returns_500():
    eng = _make_engine()
    eng.handle_message = AsyncMock(side_effect=RuntimeError("boom"))
    client = TestClient(WebChannel(eng).app)
    r = client.post("/api/message", json={"text": "hi"})
    assert r.status_code == 500
    assert "boom" in r.json()["detail"]


def test_history_endpoint_passes_through():
    eng = _make_engine()
    client = TestClient(WebChannel(eng).app)
    r = client.get("/api/history?user_id=alice&limit=5")
    assert r.status_code == 200
    assert r.json()["messages"] == [{"text": "hello", "channel": "web"}]
    eng.memory.get_history.assert_awaited_once_with("alice", 5)


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

def test_auth_token_blocks_missing_header():
    eng = _make_engine()
    client = TestClient(WebChannel(eng, auth_token="secret").app)
    r = client.get("/api/health")
    assert r.status_code == 401


def test_auth_token_accepts_bearer():
    eng = _make_engine()
    client = TestClient(WebChannel(eng, auth_token="secret").app)
    r = client.get("/api/health",
                   headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200


def test_auth_token_accepts_x_header():
    eng = _make_engine()
    client = TestClient(WebChannel(eng, auth_token="secret").app)
    r = client.get("/api/health",
                   headers={"X-SafestClaw-Token": "secret"})
    assert r.status_code == 200


def test_auth_token_rejects_wrong_token():
    eng = _make_engine()
    client = TestClient(WebChannel(eng, auth_token="secret").app)
    r = client.get("/api/health",
                   headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# from_config
# ─────────────────────────────────────────────────────────────────────────────

def test_from_config_uses_defaults_when_missing():
    eng = _make_engine()
    ch = WebChannel.from_config(eng, None)
    assert ch.host == "127.0.0.1"
    assert ch.port == 8771
    assert ch.auth_token is None


def test_from_config_reads_settings():
    eng = _make_engine()
    ch = WebChannel.from_config(eng, {
        "host": "127.0.0.1",
        "port": 9000,
        "auth_token": "abc",
        "user_id": "alice",
    })
    assert ch.port == 9000
    assert ch.auth_token == "abc"
    assert ch.user_id == "alice"
