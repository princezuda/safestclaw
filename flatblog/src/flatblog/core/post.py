"""Post model — reads/writes Markdown files with YAML frontmatter."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Post:
    path: Path
    title: str
    date: date
    author: str = ""
    tags: list[str] = field(default_factory=list)
    draft: bool = False
    description: str = ""          # used in RSS + meta description
    slug: str = ""                 # derived from filename if blank
    cover_image: str = ""          # URL or relative path (images/file.jpg)
    extra: dict[str, Any] = field(default_factory=dict)
    body: str = ""                 # raw Markdown body (no frontmatter)

    @property
    def url_slug(self) -> str:
        return self.slug or self.path.stem

    @property
    def output_filename(self) -> str:
        return f"{self.url_slug}.html"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "date": self.date,
            "author": self.author,
            "tags": self.tags,
            "draft": self.draft,
            "description": self.description,
            "slug": self.url_slug,
            "body": self.body,
            "path": str(self.path),
        }


def parse_post(path: Path) -> Post:
    """Parse a Markdown file with optional YAML frontmatter."""
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = raw

    m = FRONTMATTER_RE.match(raw)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = raw[m.end():]

    # Derive date from filename like 2025-01-15-my-post.md
    stem = path.stem
    date_obj: date = meta.get("date") or _date_from_stem(stem) or datetime.today().date()
    if isinstance(date_obj, datetime):
        date_obj = date_obj.date()

    slug = meta.get("slug", "")
    if not slug:
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)  # strip leading date

    known = {"title", "date", "author", "tags", "draft", "description", "slug", "cover_image"}
    return Post(
        path=path,
        title=meta.get("title", slug.replace("-", " ").title()),
        date=date_obj,
        author=meta.get("author", ""),
        tags=meta.get("tags") or [],
        draft=bool(meta.get("draft", False)),
        description=meta.get("description", ""),
        slug=slug,
        cover_image=meta.get("cover_image", ""),
        extra={k: v for k, v in meta.items() if k not in known},
        body=body.strip(),
    )


def write_post(path: Path, title: str, body: str = "", **meta: Any) -> Post:
    """Write a new Markdown file with frontmatter and return the Post."""
    today = datetime.today().date()
    slug = meta.get("slug") or _slugify(title)
    fm: dict[str, Any] = {
        "title": title,
        "date": today,
        "author": meta.get("author", ""),
        "tags": meta.get("tags", []),
        "draft": meta.get("draft", True),
        "description": meta.get("description", ""),
        "cover_image": meta.get("cover_image", ""),
    }
    content = f"---\n{yaml.dump(fm, default_flow_style=False, allow_unicode=True)}---\n\n{body}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return parse_post(path)


def _date_from_stem(stem: str) -> date | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", stem)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].strip("-")


def load_all_posts(posts_dir: Path, include_drafts: bool = False) -> list[Post]:
    """Load all .md posts, sorted newest first."""
    posts = []
    for p in posts_dir.glob("*.md"):
        try:
            post = parse_post(p)
            if post.draft and not include_drafts:
                continue
            posts.append(post)
        except Exception:
            pass
    return sorted(posts, key=lambda p: p.date, reverse=True)
