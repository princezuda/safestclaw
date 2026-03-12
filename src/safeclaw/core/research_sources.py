"""
SafeClaw Research Sources - Academic and knowledge search providers.

Provides real research sources instead of just RSS news feeds:
- arXiv (academic papers, free API, no key needed)
- Wolfram Alpha (computational knowledge, free short answers API)
- Semantic Scholar (academic papers, free API)

All sources are free, no API keys required for basic usage.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

# arXiv subject categories for smarter searching
ARXIV_CATEGORIES = {
    "cs": "Computer Science",
    "math": "Mathematics",
    "physics": "Physics",
    "stat": "Statistics",
    "econ": "Economics",
    "q-bio": "Quantitative Biology",
    "q-fin": "Quantitative Finance",
    "eess": "Electrical Engineering",
    "astro-ph": "Astrophysics",
    "cond-mat": "Condensed Matter",
    "hep": "High Energy Physics",
    "nlin": "Nonlinear Sciences",
}


@dataclass
class AcademicPaper:
    """A research paper from an academic source."""
    title: str
    authors: list[str]
    abstract: str
    url: str
    source: str  # "arxiv", "semantic_scholar"
    published: str = ""
    categories: list[str] | None = None
    citation_count: int = 0


@dataclass
class KnowledgeResult:
    """A knowledge/computational result from Wolfram Alpha."""
    query: str
    result: str
    source: str = "wolfram_alpha"
    pods: list[dict] | None = None


async def search_arxiv(
    query: str,
    max_results: int = 8,
    sort_by: str = "relevance",
) -> list[AcademicPaper]:
    """
    Search arXiv for academic papers.

    Uses the free arXiv API (no key needed).
    https://info.arxiv.org/help/api/basics.html

    Args:
        query: Search query (supports arXiv query syntax)
        max_results: Max papers to return (default 8)
        sort_by: "relevance" or "lastUpdatedDate" or "submittedDate"

    Returns:
        List of AcademicPaper results
    """
    papers = []
    encoded_query = quote_plus(query)

    sort_map = {
        "relevance": "relevance",
        "date": "lastUpdatedDate",
        "submitted": "submittedDate",
        "lastUpdatedDate": "lastUpdatedDate",
        "submittedDate": "submittedDate",
    }
    sort_param = sort_map.get(sort_by, "relevance")

    url = (
        f"http://export.arxiv.org/api/query"
        f"?search_query=all:{encoded_query}"
        f"&start=0&max_results={max_results}"
        f"&sortBy={sort_param}&sortOrder=descending"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        # Parse Atom XML
        root = ET.fromstring(response.text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""

            summary_el = entry.find("atom:summary", ns)
            abstract = summary_el.text.strip().replace("\n", " ") if summary_el is not None else ""

            # Get authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name_el = author.find("atom:name", ns)
                if name_el is not None:
                    authors.append(name_el.text)

            # Get URL (prefer abs link)
            paper_url = ""
            for link in entry.findall("atom:link", ns):
                if link.get("type") == "text/html" or link.get("rel") == "alternate":
                    paper_url = link.get("href", "")
                    break
            if not paper_url:
                id_el = entry.find("atom:id", ns)
                paper_url = id_el.text if id_el is not None else ""

            # Get published date
            published_el = entry.find("atom:published", ns)
            published = published_el.text[:10] if published_el is not None else ""

            # Get categories
            categories = []
            for cat in entry.findall("atom:category", ns):
                term = cat.get("term", "")
                if term:
                    categories.append(term)

            if title:
                papers.append(AcademicPaper(
                    title=title,
                    authors=authors[:5],  # Limit to 5 authors
                    abstract=abstract,
                    url=paper_url,
                    source="arxiv",
                    published=published,
                    categories=categories,
                ))

    except Exception as e:
        logger.error(f"arXiv search failed: {e}")

    return papers


async def search_semantic_scholar(
    query: str,
    max_results: int = 5,
) -> list[AcademicPaper]:
    """
    Search Semantic Scholar for academic papers.

    Uses the free Semantic Scholar API (no key needed for basic usage).
    https://api.semanticscholar.org/

    Args:
        query: Search query
        max_results: Max papers to return (default 5)

    Returns:
        List of AcademicPaper results
    """
    papers = []
    encoded_query = quote_plus(query)

    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={encoded_query}"
        f"&limit={max_results}"
        f"&fields=title,authors,abstract,url,year,citationCount,externalIds"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        data = response.json()

        for paper in data.get("data", []):
            title = paper.get("title", "")
            if not title:
                continue

            authors = [
                a.get("name", "") for a in paper.get("authors", [])[:5]
            ]
            abstract = paper.get("abstract", "") or ""

            # Build URL
            paper_url = paper.get("url", "")
            if not paper_url:
                ext_ids = paper.get("externalIds", {})
                if ext_ids.get("ArXiv"):
                    paper_url = f"https://arxiv.org/abs/{ext_ids['ArXiv']}"
                elif ext_ids.get("DOI"):
                    paper_url = f"https://doi.org/{ext_ids['DOI']}"

            year = paper.get("year", "")
            citation_count = paper.get("citationCount", 0) or 0

            papers.append(AcademicPaper(
                title=title,
                authors=authors,
                abstract=abstract,
                url=paper_url,
                source="semantic_scholar",
                published=str(year) if year else "",
                citation_count=citation_count,
            ))

    except Exception as e:
        logger.error(f"Semantic Scholar search failed: {e}")

    return papers


async def query_wolfram_alpha(
    query: str,
    app_id: str = "",
) -> KnowledgeResult | None:
    """
    Query Wolfram Alpha for computational knowledge.

    Uses the free Short Answers API if no app_id is provided.
    With an app_id, uses the Full Results API for richer output.

    Get a free app_id at: https://developer.wolframalpha.com/

    Args:
        query: Question or computation to evaluate
        app_id: Optional Wolfram Alpha App ID (free tier available)

    Returns:
        KnowledgeResult or None if query fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if app_id:
                # Full Results API (richer output)
                url = (
                    f"http://api.wolframalpha.com/v2/query"
                    f"?appid={app_id}"
                    f"&input={quote_plus(query)}"
                    f"&format=plaintext"
                    f"&output=JSON"
                )
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                result_parts = []
                pods = []

                query_result = data.get("queryresult", {})
                for pod in query_result.get("pods", []):
                    pod_title = pod.get("title", "")
                    subpods = pod.get("subpods", [])
                    pod_text = "\n".join(
                        sp.get("plaintext", "") for sp in subpods if sp.get("plaintext")
                    )
                    if pod_text:
                        pods.append({"title": pod_title, "text": pod_text})
                        result_parts.append(f"**{pod_title}:** {pod_text}")

                if result_parts:
                    return KnowledgeResult(
                        query=query,
                        result="\n".join(result_parts),
                        pods=pods,
                    )
            else:
                # Short Answers API (no key needed, limited)
                url = (
                    f"http://api.wolframalpha.com/v1/result"
                    f"?appid=DEMO"
                    f"&i={quote_plus(query)}"
                )
                response = await client.get(url)

                if response.status_code == 200 and response.text:
                    return KnowledgeResult(
                        query=query,
                        result=response.text,
                    )

    except Exception as e:
        logger.error(f"Wolfram Alpha query failed: {e}")

    return None


