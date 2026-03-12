"""
SafeClaw Core Engine - The main event loop and orchestrator.

Coordinates channels, actions, triggers, and the command parser.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from safeclaw.core.memory import Memory
from safeclaw.core.parser import CommandParser
from safeclaw.core.scheduler import Scheduler

logger = logging.getLogger(__name__)


class SafeClaw:
    """
    Main SafeClaw engine that orchestrates all components.

    Features:
    - Multi-channel message handling (Telegram, Discord, CLI, etc.)
    - Action execution (files, shell, browser, email, etc.)
    - Scheduled triggers (cron, webhooks, file watchers)
    - Persistent memory (SQLite-based)
    - No GenAI required - uses rule-based parsing
    - Fuzzy learning: deterministic writing style profiling
    - Per-task LLM routing (blog, research, coding each get their own provider)
    - Cron-based auto-blogging (no LLM)
    - Non-deterministic system prompts (context-aware, learned from user)
    """

    def __init__(
        self,
        config_path: Path | None = None,
        data_dir: Path | None = None,
    ):
        self.config_path = config_path or Path("config/config.yaml")
        self.data_dir = data_dir or Path.home() / ".safeclaw"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.config: dict[str, Any] = {}
        self.channels: dict[str, Any] = {}
        self.actions: dict[str, Callable] = {}
        self.running = False

        # Core components
        self.parser = CommandParser()
        self.memory = Memory(self.data_dir / "memory.db")
        self.scheduler = Scheduler()

        # Blog scheduler (initialized after config load)
        self.blog_scheduler: Any = None

        # Event queue for async message processing
        self._message_queue: asyncio.Queue = asyncio.Queue()

    def load_config(self) -> None:
        """Load configuration from YAML file."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.config = yaml.safe_load(f) or {}
            logger.info(f"Loaded config from {self.config_path}")
        else:
            logger.warning(f"Config not found at {self.config_path}, using defaults")
            self.config = self._default_config()

        # Load multilingual command support
        self._load_languages()

    def _load_languages(self) -> None:
        """Load multilingual command support from config.

        Reads either ``safeclaw.languages`` (list) or ``safeclaw.language``
        (single code) and loads the corresponding language packs into the
        parser so commands are understood in those languages.
        """
        sc = self.config.get("safeclaw", {})

        # Prefer explicit list: languages: ["en", "es", "fr"]
        languages = sc.get("languages")

        if languages and isinstance(languages, list):
            self.parser.load_languages(languages)
        else:
            # Fall back to single language field
            lang = sc.get("language", "en")
            if lang and lang != "en":
                self.parser.load_language(lang)

    def _default_config(self) -> dict[str, Any]:
        """Return default configuration."""
        return {
            "safeclaw": {
                "name": "SafeClaw",
                "language": "en",
                "timezone": "UTC",
            },
            "channels": {
                "cli": {"enabled": True},
                "webhook": {"enabled": True, "port": 8765},
            },
            "actions": {
                "shell": {"enabled": True, "sandboxed": True},
                "files": {"enabled": True, "allowed_paths": ["~"]},
                "browser": {"enabled": False},
            },
            "memory": {
                "max_history": 1000,
                "retention_days": 365,
            },
        }

    def register_channel(self, name: str, channel: Any) -> None:
        """Register a communication channel."""
        self.channels[name] = channel
        logger.info(f"Registered channel: {name}")

    def register_action(self, name: str, handler: Callable) -> None:
        """Register an action handler."""
        self.actions[name] = handler
        logger.info(f"Registered action: {name}")

    async def handle_message(
        self,
        text: str,
        channel: str,
        user_id: str,
        metadata: dict | None = None,
    ) -> str:
        """
        Process an incoming message and return a response.

        This is the main entry point for all channels.
        Supports command chaining with pipes (|) and sequences (;, "and then").
        """
        metadata = metadata or {}

        # Check for command chains
        if self.parser.is_chain(text):
            return await self._handle_chain(text, channel, user_id, metadata)

        # Parse the command
        parsed = self.parser.parse(text, user_id)
        logger.debug(f"Parsed command: {parsed}")

        # Store in memory
        await self.memory.store_message(
            user_id=user_id,
            channel=channel,
            text=text,
            parsed=parsed,
            metadata=metadata,
        )

        # Execute the action
        if parsed.intent and parsed.intent in self.actions:
            try:
                # Include raw input text in params for actions that need it
                params_with_raw = dict(parsed.params)
                params_with_raw["raw_input"] = text
                result = await self._execute_action(
                    action=parsed.intent,
                    params=params_with_raw,
                    user_id=user_id,
                    channel=channel,
                )

                # Auto-learning: if a previous command failed and this one
                # succeeded, learn the correction so next time the failed
                # input maps to the right intent automatically
                if user_id:
                    last_failed = await self.memory.get(f"_last_failed:{user_id}")
                    if last_failed and last_failed != text:
                        await self.parser.learn_correction(
                            user_id=user_id,
                            phrase=last_failed,
                            correct_intent=parsed.intent,
                            params=parsed.params,
                        )
                        logger.info(
                            f"Auto-learned: '{last_failed}' -> {parsed.intent}"
                        )
                        # Clear the failed command
                        await self.memory.set(
                            f"_last_failed:{user_id}", "", ttl_seconds=1
                        )

                return result
            except Exception as e:
                logger.error(f"Action failed: {e}")
                return f"Sorry, that action failed: {e}"

        # No matching intent — auto-learn opportunity
        if parsed.intent:
            return f"I understand you want to '{parsed.intent}', but I don't have that action configured."

        # Track failed command for potential auto-learning
        # If the user immediately follows up with a successful command,
        # we can learn the mapping
        if user_id:
            await self.memory.set(
                f"_last_failed:{user_id}",
                text,
                ttl_seconds=120,  # Remember for 2 minutes
            )

        return "I didn't understand that command. Try 'help' to see what I can do."

    async def _handle_chain(
        self,
        text: str,
        channel: str,
        user_id: str,
        metadata: dict,
    ) -> str:
        """
        Execute a chain of commands.

        For pipes (|, ->): passes output from one command to the next
        For sequences (;, "and then"): runs commands independently
        """
        chain = self.parser.parse_chain(text, user_id)
        logger.info(f"Executing command chain: {len(chain.commands)} commands ({chain.chain_type})")

        results: list[str] = []
        previous_output: str | None = None

        for i, cmd in enumerate(chain.commands):
            # Store each command in memory
            await self.memory.store_message(
                user_id=user_id,
                channel=channel,
                text=cmd.raw_text,
                parsed=cmd,
                metadata={**metadata, "chain_index": i, "chain_type": chain.chain_type},
            )

            if not cmd.intent:
                results.append(f"[{i+1}] Could not understand: {cmd.raw_text}")
                continue

            if cmd.intent not in self.actions:
                results.append(f"[{i+1}] Unknown action: {cmd.intent}")
                continue

            try:
                # For piped commands, inject previous output
                params = dict(cmd.params)
                if chain.chain_type == "pipe" and previous_output and cmd.use_previous_output:
                    # Add previous output as input for this command
                    params["_previous_output"] = previous_output
                    # If no target specified, use previous output as target
                    if params.get("_use_previous") or not params.get("target"):
                        params["target"] = previous_output

                result = await self._execute_action(
                    action=cmd.intent,
                    params=params,
                    user_id=user_id,
                    channel=channel,
                )
                previous_output = result
                results.append(result)

            except Exception as e:
                logger.error(f"Chain action {i+1} failed: {e}")
                results.append(f"[{i+1}] Failed: {e}")
                # For pipes, stop on error
                if chain.chain_type == "pipe":
                    break

        # Format output based on chain type
        if chain.chain_type == "pipe":
            # For pipes, return only the final result
            return results[-1] if results else "No output"
        else:
            # For sequences, return all results
            if len(results) == 1:
                return results[0]
            return "\n\n---\n\n".join(results)

    async def _execute_action(
        self,
        action: str,
        params: dict[str, Any],
        user_id: str,
        channel: str,
    ) -> str:
        """Execute a registered action."""
        handler = self.actions[action]

        # Check if handler is async
        if asyncio.iscoroutinefunction(handler):
            return await handler(params=params, user_id=user_id, channel=channel, engine=self)
        else:
            return handler(params=params, user_id=user_id, channel=channel, engine=self)

    async def start(self) -> None:
        """Start the SafeClaw engine."""
        logger.info("Starting SafeClaw...")
        self.running = True

        # Initialize components
        self.load_config()
        await self.memory.initialize()
        await self.scheduler.start()

        # Initialize blog scheduler from config (cron auto-blogging, no LLM)
        if self.config.get("auto_blogs"):
            try:
                from safeclaw.core.blog_scheduler import BlogScheduler
                self.blog_scheduler = BlogScheduler.from_config(self)
                logger.info("Blog scheduler initialized")
            except Exception as e:
                logger.warning(f"Blog scheduler init failed: {e}")

        # Start all enabled channels
        channel_tasks = []
        for name, channel in self.channels.items():
            if hasattr(channel, "start"):
                channel_tasks.append(asyncio.create_task(channel.start()))
                logger.info(f"Started channel: {name}")

        # Main event loop
        try:
            await asyncio.gather(*channel_tasks)
        except asyncio.CancelledError:
            logger.info("SafeClaw shutting down...")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the SafeClaw engine."""
        logger.info("Stopping SafeClaw...")
        self.running = False

        # Stop scheduler
        await self.scheduler.stop()

        # Stop all channels
        for name, channel in self.channels.items():
            if hasattr(channel, "stop"):
                await channel.stop()
                logger.info(f"Stopped channel: {name}")

        # Close memory connection
        await self.memory.close()

        logger.info("SafeClaw stopped.")

    def get_help(self) -> str:
        """Return help text with available commands."""
        help_lines = [
            "SafeClaw - Your privacy-first automation assistant",
            "",
            "Available commands:",
        ]

        for intent in self.parser.get_intents():
            examples = self.parser.get_examples(intent)
            if examples:
                help_lines.append(f"  • {intent}: {examples[0]}")

        help_lines.extend([
            "",
            "Available actions:",
        ])

        for action in self.actions:
            help_lines.append(f"  • {action}")

        help_lines.extend([
            "",
            "250-Star Features:",
            "  • research <topic>     — Search arXiv, Semantic Scholar, Wolfram Alpha",
            "  • research arxiv <q>   — Search arXiv papers directly",
            "  • research scholar <q> — Search Semantic Scholar papers",
            "  • research wolfram <q> — Ask Wolfram Alpha",
            "  • setup ai sk-ant-...  — Enter your Anthropic key, done",
            "  • setup ai local       — Auto-install Ollama (free, private)",
            "  • setup ai status      — Check your AI setup",
            "",
            "100-Star Features:",
            "  • code template <type> — Code generation (non-LLM templates + optional LLM)",
            "  • style profile        — View your learned writing style profile",
            "  • style learn          — Feed text to the writing style profiler",
            "  • auto blog            — Configure cron-based auto-blogging (no LLM)",
            "  • flow                 — Show system architecture flow diagram",
            "",
            "Smart Input:",
            "  • Auto-corrects typos (remaind → remind, summerize → summarize)",
            "  • Word-to-number (select one two three → select 1 2 3)",
            "  • Learns from your mistakes automatically",
            "",
            "Per-task LLM routing:",
            "  Configure different LLMs for blogging, research, and coding",
            "  in config.yaml under task_providers.",
        ])

        return "\n".join(help_lines)
