"""
Blog action - AI-powered blogging with multi-platform publishing.

Combines the original extractive-summarization blog (no AI required)
with optional generative AI from multiple providers and publishing
to WordPress, Joomla, SFTP, and generic APIs.

Features:
- Write blog entries manually (original, no AI)
- Generate blog posts with AI (Ollama, OpenAI, Claude, Gemini, etc.)
- Rewrite/expand content with AI
- Crawl websites for content
- Publish to WordPress (REST API v2 - native)
- Publish to Joomla (Web Services API - native)
- Upload via SFTP to any server
- Publish via generic API/webhook
- Front page management (specify which post is the home page)
- Multiple AI API keys and publishing targets
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import yaml

from safeclaw.actions.base import BaseAction
from safeclaw.core.ai_writer import AIWriter, load_ai_writer_from_yaml
from safeclaw.core.blog_publisher import BlogPublisher, PublishTarget, PublishTargetType
from safeclaw.core.crawler import Crawler
from safeclaw.core.frontpage import FrontPageManager
from safeclaw.core.summarizer import Summarizer

if TYPE_CHECKING:
    from safeclaw.core.engine import SafeClaw

logger = logging.getLogger(__name__)


# Session states for the interactive blog flow
SESSION_AWAITING_CHOICE = "awaiting_choice"
SESSION_AWAITING_TOPIC = "awaiting_topic"
SESSION_REVIEWING = "reviewing"
SESSION_PENDING_PUBLISH = "pending_publish"


class BlogAction(BaseAction):
    """
    AI-powered blogging with multi-platform publishing.

    Original features (no AI):
    - Write blog news entries
    - Crawl websites for content (titles, body, non-title)
    - Auto-generate blog titles from summarized content
    - Output as plain .txt

    AI features (optional):
    - Generate full blog posts from a topic
    - Rewrite/expand existing content
    - Generate headlines and SEO metadata
    - Multiple AI provider support (local + cloud)

    Publishing (optional):
    - WordPress REST API (native)
    - Joomla Web Services API (native)
    - SFTP upload (any server)
    - Generic API/webhook

    Front page:
    - Set which post is the front/home page
    - Works with WordPress, Joomla, and SFTP
    """

    name = "blog"
    description = "AI-powered blogging with multi-platform publishing"

    def __init__(self, blog_dir: Path | None = None):
        self.blog_dir = blog_dir or Path.home() / ".safeclaw" / "blogs"
        self.blog_dir.mkdir(parents=True, exist_ok=True)
        self.summarizer = Summarizer()
        self.ai_writer: AIWriter | None = None
        self.publisher: BlogPublisher | None = None
        self.frontpage: FrontPageManager | None = None
        self._initialized = False
        self._sessions_dir = self.blog_dir / ".sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_initialized(self, engine: "SafeClaw") -> None:
        """Lazy-initialize AI writer, publisher, and front page manager from config."""
        if self._initialized:
            return
        self._initialized = True

        config = engine.config

        # Initialize AI writer
        if config.get("ai_providers"):
            self.ai_writer = load_ai_writer_from_yaml(config)

            # Apply per-task routing: use blog-specific provider if configured
            task_providers = config.get("task_providers", {})
            blog_provider = task_providers.get("blog")
            if blog_provider and blog_provider in self.ai_writer.providers:
                self.ai_writer.set_active_provider(blog_provider)
                logger.info(f"Blog using task-specific provider: {blog_provider}")

            logger.info(
                f"AI writer initialized with {len(self.ai_writer.providers)} provider(s)"
            )

        # Initialize publisher
        if config.get("publish_targets"):
            self.publisher = BlogPublisher.from_config(config)
            logger.info(
                f"Publisher initialized with {len(self.publisher.targets)} target(s)"
            )

            # Initialize front page manager
            self.frontpage = FrontPageManager(
                publisher=self.publisher,
                state_dir=Path.home() / ".safeclaw" / "frontpage",
            )

    # ── Session state management ───────────────────────────────────────────

    def _get_session_path(self, user_id: str) -> Path:
        """Get the session state file path for a user."""
        safe_id = re.sub(r'[^\w]', '_', user_id)
        return self._sessions_dir / f"session-{safe_id}.json"

    def _get_session(self, user_id: str) -> dict[str, Any]:
        """Load session state for a user."""
        path = self._get_session_path(user_id)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _set_session(self, user_id: str, state: str, **data: Any) -> None:
        """Save session state for a user."""
        path = self._get_session_path(user_id)
        session = {"state": state, **data}
        path.write_text(json.dumps(session))

    def _clear_session(self, user_id: str) -> None:
        """Clear session state for a user."""
        path = self._get_session_path(user_id)
        path.unlink(missing_ok=True)

    # ── Main execute with interactive flow ───────────────────────────────────

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafeClaw",
    ) -> str:
        """Execute blog action based on natural language input."""
        self._ensure_initialized(engine)
        raw_input = params.get("raw_input", "").strip()
        lower = raw_input.lower()

        # ── Check session state FIRST (for interactive flow) ─────────────
        session = self._get_session(user_id)
        session_state = session.get("state")

        if session_state:
            result = await self._handle_session(
                session, raw_input, lower, user_id, engine,
            )
            if result is not None:
                return result
            # If _handle_session returns None, fall through to normal routing

        # ── Bare "blog" → show interactive menu ──────────────────────────
        if self._is_bare_blog(lower):
            return self._show_blog_menu(user_id)

        # ── Edit blog command ────────────────────────────────────────────
        if self._is_edit_blog(lower):
            return await self._edit_blog(raw_input, user_id)

        # ── Route based on natural language ──────────────────────────────
        if self._is_help(lower):
            return self._help_text()

        # AI commands
        if self._is_ai_generate(lower):
            return await self._ai_generate(raw_input, user_id, engine)
        if self._is_ai_rewrite(lower):
            return await self._ai_rewrite(raw_input, user_id)
        if self._is_ai_expand(lower):
            return await self._ai_expand(raw_input, user_id)
        if self._is_ai_headlines(lower):
            return await self._ai_headlines(user_id)
        if self._is_ai_seo(lower):
            return await self._ai_seo(user_id)
        if self._is_ai_info(lower):
            return self._ai_info()
        if self._is_ai_providers(lower):
            return self._ai_providers_info()
        if self._is_ai_switch(lower):
            return self._ai_switch_provider(raw_input)

        # Publishing commands
        if self._is_setup_publish(lower):
            return await self._setup_publish(raw_input, user_id, engine)
        if self._is_publish_remote(lower):
            return await self._publish_remote(raw_input, user_id)
        if self._is_list_targets(lower):
            return self._list_publish_targets()

        # Front page commands
        if self._is_set_front_page(lower):
            return await self._set_front_page(raw_input, user_id)
        if self._is_show_front_page(lower):
            return self._show_front_page()
        if self._is_list_pages(lower):
            return await self._list_pages(raw_input)

        # Original (non-AI) commands
        if self._is_crawl_blog(lower):
            return await self._crawl_for_blog(raw_input, user_id, engine)
        if self._is_write(lower):
            return await self._write_blog_news(raw_input, user_id, engine)
        if self._is_show(lower):
            return self._show_blogs(user_id)
        if self._is_generate_title(lower):
            return self._generate_title(user_id)
        if self._is_publish(lower):
            return self._publish_blog(raw_input, user_id)

        # Default: treat as writing blog news
        content = self._extract_blog_content(raw_input)
        if content:
            return await self._write_blog_news(raw_input, user_id, engine)

        return self._help_text()

    # ── Interactive flow ─────────────────────────────────────────────────────

    def _is_bare_blog(self, text: str) -> bool:
        """Check if user typed just 'blog' with no other arguments."""
        return text.strip() in ("blog", "blog ai", "ai blog", "manual blog")

    def _is_edit_blog(self, text: str) -> bool:
        """Check if user wants to edit their blog draft."""
        return bool(re.search(r"^edit\s+blog\s*", text))

    def _show_blog_menu(self, user_id: str) -> str:
        """Show the interactive blog menu when user types 'blog'."""
        self._set_session(user_id, SESSION_AWAITING_CHOICE)

        # Check for existing draft
        draft_path = self._get_draft_path(user_id)
        draft_info = ""
        if draft_path.exists():
            entry_count = self._count_entries(draft_path)
            if entry_count > 0:
                draft_info = f"\n  You have a draft in progress ({entry_count} entries).\n"

        # Build AI provider info
        ai_status = ""
        if self.ai_writer and self.ai_writer.providers:
            active = self.ai_writer.get_active_provider()
            if active:
                ai_status = f" [{active.provider.value}/{active.model}]"
        else:
            ai_status = " [setup needed - type 'ai options']"

        return (
            "**What would you like to do?**\n"
            f"{draft_info}\n"
            "  **1. AI Blog for You (Recommended)**\n"
            f"     AI writes a full blog post for you. You can edit it after.{ai_status}\n"
            "\n"
            "  **2. Manual Blogging (No AI)**\n"
            "     Write entries yourself, crawl sites for content.\n"
            "     SafeClaw generates titles using extractive summarization.\n"
            "\n"
            "Type **1** or **2** to choose."
        )

    async def _handle_session(
        self,
        session: dict[str, Any],
        raw_input: str,
        lower: str,
        user_id: str,
        engine: "SafeClaw",
    ) -> str | None:
        """
        Handle input based on active session state.

        Returns a response string, or None to fall through to normal routing.
        """
        state = session.get("state", "")

        # If user types a specific command, let normal routing handle it
        # (only intercept bare numbers and free-text during active sessions)
        if self._is_explicit_command(lower):
            self._clear_session(user_id)
            return None

        if state == SESSION_AWAITING_CHOICE:
            return await self._handle_choice(lower, user_id, engine)

        elif state == SESSION_AWAITING_TOPIC:
            return await self._handle_topic(raw_input, user_id, engine)

        elif state == SESSION_REVIEWING:
            return await self._handle_review(raw_input, lower, user_id, engine)

        elif state == SESSION_PENDING_PUBLISH:
            return await self._handle_pending_publish(session, raw_input, lower, user_id)

        return None

    def _is_explicit_command(self, text: str) -> bool:
        """Check if input is an explicit command (not a session response)."""
        # These are commands that should bypass the session and go through normal routing
        explicit_patterns = [
            r"blog\s+help", r"help\s+blog",
            r"show\s+blog", r"list\s+blog",
            r"publish\s+blog\s+to\s+",
            r"set\s+front",
            r"ai\s+(options|providers|switch)",
            r"(switch|use|set)\s+ai\s+provider",
            r"crawl\s+",
            r"^quit$", r"^exit$",
        ]
        return any(re.search(p, text) for p in explicit_patterns)

    async def _handle_choice(self, lower: str, user_id: str, engine: "SafeClaw") -> str | None:
        """Handle response to the blog menu (awaiting_choice state)."""
        choice = lower.strip()

        if choice == "1":
            # User chose AI blogging
            if not self.ai_writer or not self.ai_writer.providers:
                self._clear_session(user_id)
                return (
                    "AI blogging requires an AI provider.\n\n"
                    + AIWriter.get_local_ai_info()
                    + "\n\nAfter setting up a provider in config/config.yaml, type **blog** to try again."
                )

            active = self.ai_writer.get_active_provider()
            provider_info = f" using {active.provider.value}/{active.model}" if active else ""

            self._set_session(user_id, SESSION_AWAITING_TOPIC)

            return (
                f"**AI Blog{provider_info}**\n"
                "\n"
                "What should the blog post be about?\n"
                "\n"
                "Type your topic. Examples:\n"
                "  sustainable technology trends in 2026\n"
                "  why privacy-first tools are the future\n"
                "  a beginner's guide to home automation\n"
                "\n"
                "Type your topic now:"
            )

        elif choice == "2":
            # User chose manual blogging
            self._clear_session(user_id)

            draft_path = self._get_draft_path(user_id)
            draft_info = ""
            if draft_path.exists():
                entry_count = self._count_entries(draft_path)
                if entry_count > 0:
                    draft_info = f"\nYou have a draft with {entry_count} entries. Continue adding to it.\n"

            return (
                "**Manual Blogging (No AI)**\n"
                f"{draft_info}\n"
                "Write blog entries and crawl websites for content.\n"
                "SafeClaw generates titles using extractive summarization.\n"
                "\n"
                "**Get started:**\n"
                "  write blog news <your content here>\n"
                "  crawl https://example.com for title content\n"
                "  crawl https://example.com for body content\n"
                "\n"
                "**When ready:**\n"
                "  blog title      - Generate a title from your entries\n"
                "  publish blog    - Save as .txt\n"
                "  show blog       - View your draft and published posts"
            )

        # Not a valid choice - remind them
        return (
            "Please type **1** for AI blogging or **2** for manual blogging.\n"
            "\n"
            "  **1** - AI Blog for You (Recommended)\n"
            "  **2** - Manual Blogging (No AI)"
        )

    async def _handle_topic(
        self, raw_input: str, user_id: str, engine: "SafeClaw"
    ) -> str | None:
        """Handle topic input for AI blog generation (awaiting_topic state)."""
        topic = re.sub(r'(?i)^please\s+', '', raw_input).strip()

        if not topic:
            return "Please type a topic for your blog post:"

        if topic.lower() in ("cancel", "back", "nevermind", "0"):
            self._clear_session(user_id)
            return "Cancelled. Type **blog** to start over."

        # Generate the blog post
        draft_path = self._get_draft_path(user_id)
        context = ""
        if draft_path.exists():
            context = self._get_entries_text(draft_path.read_text())

        response = await self.ai_writer.generate_blog(topic, context)

        if response.error:
            self._clear_session(user_id)
            return f"AI generation failed: {response.error}\n\nType **blog** to try again."

        # Save generated content to draft
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n[{timestamp}] AI-generated ({response.provider}/{response.model})\n{response.content}\n"

        with open(draft_path, "a") as f:
            f.write(entry)

        # Switch to reviewing state
        self._set_session(user_id, SESSION_REVIEWING)

        tokens_info = f" ({response.tokens_used} tokens)" if response.tokens_used else ""

        # Show the full content for review
        content_preview = response.content
        if len(content_preview) > 1500:
            content_preview = content_preview[:1500] + "\n\n... [truncated - full content saved to draft]"

        return (
            f"**AI-Generated Blog Post**\n"
            f"Provider: {response.provider}/{response.model}{tokens_info}\n"
            "\n"
            "---\n"
            f"\n{content_preview}\n\n"
            "---\n"
            "\n"
            "**What would you like to do?**\n"
            "\n"
            "  **edit blog** <your changes>               - Replace with your edits\n"
            "  **ai rewrite blog**                        - Have AI polish/rewrite it\n"
            "  **ai expand blog**                         - Have AI make it longer\n"
            "  **ai headlines**                           - Generate headline options\n"
            "  **publish blog**                           - Save as .txt locally\n"
            "  **publish blog to wp://site.com u pass**   - Publish (shows preview first)\n"
            "  **publish blog to <saved-target>**         - Publish to configured target\n"
            "  **blog**                                   - Start over\n"
            "\n"
            "Or just type more text to add to the draft."
        )

    async def _handle_review(
        self,
        raw_input: str,
        lower: str,
        user_id: str,
        engine: "SafeClaw",
    ) -> str | None:
        """Handle input during the review state (after AI generates content)."""
        # If user types just text (not a command), treat as adding to draft
        if not self._looks_like_command(lower):
            # Append the user's text to the draft
            draft_path = self._get_draft_path(user_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"\n[{timestamp}] user edit\n{raw_input}\n"

            with open(draft_path, "a") as f:
                f.write(entry)

            entry_count = self._count_entries(draft_path)

            return (
                f"Added to draft ({entry_count} entries).\n\n"
                "Continue editing, or:\n"
                "  **publish blog**              - Save as .txt\n"
                "  **publish blog to <target>**  - Publish remotely\n"
                "  **ai rewrite blog**           - AI polish\n"
                "  **show blog**                 - See full draft"
            )

        # It's a command - clear session and fall through to normal routing
        self._clear_session(user_id)
        return None

    def _looks_like_command(self, text: str) -> bool:
        """Check if text looks like a SafeClaw command rather than content."""
        command_starts = [
            "blog", "publish", "show", "list", "view", "read",
            "ai ", "edit ", "crawl", "write", "add ", "post ",
            "create ", "generate", "suggest", "set ", "make ",
            "switch", "use ", "cancel", "back", "help",
        ]
        return any(text.startswith(prefix) for prefix in command_starts)

    async def _edit_blog(self, raw_input: str, user_id: str) -> str:
        """Edit/replace the blog draft content."""
        # Extract the new content
        new_content = re.sub(r'(?i)^edit\s+blog\s*', '', raw_input).strip()

        draft_path = self._get_draft_path(user_id)

        if not new_content:
            # Show current draft for reference
            if draft_path.exists():
                content = self._get_entries_text(draft_path.read_text())
                preview = content[:1000]
                if len(content) > 1000:
                    preview += "\n\n... [truncated]"
                return (
                    "**Current draft:**\n"
                    f"\n{preview}\n\n"
                    "To replace the draft, type:\n"
                    "  edit blog <your new content here>\n\n"
                    "Or type text to add to the draft."
                )
            return "No draft found. Type **blog** to start."

        # Replace the entire draft with new content
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_draft = f"[{timestamp}] user edit\n{new_content}\n"
        draft_path.write_text(new_draft)

        preview = new_content[:500]
        if len(new_content) > 500:
            preview += "..."

        return (
            "**Draft updated.**\n\n"
            f"{preview}\n\n"
            "Next:\n"
            "  **ai rewrite blog**           - AI polish\n"
            "  **publish blog**              - Save as .txt\n"
            "  **publish blog to <target>**  - Publish remotely\n"
            "  **blog title**                - Generate a title"
        )

    # ── Natural language detection ───────────────────────────────────────────

    def _is_help(self, text: str) -> bool:
        return bool(re.search(r"blog\s+help|help\s+blog", text))

    def _is_show(self, text: str) -> bool:
        return bool(re.search(
            r"^(show|list|view|read)\s+(my\s+)?blog|^blog\s+(entries|posts|list|show)$",
            text.strip(),
        ))

    def _is_write(self, text: str) -> bool:
        return bool(re.search(
            r"(write|add|post|create)\s+(blog\s+)?(news|entry|post|content)|"
            r"blog\s+(news|write|add|post)",
            text,
        ))

    def _is_crawl_blog(self, text: str) -> bool:
        return bool(re.search(
            r"(crawl|scrape|fetch|grab)\s+.+\s+for\s+.*(title|body|content|heading|text|non.?title)",
            text,
        ))

    def _is_generate_title(self, text: str) -> bool:
        return bool(re.search(
            r"(generate|create|make|suggest)\s+(blog\s+)?(title|headline)|"
            r"blog\s+title",
            text,
        ))

    def _is_publish(self, text: str) -> bool:
        # Local publish (to .txt) - not "publish to" or "publish blog to"
        return bool(re.search(
            r"(publish|finalize|save|export)\s+(my\s+)?blog(?!\s+to\b)|blog\s+(publish|save|export)(?!\s+to\b)",
            text,
        ))

    # AI detection
    def _is_ai_generate(self, text: str) -> bool:
        return bool(re.search(
            r"ai\s+(blog\s+)?(generate|write|create|draft)|"
            r"(generate|write|create|draft)\s+(a\s+)?blog\s+(post\s+)?(about|on|for)|"
            r"blog\s+ai\s+(generate|write|create)",
            text,
        ))

    def _is_ai_rewrite(self, text: str) -> bool:
        return bool(re.search(
            r"ai\s+(blog\s+)?(rewrite|improve|polish|edit)|"
            r"(rewrite|improve|polish)\s+(my\s+)?blog|"
            r"blog\s+ai\s+(rewrite|improve)",
            text,
        ))

    def _is_ai_expand(self, text: str) -> bool:
        return bool(re.search(
            r"ai\s+(blog\s+)?(expand|extend|elaborate|lengthen)|"
            r"(expand|extend|elaborate)\s+(my\s+)?blog|"
            r"blog\s+ai\s+(expand|extend)",
            text,
        ))

    def _is_ai_headlines(self, text: str) -> bool:
        return bool(re.search(
            r"ai\s+(blog\s+)?(headlines?|titles?)|"
            r"(generate|suggest)\s+(ai\s+)?headlines?",
            text,
        ))

    def _is_ai_seo(self, text: str) -> bool:
        return bool(re.search(r"ai\s+(blog\s+)?seo|blog\s+seo|seo\s+blog", text))

    def _is_ai_info(self, text: str) -> bool:
        return bool(re.search(
            r"(local\s+)?ai\s+(options?|info|setup|install)|"
            r"ai\s+blog\s+(options?|info|setup)",
            text,
        ))

    def _is_ai_providers(self, text: str) -> bool:
        return bool(re.search(
            r"(ai\s+)?provider[s]?|ai\s+(list|show|status)|"
            r"(cloud|api)\s+(ai|providers?|keys?)",
            text,
        ))

    def _is_ai_switch(self, text: str) -> bool:
        return bool(re.search(r"(use|switch|set)\s+(ai\s+)?(provider|model)\s+", text))

    # Publishing detection
    def _is_publish_remote(self, text: str) -> bool:
        return bool(re.search(
            r"publish\s+(blog\s+)?to\s+|"
            r"(upload|deploy|push)\s+(blog\s+)?to\s+|"
            r"blog\s+publish\s+to\s+",
            text,
        ))

    def _is_setup_publish(self, text: str) -> bool:
        return bool(re.search(
            r"setup\s+(blog\s+)?publish|"
            r"setup\s+publish\s+blog|"
            r"(save|add|store)\s+(blog\s+)?publish\s+target",
            text,
        ))

    def _is_list_targets(self, text: str) -> bool:
        return bool(re.search(
            r"(list|show)\s+(publish|upload|deploy)\s*targets?|"
            r"publish\s*targets?|"
            r"where\s+can\s+i\s+publish",
            text,
        ))

    # Front page detection
    def _is_set_front_page(self, text: str) -> bool:
        return bool(re.search(
            r"(set|make|change|update)\s+(the\s+)?(front\s*page|home\s*page|featured|main\s*page)|"
            r"front\s*page\s+(set|to|is)|"
            r"feature\s+(post|article|page)\s+",
            text,
        ))

    def _is_show_front_page(self, text: str) -> bool:
        return bool(re.search(
            r"(show|what|which|current)\s+(is\s+)?(the\s+)?(front\s*page|home\s*page|featured)",
            text,
        ))

    def _is_list_pages(self, text: str) -> bool:
        return bool(re.search(
            r"(list|show)\s+(available\s+)?(pages|articles)\s+(for|on)\s+",
            text,
        ))

    # ── AI operations ────────────────────────────────────────────────────────

    async def _ai_generate(self, raw_input: str, user_id: str, engine: "SafeClaw") -> str:
        """Generate a blog post with AI."""
        if not self.ai_writer or not self.ai_writer.providers:
            return (
                "No AI providers configured.\n\n"
                "Add providers in config/config.yaml under ai_providers.\n"
                "Use 'ai options' to see local AI options (free, private).\n"
                "Use 'ai providers' to see cloud API providers."
            )

        # Extract topic from command
        topic = re.sub(
            r'(?i)(please\s+)?(ai\s+)?(blog\s+)?(generate|write|create|draft)\s+(a\s+)?(blog\s+)?(post\s+)?(about|on|for)?\s*',
            '',
            raw_input,
        ).strip()
        # Strip any remaining polite prefix
        topic = re.sub(r'(?i)^please\s+', '', topic).strip()

        if not topic:
            return "Please provide a topic. Example: ai blog generate about sustainable technology trends"

        # Get existing draft content as context
        draft_path = self._get_draft_path(user_id)
        context = ""
        if draft_path.exists():
            context = self._get_entries_text(draft_path.read_text())

        response = await self.ai_writer.generate_blog(topic, context)

        if response.error:
            return f"AI generation failed: {response.error}"

        # Save generated content to draft
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n[{timestamp}] AI-generated ({response.provider}/{response.model})\n{response.content}\n"

        with open(draft_path, "a") as f:
            f.write(entry)

        entry_count = self._count_entries(draft_path)
        preview = response.content[:500]
        if len(response.content) > 500:
            preview += "..."

        tokens_info = f" ({response.tokens_used} tokens)" if response.tokens_used else ""

        return (
            f"AI-generated blog post added to draft ({entry_count} entries total).\n"
            f"Provider: {response.provider} / {response.model}{tokens_info}\n\n"
            f"Preview:\n{preview}\n\n"
            f"Next steps:\n"
            f"  'ai rewrite blog' - Polish the content\n"
            f"  'ai headlines' - Generate headline options\n"
            f"  'publish blog' - Save as .txt locally\n"
            f"  'publish blog to <target>' - Publish to WordPress/Joomla/SFTP"
        )

    async def _ai_rewrite(self, raw_input: str, user_id: str) -> str:
        """Rewrite blog draft with AI."""
        if not self.ai_writer or not self.ai_writer.providers:
            return "No AI providers configured. Use 'ai options' for setup info."

        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found. Write some entries first or use 'ai blog generate about <topic>'."

        content = self._get_entries_text(draft_path.read_text())
        if not content.strip():
            return "Blog draft is empty."

        response = await self.ai_writer.rewrite_blog(content)

        if response.error:
            return f"AI rewrite failed: {response.error}"

        # Replace draft content
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_draft = f"[{timestamp}] AI-rewritten ({response.provider}/{response.model})\n{response.content}\n"
        draft_path.write_text(new_draft)

        preview = response.content[:500]
        if len(response.content) > 500:
            preview += "..."

        return (
            f"Blog draft rewritten by AI.\n"
            f"Provider: {response.provider} / {response.model}\n\n"
            f"Preview:\n{preview}\n\n"
            f"Use 'publish blog' to save locally or 'publish blog to <target>' to publish."
        )

    async def _ai_expand(self, raw_input: str, user_id: str) -> str:
        """Expand blog draft with AI."""
        if not self.ai_writer or not self.ai_writer.providers:
            return "No AI providers configured. Use 'ai options' for setup info."

        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found. Write some entries first."

        content = self._get_entries_text(draft_path.read_text())
        if not content.strip():
            return "Blog draft is empty."

        response = await self.ai_writer.expand_blog(content)

        if response.error:
            return f"AI expand failed: {response.error}"

        # Replace draft content
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_draft = f"[{timestamp}] AI-expanded ({response.provider}/{response.model})\n{response.content}\n"
        draft_path.write_text(new_draft)

        return (
            f"Blog draft expanded by AI.\n"
            f"Provider: {response.provider} / {response.model}\n\n"
            f"Preview:\n{response.content[:500]}{'...' if len(response.content) > 500 else ''}\n\n"
            f"Use 'publish blog' to save or 'publish blog to <target>' to publish."
        )

    async def _ai_headlines(self, user_id: str) -> str:
        """Generate headline suggestions with AI."""
        if not self.ai_writer or not self.ai_writer.providers:
            return "No AI providers configured. Use 'ai options' for setup info."

        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found."

        content = self._get_entries_text(draft_path.read_text())
        if not content.strip():
            return "Blog draft is empty."

        response = await self.ai_writer.generate_headlines(content)

        if response.error:
            return f"AI headline generation failed: {response.error}"

        return (
            f"**AI-Generated Headlines**\n"
            f"Provider: {response.provider} / {response.model}\n\n"
            f"{response.content}\n\n"
            f"Use 'publish blog <Your Chosen Title>' to publish with a title."
        )

    async def _ai_seo(self, user_id: str) -> str:
        """Generate SEO metadata with AI."""
        if not self.ai_writer or not self.ai_writer.providers:
            return "No AI providers configured. Use 'ai options' for setup info."

        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found."

        content = self._get_entries_text(draft_path.read_text())
        if not content.strip():
            return "Blog draft is empty."

        response = await self.ai_writer.generate_seo(content)

        if response.error:
            return f"AI SEO generation failed: {response.error}"

        return (
            f"**AI-Generated SEO Metadata**\n"
            f"Provider: {response.provider} / {response.model}\n\n"
            f"{response.content}"
        )

    def _ai_info(self) -> str:
        """Show local AI options."""
        info = AIWriter.get_local_ai_info()

        if self.ai_writer and self.ai_writer.providers:
            info += "\n\n---\n\n**Your Configured Providers:**\n"
            for p in self.ai_writer.list_providers():
                active = " (ACTIVE)" if p["active"] else ""
                local = " [local]" if p["is_local"] else " [cloud]"
                info += f"  - {p['label']}: {p['provider']}/{p['model']}{local}{active}\n"

        return info

    def _ai_providers_info(self) -> str:
        """Show cloud AI providers and current config."""
        info = AIWriter.get_cloud_providers_info()

        if self.ai_writer and self.ai_writer.providers:
            info += "\n---\n\n**Your Configured Providers:**\n"
            for p in self.ai_writer.list_providers():
                active = " (ACTIVE)" if p["active"] else ""
                local = " [local]" if p["is_local"] else " [cloud]"
                has_key = " [key set]" if p["has_key"] else " [no key]"
                enabled = "" if p["enabled"] else " [DISABLED]"
                info += f"  - {p['label']}: {p['provider']}/{p['model']}{local}{has_key}{active}{enabled}\n"
        else:
            info += "\n---\n\nNo providers configured yet. Add them in config/config.yaml."

        return info

    def _ai_switch_provider(self, raw_input: str) -> str:
        """Switch active AI provider."""
        if not self.ai_writer:
            return "No AI providers configured."

        # Extract provider label
        label = re.sub(
            r'(?i)(use|switch|set)\s+(ai\s+)?(provider|model)\s+(to\s+)?',
            '',
            raw_input,
        ).strip()

        if not label:
            providers = self.ai_writer.list_providers()
            lines = ["Available providers:"]
            for p in providers:
                active = " (ACTIVE)" if p["active"] else ""
                lines.append(f"  - {p['label']}{active}")
            lines.append("\nUse: switch ai provider <label>")
            return "\n".join(lines)

        if self.ai_writer.set_active_provider(label):
            return f"Switched active AI provider to '{label}'."
        else:
            available = ", ".join(self.ai_writer.providers.keys())
            return f"Provider '{label}' not found. Available: {available}"

    # ── Publishing operations ────────────────────────────────────────────────

    # ── Publish target setup (saves to config, no YAML editing needed) ──────

    async def _setup_publish(self, raw_input: str, user_id: str, engine: "SafeClaw") -> str:
        """
        Set up a permanent publish target without touching config files.

        Usage:
          setup blog publish wp://mysite.com user pass
          setup blog publish sftp://host user pass /remote/path
          setup blog publish joomla://cms.example.com user token
          setup blog publish api://api.example.com/posts api-key
          setup blog publish list
          setup blog publish remove <label>
        """
        lower = raw_input.lower().strip()

        # List saved targets
        if re.search(r'\b(list|show|ls)\b', lower.split("publish", 1)[-1]):
            return self._list_publish_targets()

        # Remove a target
        remove_m = re.search(r'\b(?:remove|delete|rm)\s+(\S+)', lower)
        if remove_m:
            label = remove_m.group(1)
            return self._remove_publish_target(label, engine)

        # Parse inline target from command
        target = self._parse_inline_target(raw_input)
        if not target:
            return self._setup_publish_help()

        # Save to config.yaml for persistence
        saved = self._save_publish_target_to_config(target, engine)

        # Also register in-memory so it's usable immediately without restart
        if not self.publisher:
            self.publisher = BlogPublisher()
        self.publisher.add_target(target)

        location = target.url or target.sftp_host
        if saved:
            return (
                f"**Publish target saved!**\n\n"
                f"  Label:    {target.label}\n"
                f"  Type:     {target.target_type.value}\n"
                f"  Location: {location}\n\n"
                f"Use it any time:\n"
                f"  publish blog to {target.label}\n"
                f"  publish blog to all\n\n"
                f"Remove later with:  setup blog publish remove {target.label}\n"
                f"List all targets:   setup blog publish list"
            )
        else:
            return (
                f"**Target active this session** (could not write to config).\n\n"
                f"  Label:    {target.label}\n"
                f"  Type:     {target.target_type.value}\n"
                f"  Location: {location}\n\n"
                f"To save permanently add to config/config.yaml under publish_targets."
            )

    def _is_publish_question(self, text: str) -> bool:
        return bool(re.search(
            r'how\s+(do\s+i|can\s+i|to)\s+(publish|upload|deploy|post|send)|'
            r'(publish|upload|deploy)\s+(to\s+)?(sftp|ftp|wordpress|wp|joomla|server|remote|site|my\s+site)|'
            r'(sftp|ftp)\s+(publish|upload|how|setup|configure)',
            text,
        ))

    def _publish_how_to(self, text: str) -> str:
        if re.search(r'\b(sftp|ftp)\b', text):
            return (
                "**Publish to SFTP**\n\n"
                "1. Register your server once:\n"
                "   `setup blog publish sftp://your-host.com user password /remote/path`\n\n"
                "   With a custom port:\n"
                "   `setup blog publish sftp://your-host.com:2222 user password /remote/path`\n\n"
                "2. Then publish any time:\n"
                "   `publish blog to your-host.com`\n\n"
                "The bot previews the title first and asks for confirmation before uploading.\n\n"
                "**Other targets:** WordPress, Joomla, custom API\n"
                "  `setup blog publish` — see all options"
            )
        if re.search(r'\b(wordpress|wp)\b', text):
            return (
                "**Publish to WordPress**\n\n"
                "1. Generate an application password in WordPress:\n"
                "   WordPress Admin → Users → Profile → Application Passwords\n\n"
                "2. Register it once:\n"
                "   `setup blog publish wp://yoursite.com username app-password`\n\n"
                "3. Then publish any time:\n"
                "   `publish blog to yoursite.com`\n\n"
                "**Other targets:** SFTP, Joomla, custom API\n"
                "  `setup blog publish` — see all options"
            )
        return self._setup_publish_help()

    def _setup_publish_help(self) -> str:
        return (
            "**Setup a permanent publish target — no config files needed**\n\n"
            "  setup blog publish wp://mysite.com user app-password\n"
            "  setup blog publish sftp://host:port user pass /remote/path\n"
            "  setup blog publish joomla://cms.example.com user token\n"
            "  setup blog publish api://api.example.com/posts api-key\n\n"
            "After setup, publish any time with:\n"
            "  publish blog to <label>\n"
            "  publish blog to all\n\n"
            "Other setup commands:\n"
            "  setup blog publish list          - Show saved targets\n"
            "  setup blog publish remove <label> - Remove a target"
        )

    def _save_publish_target_to_config(self, target: PublishTarget, engine: "SafeClaw") -> bool:
        """Write a publish target into config.yaml so it survives restarts."""
        config_path = getattr(engine, "config_path", None)
        if not config_path:
            return False
        try:
            config_path = Path(config_path)
            config_path.parent.mkdir(parents=True, exist_ok=True)

            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            targets = config.get("publish_targets") or []

            # Build a minimal dict — only include non-default fields
            t_dict: dict = {
                "label": target.label,
                "type": target.target_type.value,
            }
            if target.url:
                t_dict["url"] = target.url
            if target.username:
                t_dict["username"] = target.username
            if target.password:
                t_dict["password"] = target.password
            if target.api_key:
                t_dict["api_key"] = target.api_key
            if target.sftp_host:
                t_dict["sftp_host"] = target.sftp_host
            if target.sftp_port != 22:
                t_dict["sftp_port"] = target.sftp_port
            if target.sftp_user:
                t_dict["sftp_user"] = target.sftp_user
            if target.sftp_password:
                t_dict["sftp_password"] = target.sftp_password
            if target.sftp_key_path:
                t_dict["sftp_key_path"] = target.sftp_key_path
            if target.sftp_remote_path != "/var/www/html/blog":
                t_dict["sftp_remote_path"] = target.sftp_remote_path

            # Update existing or append
            for i, t in enumerate(targets):
                if isinstance(t, dict) and t.get("label") == target.label:
                    targets[i] = t_dict
                    break
            else:
                targets.append(t_dict)

            config["publish_targets"] = targets
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            # Keep engine config in sync so the change is live immediately
            engine.config["publish_targets"] = targets

            return True
        except Exception as e:
            logger.error(f"Failed to save publish target: {e}")
            return False

    def _remove_publish_target(self, label: str, engine: "SafeClaw") -> str:
        """Remove a publish target from config.yaml and from memory."""
        removed_memory = False
        if self.publisher and label in self.publisher.targets:
            del self.publisher.targets[label]
            removed_memory = True

        config_path = getattr(engine, "config_path", None)
        if not config_path or not Path(config_path).exists():
            if removed_memory:
                return f"Removed '{label}' from this session (it was not in saved config)."
            return f"Target '{label}' not found."

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            targets = config.get("publish_targets") or []
            original_len = len(targets)
            targets = [t for t in targets if not (isinstance(t, dict) and t.get("label") == label)]

            if len(targets) == original_len and not removed_memory:
                return f"Target '{label}' not found. Use 'setup blog publish list' to see targets."

            config["publish_targets"] = targets
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            engine.config["publish_targets"] = targets

            return f"Removed publish target **{label}**."
        except Exception as e:
            return f"Error removing target: {e}"

    async def _publish_remote(self, raw_input: str, user_id: str) -> str:
        """Stage a remote publish — show preview and wait for confirmation."""
        # Try to parse an inline target (sftp://... wp://... etc.) before
        # checking configured targets, so setup-free publishing always works.
        inline_target = self._parse_inline_target(raw_input)
        if inline_target:
            if not self.publisher:
                self.publisher = BlogPublisher()
            self.publisher.add_target(inline_target)

        if not self.publisher or not self.publisher.targets:
            return (
                "No publishing targets configured.\n\n"
                "You can publish inline without any config:\n"
                "  publish blog to sftp://host username password\n"
                "  publish blog to sftp://host:port username password /remote/path\n"
                "  publish blog to wp://mysite.com username password\n"
                "  publish blog to wordpress://mysite.com username password\n"
                "  publish blog to joomla://mysite.com username password\n"
                "  publish blog to api://mysite.com/endpoint api_key\n\n"
                "Or add permanent targets in config/config.yaml under publish_targets."
            )

        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found. Write or generate content first."

        content = self._get_entries_text(draft_path.read_text())
        if not content.strip():
            return "Blog draft is empty."

        # Resolve target label
        target_match = re.search(
            r'(?:publish|upload|deploy|push)\s+(?:blog\s+)?to\s+(\S+)',
            raw_input, re.IGNORECASE,
        )
        target_label = None
        if inline_target:
            target_label = inline_target.label
        elif target_match:
            label = target_match.group(1).lower()
            if label in self.publisher.targets:
                target_label = label
            elif label == "all":
                target_label = None
            else:
                for tgt_label, tgt in self.publisher.targets.items():
                    if tgt.target_type.value == label:
                        target_label = tgt_label
                        break
                if target_label is None:
                    available = ", ".join(self.publisher.targets.keys())
                    return f"Target '{label}' not found. Available: {available}, or 'all'"

        # Generate title
        title = self._extract_publish_title(raw_input)
        if not title:
            title = self.summarizer.summarize(content, sentences=1).strip()
            if not title:
                keywords = self.summarizer.get_keywords(content, top_n=5)
                title = " ".join(w.capitalize() for w in keywords) if keywords else "Untitled Blog Post"

        # Store pending publish state
        self._set_session(
            user_id, SESSION_PENDING_PUBLISH,
            pending_title=title,
            target_label=target_label,
        )

        # Show preview
        word_count = len(content.split())
        preview = content[:400].strip()
        if len(content) > 400:
            preview += "\n... [truncated]"
        target_info = target_label or "all configured targets"

        return (
            f"**Ready to Publish**\n\n"
            f"  Title:  {title}\n"
            f"  Words:  {word_count}\n"
            f"  Target: {target_info}\n\n"
            f"**Preview:**\n{preview}\n\n"
            f"---\n"
            f"  **confirm**                    - Publish now\n"
            f"  **change title** <new title>   - Rename before publishing\n"
            f"  **edit blog** <new content>    - Edit content first\n"
            f"  **cancel**                     - Abort\n"
        )

    async def _handle_pending_publish(
        self,
        session: dict[str, Any],
        raw_input: str,
        lower: str,
        user_id: str,
    ) -> str | None:
        """Handle input while a publish is staged and awaiting confirmation."""
        stripped = lower.strip()

        # Confirm → publish
        if stripped in ("confirm", "yes", "publish", "publish it", "go", "send it", "do it"):
            title = session.get("pending_title", "Untitled Blog Post")
            target_label = session.get("target_label")
            self._clear_session(user_id)
            return await self._do_publish(title, target_label, user_id)

        # Change title
        title_match = re.match(r'(?:change\s+)?(?:set\s+)?title\s+(.+)', stripped)
        if title_match:
            # Preserve original casing from raw_input
            new_title = re.sub(r'(?i)^(?:change\s+)?(?:set\s+)?title\s+', '', raw_input).strip()
            target_label = session.get("target_label")
            self._set_session(
                user_id, SESSION_PENDING_PUBLISH,
                pending_title=new_title,
                target_label=target_label,
            )
            target_info = target_label or "all configured targets"
            return (
                f"**Title updated.**\n\n"
                f"  Title:  {new_title}\n"
                f"  Target: {target_info}\n\n"
                f"Type **confirm** to publish or **cancel** to abort."
            )

        # Cancel
        if stripped in ("cancel", "no", "abort", "stop", "back", "nevermind"):
            self._clear_session(user_id)
            return "Publish cancelled. Your draft is still saved."

        # Any other explicit command — clear session and fall through to normal routing
        if self._looks_like_command(lower):
            self._clear_session(user_id)
            return None

        # Unrecognised input — remind them what's pending
        title = session.get("pending_title", "Untitled Blog Post")
        target_info = session.get("target_label") or "all configured targets"
        return (
            f"**Pending publish** — \"{title}\" → {target_info}\n\n"
            f"  **confirm**                    - Publish now\n"
            f"  **change title** <new title>   - Rename\n"
            f"  **edit blog** <content>        - Edit content (cancels pending publish)\n"
            f"  **cancel**                     - Abort\n"
        )

    async def _do_publish(
        self,
        title: str,
        target_label: str | None,
        user_id: str,
    ) -> str:
        """Execute the actual remote publish after confirmation."""
        if not self.publisher or not self.publisher.targets:
            return (
                "Publishing target is no longer available (session may have been restored after restart).\n"
                "Please re-issue the publish command:\n"
                "  publish blog to wp://mysite.com user pass\n"
                "  publish blog to sftp://host user pass"
            )

        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found."

        content = self._get_entries_text(draft_path.read_text())
        if not content.strip():
            return "Blog draft is empty."

        # Generate excerpt
        excerpt = ""
        if self.ai_writer and self.ai_writer.providers:
            resp = await self.ai_writer.generate_excerpt(content)
            if not resp.error:
                excerpt = resp.content.strip()
        if not excerpt:
            excerpt = content[:160].strip()

        # Generate slug
        slug = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '-').lower()

        results = await self.publisher.publish(
            title=title,
            content=content,
            target_label=target_label,
            excerpt=excerpt,
            slug=slug,
        )

        lines = ["**Blog Published**", ""]
        any_success = False
        for r in results:
            if r.success:
                any_success = True
                lines.append(f"  {r.target_label} ({r.target_type}): {r.message}")
                if r.url:
                    lines.append(f"    URL: {r.url}")
            else:
                lines.append(f"  {r.target_label} ({r.target_type}): FAILED - {r.error}")

        if any_success:
            lines.extend(["", "Use 'set front page <post_id> on <target>' to feature this post."])

        return "\n".join(lines)

    @staticmethod
    def _parse_inline_target(raw_input: str) -> PublishTarget | None:
        """
        Parse an inline publish target from the command string.

        Supported syntax:
          publish blog to sftp://host username password
          publish blog to sftp://host:port username password
          publish blog to sftp://host:port username password /remote/path
          publish blog to wp://https://mysite.com username password
          publish blog to wordpress://mysite.com username password
          publish blog to joomla://mysite.com username password
          publish blog to api://mysite.com/endpoint api_key
        """
        # Match scheme://... followed by optional tokens
        m = re.search(
            r'(?:publish|upload|deploy|push)\s+(?:blog\s+)?to\s+'
            r'(sftp|wp|wordpress|joomla|api)://([\S]+?)(?:\s+(\S+)(?:\s+(\S+)(?:\s+(\S+))?)?)?$',
            raw_input.strip(), re.IGNORECASE,
        )
        if not m:
            return None

        scheme = m.group(1).lower()
        host_part = m.group(2).rstrip('/')
        token1 = m.group(3) or ""   # username / api_key
        token2 = m.group(4) or ""   # password
        token3 = m.group(5) or ""   # remote path (sftp only)

        if scheme == "sftp":
            host, _, port_str = host_part.partition(":")
            port = int(port_str) if port_str.isdigit() else 22
            return PublishTarget(
                label=f"sftp-{host}",
                target_type=PublishTargetType.SFTP,
                sftp_host=host,
                sftp_port=port,
                sftp_user=token1,
                sftp_password=token2,
                sftp_remote_path=token3 or "/var/www/html/blog",
            )

        if scheme in ("wp", "wordpress"):
            url = host_part if host_part.startswith("http") else f"https://{host_part}"
            domain = urlparse(url).netloc or host_part.split('/')[0]
            return PublishTarget(
                label=f"wp-{domain}",
                target_type=PublishTargetType.WORDPRESS,
                url=url,
                username=token1,
                password=token2,
            )

        if scheme == "joomla":
            url = host_part if host_part.startswith("http") else f"https://{host_part}"
            domain = urlparse(url).netloc or host_part.split('/')[0]
            return PublishTarget(
                label=f"joomla-{domain}",
                target_type=PublishTargetType.JOOMLA,
                url=url,
                username=token1,
                password=token2,
            )

        if scheme == "api":
            url = host_part if host_part.startswith("http") else f"https://{host_part}"
            domain = urlparse(url).netloc or host_part.split('/')[0]
            return PublishTarget(
                label=f"api-{domain}",
                target_type=PublishTargetType.API,
                url=url,
                api_key=token1,
            )

        return None

    def _extract_publish_title(self, raw_input: str) -> str:
        """Extract a custom title from the publish command."""
        # Look for quoted title
        quoted = re.search(r'"([^"]+)"', raw_input)
        if quoted:
            return quoted.group(1)

        # Look for 'titled X' or 'title X'
        titled = re.search(r'titled?\s+(.+?)(?:\s+on\s+|\s+to\s+|$)', raw_input, re.I)
        if titled:
            return titled.group(1).strip()

        return ""

    def _list_publish_targets(self) -> str:
        """List configured publishing targets."""
        if not self.publisher or not self.publisher.targets:
            return (
                "No publishing targets configured.\n\n"
                "Add in config/config.yaml:\n"
                "  publish_targets:\n"
                "    - label: my-site\n"
                "      type: wordpress|joomla|sftp|api\n"
                "      url: https://...\n"
            )

        targets = self.publisher.list_targets()
        lines = ["**Publishing Targets**", ""]
        for t in targets:
            status = "enabled" if t["enabled"] else "DISABLED"
            lines.append(f"  - {t['label']} ({t['type']}): {t['url']} [{status}]")

        lines.extend([
            "",
            "Publish with: publish blog to <label>",
            "Publish to all: publish blog to all",
        ])

        return "\n".join(lines)

    # ── Front page operations ────────────────────────────────────────────────

    async def _set_front_page(self, raw_input: str, user_id: str) -> str:
        """Set a post as the front page for a target."""
        if not self.frontpage:
            return "No publishing targets configured. Front page requires a target."

        # Parse: set front page <post_id> on <target>
        # Or: set front page <post_id>  (uses first target)
        match = re.search(
            r'(?:set|make|change|update)\s+(?:the\s+)?(?:front\s*page|home\s*page|featured)\s+'
            r'(?:to\s+)?(\S+)(?:\s+(?:on|for)\s+(\S+))?',
            raw_input, re.IGNORECASE,
        )

        if not match:
            # Try: feature post <id> on <target>
            match = re.search(
                r'feature\s+(?:post|article|page)\s+(\S+)(?:\s+(?:on|for)\s+(\S+))?',
                raw_input, re.IGNORECASE,
            )

        if not match:
            current = self.frontpage.show_status()
            return (
                f"{current}\n\n"
                f"Usage: set front page <post_id> on <target>\n"
                f"Example: set front page 42 on my-wordpress"
            )

        post_id = match.group(1)
        target_label = match.group(2) if match.group(2) else None

        # Default to first target if not specified
        if not target_label:
            target_label = next(iter(self.publisher.targets), None) if self.publisher else None

        if not target_label:
            return "No target specified and no targets configured."

        result = await self.frontpage.set_front_page(
            target_label=target_label,
            post_id=post_id,
        )

        if result.success:
            return f"Front page updated: {result.message}"
        else:
            return f"Failed to set front page: {result.error}"

    def _show_front_page(self) -> str:
        """Show current front page status."""
        if not self.frontpage:
            return "No publishing targets configured."
        return self.frontpage.show_status()

    async def _list_pages(self, raw_input: str) -> str:
        """List available pages for front page selection."""
        if not self.frontpage:
            return "No publishing targets configured."

        # Extract target label
        match = re.search(r'(?:for|on)\s+(\S+)', raw_input, re.IGNORECASE)
        target_label = match.group(1) if match else None

        if not target_label:
            target_label = next(iter(self.publisher.targets), None) if self.publisher else None

        if not target_label:
            return "No target specified."

        pages = await self.frontpage.list_pages(target_label)

        if not pages:
            return f"No pages/articles found on '{target_label}'."

        lines = [f"**Pages on {target_label}**", ""]
        for p in pages:
            featured = " [FEATURED]" if p.get("featured") else ""
            lines.append(f"  ID {p['id']}: {p['title']}{featured}")

        lines.extend(["", f"Set front page: set front page <id> on {target_label}"])

        return "\n".join(lines)

    # ── Original (non-AI) blog operations ────────────────────────────────────

    async def _write_blog_news(
        self, raw_input: str, user_id: str, engine: "SafeClaw"
    ) -> str:
        """Write blog news content to the user's draft."""
        content = self._extract_blog_content(raw_input)
        if not content:
            return "Please provide some content. Example: write blog news The new update brings faster crawling and better summaries."

        draft_path = self._get_draft_path(user_id)

        # Append to existing draft
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n[{timestamp}]\n{content}\n"

        with open(draft_path, "a") as f:
            f.write(entry)

        # Feed to writing style profiler (fuzzy learning)
        if engine and hasattr(engine, "memory") and engine.memory:
            try:
                from safeclaw.core.writing_style import update_writing_profile
                await update_writing_profile(engine.memory, user_id, content)
            except Exception as e:
                logger.debug(f"Style profiling skipped: {e}")

        # Count entries
        entry_count = self._count_entries(draft_path)

        # Auto-generate title suggestion from accumulated content
        title_suggestion = ""
        if entry_count >= 2:
            title = self._compute_title(draft_path)
            if title:
                title_suggestion = f"\nSuggested title: {title}"

        ai_hint = ""
        if self.ai_writer and self.ai_writer.providers:
            ai_hint = "\n  'ai rewrite blog' - Polish with AI"

        return (
            f"Added blog entry ({entry_count} total in draft).\n"
            f"Saved to: {draft_path}"
            f"{title_suggestion}\n\n"
            f"Next:\n"
            f"  'blog title' - Generate a title\n"
            f"  'publish blog' - Save as .txt{ai_hint}\n"
            f"  'publish blog to <target>' - Publish remotely"
        )

    async def _crawl_for_blog(
        self, raw_input: str, user_id: str, engine: "SafeClaw"
    ) -> str:
        """Crawl a website and extract content for the blog."""
        # Extract URL
        url_match = re.search(
            r'(https?://[^\s]+|(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}[^\s]*)',
            raw_input,
        )
        if not url_match:
            return "Please provide a URL. Example: crawl https://example.com for title content"

        url = url_match.group(1)
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Determine what content to extract
        lower = raw_input.lower()
        extract_type = self._determine_extract_type(lower)

        # Crawl the page
        async with Crawler() as crawler:
            result = await crawler.fetch(url)

        if result.error:
            return f"Could not crawl {url}: {result.error}"

        if not result.text:
            return f"No content found on {url}"

        # Extract the requested content type
        import httpx
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "SafeClaw/0.2 (Privacy-first crawler)"},
        ) as client:
            try:
                response = await client.get(url)
                soup = BeautifulSoup(response.text, "lxml")
            except Exception as e:
                return f"Could not fetch {url}: {e}"

        # Remove script/style
        for element in soup(["script", "style"]):
            element.decompose()

        extracted = self._extract_by_type(soup, extract_type)

        if not extracted:
            return f"No {extract_type} content found on {url}"

        # Write extracted content to blog draft
        draft_path = self._get_draft_path(user_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        domain = urlparse(url).netloc

        entry = f"\n[{timestamp}] crawled {domain} ({extract_type})\n{extracted}\n"

        with open(draft_path, "a") as f:
            f.write(entry)

        entry_count = self._count_entries(draft_path)

        # Preview
        preview = extracted[:300]
        if len(extracted) > 300:
            preview += "..."

        return (
            f"Crawled {extract_type} content from {domain} and added to blog draft.\n"
            f"Entries in draft: {entry_count}\n\n"
            f"Preview:\n{preview}\n\n"
            f"Use 'blog title' to generate a title from your collected content."
        )

    def _determine_extract_type(self, text: str) -> str:
        """Determine what type of content to extract from natural language."""
        if re.search(r"non.?title|non.?heading|without\s+title", text):
            return "non-title"
        if re.search(r"body|main|article|paragraph|text\s+content", text):
            return "body"
        if re.search(r"title|heading|headline|h[1-6]", text):
            return "title"
        return "body"

    def _extract_by_type(self, soup: Any, extract_type: str) -> str:
        """Extract content from parsed HTML by type."""
        if extract_type == "title":
            return self._extract_titles(soup)
        elif extract_type == "non-title":
            return self._extract_non_titles(soup)
        else:
            return self._extract_body(soup)

    def _extract_titles(self, soup: Any) -> str:
        """Extract title and heading content from page."""
        titles = []
        title_tag = soup.find("title")
        if title_tag:
            titles.append(title_tag.get_text(strip=True))
        for level in range(1, 7):
            for heading in soup.find_all(f"h{level}"):
                text = heading.get_text(strip=True)
                if text and text not in titles:
                    titles.append(text)
        return "\n".join(titles)

    def _extract_non_titles(self, soup: Any) -> str:
        """Extract non-title content (everything except headings)."""
        for tag in soup.find_all(["title", "h1", "h2", "h3", "h4", "h5", "h6"]):
            tag.decompose()
        for tag in soup.find_all(["nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def _extract_body(self, soup: Any) -> str:
        """Extract main body/article content."""
        main = soup.find("article") or soup.find("main") or soup.find(
            "div", class_=re.compile(r"content|article|post|entry|body", re.I)
        )
        if main:
            for tag in main.find_all(["nav", "footer", "header"]):
                tag.decompose()
            text = main.get_text(separator="\n", strip=True)
        else:
            paragraphs = soup.find_all("p")
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def _generate_title(self, user_id: str) -> str:
        """Generate a blog title from accumulated content using extractive summarization."""
        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found. Write some entries first with 'write blog news ...'"

        content = draft_path.read_text()
        entries_text = self._get_entries_text(content)

        if not entries_text.strip():
            return "Blog draft is empty. Add some content first."

        title = self.summarizer.summarize(entries_text, sentences=1)

        if not title or not title.strip():
            keywords = self.summarizer.get_keywords(entries_text, top_n=5)
            if keywords:
                title = " ".join(w.capitalize() for w in keywords)
            else:
                return "Not enough content to generate a title. Add more entries."

        title = title.strip()
        if len(title) > 120:
            title = title[:117] + "..."

        ai_hint = ""
        if self.ai_writer and self.ai_writer.providers:
            ai_hint = "\nOr use 'ai headlines' for AI-generated headline options."

        return (
            f"Generated blog title:\n\n  {title}\n\n"
            f"Use 'publish blog' to save with this title, or 'publish blog My Custom Title' to use your own."
            f"{ai_hint}"
        )

    def _publish_blog(self, raw_input: str, user_id: str) -> str:
        """Finalize blog and save as .txt with title."""
        draft_path = self._get_draft_path(user_id)
        if not draft_path.exists():
            return "No blog draft found. Write some entries first."

        content = draft_path.read_text()
        entries_text = self._get_entries_text(content)

        if not entries_text.strip():
            return "Blog draft is empty."

        # Extract custom title or auto-generate
        custom_title = re.sub(
            r'(?i)(publish|finalize|save|export)\s+(my\s+)?blog\s*',
            '',
            raw_input,
        ).strip()

        if custom_title:
            title = custom_title
        else:
            title = self.summarizer.summarize(entries_text, sentences=1).strip()
            if not title:
                keywords = self.summarizer.get_keywords(entries_text, top_n=5)
                title = " ".join(w.capitalize() for w in keywords) if keywords else "Untitled Blog Post"

        # Create the final blog .txt
        timestamp = datetime.now().strftime("%Y-%m-%d")
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '-').lower()
        filename = f"{timestamp}-{safe_title}.txt"
        blog_path = self.blog_dir / filename

        blog_content = f"{title}\n{'=' * len(title)}\n\n{entries_text}\n"
        blog_path.write_text(blog_content)

        # Clear the draft
        draft_path.unlink(missing_ok=True)

        publish_hint = ""
        if self.publisher and self.publisher.targets:
            targets = ", ".join(self.publisher.targets.keys())
            publish_hint = (
                f"\n\nPublish remotely:\n"
                f"  'publish blog to <target>' (targets: {targets})"
            )

        return (
            f"Blog published!\n\n"
            f"Title: {title}\n"
            f"Saved to: {blog_path}\n\n"
            f"The blog is a plain .txt file you can share anywhere."
            f"{publish_hint}"
        )

    def _show_blogs(self, user_id: str) -> str:
        """Show existing blog posts and current draft."""
        lines = ["**Your Blog**", ""]

        # Check for draft
        draft_path = self._get_draft_path(user_id)
        if draft_path.exists():
            entry_count = self._count_entries(draft_path)
            lines.append(f"**Draft in progress:** {entry_count} entries")
            lines.append(f"  {draft_path}")
            lines.append("")

        # List published blogs
        blogs = sorted(self.blog_dir.glob("*.txt"))
        blogs = [b for b in blogs if not b.name.startswith("draft-")]

        if blogs:
            lines.append(f"**Published blogs:** ({len(blogs)} total)")
            for blog in blogs[-10:]:
                first_line = blog.read_text().split("\n", 1)[0]
                lines.append(f"  - {first_line} ({blog.name})")
        else:
            lines.append("No published blogs yet.")

        # Show publishing targets
        if self.publisher and self.publisher.targets:
            lines.extend(["", "**Publishing targets:**"])
            for label, t in self.publisher.targets.items():
                lines.append(f"  - {label} ({t.target_type.value})")
            lines.append("  setup blog publish list  — manage targets")
        else:
            lines.extend(["", "**No publish targets saved.**",
                          "  setup blog publish wp://mysite.com user pass  — add one"])

        # Show AI status
        if self.ai_writer and self.ai_writer.providers:
            active = self.ai_writer.get_active_provider()
            if active:
                lines.extend([
                    "",
                    f"**AI:** {active.provider.value}/{active.model} (active)",
                ])

        lines.extend([
            "",
            "**Commands:**",
            "  Manual: 'write blog news ...', 'crawl <url> for title content'",
            "  AI: 'ai blog generate about <topic>', 'ai rewrite blog'",
            "  Title: 'blog title', 'ai headlines'",
            "  Publish: 'publish blog', 'publish blog to <target>'",
            "  Front page: 'set front page <id> on <target>'",
        ])

        return "\n".join(lines)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_draft_path(self, user_id: str) -> Path:
        """Get the draft file path for a user."""
        safe_id = re.sub(r'[^\w]', '_', user_id)
        return self.blog_dir / f"draft-{safe_id}.txt"

    def _count_entries(self, draft_path: Path) -> int:
        """Count entries in a draft file."""
        if not draft_path.exists():
            return 0
        content = draft_path.read_text()
        return len(re.findall(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]', content))

    def _get_entries_text(self, content: str) -> str:
        """Extract just the text content from entries, stripping timestamps."""
        lines = []
        for line in content.split("\n"):
            if re.match(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]', line.strip()):
                continue
            if line.strip():
                lines.append(line.strip())
        return "\n".join(lines)

    def _extract_blog_content(self, raw_input: str) -> str:
        """Extract blog content from natural language input."""
        content = re.sub(
            r'(?i)^(write|add|post|create)\s+(blog\s+)?(news|entry|post|content)\s*',
            '',
            raw_input,
        )
        content = re.sub(
            r'(?i)^blog\s+(news|write|add|post)\s*',
            '',
            content,
        )
        return content.strip()

    def _compute_title(self, draft_path: Path) -> str:
        """Compute a title from draft content."""
        content = draft_path.read_text()
        entries_text = self._get_entries_text(content)
        if not entries_text.strip():
            return ""
        title = self.summarizer.summarize(entries_text, sentences=1).strip()
        if len(title) > 120:
            title = title[:117] + "..."
        return title

    def _help_text(self) -> str:
        """Return blog help text."""
        ai_section = ""
        if self.ai_writer and self.ai_writer.providers:
            active = self.ai_writer.get_active_provider()
            provider_info = f" (using {active.provider.value}/{active.model})" if active else ""
            ai_section = (
                f"\n**AI Blog Writing{provider_info}:**\n"
                "  ai blog generate about <topic>  - Generate a full post\n"
                "  ai rewrite blog                 - Rewrite/polish draft\n"
                "  ai expand blog                  - Expand into longer article\n"
                "  ai headlines                    - Generate headline options\n"
                "  ai blog seo                     - Generate SEO metadata\n"
                "  switch ai provider <label>      - Change AI provider\n"
            )
        else:
            ai_section = (
                "\n**AI Writing (not configured):**\n"
                "  ai options    - See local AI options (free, private)\n"
                "  ai providers  - See cloud AI providers and API key setup\n"
            )

        if self.publisher and self.publisher.targets:
            targets = ", ".join(self.publisher.targets.keys())
            publish_section = (
                f"\n**Saved publish targets ({targets}):**\n"
                "  publish blog to <target>              - Publish to a specific target\n"
                "  publish blog to all                   - Publish to all targets\n"
                "  setup blog publish list               - Show all saved targets\n"
                "  setup blog publish remove <label>     - Remove a target\n"
                "\n**One-off publish (not saved):**\n"
                "  publish blog to wp://mysite.com user pass\n"
                "  publish blog to sftp://host user pass /path\n"
            )
        else:
            publish_section = (
                "\n**Set up a publish target (saved — no config file needed):**\n"
                "  setup blog publish wp://mysite.com user app-password\n"
                "  setup blog publish sftp://host user pass\n"
                "  setup blog publish joomla://cms.example.com user token\n"
                "  setup blog publish api://api.example.com/posts api-key\n"
                "\n**Or publish one-off without saving:**\n"
                "  publish blog to wp://mysite.com user pass\n"
                "  publish blog to sftp://host:port user pass /path\n"
            )
        publish_section += (
            "\n  After any publish command you'll see a preview.\n"
            "  confirm / change title <new> / edit blog / cancel\n"
        )

        frontpage_section = ""
        if self.frontpage:
            frontpage_section = (
                "\n**Front page management:**\n"
                "  set front page <id> on <target> - Set front/home page\n"
                "  show front page                 - Show current front page\n"
                "  list pages for <target>         - List available pages\n"
            )

        return (
            "**Blog - AI-Powered Blogging with Multi-Platform Publishing**\n"
            "\n"
            "**Write blog entries (no AI):**\n"
            "  write blog news <content>         - Add manual entry\n"
            "  crawl <url> for title content      - Extract page titles\n"
            "  crawl <url> for body content       - Extract main content\n"
            "  crawl <url> for non-title content  - Extract non-heading text\n"
            f"{ai_section}"
            "\n"
            "**Generate title and publish locally:**\n"
            "  blog title                        - Generate title (extractive)\n"
            "  publish blog                      - Save as .txt locally\n"
            "  publish blog My Custom Title      - Save with custom title\n"
            f"{publish_section}"
            f"{frontpage_section}"
            "\n"
            "**View:**\n"
            "  show blog                         - See draft and published posts\n"
        )
