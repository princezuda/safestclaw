"""
Tests for the new blog publishing features:

- ``sftp_subfolder`` on PublishTarget
- Per-target HTML template (inline ``html_template`` and on-disk
  ``html_template_path``)
- ``BlogPublisher.render_preview`` for see-before-publish
- BlogAction.preview blog / publish blog again / saved last target

Real network is never touched — SFTP uploads are mocked at the
``_sftp_upload_via_command`` level.
"""

from __future__ import annotations

import asyncio
import sys
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
    "paramiko", "sgmllib3k", "vaderSentiment", "vaderSentiment.vaderSentiment",
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

from safestclaw.core.blog_publisher import (  # noqa: E402
    BlogPublisher,
    PublishResult,
    PublishTarget,
    PublishTargetType,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# PublishTarget: subfolder + template helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_remote_dir_without_subfolder_unchanged():
    t = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_remote_path="/var/www/html/blog",
    )
    assert t.remote_dir() == "/var/www/html/blog"


def test_remote_dir_appends_subfolder():
    t = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_remote_path="/var/www/html",
        sftp_subfolder="blog",
    )
    assert t.remote_dir() == "/var/www/html/blog"


def test_remote_dir_strips_extra_slashes():
    t = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_remote_path="/var/www/html/",
        sftp_subfolder="/posts/2026/",
    )
    assert t.remote_dir() == "/var/www/html/posts/2026"


def test_load_html_template_inline_wins():
    t = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        html_template="<h1>{title}</h1>",
        html_template_path="/nonexistent",
    )
    assert t.load_html_template() == "<h1>{title}</h1>"


def test_load_html_template_from_path(tmp_path: Path):
    f = tmp_path / "tmpl.html"
    f.write_text("<header>{title}</header><main>{content}</main>")
    t = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        html_template_path=str(f),
    )
    assert "{content}" in t.load_html_template()


def test_load_html_template_returns_empty_when_unset():
    t = PublishTarget(label="t", target_type=PublishTargetType.SFTP)
    assert t.load_html_template() == ""


def test_load_html_template_missing_path_returns_empty(tmp_path: Path):
    t = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        html_template_path=str(tmp_path / "nope.html"),
    )
    assert t.load_html_template() == ""


# ─────────────────────────────────────────────────────────────────────────────
# render_preview
# ─────────────────────────────────────────────────────────────────────────────

def test_render_preview_uses_default_when_no_template():
    pub = BlogPublisher()
    pub.add_target(PublishTarget(
        label="default", target_type=PublishTargetType.SFTP,
        sftp_host="h", sftp_user="u",
    ))
    html, target = pub.render_preview(
        title="Hello", content="Body para 1\n\nBody para 2",
        target_label="default",
    )
    assert target.label == "default"
    assert "<title>Hello</title>" in html
    assert "<p>Body para 1</p>" in html


def test_render_preview_honors_inline_template():
    pub = BlogPublisher()
    pub.add_target(PublishTarget(
        label="custom", target_type=PublishTargetType.SFTP,
        html_template=(
            "<!doctype html><h1>{title}</h1><time>{date}</time>"
            "<article>{content}</article>"
        ),
    ))
    html, _ = pub.render_preview(
        title="My Post", content="One.\n\nTwo.",
        target_label="custom",
    )
    assert "<h1>My Post</h1>" in html
    assert "<article><p>One.</p>" in html


def test_render_preview_falls_back_when_template_has_bad_placeholder():
    """A template referencing a non-existent placeholder must not break."""
    pub = BlogPublisher()
    pub.add_target(PublishTarget(
        label="bad", target_type=PublishTargetType.SFTP,
        html_template="<h1>{title}</h1>{nonexistent}",
    ))
    html, _ = pub.render_preview(title="T", content="x", target_label="bad")
    # Falls through to the default template
    assert "<title>T</title>" in html


def test_render_preview_no_target_uses_default():
    pub = BlogPublisher()
    html, target = pub.render_preview(title="T", content="x")
    assert target is None
    assert "<title>T</title>" in html


# ─────────────────────────────────────────────────────────────────────────────
# SFTP upload uses subfolder + template end-to-end
# ─────────────────────────────────────────────────────────────────────────────

def test_publish_sftp_uploads_to_subfolder():
    """When sftp_subfolder is set, the remote path includes it."""
    pub = BlogPublisher()
    target = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_host="example.com", sftp_user="u",
        sftp_remote_path="/var/www/html",
        sftp_subfolder="blog/posts",
    )
    pub.add_target(target)

    captured: dict[str, str] = {}

    async def fake_upload(self, target, content, remote_path, filename):
        captured["remote_path"] = remote_path
        captured["html"] = content
        return PublishResult(
            success=True, target_label=target.label, target_type="sftp",
            message="ok", url=f"sftp://h{remote_path}",
        )

    with patch.object(BlogPublisher, "_sftp_upload_via_command", new=fake_upload):
        result = run(pub.publish(
            title="My Post", content="Body", target_label="t",
            slug="my-post",
        ))
    assert result[0].success
    assert captured["remote_path"].startswith("/var/www/html/blog/posts/")
    assert captured["remote_path"].endswith("-my-post.html")


