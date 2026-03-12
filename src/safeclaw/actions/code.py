"""
SafeClaw Coding Action - Code generation and assistance.

Non-LLM features (always available, $0):
- Code search across local files (grep/find)
- File reading and display with syntax info
- Code statistics (line count, language detection)
- Diff generation between files
- Template/boilerplate generation for common patterns
- Regex testing and explanation

LLM features (optional, per-task routing):
- Code generation from description
- Code explanation
- Bug finding / review
- Refactoring suggestions
- Documentation generation

Uses the coding-specific LLM provider when configured.
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from safeclaw.actions.base import BaseAction

if TYPE_CHECKING:
    from safeclaw.core.engine import SafeClaw

logger = logging.getLogger(__name__)

# Language detection by file extension
LANGUAGE_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".rs": "rust", ".go": "go",
    ".java": "java", ".kt": "kotlin", ".swift": "swift",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".cs": "csharp",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".sql": "sql", ".sh": "bash", ".bash": "bash",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json",
    ".toml": "toml", ".xml": "xml", ".md": "markdown",
    ".r": "r", ".R": "r", ".lua": "lua", ".zig": "zig",
    ".ex": "elixir", ".exs": "elixir", ".erl": "erlang",
    ".hs": "haskell", ".ml": "ocaml", ".clj": "clojure",
    ".dart": "dart", ".scala": "scala", ".v": "v",
    ".nim": "nim", ".jl": "julia",
}

# Common boilerplate templates (non-LLM)
TEMPLATES = {
    "python-script": '''#!/usr/bin/env python3
"""
{description}
"""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    # TODO: Implement main logic
    logger.info("Starting...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
    "python-class": '''"""
{description}
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class {name}:
    """{description}"""

    # TODO: Add fields

    def __post_init__(self):
        """Validate after initialization."""
        pass

    def __repr__(self) -> str:
        return f"{{self.__class__.__name__}}()"
''',
    "python-test": '''"""
Tests for {name}.
"""

import pytest


class Test{name}:
    """Test suite for {name}."""

    def test_basic(self):
        """Test basic functionality."""
        # TODO: Implement test
        assert True

    def test_edge_cases(self):
        """Test edge cases."""
        # TODO: Implement test
        pass

    @pytest.fixture
    def sample_data(self):
        """Provide sample test data."""
        return {{}}
