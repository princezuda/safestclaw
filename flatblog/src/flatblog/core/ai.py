"""AI post generation — supports Anthropic, OpenAI-compatible, and Ollama."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

_BANNED_PHRASES = [
    "in today's", "rapidly evolving", "fast-paced", "cutting-edge", "state-of-the-art",
    "next-generation", "game-changer", "revolutionary", "paradigm shift", "disruptive",
    "seamlessly", "effortlessly", "leverage", "utilize", "facilitate",
    "it is important to note", "as we can see", "in conclusion", "to summarize",
    "to wrap things up", "in this article", "this post will explore",
    "in the world of", "in the realm of", "delve into", "dive into",
    "tapestry", "bustling", "vibrant", "transformative", "innovative solution",
    "unlock the potential", "harness the power", "shed light on",
]


class AIWriter:
    """Thin async AI client that writes blog posts from topics."""

    def __init__(self, cfg: dict[str, Any], blog_root: Path | None = None):
        self._cfg = cfg
        self._blog_root = blog_root
        ai = cfg.get("ai", {})
        self.provider = ai.get("provider", "").lower()
        self.api_key = ai.get("api_key") or os.environ.get("FLATBLOG_AI_KEY", "")
        self.model = ai.get("model", "")
        self.base_url = ai.get("base_url", "").rstrip("/")

        topics_cfg = cfg.get("topics", {})
        self.tone = topics_cfg.get("tone", "")
        self.word_count = topics_cfg.get("word_count", 800)
        self.style_file = topics_cfg.get("style_file", "")

    def is_configured(self) -> bool:
        if self.provider == "ollama":
            return bool(self.model)
        return bool(self.api_key and self.model)

    def _load_style(self) -> str:
        """Load style file. Resolves relative paths against the blog root."""
        candidates: list[Path] = []

        if self.style_file:
            p = Path(self.style_file).expanduser()
            candidates.append(p)
            if self._blog_root and not p.is_absolute():
                candidates.append(self._blog_root / p)

        # Auto-discover style-guide.md at the blog root if no explicit file works
        if self._blog_root:
            candidates.append(self._blog_root / "style-guide.md")

        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        return ""

    def _build_system_prompt(self) -> str:
        style = self._load_style()

        if style:
            # Style guide takes over — inject it as the primary instruction
            parts = [
                "You are a blog writer. Follow the style guide below exactly.",
                "Output only the post itself in Markdown: start with # Title, then the body.",
                "Do not add any preamble, meta-commentary, or sign-off.",
                "",
                style,
                "",
                f"Target length: approximately {self.word_count} words.",
            ]
            if self.tone:
                parts.append(f"Tone: {self.tone}.")
        else:
            # Fallback — still enforce anti-AI-speak rules
            banned = ", ".join(f'"{p}"' for p in _BANNED_PHRASES[:12])
            parts = [
                "You are a blog writer. Write a complete blog post in Markdown.",
                "Start with a single # heading for the title, then write the body.",
                "Output only the post itself — no preamble, no sign-off.",
                "",
                "Rules:",
                "- Write directly. Get to the point in the first sentence.",
                "- Use short and medium sentences. Vary the rhythm.",
                "- Be specific: name the actual tools, give real numbers.",
                "- Be honest about tradeoffs. Don't oversell.",
                "- Do NOT use these phrases or anything like them: " + banned,
                "- Do NOT open with a question, a definition, or a statistic you then undermine.",
                "- Do NOT end with 'In conclusion' or 'To summarize'.",
                "",
                f"Target length: approximately {self.word_count} words.",
            ]
            if self.tone:
                parts.append(f"Tone: {self.tone}.")

        return "\n".join(parts)

    def _build_user_prompt(self, topic: str) -> str:
        return f"Write a complete blog post about: {topic}"

    async def generate(
        self,
        topic: str,
        fetch_image: bool = False,
        images_dir: Path | None = None,
    ) -> tuple[str, str, str]:
        """
        Generate a post. Returns (title, body_markdown, cover_image).

        cover_image is a local relative path or URL if fetch_image=True,
        else an empty string.
        """
        if not self.is_configured():
            raise RuntimeError(
                "AI not configured. Run: flatblog setup ai anthropic sk-ant-..."
            )

        system = self._build_system_prompt()
        user = self._build_user_prompt(topic)

        if self.provider == "anthropic":
            content = await self._call_anthropic(system, user)
        elif self.provider == "ollama":
            content = await self._call_ollama(system, user)
        else:
            content = await self._call_openai(system, user)

        title, body = _extract_title_body(content, topic)

        cover_image = ""
        if fetch_image:
            from .images import fetch_image as _fetch
            cover_image = await _fetch(title or topic, self._cfg, save_dir=images_dir)

        return title, body, cover_image

    async def _call_anthropic(self, system: str, user: str) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model or "claude-haiku-4-5-20251001",
            "max_tokens": max(self.word_count * 2, 2048),
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            return r.json()["content"][0]["text"]

    async def _call_openai(self, system: str, user: str) -> str:
        base = self.base_url or "https://api.openai.com/v1"
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model or "gpt-4o-mini",
            "max_tokens": max(self.word_count * 2, 2048),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    async def _call_ollama(self, system: str, user: str) -> str:
        base = self.base_url or "http://localhost:11434/api"
        url = f"{base}/chat"
        body = {
            "model": self.model or "llama3.2",
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json()["message"]["content"]


def _extract_title_body(content: str, fallback_topic: str) -> tuple[str, str]:
    """Split AI response into (title, body). Title comes from first # heading."""
    content = content.strip()
    lines = content.splitlines()
    title = fallback_topic
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    return title, body