def test_publish_sftp_uses_inline_template():
    pub = BlogPublisher()
    target = PublishTarget(
        label="t", target_type=PublishTargetType.SFTP,
        sftp_host="example.com", sftp_user="u",
        html_template=(
            "<!-- custom -->\n<h1>{title}</h1>\n<div>{content}</div>"
        ),
    )
    pub.add_target(target)

    captured: dict[str, str] = {}

    async def fake_upload(self, target, content, remote_path, filename):
        captured["html"] = content
        return PublishResult(
            success=True, target_label=target.label, target_type="sftp",
            message="ok", url="",
        )

    with patch.object(BlogPublisher, "_sftp_upload_via_command", new=fake_upload):
        run(pub.publish(title="Hi", content="Body para",
                        target_label="t", slug="hi"))
    assert captured["html"].startswith("<!-- custom -->")
    assert "<h1>Hi</h1>" in captured["html"]
    assert "<title>Hi</title>" not in captured["html"]  # default template not used


# ─────────────────────────────────────────────────────────────────────────────
# from_config picks up the new fields
# ─────────────────────────────────────────────────────────────────────────────

def test_from_config_reads_new_fields(tmp_path: Path):
    tmpl = tmp_path / "wrap.html"
    tmpl.write_text("<x>{title}</x>")
    pub = BlogPublisher.from_config({
        "publish_targets": [{
            "label": "ours",
            "type": "sftp",
            "sftp_host": "h",
            "sftp_user": "u",
            "sftp_remote_path": "/srv/www",
            "sftp_subfolder": "site/blog",
            "html_template_path": str(tmpl),
        }],
    })
    t = pub.targets["ours"]
    assert t.sftp_subfolder == "site/blog"
    assert t.html_template_path == str(tmpl)
    assert t.remote_dir() == "/srv/www/site/blog"
    assert "{title}" in t.load_html_template()


# ─────────────────────────────────────────────────────────────────────────────
# BlogAction: preview, publish-again, saved-target memory, subfolder parse
# ─────────────────────────────────────────────────────────────────────────────

from safestclaw.actions.blog import BlogAction  # noqa: E402


def _make_action(tmp_path: Path) -> BlogAction:
    a = BlogAction(blog_dir=tmp_path)
    a._initialized = True
    a.summarizer = MagicMock()
    a.summarizer.summarize = MagicMock(return_value="Auto Title")
    a.summarizer.get_keywords = MagicMock(return_value=["x"])
    return a


def _engine_with_memory():
    eng = MagicMock()
    eng.config = {}

    store: dict = {}
    eng.memory = MagicMock()
    eng.memory.get = AsyncMock(side_effect=lambda k: store.get(k))
    eng.memory.set = AsyncMock(
        side_effect=lambda k, v, ttl_seconds=None: store.update({k: v})
    )
    return eng, store


def test_preview_blog_renders_html(tmp_path: Path):
    a = _make_action(tmp_path)
    # Seed a draft
    draft = a._get_draft_path("u")
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("My Post Title\n\n## Entries\nFirst paragraph.\n\nSecond paragraph.")

    eng, _ = _engine_with_memory()
    out = run(a._preview_blog("preview blog", "u", eng))

    assert "**Preview" in out
    assert "<title>" in out  # default template body shown


def test_preview_blog_uses_named_target(tmp_path: Path):
    a = _make_action(tmp_path)
    draft = a._get_draft_path("u")
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("T\n\nbody")

    a.publisher = BlogPublisher()
    a.publisher.add_target(PublishTarget(
        label="myhost", target_type=PublishTargetType.SFTP,
        sftp_host="example.com", sftp_user="u",
        sftp_remote_path="/var/www/html",
        sftp_subfolder="blog",
    ))

    eng, _ = _engine_with_memory()
    out = run(a._preview_blog("preview blog to myhost", "u", eng))
    # The preview header should mention the resolved upload path
    assert "/var/www/html/blog/" in out
    assert out.endswith(
        "to keep the draft and skip publishing"
    ) or "publish blog to myhost" in out


