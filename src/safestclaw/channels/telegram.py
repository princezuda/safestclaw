"""Telegram channel adapter."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

try:
    from telegram import Update
    from telegram.error import TelegramError
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    TelegramError = Exception  # type: ignore[assignment,misc]

from safestclaw.channels.base import BaseChannel

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """
    Telegram bot channel.

    Requires: pip install safestclaw[telegram]

    Features:
    - Direct messages
    - Group chat support
    - Command handling
    - Markdown formatting
    """

    name = "telegram"

    def __init__(
        self,
        engine: "SafestClaw",
        token: str,
        allowed_users: list[int] | None = None,
    ):
        if not HAS_TELEGRAM:
            raise ImportError(
                "Telegram support not installed. "
                "Run: pip install safestclaw[telegram]"
            )

        super().__init__(engine)
        self.token = token
        self.allowed_users = set(allowed_users) if allowed_users else None
        self.app: Application | None = None
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        """Start the Telegram bot."""
        self.app = Application.builder().token(self.token).build()

        # Register handlers
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )
        self.app.add_error_handler(self._on_error)

        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()

        # Confirm we're authenticated and warn about group-privacy gotchas.
        try:
            me = await self.app.bot.get_me()
            logger.info(
                "Telegram bot connected as @%s (id=%s)",
                me.username, me.id,
            )
            if not getattr(me, "can_read_all_group_messages", False):
                logger.warning(
                    "Group privacy mode is ON for @%s — in groups the bot will "
                    "only see commands, @mentions, and replies to its own "
                    "messages. To respond to every group message, message "
                    "@BotFather → /setprivacy → select your bot → Disable.",
                    me.username,
                )
        except Exception as e:
            logger.warning("Could not fetch bot info: %s", e)

        await self.app.updater.start_polling(
            allowed_updates=["message", "edited_message", "callback_query"],
        )

        # python-telegram-bot v20+ kicks polling off in the background and
        # returns from start_polling() immediately. Block here so the engine's
        # asyncio.gather() over channel tasks doesn't see this coroutine
        # finish and tear the whole process down. stop() releases this wait.
        self._stop_event = asyncio.Event()
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            # Engine was cancelled — let stop() do the cleanup.
            raise

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self.app:
            try:
                if self.app.updater and self.app.updater.running:
                    await self.app.updater.stop()
                if self.app.running:
                    await self.app.stop()
                await self.app.shutdown()
            except Exception as e:
                logger.warning("Error during Telegram shutdown: %s", e)
            logger.info("Telegram bot stopped")

    async def send(self, user_id: str, message: str) -> None:
        """Send a message to a user, with Markdown→plain-text fallback."""
        if not self.app or not message:
            return
        chat_id = int(user_id)
        try:
            await self.app.bot.send_message(
                chat_id=chat_id, text=message, parse_mode="Markdown",
            )
        except TelegramError as e:
            # Markdown parsing or formatting issue — retry as plain text so
            # the user always gets the response.
            logger.warning("Markdown send failed (%s); retrying as plain text", e)
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=message)
            except Exception as e2:
                logger.error("Plain-text send also failed: %s", e2)
        except Exception as e:
            logger.error("Failed to send message: %s", e)

    async def _safe_reply(self, message: Any, text: str) -> None:
        """Reply with Markdown, falling back to plain text on parse errors.

        Engine responses occasionally include unbalanced ``*``/``_``/backticks
        (action help, code excerpts, etc.). Telegram's legacy Markdown parser
        rejects those with HTTP 400 and the user would see no reply at all
        unless we retry without ``parse_mode``.
        """
        if not text:
            return
        try:
            await message.reply_text(text, parse_mode="Markdown")
        except TelegramError as e:
            logger.warning("Markdown reply failed (%s); retrying as plain text", e)
            try:
                await message.reply_text(text)
            except Exception as e2:
                logger.error("Plain-text reply also failed: %s", e2)
        except Exception as e:
            logger.error("Failed to reply: %s", e)

    async def _on_error(
        self,
        update: object,
        context: "ContextTypes.DEFAULT_TYPE",
    ) -> None:
        """Log uncaught handler errors so AI/engine failures are visible."""
        logger.exception(
            "Telegram handler error: %s", context.error,
            exc_info=context.error,
        )

    def _is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed."""
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    async def _cmd_start(
        self,
        update: "Update",
        context: "ContextTypes.DEFAULT_TYPE",
    ) -> None:
        """Handle /start command."""
        if not update.effective_user or not update.message:
            return

        if not self._is_allowed(update.effective_user.id):
            await self._safe_reply(
                update.message, "Sorry, you're not authorized to use this bot."
            )
            return

        await self._safe_reply(
            update.message,
            "Welcome to SafestClaw! 🐾\n\n"
            "I'm your privacy-first automation assistant.\n"
            "Type /help to see what I can do.",
        )

    async def _cmd_help(
        self,
        update: "Update",
        context: "ContextTypes.DEFAULT_TYPE",
    ) -> None:
        """Handle /help command."""
        if not update.message:
            return

        help_text = self.engine.get_help()
        await self._safe_reply(update.message, help_text)

    async def _handle_message(
        self,
        update: "Update",
        context: "ContextTypes.DEFAULT_TYPE",
    ) -> None:
        """Handle incoming text messages."""
        if not update.effective_user or not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        text = update.message.text
        no_allowlist = not self.allowed_users

        # Bootstrap: allow self-registration even when allowlist is empty
        is_self_register = (
            no_allowlist
            and text.strip().lower() == "setup telegram allow me"
        )

        if not is_self_register and not self._is_allowed(user_id):
            await self._safe_reply(
                update.message, "Sorry, you're not authorized to use this bot."
            )
            return

        # Route through the engine (rule-based parser \u2192 action \u2192 optional
        # AI/NLU). Surface errors so the user always gets a reply, even when
        # an action or AI provider raises.
        try:
            response = await self.handle_message(
                text=text,
                user_id=str(user_id),
            )
        except Exception as e:
            logger.exception("Engine failed to handle message from %s", user_id)
            await self._safe_reply(
                update.message, f"Something went wrong handling that: {e}"
            )
            return

        if not response:
            response = "(no response)"

        # Warn when no allowlist is configured (bot is open to anyone)
        if no_allowlist and not is_self_register:
            response = (
                response
                + "\n\n\u26a0\ufe0f *Bot is open to anyone.* "
                "Send `setup telegram allow me` to restrict access to your ID."
            )

        await self._safe_reply(update.message, response)
