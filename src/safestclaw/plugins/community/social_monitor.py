"""
SafestClaw Social Monitor Plugin - Track usernames and summarize new posts.

Monitors social media accounts and shows new posts/@mentions since last check.

Supports:
- X/Twitter (via Nitter instances or RSS bridges)
- Mastodon (native API, no auth needed for public)
- Bluesky (AT Protocol)
- RSS feeds (any)

Usage:
    "watch @username" / "follow @username" - Start monitoring a user
    "check @username" - Get new posts since last check
    "unwatch @username" - Stop monitoring
    "list watched" - Show all monitored accounts
"""

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


@dataclass
class WatchedAccount:
    """A monitored social media account."""
    username: str
    platform: str  # twitter, mastodon, bluesky, rss
    display_name: str | None = None
    last_checked: str | None = None
    last_post_id: str | None = None
    url: str | None = None
    added: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Post:
    """A social media post."""
    id: str
    author: str
    content: str
    timestamp: str | None = None
    url: str | None = None
    is_mention: bool = False
    is_reply: bool = False


class SocialMonitorPlugin(BasePlugin):
    """
    Monitor social media accounts for new posts and mentions.

    Summarizes activity since last check without needing API keys
    for most platforms (uses public endpoints/RSS).
    """

    info = PluginInfo(
        name="social",
        version="1.0.0",
        description="Monitor social accounts, summarize new posts and mentions",
        author="SafestClaw Community",
        keywords=[
            "watch", "follow", "monitor", "twitter", "x", "mastodon", "bluesky",
            "posts", "mentions", "social", "check", "unwatch",
        ],
        patterns=[
            r"(?i)^(?:watch|follow|monitor)\s+@?(\S+)",
            r"(?i)^check\s+@?(\S+)",
            r"(?i)^unwatch\s+@?(\S+)",
            r"(?i)^(?:list|show)\s+(?:watched|following|monitored)",
            r"(?i)^social\s+(?:status|help)",
        ],
        examples=[
            "watch @elonmusk",
            "check @github",
            "unwatch @someone",
            "list watched",
        ],
    )

    # Nitter instances (Twitter frontends) - rotate if one fails
    NITTER_INSTANCES = [
        "nitter.net",
        "nitter.privacydev.net",
        "nitter.poast.org",
        "nitter.woodland.cafe",
    ]

    def __init__(self):
        self._engine: Any = None
        self._data_file: Path | None = None
        self.accounts: dict[str, WatchedAccount] = {}
        self._http_client: Any = None

    def on_load(self, engine: Any) -> None:
        """Initialize plugin."""
        self._engine = engine
        self._data_file = engine.data_dir / "watched_accounts.json"
        self._load_accounts()

    def _load_accounts(self) -> None:
        """Load watched accounts from disk."""
        if self._data_file and self._data_file.exists():
            try:
                data = json.loads(self._data_file.read_text())
                for key, acc_data in data.items():
                    self.accounts[key] = WatchedAccount(**acc_data)
                logger.info(f"Loaded {len(self.accounts)} watched accounts")
            except Exception as e:
                logger.warning(f"Failed to load accounts: {e}")

    def _save_accounts(self) -> None:
        """Save watched accounts to disk."""
        if self._data_file:
            try:
                data = {k: asdict(v) for k, v in self.accounts.items()}
                self._data_file.write_text(json.dumps(data, indent=2))
            except Exception as e:
                logger.warning(f"Failed to save accounts: {e}")

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """Handle social monitoring commands."""
        text = params.get("raw_input", "").strip()
        text_lower = text.lower()

        # Watch/follow command
        match = re.match(r"(?i)^(?:watch|follow|monitor)\s+@?(\S+)", text)
        if match:
            username = match.group(1)
            return await self._watch_account(username)

        # Check command
        match = re.match(r"(?i)^check\s+@?(\S+)", text)
        if match:
            username = match.group(1)
            return await self._check_account(username)

        # Unwatch command
        match = re.match(r"(?i)^unwatch\s+@?(\S+)", text)
        if match:
            username = match.group(1)
            return self._unwatch_account(username)

        # List watched
        if any(kw in text_lower for kw in ["list watched", "show watched", "list following", "show following"]):
            return self._list_watched()

        # Status/help
        return self._get_status()

    def _detect_platform(self, username: str) -> tuple[str, str]:
        """
        Detect platform from username format.

        Returns (platform, clean_username)
        """
        # Full URLs
        if "twitter.com/" in username or "x.com/" in username:
            match = re.search(r"(?:twitter|x)\.com/(\w+)", username)
            return ("twitter", match.group(1) if match else username)

        if "mastodon" in username or "@" in username and "." in username.split("@")[-1]:
            # Mastodon format: @user@instance.social
            return ("mastodon", username.lstrip("@"))

        if "bsky.app" in username or ".bsky.social" in username:
            match = re.search(r"(?:bsky\.app/profile/)?([^\s/]+)", username)
            return ("bluesky", match.group(1) if match else username)

        # Default to Twitter/X
        return ("twitter", username.lstrip("@"))

    async def _watch_account(self, username: str) -> str:
        """Start monitoring an account."""
        platform, clean_username = self._detect_platform(username)
        key = f"{platform}:{clean_username}"

        if key in self.accounts:
            return f"Already watching @{clean_username} on {platform}"

        # Verify account exists by fetching
        posts = await self._fetch_posts(platform, clean_username, limit=1)

        if posts is None:
            return f"[yellow]Could not find @{clean_username} on {platform}[/yellow]"

        self.accounts[key] = WatchedAccount(
            username=clean_username,
            platform=platform,
            last_checked=datetime.now().isoformat(),
        )
        self._save_accounts()

        return f"[green]Now watching @{clean_username} on {platform}[/green]\n\nSay 'check @{clean_username}' to see new posts."

    async def _check_account(self, username: str) -> str:
        """Check for new posts since last check."""
        platform, clean_username = self._detect_platform(username)
        key = f"{platform}:{clean_username}"

        # Get or create account
        if key not in self.accounts:
            # Auto-watch if not already
            await self._watch_account(username)

        account = self.accounts.get(key)
        if not account:
            return f"[yellow]Could not find @{clean_username}[/yellow]"

        # Fetch recent posts
        posts = await self._fetch_posts(platform, clean_username, limit=20)

        if posts is None:
            return f"[red]Failed to fetch posts for @{clean_username}[/red]"

        if not posts:
            return f"No posts found for @{clean_username}"

        # Filter to new posts since last check
        new_posts = posts
        if account.last_post_id:
            new_posts = []
            for post in posts:
                if post.id == account.last_post_id:
                    break
                new_posts.append(post)

        # Update last checked
        if posts:
            account.last_post_id = posts[0].id
        account.last_checked = datetime.now().isoformat()
        self._save_accounts()

        if not new_posts:
            return f"No new posts from @{clean_username} since last check."

        # Format output
        lines = [f"[bold]@{clean_username}[/bold] - {len(new_posts)} new posts:\n"]

        mentions = [p for p in new_posts if p.is_mention]
        regular = [p for p in new_posts if not p.is_mention]

        if mentions:
            lines.append("[cyan]Mentions:[/cyan]")
            for post in mentions[:5]:
                preview = post.content[:100] + "..." if len(post.content) > 100 else post.content
                lines.append(f"  • {preview}")
            lines.append("")

        if regular:
            lines.append("[cyan]Posts:[/cyan]")
            for post in regular[:10]:
                preview = post.content[:100] + "..." if len(post.content) > 100 else post.content
                lines.append(f"  • {preview}")

        if len(new_posts) > 15:
            lines.append(f"\n[dim]...and {len(new_posts) - 15} more[/dim]")

        return "\n".join(lines)

    def _unwatch_account(self, username: str) -> str:
        """Stop monitoring an account."""
        platform, clean_username = self._detect_platform(username)
        key = f"{platform}:{clean_username}"

        if key not in self.accounts:
            # Try without platform prefix
            for k in list(self.accounts.keys()):
                if k.endswith(f":{clean_username}"):
                    del self.accounts[k]
                    self._save_accounts()
                    return f"[green]Stopped watching @{clean_username}[/green]"
            return f"Not watching @{clean_username}"

        del self.accounts[key]
        self._save_accounts()
        return f"[green]Stopped watching @{clean_username}[/green]"

    def _list_watched(self) -> str:
        """List all watched accounts."""
        if not self.accounts:
            return "Not watching any accounts.\n\nSay 'watch @username' to start monitoring."

        lines = ["[bold]Watched Accounts[/bold]\n"]

        by_platform: dict[str, list] = {}
        for acc in self.accounts.values():
            by_platform.setdefault(acc.platform, []).append(acc)

        for platform, accounts in sorted(by_platform.items()):
            lines.append(f"[cyan]{platform.title()}:[/cyan]")
            for acc in accounts:
                last = ""
                if acc.last_checked:
                    try:
                        dt = datetime.fromisoformat(acc.last_checked)
                        last = f" (checked {dt.strftime('%b %d %H:%M')})"
                    except ValueError:
                        pass
                lines.append(f"  • @{acc.username}{last}")
            lines.append("")

        return "\n".join(lines)

    def _get_status(self) -> str:
        """Get plugin status."""
        return (
            "[bold]Social Monitor[/bold]\n\n"
            f"Watching: {len(self.accounts)} accounts\n\n"
            "Commands:\n"
            "  • 'watch @username' - Start monitoring\n"
            "  • 'check @username' - Get new posts\n"
            "  • 'unwatch @username' - Stop monitoring\n"
            "  • 'list watched' - Show all monitored\n\n"
            "Supported platforms:\n"
            "  • X/Twitter (via Nitter)\n"
            "  • Mastodon (@user@instance)\n"
            "  • Bluesky (user.bsky.social)"
        )

    async def _fetch_posts(
        self,
        platform: str,
        username: str,
        limit: int = 20
    ) -> list[Post] | None:
        """Fetch posts from a platform."""
        try:
            if platform == "twitter":
                return await self._fetch_twitter(username, limit)
            elif platform == "mastodon":
                return await self._fetch_mastodon(username, limit)
            elif platform == "bluesky":
                return await self._fetch_bluesky(username, limit)
            else:
                logger.warning(f"Unknown platform: {platform}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch from {platform}: {e}")
            return None

    async def _get_http_client(self):
        """Get or create HTTP client."""
        if self._http_client is None:
            try:
                import httpx
                self._http_client = httpx.AsyncClient(
                    timeout=30.0,
                    follow_redirects=True,
                    headers={"User-Agent": "SafestClaw/1.0"}
                )
            except ImportError:
                logger.error("httpx not installed")
                return None
        return self._http_client

    async def _fetch_twitter(self, username: str, limit: int) -> list[Post] | None:
        """Fetch Twitter posts via Nitter RSS."""
        client = await self._get_http_client()
        if not client:
            return None

        posts = []

        # Try Nitter instances
        for instance in self.NITTER_INSTANCES:
            try:
                # Nitter provides RSS feeds
                url = f"https://{instance}/{username}/rss"
                response = await client.get(url)

                if response.status_code == 200:
                    # Parse RSS
                    posts = self._parse_rss(response.text, username)
                    if posts:
                        return posts[:limit]
            except Exception as e:
                logger.debug(f"Nitter {instance} failed: {e}")
                continue

        # All instances failed
        return None

    async def _fetch_mastodon(self, username: str, limit: int) -> list[Post] | None:
        """Fetch Mastodon posts via public API."""
        client = await self._get_http_client()
        if not client:
            return None

        # Parse user@instance format
        if "@" in username:
            parts = username.split("@")
            if len(parts) >= 2:
                user = parts[0] if parts[0] else parts[1]
                instance = parts[-1]
            else:
                return None
        else:
            return None

        try:
            # Lookup user
            lookup_url = f"https://{instance}/api/v1/accounts/lookup?acct={user}"
            response = await client.get(lookup_url)

            if response.status_code != 200:
                return None

            account_data = response.json()
            account_id = account_data.get("id")

            if not account_id:
                return None

            # Fetch statuses
            statuses_url = f"https://{instance}/api/v1/accounts/{account_id}/statuses?limit={limit}"
            response = await client.get(statuses_url)

            if response.status_code != 200:
                return None

            posts = []
            for status in response.json():
                # Strip HTML tags from content
                content = re.sub(r'<[^>]+>', '', status.get("content", ""))
                posts.append(Post(
                    id=status["id"],
                    author=username,
                    content=content,
                    timestamp=status.get("created_at"),
                    url=status.get("url"),
                    is_reply=status.get("in_reply_to_id") is not None,
                ))

            return posts

        except Exception as e:
            logger.error(f"Mastodon fetch failed: {e}")
            return None

    async def _fetch_bluesky(self, username: str, limit: int) -> list[Post] | None:
        """Fetch Bluesky posts via AT Protocol."""
        client = await self._get_http_client()
        if not client:
            return None

        # Ensure handle format
        if "." not in username:
            username = f"{username}.bsky.social"

        try:
            # Use public API
            url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
            params = {"actor": username, "limit": limit}

            response = await client.get(url, params=params)

            if response.status_code != 200:
                return None

            data = response.json()
            posts = []

            for item in data.get("feed", []):
                post = item.get("post", {})
                record = post.get("record", {})

                posts.append(Post(
                    id=post.get("uri", ""),
                    author=username,
                    content=record.get("text", ""),
                    timestamp=record.get("createdAt"),
                    url=f"https://bsky.app/profile/{username}/post/{post.get('uri', '').split('/')[-1]}",
                    is_reply=record.get("reply") is not None,
                ))

            return posts

        except Exception as e:
            logger.error(f"Bluesky fetch failed: {e}")
            return None

    def _parse_rss(self, xml_content: str, username: str) -> list[Post]:
        """Parse RSS feed into posts."""
        posts = []

        try:
            # Simple regex parsing (avoid xml dependency)
            items = re.findall(r'<item>(.*?)</item>', xml_content, re.DOTALL)

            for item in items:
                title = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
                link = re.search(r'<link>(.*?)</link>', item)
                guid = re.search(r'<guid>(.*?)</guid>', item)
                pubdate = re.search(r'<pubDate>(.*?)</pubDate>', item)
                desc = re.search(r'<description>(.*?)</description>', item, re.DOTALL)

                content = ""
                if desc:
                    # Unescape HTML entities and strip tags
                    content = desc.group(1)
                    content = content.replace("&lt;", "<").replace("&gt;", ">")
                    content = content.replace("&amp;", "&").replace("&quot;", '"')
                    content = re.sub(r'<[^>]+>', '', content)
                    content = content.strip()

                if not content and title:
                    content = title.group(1)

                posts.append(Post(
                    id=guid.group(1) if guid else link.group(1) if link else "",
                    author=username,
                    content=content,
                    timestamp=pubdate.group(1) if pubdate else None,
                    url=link.group(1) if link else None,
                    is_mention="@" in content if content else False,
                ))
        except Exception as e:
            logger.error(f"RSS parse failed: {e}")

        return posts

    def on_unload(self) -> None:
        """Cleanup."""
        if self._http_client:
            asyncio.create_task(self._http_client.aclose())
