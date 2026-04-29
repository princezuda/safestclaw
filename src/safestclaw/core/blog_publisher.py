"""
Blog Publisher - Publish blog posts to multiple platforms.

Supported targets:
- WordPress (REST API v2 - native)
- Joomla (Web Services API - native)
- SFTP upload (any server)
- Generic webhook/API (POST JSON)

Each target is configured in config.yaml under publish_targets.
Multiple targets can be active simultaneously.
"""

import asyncio
import io
import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PublishTargetType(StrEnum):
    """Supported publishing target types."""
    WORDPRESS = "wordpress"
    JOOMLA = "joomla"
    SFTP = "sftp"
    API = "api"


@dataclass
class PublishTarget:
    """Configuration for a publishing target."""
    label: str
    target_type: PublishTargetType
    url: str = ""
    username: str = ""
    password: str = ""
    api_key: str = ""
    # SFTP-specific
    sftp_host: str = ""
    sftp_port: int = 22
    sftp_user: str = ""
    sftp_password: str = ""
    sftp_key_path: str = ""
    sftp_remote_path: str = "/var/www/html/blog"
    # WordPress-specific
    wp_status: str = "publish"
    wp_category_ids: list[int] = field(default_factory=list)
    wp_tag_ids: list[int] = field(default_factory=list)
    wp_author_id: int = 0
    # Joomla-specific
    joomla_category_id: int = 0
    joomla_access: int = 1
    joomla_featured: bool = False
    # Generic API
    api_method: str = "POST"
    api_headers: dict[str, str] = field(default_factory=dict)
    api_body_template: str = ""
    # General
    enabled: bool = True


@dataclass
class PublishResult:
    """Result of a publish operation."""
    success: bool
    target_label: str
    target_type: str
    url: str = ""
    post_id: str = ""
    message: str = ""
    error: str = ""


