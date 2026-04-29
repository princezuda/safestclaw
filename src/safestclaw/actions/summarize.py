"""Summarization action using sumy."""

from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction
from safestclaw.core.crawler import Crawler
from safestclaw.core.summarizer import Summarizer, SummaryMethod

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class SummarizeAction(BaseAction):
    """
    Summarize text or web pages using extractive summarization.

    No AI required - uses sumy's mathematical algorithms.
    """

    name = "summarize"
    description = "Summarize text or URLs"

    def __init__(
        self,
        default_sentences: int = 5,
        default_method: SummaryMethod = SummaryMethod.LEXRANK,
    ):
        self.default_sentences = default_sentences
        self.summarizer = Summarizer(default_method=default_method)
        self.crawler = Crawler()

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute summarization."""
        target = params.get("target", "")

        if not target:
            return "Please specify text or a URL to summarize"

        # Check if target is a URL
        if target.startswith(("http://", "https://")):
            return await self._summarize_url(target, params, engine)
        else:
            return await self._summarize_text(target, params)

    async def _summarize_url(
        self,
        url: str,
        params: dict[str, Any],
        engine: "SafestClaw",
    ) -> str:
        """Summarize content from a URL."""
        # Check cache first
        cached = await engine.memory.get_cached_crawl(url)
        if cached and cached.get("summary"):
            return f"**Summary of {url}:**\n\n{cached['summary']}"

        # Fetch the page
        async with Crawler() as crawler:
            result = await crawler.fetch(url)

        if result.error:
            return f"Failed to fetch URL: {result.error}"

        if not result.text:
            return "No text content found on the page"

        # Summarize
        sentences = params.get("sentences", self.default_sentences)
        method = params.get("method", SummaryMethod.LEXRANK)

        summary = self.summarizer.summarize(result.text, sentences, method)

        # Cache the result
        await engine.memory.cache_crawl(
            url=url,
            content=result.text,
            links=result.links,
            summary=summary,
        )

        # Format response
        title = result.title or url
        return f"**{title}**\n\n{summary}"

    async def _summarize_text(
        self,
        text: str,
        params: dict[str, Any],
    ) -> str:
        """Summarize provided text."""
        sentences = params.get("sentences", self.default_sentences)
        method = params.get("method", SummaryMethod.LEXRANK)

        summary = self.summarizer.summarize(text, sentences, method)

        return f"**Summary:**\n\n{summary}"
