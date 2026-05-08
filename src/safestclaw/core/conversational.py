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


def _detect_topic(text: str) -> tuple[str, str] | None:
    """Return (topic_id, hint) for the first matching topic, else None."""
    for topic, pattern, hint in _TOPIC_HINTS:
        if pattern.search(text):
            return topic, hint
    return None


class ConversationalFallback:
    """Build a chat-friendly reply for messages the parser couldn't match."""

    def __init__(self, memory: "Memory") -> None:
        self.memory = memory

    async def reply(self, text: str, user_id: str) -> str:
        """Return a friendly response for an unparsed message."""
        if _GREETING.match(text):
            return "Hey 👋 — what would you like me to automate?"
        if _THANKS.match(text):
            return "Anytime."

        topic_match = _detect_topic(text)
        if topic_match:
            return await self._topic_reply(text, user_id, *topic_match)

        return await self._orientation_reply(user_id)

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

    async def _orientation_reply(self, user_id: str) -> str:
        """Show the automation orientation exactly once per user."""
        oriented_key = f"_chat_oriented:{user_id}" if user_id else None
        oriented = bool(await self.memory.get(oriented_key)) if oriented_key else False
        if not oriented:
            if oriented_key:
                await self.memory.set(oriented_key, "1")
            return (
                "Hey — I'm here to help with automation. Ask about anything "
                "you want automated and I can help with it, or you can read "
                "the raw documentation with /help."
            )
        return "I'm listening — what would you like me to do?"
