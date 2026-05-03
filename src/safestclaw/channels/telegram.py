"""Telegram channel adapter."""

import logging
from typing import TYPE_CHECKING

try:
    from telegram import Update
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

from safestclaw.channels.base import BaseChannel

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    """
    Telegram bot channel.

    Requires: pip install python-telegram-bot
    (or, from a checkout: pip install -e ".[telegram]")

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
                "Run: pip install python-telegram-bot "
                "(or, from a checkout: pip install -e \".[telegram]\")"
            )

        super().__init__(engine)
        self.token = token
        self.allowed_users = set(allowed_users) if allowed_users else None
        self.app: Application | None = None

    async def start(self) -> None:
        """Start the Telegram bot."""
        self.app = Application.builder().token(self.token).build()

        # Register handlers
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")

    async def send(self, user_id: str, message: str) -> None:
        """Send a message to a user."""
        if self.app:
            try:
                await self.app.bot.send_message(
                    chat_id=int(user_id),
                    text=message,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

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
            await update.message.reply_text("Sorry, you're not authorized to use this bot.")
            return

        await update.message.reply_text(
            "Welcome to SafestClaw! 🐾\n\n"
            "I'm your privacy-first automation assistant.\n"
            "Type /help to see what I can do.",
            parse_mode="Markdown",
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
        await update.message.reply_text(help_text, parse_mode="Markdown")

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
            await update.message.reply_text("Sorry, you're not authorized to use this bot.")
            return

        # Process message
        response = await self.handle_message(
            text=text,
            user_id=str(user_id),
        )

        # Warn when no allowlist is configured (bot is open to anyone)
        if no_allowlist and not is_self_register:
            response = (
                response
                + "\n\n\u26a0\ufe0f *Bot is open to anyone.* "
                "Send `setup telegram allow me` to restrict access to your ID."
            )

        # Send response
        await update.message.reply_text(response, parse_mode="Markdown")
