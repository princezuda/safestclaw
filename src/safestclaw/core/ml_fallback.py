"""
Deterministic ML fall-backs for AI-shaped tasks.

When every configured LLM provider fails (auth, quota, network), the
action layer can call into here to get a still-useful response built
from the same offline ML stack SafestClaw ships with — sumy for
extractive summaries, simple heuristics for headlines, and so on.

Nothing here calls an LLM. None of these helpers are as good as a real
language model, but they're predictable, free, and they keep the
chat working when the API is down.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from safestclaw.core.summarizer import Summarizer


def _summarizer() -> Summarizer:
    from safestclaw.core.summarizer import Summarizer
    return Summarizer()


def fallback_rewrite(content: str, target_sentences: int = 6) -> str:
    """
    Stand-in for AIWriter.rewrite_blog: keep the user's text but
    extract the most salient sentences, then drop them back into a
    cleaned-up paragraph structure.
    """
    if not content.strip():
        return content
    try:
        summary = _summarizer().summarize(content, sentences=target_sentences)
    except Exception as e:
        logger.warning(f"fallback_rewrite summarize failed: {e}")
        return content
    if not summary.strip():
        return content
    # Re-paragraph: every two sentences become one paragraph for readability.
    sents = re.split(r"(?<=[.!?])\s+", summary.strip())
    paragraphs: list[str] = []
    buf: list[str] = []
    for s in sents:
        if not s:
            continue
        buf.append(s)
        if len(buf) == 2:
            paragraphs.append(" ".join(buf))
            buf = []
    if buf:
        paragraphs.append(" ".join(buf))
    return "\n\n".join(paragraphs)


def fallback_expand(content: str) -> str:
    """
    Stand-in for AIWriter.expand_blog: we can't truly expand without
    an LLM, but we can give the user back a structured version of
    their draft with a TL;DR section, the body, and a 3-bullet
    "key points" appendix derived from extracted keywords.
    """
    if not content.strip():
        return content
    try:
        s = _summarizer()
        tldr = s.summarize(content, sentences=2)
        keywords = s.get_keywords(content, top_n=6)
    except Exception as e:
        logger.warning(f"fallback_expand failed: {e}")
        return content

    parts = []
    if tldr.strip():
        parts.append("**TL;DR**\n" + tldr.strip())
    parts.append(content.strip())
    if keywords:
        bullets = "\n".join(f"- {k.title()}" for k in keywords[:5])
        parts.append("**Key points**\n" + bullets)
    return "\n\n".join(parts)


def fallback_headlines(content: str, count: int = 5) -> str:
    """
    Stand-in for AIWriter.generate_headlines: returns ``count`` headline
    candidates built from the extracted keywords + the first sentence.
    Format matches what the LLM helpers return — one per line — so
    callers don't have to special-case anything.
    """
    if not content.strip():
        return ""
    try:
        s = _summarizer()
        keywords = s.get_keywords(content, top_n=10)
        first = s.summarize(content, sentences=1).strip().rstrip(".")
    except Exception as e:
        logger.warning(f"fallback_headlines failed: {e}")
        return ""
    candidates: list[str] = []
    if first:
        candidates.append(first)
    if keywords:
        kw = [k.title() for k in keywords[:6]]
        if len(kw) >= 3:
            candidates.append(f"{kw[0]}, {kw[1]}, and the {kw[2]} angle")
        if len(kw) >= 2:
            candidates.append(f"What {kw[0]} means for {kw[1]}")
            candidates.append(f"{kw[0]}: a closer look")
            candidates.append(f"The {kw[0]} story you missed")
        else:
            candidates.append(f"{kw[0]}: the basics")
    return "\n".join(f"{i}. {c}" for i, c in enumerate(candidates[:count], 1))


def fallback_excerpt(content: str, max_chars: int = 160) -> str:
    """Stand-in for AIWriter.generate_excerpt: extractive 1-sentence
    summary trimmed to the meta-description budget."""
    if not content.strip():
        return ""
    try:
        out = _summarizer().summarize(content, sentences=1).strip()
    except Exception:
        out = content.strip().split("\n", 1)[0]
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out


def fallback_seo(content: str) -> str:
    """Stand-in for AIWriter.generate_seo: keyword-driven metadata."""
    excerpt = fallback_excerpt(content, max_chars=160)
    try:
        keywords = _summarizer().get_keywords(content, top_n=10)
    except Exception:
        keywords = []
    title = excerpt[:55].rstrip(".!?") if excerpt else "Untitled"
    slug = re.sub(r"[^\w\s-]", "", title)[:50].strip().lower().replace(" ", "-")
    tags = ", ".join(keywords[:8]) if keywords else "blog"
    return (
        f"Meta title:       {title}\n"
        f"Meta description: {excerpt}\n"
        f"Tags / keywords:  {tags}\n"
        f"URL slug:         {slug}\n"
    )


def fallback_generate_blog(topic: str, context: str = "") -> str:
    """
    Stand-in for AIWriter.generate_blog: build a structured post from
    the topic + supplied context (typically gathered news/feed items
    for auto-blog) using only sumy + a fixed template.
    """
    body_source = context.strip() or topic
    try:
        s = _summarizer()
        summary = s.summarize(body_source, sentences=6)
        keywords = s.get_keywords(body_source, top_n=8)
    except Exception as e:
        logger.warning(f"fallback_generate_blog failed: {e}")
        summary = body_source[:1500]
        keywords = []

    topic_clean = topic.strip().rstrip(".") or "Today's roundup"
    sections = [
        f"# {topic_clean}\n",
        "## Overview\n",
        summary or "_No source material to summarize._",
    ]
    if context:
        sections.extend([
            "\n## Sources covered\n",
            context.strip()[:2000],
        ])
    if keywords:
        sections.extend([
            "\n## Themes\n",
            ", ".join(k.title() for k in keywords[:8]),
        ])
    sections.append(
        "\n_Generated locally without an LLM — install or configure an "
        "AI provider in `config.yaml` for AI-quality writing._"
    )
    return "\n".join(sections)


def offline_ml_banner(reason: str = "") -> str:
    """Banner the action layer prepends when serving an ML fallback."""
    if reason:
        return (
            f"_(Falling back to local ML — {reason}. "
            "Configure an AI provider for richer output.)_\n\n"
        )
    return (
        "_(Falling back to local ML — every configured AI provider "
        "failed. Configure / fix a provider for richer output.)_\n\n"
    )
