"""
SafestClaw → Model Context Protocol bridge.

Exposes every registered SafestClaw action as an MCP tool so that MCP-aware
clients (Claude Desktop, IDE extensions, etc.) can call them directly.

The bridge is built on top of FastMCP, which is an optional dependency:

    pip install fastmcp

If FastMCP is not installed, importing this module still succeeds — but
``build_mcp_server`` will raise ``ImportError`` when called.

Transports supported:
- stdio              — for MCP clients that spawn the server as a subprocess
- sse                — Server-Sent Events over HTTP
- streamable-http    — HTTP streaming transport
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

try:
    from fastmcp import FastMCP
    HAS_FASTMCP = True
except ImportError:  # pragma: no cover - import guard
    FastMCP = None  # type: ignore[assignment]
    HAS_FASTMCP = False


# Actions that don't make sense to expose over MCP because they assume
# stateful session interaction inside SafestClaw's chat loop.
DEFAULT_EXCLUDED_ACTIONS: frozenset[str] = frozenset({
    "help",  # MCP clients have their own discovery
})


def _action_description(name: str, engine: "SafestClaw") -> str:
    """Best-effort human-readable description for an MCP tool."""
    intents = getattr(engine.parser, "intents", {})
    pattern = intents.get(name)
    if pattern is not None and pattern.examples:
        examples = "; ".join(pattern.examples[:3])
        return f"SafestClaw '{name}' action. Examples: {examples}"
    return f"SafestClaw '{name}' action."


def build_mcp_server(
    engine: "SafestClaw",
    server_name: str = "safestclaw",
    exclude: set[str] | None = None,
) -> Any:
    """
    Build a FastMCP server that exposes SafestClaw actions as tools.

    Each action becomes an MCP tool that takes a single ``input`` argument
    (the natural-language command, e.g. ``"calendar today"``) and returns
    the action's text response.

    Args:
        engine: A loaded SafestClaw engine. ``engine.start()`` does not need
            to have been called, but ``engine.load_config()`` and the action
            registrations from ``cli.create_engine`` should have run.
        server_name: Name advertised to MCP clients.
        exclude: Action names to skip when registering tools. Defaults to
            :data:`DEFAULT_EXCLUDED_ACTIONS`.

    Returns:
        A configured ``FastMCP`` instance. Call ``.run(transport=...)`` on it.

    Raises:
        ImportError: If ``fastmcp`` is not installed.
    """
    if not HAS_FASTMCP:
        raise ImportError(
            "fastmcp is not installed. Run: pip install safestclaw[mcp]"
        )

    excluded = set(DEFAULT_EXCLUDED_ACTIONS)
    if exclude:
        excluded.update(exclude)

    mcp = FastMCP(server_name)

    def _make_tool(action_name: str):
        description = _action_description(action_name, engine)

        async def _tool(input: str = "", user_id: str = "mcp") -> str:
            """Dynamic tool that forwards to engine.handle_message."""
            text = input.strip() if input else action_name
            # Prepend the action name if the caller forgot, so plain
            # arguments like ``"~/calendar.ics"`` still route correctly.
            lowered = text.lower()
            if not lowered.startswith(action_name):
                text = f"{action_name} {text}".strip()
            return await engine.handle_message(
                text=text,
                channel="mcp",
                user_id=user_id,
            )

        _tool.__name__ = action_name
        _tool.__doc__ = description
        return _tool

    registered: list[str] = []
    for name in sorted(engine.actions.keys()):
        if name in excluded:
            continue
        try:
            mcp.tool(name=name, description=_action_description(name, engine))(
                _make_tool(name)
            )
            registered.append(name)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not register MCP tool '{name}': {e}")

    # A catch-all tool so clients can issue free-form commands too.
    @mcp.tool(
        name="run_command",
        description=(
            "Run any SafestClaw command (the same syntax as the interactive "
            "CLI, e.g. 'crawl https://example.com', 'summarize <text>', "
            "'calendar upcoming 14'). Use this when no action-specific tool "
            "fits."
        ),
    )
    async def run_command(command: str, user_id: str = "mcp") -> str:
        return await engine.handle_message(
            text=command,
            channel="mcp",
            user_id=user_id or "mcp",
        )

    logger.info(
        "FastMCP server '%s' built with %d action tools (+ run_command)",
        server_name,
        len(registered),
    )
    return mcp


async def serve_mcp(
    engine: "SafestClaw",
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8770,
    server_name: str = "safestclaw",
) -> None:
    """
    Start an MCP server over the requested transport and block until done.

    For ``stdio`` the server reads/writes the parent process's stdio, which
    is what MCP clients like Claude Desktop expect when they spawn the
    server as a subprocess.
    """
    if not HAS_FASTMCP:
        raise ImportError(
            "fastmcp is not installed. Run: pip install safestclaw[mcp]"
        )

    # Make sure config is loaded so actions can read provider settings.
    if not engine.config:
        engine.load_config()
    # Initialize memory so actions that touch engine.memory don't crash.
    if hasattr(engine.memory, "initialize"):
        try:
            await engine.memory.initialize()
        except Exception as e:
            logger.warning(f"Memory init failed before MCP serve: {e}")

    server = build_mcp_server(engine, server_name=server_name)

    transport = (transport or "stdio").lower()
    logger.info(
        "Starting SafestClaw MCP server on transport=%s (host=%s, port=%s)",
        transport, host, port,
    )

    # FastMCP's run is synchronous; run_async is the awaitable form.
    runner = getattr(server, "run_async", None)
    if runner is None:
        # Fall back to the sync API in a thread.
        import asyncio
        if transport == "stdio":
            await asyncio.to_thread(server.run, transport="stdio")
        else:
            await asyncio.to_thread(
                server.run, transport=transport, host=host, port=port
            )
        return

    if transport == "stdio":
        await runner(transport="stdio")
    else:
        await runner(transport=transport, host=host, port=port)