''',
    "fastapi-endpoint": '''"""
{description}
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/{name}", tags=["{name}"])


class {name}Request(BaseModel):
    """Request model."""
    pass  # TODO: Add fields


class {name}Response(BaseModel):
    """Response model."""
    success: bool = True
    message: str = ""


@router.get("/")
async def list_{name}s():
    """List all {name}s."""
    return []


@router.post("/", response_model={name}Response)
async def create_{name}(request: {name}Request):
    """Create a new {name}."""
    return {name}Response(message="Created")


@router.get("/{{item_id}}")
async def get_{name}(item_id: int):
    """Get a specific {name}."""
    raise HTTPException(status_code=404, detail="Not found")
''',
    "html-page": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{description}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: system-ui, sans-serif; line-height: 1.6; padding: 2rem; }}
        h1 {{ margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <h1>{description}</h1>
    <!-- TODO: Add content -->
</body>
</html>
''',
    "dockerfile": '''FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
    "github-action": '''name: {description}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest
''',
}


class CodeAction(BaseAction):
    """
    Code generation and assistance.

    Non-LLM (always available):
        code template <type>       - Generate boilerplate
        code templates             - List available templates
        code stats <path>          - Code statistics
        code search <pattern>      - Search code files
        code read <file>           - Read and display file
        code diff <file1> <file2>  - Compare two files
        code regex <pattern>       - Test regex pattern
        code help                  - Show commands

    LLM (optional):
        code generate <desc>       - Generate code from description
        code explain <file>        - Explain code
        code review <file>         - Review code for issues
        code refactor <file>       - Suggest refactoring
        code document <file>       - Generate documentation
    """

    name = "code"
    description = "Code generation and assistance"

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafeClaw",
    ) -> str:
        """Execute coding action."""
        raw = params.get("raw_input", "").strip()
        lower = raw.lower()

        # Parse subcommand
        if "code help" in lower or lower in ("code", "coding"):
            return self._help()

        if "code template" in lower and "code templates" not in lower:
            return self._generate_template(raw)

        if "code templates" in lower:
            return self._list_templates()

        if "code stats" in lower:
            path = self._extract_path(raw, "stats")
            return self._code_stats(path)

        if "code search" in lower:
            pattern = raw.split("search", 1)[-1].strip()
            path = "."
            if " in " in pattern:
                pattern, path = pattern.rsplit(" in ", 1)
            return self._code_search(pattern.strip(), path.strip())

        if "code read" in lower:
            path = self._extract_path(raw, "read")
            return self._read_file(path)

        if "code diff" in lower:
            return self._diff_files(raw)

        if "code regex" in lower:
            pattern = raw.split("regex", 1)[-1].strip()
            return self._regex_helper(pattern)

        # LLM-powered commands
        if "code generate" in lower:
            desc = raw.split("generate", 1)[-1].strip()
            return await self._llm_generate(desc, user_id, engine)

        if "code explain" in lower:
            path = self._extract_path(raw, "explain")
            return await self._llm_explain(path, user_id, engine)

        if "code review" in lower:
            path = self._extract_path(raw, "review")
            return await self._llm_review(path, user_id, engine)

        if "code refactor" in lower:
            path = self._extract_path(raw, "refactor")
            return await self._llm_refactor(path, user_id, engine)

        if "code document" in lower or "code doc" in lower:
            path = self._extract_path(raw, "doc")
            return await self._llm_document(path, user_id, engine)

        return self._help()

    # ── Non-LLM Features ─────────────────────────────────────────────────────

    def _generate_template(self, raw: str) -> str:
        """Generate a boilerplate template (no LLM)."""
        # Parse: code template <type> [name] [description]
        parts = raw.split("template", 1)[-1].strip().split(None, 2)
        if not parts:
            return self._list_templates()

        template_type = parts[0].lower()
        name = parts[1] if len(parts) > 1 else "MyComponent"
        description = parts[2] if len(parts) > 2 else "TODO: Add description"

        template = TEMPLATES.get(template_type)
        if not template:
            # Try partial match
            matches = [k for k in TEMPLATES if template_type in k]
            if matches:
                template = TEMPLATES[matches[0]]
                template_type = matches[0]
            else:
                return (
                    f"Unknown template: {template_type}\n\n"
                    f"Available: {', '.join(TEMPLATES.keys())}"
                )

        try:
            code = template.format(
                name=name,
                description=description,
            )
        except KeyError:
            code = template

        return f"**Template: {template_type}**\n\n```\n{code}\n```"

    def _list_templates(self) -> str:
        """List available code templates."""
        lines = ["**Available Code Templates**", ""]
        for name in sorted(TEMPLATES.keys()):
            lines.append(f"  - `code template {name}` — {name.replace('-', ' ').title()}")
        lines.extend([
            "",
            "Usage: `code template <type> [Name] [description]`",
            "Example: `code template python-class UserAuth Authentication handler`",
        ])
        return "\n".join(lines)

    def _code_stats(self, path_str: str) -> str:
        """Get code statistics for a file or directory (no LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"Path not found: {path}"

        if path.is_file():
            return self._file_stats(path)

        # Directory stats
        stats: dict[str, dict[str, int]] = {}
        total_files = 0
        total_lines = 0

        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix in LANGUAGE_MAP:
                # Skip common non-source directories
                parts = file_path.parts
                if any(d in parts for d in ["node_modules", ".git", "__pycache__", "venv", ".venv"]):
                    continue

                lang = LANGUAGE_MAP[file_path.suffix]
                try:
                    lines = len(file_path.read_text(errors="ignore").splitlines())
                except Exception:
                    continue

                if lang not in stats:
                    stats[lang] = {"files": 0, "lines": 0}
                stats[lang]["files"] += 1
                stats[lang]["lines"] += lines
                total_files += 1
                total_lines += lines

        if not stats:
            return f"No recognized source files in {path}"

        lines_output = [f"**Code Statistics: {path}**", ""]
        sorted_langs = sorted(stats.items(), key=lambda x: x[1]["lines"], reverse=True)
        for lang, data in sorted_langs:
            pct = (data["lines"] / total_lines * 100) if total_lines else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines_output.append(
                f"  {lang:12s} {bar} {data['lines']:>6,} lines ({data['files']} files) {pct:.0f}%"
            )
        lines_output.extend([
            "",
            f"  Total: {total_files:,} files, {total_lines:,} lines",
        ])
        return "\n".join(lines_output)

    def _file_stats(self, path: Path) -> str:
        """Stats for a single file."""
        try:
            content = path.read_text(errors="ignore")
        except Exception as e:
            return f"Cannot read {path}: {e}"

        lines = content.splitlines()
        lang = LANGUAGE_MAP.get(path.suffix, "unknown")
        blank = sum(1 for line in lines if not line.strip())
        comment = sum(1 for line in lines if line.strip().startswith(("#", "//", "/*", "*", "--")))

        return (
            f"**{path.name}** ({lang})\n"
            f"  Lines: {len(lines):,} (code: {len(lines)-blank-comment:,}, "
            f"blank: {blank}, comment: {comment})\n"
            f"  Size: {path.stat().st_size:,} bytes"
        )

    def _code_search(self, pattern: str, path_str: str) -> str:
        """Search for pattern in code files (no LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"Path not found: {path}"

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex: {e}"

        matches = []
        search_path = path if path.is_dir() else path.parent

        for file_path in search_path.rglob("*"):
            if not file_path.is_file() or file_path.suffix not in LANGUAGE_MAP:
                continue
            parts = file_path.parts
            if any(d in parts for d in ["node_modules", ".git", "__pycache__", "venv"]):
                continue

            try:
                content = file_path.read_text(errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        matches.append((file_path, i, line.strip()))
                        if len(matches) >= 50:
                            break
            except Exception:
                continue

            if len(matches) >= 50:
                break

        if not matches:
            return f"No matches for '{pattern}' in {path}"

        lines = [f"**Search: '{pattern}'** ({len(matches)} matches)", ""]
        for fp, ln, text in matches[:30]:
            lines.append(f"  {fp}:{ln}: {text[:100]}")

        if len(matches) > 30:
            lines.append(f"\n  ... and {len(matches) - 30} more")

        return "\n".join(lines)

    def _read_file(self, path_str: str) -> str:
        """Read and display a file (no LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"File not found: {path}"
        if not path.is_file():
            return f"Not a file: {path}"

        try:
            content = path.read_text(errors="ignore")
        except Exception as e:
            return f"Cannot read {path}: {e}"

        lang = LANGUAGE_MAP.get(path.suffix, "")
        lines = content.splitlines()

        if len(lines) > 100:
            preview = "\n".join(lines[:100])
            return (
                f"**{path.name}** ({lang}, {len(lines)} lines)\n\n"
                f"```{lang}\n{preview}\n```\n\n"
                f"... truncated ({len(lines) - 100} more lines)"
            )

        return f"**{path.name}** ({lang})\n\n```{lang}\n{content}\n```"

    def _diff_files(self, raw: str) -> str:
        """Compare two files (no LLM)."""
        import difflib

        parts = raw.split("diff", 1)[-1].strip().split()
        if len(parts) < 2:
            return "Usage: code diff <file1> <file2>"

        path1 = Path(parts[0]).expanduser()
        path2 = Path(parts[1]).expanduser()

        if not path1.exists():
            return f"File not found: {path1}"
        if not path2.exists():
            return f"File not found: {path2}"

        try:
            lines1 = path1.read_text(errors="ignore").splitlines(keepends=True)
            lines2 = path2.read_text(errors="ignore").splitlines(keepends=True)
        except Exception as e:
            return f"Cannot read files: {e}"

        diff = difflib.unified_diff(
            lines1, lines2,
            fromfile=str(path1),
            tofile=str(path2),
        )
        diff_text = "".join(diff)

        if not diff_text:
            return "Files are identical."

        return f"**Diff: {path1.name} vs {path2.name}**\n\n```diff\n{diff_text[:3000]}\n```"

    def _regex_helper(self, pattern_str: str) -> str:
        """Test and explain a regex pattern (no LLM)."""
        # Split pattern and test string if provided
        parts = pattern_str.split(" test ", 1)
        pattern = parts[0].strip().strip("\"'")
        test_string = parts[1].strip().strip("\"'") if len(parts) > 1 else ""

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex: {e}"

        lines = [f"**Regex: `{pattern}`**", ""]

        # Basic explanation
        explanations = {
            r"\d": "digit (0-9)",
            r"\w": "word character (a-z, A-Z, 0-9, _)",
            r"\s": "whitespace",
            r".": "any character",
            r"*": "zero or more",
            r"+": "one or more",
            r"?": "zero or one",
            r"^": "start of string",
            r"$": "end of string",
            r"\b": "word boundary",
        }

        for token, desc in explanations.items():
            if token in pattern:
                lines.append(f"  `{token}` — {desc}")

        groups = regex.groups
        if groups:
            lines.append(f"\n  Capture groups: {groups}")

        if test_string:
            match = regex.search(test_string)
            lines.append(f"\nTest: `{test_string}`")
            if match:
                lines.append(f"  Match: `{match.group()}`")
                if match.groups():
                    for i, g in enumerate(match.groups(), 1):
                        lines.append(f"  Group {i}: `{g}`")
            else:
                lines.append("  No match.")

        return "\n".join(lines)

    # ── LLM-Powered Features ─────────────────────────────────────────────────

    async def _get_ai_writer(self, engine: "SafeClaw"):
        """Get AI writer with coding-specific provider."""
        from safeclaw.core.ai_writer import AIWriter

        task_providers = engine.config.get("task_providers", {})
        coding_provider = task_providers.get("coding")

        ai_writer = AIWriter.from_config(engine.config)
        return ai_writer, coding_provider

    async def _llm_generate(self, description: str, user_id: str, engine: "SafeClaw") -> str:
        """Generate code from description (LLM)."""
        ai_writer, coding_provider = await self._get_ai_writer(engine)
        if not ai_writer.providers:
            return (
                "No LLM configured for code generation.\n\n"
                "Non-LLM alternatives:\n"
                "  `code template <type>` — Generate boilerplate\n"
                "  `code templates` — List available templates\n\n"
                "To enable LLM code generation, add a provider in config.yaml:\n"
                "  task_providers:\n"
                '    coding: "my-ollama"'
            )

        from safeclaw.core.prompt_builder import PromptBuilder

        prompt_builder = PromptBuilder()
        system_prompt = prompt_builder.build(task="coding")

        response = await ai_writer.generate(
            prompt=f"Generate code for: {description}",
            provider_label=coding_provider,
            system_prompt=system_prompt,
        )

        if response.error:
            return f"Code generation failed: {response.error}"

        return (
            f"**Generated Code** *(via {response.provider}/{response.model})*\n\n"
            f"{response.content}"
        )

    async def _llm_explain(self, path_str: str, user_id: str, engine: "SafeClaw") -> str:
        """Explain code in a file (LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"File not found: {path}"

        content = path.read_text(errors="ignore")
        if len(content) > 5000:
            content = content[:5000] + "\n... (truncated)"

        ai_writer, coding_provider = await self._get_ai_writer(engine)
        if not ai_writer.providers:
            return f"No LLM configured. File is {LANGUAGE_MAP.get(path.suffix, 'unknown')}, {len(content.splitlines())} lines."

        response = await ai_writer.generate(
            prompt=f"Explain this code clearly and concisely:\n\n```\n{content}\n```",
            provider_label=coding_provider,
            system_prompt="You are an expert programmer. Explain code clearly.",
        )

        if response.error:
            return f"Explanation failed: {response.error}"

        return f"**Code Explanation: {path.name}**\n\n{response.content}"

    async def _llm_review(self, path_str: str, user_id: str, engine: "SafeClaw") -> str:
        """Review code for issues (LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"File not found: {path}"

        content = path.read_text(errors="ignore")
        ai_writer, coding_provider = await self._get_ai_writer(engine)
        if not ai_writer.providers:
            # Basic non-LLM review: just stats
            return self._file_stats(path)

        response = await ai_writer.generate(
            prompt=(
                f"Review this code for bugs, security issues, and improvements:\n\n"
                f"```\n{content[:5000]}\n```"
            ),
            provider_label=coding_provider,
            system_prompt="You are a senior code reviewer. Find bugs and suggest improvements concisely.",
        )

        if response.error:
            return f"Review failed: {response.error}"

        return f"**Code Review: {path.name}**\n\n{response.content}"

    async def _llm_refactor(self, path_str: str, user_id: str, engine: "SafeClaw") -> str:
        """Suggest refactoring (LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"File not found: {path}"

        content = path.read_text(errors="ignore")
        ai_writer, coding_provider = await self._get_ai_writer(engine)
        if not ai_writer.providers:
            return "No LLM configured for refactoring suggestions."

        response = await ai_writer.generate(
            prompt=(
                f"Suggest refactoring improvements for this code. "
                f"Show the refactored version:\n\n```\n{content[:5000]}\n```"
            ),
            provider_label=coding_provider,
            system_prompt="You are a senior programmer. Suggest clean, maintainable refactoring.",
        )

        if response.error:
            return f"Refactoring failed: {response.error}"

        return f"**Refactoring Suggestions: {path.name}**\n\n{response.content}"

    async def _llm_document(self, path_str: str, user_id: str, engine: "SafeClaw") -> str:
        """Generate documentation (LLM)."""
        path = Path(path_str).expanduser()
        if not path.exists():
            return f"File not found: {path}"

        content = path.read_text(errors="ignore")
        ai_writer, coding_provider = await self._get_ai_writer(engine)
        if not ai_writer.providers:
            return "No LLM configured for documentation generation."

        response = await ai_writer.generate(
            prompt=(
                f"Generate documentation for this code. Include:\n"
                f"- Module/class overview\n"
                f"- Function/method docstrings\n"
                f"- Usage examples\n\n"
                f"```\n{content[:5000]}\n```"
            ),
            provider_label=coding_provider,
            system_prompt="You are a technical writer. Write clear, useful documentation.",
        )

        if response.error:
            return f"Documentation generation failed: {response.error}"

        return f"**Documentation: {path.name}**\n\n{response.content}"

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _extract_path(self, raw: str, keyword: str) -> str:
        """Extract file path from raw input."""
        after = raw.split(keyword, 1)[-1].strip()
        # Take the first path-like token
        tokens = after.split()
        return tokens[0] if tokens else "."

    def _help(self) -> str:
        """Return coding help text."""
        return (
            "**Coding Commands**\n\n"
            "Non-LLM (always free):\n"
            "  `code template <type>`      — Generate boilerplate code\n"
            "  `code templates`            — List available templates\n"
            "  `code stats <path>`         — Code statistics (lines, languages)\n"
            "  `code search <pattern>`     — Search code files with regex\n"
            "  `code read <file>`          — Display file with syntax info\n"
            "  `code diff <f1> <f2>`       — Compare two files\n"
            "  `code regex <pattern>`      — Test and explain regex\n\n"
            "LLM-Powered (optional, uses coding provider):\n"
            "  `code generate <desc>`      — Generate code from description\n"
            "  `code explain <file>`       — Explain what code does\n"
            "  `code review <file>`        — Find bugs and issues\n"
            "  `code refactor <file>`      — Suggest improvements\n"
            "  `code document <file>`      — Generate documentation\n\n"
            "Configure a coding-specific LLM in config.yaml:\n"
            "  task_providers:\n"
            '    coding: "my-ollama"  # or any configured provider'
        )
