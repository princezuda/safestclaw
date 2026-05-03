"""
Tests for the SFTP browser, template learner, and the blog action's
list-folders / learn-template chat commands.

paramiko is mocked at the module level so the suite stays hermetic
(no real SSH connections, no need to install paramiko in CI).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── src/ on path ────────────────────────────────────────────────────────────
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── Mock heavy optional deps (mirrors test_sweep.py) ────────────────────────
_mock_fp = MagicMock()
_mock_fp.parse = MagicMock(return_value=MagicMock(entries=[]))
sys.modules.setdefault("feedparser", _mock_fp)
sys.modules.setdefault("desktop_notifier", MagicMock())
for _mod in (
    "sgmllib3k", "vaderSentiment", "vaderSentiment.vaderSentiment",
    "aiosqlite", "aiohttp", "aiofiles",
    "apscheduler", "apscheduler.schedulers.asyncio",
    "apscheduler.triggers.cron", "apscheduler.triggers.interval",
    "apscheduler.triggers.date",
    "yaml",
    "typer",
    "rich", "rich.console", "rich.markdown", "rich.live", "rich.panel",
    "rich.text", "rich.prompt", "rich.table", "rich.logging",
    "sumy", "sumy.parsers", "sumy.parsers.plaintext",
    "sumy.nlp", "sumy.nlp.tokenizers", "sumy.nlp.stemmers",
    "sumy.summarizers", "sumy.summarizers.lex_rank", "sumy.summarizers.lsa",
    "sumy.summarizers.luhn", "sumy.summarizers.text_rank",
    "sumy.summarizers.edmundson", "sumy.utils",
    "nltk",
    "icalendar",
    "fitz",
    "docx",
    "PIL", "PIL.Image",
    "fastapi", "uvicorn",
):
    sys.modules.setdefault(_mod, MagicMock())

import rapidfuzz  # noqa: E402

from safestclaw.actions.blog import BlogAction  # noqa: E402
from safestclaw.core.blog_publisher import (  # noqa: E402
    BlogPublisher,
    PublishTarget,
    PublishTargetType,
)
from safestclaw.core import sftp_browser  # noqa: E402


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# learn_template_from_html — pure function, no SSH
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_POST = """<!DOCTYPE html>
<html>
<head>
  <title>The Old Post Title</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header><nav>home · blog · about</nav></header>
  <article>
    <h1>The Old Post Title</h1>
    <time class="post-date">2026-04-01</time>
    <p>First paragraph of the old post.</p>
    <p>Second paragraph with <em>emphasis</em>.</p>
  </article>
  <footer>© 2026</footer>