async def search_all(
    query: str,
    max_results: int = 10,
    wolfram_app_id: str = "",
) -> dict:
    """
    Search all available research sources concurrently.

    Args:
        query: Search query
        max_results: Max results per source
        wolfram_app_id: Optional Wolfram Alpha App ID

    Returns:
        Dict with keys: "arxiv", "semantic_scholar", "wolfram"
    """
    import asyncio

    # Run all searches concurrently
    arxiv_task = asyncio.create_task(search_arxiv(query, max_results=max_results))
    scholar_task = asyncio.create_task(
        search_semantic_scholar(query, max_results=min(max_results, 5))
    )

    # Wolfram Alpha is optional — only useful for factual/computational queries
    wolfram_task = asyncio.create_task(query_wolfram_alpha(query, wolfram_app_id))

    arxiv_results, scholar_results, wolfram_result = await asyncio.gather(
        arxiv_task, scholar_task, wolfram_task,
        return_exceptions=True,
    )

    results = {
        "arxiv": arxiv_results if isinstance(arxiv_results, list) else [],
        "semantic_scholar": scholar_results if isinstance(scholar_results, list) else [],
        "wolfram": wolfram_result if isinstance(wolfram_result, KnowledgeResult) else None,
    }

    return results


def is_academic_query(query: str) -> bool:
    """
    Heuristic check if a query looks like it would benefit from academic sources.

    Returns True for queries about research topics, science, math, etc.
    """
    academic_signals = [
        "research", "paper", "study", "journal", "arxiv", "academic",
        "algorithm", "theorem", "proof", "hypothesis", "experiment",
        "neural", "machine learning", "deep learning", "transformer",
        "quantum", "physics", "biology", "chemistry", "mathematics",
        "statistical", "analysis", "model", "dataset", "benchmark",
        "performance", "optimization", "architecture", "framework",
        "survey", "review", "comparison", "evaluation", "methodology",
    ]
    lower = query.lower()
    return any(signal in lower for signal in academic_signals)
