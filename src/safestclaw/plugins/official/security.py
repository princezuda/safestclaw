"""
SafestClaw Security Plugin — deterministic security scanners, no AI required.

Wraps a curated set of well-known, locally-installed security tools so they
can be invoked through the SafestClaw chat interface or CLI like any other
action. Nothing here calls an LLM.

Supported scanners (each is optional; the plugin degrades gracefully when
the tool isn't on PATH):

  • bandit       — Python static analysis for common security issues
  • pip-audit    — CVEs in installed Python packages
  • safety       — alternative CVE scanner for Python packages
  • semgrep      — multi-language pattern-based static analysis
  • trivy        — filesystem / dependency / container vulnerability scan
  • detect-secrets — finds hard-coded secrets and credentials
  • gitleaks     — git history secret scanner

Chat commands:
  security tools                  — show which scanners are installed
  security scan [path]            — run every available scanner
  security bandit [path]          — Python static analysis
  security pip-audit              — CVEs in installed Python deps
  security safety                 — CVE scan via `safety`
  security semgrep [path]         — semgrep with `--config auto`
  security trivy [path]           — trivy filesystem scan
  security secrets [path]         — detect-secrets scan
  security gitleaks [path]        — gitleaks detect

Path arguments must live inside the configured allowlist (defaults to the
home directory). Each scanner is run via ``create_subprocess_exec`` so no
shell interpretation happens; output is bounded by ``max_output`` bytes.

Config in ~/.safestclaw/config.yaml:

    plugins:
      security:
        allowed_paths:
          - "~"
          - "/tmp"
        timeout: 120
        max_output: 20000
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import shutil
from pathlib import Path
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


# Static metadata for each scanner. Argv templates use ``{path}`` as the
# only substitution slot — never the unsplit raw command — so no shell
# interpretation can sneak in.
SCANNERS: dict[str, dict[str, Any]] = {
    "bandit": {
        "executable": "bandit",
        "argv": ["bandit", "-r", "-q", "{path}"],
        "needs_path": True,
        "install": "pip install bandit",
        "description": "Python static analysis for common security issues",
    },
    "pip-audit": {
        "executable": "pip-audit",
        "argv": ["pip-audit"],
        "needs_path": False,
        "install": "pip install pip-audit",
        "description": "Scan installed Python packages for known CVEs",
    },
    "safety": {
        "executable": "safety",
        "argv": ["safety", "check", "--full-report"],
        "needs_path": False,
        "install": "pip install safety",
        "description": "CVE scan for installed Python packages",
    },
    "semgrep": {
        "executable": "semgrep",
        "argv": ["semgrep", "--config", "auto", "--quiet", "{path}"],
        "needs_path": True,
        "install": "pip install semgrep",
        "description": "Multi-language pattern-based static analysis",
    },
    "trivy": {
        "executable": "trivy",
        "argv": ["trivy", "fs", "--quiet", "{path}"],
        "needs_path": True,
        "install": "https://aquasecurity.github.io/trivy/",
        "description": "Filesystem / dependency vulnerability scan",
    },
    "secrets": {
        "executable": "detect-secrets",
        "argv": ["detect-secrets", "scan", "{path}"],
        "needs_path": True,
        "install": "pip install detect-secrets",
        "description": "Find hard-coded secrets and credentials",
    },
    "gitleaks": {
        "executable": "gitleaks",
        "argv": ["gitleaks", "detect", "--no-banner", "--source", "{path}"],
        "needs_path": True,
        "install": "https://github.com/gitleaks/gitleaks#installing",
        "description": "Git history secret scanner",
    },
}


class SecurityPlugin(BasePlugin):
    """Wrap deterministic security scanners as a SafestClaw action."""

    info = PluginInfo(
        name="security",
        version="1.0.0",
        description="Run deterministic security scanners (bandit, pip-audit, "
                    "semgrep, trivy, detect-secrets, gitleaks) — no AI",
        author="SafestClaw",
        keywords=[
            "security", "scan", "audit", "vulnerability", "vulnerabilities",
            "cve", "secrets", "bandit", "semgrep", "trivy", "pip-audit",
            "gitleaks",
        ],
        patterns=[
            r"^security$",
            r"^security\s+(tools|scan|bandit|pip-audit|pip_audit|safety|"
            r"semgrep|trivy|secrets|gitleaks|help)\b.*",
            r"^scan\s+(?:for\s+)?(?:vulnerabilities|cves|secrets)\b.*",
        ],
        examples=[
            "security tools",
            "security scan",
            "security scan ~/projects/myapp",
            "security bandit ~/projects/myapp",
            "security pip-audit",
            "security semgrep ~/projects/myapp",
            "security trivy ~/projects/myapp",
            "security secrets ~/projects/myapp",
            "security gitleaks ~/projects/myapp",
        ],
    )

    def __init__(self) -> None:
        self._allowed_paths: list[Path] = []
        self._timeout: float = 120.0
        self._max_output: int = 20000
        self._default_target: Path = Path.cwd()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_load(self, engine: Any) -> None:
        cfg = (engine.config.get("plugins") or {}).get("security") or {}
        paths = cfg.get("allowed_paths") or ["~"]
        self._allowed_paths = [
            Path(p).expanduser().resolve() for p in paths
        ]
        try:
            self._timeout = float(cfg.get("timeout", 120))
        except (TypeError, ValueError):
            self._timeout = 120.0
        try:
            self._max_output = int(cfg.get("max_output", 20000))
        except (TypeError, ValueError):
            self._max_output = 20000

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    def _is_allowed_path(self, path: Path) -> bool:
        """Path must resolve inside one of the allowed roots."""
        try:
            resolved = path.expanduser().resolve()
        except (OSError, ValueError):
            return False
        for allowed in self._allowed_paths:
            try:
                if resolved == allowed or resolved.is_relative_to(allowed):
                    return True
            except (ValueError, AttributeError):
                continue
        return False

    def _resolve_target(self, raw: str) -> tuple[Path | None, str]:
        """
        Parse a path argument from raw user text. Returns ``(path, error)``;
        if ``path`` is None, ``error`` explains why.
        """
        text = (raw or "").strip()
        if not text:
            target = self._default_target
        else:
            # Take only the first whitespace-separated token so users can add
            # comments after the path without surprises.
            token = shlex.split(text)[0] if text else ""
            target = Path(token).expanduser()

        if not self._is_allowed_path(target):
            return None, (
                f"Access denied: {target} is outside the configured "
                "security.allowed_paths."
            )
        if not target.exists():
            return None, f"Path not found: {target}"
        return target, ""

    # ------------------------------------------------------------------
    # Subprocess
    # ------------------------------------------------------------------

    @staticmethod
    def _has_executable(name: str) -> bool:
        return shutil.which(name) is not None

    async def _run_scanner(
        self, scanner_key: str, path: Path | None
    ) -> str:
        """Invoke one scanner and return its formatted output."""
        spec = SCANNERS.get(scanner_key)
        if spec is None:
            return f"Unknown scanner: {scanner_key}"

        if not self._has_executable(spec["executable"]):
            return (
                f"`{spec['executable']}` is not installed.\n"
                f"Install with: {spec['install']}"
            )

        argv = []
        for arg in spec["argv"]:
            if arg == "{path}":
                if path is None:
                    return f"Scanner `{scanner_key}` needs a path argument."
                argv.append(str(path))
            else:
                argv.append(arg)

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return (
                f"`{spec['executable']}` disappeared between the check and "
                "the run. Install with: " + spec["install"]
            )
        except Exception as e:
            return f"Failed to launch `{spec['executable']}`: {e}"

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except TimeoutError:
            process.kill()
            return f"`{spec['executable']}` timed out after {self._timeout:.0f}s"

        return self._format_output(scanner_key, process.returncode, stdout, stderr)

    def _format_output(
        self,
        scanner_key: str,
        returncode: int | None,
        stdout: bytes,
        stderr: bytes,
    ) -> str:
        out = stdout.decode("utf-8", errors="replace") if stdout else ""
        err = stderr.decode("utf-8", errors="replace") if stderr else ""

        if len(out) > self._max_output:
            out = out[: self._max_output] + "\n... (truncated)"
        if len(err) > self._max_output:
            err = err[: self._max_output] + "\n... (truncated)"

        # Many scanners exit non-zero specifically when findings exist —
        # that's a successful scan that found something, not an error.
        finding = returncode not in (0, None)
        header_emoji = "🔎" if finding else "✅"
        header = f"{header_emoji} {scanner_key} (exit {returncode})"

        body_parts: list[str] = []
        if out.strip():
            body_parts.append(out.rstrip())
        if err.strip():
            body_parts.append(f"[stderr]\n{err.rstrip()}")
        if not body_parts:
            body_parts.append("(no output)")

        return f"{header}\n" + "\n\n".join(body_parts)

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    def _list_tools(self) -> str:
        lines = ["**Security scanners**", ""]
        for key, spec in SCANNERS.items():
            installed = "✅" if self._has_executable(spec["executable"]) else "⬜"
            lines.append(
                f"{installed} **{key}** ({spec['executable']}) — "
                f"{spec['description']}"
            )
            if installed == "⬜":
                lines.append(f"      install: {spec['install']}")
        lines.append("")
        lines.append(f"Allowed paths: {[str(p) for p in self._allowed_paths]}")
        return "\n".join(lines)

    @staticmethod
    def _help() -> str:
        return (
            "**Security plugin** — deterministic scanners, no AI.\n\n"
            "  security tools                — list installed scanners\n"
            "  security scan [path]          — run every available scanner\n"
            "  security bandit [path]        — Python static analysis\n"
            "  security pip-audit            — CVE scan for installed Python deps\n"
            "  security safety               — alternative CVE scan\n"
            "  security semgrep [path]       — multi-language SAST\n"
            "  security trivy [path]         — filesystem vulnerability scan\n"
            "  security secrets [path]       — detect-secrets\n"
            "  security gitleaks [path]      — gitleaks secret scan\n\n"
            "Paths must be inside plugins.security.allowed_paths."
        )

    async def _scan_all(self, raw_args: str) -> str:
        path, err = self._resolve_target(raw_args)
        if err:
            return err

        results: list[str] = []
        ran = 0
        for key, spec in SCANNERS.items():
            if not self._has_executable(spec["executable"]):
                continue
            ran += 1
            target = path if spec["needs_path"] else None
            results.append(await self._run_scanner(key, target))

        if not ran:
            return (
                "No security scanners are installed.\n\n"
                + self._list_tools()
            )

        header = f"Ran {ran} scanner(s) on `{path}`\n"
        return header + "\n\n---\n\n".join(results)

    # ------------------------------------------------------------------
    # BasePlugin
    # ------------------------------------------------------------------

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        raw = (params.get("raw_input") or "").strip()
        lower = raw.lower()

        # Normalise the leading "security " or "scan " prefix
        for prefix in ("security ", "scan "):
            if lower.startswith(prefix):
                raw = raw[len(prefix):].strip()
                lower = raw.lower()
                break
        else:
            if lower in ("security", "scan"):
                raw = ""
                lower = ""

        if not raw or lower == "help":
            return self._help()
        if lower == "tools":
            return self._list_tools()
        if lower == "scan" or lower.startswith("scan "):
            rest = raw[4:].strip() if lower.startswith("scan ") else ""
            return await self._scan_all(rest)

        # Per-scanner subcommands
        first, _, rest = raw.partition(" ")
        first_norm = first.lower().replace("_", "-")
        if first_norm == "pip-audit":
            scanner_key = "pip-audit"
        elif first_norm in SCANNERS:
            scanner_key = first_norm
        else:
            return self._help()

        spec = SCANNERS[scanner_key]
        if spec["needs_path"]:
            path, err = self._resolve_target(rest)
            if err:
                return err
            return await self._run_scanner(scanner_key, path)

        return await self._run_scanner(scanner_key, None)
