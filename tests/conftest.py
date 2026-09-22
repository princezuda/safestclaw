"""Shared pytest configuration."""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Guarantee a usable current event loop for sync tests.

    Many tests drive coroutines via ``asyncio.get_event_loop().run_until_complete``.
    pytest-asyncio (and ``asyncio.run``) leave no current loop behind after an
    async test, so without this, sync tests that run later fail with
    "There is no current event loop".
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield
