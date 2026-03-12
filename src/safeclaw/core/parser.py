"""
SafeClaw Command Parser - Rule-based intent classification.

No GenAI needed! Uses:
- Keyword matching
- Regex patterns
- Slot filling (dates, times, entities)
- Fuzzy matching for typo tolerance
- User-learned patterns from corrections
- Auto-learning from user mistakes (word-to-number, typo correction)
- Multilingual command understanding (deterministic, no AI)
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import dateparser
from rapidfuzz import fuzz

from safeclaw.core.i18n import (
    LANGUAGE_PACK,
    get_language_name,
    get_supported_languages,
)

if TYPE_CHECKING:
    from safeclaw.core.memory import Memory

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Smart Input Normalization — converts natural language quirks into
# machine-readable form BEFORE any intent matching happens.
# ──────────────────────────────────────────────────────────────────────────────

# Word-to-number mapping (supports ordinals too)
WORD_TO_NUMBER = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100",
    # Ordinals
    "first": "1", "second": "2", "third": "3", "fourth": "4",
    "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8",
    "ninth": "9", "tenth": "10",
}

# Common misspellings / shorthand that users type
COMMON_CORRECTIONS = {
    "remaind": "remind", "remimd": "remind", "reminde": "remind",
    "remmber": "remember", "rember": "remember",
    "summerize": "summarize", "sumarize": "summarize", "summarise": "summarize",
    "analize": "analyze", "analyse": "analyze", "analze": "analyze",
    "wether": "weather", "wheather": "weather", "weathr": "weather",
    "calender": "calendar", "calandar": "calendar",
    "scedule": "schedule", "schedual": "schedule", "shedule": "schedule",
    "recearch": "research", "reserch": "research", "reasearch": "research",
    "reasrch": "research",
    "pubish": "publish", "publsh": "publish",
    "tempalte": "template", "templete": "template",
    "crawel": "crawl", "crawal": "crawl",
    "doccument": "document", "documnet": "document",
    "notifiy": "notify", "notfy": "notify",
    "breifing": "briefing", "breiifng": "briefing",
    "instll": "install", "instal": "install",
    "plz": "please", "pls": "please",
    "tmrw": "tomorrow", "tmr": "tomorrow", "tmrow": "tomorrow",
    "yr": "year", "yrs": "years",
    "hr": "hour", "hrs": "hours",
    "min": "minute", "mins": "minutes",
    "sec": "second", "secs": "seconds",
}


def normalize_text(text: str) -> str:
    """
    Smart text normalization — fix common mistakes before parsing.

    This runs automatically on every input:
    1. Fix common misspellings (remaind -> remind)
    2. Convert word-numbers to digits when they appear alone or in
       contexts like "research select one two three"
    3. Normalize whitespace

    Args:
        text: Raw user input

    Returns:
        Normalized text with corrections applied
    """
    if not text:
        return text

    words = text.split()
    corrected = []
    changes_made = []

    for word in words:
        lower = word.lower()
        # Strip trailing punctuation for matching but preserve it
        stripped = lower.rstrip(".,!?;:")
        trailing = lower[len(stripped):]

        # Check common corrections first
        if stripped in COMMON_CORRECTIONS:
            fixed = COMMON_CORRECTIONS[stripped]
            # Preserve original case pattern
            if word[0].isupper():
                fixed = fixed.capitalize()
            corrected.append(fixed + trailing)
            changes_made.append((word, fixed))
            continue

        # Check word-to-number (only for standalone words, not inside URLs etc.)
        if stripped in WORD_TO_NUMBER:
            corrected.append(WORD_TO_NUMBER[stripped] + trailing)
            changes_made.append((word, WORD_TO_NUMBER[stripped]))
            continue

        corrected.append(word)

    result = " ".join(corrected)

    if changes_made:
        logger.debug(
            "Auto-corrected input: %s",
            ", ".join(f"'{old}' -> '{new}'" for old, new in changes_made),
        )

    return result


# Common phrase variations that map to core intents
# These cover natural language that users might type day-one
PHRASE_VARIATIONS = {
    "reminder": [
        "don't let me forget",
        "make sure i",
        "ping me",
        "tell me to",
        "remind me about",
        "i need to remember",
        "can you remind",
        "heads up about",
        "don't forget to",
        "note to self",
    ],
    "weather": [
        "how's the weather",
        "what's it like outside",
        "is it raining",
        "should i bring umbrella",
        "do i need a jacket",
        "temperature outside",
        "how hot is it",
        "how cold is it",
        "weather check",
    ],
    "crawl": [
        "what links are on",
        "show me links from",
        "find urls on",
        "list links on",
        "what pages link to",
        "scan website",
        "spider",
        "follow links",
    ],
    "email": [
        "any new mail",
        "new messages",
        "did i get mail",
        "any emails",
        "message from",
        "write email",
        "compose email",
        "mail to",
    ],
    "calendar": [
        "what's happening",
        "am i busy",
        "do i have anything",
        "free time",
        "book a meeting",
        "set up meeting",
        "schedule with",
        "my day",
        "today's events",
    ],
    "news": [
        "what's new",
        "latest news",
        "what's going on",
        "current events",
        "top stories",
        "breaking news",
        "recent news",
    ],
    "briefing": [
        "catch me up",
        "what's happening today",
        "daily digest",
        "morning summary",
        "start my day",
        "anything i should know",
        "overview for today",
    ],
    "help": [
        "what do you do",
        "how does this work",
        "show options",
        "list features",
        "what are my options",
        "menu",
        "capabilities",
    ],
    "summarize": [
        "sum up",
        "quick summary",
        "give me the gist",
        "main points",
        "key takeaways",
        "in brief",
        "cliff notes",
        "the short version",
    ],
    "shell": [
        "terminal",
        "cmd",
        "cli",
        "bash",
        "run this",
        "exec",
    ],
    "smarthome": [
        "switch on",
        "switch off",
        "lights on",
        "lights off",
        "make it brighter",
        "make it darker",
        "adjust lights",
    ],
    "blog": [
        "write blog",
        "blog news",
        "blog post",
        "add blog entry",
        "publish blog",
        "show blog",
        "blog title",
        "blog help",
        "my blog",
        "create blog",
        "for title content",
        "for body content",
        "for non-title content",
        "for heading content",
        "for text content",
        "ai blog",
        "blog ai",
        "manual blog",
        "edit blog",
        "ai options",
        "ai providers",
        "ai headlines",
        "ai rewrite",
        "ai expand",
        "ai blog seo",
    ],
    "research": [
        "research",
        "look up",
        "find out about",
        "search for",
        "investigate",
        "research url",
        "research select",
        "research analyze",
        "research sources",
        "research results",
        "deep dive",
        "research help",
        "research arxiv",
        "research scholar",
        "research wolfram",
        "arxiv search",
        "academic search",
        "find papers",
        "search papers",
    ],
    "llm_setup": [
        "install llm",
        "install ai",
        "setup llm",
        "setup ai",
        "setup ollama",
        "install ollama",
        "llm status",
        "ai status",
        "llm setup",
        "ai setup",
        "local ai",
        "get ollama",
        "enter key",
        "api key",
        "set key",
        "add key",
    ],
    "code": [
        "code",
        "coding",
        "code template",
        "code templates",
        "code stats",
        "code search",
        "code read",
        "code diff",
        "code regex",
        "code generate",
        "code explain",
        "code review",
        "code refactor",
        "code document",
        "programming",
    ],
    "style": [
        "style profile",
        "writing style",
        "my style",
        "style learn",
        "learn my style",
        "writing profile",
        "how do i write",
    ],
    "autoblog": [
        "auto blog",
        "auto-blog",
        "schedule blog",
        "blog schedule",
        "blog cron",
        "cron blog",
        "auto publish",
    ],
    "flow": [
        "flow",
        "architecture",
        "system flow",
        "show flow",
        "how does it work",
        "diagram",
    ],
}


# Patterns for detecting command chains
# Order matters - more specific patterns first
CHAIN_PATTERNS = [
    (r'\s*\|\s*', 'pipe'),              # Unix-style pipe: "crawl url | summarize"
    (r'\s*->\s*', 'pipe'),              # Arrow pipe: "crawl url -> summarize"
    (r'\s+and\s+then\s+', 'sequence'),  # "crawl url and then summarize" (must be before "then")
    (r'\s+then\s+', 'sequence'),        # "crawl url then summarize"
    (r'\s*;\s*', 'sequence'),           # Semicolon: "crawl url; summarize"
]


@dataclass
class ParsedCommand:
    """Result of parsing a user command."""
    raw_text: str
    intent: str | None = None
    confidence: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, Any] = field(default_factory=dict)
    # For command chaining
    chain_type: str | None = None  # 'pipe' or 'sequence' or None
    use_previous_output: bool = False  # True if this command should receive previous output


@dataclass
class CommandChain:
    """A chain of commands to execute in sequence."""
    commands: list[ParsedCommand]
    chain_type: str = "sequence"  # 'pipe' passes output, 'sequence' runs independently


@dataclass
class IntentPattern:
    """Pattern definition for an intent."""
    intent: str
    keywords: list[str]
    patterns: list[str]
    examples: list[str]
    slots: list[str] = field(default_factory=list)


class CommandParser:
    """
    Rule-based command parser with fuzzy matching.

    Parses user input into structured commands without any AI/ML.
    Uses keyword matching, regex, and dateparser for slot filling.
    Supports user-learned patterns from corrections.
    """

    def __init__(self, memory: Optional["Memory"] = None):
        self.intents: dict[str, IntentPattern] = {}
        self.memory = memory
        self._learned_patterns_cache: dict[str, list[dict]] = {}
        self._loaded_languages: list[str] = ["en"]
        # Instance-level copy so load_language() doesn't mutate the global
        self._phrase_variations: dict[str, list[str]] = {
            k: list(v) for k, v in PHRASE_VARIATIONS.items()
        }
        self._setup_default_intents()

    def _setup_default_intents(self) -> None:
        """Register default intent patterns."""
        default_intents = [
            IntentPattern(
                intent="reminder",
                keywords=["remind", "reminder", "remember", "alert", "notify"],
                patterns=[
                    r"remind(?:\s+me)?\s+(?:to\s+)?(.+?)(?:\s+(?:at|on|in)\s+(.+))?$",
                    r"set\s+(?:a\s+)?reminder\s+(?:for\s+)?(.+?)(?:\s+(?:at|on|in)\s+(.+))?$",
                ],
                examples=[
                    "remind me to call mom tomorrow at 3pm",
                    "set a reminder for meeting in 2 hours",
                ],
                slots=["task", "time"],
            ),
            IntentPattern(
                intent="weather",
                keywords=["weather", "temperature", "forecast", "rain", "sunny", "cold", "hot"],
                patterns=[
                    r"(?:what(?:'s| is)\s+the\s+)?weather\s+(?:in\s+)?(.+)?",
                    r"(?:is\s+it|will\s+it)\s+(?:going\s+to\s+)?(?:rain|snow|be\s+\w+)\s*(?:in\s+)?(.+)?",
                ],
                examples=[
                    "what's the weather in NYC",
                    "weather tomorrow",
                    "is it going to rain",
                ],
                slots=["location", "time"],
            ),
            IntentPattern(
                intent="summarize",
                keywords=["summarize", "summary", "tldr", "brief", "condense"],
                patterns=[
                    r"summarize\s+(.+)",
                    r"(?:give\s+me\s+)?(?:a\s+)?summary\s+of\s+(.+)",
                    r"tldr\s+(.+)",
                ],
                examples=[
                    "summarize https://example.com/article",
                    "give me a summary of this page",
                    "tldr https://news.com/story",
                ],
                slots=["target"],
            ),
            IntentPattern(
                intent="crawl",
                keywords=["crawl", "scrape", "fetch", "grab", "extract", "get links"],
                patterns=[
                    r"crawl\s+(.+)",
                    r"(?:scrape|fetch|grab)\s+(?:links\s+from\s+)?(.+)",
                    r"get\s+(?:all\s+)?links\s+from\s+(.+)",
                    r"extract\s+(?:urls|links)\s+from\s+(.+)",
                ],
                examples=[
                    "crawl https://example.com",
                    "get links from https://news.site.com",
                    "scrape https://blog.com",
                ],
                slots=["url", "depth"],
            ),
            IntentPattern(
                intent="email",
                keywords=["email", "mail", "inbox", "unread", "send email"],
                patterns=[
                    r"(?:check|show|list)\s+(?:my\s+)?(?:unread\s+)?emails?",
                    r"send\s+(?:an?\s+)?email\s+to\s+(.+)",
                    r"(?:what(?:'s| is)\s+in\s+)?my\s+inbox",
                ],
                examples=[
                    "check my email",
                    "show unread emails",
                    "send email to john@example.com",
                ],
                slots=["recipient", "subject", "body"],
            ),
            IntentPattern(
                intent="calendar",
                keywords=["calendar", "schedule", "meeting", "event", "appointment"],
                patterns=[
                    r"(?:show|what(?:'s| is))\s+(?:on\s+)?my\s+(?:calendar|schedule)",
                    r"(?:add|create|schedule)\s+(?:a\s+)?(?:meeting|event|appointment)\s+(.+)",
                    r"(?:what(?:'s| is)|do\s+i\s+have)\s+(?:happening\s+)?(?:on\s+)?(.+)",
                ],
                examples=[
                    "what's on my calendar",
                    "show my schedule for tomorrow",
                    "add meeting with Bob at 2pm",
                ],
                slots=["action", "event", "time"],
            ),
            IntentPattern(
                intent="shell",
                keywords=["run", "execute", "shell", "command", "terminal"],
                patterns=[
                    r"run\s+(?:command\s+)?[`'\"]?(.+?)[`'\"]?$",
                    r"execute\s+[`'\"]?(.+?)[`'\"]?$",
                    r"shell\s+[`'\"]?(.+?)[`'\"]?$",
                ],
                examples=[
                    "run ls -la",
                    "execute 'git status'",
                    "shell df -h",
                ],
                slots=["command"],
            ),
            IntentPattern(
                intent="files",
                keywords=["file", "files", "folder", "directory", "list", "find", "search"],
                patterns=[
                    r"(?:list|show)\s+files\s+in\s+(.+)",
                    r"find\s+(?:files?\s+)?(.+?)(?:\s+in\s+(.+))?",
                    r"search\s+(?:for\s+)?(.+?)(?:\s+in\s+(.+))?",
                ],
                examples=[
                    "list files in ~/Documents",
                    "find *.py in ~/projects",
                    "search for config files",
                ],
                slots=["pattern", "path"],
            ),
            IntentPattern(
                intent="smarthome",
                keywords=["light", "lights", "lamp", "turn on", "turn off", "dim", "bright"],
                patterns=[
                    r"turn\s+(on|off)\s+(?:the\s+)?(.+?)(?:\s+lights?)?$",
                    r"(?:set|dim)\s+(?:the\s+)?(.+?)\s+(?:lights?\s+)?(?:to\s+)?(\d+)%?",
                    r"(?:make\s+)?(?:the\s+)?(.+?)\s+(brighter|dimmer)",
                ],
                examples=[
                    "turn on living room lights",
                    "turn off bedroom",
                    "dim kitchen to 50%",
                ],
                slots=["action", "room", "level"],
            ),
            IntentPattern(
                intent="briefing",
                keywords=["briefing", "brief", "morning", "daily", "update"],
                patterns=[
                    r"(?:morning|daily|evening)\s+briefing",
                    r"(?:give\s+me\s+)?(?:my\s+)?(?:daily\s+)?(?:briefing|update|summary)",
                    r"what(?:'s| did i)\s+miss",
                ],
                examples=[
                    "morning briefing",
                    "give me my daily update",
                    "what did I miss",
                ],
                slots=[],
            ),
            IntentPattern(
                intent="help",
                keywords=["help", "commands", "what can you do", "how to"],
                patterns=[
                    r"^help$",
                    r"(?:show\s+)?(?:available\s+)?commands",
                    r"what\s+can\s+you\s+do",
                ],
                examples=[
                    "help",
                    "show commands",
                    "what can you do",
                ],
                slots=[],
            ),
            IntentPattern(
                intent="webhook",
                keywords=["webhook", "hook", "trigger", "api"],
                patterns=[
                    r"(?:create|add|set\s+up)\s+(?:a\s+)?webhook\s+(?:for\s+)?(.+)",
                    r"(?:list|show)\s+webhooks",
                    r"trigger\s+webhook\s+(.+)",
                ],
                examples=[
                    "create a webhook for deployments",
                    "list webhooks",
                    "trigger webhook build",
                ],
                slots=["name", "url", "action"],
            ),
            IntentPattern(
                intent="news",
                keywords=["news", "headlines", "feed", "feeds", "rss"],
                patterns=[
                    r"^news$",
                    r"(?:show|get|fetch)\s+(?:me\s+)?(?:the\s+)?news",
                    r"(?:show|get|fetch)\s+(?:me\s+)?(?:the\s+)?headlines",
                    r"news\s+(?:from\s+)?(\w+)",  # news tech, news world
                    r"(?:show|list)\s+(?:news\s+)?(?:categories|feeds)",
                    r"news\s+enable\s+(\w+)",
                    r"news\s+disable\s+(\w+)",
                    r"news\s+add\s+(.+)",
                    r"(?:add|import)\s+(?:rss\s+)?feed\s+(.+)",
                    r"news\s+remove\s+(.+)",
                    r"read\s+(?:article\s+)?(.+)",
                ],
                examples=[
                    "news",
                    "show me the headlines",
                    "news tech",
                    "news categories",
                    "news enable science",
                    "add feed https://blog.example.com/rss",
                    "read https://article.com/story",
                ],
                slots=["category", "subcommand", "url", "target"],
            ),
            IntentPattern(
                intent="analyze",
                keywords=["analyze", "sentiment", "keywords", "readability", "tone"],
                patterns=[
                    r"analyze\s+(?:sentiment\s+)?(?:of\s+)?(.+)",
                    r"(?:what(?:'s| is)\s+the\s+)?sentiment\s+(?:of\s+)?(.+)",
                    r"(?:extract|get)\s+keywords\s+(?:from\s+)?(.+)",
                    r"(?:check|measure)\s+readability\s+(?:of\s+)?(.+)",
                ],
                examples=[
                    "analyze sentiment of this text",
                    "what's the sentiment of this article",
                    "extract keywords from document.txt",
                    "check readability of my essay",
                ],
                slots=["target", "type"],
            ),
            IntentPattern(
                intent="document",
                keywords=["document", "pdf", "docx", "read file", "extract text"],
                patterns=[
                    r"(?:read|open|extract)\s+(?:text\s+from\s+)?(?:document\s+)?(.+\.(?:pdf|docx?|txt|md|html?))",
                    r"(?:what(?:'s| is)\s+in\s+)?(.+\.(?:pdf|docx?|txt|md|html?))",
                    r"summarize\s+(?:document\s+)?(.+\.(?:pdf|docx?))",
                ],
                examples=[
                    "read document.pdf",
                    "extract text from report.docx",
                    "what's in notes.txt",
                    "summarize paper.pdf",
                ],
                slots=["path"],
            ),
            IntentPattern(
                intent="notify",
                keywords=["notify", "notification", "alert", "desktop"],
                patterns=[
                    r"(?:send\s+)?notification\s+(.+)",
                    r"notify\s+(?:me\s+)?(?:that\s+)?(.+)",
                    r"(?:show\s+)?(?:notification\s+)?history",
                ],
                examples=[
                    "send notification Task complete",
                    "notify me that the build finished",
                    "notification history",
                ],
                slots=["message", "priority"],
            ),
            IntentPattern(
                intent="vision",
                keywords=["detect", "objects", "what's in", "identify", "yolo", "image"],
                patterns=[
                    r"(?:detect|find|identify)\s+(?:objects\s+)?(?:in\s+)?(.+\.(?:jpg|jpeg|png|gif|webp))",
                    r"what(?:'s| is)\s+in\s+(?:this\s+)?(?:image|photo|picture)\s*(.+)?",
                    r"(?:analyze|describe)\s+(?:this\s+)?(?:image|photo)\s*(.+)?",
                ],
                examples=[
                    "detect objects in photo.jpg",
                    "what's in this image",
                    "identify objects in screenshot.png",
                ],
                slots=["path"],
            ),
            IntentPattern(
                intent="ocr",
                keywords=["ocr", "extract text", "read text", "scan"],
                patterns=[
                    r"(?:ocr|scan|extract\s+text)\s+(?:from\s+)?(.+\.(?:jpg|jpeg|png|gif|webp|pdf))",
                    r"(?:read|get)\s+text\s+from\s+(?:image\s+)?(.+)",
                    r"what\s+(?:does|do)\s+(?:it|this)\s+say",
                ],
                examples=[
                    "ocr photo.jpg",
                    "extract text from screenshot.png",
                    "read text from receipt.jpg",
                ],
                slots=["path"],
            ),
            IntentPattern(
                intent="entities",
                keywords=["entities", "ner", "people", "places", "organizations", "extract names"],
                patterns=[
                    r"(?:extract|find|get)\s+(?:named\s+)?entities\s+(?:from\s+)?(.+)",
                    r"(?:who|what)\s+(?:people|organizations?|places?|locations?)\s+(?:are\s+)?(?:in|mentioned)\s+(.+)",
                    r"ner\s+(.+)",
                ],
                examples=[
                    "extract entities from article.txt",
                    "find people mentioned in document.pdf",
                    "what organizations are in this text",
                ],
                slots=["target"],
            ),
            IntentPattern(
                intent="blog",
                keywords=["blog", "blog news", "blog post", "blog entry", "publish blog",
                          "ai blog", "edit blog", "manual blog"],
                patterns=[
                    r"^blog$",
                    r"blog\s+help",
                    r"(?:write|add|post|create)\s+(?:blog\s+)?(?:news|entry|post|content)\s*(.*)",
                    r"blog\s+(?:news|write|add|post)\s*(.*)",
                    r"(?:show|list|view|read)\s+(?:my\s+)?blog",
                    r"blog\s+(?:entries|posts|list|show)",
                    r"(?:generate|create|make|suggest)\s+(?:blog\s+)?(?:title|headline)",
                    r"blog\s+title",
                    r"(?:publish|finalize|save|export)\s+(?:my\s+)?blog\s*(.*)",
                    r"(?:crawl|scrape|fetch|grab)\s+(.+?)\s+for\s+(title|body|non.?title|heading|text|content)\s*(?:content)?",
                    # Interactive flow: bare number responses when in blog session
                    r"^[12]$",
                    # AI blog commands
                    r"ai\s+blog",
                    r"blog\s+ai",
                    r"manual\s+blog",
                    r"edit\s+blog",
                    r"ai\s+(?:generate|write|create|draft|rewrite|expand|headlines?|seo|options?|providers?)",
                    r"(?:switch|use|set)\s+(?:ai\s+)?provider",
                    r"publish\s+(?:blog\s+)?to\s+",
                    r"(?:set|make|change)\s+(?:the\s+)?(?:front\s*page|home\s*page)",
                    r"(?:show|what|which)\s+(?:is\s+)?(?:the\s+)?(?:front\s*page|home\s*page)",
                    r"(?:list|show)\s+(?:publish|upload)\s*targets?",
                ],
                examples=[
                    "blog",
                    "write blog news The latest update adds crawling support.",
                    "blog news tech We added 50 new RSS feeds.",
                    "crawl https://example.com for title content",
                    "crawl https://example.com for body content",
                    "crawl https://example.com for non-title content",
                    "blog title",
                    "publish blog",
                    "show blog",
                    "blog help",
                    "ai blog generate about technology",
                    "publish blog to my-wordpress",
                ],
                slots=["content", "url", "extract_type"],
            ),
            IntentPattern(
                intent="research",
                keywords=["research", "investigate", "look up", "deep dive",
                          "arxiv", "scholar", "wolfram"],
                patterns=[
                    r"^research$",
                    r"research\s+help",
                    r"research\s+url\s+(.+)",
                    r"research\s+arxiv\s+(.+)",
                    r"research\s+scholar\s+(.+)",
                    r"research\s+wolfram\s+(.+)",
                    r"research\s+select\s+(.+)",
                    r"research\s+(?:analyze|deep)",
                    r"research\s+sources",
                    r"research\s+results",
                    r"(?:research|investigate|look\s+up|find\s+out\s+about)\s+(.+)",
                    r"(?:find|search)\s+(?:papers?|articles?)\s+(?:on|about)\s+(.+)",
                ],
                examples=[
                    "research artificial intelligence trends",
                    "research arxiv quantum computing",
                    "research scholar machine learning",
                    "research wolfram integrate x^2",
                    "research url https://example.com/article",
                    "research select 1,2,3",
                    "research analyze",
                ],
                slots=["topic", "url"],
            ),
            IntentPattern(
                intent="code",
                keywords=["code", "coding", "programming", "code template",
                          "code stats", "code search", "code generate"],
                patterns=[
                    r"^code$",
                    r"^coding$",
                    r"code\s+help",
                    r"code\s+template(?:s)?\s*(.*)",
                    r"code\s+stats\s+(.+)",
                    r"code\s+search\s+(.+)",
                    r"code\s+read\s+(.+)",
                    r"code\s+diff\s+(.+)",
                    r"code\s+regex\s+(.+)",
                    r"code\s+(?:generate|explain|review|refactor|document|doc)\s+(.+)",
                ],
                examples=[
                    "code template python-script",
                    "code stats ~/projects",
                    "code generate a REST API for user management",
                    "code review main.py",
                ],
                slots=["subcommand", "target"],
            ),
            IntentPattern(
                intent="style",
                keywords=["style", "writing style", "writing profile"],
                patterns=[
                    r"(?:style|writing)\s+profile",
                    r"(?:my|show)\s+(?:writing\s+)?style",
                    r"style\s+learn\s*(.*)",
                    r"learn\s+(?:my\s+)?(?:writing\s+)?style",
                    r"how\s+do\s+i\s+write",
                ],
                examples=[
                    "style profile",
                    "my writing style",
                    "style learn",
                ],
                slots=["text"],
            ),
            IntentPattern(
                intent="autoblog",
                keywords=["auto blog", "auto-blog", "blog schedule", "blog cron"],
                patterns=[
                    r"auto[\s-]?blog",
                    r"(?:schedule|cron)\s+blog",
                    r"blog\s+(?:schedule|cron)",
                    r"auto[\s-]?blog\s+(?:add|create|new|list|remove|show)\s*(.*)",
                ],
                examples=[
                    "auto blog",
                    "schedule blog every Monday at 9am",
                    "auto blog list",
                ],
                slots=["subcommand", "schedule"],
            ),
            IntentPattern(
                intent="flow",
                keywords=["flow", "architecture", "diagram"],
                patterns=[
                    r"^flow$",
                    r"(?:show|display)\s+(?:system\s+)?flow",
                    r"(?:system\s+)?architecture",
                    r"(?:show\s+)?diagram",
                    r"how\s+does\s+(?:it|this|safeclaw)\s+work",
                ],
                examples=[
                    "flow",
                    "show system flow",
                    "architecture",
                    "how does it work",
                ],
                slots=[],
            ),
            IntentPattern(
                intent="llm_setup",
                keywords=["install llm", "install ai", "setup llm", "setup ai",
                          "install ollama", "setup ollama", "llm status", "ai status"],
                patterns=[
                    r"install\s+(?:llm|ai|ollama)\s*(.*)",
                    r"setup\s+(?:llm|ai|ollama)\s*(.*)",
                    r"(?:llm|ai|ollama)\s+(?:status|setup|install)\s*(.*)",
                    r"(?:get|download)\s+(?:llm|ai|ollama)\s*(.*)",
                    r"local\s+ai\s*(.*)",
                ],
                examples=[
                    "install llm",
                    "install llm small",
                    "setup ai",
                    "llm status",
                    "install ollama",
                ],
                slots=["model"],
            ),
        ]

        for intent in default_intents:
            self.register_intent(intent)

    # ------------------------------------------------------------------
    # Multilingual support
    # ------------------------------------------------------------------

    def load_language(self, lang: str) -> None:
        """
        Load a language pack, merging translated keywords and phrases
        into the existing English intents.

        Keywords are appended to each IntentPattern.keywords list.
        Phrases are appended to PHRASE_VARIATIONS for fuzzy matching.

        Args:
            lang: ISO 639-1 language code (e.g. "es", "fr", "de").
        """
        if lang == "en":
            return  # English is always loaded
        if lang in self._loaded_languages:
            logger.debug(f"Language already loaded: {lang}")
            return

        pack = LANGUAGE_PACK.get(lang)
        if pack is None:
            supported = ", ".join(get_supported_languages())
            logger.warning(
                f"Unsupported language '{lang}'. Supported: {supported}"
            )
            return

        added_keywords = 0
        added_phrases = 0

        for intent_name, translation in pack.items():
            # Merge keywords into IntentPattern
            if intent_name in self.intents:
                new_kw = translation.get("keywords", [])
                existing = set(self.intents[intent_name].keywords)
                for kw in new_kw:
                    if kw not in existing:
                        self.intents[intent_name].keywords.append(kw)
                        added_keywords += 1

            # Merge phrases into instance-level phrase variations
            new_phrases = translation.get("phrases", [])
            if new_phrases:
                if intent_name not in self._phrase_variations:
                    self._phrase_variations[intent_name] = []
                existing_phrases = set(self._phrase_variations[intent_name])
                for phrase in new_phrases:
                    if phrase not in existing_phrases:
                        self._phrase_variations[intent_name].append(phrase)
                        added_phrases += 1

        self._loaded_languages.append(lang)
        lang_name = get_language_name(lang)
        logger.info(
            f"Loaded language {lang_name}: "
            f"+{added_keywords} keywords, +{added_phrases} phrases"
        )

    def load_languages(self, languages: list[str]) -> None:
        """
        Load multiple language packs at once.

        Args:
            languages: List of ISO 639-1 language codes.
        """
        for lang in languages:
            self.load_language(lang)

    def get_loaded_languages(self) -> list[str]:
        """Return the list of currently loaded language codes."""
        return list(self._loaded_languages)

    def register_intent(self, pattern: IntentPattern) -> None:
        """Register a new intent pattern."""
        self.intents[pattern.intent] = pattern
        logger.debug(f"Registered intent: {pattern.intent}")

    def parse(self, text: str, user_id: str | None = None) -> ParsedCommand:
        """
        Parse user input into a structured command.

        Returns ParsedCommand with intent, confidence, and extracted params.
        Automatically normalizes input (word-to-number, typo correction).

        Args:
            text: User input to parse
            user_id: Optional user ID for checking learned patterns
        """
        text = text.strip()
        result = ParsedCommand(raw_text=text)

        if not text:
            return result

        # Smart normalization: fix typos, convert word-numbers
        text = normalize_text(text)

        # Normalize text
        normalized = text.lower()

        # 1. Check learned patterns first (user corrections have highest priority)
        if user_id and user_id in self._learned_patterns_cache:
            learned_match = self._match_learned_patterns(normalized, user_id)
            if learned_match:
                result.intent = learned_match["intent"]
                result.confidence = 0.98  # Very high - user explicitly corrected this
                result.params = learned_match.get("params") or {}
                result.entities = self._extract_entities(text)
                logger.debug(f"Matched learned pattern: '{text}' -> {result.intent}")
                return result

        # 2. Check phrase variations (fuzzy match against common phrases)
        phrase_match = self._match_phrase_variations(normalized)
        if phrase_match and phrase_match[1] >= 0.85:
            result.intent = phrase_match[0]
            result.confidence = phrase_match[1]

            intent_pattern = self.intents[result.intent]
            result.params = self._extract_params(text, intent_pattern)
            result.entities = self._extract_entities(text)
            return result

        # 3. Fall back to keyword/pattern matching
        best_match = self._match_keywords(normalized)

        if best_match:
            result.intent = best_match[0]
            result.confidence = best_match[1]

            # Extract params using regex patterns
            intent_pattern = self.intents[result.intent]
            result.params = self._extract_params(text, intent_pattern)
            result.entities = self._extract_entities(text)

        return result

    def _match_keywords(self, text: str) -> tuple[str, float] | None:
        """Match text against intent keywords using fuzzy matching.

        Keyword specificity (length relative to input) is factored into the
        score so that longer, more-specific keyword matches beat shorter
        substring hits (e.g. "nachrichten" beats "nachricht").
        """
        best_intent = None
        best_score = 0.0

        words = text.split()

        for intent_name, pattern in self.intents.items():
            # Check for keyword matches
            for keyword in pattern.keywords:
                # Exact match in text (substring)
                if keyword in text:
                    # Score scales with keyword specificity: longer keywords
                    # that cover more of the input score higher (0.85 – 0.95).
                    specificity = len(keyword) / max(len(text), 1)
                    score = 0.85 + 0.10 * min(specificity, 1.0)
                    if score > best_score:
                        best_score = score
                        best_intent = intent_name
                    continue

                # Fuzzy match against words
                for word in words:
                    ratio = fuzz.ratio(keyword, word) / 100.0
                    if ratio > 0.8 and ratio > best_score:
                        best_score = ratio
                        best_intent = intent_name

            # Check regex patterns
            for regex in pattern.patterns:
                if re.search(regex, text, re.IGNORECASE):
                    score = 0.95
                    if score > best_score:
                        best_score = score
                        best_intent = intent_name

        if best_intent and best_score >= 0.6:
            return (best_intent, best_score)

        return None

    def _extract_params(self, text: str, pattern: IntentPattern) -> dict[str, Any]:
        """Extract parameters from text using regex patterns."""
        params: dict[str, Any] = {}

        for regex in pattern.patterns:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                # Map groups to slots
                for i, slot in enumerate(pattern.slots):
                    if i < len(groups) and groups[i]:
                        params[slot] = groups[i].strip()
                break

        return params

    def _extract_entities(self, text: str) -> dict[str, Any]:
        """Extract common entities (dates, times, URLs, emails)."""
        entities: dict[str, Any] = {}

        # Extract URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        if urls:
            entities["urls"] = urls

        # Extract emails
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)
        if emails:
            entities["emails"] = emails

        # Extract dates/times using dateparser
        # Remove URLs first to avoid confusion
        text_no_urls = re.sub(url_pattern, '', text)
        parsed_date = dateparser.parse(
            text_no_urls,
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(),
            }
        )
        if parsed_date:
            entities["datetime"] = parsed_date

        # Extract numbers
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', text)
        if numbers:
            entities["numbers"] = [float(n) if '.' in n else int(n) for n in numbers]

        return entities

    def get_intents(self) -> list[str]:
        """Return list of registered intent names."""
        return list(self.intents.keys())

    def get_examples(self, intent: str) -> list[str]:
        """Return example phrases for an intent."""
        if intent in self.intents:
            return self.intents[intent].examples
        return []

    def _match_phrase_variations(self, text: str) -> tuple[str, float] | None:
        """
        Match text against common phrase variations using fuzzy matching.

        This provides day-one natural language understanding without training.
        Uses instance-level phrase variations so multilingual additions are
        isolated per parser instance.
        """
        best_intent = None
        best_score = 0.0

        for intent, phrases in self._phrase_variations.items():
            if intent not in self.intents:
                continue

            for phrase in phrases:
                # Check if phrase is contained in text
                if phrase in text:
                    # For single-word ASCII phrases, require word-boundary
                    # match to prevent "cli" from matching inside "clima".
                    if " " not in phrase and phrase.isascii() and len(phrase) < len(text):
                        idx = text.index(phrase)
                        before_ok = (idx == 0) or not text[idx - 1].isalnum()
                        end = idx + len(phrase)
                        after_ok = (end == len(text)) or not text[end].isalnum()
                        if not (before_ok and after_ok):
                            continue

                    # Prefer longer phrase matches: "style learn" should beat
                    # a bare "code" found later in the text.
                    specificity = len(phrase) / max(len(text), 1)
                    score = 0.92 + 0.05 * min(specificity, 1.0)
                    if score > best_score:
                        best_score = score
                        best_intent = intent
                    continue

                # Fuzzy match - require text to be at least 70% as long as
                # phrase to prevent short inputs matching inside long phrases
                # (e.g. "help" perfectly matching inside "blog help").
                if len(text) >= len(phrase) * 0.7:
                    ratio = fuzz.partial_ratio(phrase, text) / 100.0
                    if ratio > 0.85 and ratio > best_score:
                        best_score = ratio
                        best_intent = intent

        if best_intent and best_score >= 0.85:
            return (best_intent, best_score)

        return None

    def _match_learned_patterns(
        self, text: str, user_id: str
    ) -> dict[str, Any] | None:
        """
        Match text against user's learned patterns using fuzzy matching.

        Returns the best matching pattern if found with high confidence.
        """
        if user_id not in self._learned_patterns_cache:
            return None

        patterns = self._learned_patterns_cache[user_id]
        if not patterns:
            return None

        best_match = None
        best_score = 0.0

        for pattern in patterns:
            phrase = pattern["phrase"]

            # Exact match (normalized)
            if text == phrase:
                return pattern

            # Fuzzy match - higher threshold for learned patterns
            ratio = fuzz.ratio(phrase, text) / 100.0
            if ratio > 0.90 and ratio > best_score:
                best_score = ratio
                best_match = pattern

        return best_match

    async def load_user_patterns(self, user_id: str) -> None:
        """
        Load learned patterns for a user from memory.

        Call this when a user session starts to enable learned pattern matching.
        """
        if not self.memory:
            return

        patterns = await self.memory.get_user_patterns(user_id)
        self._learned_patterns_cache[user_id] = patterns
        logger.debug(f"Loaded {len(patterns)} learned patterns for user {user_id}")

    async def learn_correction(
        self,
        user_id: str,
        phrase: str,
        correct_intent: str,
        params: dict | None = None,
    ) -> None:
        """
        Learn a correction from user feedback.

        When a user says "I meant X" or corrects a misunderstood command,
        store the mapping so future similar phrases match correctly.

        Args:
            user_id: User who made the correction
            phrase: The original phrase that was misunderstood
            correct_intent: The intent the user actually wanted
            params: Optional parameters for the intent
        """
        if not self.memory:
            logger.warning("Cannot learn correction: no memory configured")
            return

        # Store in database
        await self.memory.learn_pattern(user_id, phrase, correct_intent, params)

        # Update cache
        if user_id not in self._learned_patterns_cache:
            self._learned_patterns_cache[user_id] = []

        # Check if already in cache and update, or add new
        normalized = phrase.lower().strip()
        for existing in self._learned_patterns_cache[user_id]:
            if existing["phrase"] == normalized:
                existing["intent"] = correct_intent
                existing["params"] = params
                existing["use_count"] = existing.get("use_count", 0) + 1
                logger.info(f"Updated learned pattern: '{phrase}' -> {correct_intent}")
                return

        # Add new pattern to cache
        self._learned_patterns_cache[user_id].append({
            "phrase": normalized,
            "intent": correct_intent,
            "params": params,
            "use_count": 1,
        })
        logger.info(f"Learned new pattern: '{phrase}' -> {correct_intent}")

    def _detect_chain(self, text: str) -> tuple[str, str] | None:
        """
        Detect if text contains a command chain pattern.

        Returns tuple of (pattern, chain_type) or None if no chain detected.
        """
        for pattern, chain_type in CHAIN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return (pattern, chain_type)
        return None

    def _split_chain(self, text: str) -> tuple[list[str], str]:
        """
        Split text into chain segments.

        Returns tuple of (segments, chain_type).
        """
        # Try each pattern in order
        for pattern, chain_type in CHAIN_PATTERNS:
            parts = re.split(pattern, text, flags=re.IGNORECASE)
            if len(parts) > 1:
                # Clean up parts and filter empty ones
                segments = [p.strip() for p in parts if p.strip()]
                if len(segments) > 1:
                    return (segments, chain_type)

        # No chain found - return single segment
        return ([text], "none")

    def parse_chain(
        self, text: str, user_id: str | None = None
    ) -> CommandChain:
        """
        Parse a potentially chained command.

        Supports:
        - Pipes: "crawl url | summarize" - passes output to next command
        - Arrows: "crawl url -> summarize" - same as pipe
        - Sequence: "check email; remind me to reply" - runs independently
        - Natural: "crawl url and then summarize it" - contextual chaining

        Args:
            text: User input that may contain multiple chained commands
            user_id: Optional user ID for learned pattern matching

        Returns:
            CommandChain with list of ParsedCommands
        """
        text = normalize_text(text.strip())

        # Split into segments
        segments, chain_type = self._split_chain(text)

        if len(segments) == 1:
            # Single command - no chaining
            cmd = self.parse(text, user_id)
            return CommandChain(commands=[cmd], chain_type="none")

        # Parse each segment
        commands: list[ParsedCommand] = []
        for i, segment in enumerate(segments):
            cmd = self.parse(segment, user_id)

            # Mark chain info
            cmd.chain_type = chain_type if i < len(segments) - 1 else None

            # For pipes, subsequent commands use previous output
            if chain_type == "pipe" and i > 0:
                cmd.use_previous_output = True
                # Handle implicit targets like "summarize it", "summarize that"
                if not cmd.params.get("target") and not cmd.entities.get("urls"):
                    cmd.params["_use_previous"] = True

            commands.append(cmd)

        logger.debug(f"Parsed chain with {len(commands)} commands ({chain_type})")
        return CommandChain(commands=commands, chain_type=chain_type)

    def is_chain(self, text: str) -> bool:
        """Check if text contains a command chain."""
        return self._detect_chain(text) is not None
