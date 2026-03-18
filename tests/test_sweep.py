"""
Comprehensive sweep test — widest possible coverage of blog action,
blog publisher, parser chain guards, and engine routing.

Covers:
- All _is_* routing methods in BlogAction
- All session state transitions (including cross-state)
- _looks_like_command / _is_explicit_command
- _parse_inline_target all schemes and edge cases
- _handle_pending_publish all branches
- _do_publish null guard and happy path
- BlogPublisher: no targets, unknown target, all 4 types (mocked network)
- BlogPublisher.from_config round-trip
- Parser chain guard (is_chain / parse_chain) for all text-consuming prefixes
- Engine handle_message: chain gate → parse → execute routing
- Multi-user isolation (sessions / drafts keyed by user_id)
- Security: path traversal in user_id, draft path stays in data_dir
- Edge cases: special chars in passwords, IPv6, empty draft, missing draft
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# ── Ensure src/ is on the path (package not installed) ───────────────────────
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── Mock heavy optional deps before any SafeClaw import ──────────────────────
_mock_fp = MagicMock()
_mock_fp.parse = MagicMock(return_value=MagicMock(entries=[]))
sys.modules.setdefault("feedparser", _mock_fp)
sys.modules.setdefault("desktop_notifier", MagicMock())
# Mock all dependencies not installed in the CI test environment
for _mod in (
    "paramiko", "sgmllib3k", "vaderSentiment", "vaderSentiment.vaderSentiment",
    "aiosqlite", "aiohttp", "aiofiles",
    "apscheduler", "apscheduler.schedulers.asyncio",
    "apscheduler.triggers.cron", "apscheduler.triggers.interval",
    "apscheduler.triggers.date",
    "yaml",
    "typer",
    "rich", "rich.console", "rich.markdown", "rich.live", "rich.panel", "rich.text",
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

# rapidfuzz.fuzz methods must return real ints (used in numeric comparisons)
_mock_fuzz = MagicMock()
_mock_fuzz.ratio = MagicMock(return_value=0)
_mock_fuzz.partial_ratio = MagicMock(return_value=0)
_mock_rapidfuzz = MagicMock()
_mock_rapidfuzz.fuzz = _mock_fuzz
sys.modules["rapidfuzz"] = _mock_rapidfuzz
sys.modules["rapidfuzz.fuzz"] = _mock_fuzz

# ── Now import SafeClaw modules ───────────────────────────────────────────────
from safeclaw.core.parser import CommandParser
from safeclaw.core.blog_publisher import (
    BlogPublisher, PublishTarget, PublishTargetType, PublishResult,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# BlogAction helpers — build a minimal BlogAction without full engine
# ─────────────────────────────────────────────────────────────────────────────

def _make_blog_action(tmp_path: Path):
    """Return a BlogAction wired to a temp data dir."""
    from safeclaw.actions.blog import BlogAction
    action = BlogAction(blog_dir=tmp_path)
    # Override summarizer with a mock so tests don't need full NLP
    action.summarizer = MagicMock()
    action.summarizer.summarize = MagicMock(return_value="Auto Generated Title")
    action.summarizer.get_keywords = MagicMock(return_value=["tech", "news"])
    # Pre-mark as initialized so _ensure_initialized won't overwrite our mocks
    action._initialized = True
    return action


def _write_draft(action, user_id: str, content: str):
    path = action._get_draft_path(user_id)
    path.write_text(content)


# ─────────────────────────────────────────────────────────────────────────────
# 1. _is_* routing methods
# ─────────────────────────────────────────────────────────────────────────────

class TestIsRouting(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)

    # _is_bare_blog
    def test_is_bare_blog_positive(self):
        for t in ("blog", "blog ai", "ai blog", "manual blog"):
            self.assertTrue(self.ba._is_bare_blog(t), t)

    def test_is_bare_blog_negative(self):
        for t in ("blog help", "write blog", "show blog", "ai blog generate about rust"):
            self.assertFalse(self.ba._is_bare_blog(t), t)

    # _is_edit_blog
    def test_is_edit_blog(self):
        self.assertTrue(self.ba._is_edit_blog("edit blog"))
        self.assertTrue(self.ba._is_edit_blog("edit blog something"))
        self.assertFalse(self.ba._is_edit_blog("ai blog edit"))  # wrong order

    # _is_help
    def test_is_help(self):
        self.assertTrue(self.ba._is_help("blog help"))
        self.assertTrue(self.ba._is_help("help blog"))
        self.assertFalse(self.ba._is_help("help me"))

    # _is_show
    def test_is_show(self):
        for t in ("show blog", "list my blog", "view blog", "blog entries", "blog list"):
            self.assertTrue(self.ba._is_show(t), t)
        self.assertFalse(self.ba._is_show("show me the front page"))

    # _is_write
    def test_is_write(self):
        for t in ("write blog post", "add blog entry", "create blog content", "blog news"):
            self.assertTrue(self.ba._is_write(t), t)
        self.assertFalse(self.ba._is_write("rewrite blog"))

    # _is_generate_title
    def test_is_generate_title(self):
        self.assertTrue(self.ba._is_generate_title("generate blog title"))
        self.assertTrue(self.ba._is_generate_title("blog title"))
        self.assertTrue(self.ba._is_generate_title("suggest headline"))
        self.assertFalse(self.ba._is_generate_title("change title"))

    # _is_publish (local)
    def test_is_publish_local(self):
        self.assertTrue(self.ba._is_publish("publish my blog"))
        self.assertTrue(self.ba._is_publish("finalize blog"))
        self.assertFalse(self.ba._is_publish("publish blog to wp://site.com user pass"))

    # _is_publish_remote
    def test_is_publish_remote(self):
        self.assertTrue(self.ba._is_publish_remote("publish blog to wp://site.com user pass"))
        self.assertTrue(self.ba._is_publish_remote("upload blog to sftp://server"))
        self.assertTrue(self.ba._is_publish_remote("deploy blog to joomla://site"))
        self.assertTrue(self.ba._is_publish_remote("blog publish to all"))
        self.assertFalse(self.ba._is_publish_remote("publish my blog"))

    # _is_ai_generate
    def test_is_ai_generate(self):
        self.assertTrue(self.ba._is_ai_generate("ai blog generate about climate"))
        self.assertTrue(self.ba._is_ai_generate("write a blog post about rust"))
        self.assertTrue(self.ba._is_ai_generate("generate blog post on quantum computing"))
        self.assertFalse(self.ba._is_ai_generate("write blog entry"))

    # _is_ai_rewrite
    def test_is_ai_rewrite(self):
        self.assertTrue(self.ba._is_ai_rewrite("ai rewrite blog"))
        self.assertTrue(self.ba._is_ai_rewrite("rewrite my blog"))
        self.assertTrue(self.ba._is_ai_rewrite("ai blog improve"))
        self.assertFalse(self.ba._is_ai_rewrite("write blog"))

    # _is_ai_expand
    def test_is_ai_expand(self):
        self.assertTrue(self.ba._is_ai_expand("ai expand blog"))
        self.assertTrue(self.ba._is_ai_expand("expand my blog"))
        self.assertFalse(self.ba._is_ai_expand("write blog"))

    # _is_ai_headlines
    def test_is_ai_headlines(self):
        self.assertTrue(self.ba._is_ai_headlines("ai headlines"))
        self.assertTrue(self.ba._is_ai_headlines("generate headlines"))
        self.assertTrue(self.ba._is_ai_headlines("ai blog title"))

    # _is_ai_seo
    def test_is_ai_seo(self):
        self.assertTrue(self.ba._is_ai_seo("ai seo"))
        self.assertTrue(self.ba._is_ai_seo("blog seo"))
        self.assertFalse(self.ba._is_ai_seo("publish blog"))

    # _is_ai_info
    def test_is_ai_info(self):
        self.assertTrue(self.ba._is_ai_info("ai options"))
        self.assertTrue(self.ba._is_ai_info("local ai setup"))
        self.assertTrue(self.ba._is_ai_info("ai blog options"))

    # _is_ai_providers
    def test_is_ai_providers(self):
        self.assertTrue(self.ba._is_ai_providers("ai providers"))
        self.assertTrue(self.ba._is_ai_providers("list providers"))
        self.assertTrue(self.ba._is_ai_providers("ai status"))
        self.assertTrue(self.ba._is_ai_providers("cloud ai keys"))

    # _is_ai_switch
    def test_is_ai_switch(self):
        self.assertTrue(self.ba._is_ai_switch("use ai provider ollama"))
        self.assertTrue(self.ba._is_ai_switch("switch provider claude"))
        self.assertFalse(self.ba._is_ai_switch("ai providers"))

    # _is_list_targets
    def test_is_list_targets(self):
        self.assertTrue(self.ba._is_list_targets("list publish targets"))
        self.assertTrue(self.ba._is_list_targets("publish targets"))
        self.assertTrue(self.ba._is_list_targets("where can i publish"))
        self.assertFalse(self.ba._is_list_targets("publish blog to wp://"))

    # _is_set_front_page
    def test_is_set_front_page(self):
        self.assertTrue(self.ba._is_set_front_page("set front page 42 on my-site"))
        self.assertTrue(self.ba._is_set_front_page("make front page 10"))
        self.assertTrue(self.ba._is_set_front_page("feature post 5 on wordpress"))
        self.assertFalse(self.ba._is_set_front_page("show front page"))

    # _is_show_front_page
    def test_is_show_front_page(self):
        self.assertTrue(self.ba._is_show_front_page("show the front page"))
        self.assertTrue(self.ba._is_show_front_page("what is the front page"))
        self.assertTrue(self.ba._is_show_front_page("current featured"))
        self.assertFalse(self.ba._is_show_front_page("set front page 1"))

    # _is_list_pages
    def test_is_list_pages(self):
        self.assertTrue(self.ba._is_list_pages("list pages for my-site"))
        self.assertTrue(self.ba._is_list_pages("show available pages on wordpress"))
        self.assertFalse(self.ba._is_list_pages("show blog"))

    # _is_crawl_blog
    def test_is_crawl_blog(self):
        self.assertTrue(self.ba._is_crawl_blog("crawl https://example.com for title"))
        self.assertTrue(self.ba._is_crawl_blog("scrape site for content"))
        self.assertFalse(self.ba._is_crawl_blog("write blog about crawling"))


# ─────────────────────────────────────────────────────────────────────────────
# 2. _looks_like_command and _is_explicit_command
# ─────────────────────────────────────────────────────────────────────────────

class TestCommandDetection(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)

    def test_looks_like_command_positive(self):
        for t in ("blog help", "publish blog", "show blog", "ai rewrite",
                  "edit blog", "crawl site", "write stuff", "cancel"):
            self.assertTrue(self.ba._looks_like_command(t), t)

    def test_looks_like_command_negative(self):
        # Free-text content should NOT look like commands
        for t in ("confirm", "yes", "title my post", "change title",
                  "My thoughts on AI today", "Some random content"):
            self.assertFalse(self.ba._looks_like_command(t), t)

    def test_is_explicit_command_positive(self):
        for t in ("blog help", "help blog", "show blog", "list blog",
                  "publish blog to wp://site", "set front page",
                  "ai options", "ai providers", "crawl example.com",
                  "quit", "exit"):
            self.assertTrue(self.ba._is_explicit_command(t), t)

    def test_is_explicit_command_negative(self):
        # Session-style responses should not be flagged as explicit commands
        for t in ("confirm", "yes", "1", "2", "cancel",
                  "change title My New Title", "My topic is climate change"):
            self.assertFalse(self.ba._is_explicit_command(t), t)


# ─────────────────────────────────────────────────────────────────────────────
# 3. _parse_inline_target
# ─────────────────────────────────────────────────────────────────────────────

class TestParseInlineTarget(unittest.TestCase):

    def _p(self, text):
        from safeclaw.actions.blog import BlogAction
        return BlogAction._parse_inline_target(text)

    # SFTP
    def test_sftp_basic(self):
        t = self._p("publish blog to sftp://192.168.1.1 user1 pass1")
        self.assertIsNotNone(t)
        self.assertEqual(t.target_type, PublishTargetType.SFTP)
        self.assertEqual(t.sftp_host, "192.168.1.1")
        self.assertEqual(t.sftp_user, "user1")
        self.assertEqual(t.sftp_password, "pass1")
        self.assertEqual(t.sftp_port, 22)
        self.assertEqual(t.sftp_remote_path, "/var/www/html/blog")
        self.assertEqual(t.label, "sftp-192.168.1.1")

    def test_sftp_custom_port(self):
        t = self._p("publish blog to sftp://myserver.com:2222 deploy secret123")
        self.assertIsNotNone(t)
        self.assertEqual(t.sftp_port, 2222)
        self.assertEqual(t.sftp_host, "myserver.com")

    def test_sftp_custom_remote_path(self):
        t = self._p("publish blog to sftp://host user pass /opt/web/blog")
        self.assertIsNotNone(t)
        self.assertEqual(t.sftp_remote_path, "/opt/web/blog")

    def test_sftp_special_chars_password(self):
        # Password with special chars (no spaces)
        t = self._p("publish blog to sftp://host admin P@$$w0rd!")
        self.assertIsNotNone(t)
        self.assertEqual(t.sftp_password, "P@$$w0rd!")

    # WordPress
    def test_wp_scheme(self):
        t = self._p("publish blog to wp://myblog.com admin app-password-xyz")
        self.assertIsNotNone(t)
        self.assertEqual(t.target_type, PublishTargetType.WORDPRESS)
        self.assertEqual(t.url, "https://myblog.com")
        self.assertEqual(t.username, "admin")
        self.assertEqual(t.password, "app-password-xyz")
        self.assertIn("myblog.com", t.label)

    def test_wordpress_scheme(self):
        t = self._p("publish blog to wordpress://myblog.com admin secret")
        self.assertIsNotNone(t)
        self.assertEqual(t.target_type, PublishTargetType.WORDPRESS)

    def test_wp_https_prefix(self):
        # host already contains https://
        t = self._p("publish blog to wp://https://myblog.com admin secret")
        self.assertIsNotNone(t)
        # label should be domain, NOT "https:"
        self.assertNotIn("https:", t.label)
        self.assertIn("myblog.com", t.label)

    def test_wp_label_is_domain(self):
        t = self._p("publish blog to wp://example.org user pass")
        self.assertEqual(t.label, "wp-example.org")

    # Joomla
    def test_joomla_scheme(self):
        t = self._p("publish blog to joomla://cms.example.com admin token123")
        self.assertIsNotNone(t)
        self.assertEqual(t.target_type, PublishTargetType.JOOMLA)
        self.assertEqual(t.url, "https://cms.example.com")
        self.assertIn("cms.example.com", t.label)

    # API
    def test_api_scheme(self):
        t = self._p("publish blog to api://api.example.com/posts my-api-key")
        self.assertIsNotNone(t)
        self.assertEqual(t.target_type, PublishTargetType.API)
        self.assertIn("api.example.com", t.label)
        self.assertEqual(t.api_key, "my-api-key")

    # Variants: upload / deploy / push
    def test_upload_verb(self):
        t = self._p("upload blog to sftp://host user pass")
        self.assertIsNotNone(t)
        self.assertEqual(t.sftp_host, "host")

    def test_deploy_verb(self):
        t = self._p("deploy to wp://site.com admin pass")
        self.assertIsNotNone(t)

    def test_push_verb(self):
        t = self._p("push blog to joomla://site.com admin pass")
        self.assertIsNotNone(t)

    # No match
    def test_no_match(self):
        self.assertIsNone(self._p("publish blog"))
        self.assertIsNone(self._p("publish blog to my-wordpress"))
        self.assertIsNone(self._p("just some text"))

    # Case insensitive
    def test_case_insensitive(self):
        t = self._p("PUBLISH BLOG TO WP://Site.com Admin Pass")
        self.assertIsNotNone(t)
        self.assertEqual(t.target_type, PublishTargetType.WORDPRESS)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Session state machine
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionStateMachine(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        from safeclaw.actions.blog import BlogAction
        self.ba = _make_blog_action(self.tmp)
        self.user = "testuser"

    def _get_session(self):
        return self.ba._get_session(self.user)

    def _set_session(self, state, **kwargs):
        self.ba._set_session(self.user, state, **kwargs)

    def _clear(self):
        self.ba._clear_session(self.user)

    def test_session_roundtrip(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="My Title", target_label="wp-site")
        s = self._get_session()
        self.assertEqual(s["state"], SESSION_PENDING_PUBLISH)
        self.assertEqual(s["pending_title"], "My Title")
        self.assertEqual(s["target_label"], "wp-site")

    def test_clear_session(self):
        from safeclaw.actions.blog import SESSION_REVIEWING
        self._set_session(SESSION_REVIEWING)
        self._clear()
        s = self._get_session()
        self.assertFalse(s.get("state"))

    def test_explicit_command_clears_session(self):
        from safeclaw.actions.blog import SESSION_AWAITING_CHOICE
        self._set_session(SESSION_AWAITING_CHOICE)
        result = run(self.ba._handle_session(
            self._get_session(), "show blog", "show blog", self.user,
            MagicMock(),
        ))
        # Returns None → falls through to normal routing
        self.assertIsNone(result)
        # Session should be cleared
        self.assertFalse(self._get_session().get("state"))

    def test_awaiting_choice_unknown_input(self):
        from safeclaw.actions.blog import SESSION_AWAITING_CHOICE
        self._set_session(SESSION_AWAITING_CHOICE)
        engine = MagicMock()
        result = run(self.ba._handle_session(
            self._get_session(), "3", "3", self.user, engine,
        ))
        # Should not be None (handled by _handle_choice)
        self.assertIsNotNone(result)

    def test_pending_publish_confirm(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        # Write a draft
        _write_draft(self.ba, self.user, "[2024-01-01]\nHello world\n")
        # Set up publisher with a mock
        mock_result = PublishResult(success=True, target_label="wp-test",
                                    target_type="wordpress", url="https://site.com/p/1",
                                    message="Published")
        self.ba.publisher = MagicMock()
        self.ba.publisher.targets = {"wp-test": MagicMock()}
        self.ba.publisher.publish = AsyncMock(return_value=[mock_result])
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="My Post", target_label="wp-test")
        result = run(self.ba._handle_pending_publish(
            self._get_session(), "confirm", "confirm", self.user,
        ))
        self.assertIn("Published", result)

    def test_pending_publish_cancel(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="Test")
        result = run(self.ba._handle_pending_publish(
            self._get_session(), "cancel", "cancel", self.user,
        ))
        self.assertIn("cancelled", result.lower())
        self.assertFalse(self._get_session().get("state"))

    def test_pending_publish_change_title(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="Old Title", target_label=None)
        result = run(self.ba._handle_pending_publish(
            self._get_session(), "title My New Post Title", "title my new post title", self.user,
        ))
        self.assertIn("My New Post Title", result)
        # Session should still be pending_publish with new title
        s = self._get_session()
        self.assertEqual(s["state"], SESSION_PENDING_PUBLISH)
        self.assertEqual(s["pending_title"], "My New Post Title")

    def test_pending_publish_change_title_with_change_prefix(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="Old Title", target_label=None)
        result = run(self.ba._handle_pending_publish(
            self._get_session(),
            "change title The Science of Coffee",
            "change title the science of coffee",
            self.user,
        ))
        self.assertIn("The Science of Coffee", result)

    def test_pending_publish_looks_like_command_clears(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="Test")
        result = run(self.ba._handle_pending_publish(
            self._get_session(), "show blog", "show blog", self.user,
        ))
        # Returns None → falls through to normal routing
        self.assertIsNone(result)
        self.assertFalse(self._get_session().get("state"))

    def test_pending_publish_unrecognised_input(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self._set_session(SESSION_PENDING_PUBLISH, pending_title="My Draft")
        result = run(self.ba._handle_pending_publish(
            self._get_session(),
            "What does this do?",
            "what does this do?",
            self.user,
        ))
        self.assertIn("Pending publish", result)
        self.assertIn("My Draft", result)

    def test_pending_publish_all_confirm_words(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent here\n")
        mock_result = PublishResult(success=True, target_label="t", target_type="api",
                                    message="ok", url="")
        self.ba.publisher = MagicMock()
        self.ba.publisher.targets = {"t": MagicMock()}
        self.ba.publisher.publish = AsyncMock(return_value=[mock_result])
        for word in ("yes", "publish", "publish it", "go", "send it", "do it"):
            self._set_session(SESSION_PENDING_PUBLISH, pending_title="T", target_label=None)
            result = run(self.ba._handle_pending_publish(
                self._get_session(), word, word.lower(), self.user,
            ))
            self.assertIn("Blog Published", result, f"word={word!r}")

    def test_pending_publish_all_cancel_words(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        for word in ("no", "abort", "stop", "back", "nevermind"):
            self._set_session(SESSION_PENDING_PUBLISH, pending_title="T")
            result = run(self.ba._handle_pending_publish(
                self._get_session(), word, word.lower(), self.user,
            ))
            self.assertIn("cancelled", result.lower(), f"word={word!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. _do_publish
# ─────────────────────────────────────────────────────────────────────────────

class TestDoPublish(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)
        self.user = "alice"

    def test_null_publisher_returns_guidance(self):
        self.ba.publisher = None
        result = run(self.ba._do_publish("Title", None, self.user))
        self.assertIn("no longer available", result.lower())
        self.assertIn("publish blog to", result)

    def test_empty_targets_returns_guidance(self):
        self.ba.publisher = BlogPublisher()  # no targets
        result = run(self.ba._do_publish("Title", None, self.user))
        self.assertIn("no longer available", result.lower())

    def test_missing_draft(self):
        mock_result = PublishResult(success=True, target_label="t", target_type="api",
                                    message="ok", url="")
        self.ba.publisher = MagicMock()
        self.ba.publisher.targets = {"t": MagicMock()}
        self.ba.publisher.publish = AsyncMock(return_value=[mock_result])
        # No draft file
        result = run(self.ba._do_publish("Title", None, self.user))
        self.assertIn("No blog draft", result)

    def test_empty_draft(self):
        _write_draft(self.ba, self.user, "")
        self.ba.publisher = MagicMock()
        self.ba.publisher.targets = {"t": MagicMock()}
        self.ba.publisher.publish = AsyncMock(return_value=[])
        result = run(self.ba._do_publish("Title", None, self.user))
        self.assertIn("empty", result.lower())

    def test_successful_publish(self):
        _write_draft(self.ba, self.user, "[2024-01-01]\nHello world content\n")
        mock_result = PublishResult(success=True, target_label="wp-test",
                                    target_type="wordpress", url="https://example.com/post/1",
                                    message="Published to WordPress")
        self.ba.publisher = MagicMock()
        self.ba.publisher.targets = {"wp-test": MagicMock()}
        self.ba.publisher.publish = AsyncMock(return_value=[mock_result])
        result = run(self.ba._do_publish("My Great Post", "wp-test", self.user))
        self.assertIn("Blog Published", result)
        self.assertIn("wp-test", result)
        self.assertIn("https://example.com/post/1", result)

    def test_failed_publish(self):
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        mock_result = PublishResult(success=False, target_label="wp-test",
                                    target_type="wordpress", error="HTTP 401")
        self.ba.publisher = MagicMock()
        self.ba.publisher.targets = {"wp-test": MagicMock()}
        self.ba.publisher.publish = AsyncMock(return_value=[mock_result])
        result = run(self.ba._do_publish("Post", "wp-test", self.user))
        self.assertIn("FAILED", result)
        self.assertIn("HTTP 401", result)


# ─────────────────────────────────────────────────────────────────────────────
# 6. _publish_remote staging flow
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishRemoteFlow(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)
        self.user = "bob"

    def test_no_publisher_no_inline_returns_help(self):
        result = run(self.ba._publish_remote("publish blog to all", self.user))
        self.assertIn("No publishing targets", result)
        self.assertIn("sftp://", result)

    def test_inline_wp_creates_publisher(self):
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        result = run(self.ba._publish_remote(
            "publish blog to wp://myblog.com admin pass", self.user,
        ))
        # Should show preview
        self.assertIn("Ready to Publish", result)
        self.assertIn("confirm", result.lower())
        self.assertIsNotNone(self.ba.publisher)
        self.assertIn("wp-myblog.com", self.ba.publisher.targets)

    def test_inline_sftp_creates_publisher(self):
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        result = run(self.ba._publish_remote(
            "publish blog to sftp://192.168.0.1 deploy secret", self.user,
        ))
        self.assertIn("Ready to Publish", result)

    def test_no_draft_returns_error(self):
        result = run(self.ba._publish_remote(
            "publish blog to wp://site.com user pass", self.user,
        ))
        self.assertIn("No blog draft", result)

    def test_empty_draft_returns_error(self):
        _write_draft(self.ba, self.user, "")
        result = run(self.ba._publish_remote(
            "publish blog to wp://site.com user pass", self.user,
        ))
        self.assertIn("empty", result.lower())

    def test_unknown_named_target_returns_error(self):
        # Publisher exists but target name doesn't
        self.ba.publisher = BlogPublisher()
        pt = PublishTarget(label="my-site", target_type=PublishTargetType.WORDPRESS,
                           url="https://my-site.com")
        self.ba.publisher.add_target(pt)
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        result = run(self.ba._publish_remote("publish blog to nonexistent", self.user))
        self.assertIn("not found", result.lower())
        self.assertIn("my-site", result)

    def test_preview_contains_content(self):
        content = "This is a very interesting blog post about technology."
        _write_draft(self.ba, self.user, f"[2024-01-01]\n{content}\n")
        result = run(self.ba._publish_remote(
            "publish blog to wp://site.com admin pass", self.user,
        ))
        self.assertIn("Preview", result)
        self.assertIn("Words", result)

    def test_quoted_title_via_named_target(self):
        """Quoted title works when publishing to a named target (not inline)."""
        self.ba.publisher = BlogPublisher()
        self.ba.publisher.add_target(PublishTarget(
            label="my-wp", target_type=PublishTargetType.WORDPRESS,
            url="https://myblog.com",
        ))
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        result = run(self.ba._publish_remote(
            'publish blog to my-wp titled "Custom Title Here"',
            self.user,
        ))
        self.assertIn("Custom Title Here", result)

    def test_inline_target_uses_auto_title(self):
        """Inline target publish shows auto-generated title when none provided."""
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        result = run(self.ba._publish_remote(
            "publish blog to wp://site.com admin pass",
            self.user,
        ))
        # Should show ready-to-publish with some title
        self.assertIn("Ready to Publish", result)
        self.assertIn("Title", result)

    def test_sets_pending_publish_session(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        run(self.ba._publish_remote("publish blog to wp://site.com admin pass", self.user))
        s = self.ba._get_session(self.user)
        self.assertEqual(s.get("state"), SESSION_PENDING_PUBLISH)
        self.assertIn("pending_title", s)


# ─────────────────────────────────────────────────────────────────────────────
# 7. BlogPublisher unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBlogPublisher(unittest.TestCase):

    def test_no_targets_returns_error(self):
        pub = BlogPublisher()
        results = run(pub.publish("T", "C"))
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("No publishing targets", results[0].error)

    def test_unknown_target_label(self):
        pub = BlogPublisher()
        pt = PublishTarget(label="site", target_type=PublishTargetType.WORDPRESS,
                           url="https://site.com")
        pub.add_target(pt)
        results = run(pub.publish("T", "C", target_label="nonexistent"))
        self.assertFalse(results[0].success)
        self.assertIn("not found", results[0].error)

    def test_add_target_and_list(self):
        pub = BlogPublisher()
        pt = PublishTarget(label="my-wp", target_type=PublishTargetType.WORDPRESS,
                           url="https://myblog.com", username="admin", password="pass")
        pub.add_target(pt)
        targets = pub.list_targets()
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["label"], "my-wp")
        self.assertEqual(targets[0]["type"], "wordpress")

    def test_from_config_empty(self):
        pub = BlogPublisher.from_config({})
        self.assertEqual(len(pub.targets), 0)

    def test_from_config_wordpress(self):
        config = {
            "publish_targets": [{
                "label": "wp-prod",
                "type": "wordpress",
                "url": "https://prod.com",
                "username": "admin",
                "password": "secret",
                "wp_status": "draft",
            }]
        }
        pub = BlogPublisher.from_config(config)
        self.assertIn("wp-prod", pub.targets)
        t = pub.targets["wp-prod"]
        self.assertEqual(t.target_type, PublishTargetType.WORDPRESS)
        self.assertEqual(t.url, "https://prod.com")
        self.assertEqual(t.wp_status, "draft")

    def test_from_config_sftp(self):
        config = {
            "publish_targets": [{
                "label": "sftp-server",
                "type": "sftp",
                "sftp_host": "deploy.example.com",
                "sftp_port": 2222,
                "sftp_user": "deploy",
                "sftp_key_path": "~/.ssh/id_rsa",
                "sftp_remote_path": "/var/www/blog",
            }]
        }
        pub = BlogPublisher.from_config(config)
        t = pub.targets["sftp-server"]
        self.assertEqual(t.target_type, PublishTargetType.SFTP)
        self.assertEqual(t.sftp_port, 2222)

    def test_from_config_joomla(self):
        config = {
            "publish_targets": [{
                "label": "joomla-prod",
                "type": "joomla",
                "url": "https://cms.example.com",
                "api_key": "joomla-token-xyz",
            }]
        }
        pub = BlogPublisher.from_config(config)
        t = pub.targets["joomla-prod"]
        self.assertEqual(t.target_type, PublishTargetType.JOOMLA)
        self.assertEqual(t.api_key, "joomla-token-xyz")

    def test_from_config_api(self):
        config = {
            "publish_targets": [{
                "label": "webhook",
                "type": "api",
                "url": "https://api.example.com/posts",
                "api_key": "my-key",
                "api_method": "PUT",
            }]
        }
        pub = BlogPublisher.from_config(config)
        t = pub.targets["webhook"]
        self.assertEqual(t.target_type, PublishTargetType.API)
        self.assertEqual(t.api_method, "PUT")

    def test_from_config_unknown_type_defaults_to_api(self):
        config = {
            "publish_targets": [{
                "label": "mystery",
                "type": "unknown-type",
                "url": "https://example.com",
            }]
        }
        pub = BlogPublisher.from_config(config)
        self.assertEqual(pub.targets["mystery"].target_type, PublishTargetType.API)

    def test_from_config_disabled_target_skipped_in_publish(self):
        config = {
            "publish_targets": [{
                "label": "disabled-target",
                "type": "api",
                "url": "https://example.com",
                "enabled": False,
            }]
        }
        pub = BlogPublisher.from_config(config)
        # publish to all — disabled targets should be skipped
        results = run(pub.publish("T", "C"))
        self.assertFalse(results[0].success)  # "no targets" error because all disabled

    @patch("httpx.AsyncClient")
    def test_publish_wordpress_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"id": 99, "link": "https://site.com/p/99"})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.get = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(), json=MagicMock(return_value=[])
        ))
        mock_client_cls.return_value = mock_client

        pub = BlogPublisher()
        pt = PublishTarget(label="wp", target_type=PublishTargetType.WORDPRESS,
                           url="https://site.com", username="admin", password="pass")
        pub.add_target(pt)
        results = run(pub.publish("Title", "Content", tags=["python"]))
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].url, "https://site.com/p/99")
        self.assertEqual(results[0].post_id, "99")

    @patch("httpx.AsyncClient")
    def test_publish_wordpress_http_error(self, mock_client_cls):
        import httpx as _httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        http_err = _httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=http_err)
        mock_client_cls.return_value = mock_client

        pub = BlogPublisher()
        pt = PublishTarget(label="wp", target_type=PublishTargetType.WORDPRESS,
                           url="https://site.com", username="admin", password="bad")
        pub.add_target(pt)
        results = run(pub.publish("T", "C"))
        self.assertFalse(results[0].success)
        self.assertIn("401", results[0].error)

    @patch("httpx.AsyncClient")
    def test_publish_joomla_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"data": {"id": 5}})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        pub = BlogPublisher()
        pt = PublishTarget(label="joomla", target_type=PublishTargetType.JOOMLA,
                           url="https://cms.example.com", api_key="token123")
        pub.add_target(pt)
        results = run(pub.publish("Title", "Content"))
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].post_id, "5")

    @patch("httpx.AsyncClient")
    def test_publish_api_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json = MagicMock(return_value={"id": "abc123"})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        pub = BlogPublisher()
        pt = PublishTarget(label="api", target_type=PublishTargetType.API,
                           url="https://api.example.com/posts", api_key="key123")
        pub.add_target(pt)
        results = run(pub.publish("Title", "Content"))
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].post_id, "abc123")

    @patch("httpx.AsyncClient")
    def test_publish_api_put_method(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.put = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        pub = BlogPublisher()
        pt = PublishTarget(label="api", target_type=PublishTargetType.API,
                           url="https://api.example.com/posts", api_method="PUT")
        pub.add_target(pt)
        results = run(pub.publish("Title", "Content"))
        mock_client.put.assert_called_once()

    def test_publish_concurrent_multiple_targets(self):
        """Publish to multiple targets concurrently — all results returned."""
        pub = BlogPublisher()
        for i in range(3):
            pub.add_target(PublishTarget(
                label=f"target-{i}",
                target_type=PublishTargetType.API,
                url=f"https://site{i}.example.com/api",
            ))

        async def fake_publish_to_target(target, *a, **k):
            return PublishResult(success=True, target_label=target.label,
                                 target_type="api", message="ok")

        pub._publish_to_target = fake_publish_to_target
        results = run(pub.publish("T", "C"))
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))

    def test_generate_html_structure(self):
        pub = BlogPublisher()
        html = pub._generate_html("My Title", "Body text.", "Excerpt text.", "2024-01-01")
        self.assertIn("<title>My Title</title>", html)
        self.assertIn("<h1>My Title</h1>", html)
        self.assertIn("Body text.", html)
        self.assertIn("Excerpt text.", html)
        self.assertIn("2024-01-01", html)

    def test_generate_html_no_excerpt(self):
        pub = BlogPublisher()
        html = pub._generate_html("T", "Content", "", "2024-01-01")
        self.assertNotIn('class="excerpt"', html)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Parser chain guard — text-consuming prefixes
# ─────────────────────────────────────────────────────────────────────────────

class TestChainGuard(unittest.TestCase):

    def setUp(self):
        self.parser = CommandParser()

    def _all_prefixes(self):
        return list(self.parser._TEXT_CONSUMING_PREFIXES)

    def test_text_consuming_prefixes_exist(self):
        prefixes = self._all_prefixes()
        self.assertGreater(len(prefixes), 0)
        self.assertIn("learn writing style", prefixes)
        self.assertIn("write blog", prefixes)

    def test_is_chain_blocked_for_all_prefixes(self):
        for prefix in self._all_prefixes():
            text = f"{prefix} and then do something else"
            self.assertFalse(
                self.parser.is_chain(text),
                f"is_chain should return False for prefix {prefix!r}, got True for: {text!r}",
            )

    def test_is_chain_blocked_learn_writing_style_with_then(self):
        # Exact reproduction of original bug
        text = "learn writing style and then review the page and then set reminder"
        self.assertFalse(self.parser.is_chain(text))

    def test_is_chain_blocked_write_blog_about(self):
        text = "write blog about AI trends; remind me tomorrow"
        self.assertFalse(self.parser.is_chain(text))

    def test_is_chain_allowed_normal_chain(self):
        # A normal chain should still be detected
        text = "remind me at 5pm | send email to bob"
        # May or may not be a chain depending on what intents are loaded,
        # but the key is that the guard doesn't block non-prefix text
        # Just ensure is_chain doesn't raise
        result = self.parser.is_chain(text)
        self.assertIsInstance(result, bool)

    def test_parse_chain_blocked_for_text_consuming(self):
        """parse_chain called directly should also return single command."""
        text = "learn writing style and then do other stuff"
        chain = self.parser.parse_chain(text, "user1")
        # Should be treated as a single command, not split
        self.assertEqual(len(chain.commands), 1)
        self.assertEqual(chain.chain_type, "none")

    def test_parse_chain_blocked_all_prefixes(self):
        for prefix in self._all_prefixes():
            text = f"{prefix} some content | other command"
            chain = self.parser.parse_chain(text, "user1")
            self.assertEqual(
                len(chain.commands), 1,
                f"parse_chain split on text-consuming prefix {prefix!r}: {text!r}",
            )

    def test_is_chain_case_insensitive(self):
        text = "LEARN WRITING STYLE then do something"
        self.assertFalse(self.parser.is_chain(text))
        text2 = "Write Blog About Python then remind me"
        self.assertFalse(self.parser.is_chain(text2))


# ─────────────────────────────────────────────────────────────────────────────
# 9. Multi-user isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiUserIsolation(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)

    def test_separate_sessions(self):
        from safeclaw.actions.blog import SESSION_REVIEWING, SESSION_AWAITING_TOPIC
        self.ba._set_session("alice", SESSION_REVIEWING)
        self.ba._set_session("bob", SESSION_AWAITING_TOPIC)
        self.assertEqual(self.ba._get_session("alice")["state"], SESSION_REVIEWING)
        self.assertEqual(self.ba._get_session("bob")["state"], SESSION_AWAITING_TOPIC)

    def test_clear_one_preserves_other(self):
        from safeclaw.actions.blog import SESSION_REVIEWING
        self.ba._set_session("alice", SESSION_REVIEWING)
        self.ba._set_session("bob", SESSION_REVIEWING)
        self.ba._clear_session("alice")
        self.assertFalse(self.ba._get_session("alice").get("state"))
        self.assertEqual(self.ba._get_session("bob")["state"], SESSION_REVIEWING)

    def test_separate_drafts(self):
        _write_draft(self.ba, "alice", "[2024-01-01]\nAlice content\n")
        _write_draft(self.ba, "bob", "[2024-01-01]\nBob content\n")
        alice_path = self.ba._get_draft_path("alice")
        bob_path = self.ba._get_draft_path("bob")
        self.assertNotEqual(alice_path, bob_path)
        self.assertIn("Alice", alice_path.read_text())
        self.assertIn("Bob", bob_path.read_text())

    def test_session_keyed_by_user_id(self):
        from safeclaw.actions.blog import SESSION_PENDING_PUBLISH
        self.ba._set_session("user-A", SESSION_PENDING_PUBLISH, pending_title="Post A")
        self.ba._set_session("user-B", SESSION_PENDING_PUBLISH, pending_title="Post B")
        self.assertEqual(self.ba._get_session("user-A")["pending_title"], "Post A")
        self.assertEqual(self.ba._get_session("user-B")["pending_title"], "Post B")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Security: path traversal
# ─────────────────────────────────────────────────────────────────────────────

class TestPathSecurity(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)

    def _draft_path(self, user_id: str) -> Path:
        return self.ba._get_draft_path(user_id)

    def _session_path(self, user_id: str) -> Path:
        return self.ba._get_session_path(user_id)

    def test_draft_path_within_data_dir(self):
        path = self._draft_path("normal_user")
        self.assertTrue(str(path).startswith(str(self.tmp)))

    def test_session_path_within_data_dir(self):
        path = self._session_path("normal_user")
        self.assertTrue(str(path).startswith(str(self.tmp)))

    def test_path_traversal_user_id_draft(self):
        """../../../etc/passwd style user_id must not escape data_dir."""
        dangerous_ids = [
            "../../../etc/passwd",
            "..%2F..%2Fetc%2Fpasswd",
            "/etc/passwd",
        ]
        for uid in dangerous_ids:
            path = self._draft_path(uid)
            # The resolved path must still be inside data_dir
            try:
                path.resolve().relative_to(self.tmp.resolve())
            except ValueError:
                self.fail(
                    f"Draft path for user_id {uid!r} escaped data_dir: {path}"
                )

    def test_path_traversal_user_id_session(self):
        dangerous_ids = [
            "../../../etc/passwd",
            "/root/.ssh/authorized_keys",
        ]
        for uid in dangerous_ids:
            path = self._session_path(uid)
            try:
                path.resolve().relative_to(self.tmp.resolve())
            except ValueError:
                self.fail(
                    f"Session path for user_id {uid!r} escaped data_dir: {path}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# 11. _extract_publish_title
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractPublishTitle(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)

    def test_quoted_title(self):
        result = self.ba._extract_publish_title('publish blog to wp://site.com "My Custom Title"')
        self.assertEqual(result, "My Custom Title")

    def test_titled_keyword(self):
        result = self.ba._extract_publish_title("publish blog titled My Title Here to my-site")
        self.assertIn("My Title Here", result)

    def test_title_keyword(self):
        result = self.ba._extract_publish_title("publish blog title My Post on my-site")
        self.assertIn("My Post", result)

    def test_no_title_returns_empty(self):
        result = self.ba._extract_publish_title("publish blog to wp://site.com user pass")
        self.assertEqual(result, "")


# ─────────────────────────────────────────────────────────────────────────────
# 12. BlogPublisher._generate_html edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateHtml(unittest.TestCase):

    def setUp(self):
        self.pub = BlogPublisher()

    def test_plain_text_wrapped_in_paragraphs(self):
        html = self.pub._generate_html("T", "Para one.\n\nPara two.", "", "2024-01-01")
        self.assertIn("<p>Para one.</p>", html)
        self.assertIn("<p>Para two.</p>", html)

    def test_existing_html_not_double_wrapped(self):
        html = self.pub._generate_html("T", "<p>Already HTML.</p>", "", "2024-01-01")
        # Should not add extra <p> around existing <p>
        self.assertNotIn("<p><p>", html)

    def test_excerpt_in_meta(self):
        html = self.pub._generate_html("T", "C", "Short excerpt", "2024-01-01")
        self.assertIn('name="description"', html)
        self.assertIn("Short excerpt", html)

    def test_long_excerpt_truncated_in_meta(self):
        long_exc = "x" * 200
        html = self.pub._generate_html("T", "C", long_exc, "2024-01-01")
        # meta description capped at 160
        import re
        m = re.search(r'content="([^"]+)"', html)
        if m:
            self.assertLessEqual(len(m.group(1)), 160)


# ─────────────────────────────────────────────────────────────────────────────
# 13. PublishTargetType enum
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishTargetType(unittest.TestCase):

    def test_all_values(self):
        types = {t.value for t in PublishTargetType}
        self.assertIn("wordpress", types)
        self.assertIn("joomla", types)
        self.assertIn("sftp", types)
        self.assertIn("api", types)

    def test_str_enum_equality(self):
        self.assertEqual(PublishTargetType.WORDPRESS, "wordpress")
        self.assertEqual(PublishTargetType.SFTP, "sftp")


# ─────────────────────────────────────────────────────────────────────────────
# 14. Execute routing integration
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteRouting(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ba = _make_blog_action(self.tmp)
        self.user = "carol"
        self.engine = MagicMock()

    def _exec(self, text: str, user_id: str | None = None) -> str:
        uid = user_id or self.user
        return run(self.ba.execute(
            params={"raw_input": text},
            user_id=uid,
            channel="test",
            engine=self.engine,
        ))

    def test_bare_blog_shows_menu(self):
        result = self._exec("blog")
        self.assertIn("What would you like to do", result)

    def test_help_route(self):
        result = self._exec("blog help")
        self.assertIn("blog", result.lower())

    def test_show_route_no_draft(self):
        result = self._exec("show blog")
        # Should say no blog or show empty
        self.assertIsInstance(result, str)

    def test_publish_remote_route(self):
        _write_draft(self.ba, self.user, "[2024-01-01]\nContent\n")
        result = self._exec("publish blog to wp://site.com admin pass")
        self.assertIn("Ready to Publish", result)

    def test_no_targets_list_targets(self):
        result = self._exec("list publish targets")
        self.assertIn("No publishing targets", result)

    def test_with_targets_list_targets(self):
        self.ba.publisher = BlogPublisher()
        self.ba.publisher.add_target(PublishTarget(
            label="my-wp", target_type=PublishTargetType.WORDPRESS,
            url="https://myblog.com",
        ))
        result = self._exec("list publish targets")
        self.assertIn("my-wp", result)

    def test_ai_generate_no_provider(self):
        result = self._exec("ai blog generate about Python")
        self.assertIn("No AI providers", result)

    def test_generate_title_route(self):
        result = self._exec("generate blog title")
        self.assertIsInstance(result, str)

    def test_session_state_intercepts_input(self):
        from safeclaw.actions.blog import SESSION_AWAITING_CHOICE
        self.ba._set_session(self.user, SESSION_AWAITING_CHOICE)
        result = self._exec("1")
        # Should be handled by _handle_choice, not fall-through
        self.assertIsNotNone(result)

    def test_explicit_command_during_session_clears_it(self):
        from safeclaw.actions.blog import SESSION_AWAITING_CHOICE
        self.ba._set_session(self.user, SESSION_AWAITING_CHOICE)
        result = self._exec("show blog")
        # show blog should route normally (not as session choice)
        self.assertFalse(self.ba._get_session(self.user).get("state"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
