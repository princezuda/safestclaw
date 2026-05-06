"""
Connectivity helpers: detect online/offline state, run code with a clean
fall-back when the network is unavailable, and let the user pin
"offline mode" so we stop probing.

Design:

- A single ``ConnectivityChecker`` per process. Probes are cheap (HTTP
  HEAD against a configurable URL with a short timeout) and cached for
  ``cache_seconds`` so we don't beat the network up on every call.
- ``user_offline_pinned`` overrides the probe entirely — when set we
  always report offline without any network IO.
- ``with_network_fallback`` lets call sites express
  *"try the online thing; on network failure or pinned-offline, run
  the offline alternative and tag the response"*.

Action code typically looks like:

    from safestclaw.core.connectivity import get_checker, with_network_fallback

    async def _do_thing():
        checker = get_checker()

        async def online():
            return await fetch_remote_thing()

        async def offline():
            return await use_local_cache_or_ml()

        result, mode = await with_network_fallback(
            checker, online, offline,
            label="research",
        )
        if mode == "offline":
            result = "(offline — local results)\n\n" + result
        return result
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)

# Lightweight, vendor-neutral endpoints used to test reachability.
DEFAULT_PROBE_URLS: tuple[str, ...] = (
    "https://1.1.1.1",                    # Cloudflare DNS HTTP endpoint
    "https://www.google.com/generate_204",  # standard captive-portal probe
)

T = TypeVar("T")


@dataclass
class ConnectivityState:
    online: bool
    last_checked: float
    reason: str = ""        # populated when offline
    pinned_offline: bool = False


class ConnectivityChecker:
    """
    Cached online/offline detector. Safe for concurrent callers — the
    actual probe runs at most once per ``cache_seconds`` window.

    When ``user_offline_pinned`` is True we report offline without any
    network IO. Useful when the user is on a plane / metered link / etc.
    """

    def __init__(
        self,
        probe_urls: tuple[str, ...] = DEFAULT_PROBE_URLS,
        cache_seconds: float = 30.0,
        timeout: float = 2.0,
    ):
        self.probe_urls = probe_urls
        self.cache_seconds = cache_seconds
        self.timeout = timeout
        self._state: ConnectivityState | None = None
        self._lock = asyncio.Lock()
        self._user_offline_pinned = False

    # ── Pin / unpin ────────────────────────────────────────────────────────

    def set_offline_pinned(self, pinned: bool) -> None:
        """Tell the checker to skip probes and always report offline."""
        self._user_offline_pinned = pinned
        if pinned:
            self._state = ConnectivityState(
                online=False,
                last_checked=time.time(),
                reason="user pinned offline mode",
                pinned_offline=True,
            )
        else:
            # Force a fresh probe next call
            self._state = None
        logger.info(
            "Connectivity offline-pin %s",
            "ON" if pinned else "OFF",
        )

    def is_offline_pinned(self) -> bool:
        return self._user_offline_pinned

    # ── Probing ────────────────────────────────────────────────────────────

    def _is_cached_fresh(self) -> bool:
        return (
            self._state is not None
            and (time.time() - self._state.last_checked) < self.cache_seconds
        )

    async def is_online(self, force: bool = False) -> bool:
        """
        Return True iff the network appears reachable.

        Cached for ``cache_seconds``. ``force=True`` skips the cache.
        Pinned-offline always returns False without IO.
        """
        if self._user_offline_pinned:
            return False

        if not force and self._is_cached_fresh():
            return self._state.online  # type: ignore[union-attr]

        async with self._lock:
            # Re-check inside the lock — another caller may have just probed.
            if not force and self._is_cached_fresh():
                return self._state.online  # type: ignore[union-attr]

            online, reason = await self._probe()
            self._state = ConnectivityState(
                online=online,
                last_checked=time.time(),
                reason=reason,
                pinned_offline=False,
            )
            return online

    async def _probe(self) -> tuple[bool, str]:
        """Try each probe URL until one succeeds. Returns (online, reason)."""
        try:
            import httpx
        except ImportError:
            return False, "httpx not installed"

        last_err = ""
        for url in self.probe_urls:
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=False,
                ) as client:
                    r = await client.head(url)
                if r.status_code < 500:
                    return True, ""
                last_err = f"HTTP {r.status_code} from {url}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                continue
        return False, last_err or "all probes failed"

    def state(self) -> ConnectivityState | None:
        return self._state


_checker: ConnectivityChecker | None = None


def get_checker(
    probe_urls: tuple[str, ...] | None = None,
    cache_seconds: float | None = None,
    timeout: float | None = None,
) -> ConnectivityChecker:
    """Return the process-wide ConnectivityChecker, creating it lazily.

    Subsequent calls ignore the constructor args (the first call wins).
    """
    global _checker
    if _checker is None:
        _checker = ConnectivityChecker(
            probe_urls=probe_urls or DEFAULT_PROBE_URLS,
            cache_seconds=(
                cache_seconds if cache_seconds is not None else 30.0
            ),
            timeout=(timeout if timeout is not None else 2.0),
        )
    return _checker


def _reset_checker_for_tests() -> None:
    """Reset the singleton — only used in tests."""
    global _checker
    _checker = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Network-shaped exceptions we'll catch and translate to "offline" mode.
NETWORK_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError, TimeoutError, OSError,
)


async def with_network_fallback(
    checker: ConnectivityChecker,
    online: Callable[[], Awaitable[T]],
    offline: Callable[[], Awaitable[T]],
    label: str = "operation",
    force_check: bool = True,
) -> tuple[T, str]:
    """
    Try ``online()`` first when the checker reports online. On any
    network-shaped failure (or when offline), run ``offline()`` instead.

    Returns ``(result, mode)`` where ``mode`` is ``"online"`` or
    ``"offline"`` so callers can decorate the response.
    """
    is_online = await checker.is_online(force=force_check)

    if is_online:
        try:
            return await online(), "online"
        except NETWORK_EXCEPTIONS as e:
            logger.warning(
                "%s: online attempt failed (%s); falling back to offline",
                label, e,
            )
            # The probe said online but the call failed — invalidate the
            # cached state so future calls re-probe instead of trusting
            # a stale "online" verdict.
            checker._state = None
        except Exception as e:
            # Try to detect httpx-shaped failures by name to avoid an
            # import-time dep on httpx in this module.
            if type(e).__name__.startswith(("Connect", "Read", "Network", "Pool")):
                logger.warning(
                    "%s: %s — falling back to offline", label, e,
                )
                checker._state = None
            else:
                raise

    return await offline(), "offline"


def offline_banner(reason: str = "") -> str:
    """Standard banner to prepend when serving an offline result."""
    if reason:
        return f"_(offline — {reason}; using local data)_\n\n"
    return "_(offline — using local data)_\n\n"


def online_banner_when_recovered() -> str:
    """Optional 'connection restored' note actions can use."""
    return "_(connection restored)_\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# User intent detection
# ─────────────────────────────────────────────────────────────────────────────

OFFLINE_PHRASES = (
    "i'm offline", "im offline", "go offline", "offline mode",
    "i am offline", "no internet", "no wifi", "im on a plane",
    "i'm on a plane", "stay offline", "use offline", "work offline",
)
ONLINE_PHRASES = (
    "i'm online", "im online", "go online", "back online",
    "online mode", "i am online", "use online", "work online",
)


def parse_offline_intent(text: str) -> str | None:
    """
    Detect whether the user is asking us to go offline / online.
    Returns ``"offline"`` / ``"online"`` / ``None``.
    """
    if not text:
        return None
    lowered = text.lower().strip()
    if any(p in lowered for p in OFFLINE_PHRASES):
        return "offline"
    if any(p in lowered for p in ONLINE_PHRASES):
        return "online"
    return None
