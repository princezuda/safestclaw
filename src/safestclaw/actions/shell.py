"""Shell command execution action."""

import asyncio
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class ShellAction(BaseAction):
    """
    Execute shell commands with sandboxing.

    Security features:
    - Command allowlist (only permitted executables can run)
    - Timeout enforcement
    - Output limiting
    - Working directory restriction
    - Uses create_subprocess_exec (no shell interpretation)
    """

    name = "shell"
    description = "Execute shell commands"

    # Default allowlist of safe executables
    DEFAULT_ALLOWED = {
        "ls", "pwd", "whoami", "date", "cal", "uptime",
        "df", "du", "free", "top", "ps",
        "cat", "head", "tail", "less", "wc", "sort", "uniq",
        "grep", "find", "file", "stat",
        "echo", "printf",
        "git", "python3", "python", "node", "npm",
        "uname", "hostname", "id", "env", "printenv",
        "which", "type", "whereis",
        "basename", "dirname", "realpath",
        "diff", "md5sum", "sha256sum",
        "ping", "dig", "nslookup", "host", "curl", "wget",
        "tar", "gzip", "gunzip", "zip", "unzip",
        "cp", "mv", "mkdir", "touch", "ln",
    }

    def __init__(
        self,
        enabled: bool = True,
        sandboxed: bool = True,
        timeout: float = 30.0,
        max_output: int = 10000,
        allowed_commands: list[str] | None = None,
        working_directory: str | None = None,
    ):
        self.enabled = enabled
        self.sandboxed = sandboxed
        self.timeout = timeout
        self.max_output = max_output
        self.working_directory = working_directory
        if allowed_commands is not None:
            self.allowed_commands = set(allowed_commands)
        else:
            self.allowed_commands = self.DEFAULT_ALLOWED.copy()

    def _validate_command(self, command: str) -> tuple[bool, str, list[str]]:
        """
        Validate and parse a command string.

        Returns:
            Tuple of (is_valid, reason, parsed_args)
        """
        if not command or not command.strip():
            return False, "Empty command", []

        try:
            args = shlex.split(command)
        except ValueError as e:
            return False, f"Invalid command syntax: {e}", []

        if not args:
            return False, "Empty command after parsing", []

        executable = Path(args[0]).name  # Strip path to get bare command name

        if self.sandboxed and executable not in self.allowed_commands:
            return False, f"Command not allowed: {executable}", []

        return True, "", args

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute shell command."""
        if not self.enabled:
            return "Shell commands are disabled"

        command = params.get("command", "")
        if not command:
            return "No command specified"

        # Validate and parse
        is_valid, reason, args = self._validate_command(command)
        if not is_valid:
            return f"Command blocked: {reason}"

        try:
            # Use create_subprocess_exec to avoid shell interpretation.
            # This prevents shell metacharacter injection (pipes, redirects,
            # command substitution, variable expansion, etc.)
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except TimeoutError:
                process.kill()
                return f"Command timed out after {self.timeout}s"

            # Format output
            output_parts = []

            if stdout:
                stdout_text = stdout.decode("utf-8", errors="replace")
                if len(stdout_text) > self.max_output:
                    stdout_text = stdout_text[:self.max_output] + "\n... (truncated)"
                output_parts.append(stdout_text)

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if len(stderr_text) > self.max_output:
                    stderr_text = stderr_text[:self.max_output] + "\n... (truncated)"
                output_parts.append(f"[stderr]\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"\n[exit code: {process.returncode}]")

            return "\n".join(output_parts) if output_parts else "(no output)"

        except Exception as e:
            return f"Error executing command: {e}"
