"""News aggregation and RSS feed action."""

from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction
from safestclaw.core.feeds import PRESET_FEEDS, Feed, FeedReader

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class NewsAction(BaseAction):
    """
    News aggregation from RSS feeds.

    Features:
    - Fetch news from preset categories (tech, world, science, etc.)
    - Add/remove custom RSS feeds
    - Automatic summarization of articles
    - Per-user feed preferences
    """

    name = "news"
    description = "Fetch and summarize news from RSS feeds"

    def __init__(
        self,
        default_limit: int = 10,
        summary_sentences: int = 2,
    ):
        self.default_limit = default_limit
        self.feed_reader = FeedReader(
            summary_sentences=summary_sentences,
            summarize_items=True,
        )

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute news action."""
        subcommand = params.get("subcommand", "fetch")
        category = params.get("category")
        limit = params.get("limit", self.default_limit)

        # Load user preferences
        await self._load_user_prefs(user_id, engine)

        if subcommand == "fetch":
            return await self._fetch_news(category, limit, engine)
        elif subcommand == "categories":
            return self._list_categories()
        elif subcommand == "enable":
            return await self._enable_category(category, user_id, engine)
        elif subcommand == "disable":
            return await self._disable_category(category, user_id, engine)
        elif subcommand == "add":
            url = params.get("url", "")
            name = params.get("name", "Custom Feed")
            return await self._add_feed(name, url, user_id, engine)
        elif subcommand == "remove":
            target = params.get("target", "")
            return await self._remove_feed(target, user_id, engine)
        elif subcommand == "list":
            return self._list_feeds()
        elif subcommand == "read":
            url = params.get("url", "")
            return await self._read_article(url)
        else:
            return await self._fetch_news(category, limit, engine)

    async def _load_user_prefs(self, user_id: str, engine: "SafestClaw") -> None:
        """Load user's feed preferences."""
        prefs = await engine.memory.get_preference(user_id, "news_feeds", {})

        # Load enabled categories
        if "categories" in prefs:
            self.feed_reader.enabled_categories = set(prefs["categories"])

        # Load custom feeds
        if "custom_feeds" in prefs:
            self.feed_reader.custom_feeds = [
                Feed(**f) for f in prefs["custom_feeds"]
            ]

    async def _save_user_prefs(self, user_id: str, engine: "SafestClaw") -> None:
        """Save user's feed preferences."""
        prefs = {
            "categories": list(self.feed_reader.enabled_categories),
            "custom_feeds": [
                {"name": f.name, "url": f.url, "category": f.category}
                for f in self.feed_reader.custom_feeds
            ],
        }
        await engine.memory.set_preference(user_id, "news_feeds", prefs)

    async def _fetch_news(
        self,
        category: str | None,
        limit: int,
        engine: "SafestClaw",
    ) -> str:
        """Fetch news from feeds."""
        if category:
            if category not in PRESET_FEEDS:
                return f"Unknown category: {category}. Use 'news categories' to see available options."
            items = await self.feed_reader.fetch_category(category)
        else:
            items = await self.feed_reader.fetch_all_enabled()

        if not items:
            return "No news items found. Try enabling more categories with 'news enable <category>'"

        items = items[:limit]

        lines = ["**📰 News Headlines**", ""]

        current_category = None
        for item in items:
            # Add category header if changed
            if item.feed_category != current_category:
                current_category = item.feed_category
                lines.append(f"### {current_category.title()}")
                lines.append("")

            # Format item
            time_str = ""
            if item.published:
                time_str = item.published.strftime(" • %b %d")

            lines.append(f"**{item.title}**")
            lines.append(f"_{item.feed_name}{time_str}_")

            # Add summary or description
            if item.summary:
                lines.append(f"> {item.summary}")
            elif item.description:
                lines.append(f"> {item.description[:200]}...")

            lines.append(f"[Read more]({item.link})")
            lines.append("")

        return "\n".join(lines)

    def _list_categories(self) -> str:
        """List available news categories."""
        categories = self.feed_reader.list_categories()

        lines = ["**📂 News Categories**", ""]

        for name, info in sorted(categories.items()):
            status = "✅" if info["enabled"] else "⬜"
            lines.append(f"{status} **{name}** ({info['count']} feeds)")

            # List feeds in category
            for feed in info["feeds"][:3]:
                lines.append(f"   • {feed['name']}")
            if len(info["feeds"]) > 3:
                lines.append(f"   • ... and {len(info['feeds']) - 3} more")
            lines.append("")

        lines.append("Use `news enable <category>` or `news disable <category>` to toggle.")

        return "\n".join(lines)

    async def _enable_category(
        self,
        category: str | None,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """Enable a news category."""
        if not category:
            return "Please specify a category to enable."

        if self.feed_reader.enable_category(category):
            await self._save_user_prefs(user_id, engine)
            count = len(PRESET_FEEDS.get(category, []))
            return f"✅ Enabled **{category}** ({count} feeds)"
        else:
            available = ", ".join(PRESET_FEEDS.keys())
            return f"Unknown category: {category}. Available: {available}"

    async def _disable_category(
        self,
        category: str | None,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """Disable a news category."""
        if not category:
            return "Please specify a category to disable."

        if self.feed_reader.disable_category(category):
            await self._save_user_prefs(user_id, engine)
            return f"⬜ Disabled **{category}**"
        else:
            return f"Category not enabled: {category}"

    async def _add_feed(
        self,
        name: str,
        url: str,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """Add a custom RSS feed."""
        if not url:
            return "Please provide an RSS feed URL."

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Validate by fetching
        test_feed = Feed(name=name, url=url, category="custom")
        items = await self.feed_reader.fetch_feed(test_feed)

        if not items:
            return f"Could not fetch any items from {url}. Is it a valid RSS feed?"

        # Add to custom feeds
        self.feed_reader.add_custom_feed(name, url)
        await self._save_user_prefs(user_id, engine)

        return f"✅ Added custom feed: **{name}**\n   {url}\n   Found {len(items)} items"

    async def _remove_feed(
        self,
        target: str,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """Remove a custom RSS feed."""
        if not target:
            return "Please specify a feed name or URL to remove."

        if self.feed_reader.remove_custom_feed(target):
            await self._save_user_prefs(user_id, engine)
            return f"✅ Removed custom feed: {target}"
        else:
            return f"Feed not found: {target}"

    def _list_feeds(self) -> str:
        """List all configured feeds."""
        lines = ["**📑 Your News Feeds**", ""]

        # Enabled categories
        lines.append("**Enabled Categories:**")
        if self.feed_reader.enabled_categories:
            for cat in sorted(self.feed_reader.enabled_categories):
                count = len(PRESET_FEEDS.get(cat, []))
                lines.append(f"  • {cat} ({count} feeds)")
        else:
            lines.append("  (none)")
        lines.append("")

        # Custom feeds
        lines.append("**Custom Feeds:**")
        if self.feed_reader.custom_feeds:
            for feed in self.feed_reader.custom_feeds:
                lines.append(f"  • {feed.name}: {feed.url}")
        else:
            lines.append("  (none - use `news add <url>` to add)")

        return "\n".join(lines)

    async def _read_article(self, url: str) -> str:
        """Fetch and summarize a full article."""
        if not url:
            return "Please provide an article URL to read."

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        item = await self.feed_reader.fetch_and_summarize_article(url)

        if not item:
            return f"Could not fetch article: {url}"

        lines = [
            f"**{item.title}**",
            "",
            "**Summary:**",
            item.summary,
            "",
            f"[Read full article]({item.link})",
        ]

        return "\n".join(lines)
