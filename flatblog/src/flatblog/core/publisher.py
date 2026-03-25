"""Publish built site to SFTP or WordPress."""
from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx


async def publish_all(output_dir: Path, cfg: dict[str, Any], target_label: str = "") -> list[str]:
    """Publish output/ to all (or one) configured targets. Returns status lines."""
    targets = cfg.get("publish", {}).get("targets", [])
    if not targets:
        return ["No publish targets configured. Run: flatblog setup publish sftp://..."]

    results: list[str] = []
    for t in targets:
        label = t.get("label", "")
        if target_label and label != target_label:
            continue
        ttype = t.get("type", "").lower()
        if ttype == "sftp":
            results.append(await _publish_sftp(output_dir, t))
        elif ttype == "wordpress":
            results.extend(await _publish_wordpress(output_dir, t, cfg))
        else:
            results.append(f"Unknown target type '{ttype}' for '{label}'")
    return results


# ── SFTP ──────────────────────────────────────────────────────────────────────

async def _publish_sftp(output_dir: Path, t: dict[str, Any]) -> str:
    host = t.get("host", "")
    port = t.get("port", 22)
    user = t.get("user", "")
    password = t.get("password", "")
    key_file = t.get("key_file", "")
    remote = t.get("remote_path", "/var/www/blog").rstrip("/")
    label = t.get("label", host)

    try:
        import paramiko  # type: ignore
    except ImportError:
        return f"[{label}] paramiko not installed: pip install paramiko"

    def _upload() -> str:
        transport = paramiko.Transport((host, int(port)))
        if key_file:
            key_path = Path(key_file).expanduser()
            pkey = paramiko.RSAKey.from_private_key_file(str(key_path))
            transport.connect(username=user, pkey=pkey)
        else:
            transport.connect(username=user, password=password)

        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None

        uploaded = 0
        for local_file in output_dir.rglob("*"):
            if local_file.is_file():
                rel = local_file.relative_to(output_dir)
                remote_path = f"{remote}/{rel.as_posix()}"
                # Ensure remote directory exists
                remote_dir = str(Path(remote_path).parent)
                _sftp_mkdir_p(sftp, remote_dir)
                sftp.put(str(local_file), remote_path)
                uploaded += 1

        sftp.close()
        transport.close()
        return f"[{label}] Uploaded {uploaded} files to {host}:{remote}"

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _upload)
        return result
    except Exception as e:
        return f"[{label}] SFTP error: {e}"


def _sftp_mkdir_p(sftp: Any, remote_dir: str) -> None:
    parts = remote_dir.replace("\\", "/").split("/")
    path = ""
    for part in parts:
        if not part:
            path = "/"
            continue
        path = f"{path}/{part}" if path and path != "/" else f"/{part}"
        try:
            sftp.stat(path)
        except FileNotFoundError:
            sftp.mkdir(path)


# ── WordPress ─────────────────────────────────────────────────────────────────

async def _publish_wordpress(
    output_dir: Path, t: dict[str, Any], cfg: dict[str, Any]
) -> list[str]:
    from .post import load_all_posts
    from .builder import render_markdown

    root = output_dir.parent  # posts are one level up
    posts_dir = root / "posts"
    posts = load_all_posts(posts_dir)

    base_url = t.get("url", "").rstrip("/")
    user = t.get("user", "")
    app_password = t.get("app_password", "")
    label = t.get("label", base_url)
    api = f"{base_url}/wp-json/wp/v2/posts"
    auth = (user, app_password)

    results: list[str] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for post in posts:
            html_body = render_markdown(post.body)
            payload = {
                "title": post.title,
                "content": html_body,
                "status": "draft" if post.draft else "publish",
                "slug": post.url_slug,
                "excerpt": post.description,
                "date": post.date.isoformat() + "T00:00:00",
            }
            if post.tags:
                tag_ids = await _wp_tag_ids(client, base_url, auth, post.tags)
                payload["tags"] = tag_ids

            # Upload cover image and set as featured_media
            if post.cover_image:
                media_id = await _wp_upload_image(
                    client, base_url, auth, post.cover_image, posts_dir, post.title
                )
                if media_id:
                    payload["featured_media"] = media_id

            r = await client.post(api, json=payload, auth=auth)
            if r.status_code in (200, 201):
                results.append(f"[{label}] Published: {post.title}")
            else:
                results.append(f"[{label}] Failed '{post.title}': {r.status_code} {r.text[:120]}")
    return results


async def _wp_upload_image(
    client: httpx.AsyncClient,
    base: str,
    auth: tuple,
    cover_image: str,
    posts_dir: Path,
    post_title: str,
) -> int | None:
    """
    Upload a cover image to the WordPress media library.

    cover_image may be:
      - a local relative path like "images/photo.jpg"  (resolved under posts_dir)
      - an https:// URL (downloaded first)

    Returns the WP media ID, or None on failure.
    """
    import mimetypes

    media_api = f"{base}/wp-json/wp/v2/media"

    # Resolve image bytes
    if cover_image.startswith("http://") or cover_image.startswith("https://"):
        try:
            resp = await client.get(cover_image, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            image_bytes = resp.content
            filename = cover_image.rstrip("/").split("/")[-1].split("?")[0] or "cover.jpg"
        except Exception:
            return None
    else:
        # Local path relative to posts_dir (e.g. "images/photo.jpg")
        local = posts_dir / cover_image
        if not local.exists():
            return None
        image_bytes = local.read_bytes()
        filename = local.name

    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        mime = "image/jpeg"

    try:
        r = await client.post(
            media_api,
            content=image_bytes,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": mime,
            },
            auth=auth,
        )
        if r.status_code == 201:
            return r.json().get("id")
    except Exception:
        pass
    return None


async def _wp_tag_ids(
    client: httpx.AsyncClient, base: str, auth: tuple, tags: list[str]
) -> list[int]:
    ids: list[int] = []
    for tag in tags:
        r = await client.get(f"{base}/wp-json/wp/v2/tags", params={"search": tag}, auth=auth)
        existing = r.json() if r.status_code == 200 else []
        if existing:
            ids.append(existing[0]["id"])
        else:
            cr = await client.post(f"{base}/wp-json/wp/v2/tags", json={"name": tag}, auth=auth)
            if cr.status_code == 201:
                ids.append(cr.json()["id"])
    return ids
