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

    # ------------------------------------------------------------------
    # Persistent per-user onboarding state.
    #
    # Stored in engine.memory so state stays consistent across:
    #   * long-running polling (`safestclaw telegram`),
    #   * cron-driven one-shot ticks (`safestclaw telegram-tick`),
    #   * restarts of either.
    # ------------------------------------------------------------------

    async def _has_been_welcomed(self, user_id: int) -> bool:
        return bool(await self.engine.memory.get(f"_telegram:welcomed:{user_id}"))

    async def _mark_welcomed(self, user_id: int) -> None:
        await self.engine.memory.set(f"_telegram:welcomed:{user_id}", "1")

    async def _is_awaiting_choice(self, user_id: int) -> bool:
        return bool(await self.engine.memory.get(f"_telegram:awaiting:{user_id}"))

    async def _set_awaiting_choice(self, user_id: int, awaiting: bool) -> None:
        key = f"_telegram:awaiting:{user_id}"
        if awaiting:
            await self.engine.memory.set(key, "1")
        else:
            # Memory has no explicit delete; a 1-second TTL clears the row.
            await self.engine.memory.set(key, "", ttl_seconds=1)

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

    # ------------------------------------------------------------------
    # Per-user onboarding (LLM or learn commands?)
    # ------------------------------------------------------------------

    _ONBOARDING_PROMPT = (
        "👋 Welcome to SafestClaw! Two ways to use me — pick one:\n\n"
        "  *1*  Use an LLM (Claude, GPT, Gemini, Groq, or local Ollama)\n"
        "       Best for blogging, research, and code generation.\n\n"
        "  *2*  Learn my commands (no LLM, no API keys, no fees)\n"
        "       Summaries, news, crawl, weather, calendar, briefings, blog.\n\n"
        "Reply *1* or *2*. (Type `skip` to do this later.)"
    )

    _ONBOARDING_LLM_REPLY = (
        "Great — to plug in an LLM, paste your API key right here:\n\n"
        "  `setup ai sk-ant-...`   — Anthropic (Claude)\n"
        "  `setup ai sk-...`       — OpenAI (GPT)\n"
        "  `setup ai AI...`        — Google Gemini\n"
        "  `setup ai gsk_...`      — Groq\n\n"
        "Or for a free local model: `setup ai local` (installs Ollama).\n\n"
        "Need a key? https://console.anthropic.com/settings/keys"
    )

    _ONBOARDING_COMMANDS_REPLY = (
        "Nice — here's what I can do without any LLM:\n\n"
        "  `summarize <url>`     — extractive summary of a page\n"
        "  `news` / `news tech`  — RSS headlines\n"
        "  `crawl <url>`         — extract links from a page\n"
        "  `weather <city>`      — current conditions\n"
        "  `briefing`            — your daily digest\n"
        "  `calendar today`      — events from your .ics\n"
        "  `blog write news ...` — assemble a post (no LLM)\n"
        "  `research <topic>`    — wiki + web extracts\n"
        "  `style learn <text>`  — teach me your writing voice\n\n"
        "Or just ask me anything you want automated and I'll explain — "
        "or `setup ai <key>` later if you change your mind."
    )

    def _parse_onboarding_choice(self, text: str) -> str | None:
        """Map a user reply to an onboarding outcome.

        Returns the reply text, or ``None`` if the message doesn't look
        like a choice (caller should re-prompt).
        """
        t = (text or "").strip().lower()
        if not t:
            return None
        if t.startswith(("1", "llm", "ai", "use llm", "use ai", "yes")):
            return self._ONBOARDING_LLM_REPLY
        if t.startswith(("2", "command", "learn", "no llm", "offline")):
            return self._ONBOARDING_COMMANDS_REPLY
        if t in ("skip", "later", "cancel", "no", "nope"):
            return (
                "OK — skipped. Just ask me anything you want automated and "
                "I'll help, or `setup ai <your-key>` any time to add an LLM."
            )
        return None

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

        # /start always (re-)launches the simple wizard.
        uid = update.effective_user.id
        await self._mark_welcomed(uid)
        await self._set_awaiting_choice(uid, True)
        await self._safe_reply(update.message, self._ONBOARDING_PROMPT)

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

        # \u2500\u2500 Onboarding intercept \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # First message from a user \u2192 show the simple wizard.
        if not await self._has_been_welcomed(user_id):
            await self._mark_welcomed(user_id)
            await self._set_awaiting_choice(user_id, True)
            await self._safe_reply(update.message, self._ONBOARDING_PROMPT)
            return

        # User is mid-wizard \u2192 parse their answer (or re-prompt).
        if await self._is_awaiting_choice(user_id):
            reply = self._parse_onboarding_choice(text)
            if reply is None:
                await self._safe_reply(
                    update.message,
                    "I didn't catch that \u2014 reply *1* (LLM) or *2* (commands), "
                    "or `skip`.",
                )
                return
            await self._set_awaiting_choice(user_id, False)
            await self._safe_reply(update.message, reply)
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

    # ------------------------------------------------------------------
    # Cron-friendly one-shot tick.
    #
    # `tick()` does a single non-blocking getUpdates call, processes
    # every pending message through the same engine path the long-
    # running bot uses, sends replies via bot.send_message, and exits.
    # Designed for `*/N * * * * safestclaw telegram-tick` so the bot
    # can keep replying (LLM included) when the always-on process
    # isn't running. Telegram queues unread updates for ~24 hours, so
    # missed messages get caught up on the next tick.
    #
    # IMPORTANT: do NOT run tick alongside the long-polling process.
    # Telegram serialises getUpdates consumers and returns 409
    # Conflict if more than one is active at a time.
    # ------------------------------------------------------------------

    _OFFSET_KEY = "_telegram:offset"

    async def tick(self) -> int:
        """Poll once, process everything pending, exit.

        Returns the number of updates processed.
        """
        if not HAS_TELEGRAM:
            raise ImportError(
                "Telegram support not installed. "
                "Run: pip install safestclaw[telegram]"
            )

        from telegram import Bot

        bot = Bot(self.token)
        await bot.initialize()
        try:
            offset_raw = await self.engine.memory.get(self._OFFSET_KEY)
            offset = int(offset_raw) + 1 if offset_raw else 0

            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=0,
                    allowed_updates=["message", "edited_message"],
                )
            except TelegramError as e:
                # 409 Conflict means another consumer (e.g. the long-
                # polling `safestclaw telegram` process) owns the
                # session. Treat it as "nothing to do this tick" so the
                # cron schedule doesn't spam errors.
                msg = str(e)
                if "Conflict" in msg or "409" in msg:
                    logger.debug(
                        "tick: another getUpdates consumer is active; "
                        "skipping this tick"
                    )
                    return 0
                logger.error("tick: get_updates failed: %s", e)
                return 0

            if not updates:
                logger.debug("tick: no pending updates")
                return 0

            for upd in updates:
                try:
                    await self._tick_handle(bot, upd)
                except Exception:
                    logger.exception(
                        "tick: error handling update %s", upd.update_id
                    )

            # Persist the highest update_id we've seen so the next tick
            # picks up where we left off.
            await self.engine.memory.set(
                self._OFFSET_KEY, str(updates[-1].update_id)
            )
            return len(updates)
        finally:
            await bot.shutdown()

    async def _tick_handle(self, bot: Any, update: Any) -> None:
        """Process a single update outside the PTB Application loop."""
        if not update.message or not update.effective_user:
            return
        msg = update.message
        chat_id = msg.chat_id
        user_id = update.effective_user.id
        text = msg.text or ""
        no_allowlist = not self.allowed_users

        is_self_register = (
            no_allowlist
            and text.strip().lower() == "setup telegram allow me"
        )

        # Authorization
        if not is_self_register and not self._is_allowed(user_id):
            await self._tick_send(
                bot, chat_id, "Sorry, you're not authorized to use this bot."
            )
            return

        # Slash commands
        stripped = text.strip()
        if stripped.startswith("/start"):
            await self._mark_welcomed(user_id)
            await self._set_awaiting_choice(user_id, True)
            await self._tick_send(bot, chat_id, self._ONBOARDING_PROMPT)
            return
        if stripped.startswith("/help"):
            await self._tick_send(bot, chat_id, self.engine.get_help())
            return

        # First-message wizard
        if not await self._has_been_welcomed(user_id):
            await self._mark_welcomed(user_id)
            await self._set_awaiting_choice(user_id, True)
            await self._tick_send(bot, chat_id, self._ONBOARDING_PROMPT)
            return

        # Mid-wizard
        if await self._is_awaiting_choice(user_id):
            reply = self._parse_onboarding_choice(text)
            if reply is None:
                await self._tick_send(
                    bot, chat_id,
                    "I didn't catch that \u2014 reply *1* (LLM) or *2* (commands), "
                    "or `skip`.",
                )
                return
            await self._set_awaiting_choice(user_id, False)
            await self._tick_send(bot, chat_id, reply)
            return

        # Engine + LLM
        try:
            response = await self.handle_message(text=text, user_id=str(user_id))
        except Exception as e:
            logger.exception("tick: engine failed for user %s", user_id)
            await self._tick_send(
                bot, chat_id, f"Something went wrong handling that: {e}"
            )
            return

        if not response:
            response = "(no response)"
        if no_allowlist and not is_self_register:
            response += (
                "\n\n\u26a0\ufe0f *Bot is open to anyone.* "
                "Send `setup telegram allow me` to restrict access to your ID."
            )
        await self._tick_send(bot, chat_id, response)

    async def _tick_send(self, bot: Any, chat_id: int, text: str) -> None:
        """Send with the same Markdown\u2192plain-text fallback as _safe_reply."""
        if not text:
            return
        try:
            await bot.send_message(
                chat_id=chat_id, text=text, parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning(
                "tick: Markdown send failed (%s); retrying as plain text", e
            )
            try:
                await bot.send_message(chat_id=chat_id, text=text)
            except Exception as e2:
                logger.error("tick: plain-text send also failed: %s", e2)
        except Exception as e:
            logger.error("tick: send failed: %s", e)
