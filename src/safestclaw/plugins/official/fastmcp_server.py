"""
SafestClaw FastMCP Plugin — exposes actions as Model Context Protocol tools.

Once enabled, every registered SafestClaw action becomes an MCP tool callable
from MCP-aware clients (Claude Desktop, IDE extensions, etc.).

Enable in config.yaml:

    plugins:
      fastmcp:
        enabled: true            # opt-in
        autostart: false         # spawn the server when SafestClaw boots
        transport: "stdio"       # stdio | sse | streamable-http
        host: "127.0.0.1"
        port: 8770
        server_name: "safestclaw"

Or run the server standalone:

    safestclaw mcp                       # stdio (for Claude Desktop, etc.)
    safestclaw mcp --transport sse       # SSE on http://127.0.0.1:8770
    safestclaw mcp --transport streamable-http --port 8770

Chat commands (when the plugin is loaded):

    mcp status         — show whether the server is running and on which transport
    mcp start [stdio|sse|streamable-http]
    mcp stop
    mcp tools          — list the action tools the server exposes
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


class FastMCPPlugin(BasePlugin):
    """Bridge SafestClaw actions into the Model Context Protocol."""

    info = PluginInfo(
        name="mcp",
        version="1.0.0",
        description="Expose SafestClaw actions as Model Context Protocol tools",
        author="SafestClaw",
        keywords=["mcp", "fastmcp", "model context protocol"],
        patterns=[
            r"^mcp$",
            r"^mcp\s+(status|start|stop|tools|help)\b.*",
        ],
        examples=[
            "mcp status",
            "mcp start stdio",
            "mcp start sse",
            "mcp stop",
            "mcp tools",
        ],
    )

    def __init__(self) -> None:
        self._engine: Any = None
        self._config: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self._transport: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_load(self, engine: Any) -> None:
        self._engine = engine
        self._config = (engine.config.get("plugins") or {}).get("fastmcp") or {}

        if not self._config.get("enabled"):
            logger.info(
                "FastMCP plugin loaded but not enabled "
                "(set plugins.fastmcp.enabled: true)"
            )
            return

        if self._config.get("autostart"):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                logger.warning(
                    "FastMCP autostart requested but no event loop available"
                )
                return
            loop.create_task(self._start_server())

    def on_unload(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _start_server(self, transport: str | None = None) -> str:
        from safestclaw.core.mcp_server import HAS_FASTMCP, serve_mcp

        if not HAS_FASTMCP:
            return (
                "FastMCP is not installed. Run: pip install fastmcp "
                "(or, from a checkout: pip install -e \".[mcp]\")"
            )

        if self._task and not self._task.done():
            return f"MCP server already running ({self._transport})."

        chosen = (
            transport
            or self._config.get("transport")
            or "stdio"
        ).lower()
        host = self._config.get("host", "127.0.0.1")
        port = int(self._config.get("port", 8770))
        server_name = self._config.get("server_name", "safestclaw")

        if chosen == "stdio":
            return (
                "Refusing to start stdio MCP server inside the SafestClaw "
                "chat process — stdio is meant for an MCP client to spawn "
                "the server as a subprocess. Run `safestclaw mcp` from your "
                "terminal instead, or pick `sse` / `streamable-http`."
            )

        async def _runner() -> None:
            try:
                await serve_mcp(
                    self._engine,
                    transport=chosen,
                    host=host,
                    port=port,
                    server_name=server_name,
                )
            except asyncio.CancelledError:
                logger.info("MCP server cancelled")
            except Exception as e:  # pragma: no cover - runtime
                logger.error(f"MCP server crashed: {e}")

        self._transport = chosen
        self._task = asyncio.create_task(_runner())
        return (
            f"MCP server started ({chosen}) on http://{host}:{port}\n"
            f"Exposing {len(self._tool_names())} action tools."
        )

    async def _stop_server(self) -> str:
        if not self._task or self._task.done():
            self._transport = None
            return "MCP server is not running."
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        self._transport = None
        return "MCP server stopped."

    def _tool_names(self) -> list[str]:
        from safestclaw.core.mcp_server import DEFAULT_EXCLUDED_ACTIONS
        if self._engine is None:
            return []
        return sorted(
            name for name in self._engine.actions
            if name not in DEFAULT_EXCLUDED_ACTIONS
        )

    def _status(self) -> str:
        from safestclaw.core.mcp_server import HAS_FASTMCP

        if not HAS_FASTMCP:
            return (
                "FastMCP is not installed. Run: pip install fastmcp "
                "(or, from a checkout: pip install -e \".[mcp]\")\n"
                "Then enable in config.yaml under plugins.fastmcp."
            )
        running = bool(self._task and not self._task.done())
        lines = [
            f"MCP plugin: {'enabled' if self._config.get('enabled') else 'disabled in config'}",
            f"Server:     {'running' if running else 'stopped'}"
            + (f" ({self._transport})" if running else ""),
            f"Transport:  {self._config.get('transport', 'stdio')}",
            f"Host/port:  {self._config.get('host', '127.0.0.1')}:"
            f"{self._config.get('port', 8770)}",
            f"Tools:      {len(self._tool_names())} actions exposed",
            "",
            "Run `safestclaw mcp` from a terminal to launch the server "
            "over stdio (the format Claude Desktop and similar MCP clients "
            "expect).",
        ]
        return "\n".join(lines)

    def _tools_listing(self) -> str:
        names = self._tool_names()
        if not names:
            return "No action tools are registered yet."
        return "MCP tools exposed:\n" + "\n".join(f"  • {n}" for n in names) + \
            "\n  • run_command  (catch-all)"

    @staticmethod
    def _help() -> str:
        return (
            "MCP plugin commands:\n"
            "  mcp status                  — show plugin and server state\n"
            "  mcp start [transport]       — sse | streamable-http\n"
            "  mcp stop                    — stop a running in-process server\n"
            "  mcp tools                   — list exposed action tools\n\n"
            "For stdio (used by Claude Desktop, IDE extensions, etc.) run:\n"
            "  safestclaw mcp\n"
        )

    # ------------------------------------------------------------------
    # BasePlugin
    # ------------------------------------------------------------------

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        raw = (params.get("raw_input") or "").strip().lower()
        if raw.startswith("mcp"):
            raw = raw[len("mcp"):].strip()

        if not raw or raw == "help":
            return self._help()
        if raw == "status":
            return self._status()
        if raw == "tools":
            return self._tools_listing()
        if raw == "stop":
            return await self._stop_server()
        if raw.startswith("start"):
            transport = raw[len("start"):].strip() or None
            return await self._start_server(transport=transport)

        return self._help()
