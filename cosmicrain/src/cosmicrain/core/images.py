"""Image fetching — Unsplash and Pexels free APIs, plus local image management."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ── Fetchers ──────────────────────────────────────────────────────────────────

async def fetch_image(
    keywords: str,
    cfg: dict[str, Any],
    save_dir: Path | None = None,
) -> str:
    """
    Fetch a relevant image for the given keywords.

    Returns:
        Local relative path (images/filename.jpg) if save_dir is given and
        save_local is True, otherwise an https:// URL.
        Empty string if images are disabled or fetch fails.
    """
    images_cfg = cfg.get("images", {})
    source = images_cfg.get("source", "none").lower()

    if source == "none" or not source:
        return ""

    access_key = images_cfg.get("access_key", "")
    save_local = images_cfg.get("save_local", True)

    try:
        if source == "unsplash":
            url, filename = await _fetch_unsplash(keywords, access_key)
        elif source == "pexels":
            url, filename = await _fetch_pexels(keywords, access_key)
        else:
            return ""
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Image fetch failed: {e}")
        return ""

    if not url:
        return ""

    if save_local and save_dir is not None:
        local_path = await _download_image(url, filename, save_dir)
        if local_path:
            return f"images/{local_path.name}"

    return url


async def _fetch_unsplash(keywords: str, access_key: str) -> tuple[str, str]:
    """
    Fetch one image from the Unsplash API.
    Requires a free Unsplash Developer account (50 requests/hour).
    https://unsplash.com/developers
    """
    import httpx

    if not access_key:
        raise ValueError(
            "Unsplash access key not set. Run: cosmicrain setup images unsplash YOUR-KEY"
        )

    query = keywords[:100]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
        )
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return "", ""

    photo = results[0]
    url = photo["urls"]["regular"]          # ~1080px wide
    photo_id = photo["id"]
    slug = _slugify(keywords)[:40]
    filename = f"{slug}-{photo_id[:8]}.jpg"

    # Unsplash requires attribution — embed it in the alt/caption
    return url, filename


async def _fetch_pexels(keywords: str, access_key: str) -> tuple[str, str]:
    """
    Fetch one image from the Pexels API.
    Requires a free Pexels account (200 requests/hour).
    https://www.pexels.com/api/
    """
    import httpx

    if not access_key:
        raise ValueError(
            "Pexels API key not set. Run: cosmicrain setup images pexels YOUR-KEY"
        )

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.pexels.com/v1/search",
            params={"query": keywords[:100], "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": access_key},
        )
        r.raise_for_status()
        data = r.json()

    photos = data.get("photos", [])
    if not photos:
        return "", ""

    photo = photos[0]
    url = photo["src"]["large"]             # ~940px wide
    photo_id = photo["id"]
    slug = _slugify(keywords)[:40]
    filename = f"{slug}-{photo_id}.jpg"
    return url, filename


async def _download_image(url: str, filename: str, save_dir: Path) -> Path | None:
    """Download image to save_dir/filename. Returns the saved path."""
    import httpx

    save_dir.mkdir(parents=True, exist_ok=True)
    dest = save_dir / filename

    if dest.exists():
        return dest  # already downloaded

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
        return dest
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not download image {url}: {e}")
        return None


# ── Local image management ────────────────────────────────────────────────────

def copy_post_images(posts_dir: Path, output_dir: Path) -> int:
    """
    Copy posts/images/ → output/images/ at build time.
    Also copies any per-post image folders (posts/my-post-images/).
    Returns number of files copied.
    """
    copied = 0
    images_src = posts_dir / "images"
    images_dst = output_dir / "images"

    if images_src.exists():
        import shutil
        shutil.copytree(images_src, images_dst, dirs_exist_ok=True)
        copied += sum(1 for f in images_src.rglob("*") if f.is_file())

    return copied


def list_images(posts_dir: Path) -> list[Path]:
    """List all images in posts/images/."""
    images_dir = posts_dir / "images"
    if not images_dir.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif"}
    return sorted(
        f for f in images_dir.iterdir()
        if f.is_file() and f.suffix.lower() in exts
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")
