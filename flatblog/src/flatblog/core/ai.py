"""AI post generation — supports Anthropic, OpenAI-compatible, and Ollama."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


class AIWriter:
    """Thin async AI client that writes blog posts from topics."""

    def __init__(self, cfg: dict[str, Any]):
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
        if not self.style_file:
            return ""
        p = Path(self.style_file).expanduser()
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    def _build_system_prompt(self) -> str:
        parts = [
            "You are a skilled blog writer. Write a complete, engaging blog post in Markdown.",
            "Start with a single # heading for the title, then write the full post body.",
            "Do not include any preamble like 'Here is the post:' — output only the post itself.",
        ]
        if self.tone:
            parts.append(f"Writing tone: {self.tone}.")
        if self.word_count:
            parts.append(f"Target length: approximately {self.word_count} words.")
        style = self._load_style()
        if style:
            parts.append(f"\nWriting style guide:\n{style}")
        return "\n".join(parts)

    def _build_user_prompt(self, topic: str) -> str:
        return f"Write a complete blog post about: {topic}"

    async def generate(self, topic: str) -> tuple[str, str]:
        """
        Generate a post. Returns (title, body_markdown).
        Raises RuntimeError if not configured or on API error.
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
            # OpenAI-compatible (openai, groq, mistral, lm-studio, etc.)
            content = await self._call_openai(system, user)

        return _extract_title_body(content, topic)

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
