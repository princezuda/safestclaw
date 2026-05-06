"""
SafestClaw Research Action - Real research from academic & knowledge sources.

Two-phase research pipeline:

Phase 1 (Non-LLM, $0):
- arXiv (academic papers, free API)
- Semantic Scholar (academic papers, free API)
- Wolfram Alpha (computational knowledge)
- RSS feeds as supplementary sources
- Crawl specific URLs
- Summarize with sumy (extractive, no AI)

Phase 2 (LLM, optional):
- User selects which sources to research in depth
- LLM analyzes and synthesizes selected sources
- Uses the research-specific LLM provider (per-task routing)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction
from safestclaw.core.connectivity import (
    NETWORK_EXCEPTIONS,
    get_checker,
    offline_banner,
)
from safestclaw.core.crawler import Crawler
from safestclaw.core.feeds import FeedReader
from safestclaw.core.parser import is_conversational, strip_conversational
from safestclaw.core.research_sources import (
    KnowledgeResult,
    query_wolfram_alpha,
    search_all,
    search_arxiv,
    search_semantic_scholar,
)
from safestclaw.core.summarizer import Summarizer

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

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
    source_type: str = ""  # "arxiv", "semantic_scholar", "wolfram", "rss", "url"
    authors: list[str] = field(default_factory=list)
    citation_count: int = 0


@dataclass
class ResearchSession:
    """Tracks an active research session for a user."""
    topic: str
    sources: list[ResearchSource] = field(default_factory=list)
    phase: str = "gathering"  # gathering, selecting, analyzing, complete
    deep_analysis: str = ""
    selected_indices: list[int] = field(default_factory=list)
    wolfram_result: str = ""  # Wolfram Alpha answer if available


class ResearchAction(BaseAction):
    """
    Two-phase research: real academic sources + optional LLM deep dive.

    Sources:
        - arXiv (academic papers, free, no API key)
        - Semantic Scholar (academic papers, free, no API key)
        - Wolfram Alpha (computational knowledge)
        - RSS feeds (supplementary)
        - Direct URLs

    Commands:
        research <topic>           - Search academic sources for a topic
        research arxiv <query>     - Search arXiv specifically
        research scholar <query>   - Search Semantic Scholar specifically
        research wolfram <query>   - Ask Wolfram Alpha
        research url <url>         - Research a specific URL
        research select <1,2,3>    - Select sources for deep analysis
        research analyze           - Run LLM deep analysis on selected sources
        research sources           - Show gathered sources
        research results           - Show research results
        research help              - Show research commands
    """

    name = "research"
    description = "Academic research with arXiv, Semantic Scholar, Wolfram Alpha"

    def __init__(self):
        self._sessions: dict[str, ResearchSession] = {}
        self._summarizer = Summarizer()
        self._feed_reader = FeedReader(
            summarize_items=True,
            max_items_per_feed=5,
        )
        self.ai_writer = None
        self._initialized = False

    def _initialize(self, engine: "SafestClaw") -> None:
        """Lazy-init: load AI writer from config (same pattern as BlogAction)."""
        if self._initialized:
            return
        self._initialized = True
        from safestclaw.core.ai_writer import AIWriter
        if engine.config.get("ai_providers"):
            self.ai_writer = AIWriter.from_config(engine.config)
            task_providers = engine.config.get("task_providers", {})
            research_provider = task_providers.get("research")
            if research_provider and research_provider in self.ai_writer.providers:
                self.ai_writer.set_active_provider(research_provider)

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute research action."""
        self._initialize(engine)
        original = params.get("raw_input", "").strip()
        # Strip conversational fillers ("hey man, id like to ...") before
        # source detection and query extraction. We keep the original
        # around so the friendly-acknowledgment heuristic can still see
        # the politeness markers.
        raw = strip_conversational(original)

        # Parse subcommand
        lower = raw.lower()

        if "research help" in lower or lower == "research":
            return self._help()

        if "research url" in lower:
            urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', raw)
            if urls:
                return await self._research_url(urls[0], user_id, engine)
            return "Please provide a URL: research url https://example.com"

        # Source-aware routing: if the user mentions arxiv / scholar /
        # wolfram anywhere in the text, pull out the topic and dispatch
        # to the matching specialist. This catches both the strict form
        # ("research arxiv quantum computing") and conversational input
        # ("hey man, id like to research, let's try arxiv quantum
        # computing") — the parser already stripped the politeness, but
        # the source word might still appear after "research" rather
        # than directly adjacent to it.
        source = self._detect_source(lower)
        if source:
            query = self._extract_query(raw, source)
            casual = self._is_conversational(original)
            if source == "arxiv":
                if query:
                    body = await self._search_arxiv(query, user_id)
                    return self._with_ack("arxiv", query, body, casual)
                return "Please provide a query: research arxiv quantum computing"
            if source == "scholar":
                if query:
                    body = await self._search_scholar(query, user_id)
                    return self._with_ack("scholar", query, body, casual)
                return "Please provide a query: research scholar machine learning"
            if source == "wolfram":
                if query:
                    body = await self._search_wolfram(query, user_id, engine)
                    return self._with_ack("wolfram", query, body, casual)
                return "Please provide a query: research wolfram integrate x^2"

        if "research select" in lower:
            numbers = re.findall(r'\d+', raw.split("select", 1)[-1])
            if numbers:
                indices = [int(n) - 1 for n in numbers]
                return self._select_sources(user_id, indices)
            return "Specify source numbers: research select 1,2,3"

        if "research analyze" in lower or "research deep" in lower:
            return await self._deep_analyze(user_id, engine)

        if "research sources" in lower:
            return self._show_sources(user_id)

        if "research results" in lower:
            return self._show_results(user_id)

        # Default: start research on a topic. Strip the leading verb
        # plus any tiny connectives so "research about quantum
        # computing" yields the topic "quantum computing" — not
        # "about quantum computing".
        topic = raw
        for prefix in (
            "find out about", "look up", "search for papers on",
            "search for", "search", "investigate", "research",
        ):
            if lower.startswith(prefix):
                topic = raw[len(prefix):].strip()
                break
        topic = re.sub(
            r"^(?:on|for|about)\s+", "", topic, flags=re.IGNORECASE
        ).strip(" ,.;:")

        if topic:
            casual = self._is_conversational(original)
            body = await self._start_research(topic, user_id, engine)
            return self._with_ack("all", topic, body, casual)

        return self._help()

    # ------------------------------------------------------------------
    # Conversational input helpers
    # ------------------------------------------------------------------

    # Words/phrases that signal which source the user wants. The parser
    # already strips polite prefixes ("hey man, id like to", "let's try"),
    # so by the time we get here the input is something like
    # "research arxiv quantum computing", "research quantum computing
    # arxiv", "arxiv quantum computing", or "research quantum computing
    # using arxiv".
    _SOURCE_ALIASES: dict[str, list[str]] = {
        "arxiv": ["arxiv", "arxiv.org"],
        "scholar": ["semantic scholar", "scholar"],
        "wolfram": ["wolfram alpha", "wolfram"],
    }

    _ACK_LABEL: dict[str, str] = {
        "arxiv": "arXiv",
        "scholar": "Semantic Scholar",
        "wolfram": "Wolfram Alpha",
        "all": "arXiv, Semantic Scholar, and Wolfram Alpha",
    }

    def _is_conversational(self, raw: str) -> bool:
        """Thin wrapper so action callsites stay readable."""
        return is_conversational(raw)

    def _with_ack(
        self,
        source: str,
        query: str,
        body: str,
        conversational: bool,
    ) -> str:
        """Prepend a friendly intro line when the input was conversational.
        Power users issuing the strict form ("research arxiv X") get the
        dense output untouched."""
        if not conversational or not body:
            return body
        label = self._ACK_LABEL.get(source, source)
        clean_query = (query or "").strip().strip('"').strip("'")
        if not clean_query:
            return body
        ack = f"On it — searching {label} for **{clean_query}**…\n\n"
        return ack + body

    def _detect_source(self, lowered: str) -> str | None:
        """Return the source key (arxiv/scholar/wolfram) mentioned in
        the input, preferring the longest match so 'semantic scholar'
        beats a stray 'scholar' inside another word."""
        best: tuple[str, int] | None = None
        for source, aliases in self._SOURCE_ALIASES.items():
            for alias in aliases:
                # Word-boundary match so "scholar" doesn't fire inside
                # "scholarly" — and so the alias must appear as a real
                # token, not a substring of an unrelated word.
                if re.search(rf"\b{re.escape(alias)}\b", lowered):
                    if best is None or len(alias) > best[1]:
                        best = (source, len(alias))
        return best[0] if best else None

    def _extract_query(self, raw: str, source: str) -> str:
        """
        Pull the actual search query out of free-form input. Removes the
        leading verb ("research", "look up", "find papers on", etc.),
        the source name ("arxiv"/"scholar"/"wolfram"/aliases), and tiny
        connectives ("on", "for", "about", "using", "via", "with").
        """
        text = raw.strip()
        lowered = text.lower()

        # Drop the leading verb phrase if present.
        for verb in (
            "research arxiv", "research scholar", "research wolfram",
            "research", "look up", "find out about",
            "find papers on", "find papers about",
            "search for papers on", "search for", "search",
            "investigate",
        ):
            if lowered.startswith(verb):
                text = text[len(verb):].strip()
                lowered = text.lower()
                break

        # Drop every alias of the chosen source (longest first so
        # "semantic scholar" is removed before "scholar"). Treat them
        # as whole words.
        aliases = sorted(self._SOURCE_ALIASES[source], key=len, reverse=True)
        for alias in aliases:
            text = re.sub(
                rf"\b{re.escape(alias)}\b", " ", text, flags=re.IGNORECASE
            )

        # Strip tiny connectives that often sit between the source and
        # the topic ("research arxiv for quantum computing").
        text = re.sub(
            r"\b(?:on|for|about|using|via|with|please)\b",
            " ", text, flags=re.IGNORECASE,
        )
        text = re.sub(r"\s{2,}", " ", text).strip(" ,.;:")

        return text

    async def _start_research(
        self,
        topic: str,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """
        Phase 1: Gather sources from academic databases and knowledge engines.

        Searches arXiv, Semantic Scholar, Wolfram Alpha, and RSS feeds concurrently.
        """
        session = ResearchSession(topic=topic)
        self._sessions[user_id] = session

        # Bail out early if we know we're offline — no point trying three
        # remote APIs when none will resolve.
        if not await get_checker().is_online():
            return await self._offline_message(
                "arXiv, Semantic Scholar, and Wolfram Alpha", topic,
            )

        ai_note = f" + LLM ({self.ai_writer.get_active_provider().provider}/{self.ai_writer.get_active_provider().model})" if (self.ai_writer and self.ai_writer.get_active_provider()) else " (no LLM — run `research analyze` after for AI summary)"
        lines = [f"**Researching: {topic}**", "", f"Searching academic sources{ai_note}...", ""]

        # Get Wolfram Alpha app_id from config if available
        wolfram_app_id = engine.config.get("apis", {}).get("wolfram_alpha", "")

        # Search all academic sources concurrently. If the bundle as a
        # whole fails (DNS down between probe + call), fall back.
        try:
            results = await search_all(
                query=topic,
                max_results=8,
                wolfram_app_id=wolfram_app_id,
            )
        except NETWORK_EXCEPTIONS as e:
            logger.warning(f"search_all failed: {e}")
            return await self._offline_message(
                "arXiv, Semantic Scholar, and Wolfram Alpha", topic,
            )

        # Process arXiv results
        for paper in results["arxiv"]:
            summary = paper.abstract[:500]
            if len(paper.abstract) > 100:
                summary = self._summarizer.summarize(paper.abstract, sentences=3)

            keywords = self._summarizer.get_keywords(paper.abstract, top_n=5)

            session.sources.append(ResearchSource(
                title=paper.title,
                url=paper.url,
                content=paper.abstract,
                summary=summary,
                keywords=keywords,
                source_type="arxiv",
                authors=paper.authors,
            ))

        # Process Semantic Scholar results
        for paper in results["semantic_scholar"]:
            abstract = paper.abstract or ""
            summary = abstract[:500]
            if len(abstract) > 100:
                summary = self._summarizer.summarize(abstract, sentences=3)

            keywords = self._summarizer.get_keywords(abstract, top_n=5) if abstract else []

            session.sources.append(ResearchSource(
                title=paper.title,
                url=paper.url,
                content=abstract,
                summary=summary,
                keywords=keywords,
                source_type="semantic_scholar",
                authors=paper.authors,
                citation_count=paper.citation_count,
            ))

        # Process Wolfram Alpha result
        wolfram = results.get("wolfram")
        if wolfram and isinstance(wolfram, KnowledgeResult):
            session.wolfram_result = wolfram.result
            lines.append(f"**Wolfram Alpha:** {wolfram.result}")
            lines.append("")

        # Supplementary: also check RSS feeds for broader coverage
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

            relevant.sort(key=lambda x: x[0], reverse=True)

            for _, item in relevant[:3]:  # Only top 3 RSS results (supplementary)
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
                    source_type="rss",
                ))
        except Exception as e:
            logger.error(f"RSS search failed: {e}")

        # Also crawl any URLs in the topic
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', topic)
        for url in urls[:3]:
            try:
                source = await self._fetch_and_summarize(url)
                if source:
                    session.sources.append(source)
            except Exception as e:
                logger.error(f"Crawl failed for {url}: {e}")

        # Present sources
        if not session.sources and not session.wolfram_result:
            return (
                f"No sources found for '{topic}'.\n\n"
                "Try:\n"
                "- `research arxiv <query>` — Search arXiv directly\n"
                "- `research scholar <query>` — Search Semantic Scholar\n"
                "- `research wolfram <query>` — Ask Wolfram Alpha\n"
                "- `research url https://specific-article.com`\n"
                "- A more specific topic"
            )

        session.phase = "selecting"

        # Group by source type for clear display
        source_icons = {
            "arxiv": "[arXiv]",
            "semantic_scholar": "[Scholar]",
            "wolfram": "[Wolfram]",
            "rss": "[RSS]",
            "url": "[Web]",
        }

        for i, source in enumerate(session.sources, 1):
            icon = source_icons.get(source.source_type, "[Source]")
            lines.append(f"**{i}. {icon} {source.title}**")
            if source.authors:
                lines.append(f"   Authors: {', '.join(source.authors[:3])}")
            if source.citation_count:
                lines.append(f"   Citations: {source.citation_count}")
            if source.summary:
                lines.append(f"   {source.summary[:150]}...")
            if source.keywords:
                lines.append(f"   Keywords: {', '.join(source.keywords[:5])}")
            if source.url:
                lines.append(f"   {source.url}")
            lines.append("")

        lines.extend([
            "---",
            f"Found {len(session.sources)} sources "
            f"(arXiv: {sum(1 for s in session.sources if s.source_type == 'arxiv')}, "
            f"Scholar: {sum(1 for s in session.sources if s.source_type == 'semantic_scholar')}, "
            f"RSS: {sum(1 for s in session.sources if s.source_type == 'rss')}).",
            "",
            "**Next steps:**",
            "- `research select 1,2,3` — Pick sources for deep analysis",
            "- `research analyze` — Analyze all sources with LLM",
            "- `research arxiv <query>` — Search arXiv for more",
            "- `research url <url>` — Add a specific URL",
        ])

        return "\n".join(lines)

    async def _offline_message(self, source: str, query: str) -> str:
        """Standard offline reply for an academic source we can't reach."""
        local = self._local_results_for(query)
        body = (
            f"Can't reach **{source}** right now — either the network is "
            f"down or you're in offline mode (say `i'm online` to retry).\n"
        )
        if local:
            body += "\n" + offline_banner("falling back to cached sources") + local
        else:
            body += (
                "\nNo cached results for this topic. "
                "Try again when you're back online, or use `summarize "
                "<file.pdf>` / `analyze <text>` for offline ML-only "
                "options."
            )
        return body

    def _local_results_for(self, query: str) -> str:
        """Best-effort local results: previous research session sources
        whose title or summary mentions the query."""
        hits: list[str] = []
        q = query.lower().strip()
        for session in self._sessions.values():
            for src in session.sources:
                blob = (src.title + " " + (src.summary or "")).lower()
                if q in blob:
                    hits.append(f"  • {src.title}  [{src.source_type}]")
                    if len(hits) >= 5:
                        break
            if len(hits) >= 5:
                break
        if hits:
            return "**From your previous research sessions:**\n" + "\n".join(hits)
        return ""

    async def _search_arxiv(self, query: str, user_id: str) -> str:
        """Search arXiv specifically."""
        if not await get_checker().is_online():
            return await self._offline_message("arXiv", query)
        try:
            papers = await search_arxiv(query, max_results=10)
        except NETWORK_EXCEPTIONS as e:
            logger.warning(f"arXiv search failed: {e}")
            return await self._offline_message("arXiv", query)

        if not papers:
            return f"No arXiv papers found for '{query}'."

        # Add to session
        if user_id not in self._sessions:
            self._sessions[user_id] = ResearchSession(topic=query)
        session = self._sessions[user_id]

        lines = [f"**arXiv Search: {query}**", ""]

        for paper in papers:
            summary = paper.abstract[:500]
            if len(paper.abstract) > 100:
                summary = self._summarizer.summarize(paper.abstract, sentences=3)

            keywords = self._summarizer.get_keywords(paper.abstract, top_n=5)

            session.sources.append(ResearchSource(
                title=paper.title,
                url=paper.url,
                content=paper.abstract,
                summary=summary,
                keywords=keywords,
                source_type="arxiv",
                authors=paper.authors,
            ))

            idx = len(session.sources)
            lines.append(f"**{idx}. {paper.title}**")
            if paper.authors:
                lines.append(f"   {', '.join(paper.authors[:3])}")
            lines.append(f"   {paper.published}")
            lines.append(f"   {summary[:150]}...")
            lines.append(f"   {paper.url}")
            lines.append("")

        session.phase = "selecting"
        lines.append(f"Added {len(papers)} arXiv papers. Use `research select` to pick favorites.")

        return "\n".join(lines)

    async def _search_scholar(self, query: str, user_id: str) -> str:
        """Search Semantic Scholar specifically."""
        if not await get_checker().is_online():
            return await self._offline_message("Semantic Scholar", query)
        try:
            papers = await search_semantic_scholar(query, max_results=8)
        except NETWORK_EXCEPTIONS as e:
            logger.warning(f"Semantic Scholar search failed: {e}")
            return await self._offline_message("Semantic Scholar", query)

        if not papers:
            return f"No Semantic Scholar papers found for '{query}'."

        if user_id not in self._sessions:
            self._sessions[user_id] = ResearchSession(topic=query)
        session = self._sessions[user_id]

        lines = [f"**Semantic Scholar: {query}**", ""]

        for paper in papers:
            abstract = paper.abstract or ""
            summary = abstract[:500]
            if len(abstract) > 100:
                summary = self._summarizer.summarize(abstract, sentences=3)

            keywords = self._summarizer.get_keywords(abstract, top_n=5) if abstract else []

            session.sources.append(ResearchSource(
                title=paper.title,
                url=paper.url,
                content=abstract,
                summary=summary,
                keywords=keywords,
                source_type="semantic_scholar",
                authors=paper.authors,
                citation_count=paper.citation_count,
            ))

            idx = len(session.sources)
            lines.append(f"**{idx}. {paper.title}**")
            if paper.authors:
                lines.append(f"   {', '.join(paper.authors[:3])}")
            if paper.citation_count:
                lines.append(f"   Citations: {paper.citation_count}")
            lines.append(f"   {summary[:150]}...")
            if paper.url:
                lines.append(f"   {paper.url}")
            lines.append("")

        session.phase = "selecting"
        lines.append(f"Added {len(papers)} papers. Use `research select` to pick favorites.")

        return "\n".join(lines)

    async def _search_wolfram(
        self, query: str, user_id: str, engine: "SafestClaw"
    ) -> str:
        """Query Wolfram Alpha specifically."""
        if not await get_checker().is_online():
            return await self._offline_message("Wolfram Alpha", query)
        wolfram_app_id = engine.config.get("apis", {}).get("wolfram_alpha", "")

        try:
            result = await query_wolfram_alpha(query, wolfram_app_id)
        except NETWORK_EXCEPTIONS as e:
            logger.warning(f"Wolfram Alpha query failed: {e}")
            return await self._offline_message("Wolfram Alpha", query)

        if not result:
            return (
                f"Wolfram Alpha couldn't answer '{query}'.\n\n"
                "For full Wolfram Alpha access, add your free App ID to config.yaml:\n"
                "  apis:\n"
                '    wolfram_alpha: "YOUR-APP-ID"\n\n'
                "Get one free at: https://developer.wolframalpha.com/"
            )

        if user_id not in self._sessions:
            self._sessions[user_id] = ResearchSession(topic=query)
        session = self._sessions[user_id]
        session.wolfram_result = result.result

        lines = [
            f"**Wolfram Alpha: {query}**",
            "",
            result.result,
            "",
        ]

        if result.pods:
            for pod in result.pods[:5]:
                lines.append(f"**{pod['title']}:** {pod['text']}")
            lines.append("")

        return "\n".join(lines)

    async def _research_url(
        self,
        url: str,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """Fetch, summarize, and add a URL to the research session."""
        source = await self._fetch_and_summarize(url)
        if not source:
            return f"Could not fetch content from {url}"

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
                source_type="url",
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

    async def _deep_analyze(self, user_id: str, engine: "SafestClaw") -> str:
        """Phase 2: LLM deep analysis of selected sources."""
        session = self._sessions.get(user_id)
        if not session:
            return "No active research session. Start with: research <topic>"

        selected = [s for s in session.sources if s.selected]
        if not selected:
            selected = session.sources

        if not selected:
            return "No sources to analyze. Gather sources first with: research <topic>"

        # Build the research prompt
        source_texts = []
        for i, source in enumerate(selected, 1):
            source_info = f"Source {i}: {source.title}\n"
            if source.source_type:
                source_info += f"Type: {source.source_type}\n"
            if source.authors:
                source_info += f"Authors: {', '.join(source.authors[:3])}\n"
            source_info += f"URL: {source.url}\n"
            source_info += f"Content: {source.content[:2000]}\n"
            source_texts.append(source_info)

        prompt = (
            f"Research topic: {session.topic}\n\n"
        )

        if session.wolfram_result:
            prompt += f"Wolfram Alpha answer: {session.wolfram_result}\n\n"

        prompt += (
            f"Analyze these {len(selected)} sources and provide:\n"
            "1. Key findings across all sources\n"
            "2. Points of agreement and disagreement\n"
            "3. Most important insights\n"
            "4. What's missing or needs further investigation\n"
            "5. A synthesis/conclusion\n\n"
            + "\n---\n".join(source_texts)
        )

        from safestclaw.core.prompt_builder import PromptBuilder
        from safestclaw.core.writing_style import load_writing_profile

        ai_writer = self.ai_writer
        if not ai_writer or not ai_writer.providers:
            combined = "\n\n".join(s.content for s in selected if s.content)
            if combined:
                extractive = self._summarizer.summarize(combined, sentences=10)
                session.deep_analysis = extractive
                session.phase = "complete"
                return (
                    f"**Research Summary (extractive, no LLM):**\n\n"
                    f"{extractive}\n\n"
                    "---\n"
                    "For AI-powered deep analysis, run: `setup ai sk-ant-your-key`"
                )
            return "No content available for analysis."

        prompt_builder = PromptBuilder()
        writing_profile = await load_writing_profile(engine.memory, user_id)

        system_prompt = prompt_builder.build(
            task="research",
            writing_profile=writing_profile,
            topic=session.topic,
        )

        response = await ai_writer.generate(
            prompt=prompt,
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

        source_icons = {
            "arxiv": "[arXiv]",
            "semantic_scholar": "[Scholar]",
            "wolfram": "[Wolfram]",
            "rss": "[RSS]",
            "url": "[Web]",
        }

        lines = [f"**Research: {session.topic}**", f"Phase: {session.phase}", ""]

        if session.wolfram_result:
            lines.append(f"**Wolfram Alpha:** {session.wolfram_result}")
            lines.append("")

        for i, source in enumerate(session.sources, 1):
            selected = " [SELECTED]" if source.selected else ""
            icon = source_icons.get(source.source_type, "[Source]")
            lines.append(f"**{i}. {icon} {source.title}**{selected}")
            if source.authors:
                lines.append(f"   Authors: {', '.join(source.authors[:3])}")
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
            "**Sources** (all free, no API key needed):\n"
            "  - arXiv — Academic papers (CS, math, physics, bio...)\n"
            "  - Semantic Scholar — Academic papers with citation counts\n"
            "  - Wolfram Alpha — Computational knowledge & facts\n"
            "  - RSS feeds — News & blog supplementary results\n\n"
            "Phase 1 — Gather Sources (No LLM, $0):\n"
            "  `research <topic>`          — Search all sources at once\n"
            "  `research arxiv <query>`    — Search arXiv papers\n"
            "  `research scholar <query>`  — Search Semantic Scholar\n"
            "  `research wolfram <query>`  — Ask Wolfram Alpha\n"
            "  `research url <url>`        — Add a specific URL\n"
            "  `research sources`          — View gathered sources\n\n"
            "Phase 2 — Deep Analysis (LLM, optional):\n"
            "  `research select 1,2,3`     — Pick your favorite sources\n"
            "  `research analyze`          — LLM deep dive on selected sources\n"
            "  `research results`          — View analysis results\n\n"
            "The research pipeline:\n"
            "  arXiv + Scholar + Wolfram (free) -> Sumy Summarize ($0) -> "
            "You Select Sources -> LLM Deep Analysis (optional)\n\n"
            "Optional: Add a Wolfram Alpha App ID for richer results:\n"
            "  apis:\n"
            '    wolfram_alpha: "YOUR-APP-ID"  # Free at developer.wolframalpha.com\n\n'
            "Configure a research-specific LLM in config.yaml:\n"
            "  task_providers:\n"
            '    research: "my-ollama"  # or any configured provider'
        )
