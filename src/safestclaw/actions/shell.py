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

    # Default allowlist of safe executables.
    #
    # NOTE: interpreters and command-runners (sh, bash, python, node, npm,
    # env, xargs, ...) are deliberately NOT here. Allowing any of them lets a
    # caller run *arbitrary* programs and completely defeats the allowlist
    # (e.g. `env id`, `python3 -c "import os; os.system(...)"`). They are
    # additionally hard-blocked via NEVER_ALLOW below.
    DEFAULT_ALLOWED = {
        "ls", "pwd", "whoami", "date", "cal", "uptime",
        "df", "du", "free", "ps",
        "cat", "head", "tail", "wc", "sort", "uniq",
        "grep", "find", "file", "stat",
        "echo", "printf",
        "git",
        "uname", "hostname", "id", "printenv",
        "which", "type", "whereis",
        "basename", "dirname", "realpath",
        "diff", "md5sum", "sha256sum",
        "ping", "dig", "nslookup", "host", "curl", "wget",
        "tar", "gzip", "gunzip", "zip", "unzip",
        "cp", "mv", "mkdir", "touch", "ln",
    }

    # Interpreters, shells and command-runners that can spawn arbitrary other
    # programs. These are rejected in sandboxed mode *even if* an operator's
    # custom allowlist names one by mistake — allowing any of them turns the
    # allowlist into a no-op.
    NEVER_ALLOW = {
        # POSIX / alternative shells
        "sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish", "ash",
        # scripting language interpreters
        "python", "python2", "python3", "pypy", "perl", "ruby", "node",
        "nodejs", "npm", "npx", "yarn", "pnpm", "deno", "bun",
        "php", "lua", "luajit", "tclsh", "rscript",
        "awk", "gawk", "mawk", "nawk",
        # generic command runners / wrappers
        "env", "xargs", "nice", "nohup", "setsid", "stdbuf", "chrt",
        "timeout", "watch", "parallel", "flock", "time",
        # build tools that execute arbitrary recipes
        "make", "cmake", "ninja",
        # privilege escalation / remote exec
        "sudo", "su", "doas", "pkexec", "chroot", "systemd-run", "runuser",
        "ssh", "scp", "sftp", "telnet", "nc", "ncat", "netcat", "socat",
        # editors / pagers / multiplexers that shell out
        "vi", "vim", "nvim", "emacs", "nano", "ed", "ex",
        "man", "less", "more", "most", "pager",
        "screen", "tmux", "byobu",
        # debuggers / tracers
        "gdb", "lldb", "strace", "ltrace",
        # job schedulers
        "crontab", "at", "batch",
        # interactive monitors that need a tty anyway
        "top", "htop",
    }

    # For multi-purpose tools that ARE on the allowlist, block the specific
    # flags / subcommands that let them execute other programs or read local
    # files. Keys are bare executable names; values are option tokens.
    DANGEROUS_ARGS = {
        "find": (
            "-exec", "-execdir", "-ok", "-okdir",
            "-fprint", "-fprintf", "-fls", "-delete",
        ),
        # NB: deliberately not blocking -p/--paginate: in a non-tty subprocess
        # the pager can't spawn an interactive shell, and `git log -p` is a
        # common benign use. The real escape is `-c core.pager=...`, covered
        # by -c below.
        "git": (
            "-c", "--config-env",
            "--exec-path", "--upload-pack", "--receive-pack",
            "help", "instaweb", "daemon",
        ),
        "tar": (
            "--to-command", "--checkpoint-action",
            "--use-compress-program", "-I", "--rsh-command", "--rmt-command",
        ),
        "curl": ("-K", "--config"),
        "wget": ("--use-askpass",),
    }

    def __init__(
        self,
        enabled: bool = True,
        sandboxed: bool = True,
        timeout: float = 30.0,
        max_output: int = 10000,
        allowed_commands: list[str] | None = None,
        working_directory: str | None = None,
        enforce_never_allow: bool = True,
    ):
        self.enabled = enabled
        self.sandboxed = sandboxed
        self.timeout = timeout
        self.max_output = max_output
        self.working_directory = working_directory
        # When True (default), the NEVER_ALLOW hard blocklist of interpreters
        # and command-runners is enforced in sandboxed mode even if they
        # appear in a custom allowlist. Operators who deliberately need an
        # interpreter (e.g. python) can set this False and take ownership of
        # that risk via their own allowed_commands.
        self.enforce_never_allow = enforce_never_allow
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

        if self.sandboxed:
            # Hard block interpreters / command-runners, regardless of the
            # configured allowlist, since they defeat it entirely. Operators
            # can opt out via enforce_never_allow=False.
            if self.enforce_never_allow and executable.lower() in self.NEVER_ALLOW:
                return (
                    False,
                    f"Command not allowed (interpreter/command-runner): "
                    f"{executable}",
                    [],
                )

            if executable not in self.allowed_commands:
                return False, f"Command not allowed: {executable}", []

            # Even allowlisted multi-tools must not use their exec/escape
            # flags (e.g. `find -exec`, `git -c core.pager=...`).
            ok, reason = self._check_dangerous_args(executable, args)
            if not ok:
                return False, reason, []

        return True, "", args

    def _check_dangerous_args(
        self, executable: str, args: list[str]
    ) -> tuple[bool, str]:
        """
        Reject argument patterns that let an allowlisted tool execute other
        programs, read local files, or reach internal network resources.

        Returns:
            Tuple of (is_ok, reason)
        """
        rest = args[1:]

        dangerous = self.DANGEROUS_ARGS.get(executable)
        if dangerous:
            for token in rest:
                for bad in dangerous:
                    if token == bad or token.startswith(bad + "="):
                        return (
                            False,
                            f"Disallowed option for {executable}: {token}",
                        )

        # Network fetch tools: only http/https URLs. Blocks file://,
        # gopher://, dict://, scp:// and similar SSRF/local-file schemes.
        if executable in {"curl", "wget"}:
            for token in rest:
                if "://" not in token:
                    continue
                scheme = token.split("://", 1)[0].lower()
                # Handle forms like --url=http://... by taking the part
                # after the last '=' (the actual scheme).
                if "=" in scheme:
                    scheme = scheme.rsplit("=", 1)[1]
                # Strip any leading short-flag noise (e.g. "-Ohttp" is not a
                # real scheme; real schemes are alphanumeric+.+-).
                if scheme and scheme not in ("http", "https"):
                    return (
                        False,
                        f"Only http/https URLs allowed for {executable}: "
                        f"{token}",
                    )

        return True, ""

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
