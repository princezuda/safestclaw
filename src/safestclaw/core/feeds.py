"""
SafestClaw RSS Feed Reader - Fetch and parse RSS/Atom feeds.

No AI required - uses feedparser for parsing, sumy for summarization.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from typing import Any

import feedparser
import httpx

from safestclaw.core.crawler import Crawler
from safestclaw.core.summarizer import Summarizer, SummaryMethod

logger = logging.getLogger(__name__)


@dataclass
class FeedItem:
    """A single item from an RSS feed."""
    title: str
    link: str
    description: str = ""
    published: datetime | None = None
    author: str = ""
    feed_name: str = ""
    feed_category: str = ""
    content: str = ""  # Full article content if fetched
    summary: str = ""  # Summarized content


@dataclass
class Feed:
    """RSS/Atom feed configuration."""
    name: str
    url: str
    category: str = "general"
    enabled: bool = True
    update_interval: int = 3600  # seconds
    last_fetched: datetime | None = None
    etag: str = ""
    modified: str = ""


# Preset news sources organized by category
PRESET_FEEDS: dict[str, list[Feed]] = {
    "tech": [
        Feed("Hacker News", "https://news.ycombinator.com/rss", "tech"),
        Feed("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab", "tech"),
        Feed("The Verge", "https://www.theverge.com/rss/index.xml", "tech"),
        Feed("TechCrunch", "https://techcrunch.com/feed/", "tech"),
        Feed("Wired", "https://www.wired.com/feed/rss", "tech"),
        Feed("MIT Tech Review", "https://www.technologyreview.com/feed/", "tech"),
    ],
    "world": [
        Feed("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml", "world"),
        Feed("Reuters World", "https://www.reutersagency.com/feed/?taxonomy=best-regions&post_type=best", "world"),
        Feed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "world"),
        Feed("NPR News", "https://feeds.npr.org/1001/rss.xml", "world"),
        Feed("The Guardian World", "https://www.theguardian.com/world/rss", "world"),
    ],
    "science": [
        Feed("Science Daily", "https://www.sciencedaily.com/rss/all.xml", "science"),
        Feed("Nature News", "https://www.nature.com/nature.rss", "science"),
        Feed("Phys.org", "https://phys.org/rss-feed/", "science"),
        Feed("NASA Breaking", "https://www.nasa.gov/rss/dyn/breaking_news.rss", "science"),
        Feed("New Scientist", "https://www.newscientist.com/feed/home/", "science"),
    ],
    "business": [
        Feed("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", "business"),
        Feed("Financial Times", "https://www.ft.com/rss/home", "business"),
        Feed("CNBC Top", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "business"),
        Feed("Economist", "https://www.economist.com/finance-and-economics/rss.xml", "business"),
    ],
    "programming": [
        Feed("Dev.to", "https://dev.to/feed", "programming"),
        Feed("Lobsters", "https://lobste.rs/rss", "programming"),
        Feed("Reddit Programming", "https://www.reddit.com/r/programming/.rss", "programming"),
        Feed("CSS Tricks", "https://css-tricks.com/feed/", "programming"),
        Feed("Martin Fowler", "https://martinfowler.com/feed.atom", "programming"),
    ],
    "security": [
        Feed("Krebs on Security", "https://krebsonsecurity.com/feed/", "security"),
        Feed("Schneier on Security", "https://www.schneier.com/feed/atom/", "security"),
        Feed("The Hacker News", "https://feeds.feedburner.com/TheHackersNews", "security"),
        Feed("Dark Reading", "https://www.darkreading.com/rss.xml", "security"),
    ],
    "linux": [
        Feed("Phoronix", "https://www.phoronix.com/rss.php", "linux"),
        Feed("OMG Ubuntu", "https://www.omgubuntu.co.uk/feed", "linux"),
        Feed("LWN.net", "https://lwn.net/headlines/rss", "linux"),
        Feed("It's FOSS", "https://itsfoss.com/feed/", "linux"),
    ],
    "ai": [
        Feed("AI News", "https://www.artificialintelligence-news.com/feed/", "ai"),
        Feed("The Batch (DeepLearning)", "https://www.deeplearning.ai/the-batch/feed/", "ai"),
        Feed("MIT AI News", "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml", "ai"),
        Feed("Google AI Blog", "https://blog.google/technology/ai/rss/", "ai"),
    ],
}


class FeedReader:
    """
    Async RSS/Atom feed reader with caching and summarization.

    Features:
    - Fetch multiple feeds concurrently
    - ETag/Last-Modified support for efficient updates
    - Built-in caching
    - Automatic summarization with sumy
    - Preset feed categories
    """

    def __init__(
        self,
        cache_ttl: int = 1800,  # 30 minutes
        timeout: float = 30.0,
        max_items_per_feed: int = 10,
        summarize_items: bool = True,
        summary_sentences: int = 3,
    ):
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.max_items_per_feed = max_items_per_feed
        self.summarize_items = summarize_items
        self.summary_sentences = summary_sentences

        self.summarizer = Summarizer(default_method=SummaryMethod.LEXRANK)
        self.crawler = Crawler()

        # Cache: url -> (items, timestamp)
        self._cache: dict[str, tuple[list[FeedItem], datetime]] = {}

        # User's custom feeds
        self.custom_feeds: list[Feed] = []

        # Enabled preset categories
        self.enabled_categories: set[str] = {"tech"}

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        clean = unescape(clean)
        # Normalize whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _parse_date(self, entry: dict) -> datetime | None:
        """Parse date from feed entry."""
        for key in ['published_parsed', 'updated_parsed', 'created_parsed']:
            if key in entry and entry[key]:
                try:
                    return datetime(*entry[key][:6])
                except (TypeError, ValueError):
                    pass
        return None

    async def fetch_feed(self, feed: Feed) -> list[FeedItem]:
        """Fetch a single RSS feed."""
        # Check cache
        cache_key = feed.url
        if cache_key in self._cache:
            items, cached_at = self._cache[cache_key]
            if datetime.now() - cached_at < timedelta(seconds=self.cache_ttl):
                return items

        items: list[FeedItem] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {}
                if feed.etag:
                    headers["If-None-Match"] = feed.etag
                if feed.modified:
                    headers["If-Modified-Since"] = feed.modified

                response = await client.get(feed.url, headers=headers)

                # Not modified
                if response.status_code == 304:
                    if cache_key in self._cache:
                        return self._cache[cache_key][0]
                    return []

                if response.status_code != 200:
                    logger.warning(f"Feed {feed.name} returned {response.status_code}")
                    return []

                # Update etag/modified
                if "etag" in response.headers:
                    feed.etag = response.headers["etag"]
                if "last-modified" in response.headers:
                    feed.modified = response.headers["last-modified"]

                # Parse feed
                parsed = feedparser.parse(response.text)

                for entry in parsed.entries[:self.max_items_per_feed]:
                    # Get description/summary
                    description = ""
                    if hasattr(entry, 'summary'):
                        description = self._clean_html(entry.summary)
                    elif hasattr(entry, 'description'):
                        description = self._clean_html(entry.description)

                    # Get content if available
                    content = ""
                    if hasattr(entry, 'content') and entry.content:
                        content = self._clean_html(entry.content[0].get('value', ''))

                    item = FeedItem(
                        title=entry.get('title', 'No title'),
                        link=entry.get('link', ''),
                        description=description[:500],  # Truncate long descriptions
                        published=self._parse_date(entry),
                        author=entry.get('author', ''),
                        feed_name=feed.name,
                        feed_category=feed.category,
                        content=content,
                    )

                    # Generate summary if enabled
                    if self.summarize_items and (content or description):
                        text_to_summarize = content or description
                        if len(text_to_summarize) > 200:  # Only summarize longer texts
                            item.summary = self.summarizer.summarize(
                                text_to_summarize,
                                sentences=self.summary_sentences,
                            )

                    items.append(item)

                feed.last_fetched = datetime.now()

        except Exception as e:
            logger.error(f"Error fetching feed {feed.name}: {e}")

        # Update cache
        self._cache[cache_key] = (items, datetime.now())

        return items

    async def fetch_feeds(self, feeds: list[Feed]) -> list[FeedItem]:
        """Fetch multiple feeds concurrently."""
        tasks = [self.fetch_feed(feed) for feed in feeds if feed.enabled]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[FeedItem] = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Feed fetch error: {result}")

        # Sort by date (newest first)
        all_items.sort(
            key=lambda x: x.published or datetime.min,
            reverse=True,
        )

        return all_items

    async def fetch_category(self, category: str) -> list[FeedItem]:
        """Fetch all feeds in a category."""
        feeds = PRESET_FEEDS.get(category, [])
        return await self.fetch_feeds(feeds)

    async def fetch_all_enabled(self) -> list[FeedItem]:
        """Fetch all enabled preset categories + custom feeds."""
        feeds: list[Feed] = []

        # Add preset feeds from enabled categories
        for category in self.enabled_categories:
            feeds.extend(PRESET_FEEDS.get(category, []))

        # Add custom feeds
        feeds.extend(self.custom_feeds)

        return await self.fetch_feeds(feeds)

    def add_custom_feed(
        self,
        name: str,
        url: str,
        category: str = "custom",
    ) -> Feed:
        """Add a custom RSS feed."""
        feed = Feed(name=name, url=url, category=category)
        self.custom_feeds.append(feed)
        return feed

    def remove_custom_feed(self, name_or_url: str) -> bool:
        """Remove a custom feed by name or URL."""
        for i, feed in enumerate(self.custom_feeds):
            if feed.name == name_or_url or feed.url == name_or_url:
                self.custom_feeds.pop(i)
                return True
        return False

    def list_custom_feeds(self) -> list[Feed]:
        """List all custom feeds."""
        return self.custom_feeds.copy()

    def enable_category(self, category: str) -> bool:
        """Enable a preset category."""
        if category in PRESET_FEEDS:
            self.enabled_categories.add(category)
            return True
        return False

    def disable_category(self, category: str) -> bool:
        """Disable a preset category."""
        if category in self.enabled_categories:
            self.enabled_categories.remove(category)
            return True
        return False

    def list_categories(self) -> dict[str, dict[str, Any]]:
        """List all available categories with their feeds."""
        result = {}
        for category, feeds in PRESET_FEEDS.items():
            result[category] = {
                "enabled": category in self.enabled_categories,
                "feeds": [{"name": f.name, "url": f.url} for f in feeds],
                "count": len(feeds),
            }
        return result

    async def fetch_and_summarize_article(self, url: str) -> FeedItem | None:
        """Fetch full article content and summarize it."""
        async with Crawler() as crawler:
            result = await crawler.fetch(url)

        if result.error or not result.text:
            return None

        summary = self.summarizer.summarize(
            result.text,
            sentences=self.summary_sentences * 2,  # Longer summary for full articles
        )

        return FeedItem(
            title=result.title or url,
            link=url,
            description=result.text[:500],
            content=result.text,
            summary=summary,
        )

    def clear_cache(self) -> None:
        """Clear the feed cache."""
        self._cache.clear()
