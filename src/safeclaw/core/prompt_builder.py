"""
SafeClaw Dynamic Prompt Builder - Non-deterministic system prompts.

Builds context-aware system prompts by combining:
- User's writing style profile (from fuzzy learning)
- Task type (blog, research, coding, general)
- User preferences
- Current context (time of day, topic, audience)

Also provides a visual flow diagram showing where data flows through the system.

The prompts are "non-deterministic" because they change based on learned
user behavior, context, and accumulated preferences - not static templates.
"""

import logging
from datetime import datetime
from typing import Any

from safeclaw.core.writing_style import WritingProfile

logger = logging.getLogger(__name__)


# ── Flow Diagram ─────────────────────────────────────────────────────────────

SYSTEM_FLOW_DIAGRAM = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                        SafeClaw 100-Star Architecture                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────┐     ┌──────────────┐     ┌──────────────────────────────┐   ║
║  │  User Input  │────▶│ Command      │────▶│        Action Router         │ ║
║  │  (any channel│     │ Parser       │     │  (blog/research/code/...)    │  ║
║  │  CLI/TG/Web) │     │ (fuzzy match)│     └──────────┬───────────────────┘  ║
║  └─────────────┘     └──────────────┘                │                       ║
║                                                       ▼                      ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │                    Per-Task LLM Router                                 │  ║
║  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌─────────────────────┐  │    ║
║  │  │ Blogging  │  │ Research  │  │  Coding  │  │  General / Custom   │  │   ║
║  │  │ LLM      │  │ LLM       │  │ LLM      │  │  LLM                │  │    ║
║  │  └─────┬────┘  └─────┬─────┘  └────┬─────┘  └──────────┬──────────┘  │    ║
║  └────────┼─────────────┼─────────────┼────────────────────┼─────────────┘   ║
║           │             │             │                    │                 ║
║           ▼             ▼             ▼                    ▼                 ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │              Dynamic Prompt Builder (this module)                    │    ║
║  │  ┌───────────────┐ ┌────────────┐ ┌──────────┐ ┌───────────────┐  │       ║
║  │  │Writing Profile│ │  Context   │ │   User   │ │  Task-Specific│  │       ║
║  │  │(fuzzy learned)│ │ (time/topic│ │  Prefs   │ │  Instructions │  │       ║
║  │  └───────┬───────┘ │ /audience) │ └────┬─────┘ └───────┬───────┘  │       ║
║  │          └─────────┴────────────┴──────┴───────────────┘           │      ║
║  │                            │                                        │     ║
║  │                   Combined System Prompt                            │     ║
║  └────────────────────────────┼────────────────────────────────────────┘     ║
║                               ▼                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │                     Non-LLM Pipeline (always available)             │     ║
║  │  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────────────┐   │       ║
║  │  │Summarizer│ │ Crawler  │ │  Analyzer  │ │  Cron Scheduler   │   │       ║
║  │  │ (sumy)   │ │ (httpx)  │ │  (VADER)   │ │  (APScheduler)    │   │       ║
║  │  └──────────┘ └──────────┘ └────────────┘ └───────────────────┘   │       ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                               │                                              ║
║                               ▼                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │                        Research Pipeline                            │     ║
║  │                                                                     │     ║
║  │  Web Search ──▶ Sumy Summarize ──▶ Source Selection ──▶ LLM Deep   │    ║
║  │  (non-LLM)     (non-LLM)          (user picks)         Research    │      ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                               │                                              ║
║                               ▼                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │                     Cron Auto-Blog Pipeline                         │     ║
║  │                                                                     │     ║
║  │  Schedule ──▶ Fetch Sources ──▶ Sumy Extract ──▶ Format ──▶ Publish │   ║
║  │  (cron)      (RSS/crawl)       (no LLM)        (template)  (target)│      ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                               │                                              ║
║                               ▼                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │                    Output / Publishing                              │     ║
║  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ ┌───────────┐  │        ║
║  │  │WordPress │ │  Joomla  │ │  SFTP  │ │ API/Hook│ │ Local File│  │        ║
║  │  └──────────┘ └──────────┘ └────────┘ └─────────┘ └───────────┘  │        ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │                    Memory / Learning Layer                          │     ║
║  │  ┌──────────────┐ ┌────────────────┐ ┌─────────────────────────┐  │       ║
║  │  │ SQLite Store  │ │ Writing Style  │ │ Command Corrections     │  │      ║
║  │  │ (all history) │ │ Profile (fuzzy)│ │ (learned patterns)      │  │      ║
║  │  └──────────────┘ └────────────────┘ └─────────────────────────┘  │       ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


