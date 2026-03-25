"""Build the static site: Markdown → HTML, index, tag pages, RSS feed."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

from .post import Post, load_all_posts
from .feeds import generate_rss
from .images import copy_post_images


md_parser = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True})


def render_markdown(text: str) -> str:
    return md_parser.render(text)


def build_site(
    root: Path,
    cfg: dict[str, Any],
    include_drafts: bool = False,
    verbose: bool = False,
) -> int:
    """Build the entire site. Returns number of posts rendered."""
    posts_dir = root / "posts"
    output_dir = root / cfg.get("output_dir", "output")
    theme_name = cfg.get("theme", "default")

    # Find theme directory — check repo-local themes/ first, then package themes/
    theme_dir = root / "themes" / theme_name
    if not theme_dir.exists():
        theme_dir = Path(__file__).parent.parent.parent / "themes" / theme_name
    if not theme_dir.exists():
        raise FileNotFoundError(f"Theme not found: {theme_name}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy static assets from theme
    static_src = theme_dir / "static"
    if static_src.exists():
        shutil.copytree(static_src, output_dir / "static", dirs_exist_ok=True)

    # Copy post images: posts/images/ → output/images/
    copy_post_images(posts_dir, output_dir)

    env = Environment(
        loader=FileSystemLoader(str(theme_dir)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown"] = render_markdown
    env.filters["date_fmt"] = lambda d, fmt=None: d.strftime(
        fmt or cfg.get("blog", {}).get("date_format", "%B %d, %Y")
    )

    blog_meta = cfg.get("blog", {})
    posts = load_all_posts(posts_dir, include_drafts=include_drafts)

    if not posts:
        if verbose:
            print("No posts found in posts/")
        return 0

    # Render individual posts
    post_tmpl = env.get_template("post.html")
    for post in posts:
        html = post_tmpl.render(
            post=post,
            content=render_markdown(post.body),
            blog=blog_meta,
            all_posts=posts,
        )
        out = output_dir / post.output_filename
        out.write_text(html, encoding="utf-8")
        if verbose:
            print(f"  {post.output_filename}")

    # Render index
    index_tmpl = env.get_template("index.html")
    index_html = index_tmpl.render(
        posts=posts,
        blog=blog_meta,
        all_posts=posts,
    )
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    # Render tag pages
    tag_tmpl_path = theme_dir / "tag.html"
    if tag_tmpl_path.exists():
        all_tags: dict[str, list[Post]] = {}
        for post in posts:
            for tag in post.tags:
                all_tags.setdefault(tag, []).append(post)
        tags_dir = output_dir / "tags"
        tags_dir.mkdir(exist_ok=True)
        tag_tmpl = env.get_template("tag.html")
        for tag, tag_posts in all_tags.items():
            tag_slug = tag.lower().replace(" ", "-")
            html = tag_tmpl.render(
                tag=tag,
                posts=tag_posts,
                blog=blog_meta,
                all_posts=posts,
            )
            (tags_dir / f"{tag_slug}.html").write_text(html, encoding="utf-8")

    # Generate RSS feed
    rss = generate_rss(posts, blog_meta)
    (output_dir / "feed.xml").write_text(rss, encoding="utf-8")

    # Generate sitemap.xml
    sitemap = _generate_sitemap(posts, blog_meta)
    (output_dir / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    return len(posts)


def _generate_sitemap(posts: list[Post], blog_meta: dict) -> str:
    base_url = blog_meta.get("url", "").rstrip("/")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    # Index
    lines.append(f"  <url><loc>{base_url}/</loc></url>")
    for post in posts:
        lines.append(
            f"  <url>"
            f"<loc>{base_url}/{post.output_filename}</loc>"
            f"<lastmod>{post.date.isoformat()}</lastmod>"
            f"</url>"
        )
    lines.append("</urlset>")
    return "\n".join(lines)