def test_publish_again_replays_last_target(tmp_path: Path):
    a = _make_action(tmp_path)
    draft = a._get_draft_path("u")
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("My Title\n\nbody body body")

    eng, store = _engine_with_memory()
    store[f"{BlogAction._LAST_TARGET_KEY}:u"] = "myhost"

    with patch.object(
        BlogAction, "_do_publish",
        new=AsyncMock(return_value="published OK"),
    ) as do_pub:
        out = run(a._publish_again("u", eng))

    assert "published OK" in out
    args = do_pub.await_args
    # _do_publish(self, title, target_label, user_id, engine=...)
    assert args.args[1] == "myhost"  # second positional after self in call
    assert args.kwargs.get("engine") is eng


def test_publish_again_without_history_says_so(tmp_path: Path):
    a = _make_action(tmp_path)
    eng, _ = _engine_with_memory()
    out = run(a._publish_again("u", eng))
    assert "No previous publish" in out


def test_inline_target_subfolder_parsed_from_command(tmp_path: Path):
    """`setup blog publish sftp://… subfolder=blog/posts` captures the folder."""
    a = _make_action(tmp_path)
    a.publisher = BlogPublisher()

    # Real config path under tmp_path so _save_publish_target_to_config
    # doesn't try to mkdir on a mocked path (which would leak a real
    # directory into the repo root).
    config_file = tmp_path / "config" / "config.yaml"
    eng = MagicMock()
    eng.config_path = config_file
    eng.config = {"publish_targets": []}

    raw = "setup blog publish sftp://example.com user pass /var/www/html subfolder=blog/posts"
    out = run(a._setup_publish(raw, "u", eng))

    assert a.publisher.targets, "target was not registered"
    last = list(a.publisher.targets.values())[-1]
    assert last.sftp_subfolder == "blog/posts"
    # Friendly response mentions the target
    assert "Target active" in out or "Publish target" in out


def test_pending_publish_preview_command_routes_to_preview(tmp_path: Path):
    """While a publish is staged, typing `preview` shows the full HTML."""
    a = _make_action(tmp_path)
    draft = a._get_draft_path("u")
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("Title\n\nbody")
    eng, _ = _engine_with_memory()

    session = {"pending_title": "Title", "target_label": "myhost"}
    a.publisher = BlogPublisher()
    a.publisher.add_target(PublishTarget(
        label="myhost", target_type=PublishTargetType.SFTP,
        sftp_host="h", sftp_user="u",
    ))
    out = run(a._handle_pending_publish(
        session, "preview", "preview", "u", eng,
    ))
    assert "**Preview" in out


def test_do_publish_saves_last_target_on_success(tmp_path: Path):
    a = _make_action(tmp_path)
    draft = a._get_draft_path("u")
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("Title\n\nbody body body")

    a.publisher = BlogPublisher()
    a.publisher.add_target(PublishTarget(
        label="myhost", target_type=PublishTargetType.SFTP,
        sftp_host="h", sftp_user="u",
    ))
    eng, store = _engine_with_memory()

    a.publisher.publish = AsyncMock(return_value=[
        PublishResult(
            success=True, target_label="myhost", target_type="sftp",
            message="ok", url="sftp://h/x", post_id="1",
        ),
    ])

    out = run(a._do_publish("Title", "myhost", "u", engine=eng))
    assert "ok" in out
    assert store[f"{BlogAction._LAST_TARGET_KEY}:u"] == "myhost"
    assert "publish blog again" in out


def test_do_publish_does_not_save_on_failure(tmp_path: Path):
    a = _make_action(tmp_path)
    draft = a._get_draft_path("u")
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("Title\n\nbody body")

    a.publisher = BlogPublisher()
    a.publisher.add_target(PublishTarget(
        label="myhost", target_type=PublishTargetType.SFTP,
        sftp_host="h", sftp_user="u",
    ))
    eng, store = _engine_with_memory()

    a.publisher.publish = AsyncMock(return_value=[
        PublishResult(
            success=False, target_label="myhost", target_type="sftp",
            error="boom",
        ),
    ])

    run(a._do_publish("Title", "myhost", "u", engine=eng))
    assert f"{BlogAction._LAST_TARGET_KEY}:u" not in store


def test_is_publish_again_matches_variants():
    a = BlogAction.__new__(BlogAction)
    assert a._is_publish_again("publish blog again")
    assert a._is_publish_again("publish again")
    assert a._is_publish_again("republish")
    assert a._is_publish_again("publish blog to here")
    assert a._is_publish_again("publish to last")
    assert not a._is_publish_again("publish blog to myhost")


def test_is_preview_matches_variants():
    a = BlogAction.__new__(BlogAction)
    assert a._is_preview("preview blog")
    assert a._is_preview("preview blog to myhost")
    assert a._is_preview("show preview")
    assert a._is_preview("render blog")
    assert not a._is_preview("publish blog")
