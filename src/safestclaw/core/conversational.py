"""
Channel-agnostic conversational fallback for unparsed messages.

When the rule-based parser can't match a message and the optional
LLM-based NLU isn't available (or didn't produce a reply), the engine
calls into here so the bot still says something helpful.

Behaviour, by design:
  * greetings and thanks get short, human replies,
  * messages that are *command-adjacent* (mention a domain SafestClaw
    actually covers — weather, news, summarize, calendar, reminder,
    blog, research, code, email, crawl, briefing) get a one-line hint
    pointing at the relevant action — but only once per user/topic,
    unless the user asks unambiguously ("can you do X?"),
  * truly off-topic chat gets a single orientation line — "I'm here to
    help with automation; ask about anything you want automated, or
    /help for raw docs" — once per user, then a brief listening line
    on subsequent off-topic turns.

Per-user state is persisted to the engine's ``Memory`` store so the
no-nag rules survive restarts and apply across every UI (CLI, web UI,
Telegram bot).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safestclaw.core.memory import Memory


# (topic_id, compiled regex, hint shown to the user)
_TOPIC_HINTS: list[tuple[str, re.Pattern[str], str]] = [
    ("weather",
     re.compile(r"\b(weather|temperature|forecast|rain|sunny|cloudy|degrees|humidity)\b", re.IGNORECASE),
     "I can pull current conditions — try `weather <city>`."),
    ("news",
     re.compile(r"\b(news|headlines?|breaking|articles?|stories)\b", re.IGNORECASE),
     "I can fetch RSS headlines — try `news` or `news tech`."),
    ("summarize",
     re.compile(r"\b(summar(y|ize|ise)|tl;?dr|recap|the gist)\b", re.IGNORECASE),
     "I can summarize URLs and text — try `summarize <url>`."),
    ("calendar",
     re.compile(r"\b(calendar|schedule|meetings?|events?|appointments?|agenda)\b", re.IGNORECASE),
     "I can read events from .ics or CalDAV — try `calendar today`."),
    ("reminder",
     re.compile(r"\b(remind(er)?|alarm|notify me|alert me|don'?t let me forget)\b", re.IGNORECASE),
     "I can set reminders — try `remind me to <thing> at <time>`."),
    ("blog",
     re.compile(r"\b(blog|publish a post|write an article)\b", re.IGNORECASE),
     "I can assemble blog posts — try `blog write news <topic>`."),
    ("research",
     re.compile(r"\b(research|look (it )?up|find out|tell me about|wiki(pedia)?)\b", re.IGNORECASE),
     "I can pull from Wikipedia and the web — try `research <topic>`."),
    ("code",
     re.compile(r"\b(code|function|script|debug|refactor|programming)\b", re.IGNORECASE),
     "I can scaffold or review code — try `code <prompt>`."),
    ("email",
     re.compile(r"\b(emails?|inbox|mailbox)\b", re.IGNORECASE),
     "I can read/send email when configured — try `email check` or `setup email`."),
    ("crawl",
     re.compile(r"\b(crawl|scrape|extract links?|fetch (the )?page)\b", re.IGNORECASE),
     "I can fetch pages and pull out links — try `crawl <url>`."),
    ("briefing",
     re.compile(r"\b(briefing|digest|morning report|catch me up)\b", re.IGNORECASE),
     "I can build a daily briefing — try `briefing`."),
]

_CAPABILITY_QUESTION = re.compile(
    r"\b(can|could|do|are|is there|how do)\b.*\b(you|i)\b",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^\s*(hi|hello|hey|yo|sup|good\s+(morning|afternoon|evening)|howdy)\b",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^\s*(thanks|thank\s+you|thx|ty|cheers|appreciate it)\b",
    re.IGNORECASE,
)
# "what are you capable of?" / "what can you do?" / "explain what you do"
# style — the user is explicitly asking for a capability summary, so we
# always answer with one (no once-per-user gating).
_WANTS_CAPABILITIES = re.compile(
    r"\b("
    r"what (can|do) you (do|automate|help|offer)|"
    r"capable of|"
    r"what are your (capabilities|features|skills)|"
    r"explain (what you (do|can do)|yourself)|"
    r"tell me what you (do|can do)|"
    r"what is your (capability|purpose)|"
    r"who are you|what are you"
    r")\b",
    re.IGNORECASE,
)
_CAPABILITY_SUMMARY = (
    "Here's what I can automate today:\n\n"
    "  • **Summarize** an article or page from a URL\n"
    "  • **News** — RSS headlines by topic\n"
    "  • **Weather** for any city\n"
    "  • **Reminders** at a time you pick\n"
    "  • **Calendar** — read your `.ics` file or CalDAV\n"
    "  • **Briefing** — your daily digest\n"
    "  • **Crawl** — fetch a page and extract its links\n"
    "  • **Research** — Wikipedia / arXiv / Wolfram lookups\n"
    "  • **Blog** — assemble or publish posts\n"
    "  • **Email** — read or send (when configured)\n"
    "  • **Security scans** — bandit / pip-audit / trivy / etc.\n\n"
    "Just ask in plain language — *\"summarize this URL\"*, *\"news tech\"*, "
    "*\"remind me to call mom at 3pm\"*. For free-form chat plug in an LLM "
    "with `setup ai <your-key>` (or `setup ai local` for free local Ollama)."
)


def _detect_topic(text: str) -> tuple[str, str] | None:
    """Return (topic_id, hint) for the first matching topic, else None."""
    for topic, pattern, hint in _TOPIC_HINTS:
        if pattern.search(text):
            return topic, hint
    return None


class ConversationalFallback:
    """Build a chat-friendly reply for messages the parser couldn't match."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    async def reply(
        self,
        text: str,
        user_id: str,
        has_llm: bool = False,
    ) -> str:
        """Return a friendly response for an unparsed message.

        ``has_llm`` lets the caller signal that an LLM/NLU was configured
        but didn't produce a reply (e.g. provider call failed). When True
        the orientation line points the user at `setup ai status` so the
        silent-failure case is debuggable. When False it suggests
        plugging an LLM in for free-form chat.
        """
        if _GREETING.match(text):
            return "Hey 👋 — what would you like me to automate?"
        if _THANKS.match(text):
            return "Anytime."

        # Capability questions get the full summary every time — the
        # user is explicitly asking, so don't gate it once-per-user.
        if _WANTS_CAPABILITIES.search(text):
            return _CAPABILITY_SUMMARY

        topic_match = _detect_topic(text)
        if topic_match:
            return await self._topic_reply(text, user_id, *topic_match)

        return await self._orientation_reply(user_id, has_llm=has_llm)

    async def _topic_reply(
        self,
        text: str,
        user_id: str,
        topic: str,
        hint: str,
    ) -> str:
        """Surface a capability hint, but only when it won't nag."""
        seen_key = f"_chat_suggested:{user_id}:{topic}" if user_id else None
        already = bool(await self.memory.get(seen_key)) if seen_key else False
        asks_explicitly = bool(_CAPABILITY_QUESTION.search(text))
        if not already or asks_explicitly:
            if seen_key:
                await self.memory.set(seen_key, "1")
            return hint
        return "Got you. Want me to do anything with that?"

    async def _orientation_reply(
        self, user_id: str, has_llm: bool = False,
    ) -> str:
        """Show the automation orientation; tailor for LLM-on/off."""
        oriented_key = f"_chat_oriented:{user_id}" if user_id else None
        oriented = bool(await self.memory.get(oriented_key)) if oriented_key else False
        if not oriented:
            if oriented_key:
                await self.memory.set(oriented_key, "1")
            if has_llm:
                # NLU is configured but didn't produce a reply for this
                # turn — surface the diagnostic instead of pretending we
                # don't have an LLM at all.
                return (
                    "I'm here. (My LLM didn't answer this turn — if it "
                    "keeps doing that, run `setup ai status` to check.) "
                    "I can also automate things — summaries, news, "
                    "reminders, blogs, briefings, research — or read "
                    "the raw documentation with /help."
                )
            return (
                "Hey — I'm here to help with automation. Ask about anything "
                "you want automated and I can help with it, or you can read "
                "the raw documentation with /help.\n\n"
                "_For free-form chat I need an LLM. Plug one in with "
                "`setup ai sk-ant-...` (Anthropic), `setup ai sk-...` (OpenAI), "
                "`setup ai AI...` (Gemini), or `setup ai local` for free local "
                "Ollama._"
            )
        # Subsequent off-topic — keep nudging toward the LLM if not yet
        # set up; otherwise just acknowledge and move on.
        if has_llm:
            return (
                "I'm listening — but my LLM didn't reply this turn. "
                "Try `setup ai status` if it keeps happening."
            )
        return (
            "I can't free-form chat without an LLM — I only have canned "
            "greetings and capability hints. To unlock real chat: "
            "`setup ai <your-key>` or `setup ai local`."
        )
