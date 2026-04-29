"""File operations action."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class FilesAction(BaseAction):
    """
    File system operations.

    Supports:
    - List files in directory
    - Search for files by pattern
    - Read file contents
    - File info (size, modified date)
    """

    name = "files"
    description = "File system operations"

    def __init__(self, allowed_paths: list[str] | None = None):
        """
        Initialize with allowed paths for security.

        Args:
            allowed_paths: List of allowed base paths (default: home directory)
        """
        self.allowed_paths = [
            Path(p).expanduser().resolve()
            for p in (allowed_paths or ["~"])
        ]

    def _is_allowed(self, path: Path) -> bool:
        """Check if path is within allowed directories."""
        try:
            resolved = path.expanduser().resolve()
            # Check if resolved path starts with any allowed path
            # This prevents path traversal attacks (e.g., ~/../../etc/passwd)
            for allowed in self.allowed_paths:
                try:
                    # is_relative_to returns True if path is under allowed
                    if resolved == allowed or resolved.is_relative_to(allowed):
                        return True
                except ValueError:
                    continue
            return False
        except (OSError, ValueError):
            # If we can't resolve the path safely, deny access
            return False

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute file operation."""
        operation = params.get("operation", "list")
        path = params.get("path", "~")
        pattern = params.get("pattern", "*")

        target = Path(path).expanduser()

        if not self._is_allowed(target):
            return f"Access denied: {path} is outside allowed directories"

        if operation == "list":
            return await self._list_files(target, pattern)
        elif operation == "search":
            return await self._search_files(target, pattern)
        elif operation == "info":
            return await self._file_info(target)
        elif operation == "read":
            return await self._read_file(target)
        else:
            return f"Unknown operation: {operation}"

    async def _list_files(self, path: Path, pattern: str = "*") -> str:
        """List files in a directory."""
        if not path.exists():
            return f"Directory not found: {path}"

        if not path.is_dir():
            return f"Not a directory: {path}"

        files = sorted(path.glob(pattern))[:50]  # Limit to 50

        if not files:
            return f"No files matching '{pattern}' in {path}"

        lines = [f"Files in {path}:", ""]
        for f in files:
            icon = "📁" if f.is_dir() else "📄"
            size = self._format_size(f.stat().st_size) if f.is_file() else ""
            lines.append(f"  {icon} {f.name}  {size}")

        if len(files) == 50:
            lines.append("  ... (showing first 50)")

        return "\n".join(lines)

    async def _search_files(self, path: Path, pattern: str) -> str:
        """Search for files recursively."""
        if not path.exists():
            return f"Directory not found: {path}"

        files = list(path.rglob(pattern))[:50]

        if not files:
            return f"No files matching '{pattern}' found in {path}"

        lines = [f"Found {len(files)} files matching '{pattern}':", ""]
        for f in files:
            rel = f.relative_to(path) if path in f.parents else f
            lines.append(f"  {rel}")

        return "\n".join(lines)

    async def _file_info(self, path: Path) -> str:
        """Get file information."""
        if not path.exists():
            return f"File not found: {path}"

        stat = path.stat()
        info = [
            f"File: {path.name}",
            f"Path: {path}",
            f"Type: {'Directory' if path.is_dir() else 'File'}",
            f"Size: {self._format_size(stat.st_size)}",
            f"Modified: {stat.st_mtime}",
        ]

        return "\n".join(info)

    async def _read_file(self, path: Path, max_lines: int = 100) -> str:
        """Read file contents (text files only)."""
        if not path.exists():
            return f"File not found: {path}"

        if path.is_dir():
            return f"Cannot read directory: {path}"

        try:
            with open(path) as f:
                lines = f.readlines()[:max_lines]
                content = "".join(lines)
                if len(lines) == max_lines:
                    content += f"\n... (showing first {max_lines} lines)"
                return content
        except UnicodeDecodeError:
            return f"Cannot read binary file: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

    def _format_size(self, size: int) -> str:
        """Format file size for display."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
