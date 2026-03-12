"""
Natural Language Understanding (NLU) bridge for SafeClaw.

When a user types something the rule-based parser can't match, the NLU
bridge can optionally ask a configured LLM to translate it into a standard
SafeClaw command string.  The translated string goes right back through the
same parser, so the LLM never executes anything directly — it only rewords
the input.

Enable in config.yaml:

    safeclaw:
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
    from safeclaw.core.ai_writer import AIWriter
    from safeclaw.core.parser import CommandParser

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a command translator for SafeClaw, a personal automation assistant.

The user typed something that could not be matched to a known command.
Your job is to translate it into the closest matching SafeClaw command.

RULES — follow all of them without exception:
1. Reply with ONLY a single command line. No explanation, no punctuation, no markdown.
2. Use ONLY the command patterns listed below.
3. Fill in placeholders (shown in angle brackets) with values from the user's input.
4. If you cannot confidently map the input to any command, reply with exactly: UNKNOWN

Known commands (one per line):
{command_list}
"""

_HELP_SYSTEM_PROMPT = """\
You are the built-in assistant for SafeClaw, a privacy-first personal automation tool.
Answer the user's question concisely using only the information in the help text below.
Use Markdown formatting. If the answer is a setup step, show the exact command.
If the question is not covered by the help text, say so briefly.

SafeClaw help text:
{help_text}
"""


class NLUInterpreter:
    """
    Optional LLM-based fallback for unrecognised SafeClaw input.

    Usage (from SafeClaw engine):

        nlu = NLUInterpreter(ai_writer, parser, config.get("safeclaw", {}).get("nlu", {}))
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
        Ask the LLM to translate *user_text* into a SafeClaw command.

        Returns the translated command string, or None if:
        - The LLM returned UNKNOWN
        - The AI writer has no providers
        - The call failed
        """
        if not self.ai_writer or not self.ai_writer.providers:
            return None

        if self._system_prompt is None:
            self._system_prompt = self._build_system_prompt()

        prompt = f'Translate this to a SafeClaw command: "{user_text}"'

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

    async def answer_question(self, user_text: str, help_text: str) -> str | None:
        """
        Ask the LLM to answer a help/how-to question about SafeClaw.

        Returns the answer string, or None if unavailable.
        """
        if not self.ai_writer or not self.ai_writer.providers:
            return None

        system_prompt = _HELP_SYSTEM_PROMPT.format(help_text=help_text)

        response = await self.ai_writer.generate(
            prompt=user_text,
            provider_label=self.provider_label,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=512,
        )

        if response.error or not response.content.strip():
            logger.debug(f"NLU question answering failed: {response.error}")
            return None

        return response.content.strip()
