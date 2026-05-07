"""
Natural Language Understanding (NLU) bridge for SafestClaw.

When a user types something the rule-based parser can't match, the NLU
bridge can optionally ask a configured LLM to translate it into a standard
SafestClaw command string.  The translated string goes right back through the
same parser, so the LLM never executes anything directly — it only rewords
the input.

Enable in config.yaml:

    safestclaw:
      nlu:
        enabled: true
        provider: my-claude      # optional — uses active provider if omitted
        max_tokens: 64           # keep it short; we only want one command line
        temperature: 0.0         # deterministic output preferred
        show_translation: true   # show user what was translated (default true)

The LLM is given a strict system prompt that lists every known intent and
an example command for each.  The prompt instructs the model to return a
*single command line and nothing else*.  If it cannot figure out a
reasonable mapping it should return the single word  UNKNOWN.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safestclaw.core.ai_writer import AIWriter
    from safestclaw.core.parser import CommandParser

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a command translator for SafestClaw, a personal automation assistant.

The user typed something that could not be matched to a known command.
Your job is to translate it into the closest matching SafestClaw command.

RULES — follow all of them without exception:
1. Reply with ONLY a single command line. No explanation, no punctuation, no markdown.
2. Use ONLY the command patterns listed below.
3. Fill in placeholders (shown in angle brackets) with values from the user's input.
4. If you cannot confidently map the input to any command, reply with exactly: UNKNOWN

Known commands (one per line):
{command_list}
"""

_HELP_SYSTEM_PROMPT = """\
You are SafestClaw, a privacy-first personal automation assistant.

How to reply, in priority order:

1. ANSWER THE USER. Whatever they ask — factual, casual, opinion, or about
   SafestClaw — answer it directly. Don't refuse and don't say "not in my
   help text". Use what you know.

2. ENGAGE OFF-TOPIC. If they want to chat, chat. Friendly, brief, human.

3. OFFER WHEN YOU CAN ACT. If the message touches something SafestClaw can
   actually do (summarize a URL, fetch news, set a reminder, fetch the
   weather, run research, write or publish a blog, read a calendar, scan
   for security issues, …), end with a short natural offer such as
   "Want me to do that for you?" Never lecture, never repeat the offer
   in consecutive turns, and never invent a capability the help text
   doesn't list.

4. PARAPHRASE — DO NOT PASTE. The help text below is reference material
   ONLY. When the user asks what you can do, or when you describe a
   capability, translate it into plain conversational English: "I can
   summarize a page if you give me a URL", "I can pull headlines from
   any RSS feed you point me at", and so on. Never paste the raw command
   list, never paste help text verbatim, never reply with a wall of
   bullet points. Show a literal command only when the user is about to
   type it themselves (e.g. they explicitly ask "what's the exact
   command?"). Never tell the user to type `/help` — they already know
   it exists; you are the help.

5. DON'T EXECUTE FROM THIS REPLY. A separate translator handles direct
   action requests like "blog for me" or "publish to <server> <user>
   <pass> <folder>". If the user clearly asks you to *do* something
   rather than discuss it, your reply here should be empty or a single
   "On it." — the translator will run the actual command.

{intro_directive}

Use Markdown sparingly. Keep it short and conversational unless the user
asks for depth.

SafestClaw help text (reference — paraphrase, do not paste):
{help_text}
"""

_INTRO_FIRST_TURN = (
    "6. INTRODUCE YOURSELF (first reply only). The user has not heard from "
    "you before. Open with this exact spirit, in your own words: "
    "\"Hey — I'm here to help with automation. Ask about anything you "
    "want automated and I can help with it, or you can read the raw "
    "documentation with /help.\" Then answer their message. Do this once."
)

_INTRO_SUBSEQUENT = (
    "6. NO RE-INTRODUCTION. The user already knows who you are; don't "
    "re-pitch SafestClaw, don't list capabilities unprompted, and never "
    "tell them to read /help. Just reply to what they said."
)


class NLUInterpreter:
    """
    Optional LLM-based fallback for unrecognised SafestClaw input.

    Usage (from SafestClaw engine):

        nlu = NLUInterpreter(ai_writer, parser, config.get("safestclaw", {}).get("nlu", {}))
        translated = await nlu.translate(text)
        if translated:
            parsed = parser.parse(translated, user_id)
    """

    def __init__(
        self,
        ai_writer: "AIWriter",
        parser: "CommandParser",
        nlu_config: dict,
    ) -> None:
        self.ai_writer = ai_writer
        self.parser = parser
        self.provider_label: str | None = nlu_config.get("provider")
        self.max_tokens: int = nlu_config.get("max_tokens", 64)
        self.temperature: float = float(nlu_config.get("temperature", 0.0))
        self.show_translation: bool = nlu_config.get("show_translation", True)
        self._system_prompt: str | None = None  # lazy-built

    def _build_system_prompt(self) -> str:
        """Build the system prompt from all known intents and their examples."""
        lines = []
        for intent in self.parser.get_intents():
            examples = self.parser.get_examples(intent)
            if examples:
                lines.append(examples[0])
            else:
                lines.append(intent.replace("_", " "))
        command_list = "\n".join(f"  {line}" for line in lines)
        return _SYSTEM_PROMPT_TEMPLATE.format(command_list=command_list)

    async def translate(self, user_text: str) -> str | None:
        """
        Ask the LLM to translate *user_text* into a SafestClaw command.

        Returns the translated command string, or None if:
        - The LLM returned UNKNOWN
        - The AI writer has no providers
        - The call failed
        """
        if not self.ai_writer or not self.ai_writer.providers:
            return None

        if self._system_prompt is None:
            self._system_prompt = self._build_system_prompt()

        prompt = f'Translate this to a SafestClaw command: "{user_text}"'

        response = await self.ai_writer.generate(
            prompt=prompt,
            provider_label=self.provider_label,
            system_prompt=self._system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        if response.error:
            logger.debug(f"NLU translation failed: {response.error}")
            return None

        translated = response.content.strip()

        # Reject if model couldn't map it or returned something suspiciously long
        if not translated or translated.upper() == "UNKNOWN" or "\n" in translated:
            logger.debug(f"NLU returned no useful translation for: {user_text!r}")
            return None

        logger.info(f"NLU translated {user_text!r} → {translated!r}")
        return translated

    async def answer_question(
        self,
        user_text: str,
        help_text: str,
        is_first_turn: bool = False,
    ) -> str | None:
        """
        Ask the LLM to answer a question or chat with the user.

        ``is_first_turn`` flips the system prompt so the LLM introduces
        itself exactly once per user. The engine is responsible for
        tracking this — see ``SafestClaw.handle_message``.

        Returns the reply, or None if unavailable.
        """
        if not self.ai_writer or not self.ai_writer.providers:
            return None

        intro_directive = (
            _INTRO_FIRST_TURN if is_first_turn else _INTRO_SUBSEQUENT
        )
        system_prompt = _HELP_SYSTEM_PROMPT.format(
            help_text=help_text,
            intro_directive=intro_directive,
        )

        response = await self.ai_writer.generate(
            prompt=user_text,
            provider_label=self.provider_label,
            system_prompt=system_prompt,
            temperature=0.4,
            max_tokens=512,
        )

        if response.error or not response.content.strip():
            logger.debug(f"NLU question answering failed: {response.error}")
            return None

        return response.content.strip()