</body>
</html>
"""


def test_learn_template_replaces_title_and_content():
    out = sftp_browser.learn_template_from_html(SAMPLE_POST)
    assert "{title}" in out
    assert "{content}" in out
    # Site chrome is preserved
    assert "home · blog · about" in out
    assert "© 2026" in out
    # Original body text is gone (replaced by the placeholder)
    assert "First paragraph of the old post" not in out


def test_learn_template_replaces_date_when_obvious():
    out = sftp_browser.learn_template_from_html(SAMPLE_POST)
    assert "{date}" in out
    assert "2026-04-01" not in out


def test_learn_template_falls_back_to_main_then_body():
    """When no <article> exists but <main> does, use that."""
    html = """
    <html><head><title>X</title></head>
    <body>
      <header>nav</header>
      <main>
        <h1>X</h1>
        <p>Body</p>
      </main>
    </body></html>
    """
    out = sftp_browser.learn_template_from_html(html)
    assert "{title}" in out and "{content}" in out


def test_learn_template_uses_class_post_content():
    html = """
    <html><body>
      <h1>X</h1>
      <div class="post-content"><p>real body</p></div>
    </body></html>
    """
    out = sftp_browser.learn_template_from_html(html)
    assert "{content}" in out
    assert 'class="post-content"' in out
    assert "real body" not in out


def test_learn_template_empty_body_raises():
    with __import__("pytest").raises(ValueError):
        sftp_browser.learn_template_from_html("")


def test_learn_template_no_title_or_content_raises():
    """If we can't find anything to substitute, raise so the caller can
    fall back to the default template."""
    import pytest
    with pytest.raises(ValueError):
        sftp_browser.learn_template_from_html("<html><head></head></html>")


# ─────────────────────────────────────────────────────────────────────────────
# list_folders / list_html_files — paramiko mocked
# ─────────────────────────────────────────────────────────────────────────────

def _fake_sftp_attr(name: str, is_dir: bool, mtime: int = 0, size: int = 0):
    a = MagicMock()
    a.filename = name
    a.st_mode = 0o040755 if is_dir else 0o100644
    a.st_size = size
    a.st_mtime = mtime
    return a


def _patch_paramiko(listdir_attrs=None, file_data=b""):
    """Return context managers that patch sftp_browser._connect to return
    a mock SFTP/transport pair."""
    sftp = MagicMock()
    sftp.listdir_attr = MagicMock(return_value=listdir_attrs or [])
    file_handle = MagicMock()
    file_handle.__enter__ = MagicMock(return_value=file_handle)
    file_handle.__exit__ = MagicMock(return_value=False)
    file_handle.read = MagicMock(return_value=file_data)
    sftp.file = MagicMock(return_value=file_handle)
    sftp.close = MagicMock()
    transport = MagicMock()
    transport.close = MagicMock()
    return patch.object(
        sftp_browser, "_connect", return_value=(sftp, transport),
    )


def _target() -> PublishTarget:
    return PublishTarget(
        label="myhost", target_type=PublishTargetType.SFTP,
        sftp_host="example.com", sftp_user="u",
        sftp_remote_path="/var/www/html",
        sftp_subfolder="blog",
    )


def test_list_folders_returns_only_directories_sorted():
    attrs = [
        _fake_sftp_attr("posts", True, mtime=100),
        _fake_sftp_attr("README", False),
        _fake_sftp_attr("archive", True, mtime=200),
        _fake_sftp_attr(".", True),
        _fake_sftp_attr("..", True),
    ]
    with _patch_paramiko(listdir_attrs=attrs), \
         patch.object(sftp_browser, "HAS_PARAMIKO", True):
        out = sftp_browser.list_folders(_target())
    names = [e.name for e in out]
    assert names == ["archive", "posts"]


def test_list_html_files_sorted_newest_first():
    attrs = [
        _fake_sftp_attr("old.html", False, mtime=100),
        _fake_sftp_attr("new.html", False, mtime=200),
        _fake_sftp_attr("readme.txt", False, mtime=300),
        _fake_sftp_attr("subdir", True),
    ]
    with _patch_paramiko(listdir_attrs=attrs), \
         patch.object(sftp_browser, "HAS_PARAMIKO", True):
        out = sftp_browser.list_html_files(_target())
    names = [e.name for e in out]
    assert names == ["new.html", "old.html"]


def test_list_folders_raises_without_paramiko():
    import pytest
    with patch.object(sftp_browser, "HAS_PARAMIKO", False):
        with pytest.raises(ImportError):
            sftp_browser.list_folders(_target())


# ─────────────────────────────────────────────────────────────────────────────
# learn_template_from_target — wires listing + download + extraction
# ─────────────────────────────────────────────────────────────────────────────

def test_learn_template_from_target_downloads_most_recent():
    attrs = [
        _fake_sftp_attr("index.html", False, mtime=999),  # listing page
        _fake_sftp_attr("old.html", False, mtime=100),
        _fake_sftp_attr("recent.html", False, mtime=500),
    ]
    with _patch_paramiko(
        listdir_attrs=attrs,
        file_data=SAMPLE_POST.encode(),
    ) as p, patch.object(sftp_browser, "HAS_PARAMIKO", True):
        template, source = sftp_browser.learn_template_from_target(_target())
    assert "{title}" in template and "{content}" in template
    # Should pick recent.html, not index.html
    assert source.endswith("/recent.html")


def test_learn_template_from_target_no_files_raises():
    import pytest
    with _patch_paramiko(listdir_attrs=[]), \
         patch.object(sftp_browser, "HAS_PARAMIKO", True):
        with pytest.raises(ValueError):
            sftp_browser.learn_template_from_target(_target())


# ─────────────────────────────────────────────────────────────────────────────
# Auto-detect path inside _generate_html
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_html_uses_auto_detected_template():
    pub = BlogPublisher()
    target = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_host="h", sftp_user="u",
        auto_detect_template=True,
    )
    pub.add_target(target)

    with patch(
        "safestclaw.core.sftp_browser.learn_template_from_target",
        return_value=("<x>{title}</x>:<y>{content}</y>", "/r/sample.html"),
    ):
        html, _ = pub.render_preview(
            title="Hi", content="body para", target_label="t",
        )
    assert "<x>Hi</x>" in html
    assert "<y><p>body para</p></y>" in html
    # Cached on the target so the next publish doesn't re-fetch
    assert "{title}" in target.html_template


def test_generate_html_auto_detect_failure_falls_back_to_default():
    pub = BlogPublisher()
    target = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_host="h", sftp_user="u",
        auto_detect_template=True,
    )
    pub.add_target(target)
    with patch(
        "safestclaw.core.sftp_browser.learn_template_from_target",
        side_effect=ValueError("no .html files"),
    ):
        html, _ = pub.render_preview(
            title="Hi", content="body", target_label="t",
        )
    # Default template is used instead
    assert "<title>Hi</title>" in html


# ─────────────────────────────────────────────────────────────────────────────
# Chat command detection
# ─────────────────────────────────────────────────────────────────────────────

def test_is_list_folders_matches_variants():
    a = BlogAction.__new__(BlogAction)
    assert a._is_list_folders("list folders on myhost")
    assert a._is_list_folders("show folders")
    assert a._is_list_folders("browse folders on myhost")
    assert a._is_list_folders("list directories on myhost")
    assert a._is_list_folders("pick folder")
    assert not a._is_list_folders("list publish targets")


def test_is_learn_template_matches_variants():
    a = BlogAction.__new__(BlogAction)
    assert a._is_learn_template("learn template from myhost")
    assert a._is_learn_template("grab template from myhost")
    assert a._is_learn_template("auto template")
    assert a._is_learn_template("template from myhost")
    assert not a._is_learn_template("html template path")


# ─────────────────────────────────────────────────────────────────────────────
# Chat commands end-to-end (paramiko mocked)
# ─────────────────────────────────────────────────────────────────────────────

def _make_action_with_target(tmp_path: Path) -> BlogAction:
    a = BlogAction(blog_dir=tmp_path)
    a._initialized = True
    a.summarizer = MagicMock()
    a.publisher = BlogPublisher()
    a.publisher.add_target(_target())
    return a


def test_list_remote_folders_returns_numbered_list(tmp_path: Path):
    a = _make_action_with_target(tmp_path)
    eng = MagicMock()
    eng.config = {}

    attrs = [
        _fake_sftp_attr("posts", True, mtime=100),
        _fake_sftp_attr("archive", True, mtime=200),
    ]
    with _patch_paramiko(listdir_attrs=attrs), \
         patch.object(sftp_browser, "HAS_PARAMIKO", True):
        out = run(a._list_remote_folders("list folders on myhost", eng))

    assert "**Folders on myhost**" in out
    assert "archive/" in out
    assert "posts/" in out


def test_list_remote_folders_unknown_target(tmp_path: Path):
    a = _make_action_with_target(tmp_path)
    eng = MagicMock()
    eng.config = {}
    out = run(a._list_remote_folders("list folders on nope", eng))
    assert "Unknown target" in out


def test_learn_template_chat_command(tmp_path: Path):
    a = _make_action_with_target(tmp_path)
    eng = MagicMock()
    eng.config = {}
    eng.config_path = tmp_path / "config.yaml"  # missing → save returns False

    attrs = [_fake_sftp_attr("recent.html", False, mtime=500)]
    with _patch_paramiko(
        listdir_attrs=attrs,
        file_data=SAMPLE_POST.encode(),
    ), patch.object(sftp_browser, "HAS_PARAMIKO", True):
        out = run(a._learn_template("learn template from myhost", eng))

    target = a.publisher.targets["myhost"]
    assert "{title}" in target.html_template
    assert "{content}" in target.html_template
    assert "Learned template from myhost" in out


def test_learn_template_handles_remote_failure(tmp_path: Path):
    a = _make_action_with_target(tmp_path)
    eng = MagicMock()
    eng.config = {}
    with patch.object(sftp_browser, "HAS_PARAMIKO", True), \
         patch.object(
             sftp_browser, "learn_template_from_target",
             side_effect=RuntimeError("connection refused"),
         ):
        out = run(a._learn_template("learn template from myhost", eng))
    assert "Could not learn template" in out
    assert "connection refused" in out


def test_resolve_target_label_picks_explicit():
    a = BlogAction.__new__(BlogAction)
    a.publisher = BlogPublisher()
    a.publisher.add_target(_target())
    label, err = a._resolve_target_label("list folders on myhost")
    assert label == "myhost"
    assert err is None


def test_resolve_target_label_defaults_to_first():
    a = BlogAction.__new__(BlogAction)
    a.publisher = BlogPublisher()
    a.publisher.add_target(_target())
    label, err = a._resolve_target_label("list folders")
    assert label == "myhost"
    assert err is None


def test_resolve_target_label_no_targets_returns_error():
    a = BlogAction.__new__(BlogAction)
    a.publisher = BlogPublisher()
    label, err = a._resolve_target_label("list folders")
    assert label is None
    assert "No publish targets" in err
