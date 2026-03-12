"""
SafeClaw Research Action - Web search + summarization + LLM deep dive.

Two-phase research pipeline:

Phase 1 (Non-LLM):
- Web search via RSS/crawl (no API key needed)
- Fetch and extract content from URLs
- Summarize with sumy (extractive, no AI)
- Present sources to user for selection

Phase 2 (LLM, optional):
- User selects which sources to research in depth
- LLM analyzes and synthesizes selected sources
- Uses the research-specific LLM provider (per-task routing)

This gives users $0 research for quick lookups and LLM-powered
deep analysis only when they choose to use it.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from safeclaw.actions.base import BaseAction
from safeclaw.core.crawler import Crawler
from safeclaw.core.feeds import FeedReader
from safeclaw.core.summarizer import Summarizer

if TYPE_CHECKING:
    from safeclaw.core.engine import SafeClaw

logger = logging.getLogger(__name__)


@dataclass
class ResearchSource:
    """A single research source with extracted content."""
    title: str
    url: str
    content: str = ""
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    selected: bool = False


@dataclass
class ResearchSession:
    """Tracks an active research session for a user."""
    topic: str
    sources: list[ResearchSource] = field(default_factory=list)
    phase: str = "gathering"  # gathering, selecting, analyzing, complete
    deep_analysis: str = ""
    selected_indices: list[int] = field(default_factory=list)


class ResearchAction(BaseAction):
    """
    Two-phase research: non-LLM discovery + optional LLM deep dive.

    Commands:
        research <topic>           - Start research on a topic
        research url <url>         - Research a specific URL
        research select <1,2,3>    - Select sources for deep analysis
        research analyze           - Run LLM deep analysis on selected sources
        research sources           - Show gathered sources
        research results           - Show research results
        research help              - Show research commands
    """

    name = "research"
    description = "Web research with optional AI deep dive"

    def __init__(self):
        self._sessions: dict[str, ResearchSession] = {}
        self._summarizer = Summarizer()
        self._feed_reader = FeedReader(
            summarize_items=True,
            max_items_per_feed=5,
        )

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafeClaw",
    ) -> str:
        """Execute research action."""
        raw = params.get("raw_input", "").strip()

        # Parse subcommand
        lower = raw.lower()

        if "research help" in lower or lower == "research":
            return self._help()

        if "research url" in lower:
            # Research a specific URL
            urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', raw)
            if urls:
                return await self._research_url(urls[0], user_id, engine)
            return "Please provide a URL: research url https://example.com"

        if "research select" in lower:
            # Select sources for deep analysis
            numbers = re.findall(r'\d+', raw.split("select", 1)[-1])
            if numbers:
                indices = [int(n) - 1 for n in numbers]  # Convert to 0-indexed
                return self._select_sources(user_id, indices)
            return "Specify source numbers: research select 1,2,3"

        if "research analyze" in lower or "research deep" in lower:
            return await self._deep_analyze(user_id, engine)

        if "research sources" in lower:
            return self._show_sources(user_id)

        if "research results" in lower:
            return self._show_results(user_id)

        # Default: start research on a topic
        topic = raw
        for prefix in ["research", "look up", "find out about", "search for"]:
            if lower.startswith(prefix):
                topic = raw[len(prefix):].strip()
                break

        if topic:
            return await self._start_research(topic, user_id, engine)

        return self._help()

    async def _start_research(
        self,
        topic: str,
        user_id: str,
        engine: "SafeClaw",
    ) -> str:
        """
        Phase 1: Gather sources on a topic using non-LLM methods.

        - Search RSS feeds for relevant articles
        - Crawl top results
        - Summarize each with sumy
        """
        session = ResearchSession(topic=topic)
        self._sessions[user_id] = session

        lines = [f"**Researching: {topic}**", "", "Gathering sources (no LLM)...", ""]

        # 1. Search RSS feeds for the topic
        try:
            all_items = await self._feed_reader.fetch_all_enabled()
            topic_words = set(topic.lower().split())

            relevant = []
            for item in all_items:
                title_words = set(item.title.lower().split())
                desc_words = set((item.description or "").lower().split())
                overlap = topic_words & (title_words | desc_words)
                if overlap:
                    relevant.append((len(overlap), item))

            # Sort by relevance (most keyword overlap first)
            relevant.sort(key=lambda x: x[0], reverse=True)

            for _, item in relevant[:8]:
                text = item.content or item.description
                summary = ""
                if text and len(text) > 100:
                    summary = self._summarizer.summarize(text, sentences=3)

                keywords = self._summarizer.get_keywords(text, top_n=5) if text else []

                session.sources.append(ResearchSource(
                    title=item.title,
                    url=item.link,
                    content=text or "",
                    summary=summary or item.description[:200],
                    keywords=keywords,
                ))
        except Exception as e:
            logger.error(f"RSS search failed: {e}")

        # 2. If we have URLs in the topic, crawl them directly
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', topic)
        for url in urls[:3]:
            try:
                source = await self._fetch_and_summarize(url)
                if source:
                    session.sources.append(source)
            except Exception as e:
                logger.error(f"Crawl failed for {url}: {e}")

        # 3. Present sources
        if not session.sources:
            return (
                f"No sources found for '{topic}'.\n\n"
                "Try:\n"
                "- `research url https://specific-article.com`\n"
                "- A more specific topic\n"
                "- Enable more news categories: `news enable science`"
            )

        session.phase = "selecting"

        for i, source in enumerate(session.sources, 1):
            lines.append(f"**{i}. {source.title}**")
            if source.summary:
                lines.append(f"   {source.summary[:150]}...")
            if source.keywords:
                lines.append(f"   Keywords: {', '.join(source.keywords[:5])}")
            if source.url:
                lines.append(f"   {source.url}")
            lines.append("")

        lines.extend([
            "---",
            f"Found {len(session.sources)} sources.",
            "",
            "**Next steps:**",
            "- `research select 1,2,3` — Pick sources for deep analysis",
            "- `research analyze` — Analyze all sources with LLM",
            "- `research url <url>` — Add a specific URL",
        ])

        return "\n".join(lines)

    async def _research_url(
        self,
        url: str,
        user_id: str,
        engine: "SafeClaw",
    ) -> str:
        """Fetch, summarize, and add a URL to the research session."""
        source = await self._fetch_and_summarize(url)
        if not source:
            return f"Could not fetch content from {url}"

        # Add to existing session or create new one
        if user_id not in self._sessions:
            self._sessions[user_id] = ResearchSession(topic=url)

        session = self._sessions[user_id]
        session.sources.append(source)

        lines = [
            f"**Added source: {source.title}**",
            "",
            "**Summary (extractive, no LLM):**",
            source.summary,
            "",
        ]
        if source.keywords:
            lines.append(f"**Keywords:** {', '.join(source.keywords)}")
            lines.append("")

        lines.append(
            f"Total sources: {len(session.sources)}. "
            "Use `research select` to pick favorites, "
            "then `research analyze` for LLM deep dive."
        )

        return "\n".join(lines)

    async def _fetch_and_summarize(self, url: str) -> ResearchSource | None:
        """Fetch a URL and create a summarized research source."""
        try:
            async with Crawler() as crawler:
                result = await crawler.fetch(url)

            if result.error or not result.text:
                return None

            summary = self._summarizer.summarize(result.text, sentences=5)
            keywords = self._summarizer.get_keywords(result.text, top_n=8)

            return ResearchSource(
                title=result.title or url,
                url=url,
                content=result.text,
                summary=summary,
                keywords=keywords,
            )
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _select_sources(self, user_id: str, indices: list[int]) -> str:
        """Select specific sources for deep analysis."""
        session = self._sessions.get(user_id)
        if not session:
            return "No active research session. Start with: research <topic>"

        valid = []
        for idx in indices:
            if 0 <= idx < len(session.sources):
                session.sources[idx].selected = True
                valid.append(idx + 1)

        session.selected_indices = [i for i in indices if 0 <= i < len(session.sources)]

        if valid:
            return (
                f"Selected sources: {', '.join(str(v) for v in valid)}\n\n"
                "Run `research analyze` to do an LLM deep dive on these sources."
            )

        return "Invalid source numbers. Check available sources with `research sources`."

    async def _deep_analyze(self, user_id: str, engine: "SafeClaw") -> str:
        """
        Phase 2: LLM deep analysis of selected sources.

        Uses the research-specific LLM provider (per-task routing).
        """
        session = self._sessions.get(user_id)
        if not session:
            return "No active research session. Start with: research <topic>"

        # Get selected sources, or all if none selected
        selected = [s for s in session.sources if s.selected]
        if not selected:
            selected = session.sources

        if not selected:
            return "No sources to analyze. Gather sources first with: research <topic>"

        # Build the research prompt
        source_texts = []
        for i, source in enumerate(selected, 1):
            source_texts.append(
                f"Source {i}: {source.title}\n"
                f"URL: {source.url}\n"
                f"Content: {source.content[:2000]}\n"
            )

        prompt = (
            f"Research topic: {session.topic}\n\n"
            f"Analyze these {len(selected)} sources and provide:\n"
            "1. Key findings across all sources\n"
            "2. Points of agreement and disagreement\n"
            "3. Most important insights\n"
            "4. What's missing or needs further investigation\n"
            "5. A synthesis/conclusion\n\n"
            + "\n---\n".join(source_texts)
        )

        # Get the research LLM (per-task routing)
        from safeclaw.core.ai_writer import AIWriter
        from safeclaw.core.prompt_builder import PromptBuilder
        from safeclaw.core.writing_style import load_writing_profile

        # Try task-specific provider first, fall back to general
        task_providers = engine.config.get("task_providers", {})
        research_provider = task_providers.get("research")

        ai_writer = AIWriter.from_config(engine.config)
        if not ai_writer.providers:
            # No LLM configured - return extractive summary only
            combined = "\n\n".join(s.content for s in selected if s.content)
            if combined:
                extractive = self._summarizer.summarize(combined, sentences=10)
                session.deep_analysis = extractive
                session.phase = "complete"
                return (
                    f"**Research Summary (extractive, no LLM):**\n\n"
                    f"{extractive}\n\n"
                    "---\n"
                    "For AI-powered deep analysis, configure an LLM provider in config.yaml\n"
                    "under `task_providers.research` or `ai_providers`."
                )
            return "No content available for analysis."

        # Build dynamic system prompt
        prompt_builder = PromptBuilder()
        writing_profile = await load_writing_profile(engine.memory, user_id)

        system_prompt = prompt_builder.build(
            task="research",
            writing_profile=writing_profile,
            topic=session.topic,
        )

        # Call LLM
        response = await ai_writer.generate(
            prompt=prompt,
            provider_label=research_provider,
            system_prompt=system_prompt,
        )

        if response.error:
            return f"LLM analysis failed: {response.error}"

        session.deep_analysis = response.content
        session.phase = "complete"

        return (
            f"**Deep Research Analysis: {session.topic}**\n"
            f"*(via {response.provider}/{response.model})*\n\n"
            f"{response.content}\n\n"
            f"---\n"
            f"Sources analyzed: {len(selected)} | "
            f"Tokens: {response.tokens_used}"
        )

    def _show_sources(self, user_id: str) -> str:
        """Show gathered sources for the current session."""
        session = self._sessions.get(user_id)
        if not session:
            return "No active research session."

        lines = [f"**Research: {session.topic}**", f"Phase: {session.phase}", ""]

        for i, source in enumerate(session.sources, 1):
            selected = " [SELECTED]" if source.selected else ""
            lines.append(f"**{i}. {source.title}**{selected}")
            if source.summary:
                lines.append(f"   {source.summary[:150]}...")
            lines.append(f"   {source.url}")
            lines.append("")

        return "\n".join(lines)

    def _show_results(self, user_id: str) -> str:
        """Show research results."""
        session = self._sessions.get(user_id)
        if not session:
            return "No active research session."

        if not session.deep_analysis:
            return "No analysis available yet. Run `research analyze` first."

        return (
            f"**Research Results: {session.topic}**\n\n"
            f"{session.deep_analysis}"
        )

    def _help(self) -> str:
        """Return research help text."""
        return (
            "**Research Commands**\n\n"
            "Phase 1 - Gather Sources (No LLM, $0):\n"
            "  `research <topic>`          — Search feeds & crawl for sources\n"
            "  `research url <url>`        — Add a specific URL as source\n"
            "  `research sources`          — View gathered sources\n\n"
            "Phase 2 - Deep Analysis (LLM, optional):\n"
            "  `research select 1,2,3`     — Pick your favorite sources\n"
            "  `research analyze`          — LLM deep dive on selected sources\n"
            "  `research results`          — View analysis results\n\n"
            "The research pipeline:\n"
            "  Web Search (non-LLM) -> Sumy Summarize (non-LLM) -> "
            "You Select Sources -> LLM Deep Analysis (optional)\n\n"
            "Configure a research-specific LLM in config.yaml:\n"
            "  task_providers:\n"
            '    research: "my-ollama"  # or any configured provider'
        )