class BlogPublisher:
    """
    Multi-target blog publisher.

    Publishes blog posts to WordPress, Joomla, SFTP, and generic APIs.
    """

    def __init__(self, targets: list[PublishTarget] | None = None):
        self.targets: dict[str, PublishTarget] = {}
        if targets:
            for t in targets:
                self.targets[t.label] = t

    def add_target(self, target: PublishTarget) -> None:
        """Register a publishing target."""
        self.targets[target.label] = target
        logger.info(f"Registered publish target: {target.label} ({target.target_type})")

    def list_targets(self) -> list[dict[str, Any]]:
        """List all configured publishing targets."""
        result = []
        for label, t in self.targets.items():
            result.append({
                "label": label,
                "type": t.target_type.value,
                "url": t.url or t.sftp_host,
                "enabled": t.enabled,
            })
        return result

    async def publish(
        self,
        title: str,
        content: str,
        target_label: str | None = None,
        excerpt: str = "",
        slug: str = "",
        tags: list[str] | None = None,
        featured: bool = False,
    ) -> list[PublishResult]:
        """
        Publish a blog post to one or all targets.

        Args:
            title: Post title
            content: Post body (HTML or plain text)
            target_label: Specific target, or None for all enabled targets
            excerpt: Short summary/excerpt
            slug: URL slug
            tags: Tag names
            featured: Whether this should be featured/front-page

        Returns:
            List of PublishResult for each target attempted
        """
        tags = tags or []
        results = []

        if target_label:
            # Publish to specific target
            if target_label not in self.targets:
                return [PublishResult(
                    success=False,
                    target_label=target_label,
                    target_type="unknown",
                    error=f"Target '{target_label}' not found.",
                )]
            targets_to_publish = [self.targets[target_label]]
        else:
            # Publish to all enabled targets
            targets_to_publish = [t for t in self.targets.values() if t.enabled]

        if not targets_to_publish:
            return [PublishResult(
                success=False,
                target_label="none",
                target_type="none",
                error="No publishing targets configured or enabled.",
            )]

        # Publish to each target concurrently
        tasks = []
        for target in targets_to_publish:
            tasks.append(self._publish_to_target(
                target, title, content, excerpt, slug, tags, featured,
            ))

        results = await asyncio.gather(*tasks)
        return list(results)

    async def _publish_to_target(
        self,
        target: PublishTarget,
        title: str,
        content: str,
        excerpt: str,
        slug: str,
        tags: list[str],
        featured: bool,
    ) -> PublishResult:
        """Route to the appropriate publisher."""
        if target.target_type == PublishTargetType.WORDPRESS:
            return await self._publish_wordpress(target, title, content, excerpt, slug, tags, featured)
        elif target.target_type == PublishTargetType.JOOMLA:
            return await self._publish_joomla(target, title, content, excerpt, slug, tags, featured)
        elif target.target_type == PublishTargetType.SFTP:
            return await self._publish_sftp(target, title, content, excerpt, slug)
        elif target.target_type == PublishTargetType.API:
            return await self._publish_api(target, title, content, excerpt, slug, tags)
        else:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type=target.target_type.value,
                error=f"Unsupported target type: {target.target_type}",
            )

    # ── WordPress REST API v2 ────────────────────────────────────────────────

    async def _publish_wordpress(
        self,
        target: PublishTarget,
        title: str,
        content: str,
        excerpt: str,
        slug: str,
        tags: list[str],
        featured: bool,
    ) -> PublishResult:
        """
        Publish to WordPress via REST API v2.

        Supports:
        - Application Passwords (username + app password)
        - JWT auth (via api_key)
        - Basic auth
        """
        base_url = target.url.rstrip("/")
        api_url = f"{base_url}/wp-json/wp/v2/posts"

        # Build auth headers
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth = None

        if target.api_key:
            # JWT or Bearer token
            headers["Authorization"] = f"Bearer {target.api_key}"
        elif target.username and target.password:
            # Application Password / Basic Auth
            auth = (target.username, target.password)

        # Build post data
        post_data: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": target.wp_status,
        }

        if excerpt:
            post_data["excerpt"] = excerpt
        if slug:
            post_data["slug"] = slug
        if target.wp_category_ids:
            post_data["categories"] = target.wp_category_ids
        if target.wp_tag_ids:
            post_data["tags"] = target.wp_tag_ids
        if target.wp_author_id:
            post_data["author"] = target.wp_author_id
        if featured:
            post_data["sticky"] = True

        # Resolve tag names to IDs if tags provided as strings
        if tags:
            tag_ids = await self._wp_resolve_tags(base_url, tags, headers, auth)
            existing_tags = post_data.get("tags", [])
            post_data["tags"] = list(set(existing_tags + tag_ids))

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(api_url, json=post_data, headers=headers, auth=auth)
                resp.raise_for_status()
                data = resp.json()

            post_id = str(data.get("id", ""))
            post_url = data.get("link", "")

            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="wordpress",
                url=post_url,
                post_id=post_id,
                message=f"Published to WordPress: {post_url}",
            )
        except httpx.HTTPStatusError as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="wordpress",
                error=f"WordPress API error {e.response.status_code}: {e.response.text[:300]}",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="wordpress",
                error=f"WordPress publish failed: {e}",
            )

    async def _wp_resolve_tags(
        self,
        base_url: str,
        tag_names: list[str],
        headers: dict[str, str],
        auth: tuple[str, str] | None,
    ) -> list[int]:
        """Resolve tag names to WordPress tag IDs, creating if needed."""
        tag_ids = []
        tags_url = f"{base_url}/wp-json/wp/v2/tags"

        async with httpx.AsyncClient(timeout=15.0) as client:
            for name in tag_names:
                try:
                    # Search for existing tag
                    resp = await client.get(
                        tags_url, params={"search": name}, headers=headers, auth=auth,
                    )
                    resp.raise_for_status()
                    existing = resp.json()

                    if existing:
                        tag_ids.append(existing[0]["id"])
                    else:
                        # Create new tag
                        resp = await client.post(
                            tags_url,
                            json={"name": name},
                            headers=headers,
                            auth=auth,
                        )
                        resp.raise_for_status()
                        tag_ids.append(resp.json()["id"])
                except Exception as e:
                    logger.warning(f"Could not resolve tag '{name}': {e}")

        return tag_ids

    async def wp_set_front_page(
        self,
        target: PublishTarget,
        page_id: int,
    ) -> PublishResult:
        """
        Set a page as the WordPress front page.

        Requires: Settings > Reading > "A static page" enabled.
        Uses the WordPress Settings API.
        """
        base_url = target.url.rstrip("/")
        settings_url = f"{base_url}/wp-json/wp/v2/settings"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth = None

        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        elif target.username and target.password:
            auth = (target.username, target.password)

        payload = {
            "show_on_front": "page",
            "page_on_front": page_id,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(settings_url, json=payload, headers=headers, auth=auth)
                resp.raise_for_status()

            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="wordpress",
                post_id=str(page_id),
                message=f"Front page set to page ID {page_id}",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="wordpress",
                error=f"Failed to set front page: {e}",
            )

    async def wp_get_pages(
        self,
        target: PublishTarget,
    ) -> list[dict[str, Any]]:
        """List WordPress pages (for front page selection)."""
        base_url = target.url.rstrip("/")
        pages_url = f"{base_url}/wp-json/wp/v2/pages"

        headers: dict[str, str] = {}
        auth = None

        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        elif target.username and target.password:
            auth = (target.username, target.password)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    pages_url, params={"per_page": 50}, headers=headers, auth=auth,
                )
                resp.raise_for_status()
                pages = resp.json()

            return [
                {"id": p["id"], "title": p["title"]["rendered"], "link": p["link"]}
                for p in pages
            ]
        except Exception as e:
            logger.error(f"Failed to list WordPress pages: {e}")
            return []

    # ── Joomla Web Services API ──────────────────────────────────────────────

    async def _publish_joomla(
        self,
        target: PublishTarget,
        title: str,
        content: str,
        excerpt: str,
        slug: str,
        tags: list[str],
        featured: bool,
    ) -> PublishResult:
        """
        Publish to Joomla via Web Services API (Joomla 4+).

        Authentication: API Token (Bearer) or Basic Auth.
        """
        base_url = target.url.rstrip("/")
        api_url = f"{base_url}/api/index.php/v1/content/articles"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth = None

        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        elif target.username and target.password:
            import base64
            creds = base64.b64encode(f"{target.username}:{target.password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

        # Joomla article structure
        article_data: dict[str, Any] = {
            "title": title,
            "articletext": content,
            "catid": target.joomla_category_id or 2,  # 2 = Uncategorised
            "state": 1,  # Published
            "access": target.joomla_access,
            "featured": 1 if (featured or target.joomla_featured) else 0,
            "language": "*",
        }

        if slug:
            article_data["alias"] = slug
        if excerpt:
            # Joomla uses introtext/fulltext split
            article_data["articletext"] = f"{excerpt}\n<hr id=\"system-readmore\" />\n{content}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(api_url, json=article_data, headers=headers, auth=auth)
                resp.raise_for_status()
                data = resp.json()

            article = data.get("data", {})
            article_id = str(article.get("id", article.get("attributes", {}).get("id", "")))

            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="joomla",
                url=f"{base_url}/index.php?option=com_content&view=article&id={article_id}",
                post_id=article_id,
                message=f"Published to Joomla (article ID: {article_id})",
            )
        except httpx.HTTPStatusError as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="joomla",
                error=f"Joomla API error {e.response.status_code}: {e.response.text[:300]}",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="joomla",
                error=f"Joomla publish failed: {e}",
            )

    async def joomla_set_featured(
        self,
        target: PublishTarget,
        article_id: int,
        featured: bool = True,
    ) -> PublishResult:
        """Set/unset a Joomla article as featured (front page)."""
        base_url = target.url.rstrip("/")
        api_url = f"{base_url}/api/index.php/v1/content/articles/{article_id}"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth = None

        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        elif target.username and target.password:
            import base64
            creds = base64.b64encode(f"{target.username}:{target.password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.patch(
                    api_url,
                    json={"featured": 1 if featured else 0},
                    headers=headers,
                    auth=auth,
                )
                resp.raise_for_status()

            status = "featured" if featured else "unfeatured"
            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="joomla",
                post_id=str(article_id),
                message=f"Article {article_id} is now {status} on front page.",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="joomla",
                error=f"Failed to update featured status: {e}",
            )

    # ── SFTP Upload ──────────────────────────────────────────────────────────

    async def _publish_sftp(
        self,
        target: PublishTarget,
        title: str,
        content: str,
        excerpt: str,
        slug: str,
    ) -> PublishResult:
        """
        Upload blog post as HTML file via SFTP.

        Uses the system sftp/scp command (no extra Python deps needed).
        Falls back to paramiko if available.
        """
        # Generate HTML file
        timestamp = datetime.now().strftime("%Y-%m-%d")
        safe_slug = slug or re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '-').lower()
        filename = f"{timestamp}-{safe_slug}.html"

        html_content = self._generate_html(title, content, excerpt, timestamp)

        # Try sftp command first (no extra deps)
        remote_path = f"{target.sftp_remote_path.rstrip('/')}/{filename}"

        result = await self._sftp_upload_via_command(
            target, html_content, remote_path, filename,
        )

        if result.success:
            return result

        # Fallback: try paramiko if available
        try:
            return await self._sftp_upload_via_paramiko(
                target, html_content, remote_path, filename,
            )
        except ImportError:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="sftp",
                error=(
                    f"SFTP upload failed. Command-line error: {result.error}\n"
                    "Install paramiko for Python-native SFTP: pip install paramiko"
                ),
            )

    async def _sftp_upload_via_command(
        self,
        target: PublishTarget,
        content: str,
        remote_path: str,
        filename: str,
    ) -> PublishResult:
        """Upload via scp/sftp command-line tool."""
        import tempfile

        # Write content to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            # Build scp command
            port_flag = f"-P {target.sftp_port}" if target.sftp_port != 22 else ""
            key_flag = f"-i {target.sftp_key_path}" if target.sftp_key_path else ""
            user_host = f"{target.sftp_user}@{target.sftp_host}" if target.sftp_user else target.sftp_host

            cmd = f"scp {port_flag} {key_flag} -o StrictHostKeyChecking=accept-new {temp_path} {user_host}:{remote_path}"

            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode == 0:
                return PublishResult(
                    success=True,
                    target_label=target.label,
                    target_type="sftp",
                    url=f"sftp://{target.sftp_host}{remote_path}",
                    message=f"Uploaded via SCP to {user_host}:{remote_path}",
                )
            else:
                return PublishResult(
                    success=False,
                    target_label=target.label,
                    target_type="sftp",
                    error=f"SCP failed: {stderr.decode()[:300]}",
                )
        except TimeoutError:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="sftp",
                error="SFTP upload timed out after 30s",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="sftp",
                error=str(e),
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    async def _sftp_upload_via_paramiko(
        self,
        target: PublishTarget,
        content: str,
        remote_path: str,
        filename: str,
    ) -> PublishResult:
        """Upload via paramiko (Python SFTP library)."""
        import paramiko

        try:
            transport = paramiko.Transport((target.sftp_host, target.sftp_port))

            if target.sftp_key_path:
                key = paramiko.RSAKey.from_private_key_file(target.sftp_key_path)
                transport.connect(username=target.sftp_user, pkey=key)
            else:
                transport.connect(
                    username=target.sftp_user,
                    password=target.sftp_password,
                )

            sftp = paramiko.SFTPClient.from_transport(transport)
            if sftp is None:
                raise RuntimeError("Could not create SFTP client")

            # Ensure remote directory exists
            remote_dir = str(Path(remote_path).parent)
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                sftp.mkdir(remote_dir)

            # Upload
            file_obj = io.BytesIO(content.encode("utf-8"))
            sftp.putfo(file_obj, remote_path)

            sftp.close()
            transport.close()

            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="sftp",
                url=f"sftp://{target.sftp_host}{remote_path}",
                message=f"Uploaded via SFTP to {target.sftp_host}:{remote_path}",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="sftp",
                error=f"Paramiko SFTP failed: {e}",
            )

    def _generate_html(
        self,
        title: str,
        content: str,
        excerpt: str,
        date: str,
    ) -> str:
        """Generate a standalone HTML blog post."""
        # Convert plain text to HTML paragraphs if not already HTML
        if "<p>" not in content and "<div>" not in content:
            paragraphs = content.split("\n\n")
            html_body = "\n".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
        else:
            html_body = content

        excerpt_meta = f'<meta name="description" content="{excerpt[:160]}">' if excerpt else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {excerpt_meta}
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; color: #333; }}
        h1 {{ color: #1a1a1a; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }}
        .date {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; }}
        .excerpt {{ font-style: italic; color: #555; border-left: 3px solid #ccc;
                    padding-left: 1rem; margin-bottom: 2rem; }}
    </style>
</head>
<body>
    <article>
        <h1>{title}</h1>
        <p class="date">Published: {date}</p>
        {f'<p class="excerpt">{excerpt}</p>' if excerpt else ''}
        {html_body}
    </article>
</body>
</html>"""

    # ── SFTP index/front page generation ─────────────────────────────────────

    async def sftp_update_index(
        self,
        target: PublishTarget,
        posts: list[dict[str, str]],
        front_page_slug: str = "",
    ) -> PublishResult:
        """
        Generate and upload an index.html listing blog posts via SFTP.

        If front_page_slug is set, that post is featured at the top.

        Args:
            target: SFTP target config
            posts: List of dicts with 'title', 'slug', 'date', 'excerpt'
            front_page_slug: Slug of the post to feature on the front page
        """
        html = self._generate_index_html(posts, front_page_slug)
        remote_path = f"{target.sftp_remote_path.rstrip('/')}/index.html"

        result = await self._sftp_upload_via_command(target, html, remote_path, "index.html")
        if not result.success:
            try:
                result = await self._sftp_upload_via_paramiko(target, html, remote_path, "index.html")
            except ImportError:
                pass

        if result.success:
            result.message = f"Blog index updated at {target.sftp_host}:{remote_path}"

        return result

    def _generate_index_html(
        self,
        posts: list[dict[str, str]],
        front_page_slug: str = "",
    ) -> str:
        """Generate an index.html page listing blog posts."""
        # Separate featured post
        featured_html = ""
        regular_posts = []

        for post in posts:
            if front_page_slug and post.get("slug") == front_page_slug:
                featured_html = f"""
        <div class="featured">
            <h2>Featured</h2>
            <h3><a href="{post['slug']}.html">{post['title']}</a></h3>
            <p class="date">{post.get('date', '')}</p>
            <p>{post.get('excerpt', '')}</p>
        </div>"""
            else:
                regular_posts.append(post)

        posts_html = ""
        for post in regular_posts:
            posts_html += f"""
        <div class="post">
            <h3><a href="{post['slug']}.html">{post['title']}</a></h3>
            <p class="date">{post.get('date', '')}</p>
            <p>{post.get('excerpt', '')}</p>
        </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Blog</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; color: #333; }}
        h1 {{ color: #1a1a1a; }}
        .featured {{ background: #f8f9fa; padding: 1.5rem; border-radius: 8px;
                     border-left: 4px solid #007bff; margin-bottom: 2rem; }}
        .featured h2 {{ color: #007bff; font-size: 0.9rem; text-transform: uppercase; margin: 0 0 0.5rem; }}
        .post {{ border-bottom: 1px solid #eee; padding: 1rem 0; }}
        .post h3 a {{ color: #1a1a1a; text-decoration: none; }}
        .post h3 a:hover {{ color: #007bff; }}
        .date {{ color: #666; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <h1>Blog</h1>
    {featured_html}
    <div class="posts">
        {posts_html}
    </div>
</body>
</html>"""

    # ── Generic API Publishing ───────────────────────────────────────────────

    async def _publish_api(
        self,
        target: PublishTarget,
        title: str,
        content: str,
        excerpt: str,
        slug: str,
        tags: list[str],
    ) -> PublishResult:
        """
        Publish via generic API (POST/PUT JSON).

        The body template can use placeholders:
        {title}, {content}, {excerpt}, {slug}, {tags}, {date}
        """
        headers = {"Content-Type": "application/json"}
        headers.update(target.api_headers)

        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"

        date = datetime.now().isoformat()

        if target.api_body_template:
            # Use custom template
            body_str = target.api_body_template.format(
                title=title,
                content=content,
                excerpt=excerpt,
                slug=slug,
                tags=json.dumps(tags),
                date=date,
            )
            body = json.loads(body_str)
        else:
            # Default structure
            body = {
                "title": title,
                "content": content,
                "excerpt": excerpt,
                "slug": slug,
                "tags": tags,
                "date": date,
            }

        method = target.api_method.upper()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "PUT":
                    resp = await client.put(target.url, json=body, headers=headers)
                else:
                    resp = await client.post(target.url, json=body, headers=headers)

                resp.raise_for_status()
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            post_id = str(data.get("id", data.get("post_id", "")))

            return PublishResult(
                success=True,
                target_label=target.label,
                target_type="api",
                url=target.url,
                post_id=post_id,
                message=f"Published via API to {target.url}",
            )
        except Exception as e:
            return PublishResult(
                success=False,
                target_label=target.label,
                target_type="api",
                error=f"API publish failed: {e}",
            )

    # ── Configuration loading ────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "BlogPublisher":
        """
        Create BlogPublisher from config dict.

        Expected format:
            publish_targets:
              - label: "my-wordpress"
                type: "wordpress"
                url: "https://mysite.com"
                username: "admin"
                password: "xxxx xxxx xxxx xxxx"
              - label: "my-server"
                type: "sftp"
                sftp_host: "myserver.com"
                sftp_user: "deploy"
                sftp_key_path: "~/.ssh/id_rsa"
                sftp_remote_path: "/var/www/html/blog"
        """
        targets_list = config.get("publish_targets", [])
        targets = []

        for t in targets_list:
            try:
                target_type = PublishTargetType(t.get("type", "api"))
            except ValueError:
                target_type = PublishTargetType.API

            target = PublishTarget(
                label=t.get("label", f"target-{len(targets)}"),
                target_type=target_type,
                url=t.get("url", ""),
                username=t.get("username", ""),
                password=t.get("password", ""),
                api_key=t.get("api_key", ""),
                sftp_host=t.get("sftp_host", ""),
                sftp_port=t.get("sftp_port", 22),
                sftp_user=t.get("sftp_user", ""),
                sftp_password=t.get("sftp_password", ""),
                sftp_key_path=t.get("sftp_key_path", ""),
                sftp_remote_path=t.get("sftp_remote_path", "/var/www/html/blog"),
                wp_status=t.get("wp_status", "publish"),
                wp_category_ids=t.get("wp_category_ids", []),
                wp_tag_ids=t.get("wp_tag_ids", []),
                wp_author_id=t.get("wp_author_id", 0),
                joomla_category_id=t.get("joomla_category_id", 0),
                joomla_access=t.get("joomla_access", 1),
                joomla_featured=t.get("joomla_featured", False),
                api_method=t.get("api_method", "POST"),
                api_headers=t.get("api_headers", {}),
                api_body_template=t.get("api_body_template", ""),
                enabled=t.get("enabled", True),
            )
            targets.append(target)

        return cls(targets=targets)
