"""
SafeClaw - A privacy-first personal automation assistant.

No GenAI required for core features. Optional AI for blogging, research, coding.
100% self-hosted. Your data stays yours.

100-Star Features:
- Real research: arXiv, Semantic Scholar, Wolfram Alpha (no API key needed)
- Simple AI setup: enter your key or auto-install Ollama
- Auto-learning: word-to-number, typo correction, learns from mistakes

100-Star Features:
- Fuzzy learning: deterministic writing style profiling
- Per-task LLM routing (blog/research/coding each get their own provider)
- Cron-based auto-blogging (no LLM needed)
- Two-phase research (non-LLM discovery + optional LLM deep analysis)
- Code tools (non-LLM templates/search/stats + optional LLM generation)
- Non-deterministic system prompts (context-aware, learned from user)
"""

__version__ = "0.3.2"
__author__ = "SafeClaw Contributors"

from safeclaw.core.engine import SafeClaw
from safeclaw.core.memory import Memory
from safeclaw.core.parser import CommandParser

__all__ = ["SafeClaw", "CommandParser", "Memory", "__version__"]
