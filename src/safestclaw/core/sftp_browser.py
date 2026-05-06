"""
SFTP folder browser and template learner for blog publishing.

Two responsibilities:

1. **Listing**: enumerate directories and HTML files on a remote SFTP
   target so the user can pick where to publish without having to type
   the path from memory.

2. **Template learning**: download an existing post from the target,
   detect the title and main-content regions, replace them with
   ``{title}`` / ``{content}`` placeholders, and return the resulting
   string. The result can be saved back to the publish target so future
   publishes inherit the site's existing look without any manual
   templating.

Both rely on `paramiko` (an optional dep, declared as the ``sftp``
extra). When it isn't installed the module's helpers raise ``ImportError``
with a clear install hint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from safestclaw.core.blog_publisher import PublishTarget

try:
    import paramiko  # type: ignore[import-not-found]
    HAS_PARAMIKO = True
except ImportError:  # pragma: no cover - import guard
    paramiko = None  # type: ignore[assignment]
    HAS_PARAMIKO = False


@dataclass
class RemoteEntry:
    """A directory entry returned by an SFTP listing."""
    name: str
    path: str
    is_dir: bool
    size: int = 0
    mtime: datetime | None = None


def _connect(target: PublishTarget):
    """Open a paramiko SFTPClient for `target`. Caller must close it."""
    if not HAS_PARAMIKO:
        raise ImportError(
            "paramiko is required for SFTP browsing. "
            "Run: pip install safestclaw[sftp]"
        )
    transport = paramiko.Transport((target.sftp_host, target.sftp_port))
    if target.sftp_key_path:
        key = paramiko.RSAKey.from_private_key_file(target.sftp_key_path)
        transport.connect(username=target.sftp_user, pkey=key)
    else:
        transport.connect(
            username=target.sftp_user,
            password=target.sftp_password,
        )
    sftp = paramiko.SFTPClient.from_transport(transport)
    if sftp is None:
        transport.close()
        raise RuntimeError("Could not create SFTP client")
    return sftp, transport


def list_folders(
    target: PublishTarget,
    base_path: str | None = None,
) -> list[RemoteEntry]:
    """
    List subdirectories under ``base_path`` (defaults to the target's
    ``remote_dir()``). Returns only directories, sorted by name.
    """
    base = (base_path or target.remote_dir()).rstrip("/")
    sftp, transport = _connect(target)
    try:
        entries: list[RemoteEntry] = []
        for attr in sftp.listdir_attr(base):
            mode = attr.st_mode or 0
            is_dir = bool(mode & 0o040000)
            if not is_dir:
                continue
            name = attr.filename
            if name in (".", ".."):
                continue
            entries.append(RemoteEntry(
                name=name,
                path=f"{base}/{name}",
                is_dir=True,
                size=attr.st_size or 0,
                mtime=(
                    datetime.fromtimestamp(attr.st_mtime)
                    if attr.st_mtime else None
                ),
            ))
        entries.sort(key=lambda e: e.name.lower())
        return entries
    finally:
        sftp.close()
        transport.close()


def list_html_files(
    target: PublishTarget,
    dir_path: str | None = None,
) -> list[RemoteEntry]:
    """
    List ``.html`` files under ``dir_path`` (defaults to the target's
    ``remote_dir()``). Sorted newest-first by mtime so the most recent
    post is the natural template sample.
    """
    base = (dir_path or target.remote_dir()).rstrip("/")
    sftp, transport = _connect(target)
    try:
        entries: list[RemoteEntry] = []
        for attr in sftp.listdir_attr(base):
            mode = attr.st_mode or 0
            if mode & 0o040000:
                continue  # skip directories
            name = attr.filename
            if not name.lower().endswith((".html", ".htm")):
                continue
            entries.append(RemoteEntry(
                name=name,
                path=f"{base}/{name}",
                is_dir=False,
                size=attr.st_size or 0,
                mtime=(
                    datetime.fromtimestamp(attr.st_mtime)
                    if attr.st_mtime else None
                ),
            ))
        entries.sort(
            key=lambda e: e.mtime or datetime.min, reverse=True,
        )
        return entries
    finally:
        sftp.close()
        transport.close()


def download_text(target: PublishTarget, remote_path: str) -> str:
    """Download ``remote_path`` as text (UTF-8, replace on errors)."""
    sftp, transport = _connect(target)
    try:
        with sftp.file(remote_path, "rb") as f:
            data = f.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)
    finally:
        sftp.close()
        transport.close()


# ─────────────────────────────────────────────────────────────────────────────
# Template learning
# ─────────────────────────────────────────────────────────────────────────────

# Tags that almost certainly hold the post body. Checked in order;
# the first match wins.
_CONTENT_SELECTORS: tuple[tuple[str, dict | None], ...] = (
    ("article", None),
    ("main", None),
    ("div", {"class_": "post-content"}),
    ("div", {"class_": "entry-content"}),
    ("div", {"class_": "post"}),
    ("div", {"class_": "content"}),
    ("div", {"id": "content"}),
    ("section", {"class_": "post"}),
)


def learn_template_from_html(html: str) -> str:
    """
    Convert an existing rendered post into a SafestClaw template by
    replacing the title and main-content regions with ``{title}`` and
    ``{content}`` placeholders. Everything else (head, nav, footer,
    sidebar, scripts, styles) is preserved verbatim.

    Returns the templated string. If the HTML can't be parsed (no
    ``bs4``, malformed input) a ``ValueError`` is raised so the caller
    can fall back to the default template.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:  # pragma: no cover - bs4 is a core dep
        raise ValueError(f"BeautifulSoup unavailable: {e}") from e

    soup = BeautifulSoup(html or "", "html.parser")

    # 1. Replace the title element. Prefer <h1> in the body, then <title>.
    h1 = soup.find("h1")
    if h1 is not None:
        h1.string = "__SAFESTCLAW_TITLE__"
    title_tag = soup.find("title")
    if title_tag is not None:
        title_tag.string = "__SAFESTCLAW_TITLE__"

    # 2. Replace the main content area.
    content_tag = None
    for tag_name, attrs in _CONTENT_SELECTORS:
        if attrs is None:
            content_tag = soup.find(tag_name)
        else:
            content_tag = soup.find(tag_name, **attrs)
        if content_tag is not None:
            break

    # Last-resort: pick the body element itself if nothing more specific
    # matched.
    if content_tag is None:
        content_tag = soup.find("body")

    if content_tag is None:
        raise ValueError("Could not identify a content region in the HTML")

    # 3. Optionally replace a date element with {date} if one looks
    # obvious. Done BEFORE clearing the content tag so a date inside
    # the article (the common case) survives long enough to be marked.
    date_el = (
        soup.find(class_="date")
        or soup.find(class_="post-date")
        or soup.find("time")
    )
    if date_el is not None:
        date_el.clear()
        date_el.append("__SAFESTCLAW_DATE__")
        # If the date sits inside the content area, lift it out so it
        # survives the upcoming content-tag clear.
        if content_tag in date_el.parents:
            content_tag.insert_before(date_el.extract())

    # Wipe the content and drop a placeholder marker. Empty out children
    # in-place so attributes (class names, ids) are preserved.
    content_tag.clear()
    content_tag.append("__SAFESTCLAW_CONTENT__")

    rendered = str(soup)
    rendered = rendered.replace("__SAFESTCLAW_TITLE__", "{title}")
    rendered = rendered.replace("__SAFESTCLAW_CONTENT__", "{content}")
    rendered = rendered.replace("__SAFESTCLAW_DATE__", "{date}")

    if "{title}" not in rendered or "{content}" not in rendered:
        raise ValueError(
            "Template detection produced an unusable result "
            "(missing title or content placeholder)"
        )

    return rendered


def learn_template_from_target(
    target: PublishTarget,
    folder: str | None = None,
    sample_filename: str | None = None,
) -> tuple[str, str]:
    """
    Download a sample post from ``target`` and convert it to a template.

    Args:
        target: Configured SFTP publish target.
        folder: Optional subdirectory to search; defaults to
                ``target.remote_dir()``.
        sample_filename: Optional explicit filename to use; otherwise the
                         most recently modified ``.html`` is picked.

    Returns:
        ``(template_string, source_path)``.

    Raises:
        ValueError: when no HTML files are found or template extraction
                    fails — caller should fall back to the default template.
        ImportError: when paramiko isn't installed.
    """
    if sample_filename:
        base = (folder or target.remote_dir()).rstrip("/")
        path = f"{base}/{sample_filename.lstrip('/')}"
    else:
        files = list_html_files(target, folder)
        if not files:
            raise ValueError(
                f"No .html files found under {folder or target.remote_dir()}"
            )
        # Skip index.html — usually a listing page, not a post.
        post_candidates = [
            f for f in files if f.name.lower() != "index.html"
        ] or files
        path = post_candidates[0].path

    html = download_text(target, path)
    return learn_template_from_html(html), path
