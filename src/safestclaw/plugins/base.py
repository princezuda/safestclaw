"""
SafestClaw Plugin System - Base classes and utilities.

Create plugins by:
1. Inherit from BasePlugin
2. Define name, version, description
3. Implement execute() method
4. Place in plugins/official/ or plugins/community/
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Metadata about a plugin."""
    name: str
    version: str
    description: str
    author: str = "Unknown"
    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


class BasePlugin(ABC):
    """
    Base class for SafestClaw plugins.

    To create a plugin:
    1. Create a new .py file in plugins/official/ or plugins/community/
    2. Define a class that inherits from BasePlugin
    3. Set the 'info' class attribute with PluginInfo
    4. Implement the execute() method

    Example:
        from safestclaw.plugins.base import BasePlugin, PluginInfo

        class HelloPlugin(BasePlugin):
            info = PluginInfo(
                name="hello",
                version="1.0.0",
                description="Says hello",
                author="Your Name",
                keywords=["hello", "hi", "greet"],
                patterns=[r"^hello$", r"^hi$"],
                examples=["hello", "hi there"],
            )

            async def execute(self, params, user_id, channel, engine):
                name = params.get("name", "World")
                return f"Hello, {name}!"
    """

    info: PluginInfo

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """
        Execute the plugin action.

        Args:
            params: Parsed parameters from user input
            user_id: ID of the user who invoked the command
            channel: Channel the command came from (cli, telegram, etc.)
            engine: SafestClaw engine instance (access to memory, config, etc.)

        Returns:
            Response string to show the user
        """
        pass

    def on_load(self, engine: Any) -> None:
        """Called when the plugin is loaded. Override for initialization."""
        pass

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""
        pass

    @classmethod
    def get_intent_pattern(cls) -> dict | None:
        """
        Convert plugin info to an IntentPattern dict for the parser.
        Returns None if no keywords/patterns defined.
        """
        if not hasattr(cls, 'info'):
            return None

        info = cls.info
        if not info.keywords and not info.patterns:
            return None

        return {
            "intent": info.name,
            "keywords": info.keywords,
            "patterns": info.patterns,
            "examples": info.examples,
            "slots": [],
        }
