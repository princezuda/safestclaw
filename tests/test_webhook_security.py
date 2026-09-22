"""Tests for webhook server hardening (DoS / exposure surface).

Loaded directly to avoid the full safestclaw import chain.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

SRC = Path(__file__).parent.parent / "src"


def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def webhook_mod():
    return _load_module(
        "safestclaw.triggers.webhook",
        SRC / "safestclaw" / "triggers" / "webhook.py",
    )


def test_default_bind_is_loopback(webhook_mod):
    server = webhook_mod.WebhookServer()
    assert server.host == "127.0.0.1"


def test_oversized_body_rejected(webhook_mod):
    server = webhook_mod.WebhookServer(max_body_bytes=1024)
    server.register("test", action="noop")
    client = TestClient(server.app)
    resp = client.post("/webhook/test", content=b"x" * 2048)
    assert resp.status_code == 413


def test_queue_full_sheds_load(webhook_mod):
    server = webhook_mod.WebhookServer(max_queue_size=2)
    server.register("test", action="noop")
    client = TestClient(server.app)
    # Nothing drains the queue, so it fills at maxsize and then 503s rather
    # than growing unbounded or blocking the request.
    codes = [client.post("/webhook/test", json={"n": i}).status_code
             for i in range(5)]
    assert codes[:2] == [202, 202]
    assert 503 in codes[2:]


def test_listing_hides_secret_status(webhook_mod):
    server = webhook_mod.WebhookServer()
    server.register("open", action="noop")
    server.register("locked", action="noop", secret="s3cr3t")
    client = TestClient(server.app)
    data = client.get("/webhooks").json()
    for wh in data["webhooks"]:
        assert "has_secret" not in wh


def test_secret_required_when_configured(webhook_mod):
    server = webhook_mod.WebhookServer()
    server.register("locked", action="noop", secret="s3cr3t")
    client = TestClient(server.app)
    # No signature header -> rejected.
    resp = client.post("/webhook/locked", json={"x": 1})
    assert resp.status_code == 401


def test_unknown_webhook_404(webhook_mod):
    server = webhook_mod.WebhookServer()
    client = TestClient(server.app)
    assert client.post("/webhook/missing", json={}).status_code == 404
