"""
Channel-agnostic first-run setup flow.

The original `setup_wizard` is rich-prompt based and only works in a
real TTY. Web UI, Telegram, and any future chat channel can't use it.
This module exposes the same decisions as a sequence of plain-text
Q&A turns that work over any channel that dispatches through
``engine.handle_message``.

Lifecycle:

  user types anything →
  engine sees `is_first_run(config_path)` →
  engine hands the message to ``ChatSetup.handle`` →
  setup advances one step and returns the next prompt →
  on the final step, ``setup_completed: true`` is written to config
  and the user is sent back into normal command routing.

States
------

  welcome   → first message a user sees explaining what's about to happen
  mode      → 1) local-only / 2) cloud LLM / 3) hybrid / 4) skip
  cloud_pick → choose anthropic / openai / google / groq
  cloud_key  → paste the API key
  local_model → pick a Ollama preset (small / default / large / coding / writing)
  done       → mark setup complete and return to normal routing

Sessions are kept in-memory per user — restart loses progress, but the
next message will just re-enter the wizard at the welcome step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChatSetupSession:
    """Per-user state through the chat setup flow."""
    state: str = "welcome"
    cloud_provider: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


# Reusing the same provider/preset tables as the rich wizard so the chat
# flow stays in sync with what `setup_wizard.py` writes.
def _cloud_providers() -> dict[str, dict[str, Any]]:
    from safestclaw.core.llm_installer import CLOUD_PROVIDERS
    return CLOUD_PROVIDERS


def _local_models() -> dict[str, dict[str, str]]:
    from safestclaw.core.llm_installer import LOCAL_MODELS
    return LOCAL_MODELS


# Phrases that mean "I don't want to do this" at any step.
_SKIP_PHRASES = (
    "skip", "later", "no", "nope", "not now",
    "cancel", "abort", "exit", "quit",
)


class ChatSetup:
    """
    Drives the per-user setup conversation. One instance per engine.

    Engine integration:

        chat_setup = ChatSetup(config_path)
        ...
        if chat_setup.needs_setup():
            reply = await chat_setup.handle(text, user_id)
            if reply is not None:
                return reply
        # otherwise fall through to normal routing
    """

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self._sessions: dict[str, ChatSetupSession] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def needs_setup(self) -> bool:
        from safestclaw.core.setup_wizard import is_first_run
        return is_first_run(self.config_path)

    async def handle(self, text: str, user_id: str) -> str | None:
        """
        Advance the setup conversation by one turn.

        Returns the next prompt to show the user, or ``None`` to defer
        to normal command routing (only happens after the user picks
        "skip" or finishes the wizard).
        """
        text = (text or "").strip()
        lowered = text.lower()
        session = self._sessions.setdefault(user_id, ChatSetupSession())

        # Universal skip — bail out and mark setup done so we stop
        # asking. The user can always run `safestclaw setup` later
        # for the rich version.
        if (
            session.state in ("welcome", "mode")
            and lowered in _SKIP_PHRASES
        ):
            self._mark_done()
            self._sessions.pop(user_id, None)
            return (
                "Skipped setup — SafestClaw works fine in local-only mode "
                "out of the box. Run `safestclaw setup` any time to "
                "configure an LLM."
            )

        if session.state == "welcome":
            session.state = "mode"
            return self._welcome_text()

        if session.state == "mode":
            return self._handle_mode(lowered, session, user_id)

        if session.state == "cloud_pick":
            return self._handle_cloud_pick(lowered, session)

        if session.state == "cloud_key":
            return self._handle_cloud_key(text, session, user_id)

        if session.state == "local_model":
            return await self._handle_local_model(lowered, session, user_id)

        # Fallback — should never be reached
        self._mark_done()
        self._sessions.pop(user_id, None)
        return None

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _welcome_text(self) -> str:
        return (
            "Welcome to SafestClaw — privacy-first personal automation.\n\n"
            "Everything works fully offline (summaries, news, blog, "
            "calendar, …). You can optionally add an LLM for blogging, "
            "research, and code generation.\n\n"
            "How would you like to set up?\n\n"
            "  **1**  Local-only — no LLM, free, private. Recommended.\n"
            "  **2**  Cloud LLM — Anthropic / OpenAI / Google / Groq (API key needed)\n"
            "  **3**  Hybrid — local Ollama + cloud, per-task routing\n"
            "  **4**  Skip — I'll edit config.yaml myself\n\n"
            "Type a number, or type **skip** to do this later."
        )

    def _handle_mode(
        self,
        lowered: str,
        session: ChatSetupSession,
        user_id: str,
    ) -> str:
        if lowered.startswith("1"):
            self._mark_done()
            self._sessions.pop(user_id, None)
            return (
                "Local-only mode it is. All deterministic features are "
                "ready to use. Try `help` to see what's available."
            )

        if lowered.startswith("2"):
            session.state = "cloud_pick"
            return self._cloud_pick_text()

        if lowered.startswith("3"):
            # Hybrid: ask about local first, then cloud after.
            session.extras["hybrid"] = True
            session.state = "local_model"
            return self._local_model_text(prefix="**Hybrid setup — step 1/2**\n\n")

        if lowered.startswith("4"):
            self._mark_done()
            self._sessions.pop(user_id, None)
            return (
                "OK — edit `config/config.yaml` to set things up by hand. "
                "Run `safestclaw setup` any time for the rich wizard."
            )

        return (
            "I didn't catch that. Type **1**, **2**, **3**, or **4** "
            "(or **skip** to defer setup)."
        )

    def _cloud_pick_text(self) -> str:
        providers = _cloud_providers()
        lines = ["Pick a cloud provider:\n"]
        for i, (name, info) in enumerate(providers.items(), 1):
            lines.append(
                f"  **{i}**  {name}  — {info['model']}  "
                f"(key prefix `{info['key_prefix']}`)"
            )
        lines.append("")
        lines.append(
            "Type a number, or **skip** to do this later. Get keys at:"
        )
        for name, info in providers.items():
            lines.append(f"  {name}: {info['key_url']}")
        return "\n".join(lines)

    def _handle_cloud_pick(
        self, lowered: str, session: ChatSetupSession,
    ) -> str:
        providers = list(_cloud_providers().items())
        try:
            idx = int(lowered.split()[0]) - 1
        except (ValueError, IndexError):
            return (
                "Type a number from the list above, "
                "or **skip** to defer."
            )
        if idx < 0 or idx >= len(providers):
            return f"Pick a number from 1 to {len(providers)}."
        name, _info = providers[idx]
        session.cloud_provider = name
        session.state = "cloud_key"
        return (
            f"Great — paste your **{name}** API key now. "
            "I'll save it to config.yaml.\n"
            "(Type **skip** if you don't have one handy.)"
        )

    def _handle_cloud_key(
        self,
        text: str,
        session: ChatSetupSession,
        user_id: str,
    ) -> str:
        if text.lower() in _SKIP_PHRASES:
            self._mark_done()
            self._sessions.pop(user_id, None)
            return (
                "Skipped — you can finish later with "
                f"`setup ai {session.cloud_provider}-...` or by editing "
                "config.yaml."
            )
        from safestclaw.core.llm_installer import setup_with_key
        try:
            msg = setup_with_key(text.strip(), self.config_path)
        except Exception as e:
            logger.warning(f"setup_with_key failed: {e}")
            return f"Couldn't save that key: {e}\nPaste the key again, or **skip**."

        if session.extras.get("hybrid"):
            # Continue to local model selection
            session.state = "local_model"
            return msg + "\n\n" + self._local_model_text(
                prefix="**Hybrid setup — step 2/2**\n\n",
            )

        self._mark_done()
        self._sessions.pop(user_id, None)
        return msg + "\n\nSetup complete. Try `help` to see commands."

    def _local_model_text(self, prefix: str = "") -> str:
        models = _local_models()
        lines = [
            prefix +
            "Pick a local Ollama model preset (we'll install Ollama "
            "if needed):\n"
        ]
        for i, (preset, info) in enumerate(models.items(), 1):
            lines.append(
                f"  **{i}**  {preset}  — {info['name']} "
                f"({info['size']}; {info['desc']})"
            )
        lines.append("")
        lines.append("Type a number, or **skip** to defer.")
        return "\n".join(lines)

    async def _handle_local_model(
        self,
        lowered: str,
        session: ChatSetupSession,
        user_id: str,
    ) -> str:
        if lowered in _SKIP_PHRASES:
            self._mark_done()
            self._sessions.pop(user_id, None)
            return (
                "Skipped local model. You can install Ollama any time "
                "with `setup ai local`."
            )
        models = list(_local_models().items())
        try:
            idx = int(lowered.split()[0]) - 1
        except (ValueError, IndexError):
            return "Type a number from the list above, or **skip**."
        if idx < 0 or idx >= len(models):
            return f"Pick a number from 1 to {len(models)}."
        preset, _info = models[idx]
        from safestclaw.core.llm_installer import setup_local
        try:
            msg = await setup_local(preset, self.config_path)
        except Exception as e:
            logger.warning(f"setup_local failed: {e}")
            self._mark_done()
            self._sessions.pop(user_id, None)
            return (
                f"Couldn't install Ollama automatically: {e}\n"
                "You can install it manually from https://ollama.com "
                "and re-run `setup ai local`."
            )
        self._mark_done()
        self._sessions.pop(user_id, None)
        return msg + "\n\nSetup complete. Try `help` to see commands."

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _mark_done(self) -> None:
        from safestclaw.core.setup_wizard import (
            _ensure_default_config,
            _mark_completed,
        )
        _ensure_default_config(self.config_path)
        _mark_completed(self.config_path)
