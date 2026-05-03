"""
SafestClaw Blog Scheduler - Cron-based auto-blogging without LLM.

Automatically publishes blog posts on a schedule using only
deterministic, non-AI content generation:

- Fetches content from configured RSS feeds
- Crawls specified source URLs
- Summarizes with sumy (extractive, no AI)
- Formats into blog post templates
- Publishes to configured targets

No LLM required. Runs on cron schedule via APScheduler.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from safestclaw.core.crawler import Crawler
from safestclaw.core.feeds import Feed, FeedReader
from safestclaw.core.summarizer import Summarizer, SummaryMethod

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

logger = logging.getLogger(__name__)


@dataclass
class AutoBlogConfig:
    """Configuration for an automatic blog schedule."""
    name: str
    cron_expr: str  # e.g. "0 9 * * *" for 9am daily
    enabled: bool = True

    # Content sources
    source_feeds: list[str] = field(default_factory=list)  # RSS feed URLs
    source_urls: list[str] = field(default_factory=list)    # URLs to crawl
    source_categories: list[str] = field(default_factory=list)  # Feed categories

    # Content settings
    summary_sentences: int = 5
    summary_method: str = "lexrank"
    max_items: int = 5
    include_source_links: bool = True

    # Template
    title_template: str = "{category} Roundup - {date}"
    post_template: str = "digest"  # digest, single, curated

    # Publishing
    publish_target: str = ""  # Specific target label, or empty for local
    auto_publish: bool = False  # Publish immediately or save as draft

    # Optional LLM enrichment. When `llm_enabled` is true the deterministic
    # draft is post-processed by the configured AI provider before
    # publishing. Source gathering + extractive summarisation still run
    # deterministically — the LLM only sees the finished draft, never the
    # internet directly.
    #
    # Modes:
    #   "rewrite"  — improve flow / readability of the deterministic draft
    #   "expand"   — same draft, expanded with examples and depth
    #   "generate" — drop the deterministic draft and write a brand-new
    #                post using the gathered items as context
    #   "headline" — keep the deterministic body, replace the title with an
    #                LLM-generated headline
    llm_enabled: bool = False
    llm_mode: str = "rewrite"
    llm_provider: str = ""        # provider label; empty = task_providers["blog"] or active
    llm_topic: str = ""           # only used when llm_mode == "generate"
    llm_system_prompt: str = ""   # optional system-prompt override

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "name": self.name,
            "cron_expr": self.cron_expr,
            "enabled": self.enabled,
            "source_feeds": self.source_feeds,
            "source_urls": self.source_urls,
            "source_categories": self.source_categories,
            "summary_sentences": self.summary_sentences,
            "summary_method": self.summary_method,
            "max_items": self.max_items,
            "include_source_links": self.include_source_links,
            "title_template": self.title_template,
            "post_template": self.post_template,
            "publish_target": self.publish_target,
            "auto_publish": self.auto_publish,
            "llm_enabled": self.llm_enabled,
            "llm_mode": self.llm_mode,
            "llm_provider": self.llm_provider,
            "llm_topic": self.llm_topic,
            "llm_system_prompt": self.llm_system_prompt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutoBlogConfig":
        """Deserialize from dict."""
        return cls(
            name=data.get("name", "auto-blog"),
            cron_expr=data.get("cron_expr", "0 9 * * 1"),
            enabled=data.get("enabled", True),
            source_feeds=data.get("source_feeds", []),
            source_urls=data.get("source_urls", []),
            source_categories=data.get("source_categories", ["tech"]),
            summary_sentences=data.get("summary_sentences", 5),
            summary_method=data.get("summary_method", "lexrank"),
            max_items=data.get("max_items", 5),
            include_source_links=data.get("include_source_links", True),
            title_template=data.get("title_template", "{category} Roundup - {date}"),
            post_template=data.get("post_template", "digest"),
            publish_target=data.get("publish_target", ""),
            auto_publish=data.get("auto_publish", False),
            llm_enabled=data.get("llm_enabled", False),
            llm_mode=data.get("llm_mode", "rewrite"),
            llm_provider=data.get("llm_provider", ""),
            llm_topic=data.get("llm_topic", ""),
            llm_system_prompt=data.get("llm_system_prompt", ""),
        )


class BlogScheduler:
    """
    Manages cron-based auto-blogging schedules.

    All content generation is deterministic (no LLM):
    - RSS feed aggregation
    - Web crawling for source material
    - Extractive summarization via sumy
    - Template-based post formatting
    """

    def __init__(self, engine: "SafestClaw"):
        self.engine = engine
        self._configs: dict[str, AutoBlogConfig] = {}
        self._summarizer = Summarizer()
        self._feed_reader = FeedReader(
            summarize_items=True,
            max_items_per_feed=10,
        )
        # Lazily built — only instantiated when an LLM-enabled schedule fires.
        self._ai_writer: Any = None

    def add_schedule(self, config: AutoBlogConfig) -> str:
        """
        Register an auto-blog schedule with the engine's scheduler.

        Returns a confirmation message.
        """
        self._configs[config.name] = config

        if config.enabled:
            # Verify scheduler uses AsyncIOScheduler (required for async cron jobs).
            # A lambda wrapping an async function is NOT detected by
            # inspect.iscoroutinefunction, so APScheduler would call it
            # synchronously and silently discard the unawaited coroutine.
            # We use a proper async def wrapper instead.
            scheduler_impl = getattr(self.engine.scheduler, "_scheduler", None)
            if scheduler_impl is not None:
                cls_name = type(scheduler_impl).__name__
                if "Async" not in cls_name:
                    msg = (
                        f"Auto-blog requires AsyncIOScheduler but found {cls_name}. "
                        "Cron jobs that call async functions will silently fail. "
                        "Switch to apscheduler.schedulers.asyncio.AsyncIOScheduler."
                    )
                    logger.error(msg)
                    return f"Auto-blog '{config.name}' NOT scheduled: {msg}"

            # Build a proper async callback so APScheduler detects it as
            # a coroutine function (inspect.iscoroutinefunction returns True).
            async def _cron_callback(
                _self: "BlogScheduler" = self,
                _cfg: AutoBlogConfig = config,
            ) -> None:
                await _self._execute_auto_blog(_cfg)

            self.engine.scheduler.add_cron(
                name=f"autoblog_{config.name}",
                func=_cron_callback,
                cron_expr=config.cron_expr,
            )
            logger.info(f"Scheduled auto-blog '{config.name}': {config.cron_expr}")
            return (
                f"Auto-blog '{config.name}' scheduled: {config.cron_expr}\n"
                f"Sources: {len(config.source_categories)} categories, "
                f"{len(config.source_feeds)} feeds, "
                f"{len(config.source_urls)} URLs\n"
                f"Template: {config.post_template}\n"
                f"Auto-publish: {'yes' if config.auto_publish else 'no (saves as draft)'}"
            )

        return f"Auto-blog '{config.name}' saved but disabled."

    def remove_schedule(self, name: str) -> bool:
        """Remove an auto-blog schedule."""
        if name in self._configs:
            self.engine.scheduler.remove_job(f"autoblog_{name}")
            del self._configs[name]
            return True
        return False

    def list_schedules(self) -> list[dict[str, Any]]:
        """List all auto-blog schedules."""
        result = []
        for name, config in self._configs.items():
            job = self.engine.scheduler.get_job(f"autoblog_{name}")
            result.append({
                "name": name,
                "cron": config.cron_expr,
                "enabled": config.enabled,
                "template": config.post_template,
                "next_run": str(job["next_run"]) if job else "not scheduled",
                "sources": (
                    f"{len(config.source_categories)} categories, "
                    f"{len(config.source_feeds)} feeds, "
                    f"{len(config.source_urls)} URLs"
                ),
            })
        return result

    async def _execute_auto_blog(self, config: AutoBlogConfig) -> None:
        """
        Execute an auto-blog job. Fetches content, summarizes, formats, optionally
        enriches with an LLM, then publishes.

        Source gathering and extractive summarisation are always deterministic
        — the LLM (when enabled) only sees the finished draft, never the
        internet directly. That keeps prompt-injection surface to a minimum.
        """
        logger.info(f"Executing auto-blog: {config.name}")

        try:
            # 1. Gather content from all sources (deterministic)
            content_items = await self._gather_content(config)

            if not content_items:
                logger.warning(f"Auto-blog '{config.name}': no content gathered")
                return

            # 2. Format into a deterministic blog post
            title, body = self._format_post(config, content_items)

            # 3. Optional LLM enrichment
            if config.llm_enabled:
                title, body = await self._llm_enrich(
                    config, title, body, content_items
                )

            # 4. Save or publish
            if config.auto_publish and config.publish_target:
                await self._publish_post(config, title, body)
            else:
                await self._save_draft(config, title, body)

            logger.info(f"Auto-blog '{config.name}' completed: {title}")

        except Exception as e:
            logger.error(f"Auto-blog '{config.name}' failed: {e}")

    # ------------------------------------------------------------------
    # LLM enrichment
    # ------------------------------------------------------------------

    def _resolve_llm_provider(self, config: AutoBlogConfig) -> str | None:
        """
        Pick the provider label to use for this schedule.

        Priority:
          1. Explicit `llm_provider` on the schedule
          2. `task_providers.blog` from the engine config
          3. The active provider on the AI writer
        """
        if config.llm_provider:
            return config.llm_provider
        task_providers = self.engine.config.get("task_providers") or {}
        blog_label = task_providers.get("blog")
        if blog_label:
            return blog_label
        return None  # AIWriter will fall back to its active provider

    def _get_ai_writer(self) -> Any:
        """Lazily build an AIWriter from engine config."""
        if self._ai_writer is None:
            from safestclaw.core.ai_writer import load_ai_writer_from_yaml
            self._ai_writer = load_ai_writer_from_yaml(self.engine.config)
        return self._ai_writer

    async def _llm_enrich(
        self,
        config: AutoBlogConfig,
        title: str,
        body: str,
        items: list[dict[str, str]],
    ) -> tuple[str, str]:
        """
        Run the deterministic draft (or the gathered items) through the AI
        writer. Returns ``(title, body)``. On any failure we fall back to
        the deterministic draft so the cron job still publishes something.
        """
        try:
            writer = self._get_ai_writer()
        except Exception as e:
            logger.warning(
                f"Auto-blog '{config.name}': AI writer init failed ({e}); "
                "falling back to deterministic draft."
            )
            return title, body

        if not writer.providers:
            logger.warning(
                f"Auto-blog '{config.name}': llm_enabled=true but no "
                "ai_providers configured. Falling back."
            )
            return title, body

        provider = self._resolve_llm_provider(config)
        mode = (config.llm_mode or "rewrite").lower().strip()
        system_prompt_override = (config.llm_system_prompt or "").strip()

        async def _call_template(template_name: str, **render_kwargs: str) -> Any:
            """
            Run a built-in BlogPromptTemplates entry through writer.generate
            with our optional system-prompt override. Falls back to the
            convenience helpers when no override is set so behaviour matches
            the chat-side `ai blog ...` commands by default.
            """
            if not system_prompt_override:
                # Use the convenience helpers — same code path as `ai blog`
                helper = {
                    "rewrite": writer.rewrite_blog,
                    "expand": writer.expand_blog,
                    "headline": writer.generate_headlines,
                }.get(template_name)
                if helper is not None:
                    arg = render_kwargs.get("content") or render_kwargs.get("body")
                    return await helper(arg, provider_label=provider)
            prompt = writer.templates.render(template_name, **render_kwargs)
            return await writer.generate(
                prompt,
                provider_label=provider,
                system_prompt=system_prompt_override
                or "You are a skilled blog writer. Write clear, engaging content.",
            )

        try:
            if mode == "rewrite":
                resp = await _call_template("rewrite", content=body)
                if resp.success and resp.content.strip():
                    return title, resp.content.strip()

            elif mode == "expand":
                resp = await _call_template("expand", content=body)
                if resp.success and resp.content.strip():
                    return title, resp.content.strip()

            elif mode == "headline":
                resp = await _call_template("headline", content=body)
                if resp.success and resp.content.strip():
                    headline = resp.content.strip().splitlines()[0].strip()
                    headline = headline.lstrip("0123456789.- ").strip('"').strip()
                    if headline:
                        return headline, body

            elif mode == "generate":
                topic = config.llm_topic or self._derive_topic(items)
                context = self._items_as_context(items)
                if system_prompt_override:
                    prompt = writer.templates.render(
                        "generate", topic=topic, context=context
                    )
                    resp = await writer.generate(
                        prompt,
                        provider_label=provider,
                        system_prompt=system_prompt_override,
                    )
                else:
                    resp = await writer.generate_blog(
                        topic=topic,
                        provider_label=provider,
                        context=context,
                    )
                if resp.success and resp.content.strip():
                    new_body = resp.content.strip()
                    if config.include_source_links:
                        new_body += "\n\n## Sources\n" + "\n".join(
                            f"- [{i.get('title', i.get('source', 'source'))}]"
                            f"({i.get('link', '')})"
                            for i in items if i.get("link")
                        )
                    return title, new_body

            else:
                logger.warning(
                    f"Auto-blog '{config.name}': unknown llm_mode '{mode}'; "
                    "using deterministic draft."
                )
                return title, body

            # Provider returned an error / empty body — keep the deterministic draft.
            err = getattr(resp, "error", "no content returned")
            logger.warning(
                f"Auto-blog '{config.name}': LLM mode '{mode}' produced "
                f"no usable output ({err}); falling back."
            )
        except Exception as e:
            logger.warning(
                f"Auto-blog '{config.name}': LLM enrichment failed ({e}); "
                "falling back to deterministic draft."
            )

        return title, body

    @staticmethod
    def _derive_topic(items: list[dict[str, str]]) -> str:
        """Best-effort topic line for `generate` mode when llm_topic is empty."""
        categories = [i.get("category") for i in items if i.get("category")]
        if categories:
            uniq = list(dict.fromkeys(categories))[:3]
            return f"Today in {', '.join(uniq)}"
        titles = [i.get("title", "") for i in items[:3]]
        return " · ".join(t for t in titles if t) or "Today's roundup"

    @staticmethod
    def _items_as_context(items: list[dict[str, str]]) -> str:
        """Render gathered items as a context block for `generate` mode."""
        lines: list[str] = []
        for i, item in enumerate(items, 1):
            lines.append(f"[{i}] {item.get('title', 'Untitled')}")
            summary = (item.get("summary") or "").strip()
            if summary:
                lines.append(f"    {summary}")
            link = item.get("link")
            if link:
                lines.append(f"    Source: {link}")
        return "\n".join(lines)

    async def _gather_content(
        self,
        config: AutoBlogConfig,
    ) -> list[dict[str, str]]:
        """Gather content from feeds, URLs, and categories."""
        items: list[dict[str, str]] = []

        # Fetch from categories
        for category in config.source_categories:
            try:
                feed_items = await self._feed_reader.fetch_category(category)
                for fi in feed_items[:config.max_items]:
                    text = fi.content or fi.description
                    if text:
                        summary = self._summarizer.summarize(
                            text,
                            sentences=config.summary_sentences,
                            method=SummaryMethod(config.summary_method),
                        )
                        items.append({
                            "title": fi.title,
                            "summary": summary,
                            "source": fi.feed_name,
                            "link": fi.link,
                            "category": category,
                        })
            except Exception as e:
                logger.error(f"Failed to fetch category '{category}': {e}")

        # Fetch from custom feed URLs
        for feed_url in config.source_feeds:
            try:
                feed = Feed(name="Custom", url=feed_url, category="custom")
                feed_items = await self._feed_reader.fetch_feed(feed)
                for fi in feed_items[:config.max_items]:
                    text = fi.content or fi.description
                    if text:
                        summary = self._summarizer.summarize(
                            text,
                            sentences=config.summary_sentences,
                        )
                        items.append({
                            "title": fi.title,
                            "summary": summary,
                            "source": fi.feed_name,
                            "link": fi.link,
                            "category": "custom",
                        })
            except Exception as e:
                logger.error(f"Failed to fetch feed '{feed_url}': {e}")

        # Crawl source URLs
        for url in config.source_urls:
            try:
                async with Crawler() as crawler:
                    result = await crawler.fetch(url)
                if result.text and not result.error:
                    summary = self._summarizer.summarize(
                        result.text,
                        sentences=config.summary_sentences,
                    )
                    items.append({
                        "title": result.title or url,
                        "summary": summary,
                        "source": url,
                        "link": url,
                        "category": "crawled",
                    })
            except Exception as e:
                logger.error(f"Failed to crawl '{url}': {e}")

        return items[:config.max_items * 3]  # Cap total items

    def _format_post(
        self,
        config: AutoBlogConfig,
        items: list[dict[str, str]],
    ) -> tuple[str, str]:
        """Format gathered content into a blog post. No LLM needed."""
        date_str = datetime.now().strftime("%B %d, %Y")
        categories = list({item.get("category", "general") for item in items})
        category_str = ", ".join(categories) if categories else "General"

        # Generate title from template
        title = config.title_template.format(
            category=category_str.title(),
            date=date_str,
            count=len(items),
        )

        # Format body based on template type
        if config.post_template == "digest":
            body = self._format_digest(items, config)
        elif config.post_template == "single":
            body = self._format_single(items, config)
        elif config.post_template == "curated":
            body = self._format_curated(items, config)
        else:
            body = self._format_digest(items, config)

        return title, body

    def _format_digest(
        self,
        items: list[dict[str, str]],
        config: AutoBlogConfig,
    ) -> str:
        """Format as a news digest with multiple items."""
        sections = [f"Here's what's noteworthy for {datetime.now().strftime('%B %d, %Y')}.\n"]

        current_category = None
        for item in items:
            category = item.get("category", "general")
            if category != current_category:
                current_category = category
                sections.append(f"\n## {category.title()}\n")

            sections.append(f"### {item['title']}\n")
            sections.append(f"{item['summary']}\n")
            if config.include_source_links and item.get("link"):
                sections.append(f"Source: {item['link']}\n")

        return "\n".join(sections)

    def _format_single(
        self,
        items: list[dict[str, str]],
        config: AutoBlogConfig,
    ) -> str:
        """Format around a single primary item with supporting context."""
        if not items:
            return ""

        primary = items[0]
        sections = [
            f"{primary['summary']}\n",
        ]

        if len(items) > 1:
            sections.append("\n## Related\n")
            for item in items[1:5]:
                sections.append(f"- **{item['title']}**: {item['summary'][:150]}...")
                if config.include_source_links and item.get("link"):
                    sections.append(f"  [{item.get('source', 'Source')}]({item['link']})")
                sections.append("")

        return "\n".join(sections)

    def _format_curated(
        self,
        items: list[dict[str, str]],
        config: AutoBlogConfig,
    ) -> str:
        """Format as a curated list with brief commentary."""
        sections = [
            "A curated selection of what caught our attention.\n",
        ]

        for i, item in enumerate(items, 1):
            sections.append(f"**{i}. {item['title']}**\n")
            # Use first sentence as the "editorial comment"
            first_sentence = item["summary"].split(".")[0] + "."
            sections.append(f"> {first_sentence}\n")
            if config.include_source_links and item.get("link"):
                sections.append(f"[Read more]({item['link']})\n")

        return "\n".join(sections)

    async def _publish_post(
        self,
        config: AutoBlogConfig,
        title: str,
        body: str,
    ) -> None:
        """Publish to configured target."""
        # Import here to avoid circular imports
        from safestclaw.core.blog_publisher import BlogPublisher

        publisher = BlogPublisher.from_config(self.engine.config)
        results = await publisher.publish(
            title=title,
            content=body,
            target_label=config.publish_target or None,
            slug=re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '-').lower(),
        )

        for result in results:
            if result.success:
                logger.info(f"Auto-blog published: {result.message}")
            else:
                logger.error(f"Auto-blog publish failed: {result.error}")

    async def _save_draft(
        self,
        config: AutoBlogConfig,
        title: str,
        body: str,
    ) -> None:
        """Save as local draft."""
        blog_dir = self.engine.data_dir / "blog" / "drafts"
        blog_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        slug = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '-').lower()
        filename = f"{timestamp}-{slug}.md"

        filepath = blog_dir / filename
        filepath.write_text(f"# {title}\n\n{body}")
        logger.info(f"Auto-blog draft saved: {filepath}")

    @classmethod
    def from_config(cls, engine: "SafestClaw") -> "BlogScheduler":
        """Create BlogScheduler from engine config."""
        scheduler = cls(engine)

        auto_blogs = engine.config.get("auto_blogs", [])
        for blog_config in auto_blogs:
            config = AutoBlogConfig.from_dict(blog_config)
            scheduler.add_schedule(config)

        return scheduler
