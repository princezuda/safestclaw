"""Web crawling action."""

from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction
from safestclaw.core.crawler import Crawler

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class CrawlAction(BaseAction):
    """
    Web crawling and link extraction.

    Features:
    - Single page link extraction
    - Multi-page crawling with depth limit
    - Domain filtering
    - Pattern matching
    """

    name = "crawl"
    description = "Crawl websites and extract links"

    def __init__(
        self,
        max_depth: int = 2,
        max_pages: int = 50,
        rate_limit: float = 1.0,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.rate_limit = rate_limit

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute crawl action."""
        url = params.get("url", "")

        if not url:
            # Check entities for URLs
            urls = params.get("urls", [])
            if urls:
                url = urls[0]

        if not url:
            return "Please specify a URL to crawl"

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        depth = params.get("depth", 0)
        same_domain = params.get("same_domain", True)
        pattern = params.get("pattern")

        if depth == 0:
            # Single page - just get links
            return await self._get_links(url, same_domain, pattern, engine)
        else:
            # Multi-page crawl
            return await self._crawl_site(url, depth, same_domain, pattern, engine)

    async def _get_links(
        self,
        url: str,
        same_domain: bool,
        pattern: str | None,
        engine: "SafestClaw",
    ) -> str:
        """Get links from a single page."""
        async with Crawler(rate_limit=self.rate_limit) as crawler:
            # Fetch the page content and extract links
            result = await crawler.fetch(url)
            links = result.links

            # Filter by domain if requested
            if same_domain:
                from urllib.parse import urlparse
                start_domain = urlparse(url).netloc
                links = [link for link in links if urlparse(link).netloc == start_domain]

            # Filter by pattern if provided
            if pattern:
                import re
                pattern_re = re.compile(pattern)
                links = [link for link in links if pattern_re.search(link)]

        if not links:
            return f"No links found on {url}"

        # Cache the result (outside context is fine - no HTTP calls)
        await engine.memory.cache_crawl(
            url=url,
            content=result.text,
            links=links,
        )

        # Format output
        lines = [f"**Links from {url}:**", ""]

        # Group by domain if showing external links
        if not same_domain:
            from urllib.parse import urlparse
            by_domain: dict[str, list[str]] = {}
            for link in links[:100]:
                domain = urlparse(link).netloc
                by_domain.setdefault(domain, []).append(link)

            for domain, domain_links in sorted(by_domain.items()):
                lines.append(f"**{domain}** ({len(domain_links)} links)")
                for link in domain_links[:10]:
                    lines.append(f"  • {link}")
                if len(domain_links) > 10:
                    lines.append(f"  ... and {len(domain_links) - 10} more")
                lines.append("")
        else:
            for link in links[:50]:
                lines.append(f"• {link}")
            if len(links) > 50:
                lines.append(f"... and {len(links) - 50} more")

        return "\n".join(lines)

    async def _crawl_site(
        self,
        url: str,
        depth: int,
        same_domain: bool,
        pattern: str | None,
        engine: "SafestClaw",
    ) -> str:
        """Crawl multiple pages."""
        crawler = Crawler(
            max_depth=min(depth, self.max_depth),
            max_pages=self.max_pages,
            rate_limit=self.rate_limit,
        )

        results = await crawler.crawl(
            start_url=url,
            same_domain=same_domain,
            pattern=pattern,
        )

        if not results:
            return f"Could not crawl {url}"

        # Collect all links
        all_links: set[str] = set()
        for result in results:
            all_links.update(result.links)

        # Cache results
        for result in results:
            await engine.memory.cache_crawl(
                url=result.url,
                content=result.text,
                links=result.links,
            )

        # Format output
        lines = [
            f"**Crawl results for {url}:**",
            f"• Pages crawled: {len(results)}",
            f"• Total links found: {len(all_links)}",
            f"• Max depth: {depth}",
            "",
            "**Pages:**",
        ]

        for result in results[:20]:
            status = "✓" if not result.error else f"✗ {result.error}"
            title = result.title or result.url
            lines.append(f"  [{result.depth}] {status} {title}")

        if len(results) > 20:
            lines.append(f"  ... and {len(results) - 20} more pages")

        return "\n".join(lines)
