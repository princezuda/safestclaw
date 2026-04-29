"""
SafestClaw Web Crawler - Extract links and content from websites.

Uses httpx + BeautifulSoup. No AI required.
"""

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# Private/internal IP ranges that should be blocked for SSRF protection
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private
    ipaddress.ip_network("172.16.0.0/12"),    # Private
    ipaddress.ip_network("192.168.0.0/16"),   # Private
    ipaddress.ip_network("192.0.0.0/24"),     # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1 (documentation)
    ipaddress.ip_network("192.88.99.0/24"),   # 6to4 Relay Anycast
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("100.64.0.0/10"),    # Shared address space (CGNAT)
    ipaddress.ip_network("198.18.0.0/15"),    # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2 (documentation)
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3 (documentation)
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved for future use
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]


def is_safe_url(url: str) -> tuple[bool, str]:
    """
    Check if URL is safe to fetch (not pointing to internal resources).

    Returns:
        Tuple of (is_safe, reason)
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False, "Invalid URL: no hostname"

        # Block common internal hostnames
        blocked_hostnames = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        if hostname.lower() in blocked_hostnames:
            return False, f"Blocked internal hostname: {hostname}"

        # Block .local and .internal domains
        if hostname.lower().endswith((".local", ".internal", ".localhost")):
            return False, f"Blocked internal domain: {hostname}"

        # Resolve hostname to check if it points to private IP
        try:
            # Get all IPs for hostname
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
            for info in infos:
                ip_str = info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    for blocked_range in BLOCKED_IP_RANGES:
                        if ip in blocked_range:
                            return False, f"Blocked internal IP: {ip_str}"
                except ValueError:
                    continue
        except socket.gaierror:
            # DNS resolution failed - block to prevent DNS rebinding attacks
            return False, f"DNS resolution failed for {hostname}"

        return True, ""

    except Exception as e:
        return False, f"URL validation error: {e}"


@dataclass
class CrawlResult:
    """Result of crawling a URL."""
    url: str
    title: str | None = None
    text: str = ""
    links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    status_code: int = 0
    error: str | None = None
    depth: int = 0


class Crawler:
    """
    Async web crawler for extracting content and links.

    Features:
    - Async HTTP requests with httpx
    - HTML parsing with BeautifulSoup
    - Link extraction and normalization
    - Depth-limited crawling
    - Robots.txt respect (optional)
    - Rate limiting
    """

    def __init__(
        self,
        max_depth: int = 2,
        max_pages: int = 100,
        timeout: float = 30.0,
        rate_limit: float = 1.0,
        respect_robots: bool = True,
        user_agent: str = "SafestClaw/0.1 (Privacy-first crawler)",
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.respect_robots = respect_robots
        self.user_agent = user_agent

        self._visited: set[str] = set()
        self._robots_cache: dict[str, set[str]] = {}
        self._client: httpx.AsyncClient | None = None

    MAX_REDIRECTS = 10

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=False,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch(self, url: str, allow_internal: bool = False) -> CrawlResult:
        """Fetch a single URL and extract content."""
        result = CrawlResult(url=url)

        # SSRF protection: check if URL points to internal resources
        if not allow_internal:
            is_safe, reason = is_safe_url(url)
            if not is_safe:
                result.error = f"SSRF blocked: {reason}"
                logger.warning(f"Blocked SSRF attempt: {url} - {reason}")
                return result

        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=False,
            )

        try:
            # Manually follow redirects with SSRF checks on each target
            current_url = url
            for _ in range(self.MAX_REDIRECTS):
                response = await self._client.get(current_url)
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        result.error = "Redirect with no Location header"
                        return result
                    redirect_url = urljoin(current_url, location)
                    if not allow_internal:
                        redirect_safe, redirect_reason = is_safe_url(redirect_url)
                        if not redirect_safe:
                            result.error = f"SSRF blocked on redirect: {redirect_reason}"
                            logger.warning(
                                f"Blocked SSRF redirect: {current_url} -> {redirect_url}"
                            )
                            return result
                    current_url = redirect_url
                    continue
                break

            result.status_code = response.status_code

            if response.status_code != 200:
                result.error = f"HTTP {response.status_code}"
                return result

            # Parse HTML
            soup = BeautifulSoup(response.text, "lxml")

            # Extract title
            title_tag = soup.find("title")
            if title_tag:
                result.title = title_tag.get_text(strip=True)

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Extract text
            result.text = soup.get_text(separator="\n", strip=True)
            # Clean up excessive whitespace
            result.text = re.sub(r'\n{3,}', '\n\n', result.text)

            # Extract links
            base_url = url
            for link in soup.find_all("a", href=True):
                href = link["href"]
                absolute_url = urljoin(base_url, href)
                # Filter out non-http links
                if absolute_url.startswith(("http://", "https://")):
                    result.links.append(absolute_url)

            # Deduplicate links
            result.links = list(dict.fromkeys(result.links))

            # Extract images
            for img in soup.find_all("img", src=True):
                src = img["src"]
                absolute_url = urljoin(base_url, src)
                if absolute_url.startswith(("http://", "https://")):
                    result.images.append(absolute_url)

            result.images = list(dict.fromkeys(result.images))

        except httpx.TimeoutException:
            result.error = "Timeout"
        except httpx.RequestError as e:
            result.error = str(e)
        except Exception as e:
            result.error = f"Parse error: {e}"
            logger.exception(f"Error crawling {url}")

        return result

    async def crawl(
        self,
        start_url: str,
        max_depth: int | None = None,
        same_domain: bool = True,
        pattern: str | None = None,
    ) -> list[CrawlResult]:
        """
        Crawl starting from a URL, following links up to max_depth.

        Args:
            start_url: URL to start crawling from
            max_depth: Maximum depth to crawl (overrides instance setting)
            same_domain: Only follow links on the same domain
            pattern: Regex pattern to filter URLs

        Returns:
            List of CrawlResults for all visited pages
        """
        max_depth = max_depth or self.max_depth
        start_domain = urlparse(start_url).netloc

        results: list[CrawlResult] = []
        queue: list[tuple[str, int]] = [(start_url, 0)]
        self._visited = set()

        pattern_re = re.compile(pattern) if pattern else None

        async with self:
            while queue and len(results) < self.max_pages:
                url, depth = queue.pop(0)

                # Skip if already visited
                if url in self._visited:
                    continue

                # Skip if exceeds max depth
                if depth > max_depth:
                    continue

                # Check domain restriction
                if same_domain and urlparse(url).netloc != start_domain:
                    continue

                # Check pattern
                if pattern_re and not pattern_re.search(url):
                    continue

                self._visited.add(url)
                logger.debug(f"Crawling: {url} (depth={depth})")

                # Fetch page
                result = await self.fetch(url)
                result.depth = depth
                results.append(result)

                # Rate limiting
                if self.rate_limit > 0:
                    await asyncio.sleep(self.rate_limit)

                # Add links to queue
                if result.links and depth < max_depth:
                    for link in result.links:
                        if link not in self._visited:
                            queue.append((link, depth + 1))

        return results

    async def get_links(
        self,
        url: str,
        same_domain: bool = False,
        pattern: str | None = None,
    ) -> list[str]:
        """
        Get all links from a single page.

        Args:
            url: URL to fetch
            same_domain: Only return links on the same domain
            pattern: Regex pattern to filter URLs

        Returns:
            List of URLs found on the page
        """
        result = await self.fetch(url)

        links = result.links
        start_domain = urlparse(url).netloc

        # Filter by domain
        if same_domain:
            links = [link for link in links if urlparse(link).netloc == start_domain]

        # Filter by pattern
        if pattern:
            pattern_re = re.compile(pattern)
            links = [link for link in links if pattern_re.search(link)]

        return links

    async def extract_text(self, url: str) -> str:
        """Extract just the text content from a URL."""
        result = await self.fetch(url)
        return result.text

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc

    def normalize_url(self, url: str, base_url: str | None = None) -> str:
        """Normalize a URL, resolving relative paths."""
        if base_url:
            url = urljoin(base_url, url)

        # Remove fragment
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


