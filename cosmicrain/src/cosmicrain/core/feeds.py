"""Generate RSS 2.0 feed from posts."""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from .post import Post


def generate_rss(posts: list[Post], blog_meta: dict[str, Any]) -> str:
    title = html.escape(blog_meta.get("title", "Blog"))
    link = blog_meta.get("url", "").rstrip("/")
    description = html.escape(blog_meta.get("description", ""))
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    items: list[str] = []
    for post in posts[:20]:
        pub_date = datetime(
            post.date.year, post.date.month, post.date.day
        ).strftime("%a, %d %b %Y 00:00:00 +0000")
        post_url = f"{link}/{post.output_filename}" if link else post.output_filename
        desc = html.escape(post.description or post.body[:200].replace("\n", " "))
        item_tags = "".join(
            f"<category>{html.escape(t)}</category>" for t in post.tags
        )
        items.append(f"""    <item>
      <title>{html.escape(post.title)}</title>
      <link>{post_url}</link>
      <guid isPermaLink="true">{post_url}</guid>
      <pubDate>{pub_date}</pubDate>
      <description>{desc}</description>
      {item_tags}
    </item>""")

    items_xml = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{title}</title>
    <link>{link}</link>
    <description>{description}</description>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{link}/feed.xml" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>
"""
