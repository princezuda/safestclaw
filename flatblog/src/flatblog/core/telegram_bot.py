"""Telegram bot — manage flatblog from your phone.

Conversation flows
──────────────────
/start / main menu  →  inline keyboard with all actions
✍️  Write post      →  ask topic → AI generates → preview → [Publish | Draft | Discard]
📝  New draft       →  ask title → create draft → confirm
📋  List drafts     →  inline list → tap to publish/discard
🚀  Publish         →  build + push to all targets
🔨  Build           →  build only
📊  Status          →  config overview
📷  Photo message   →  ask which post → attach as cover
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("flatblog.bot")

# ── Telegram API helpers ───────────────────────────────────────────────────────

class TG:
    def __init__(self, token: str, client: httpx.AsyncClient):
        self._base = f"https://api.telegram.org/bot{token}"
        self._file = f"https://api.telegram.org/file/bot{token}"
        self._c = client

    async def _post(self, method: str, **kw) -> dict:
        r = await self._c.post(f"{self._base}/{method}", json=kw, timeout=30)
        return r.json()

    async def _post_form(self, method: str, data: dict, files: dict | None = None) -> dict:
        r = await self._c.post(
            f"{self._base}/{method}", data=data, files=files or {}, timeout=60
        )
        return r.json()

    async def send(self, chat_id: int | str, text: str,
                   reply_markup: dict | None = None, parse_mode: str = "HTML") -> dict:
        kw: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            kw["reply_markup"] = reply_markup
        return await self._post("sendMessage", **kw)

    async def edit(self, chat_id: int | str, message_id: int, text: str,
                   reply_markup: dict | None = None, parse_mode: str = "HTML") -> dict:
        kw: dict[str, Any] = {
            "chat_id": chat_id, "message_id": message_id,
            "text": text, "parse_mode": parse_mode,
        }
        if reply_markup:
            kw["reply_markup"] = reply_markup
        return await self._post("editMessageText", **kw)

    async def answer_callback(self, callback_query_id: str, text: str = "") -> None:
        await self._post("answerCallbackQuery",
                         callback_query_id=callback_query_id, text=text)

    async def send_photo(self, chat_id: int | str, photo: bytes, filename: str,
                         caption: str = "", reply_markup: dict | None = None) -> dict:
        data: dict[str, Any] = {
            "chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        mime, _ = mimetypes.guess_type(filename)
        return await self._post_form(
            "sendPhoto", data=data,
            files={"photo": (filename, photo, mime or "image/jpeg")},
        )

    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Returns (bytes, extension)."""
        info = await self._post("getFile", file_id=file_id)
        file_path = info.get("result", {}).get("file_path", "")
        r = await self._c.get(f"{self._file}/{file_path}", timeout=60)
        ext = Path(file_path).suffix or ".jpg"
        return r.content, ext

    async def get_updates(self, offset: int, timeout: int = 30) -> list[dict]:
        r = await self._c.get(
            f"{self._base}/getUpdates",
            params={"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]},
            timeout=timeout + 5,
        )
        data = r.json()
        return data.get("result", []) if data.get("ok") else []


# ── Keyboard builders ──────────────────────────────────────────────────────────

def _inline(*rows: list[tuple[str, str]]) -> dict:
    """Build an InlineKeyboardMarkup from rows of (label, callback_data) tuples."""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


MAIN_MENU = _inline(
    [("✍️  Write post", "write"), ("📝  New draft", "new")],
    [("📋  List drafts", "drafts"), ("🚀  Publish", "publish")],
    [("🔨  Build", "build"), ("📊  Status", "status")],
    [("🎨  Style guide", "style")],
)

STYLE_MENU = _inline(
    [("📖 Show guide", "style_show")],
    [("✏️  Write new guide", "style_write"), ("📥  Import URL", "style_import_url")],
    [("🔄  Reset to built-in", "style_reset"), ("🗑️  Clear", "style_clear")],
    [("« Back", "menu")],
)


# ── Conversation state ─────────────────────────────────────────────────────────

@dataclass
class ChatState:
    step: str = "idle"       # current conversation step
    data: dict = field(default_factory=dict)   # scratchpad for multi-step flows


# ── Bot core ───────────────────────────────────────────────────────────────────

class FlatblogBot:
    def __init__(self, token: str, cfg: dict, cfg_path: Path):
        self.token    = token
        self.cfg      = cfg
        self.cfg_path = cfg_path
        self.root     = cfg_path.parent
        self._state: dict[int, ChatState] = {}

    def _st(self, chat_id: int) -> ChatState:
        if chat_id not in self._state:
            self._state[chat_id] = ChatState()
        return self._state[chat_id]

    # ── Dispatch ───────────────────────────────────────────────────────────────

    async def handle_update(self, update: dict, tg: TG) -> None:
        if "callback_query" in update:
            await self._on_callback(update["callback_query"], tg)
        elif "message" in update:
            await self._on_message(update["message"], tg)

    async def _on_callback(self, cb: dict, tg: TG) -> None:
        chat_id = cb["message"]["chat"]["id"]
        msg_id  = cb["message"]["message_id"]
        data    = cb.get("data", "")
        await tg.answer_callback(cb["id"])
        st = self._st(chat_id)

        # Draft selection callbacks: "pub_SLUG" or "dis_SLUG"
        if data.startswith("pub_"):
            await self._do_publish_draft(chat_id, msg_id, data[4:], tg)
            return
        if data.startswith("dis_"):
            await self._do_discard_draft(chat_id, msg_id, data[4:], tg)
            return
        # Cover image target selection: "cover_SLUG"
        if data.startswith("cover_"):
            await self._do_attach_cover(chat_id, msg_id, data[6:], tg)
            return

        # Style guide callbacks
        if data == "style_show":
            await self._style_show(chat_id, msg_id, tg)
            return
        if data == "style_write":
            st.step = "wait_style_text"
            st.data["style_msg_id"] = msg_id
            await tg.edit(
                chat_id, msg_id,
                "✏️  <b>Send your style guide as a message.</b>\n\n"
                "<i>Paste or type your full guide. Send /cancel to abort.</i>",
                reply_markup=None,
            )
            return
        if data == "style_import_url":
            st.step = "wait_style_url"
            await tg.edit(
                chat_id, msg_id,
                "📥  <b>Send the URL to download the style guide from.</b>",
                reply_markup=None,
            )
            return
        if data == "style_reset":
            from flatblog.core.style import reset_style
            reset_style(self.root)
            await tg.edit(chat_id, msg_id, "🔄  Style guide reset to built-in SafeClaw guide.", reply_markup=None)
            await tg.send(chat_id, "Anything else?", reply_markup=MAIN_MENU)
            return
        if data == "style_clear":
            from flatblog.core.style import style_path
            sp = style_path(self.root)
            if sp.exists():
                sp.unlink()
            await tg.edit(chat_id, msg_id, "🗑️  Style guide cleared. AI will use built-in defaults.", reply_markup=None)
            await tg.send(chat_id, "Anything else?", reply_markup=MAIN_MENU)
            return

        # After AI write preview: publish / draft / discard
        if data == "write_publish" and st.step == "write_preview":
            await self._do_write_confirm(chat_id, msg_id, publish=True, tg=tg)
            return
        if data == "write_draft" and st.step == "write_preview":
            await self._do_write_confirm(chat_id, msg_id, publish=False, tg=tg)
            return
        if data == "write_discard" and st.step == "write_preview":
            st.step = "idle"
            st.data.clear()
            await tg.edit(chat_id, msg_id, "Discarded.", reply_markup=None)
            return

        # Main menu actions
        await self._dispatch_action(chat_id, msg_id, data, tg, is_edit=True)

    async def _on_message(self, msg: dict, tg: TG) -> None:
        chat_id = msg["chat"]["id"]
        text    = msg.get("text", "").strip()
        photo   = msg.get("photo")
        st      = self._st(chat_id)

        # Photo sent → start cover-image flow
        if photo:
            await self._on_photo(chat_id, photo, tg)
            return

        if text in ("/start", "/menu"):
            st.step = "idle"
            st.data.clear()
            await tg.send(
                chat_id,
                "<b>flatblog</b> — what would you like to do?",
                reply_markup=MAIN_MENU,
            )
            return

        # Multi-step flows waiting for text input
        if st.step == "wait_topic":
            await self._do_write_topic(chat_id, text, tg)
            return
        if st.step == "wait_title":
            await self._do_new_title(chat_id, text, tg)
            return
        if st.step == "wait_style_text":
            await self._do_save_style_text(chat_id, text, tg)
            return
        if st.step == "wait_style_url":
            await self._do_import_style_url(chat_id, text, tg)
            return

        # Unknown text — show menu
        await tg.send(
            chat_id,
            "Use the menu below or send /start anytime.",
            reply_markup=MAIN_MENU,
        )

    # ── Actions ────────────────────────────────────────────────────────────────

    async def _dispatch_action(
        self, chat_id: int, msg_id: int | None, action: str, tg: TG, *, is_edit: bool = False
    ) -> None:
        st = self._st(chat_id)

        async def _reply(text: str, markup: dict | None = None) -> None:
            if is_edit and msg_id:
                await tg.edit(chat_id, msg_id, text, reply_markup=markup)
            else:
                await tg.send(chat_id, text, reply_markup=markup)

        if action == "write":
            st.step = "wait_topic"
            st.data.clear()
            await _reply("✍️  <b>What topic should I write about?</b>\n\n<i>Type it below…</i>")

        elif action == "new":
            st.step = "wait_title"
            st.data.clear()
            await _reply("📝  <b>Post title?</b>\n\n<i>Type it below…</i>")

        elif action == "drafts":
            await self._show_drafts(chat_id, msg_id, tg, is_edit=is_edit)

        elif action == "publish":
            await _reply("🚀  Publishing…")
            lines = await self._run_publish()
            await tg.send(chat_id, "<pre>" + "\n".join(lines) + "</pre>",
                          reply_markup=MAIN_MENU)

        elif action == "build":
            msg = await _reply("🔨  Building…")
            count = await self._run_build()
            await tg.send(chat_id, f"🔨  Built {count} posts.", reply_markup=MAIN_MENU)

        elif action == "status":
            text = self._status_text()
            await _reply(text, markup=MAIN_MENU)

        elif action == "style":
            await _reply("🎨  <b>Style guide</b>", markup=STYLE_MENU)

        else:
            await _reply(
                "<b>flatblog</b> — what would you like to do?",
                markup=MAIN_MENU,
            )

    # ── Write post ─────────────────────────────────────────────────────────────

    async def _do_write_topic(self, chat_id: int, topic: str, tg: TG) -> None:
        st = self._st(chat_id)
        st.step = "writing"
        thinking = await tg.send(chat_id, f"✍️  Writing <b>{topic}</b>…\n<i>(this takes a moment)</i>")

        try:
            post = await self._ai_write(topic)
        except Exception as e:
            st.step = "idle"
            await tg.send(chat_id, f"❌  AI error: {e}", reply_markup=MAIN_MENU)
            return

        st.step = "write_preview"
        st.data["post_path"] = str(post.path)
        st.data["post_slug"] = post.url_slug

        preview = (post.description or post.body[:300]).strip()
        if len(post.body) > 300:
            preview += "…"

        markup = _inline(
            [("🚀 Publish now", "write_publish"), ("💾 Save as draft", "write_draft")],
            [("🗑️  Discard", "write_discard")],
        )
        await tg.send(
            chat_id,
            f"<b>{post.title}</b>\n\n{preview}",
            reply_markup=markup,
        )

    async def _do_write_confirm(
        self, chat_id: int, msg_id: int, *, publish: bool, tg: TG
    ) -> None:
        from flatblog.core.post import parse_post, set_draft_flag

        st = self._st(chat_id)
        path = Path(st.data.get("post_path", ""))
        slug = st.data.get("post_slug", "")
        st.step = "idle"
        st.data.clear()

        if not path.exists():
            await tg.edit(chat_id, msg_id, "❌  Post file not found.", reply_markup=None)
            return

        if publish:
            set_draft_flag(path, draft=False)
            count = await self._run_build()
            lines = await self._run_publish()
            summary = "\n".join(lines)
            await tg.edit(chat_id, msg_id, f"🚀  Published!\n\n<pre>{summary}</pre>",
                          reply_markup=None)
        else:
            await tg.edit(chat_id, msg_id, f"💾  Saved as draft: <b>{slug}</b>",
                          reply_markup=None)

        await tg.send(chat_id, "Anything else?", reply_markup=MAIN_MENU)

    # ── New blank draft ────────────────────────────────────────────────────────

    async def _do_new_title(self, chat_id: int, title: str, tg: TG) -> None:
        from flatblog.core.post import write_post

        st = self._st(chat_id)
        st.step = "idle"
        posts_dir = self.root / "posts"
        from flatblog.core.post import _slugify
        slug = _slugify(title)
        from datetime import datetime
        filename = f"{datetime.today().date()}-{slug}.md"
        path = posts_dir / filename
        write_post(path, title, body="", draft=True)

        await tg.send(
            chat_id,
            f"📝  Draft created: <b>{title}</b>\n<i>{filename}</i>",
            reply_markup=MAIN_MENU,
        )

    # ── Draft management ───────────────────────────────────────────────────────

    async def _show_drafts(
        self, chat_id: int, msg_id: int | None, tg: TG, *, is_edit: bool
    ) -> None:
        from flatblog.core.post import load_all_posts

        posts_dir = self.root / "posts"
        draft_posts = [p for p in load_all_posts(posts_dir, include_drafts=True) if p.draft]

        if not draft_posts:
            text = "📋  No drafts right now."
            if is_edit and msg_id:
                await tg.edit(chat_id, msg_id, text, reply_markup=MAIN_MENU)
            else:
                await tg.send(chat_id, text, reply_markup=MAIN_MENU)
            return

        text = "📋  <b>Drafts</b> — tap to publish or discard:\n\n" + "\n".join(
            f"  • <b>{p.title}</b>  <i>{p.date}</i>" for p in draft_posts
        )
        rows = [
            [
                (f"🚀 {p.title[:22]}", f"pub_{p.url_slug}"),
                (f"🗑️", f"dis_{p.url_slug}"),
            ]
            for p in draft_posts[:8]  # cap at 8
        ]
        rows.append([("« Back", "menu")])
        markup = _inline(*rows)

        if is_edit and msg_id:
            await tg.edit(chat_id, msg_id, text, reply_markup=markup)
        else:
            await tg.send(chat_id, text, reply_markup=markup)

    async def _do_publish_draft(
        self, chat_id: int, msg_id: int, slug: str, tg: TG
    ) -> None:
        from flatblog.core.post import load_all_posts, set_draft_flag

        posts_dir = self.root / "posts"
        posts = load_all_posts(posts_dir, include_drafts=True)
        match = next((p for p in posts if p.url_slug == slug), None)

        if not match:
            await tg.edit(chat_id, msg_id, f"❌  Draft not found: {slug}", reply_markup=None)
            return

        set_draft_flag(match.path, draft=False)
        await tg.edit(chat_id, msg_id, f"🚀  Publishing <b>{match.title}</b>…", reply_markup=None)
        await self._run_build()
        lines = await self._run_publish()
        summary = "\n".join(lines)
        await tg.send(chat_id, f"✅  Done!\n\n<pre>{summary}</pre>", reply_markup=MAIN_MENU)

    async def _do_discard_draft(
        self, chat_id: int, msg_id: int, slug: str, tg: TG
    ) -> None:
        from flatblog.core.post import load_all_posts

        posts_dir = self.root / "posts"
        posts = load_all_posts(posts_dir, include_drafts=True)
        match = next((p for p in posts if p.url_slug == slug), None)

        if not match:
            await tg.edit(chat_id, msg_id, f"❌  Not found: {slug}", reply_markup=None)
            return

        match.path.unlink()
        await tg.edit(chat_id, msg_id, f"🗑️  Deleted draft: <b>{match.title}</b>", reply_markup=None)
        await tg.send(chat_id, "Anything else?", reply_markup=MAIN_MENU)

    # ── Style guide ────────────────────────────────────────────────────────────

    async def _style_show(self, chat_id: int, msg_id: int, tg: TG) -> None:
        from flatblog.core.style import load_style, style_path

        text = load_style(self.root)
        sp   = style_path(self.root)

        if not text:
            await tg.edit(
                chat_id, msg_id,
                "🎨  No style guide set yet.\n\nUse <b>Reset to built-in</b> to load the SafeClaw guide.",
                reply_markup=STYLE_MENU,
            )
            return

        # Telegram message limit is 4096 chars; split if needed
        preview = text[:3800]
        truncated = len(text) > 3800
        footer = f"\n\n<i>({sp.name}{', truncated…' if truncated else ''})</i>"
        await tg.edit(
            chat_id, msg_id,
            f"🎨  <b>Current style guide</b>\n\n<pre>{preview}</pre>{footer}",
            reply_markup=STYLE_MENU,
        )

    async def _do_save_style_text(self, chat_id: int, text: str, tg: TG) -> None:
        from flatblog.core.style import save_style

        st = self._st(chat_id)
        st.step = "idle"
        st.data.clear()

        if text.strip() in ("/cancel", ""):
            await tg.send(chat_id, "Cancelled.", reply_markup=MAIN_MENU)
            return

        save_style(self.root, text)
        lines = len(text.splitlines())
        await tg.send(
            chat_id,
            f"✅  Style guide saved ({lines} lines).",
            reply_markup=MAIN_MENU,
        )

    async def _do_import_style_url(self, chat_id: int, url: str, tg: TG) -> None:
        from flatblog.core.style import save_style, import_from_url

        st = self._st(chat_id)
        st.step = "idle"

        if url.strip() == "/cancel":
            await tg.send(chat_id, "Cancelled.", reply_markup=MAIN_MENU)
            return

        await tg.send(chat_id, f"📥  Downloading…")
        try:
            text = await import_from_url(url.strip())
            save_style(self.root, text)
            lines = len(text.splitlines())
            await tg.send(chat_id, f"✅  Imported ({lines} lines).", reply_markup=MAIN_MENU)
        except Exception as e:
            await tg.send(chat_id, f"❌  Import failed: {e}", reply_markup=MAIN_MENU)

    # ── Cover image ────────────────────────────────────────────────────────────

    async def _on_photo(self, chat_id: int, photo: list[dict], tg: TG) -> None:
        from flatblog.core.post import load_all_posts

        st = self._st(chat_id)
        # Pick largest photo size
        file_id = sorted(photo, key=lambda p: p.get("file_size", 0))[-1]["file_id"]
        st.data["pending_photo_file_id"] = file_id
        st.step = "wait_cover_target"

        posts_dir = self.root / "posts"
        all_posts = load_all_posts(posts_dir, include_drafts=True)

        if not all_posts:
            await tg.send(chat_id, "No posts found to attach this image to.", reply_markup=MAIN_MENU)
            return

        rows = [
            [(f"{p.title[:30]}", f"cover_{p.url_slug}")]
            for p in all_posts[:8]
        ]
        rows.append([("Cancel", "menu")])
        await tg.send(
            chat_id,
            "📷  <b>Which post should this be the cover for?</b>",
            reply_markup=_inline(*rows),
        )

    async def _do_attach_cover(
        self, chat_id: int, msg_id: int, slug: str, tg: TG
    ) -> None:
        from flatblog.core.post import load_all_posts, parse_post
        import re as _re

        st = self._st(chat_id)
        file_id = st.data.pop("pending_photo_file_id", None)
        st.step = "idle"

        if not file_id:
            await tg.edit(chat_id, msg_id, "❌  No photo pending.", reply_markup=None)
            return

        posts_dir = self.root / "posts"
        posts = load_all_posts(posts_dir, include_drafts=True)
        match = next((p for p in posts if p.url_slug == slug), None)

        if not match:
            await tg.edit(chat_id, msg_id, f"❌  Post not found: {slug}", reply_markup=None)
            return

        await tg.edit(chat_id, msg_id, "📷  Downloading image…", reply_markup=None)

        async with httpx.AsyncClient(timeout=60) as client:
            tg_dl = TG(self.token, client)
            img_bytes, ext = await tg_dl.download_file(file_id)

        images_dir = posts_dir / "images"
        images_dir.mkdir(exist_ok=True)
        img_path = images_dir / f"{slug}{ext}"
        img_path.write_bytes(img_bytes)

        # Patch cover_image in frontmatter
        relative = f"images/{slug}{ext}"
        text = match.path.read_text(encoding="utf-8")
        if _re.search(r"^cover_image:", text, _re.MULTILINE):
            text = _re.sub(r"^cover_image:.*$", f"cover_image: {relative}", text, flags=_re.MULTILINE)
        else:
            text = _re.sub(r"^(---\n)", f"---\ncover_image: {relative}\n", text, count=1)
        match.path.write_text(text, encoding="utf-8")

        await tg.send(
            chat_id,
            f"✅  Cover saved for <b>{match.title}</b>",
            reply_markup=MAIN_MENU,
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _ai_write(self, topic: str):
        from flatblog.core.ai import AIWriter
        from flatblog.core.post import write_post, _slugify
        from datetime import datetime

        writer = AIWriter(self.cfg, blog_root=self.root)
        if not writer.is_configured():
            raise RuntimeError("AI not configured. Run: flatblog setup ai")

        title, body, _ = await writer.generate(topic)

        posts_dir = self.root / "posts"
        slug = _slugify(title)
        filename = f"{datetime.today().date()}-{slug}.md"
        path = posts_dir / filename

        post = write_post(
            path,
            title=title,
            body=body,
            draft=True,
        )
        return post

    async def _run_build(self) -> int:
        from flatblog.core.builder import build_site
        from flatblog.core.config import load_config

        cfg = load_config(self.cfg_path)
        root = self.root
        posts_dir  = root / "posts"
        output_dir = root / cfg.get("build", {}).get("output_dir", "output")
        blog_meta  = cfg.get("blog", {})
        theme_dir  = root / "themes" / cfg.get("build", {}).get("theme", "default")

        return build_site(posts_dir, output_dir, theme_dir, blog_meta)

    async def _run_publish(self) -> list[str]:
        from flatblog.core.publisher import publish_all
        from flatblog.core.config import load_config

        cfg = load_config(self.cfg_path)
        root = self.root
        output_dir = root / cfg.get("build", {}).get("output_dir", "output")
        return await publish_all(output_dir, cfg)

    def _status_text(self) -> str:
        from flatblog.core.post import load_all_posts

        blog  = self.cfg.get("blog", {})
        posts = load_all_posts(self.root / "posts", include_drafts=True)
        pub   = [p for p in posts if not p.draft]
        dra   = [p for p in posts if p.draft]
        tgts  = self.cfg.get("publish", {}).get("targets", [])
        tgt_s = ", ".join(t.get("label", t.get("type", "?")) for t in tgts) or "none"

        return (
            f"<b>{blog.get('title', 'flatblog')}</b>\n"
            f"Author: {blog.get('author', '—')}\n"
            f"URL:    {blog.get('url', '—')}\n\n"
            f"Posts:   {len(pub)}\n"
            f"Drafts:  {len(dra)}\n"
            f"Targets: {tgt_s}"
        )


# ── Runner ─────────────────────────────────────────────────────────────────────

async def run_bot(token: str, cfg: dict, cfg_path: Path) -> None:
    """Long-poll loop — runs until interrupted."""
    bot    = FlatblogBot(token, cfg, cfg_path)
    offset = 0

    log.info("flatblog bot started")
    async with httpx.AsyncClient(timeout=40) as client:
        tg = TG(token, client)
        while True:
            try:
                updates = await tg.get_updates(offset, timeout=30)
            except (httpx.ReadTimeout, httpx.ConnectError):
                await asyncio.sleep(2)
                continue
            except asyncio.CancelledError:
                break

            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    await bot.handle_update(upd, tg)
                except Exception as exc:
                    log.exception("Update error: %s", exc)
