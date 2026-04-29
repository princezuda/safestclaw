"""
AI Writer - Multi-provider generative AI for blog content.

Supports local and cloud AI providers:

Local (free, private):
- Ollama       (https://ollama.com)
- LM Studio    (https://lmstudio.ai)
- llama.cpp    (https://github.com/ggerganov/llama.cpp)
- LocalAI      (https://localai.io)
- Jan          (https://jan.ai)

Cloud (API key required):
- OpenAI       (GPT-4o, GPT-4, GPT-3.5)
- Anthropic    (Claude Opus, Sonnet, Haiku)
- Google       (Gemini Pro, Gemini Flash)
- Mistral      (Mistral Large, Medium, Small)
- Groq         (Llama, Mixtral - fast inference)

All providers use OpenAI-compatible chat/completions API where possible,
so adding new providers is straightforward.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Local AI download/install links ──────────────────────────────────────────

LOCAL_AI_OPTIONS = {
    "ollama": {
        "name": "Ollama",
        "url": "https://ollama.com/download",
        "description": "Easiest local AI. One-command install, runs models locally.",
        "default_endpoint": "http://localhost:11434/api/chat",
        "api_style": "ollama",
        "recommended_models": ["llama3.1", "mistral", "gemma2", "phi3", "qwen2.5"],
        "install": "curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.1",
    },
    "lm_studio": {
        "name": "LM Studio",
        "url": "https://lmstudio.ai",
        "description": "GUI app for running local models. Download models from HuggingFace.",
        "default_endpoint": "http://localhost:1234/v1/chat/completions",
        "api_style": "openai",
        "recommended_models": ["lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"],
        "install": "Download from https://lmstudio.ai - GUI installer for Mac/Win/Linux",
    },
    "llamacpp": {
        "name": "llama.cpp Server",
        "url": "https://github.com/ggerganov/llama.cpp",
        "description": "High-performance C++ inference. Best for power users.",
        "default_endpoint": "http://localhost:8080/v1/chat/completions",
        "api_style": "openai",
        "recommended_models": ["Download GGUF models from HuggingFace"],
        "install": "git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && make",
    },
    "localai": {
        "name": "LocalAI",
        "url": "https://localai.io",
        "description": "Drop-in OpenAI replacement. Docker-based, many model formats.",
        "default_endpoint": "http://localhost:8080/v1/chat/completions",
        "api_style": "openai",
        "recommended_models": ["lunademo", "hermes-2-pro-mistral"],
        "install": "docker run -p 8080:8080 localai/localai:latest",
    },
    "jan": {
        "name": "Jan",
        "url": "https://jan.ai",
        "description": "Desktop AI app with built-in model library. Very user-friendly.",
        "default_endpoint": "http://localhost:1337/v1/chat/completions",
        "api_style": "openai",
        "recommended_models": ["llama3.1-8b", "mistral-7b", "phi-3"],
        "install": "Download from https://jan.ai - GUI installer",
    },
}


class AIProvider(StrEnum):
    """Supported AI providers."""
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    LLAMACPP = "llamacpp"
    LOCALAI = "localai"
    JAN = "jan"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"
    GROQ = "groq"
    CUSTOM = "custom"


# Default cloud endpoints
CLOUD_ENDPOINTS = {
    AIProvider.OPENAI: "https://api.openai.com/v1/chat/completions",
    AIProvider.ANTHROPIC: "https://api.anthropic.com/v1/messages",
    AIProvider.GOOGLE: "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    AIProvider.MISTRAL: "https://api.mistral.ai/v1/chat/completions",
    AIProvider.GROQ: "https://api.groq.com/openai/v1/chat/completions",
}

# Default models per provider
DEFAULT_MODELS = {
    AIProvider.OLLAMA: "llama3.1",
    AIProvider.LM_STUDIO: "local-model",
    AIProvider.LLAMACPP: "local-model",
    AIProvider.LOCALAI: "lunademo",
    AIProvider.JAN: "llama3.1-8b",
    AIProvider.OPENAI: "gpt-4o",
    AIProvider.ANTHROPIC: "claude-sonnet-4-5",
    AIProvider.GOOGLE: "gemini-1.5-flash",
    AIProvider.MISTRAL: "mistral-large-latest",
    AIProvider.GROQ: "llama-3.1-70b-versatile",
}


@dataclass
class AIProviderConfig:
    """Configuration for a single AI provider."""
    provider: AIProvider
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000
    enabled: bool = True
    label: str = ""

    def __post_init__(self):
        if not self.model:
            self.model = DEFAULT_MODELS.get(self.provider, "")
        if not self.endpoint:
            if self.provider in CLOUD_ENDPOINTS:
                self.endpoint = CLOUD_ENDPOINTS[self.provider]
            elif self.provider in LOCAL_AI_OPTIONS:
                self.endpoint = LOCAL_AI_OPTIONS[self.provider]["default_endpoint"]
        if not self.label:
            self.label = self.provider.value


@dataclass
class AIResponse:
    """Response from an AI provider."""
    content: str
    provider: str
    model: str
    tokens_used: int = 0
    error: str = ""


@dataclass
class BlogPromptTemplates:
    """Built-in prompt templates for blog writing tasks."""
    templates: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.templates:
            self.templates = {
                "generate": (
                    "Write a blog post about the following topic. "
                    "Make it engaging, informative, and well-structured with "
                    "headings, paragraphs, and a clear conclusion.\n\n"
                    "Topic: {topic}\n\n"
                    "Additional context:\n{context}"
                ),
                "rewrite": (
                    "Rewrite the following blog content to be more engaging "
                    "and professional. Maintain the key points but improve "
                    "the writing quality, flow, and readability.\n\n"
                    "Original content:\n{content}"
                ),
                "expand": (
                    "Expand the following blog content into a fuller, more detailed "
                    "article. Add depth, examples, and supporting points while "
                    "maintaining the original tone.\n\n"
                    "Content to expand:\n{content}"
                ),
                "headline": (
                    "Generate 5 compelling blog post headlines for the following "
                    "content. Each headline should be attention-grabbing and "
                    "SEO-friendly. Return only the headlines, one per line.\n\n"
                    "Content:\n{content}"
                ),
                "summary": (
                    "Write a concise summary/excerpt for this blog post "
                    "suitable for a homepage preview or meta description "
                    "(max 160 characters).\n\n"
                    "Blog content:\n{content}"
                ),
                "seo": (
                    "Generate SEO metadata for this blog post:\n"
                    "1. Meta title (max 60 chars)\n"
                    "2. Meta description (max 160 chars)\n"
                    "3. 5-10 keywords/tags\n"
                    "4. URL slug suggestion\n\n"
                    "Blog content:\n{content}"
                ),
            }

    def render(self, template_name: str, **kwargs: str) -> str:
        """Render a template with the given variables."""
        template = self.templates.get(template_name, "")
        if not template:
            return ""
        try:
            return template.format(**kwargs)
        except KeyError:
            return template


class AIWriter:
    """
    Multi-provider AI writer for blog content generation.

    Manages multiple AI provider configurations and provides a unified
    interface for generating, rewriting, and enhancing blog content.
    """

    def __init__(self, providers: list[AIProviderConfig] | None = None):
        self.providers: dict[str, AIProviderConfig] = {}
        self.templates = BlogPromptTemplates()
        self._active_provider: str | None = None

        if providers:
            for p in providers:
                self.add_provider(p)

    def add_provider(self, config: AIProviderConfig) -> None:
        """Register an AI provider."""
        self.providers[config.label] = config
        if self._active_provider is None and config.enabled:
            self._active_provider = config.label
        logger.info(f"Registered AI provider: {config.label} ({config.provider})")

    def set_active_provider(self, label: str) -> bool:
        """Set the active provider by label."""
        if label in self.providers:
            self._active_provider = label
            return True
        return False

    def get_active_provider(self) -> AIProviderConfig | None:
        """Get the currently active provider config."""
        if self._active_provider and self._active_provider in self.providers:
            return self.providers[self._active_provider]
        return None

    def list_providers(self) -> list[dict[str, Any]]:
        """List all configured providers with status."""
        result = []
        for label, cfg in self.providers.items():
            result.append({
                "label": label,
                "provider": cfg.provider.value,
                "model": cfg.model,
                "endpoint": cfg.endpoint,
                "enabled": cfg.enabled,
                "active": label == self._active_provider,
                "has_key": bool(cfg.api_key),
                "is_local": cfg.provider in (
                    AIProvider.OLLAMA, AIProvider.LM_STUDIO,
                    AIProvider.LLAMACPP, AIProvider.LOCALAI, AIProvider.JAN,
                ),
            })
        return result

    async def generate(
        self,
        prompt: str,
        provider_label: str | None = None,
        system_prompt: str = "You are a skilled blog writer. Write clear, engaging content.",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """
        Generate text using the specified or active AI provider.

        Args:
            prompt: The user prompt / content request
            provider_label: Specific provider to use (or active if None)
            system_prompt: System-level instructions
            temperature: Override provider default temperature
            max_tokens: Override provider default max_tokens

        Returns:
            AIResponse with generated content
        """
        label = provider_label or self._active_provider
        if not label or label not in self.providers:
            return AIResponse(
                content="",
                provider="none",
                model="",
                error="No AI provider configured. Add one in config/config.yaml under ai_providers.",
            )

        config = self.providers[label]
        if not config.enabled:
            return AIResponse(
                content="",
                provider=config.provider.value,
                model=config.model,
                error=f"Provider '{label}' is disabled.",
            )

        temp = temperature if temperature is not None else config.temperature
        tokens = max_tokens if max_tokens is not None else config.max_tokens

        # Route to the appropriate API style
        if config.provider == AIProvider.ANTHROPIC:
            return await self._call_anthropic(config, prompt, system_prompt, temp, tokens)
        elif config.provider == AIProvider.GOOGLE:
            return await self._call_google(config, prompt, system_prompt, temp, tokens)
        elif config.provider == AIProvider.OLLAMA:
            return await self._call_ollama(config, prompt, system_prompt, temp, tokens)
        else:
            # OpenAI-compatible (OpenAI, Mistral, Groq, LM Studio, llama.cpp, LocalAI, Jan, Custom)
            return await self._call_openai_compatible(config, prompt, system_prompt, temp, tokens)

    async def generate_blog(
        self,
        topic: str,
        context: str = "",
        provider_label: str | None = None,
    ) -> AIResponse:
        """Generate a full blog post from a topic."""
        prompt = self.templates.render("generate", topic=topic, context=context)
        return await self.generate(prompt, provider_label)

    async def rewrite_blog(
        self,
        content: str,
        provider_label: str | None = None,
    ) -> AIResponse:
        """Rewrite/improve existing blog content."""
        prompt = self.templates.render("rewrite", content=content)
        return await self.generate(prompt, provider_label)

    async def expand_blog(
        self,
        content: str,
        provider_label: str | None = None,
    ) -> AIResponse:
        """Expand short content into a fuller article."""
        prompt = self.templates.render("expand", content=content)
        return await self.generate(prompt, provider_label)

    async def generate_headlines(
        self,
        content: str,
        provider_label: str | None = None,
    ) -> AIResponse:
        """Generate headline suggestions for blog content."""
        prompt = self.templates.render("headline", content=content)
        return await self.generate(prompt, provider_label)

    async def generate_seo(
        self,
        content: str,
        provider_label: str | None = None,
    ) -> AIResponse:
        """Generate SEO metadata for a blog post."""
        prompt = self.templates.render("seo", content=content)
        return await self.generate(prompt, provider_label)

    async def generate_excerpt(
        self,
        content: str,
        provider_label: str | None = None,
    ) -> AIResponse:
        """Generate a short excerpt/summary for homepage display."""
        prompt = self.templates.render("summary", content=content)
        return await self.generate(prompt, provider_label)

    # ── Provider-specific API calls ──────────────────────────────────────────

    async def _call_openai_compatible(
        self,
        config: AIProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Call OpenAI-compatible API (OpenAI, Mistral, Groq, LM Studio, llama.cpp, etc.)."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(config.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)

            return AIResponse(
                content=content,
                provider=config.provider.value,
                model=config.model,
                tokens_used=tokens,
            )
        except httpx.HTTPStatusError as e:
            return AIResponse(
                content="",
                provider=config.provider.value,
                model=config.model,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            return AIResponse(
                content="",
                provider=config.provider.value,
                model=config.model,
                error=str(e),
            )

    async def _call_anthropic(
        self,
        config: AIProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Call Anthropic Messages API."""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": config.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(config.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            content = data["content"][0]["text"]
            tokens = data.get("usage", {})
            total = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)

            return AIResponse(
                content=content,
                provider="anthropic",
                model=config.model,
                tokens_used=total,
            )
        except httpx.HTTPStatusError as e:
            return AIResponse(
                content="",
                provider="anthropic",
                model=config.model,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            return AIResponse(
                content="",
                provider="anthropic",
                model=config.model,
                error=str(e),
            )

    async def _call_google(
        self,
        config: AIProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Call Google Gemini API."""
        endpoint = config.endpoint.format(model=config.model)
        url = f"{endpoint}?key={config.api_key}"

        payload = {
            "contents": [
                {"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]},
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            content = data["candidates"][0]["content"]["parts"][0]["text"]
            tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)

            return AIResponse(
                content=content,
                provider="google",
                model=config.model,
                tokens_used=tokens,
            )
        except httpx.HTTPStatusError as e:
            return AIResponse(
                content="",
                provider="google",
                model=config.model,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            return AIResponse(
                content="",
                provider="google",
                model=config.model,
                error=str(e),
            )

    async def _call_ollama(
        self,
        config: AIProviderConfig,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> AIResponse:
        """Call Ollama native API."""
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(config.endpoint, json=payload, headers={})
                resp.raise_for_status()
                data = resp.json()

            content = data.get("message", {}).get("content", "")
            tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

            return AIResponse(
                content=content,
                provider="ollama",
                model=config.model,
                tokens_used=tokens,
            )
        except httpx.ConnectError:
            return AIResponse(
                content="",
                provider="ollama",
                model=config.model,
                error=(
                    "Cannot connect to Ollama. Is it running?\n"
                    "Start with: ollama serve\n"
                    "Install: https://ollama.com/download"
                ),
            )
        except Exception as e:
            return AIResponse(
                content="",
                provider="ollama",
                model=config.model,
                error=str(e),
            )

    # ── Configuration loading ────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "AIWriter":
        """
        Create an AIWriter from a config dict (loaded from config.yaml).

        Expected format:
            ai_providers:
              - label: "my-ollama"
                provider: "ollama"
                model: "llama3.1"
                endpoint: "http://localhost:11434/api/chat"
              - label: "openai-main"
                provider: "openai"
                api_key: "sk-..."
                model: "gpt-4o"
        """
        providers_list = config.get("ai_providers", [])
        configs = []

        for p in providers_list:
            try:
                provider = AIProvider(p.get("provider", "custom"))
            except ValueError:
                provider = AIProvider.CUSTOM

            cfg = AIProviderConfig(
                provider=provider,
                api_key=p.get("api_key", ""),
                endpoint=p.get("endpoint", ""),
                model=p.get("model", ""),
                temperature=p.get("temperature", 0.7),
                max_tokens=p.get("max_tokens", 2000),
                enabled=p.get("enabled", True),
                label=p.get("label", provider.value),
            )
            configs.append(cfg)

        return cls(providers=configs)

    @staticmethod
    def get_local_ai_info() -> str:
        """Return formatted info about local AI options."""
        lines = [
            "**Local AI Options (Free, Private, No API Key)**",
            "",
        ]

        for key, info in LOCAL_AI_OPTIONS.items():
            lines.extend([
                f"**{info['name']}**",
                f"  {info['description']}",
                f"  Download: {info['url']}",
                f"  Install:  {info['install']}",
                f"  Models:   {', '.join(info['recommended_models'])}",
                "",
            ])

        lines.extend([
            "**Quick Start (Ollama - recommended):**",
            "  1. curl -fsSL https://ollama.com/install.sh | sh",
            "  2. ollama pull llama3.1",
            "  3. Add to config/config.yaml:",
            "     ai_providers:",
            "       - label: local",
            "         provider: ollama",
            "         model: llama3.1",
            "",
            "Then use: ai blog generate <topic>",
        ])

        return "\n".join(lines)

    @staticmethod
    def get_cloud_providers_info() -> str:
        """Return formatted info about cloud AI providers."""
        cloud = {
            "OpenAI": {
                "url": "https://platform.openai.com/api-keys",
                "models": "gpt-4o, gpt-4-turbo, gpt-3.5-turbo",
            },
            "Anthropic": {
                "url": "https://console.anthropic.com/settings/keys",
                "models": "claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5",
            },
            "Google Gemini": {
                "url": "https://aistudio.google.com/apikey",
                "models": "gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash",
            },
            "Mistral": {
                "url": "https://console.mistral.ai/api-keys",
                "models": "mistral-large-latest, mistral-medium, mistral-small",
            },
            "Groq": {
                "url": "https://console.groq.com/keys",
                "models": "llama-3.1-70b-versatile, mixtral-8x7b (fast!)",
            },
        }

        lines = ["**Cloud AI Providers (API Key Required)**", ""]
        for name, info in cloud.items():
            lines.extend([
                f"**{name}**",
                f"  Get API key: {info['url']}",
                f"  Models: {info['models']}",
                "",
            ])

        return "\n".join(lines)


def load_ai_writer_from_yaml(config: dict[str, Any]) -> AIWriter:
    """Convenience function to load AIWriter from full app config."""
    return AIWriter.from_config(config)
