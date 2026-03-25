"""Style guide management — load, save, import, edit."""
from __future__ import annotations

from pathlib import Path


_DEFAULT_GUIDE_NAME = "style-guide.md"


def style_path(blog_root: Path) -> Path:
    return blog_root / _DEFAULT_GUIDE_NAME


def load_style(blog_root: Path) -> str:
    p = style_path(blog_root)
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def save_style(blog_root: Path, text: str) -> None:
    style_path(blog_root).write_text(text.strip() + "\n", encoding="utf-8")


def reset_style(blog_root: Path) -> None:
    """Restore the built-in safeclaw style guide."""
    _builtin = _builtin_guide()
    save_style(blog_root, _builtin)


async def import_from_url(url: str) -> str:
    import httpx
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text.strip()


def import_from_file(path: str) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Not found: {p}")
    return p.read_text(encoding="utf-8").strip()


def _builtin_guide() -> str:
    """Return the built-in SafeClaw writing style guide."""
    # Look for it next to this module's package tree
    candidates = [
        Path(__file__).parent.parent.parent.parent / "style-guide.md",  # repo root
        Path(__file__).parent.parent.parent.parent.parent / "style-guide.md",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    return _FALLBACK_GUIDE


# ── Fallback (embedded) ────────────────────────────────────────────────────────
# Matches the style-guide.md at the repo root — kept in sync manually.

_FALLBACK_GUIDE = """\
# Writing Style Guide

## The voice

Direct. Confident. No hedging. No hype.

Get to the point in the first sentence. If the first sentence could be deleted \
without losing anything, delete it. Skip "In today's world" and anything like it. \
Start with the thing.

## Sentence rhythm

Mix short and medium sentences. After a long explanation, hit it with a short one. \
Use a colon before a short payoff: deterministic, predictable, free.

## Numbers and specifics

Be specific. Not "many feeds" — "50+ feeds." Not "supports algorithms" — \
"LexRank, TextRank, LSA, Luhn." Bold the number when it's the whole point: **$0**, **100 stars**.

## Em-dashes

Use em-dashes for asides and to separate a feature from what it does:

> **Real Research** — searches actual academic databases

## Honest about tradeoffs

Don't hide limitations. Say them plainly. Admitting a tradeoff builds more \
trust than hiding it.

## What to never write

Banned phrases:
- in today's / rapidly evolving / fast-paced
- seamlessly, effortlessly, powerful (as filler)
- cutting-edge, state-of-the-art, next-generation
- leverage (use "use"), utilize (use "use")
- game-changer, revolutionary, paradigm shift
- this post will explore / in this article
- in conclusion / to summarize
- delve into, dive into, tapestry, vibrant, transformative

## Length

600–900 words. Stop when done. Cut padding.
"""
