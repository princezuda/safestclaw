"""
Front Page Manager - Manage which blog post appears on the front/home page.

Supports:
- WordPress: Set static front page via Settings API
- Joomla: Toggle featured status on articles
- SFTP: Regenerate index.html with featured post at top
- Track front page preference locally per target
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safestclaw.core.blog_publisher import (
    BlogPublisher,
    PublishResult,
    PublishTarget,
    PublishTargetType,
)

logger = logging.getLogger(__name__)


@dataclass
class FrontPageConfig:
    """Front page configuration for a target."""
    target_label: str
    post_id: str = ""
    post_title: str = ""
    slug: str = ""
    updated_at: str = ""


class FrontPageManager:
    """
    Manages front page settings across publishing targets.

    The user specifies which post is the front/home page, and this
    manager coordinates the update across WordPress, Joomla, SFTP, etc.
    """

    def __init__(
        self,
        publisher: BlogPublisher,
        state_dir: Path | None = None,
    ):
        self.publisher = publisher
        self.state_dir = state_dir or Path.home() / ".safestclaw" / "frontpage"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self.state_dir / "frontpage_state.json"
        self._state: dict[str, FrontPageConfig] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load front page state from disk."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                for label, cfg in data.items():
                    self._state[label] = FrontPageConfig(
                        target_label=label,
                        post_id=cfg.get("post_id", ""),
                        post_title=cfg.get("post_title", ""),
                        slug=cfg.get("slug", ""),
                        updated_at=cfg.get("updated_at", ""),
                    )
            except Exception as e:
                logger.warning(f"Could not load front page state: {e}")

    def _save_state(self) -> None:
        """Save front page state to disk."""
        data = {}
        for label, cfg in self._state.items():
            data[label] = {
                "post_id": cfg.post_id,
                "post_title": cfg.post_title,
                "slug": cfg.slug,
                "updated_at": cfg.updated_at,
            }
        self._state_file.write_text(json.dumps(data, indent=2))

    def get_front_page(self, target_label: str) -> FrontPageConfig | None:
        """Get the current front page config for a target."""
        return self._state.get(target_label)

    def get_all_front_pages(self) -> dict[str, FrontPageConfig]:
        """Get front page config for all targets."""
        return dict(self._state)

    async def set_front_page(
        self,
        target_label: str,
        post_id: str,
        post_title: str = "",
        slug: str = "",
    ) -> PublishResult:
        """
        Set a post as the front page for a specific target.

        Args:
            target_label: The publishing target label
            post_id: The post/article/page ID
            post_title: Human-readable title
            slug: URL slug (used for SFTP)

        Returns:
            PublishResult indicating success/failure
        """
        if target_label not in self.publisher.targets:
            return PublishResult(
                success=False,
                target_label=target_label,
                target_type="unknown",
                error=f"Target '{target_label}' not found.",
            )

        target = self.publisher.targets[target_label]

        # Update the front page on the target platform
        result = await self._update_platform_front_page(target, post_id, slug)

        if result.success:
            # Save state locally
            from datetime import datetime
            self._state[target_label] = FrontPageConfig(
                target_label=target_label,
                post_id=post_id,
                post_title=post_title,
                slug=slug,
                updated_at=datetime.now().isoformat(),
            )
            self._save_state()

        return result

    async def _update_platform_front_page(
        self,
        target: PublishTarget,
        post_id: str,
        slug: str,
    ) -> PublishResult:
        """Update front page on the specific platform."""
        if target.target_type == PublishTargetType.WORDPRESS:
            return await self.publisher.wp_set_front_page(target, int(post_id))

        elif target.target_type == PublishTargetType.JOOMLA:
            return await self.publisher.joomla_set_featured(target, int(post_id), featured=True)

        elif target.target_type == PublishTargetType.SFTP:
            # For SFTP, we regenerate the index with this post featured
            # Load published posts from local blog dir
            posts = self._get_local_posts()
            return await self.publisher.sftp_update_index(
                target, posts, front_page_slug=slug,
            )

        elif target.target_type == PublishTargetType.API:
            # For generic API, re-publish with featured flag
            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="api",
                post_id=post_id,
                message=f"Front page preference saved locally for API target (post ID: {post_id}). "
                        "The API target does not have a native front page concept.",
            )

        return PublishResult(
            success=False,
            target_label=target.label,
            target_type=target.target_type.value,
            error=f"Front page management not supported for {target.target_type}",
        )

    def _get_local_posts(self) -> list[dict[str, str]]:
        """Load published blog posts from local blog directory."""
        blog_dir = Path.home() / ".safestclaw" / "blogs"
        posts = []

        if not blog_dir.exists():
            return posts

        for f in sorted(blog_dir.glob("*.txt"), reverse=True):
            if f.name.startswith("draft-"):
                continue
            content = f.read_text()
            lines = content.split("\n")
            title = lines[0] if lines else f.stem
            # Extract date from filename
            date_match = f.name[:10]  # YYYY-MM-DD
            slug = f.stem
            # Simple excerpt: first paragraph after title
            excerpt = ""
            for line in lines[2:]:
                if line.strip():
                    excerpt = line.strip()[:160]
                    break

            posts.append({
                "title": title,
                "slug": slug,
                "date": date_match,
                "excerpt": excerpt,
            })

        return posts

    async def list_pages(self, target_label: str) -> list[dict[str, Any]]:
        """
        List available pages/posts for front page selection.

        For WordPress: fetches pages via REST API.
        For Joomla: fetches articles via API.
        For SFTP: lists local published blog files.
        """
        if target_label not in self.publisher.targets:
            return []

        target = self.publisher.targets[target_label]

        if target.target_type == PublishTargetType.WORDPRESS:
            return await self.publisher.wp_get_pages(target)

        elif target.target_type == PublishTargetType.JOOMLA:
            return await self._joomla_list_articles(target)

        elif target.target_type == PublishTargetType.SFTP:
            return [
                {"id": p["slug"], "title": p["title"], "date": p["date"]}
                for p in self._get_local_posts()
            ]

        return []

    async def _joomla_list_articles(
        self,
        target: PublishTarget,
    ) -> list[dict[str, Any]]:
        """List Joomla articles for front page selection."""
        import httpx

        base_url = target.url.rstrip("/")
        api_url = f"{base_url}/api/index.php/v1/content/articles"

        headers: dict[str, str] = {}
        auth = None

        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        elif target.username and target.password:
            import base64
            creds = base64.b64encode(f"{target.username}:{target.password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    api_url,
                    params={"list[limit]": 50},
                    headers=headers,
                    auth=auth,
                )
                resp.raise_for_status()
                data = resp.json()

            articles = data.get("data", [])
            return [
                {
                    "id": a.get("id", a.get("attributes", {}).get("id", "")),
                    "title": a.get("attributes", {}).get("title", ""),
                    "featured": a.get("attributes", {}).get("featured", 0),
                }
                for a in articles
            ]
        except Exception as e:
            logger.error(f"Failed to list Joomla articles: {e}")
            return []

    def show_status(self) -> str:
        """Return human-readable front page status."""
        if not self._state:
            return "No front page configured for any target."

        lines = ["**Front Page Status**", ""]
        for label, cfg in self._state.items():
            target = self.publisher.targets.get(label)
            target_type = target.target_type.value if target else "unknown"
            lines.append(
                f"  {label} ({target_type}): "
                f"{cfg.post_title or cfg.post_id or 'not set'}"
                f" (updated: {cfg.updated_at[:10] if cfg.updated_at else 'never'})"
            )

        return "\n".join(lines)
