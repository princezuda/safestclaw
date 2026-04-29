"""Tests for security-critical components.

These tests import modules directly to avoid triggering the full
safestclaw import chain which requires all dependencies.
"""

import asyncio
import importlib.util
import ipaddress
import shlex
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Load modules directly without going through __init__.py
SRC = Path(__file__).parent.parent / "src"


def _load_module(name, filepath):
    """Load a Python module directly from file path."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- Shell Action Tests ----

class TestShellValidation:
    """Test command validation and allowlist enforcement."""

    @pytest.fixture(autouse=True)
    def _load_shell(self):
        # We need the base action class first
        base_mod = _load_module(
            "safestclaw.actions.base",
            SRC / "safestclaw" / "actions" / "base.py",
        )
        self._shell_mod = _load_module(
            "safestclaw.actions.shell",
            SRC / "safestclaw" / "actions" / "shell.py",
        )

    def _get_shell(self, **kwargs):
        return self._shell_mod.ShellAction(**kwargs)

    def test_allowed_command(self):
        shell = self._get_shell(sandboxed=True)
        is_valid, reason, args = shell._validate_command("ls -la")
        assert is_valid
        assert args == ["ls", "-la"]

    def test_blocked_command_not_in_allowlist(self):
        shell = self._get_shell(sandboxed=True)
        is_valid, reason, _ = shell._validate_command("rm -rf /")
        assert not is_valid
        assert "not allowed" in reason

    def test_blocked_interpreter(self):
        """Shell interpreters must not be in the allowlist."""
        shell = self._get_shell(sandboxed=True)
        for cmd in ["sh", "bash", "zsh", "dash"]:
            is_valid, _, _ = shell._validate_command(f"{cmd} -c 'echo pwned'")
            assert not is_valid, f"{cmd} should not be allowed"

    def test_blocked_scripting_languages(self):
        shell = self._get_shell(sandboxed=True)
        for cmd in ["perl", "ruby"]:
            is_valid, _, _ = shell._validate_command(f"{cmd} -e 'system(\"id\")'")
            assert not is_valid, f"{cmd} should not be allowed"

    def test_empty_command(self):
        shell = self._get_shell(sandboxed=True)
        is_valid, _, _ = shell._validate_command("")
        assert not is_valid

    def test_path_stripping(self):
        """Absolute paths should be checked by basename only."""
        shell = self._get_shell(sandboxed=True)
        is_valid, _, args = shell._validate_command("/usr/bin/ls -la")
        assert is_valid
        assert args == ["/usr/bin/ls", "-la"]

    def test_unsandboxed_allows_anything(self):
        shell = self._get_shell(sandboxed=False)
        is_valid, _, _ = shell._validate_command("anything_goes")
        assert is_valid

    def test_custom_allowlist(self):
        shell = self._get_shell(allowed_commands=["myapp"])
        is_valid, _, _ = shell._validate_command("myapp --flag")
        assert is_valid
        is_valid, _, _ = shell._validate_command("ls")
        assert not is_valid

    @pytest.mark.asyncio
    async def test_execute_disabled(self):
        shell = self._get_shell(enabled=False)
        result = await shell.execute({"command": "ls"}, "user", "cli", None)
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_execute_blocked(self):
        shell = self._get_shell(sandboxed=True)
        result = await shell.execute({"command": "bash -c 'echo hi'"}, "user", "cli", None)
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_allowed(self):
        shell = self._get_shell(sandboxed=True)
        result = await shell.execute({"command": "echo hello"}, "user", "cli", None)
        assert "hello" in result


# ---- SSRF Protection Tests ----

class TestSSRFProtection:
    """Test the is_safe_url function from crawler.py."""

    @pytest.fixture(autouse=True)
    def _load_crawler(self):
        self._mod = _load_module(
            "safestclaw.core.crawler",
            SRC / "safestclaw" / "core" / "crawler.py",
        )

    def test_blocks_localhost(self):
        safe, _ = self._mod.is_safe_url("http://localhost/admin")
        assert not safe

    def test_blocks_127(self):
        safe, _ = self._mod.is_safe_url("http://127.0.0.1/admin")
        assert not safe

    def test_blocks_metadata_endpoint(self):
        safe, _ = self._mod.is_safe_url("http://169.254.169.254/latest/meta-data/")
        assert not safe

    def test_blocks_private_10(self):
        safe, _ = self._mod.is_safe_url("http://10.0.0.1/internal")
        assert not safe

    def test_blocks_private_192(self):
        safe, _ = self._mod.is_safe_url("http://192.168.1.1/router")
        assert not safe

    def test_blocks_dot_local(self):
        safe, _ = self._mod.is_safe_url("http://myserver.local/api")
        assert not safe

    def test_allows_public_url(self):
        """Public URL with a public IP should be allowed."""
        # Mock DNS to return a public IP (93.184.216.34 is example.com)
        mock_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=mock_info):
            safe, _ = self._mod.is_safe_url("https://example.com")
            assert safe

    def test_blocks_no_hostname(self):
        safe, _ = self._mod.is_safe_url("not-a-url")
        assert not safe

    def test_blocks_dns_failure(self):
        """DNS resolution failure should block the request."""
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS failed")):
            safe, reason = self._mod.is_safe_url("http://evil.example.com/")
            assert not safe
            assert "DNS" in reason


# ---- Document Path Access Tests ----

class TestDocumentSecurity:
    """Test document reader path restrictions."""

    @pytest.fixture(autouse=True)
    def _load_docs(self):
        self._mod = _load_module(
            "safestclaw.core.documents",
            SRC / "safestclaw" / "core" / "documents.py",
        )

    def test_blocks_etc_passwd(self):
        reader = self._mod.DocumentReader()
        result = reader.read("/etc/passwd")
        assert result.error is not None
        assert "denied" in result.error.lower() or "outside" in result.error.lower()

    def test_blocks_traversal(self):
        reader = self._mod.DocumentReader(allowed_paths=["~/documents"])
        result = reader.read("/etc/shadow")
        assert result.error is not None

    def test_allows_home_dir(self):
        reader = self._mod.DocumentReader()
        # This should not be denied (file won't exist, but should get
        # "not found" rather than "access denied")
        result = reader.read(str(Path.home() / "nonexistent_test_file.txt"))
        assert result.error is not None
        assert "denied" not in result.error.lower()