class PromptBuilder:
    """
    Builds context-aware, non-deterministic system prompts.

    Combines user writing profile, task context, and preferences
    into a tailored system prompt for each LLM call.
    """

    # Base role descriptions per task type
    TASK_ROLES = {
        "blog": (
            "You are a skilled blog writer. "
            "Write clear, engaging, well-structured content."
        ),
        "research": (
            "You are a thorough research analyst. "
            "Provide detailed, well-sourced analysis with clear conclusions."
        ),
        "coding": (
            "You are an expert programmer. "
            "Write clean, well-documented, production-ready code. "
            "Explain your approach concisely."
        ),
        "general": (
            "You are a helpful, knowledgeable assistant. "
            "Be concise and accurate."
        ),
    }

    def __init__(self):
        pass

    def build(
        self,
        task: str = "blog",
        writing_profile: WritingProfile | None = None,
        topic: str = "",
        audience: str = "",
        extra_instructions: str = "",
        user_prefs: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a complete system prompt for an LLM call.

        This prompt is "non-deterministic" because it changes based on:
        - The user's learned writing style (evolves over time)
        - The specific task and topic
        - Time of day and context
        - User preferences that accumulate

        Args:
            task: Task type (blog, research, coding, general)
            writing_profile: User's writing style profile (from fuzzy learning)
            topic: The topic being worked on
            audience: Target audience description
            extra_instructions: Additional user-specified instructions
            user_prefs: User preferences dict

        Returns:
            Complete system prompt string
        """
        user_prefs = user_prefs or {}
        sections = []

        # 1. Base role
        role = self.TASK_ROLES.get(task, self.TASK_ROLES["general"])
        sections.append(role)

        # 2. Writing style instructions (from fuzzy learning)
        if writing_profile and writing_profile.samples_analyzed > 0:
            style_instructions = writing_profile.to_prompt_instructions()
            if style_instructions:
                sections.append(
                    f"\nMatch this writing style (learned from the user's actual writing):\n"
                    f"{style_instructions}"
                )

        # 3. Topic context
        if topic:
            sections.append(f"\nTopic: {topic}")

        # 4. Audience
        if audience:
            sections.append(f"Target audience: {audience}")

        # 5. Time-of-day context
        hour = datetime.now().hour
        if task == "blog":
            if hour < 6:
                sections.append("Note: Writing late at night — keep it concise.")
            elif hour < 12:
                sections.append("Note: Morning writing session — fresh and energetic tone.")

        # 6. User preferences
        if user_prefs:
            tone = user_prefs.get("tone")
            if tone:
                sections.append(f"Preferred tone: {tone}")

            word_count = user_prefs.get("target_word_count")
            if word_count:
                sections.append(f"Target length: approximately {word_count} words.")

            avoid_topics = user_prefs.get("avoid_topics")
            if avoid_topics:
                sections.append(f"Avoid discussing: {', '.join(avoid_topics)}")

        # 7. Task-specific additions
        if task == "blog":
            sections.append(
                "\nFormat the output as a complete blog post with title, "
                "introduction, body sections, and conclusion."
            )
        elif task == "research":
            sections.append(
                "\nProvide your analysis with:\n"
                "- Key findings\n"
                "- Supporting evidence\n"
                "- Implications\n"
                "- Areas needing further investigation"
            )
        elif task == "coding":
            lang = user_prefs.get("preferred_language", "")
            if lang:
                sections.append(f"Write code in {lang}.")
            sections.append(
                "\nInclude comments explaining complex logic. "
                "Handle edge cases appropriately."
            )

        # 8. Extra instructions (highest priority, always last)
        if extra_instructions:
            sections.append(f"\nAdditional instructions: {extra_instructions}")

        return "\n".join(sections)

    @staticmethod
    def get_flow_diagram() -> str:
        """Return the system architecture flow diagram."""
        return SYSTEM_FLOW_DIAGRAM
