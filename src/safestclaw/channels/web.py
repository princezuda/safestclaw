"""
SafestClaw localhost web interface.

A FastAPI-backed channel that exposes the *entire* SafestClaw engine —
every action, every plugin, every command — through a tiny single-page
chat UI plus a small JSON API.

By default the server binds to **127.0.0.1** only. There is intentionally
no remote-binding helper: if you want to expose this beyond localhost,
put a real reverse proxy with TLS + auth in front.

Endpoints
---------

  GET  /                 → chat UI (HTML, no external CDNs)
  GET  /api/health       → liveness probe
  GET  /api/actions      → list registered actions with example commands
  GET  /api/help         → engine.get_help() text
  POST /api/message      → run a command, returns the response text
                            body: {"text": "...", "user_id": "..."}
  GET  /api/history      → recent messages for a user (best-effort, from
                            engine.memory)

Auth
----

Optional ``auth_token`` in the channel config. When set, every request
must include ``Authorization: Bearer <token>`` (or ``X-SafestClaw-Token``).
When unset, requests from 127.0.0.1 are accepted with no token because
anyone on this machine could already invoke SafestClaw locally.

Config
------

    channels:
      web:
        enabled: true
        host: "127.0.0.1"
        port: 8771
        auth_token: ""     # optional
        user_id: "web_user"
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from safestclaw.channels.base import BaseChannel

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover - already a core dep, but be defensive
    FastAPI = None  # type: ignore[assignment]
    HAS_FASTAPI = False


# ─────────────────────────────────────────────────────────────────────────────
# Per-action UI metadata. Tells the front-end how clicking an action button
# should behave:
#
#   "immediate" → run the command directly, no input typing required
#   "config"    → first click asks for a value, saves it to localStorage,
#                 every later click runs immediately with the saved value
#   "explain"   → show a short explainer + a single button to run / set up
#
# Actions not listed here fall through to the default behaviour: prefill
# the chat input with the first example so the user can edit + submit.
# ─────────────────────────────────────────────────────────────────────────────

ACTION_UI: dict[str, dict[str, Any]] = {
    "weather": {
        "type": "config",
        "description": "Current weather. Free, no API key.",
        "key": "weather_location",
        "label": "Default location",
        "placeholder": "e.g. New York or London",
        "template": "weather {value}",
    },
    "news": {
        "type": "config",
        "description": "Latest headlines from RSS feeds.",
        "key": "news_category",
        "label": "Default category (blank = all)",
        "placeholder": "tech, world, science…",
        "template": "news {value}",
        "allow_empty": True,
    },
    "briefing": {
        "type": "immediate",
        "description": "Daily briefing: weather + news + calendar.",
        "run": "briefing",
    },
    "calendar": {
        "type": "immediate",
        "description": "Today's events from your calendar.",
        "run": "calendar today",
    },
    "help": {"type": "immediate", "run": "help"},
    "flow": {"type": "immediate", "run": "flow"},
    "style": {"type": "immediate", "run": "style"},
    "mcp": {
        "type": "explain",
        "description": (
            "Model Context Protocol — expose every SafestClaw action as a "
            "tool that Claude Desktop and IDE clients can call. Configure "
            "with `safestclaw setup` or edit config.yaml."
        ),
        "run": "help mcp",
        "run_label": "Show MCP help",
    },
    "llm_setup": {
        "type": "explain",
        "description": (
            "Install or connect a language model — local Ollama or a cloud "
            "API key. Optional: every deterministic feature works without one."
        ),
        "run": "ai status",
        "run_label": "Show AI status",
    },
    "security": {
        "type": "explain",
        "description": (
            "Deterministic security scanners (bandit, pip-audit, semgrep, "
            "trivy, gitleaks, …). No AI required."
        ),
        "run": "security tools",
        "run_label": "Show installed scanners",
    },
    "autoblog": {
        "type": "explain",
        "description": "Cron-based blog publishing from RSS feeds.",
        "run": "autoblog list",
        "run_label": "List schedules",
    },
    "blog": {
        "type": "explain",
        "description": "Write, list, and publish blog posts (no LLM required).",
        "run": "blog help",
        "run_label": "Show blog commands",
    },
    "email": {
        "type": "explain",
        "description": "Read, search, and compose email (IMAP / SMTP).",
        "run": "email help",
        "run_label": "Show email commands",
    },
    "research": {
        "type": "explain",
        "description": "Multi-source research with selectable sources.",
        "run": "research help",
        "run_label": "Show research commands",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# HTML / CSS / JS — single inline page, no external assets, no CDNs.
# ─────────────────────────────────────────────────────────────────────────────

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SafestClaw</title>
<style>
  :root {
    --bg: #0e1116;
    --panel: #161b22;
    --panel-border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --accent-bg: #1f6feb;
    --good: #3fb950;
    --warn: #d29922;
    --bad: #f85149;
    --user-bg: #1f6feb;
    --asst-bg: #1c2128;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  #app { display: grid; grid-template-columns: 280px 1fr;
         height: 100vh; }
  aside {
    background: var(--panel);
    border-right: 1px solid var(--panel-border);
    overflow-y: auto;
    padding: 14px;
  }
  aside h1 { font-size: 16px; margin: 0 0 4px; color: var(--accent); }
  aside .sub { color: var(--muted); font-size: 12px; margin-bottom: 14px; }
  aside h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
             color: var(--muted); margin: 14px 0 6px; }
  .actions { display: flex; flex-direction: column; gap: 4px; }
  .action {
    background: transparent;
    border: 1px solid var(--panel-border);
    color: var(--text);
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    text-align: left;
    font-size: 13px;
  }
  .action:hover { border-color: var(--accent); color: var(--accent); }
  .action small { display: block; color: var(--muted); margin-top: 2px;
                  font-size: 11px; white-space: nowrap; overflow: hidden;
                  text-overflow: ellipsis; }
  main { display: flex; flex-direction: column; min-width: 0; }
  header {
    border-bottom: 1px solid var(--panel-border);
    padding: 10px 16px;
    display: flex; align-items: center; gap: 10px;
    background: var(--panel);
  }
  header .dot { width: 8px; height: 8px; border-radius: 50%;
                background: var(--good); }
  header .dot.bad { background: var(--bad); }
  header h1 { font-size: 14px; margin: 0; font-weight: 600; }
  header .meta { color: var(--muted); font-size: 12px; }
  #log {
    flex: 1; overflow-y: auto; padding: 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .msg { max-width: 80%; padding: 8px 12px; border-radius: 10px;
         white-space: pre-wrap; word-wrap: break-word; }
  .msg.user { background: var(--user-bg); align-self: flex-end; }
  .msg.asst { background: var(--asst-bg); border: 1px solid var(--panel-border);
              align-self: flex-start; }
  .msg.err  { background: #3a1414; border: 1px solid var(--bad);
              align-self: flex-start; }
  .msg pre { background: #0b0e13; padding: 8px; border-radius: 6px;
             overflow-x: auto; margin: 6px 0; font-size: 12px; }
  .msg code { background: #0b0e13; padding: 1px 4px; border-radius: 4px;
              font-size: 12px; }
  form {
    border-top: 1px solid var(--panel-border);
    padding: 10px; display: flex; gap: 8px; background: var(--panel);
  }
  input[type=text] {
    flex: 1; background: var(--bg); color: var(--text);
    border: 1px solid var(--panel-border); border-radius: 6px;
    padding: 8px 10px; font: inherit;
  }
  input[type=text]:focus { outline: none; border-color: var(--accent); }
  button.send {
    background: var(--accent-bg); color: white; border: 0; border-radius: 6px;
    padding: 8px 14px; cursor: pointer; font: inherit;
  }
  button.send:disabled { opacity: 0.5; cursor: not-allowed; }
  .pill { display: inline-block; padding: 1px 6px; border-radius: 999px;
          background: #21262d; color: var(--muted); font-size: 11px; }
  .empty { color: var(--muted); text-align: center; margin-top: 20vh; }
  .card {
    align-self: flex-start; max-width: 80%;
    background: var(--asst-bg); border: 1px solid var(--panel-border);
    border-radius: 10px; padding: 10px 12px;
  }
  .card .title { font-weight: 600; margin-bottom: 4px; }
  .card .desc  { color: var(--muted); margin-bottom: 8px; }
  .card .saved { color: var(--good); font-size: 12px; margin-bottom: 8px; }
  .card .row   { display: flex; gap: 6px; flex-wrap: wrap; }
  .card input  {
    flex: 1; min-width: 160px; background: var(--bg); color: var(--text);
    border: 1px solid var(--panel-border); border-radius: 6px;
    padding: 6px 8px; font: inherit;
  }
  .card button {
    background: var(--accent-bg); color: white; border: 0; border-radius: 6px;
    padding: 6px 12px; cursor: pointer; font: inherit;
  }
  .card button.secondary {
    background: transparent; color: var(--muted);
    border: 1px solid var(--panel-border);
  }
  .card button:hover { filter: brightness(1.1); }
  aside .footer {
    margin-top: 14px; padding-top: 10px;
    border-top: 1px solid var(--panel-border);
  }
  aside .footer button {
    background: transparent; color: var(--muted);
    border: 1px solid var(--panel-border); border-radius: 6px;
    padding: 5px 8px; cursor: pointer; font: inherit; font-size: 12px;
    width: 100%;
  }
  aside .footer button:hover { color: var(--accent); border-color: var(--accent); }
</style>
</head>
<body>
<div id="app">
  <aside>
    <h1>SafestClaw</h1>
    <div class="sub">Privacy-first automation</div>
    <h2>Actions</h2>
    <div class="actions" id="actions"></div>
    <h2>Help</h2>
    <button class="action" id="help-btn">Show help</button>
    <div class="footer">
      <button id="reset-prefs">Reset saved defaults</button>
    </div>
  </aside>
  <main>
    <header>
      <span class="dot" id="status-dot"></span>
      <h1>Chat</h1>
      <span class="meta" id="status-text">Connecting…</span>
    </header>
    <div id="setup-banner" style="display:none; padding:10px 16px; background:#3a2c0a; color:#f0c674; border-bottom:1px solid #6a5328; font-size:13px;">
      🛠️  Looks like SafestClaw isn't set up yet.
      Type <strong>setup</strong> below to start the walkthrough,
      or <strong>skip</strong> to defer.
    </div>
    <div id="log">
      <div class="empty" id="empty">
        Type a command below or pick an action on the left.
      </div>
    </div>
    <form id="form" autocomplete="off">
      <input id="input" type="text" placeholder="Try: news tech, calendar today, summarize https://…" autofocus>
      <button class="send" type="submit">Send</button>
    </form>
  </main>
</div>
<script>
(function () {
  const TOKEN = window.localStorage.getItem("safestclaw-token") || "";
  const log = document.getElementById("log");
  const empty = document.getElementById("empty");
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const sendBtn = form.querySelector("button");
  const dot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const actionsList = document.getElementById("actions");
  const helpBtn = document.getElementById("help-btn");

  const headers = () => {
    const h = { "Content-Type": "application/json" };
    if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
    return h;
  };

  function escapeHTML(s) {
    return s.replace(/[&<>"]/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
    })[c]);
  }
  function renderMarkdownLite(s) {
    // Tiny safe-ish renderer: escape, then handle ``` blocks, `code`, **bold**.
    let out = escapeHTML(s);
    out = out.replace(/```([\\s\\S]*?)```/g, (_, b) => "<pre>" + b + "</pre>");
    out = out.replace(/`([^`]+)`/g, (_, c) => "<code>" + c + "</code>");
    out = out.replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
    return out;
  }
  function addMessage(text, kind) {
    if (empty) empty.remove();
    const d = document.createElement("div");
    d.className = "msg " + kind;
    d.innerHTML = renderMarkdownLite(text);
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  async function ping() {
    try {
      const r = await fetch("/api/health", { headers: headers() });
      if (r.ok) {
        const j = await r.json();
        dot.classList.remove("bad");
        statusText.textContent = j.name + " · " +
          j.actions + " actions, " + j.channels + " channels";
        const banner = document.getElementById("setup-banner");
        if (banner) banner.style.display = j.needs_setup ? "block" : "none";
        return true;
      }
      throw new Error("status " + r.status);
    } catch (e) {
      dot.classList.add("bad");
      statusText.textContent = "Disconnected (" + e.message + ")";
      return false;
    }
  }

  const PREF_PREFIX = "safestclaw-pref-";
  function getPref(key) { return window.localStorage.getItem(PREF_PREFIX + key); }
  function setPref(key, val) { window.localStorage.setItem(PREF_PREFIX + key, val); }
  function clearPrefs() {
    Object.keys(window.localStorage)
      .filter(k => k.startsWith(PREF_PREFIX))
      .forEach(k => window.localStorage.removeItem(k));
  }

  function showCard(buildBody) {
    if (empty) empty.remove();
    const card = document.createElement("div");
    card.className = "card";
    buildBody(card, () => card.remove());
    log.appendChild(card);
    log.scrollTop = log.scrollHeight;
    return card;
  }

  function explainCard(action) {
    const ui = action.ui || {};
    showCard((card, close) => {
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = action.name;
      const desc = document.createElement("div");
      desc.className = "desc";
      desc.textContent = ui.description || "";
      const row = document.createElement("div");
      row.className = "row";
      const run = document.createElement("button");
      run.textContent = ui.run_label || "Run it";
      run.addEventListener("click", () => {
        close();
        send(ui.run || action.name);
      });
      const cancel = document.createElement("button");
      cancel.className = "secondary";
      cancel.textContent = "Cancel";
      cancel.addEventListener("click", close);
      row.appendChild(run);
      row.appendChild(cancel);
      card.appendChild(title);
      if (ui.description) card.appendChild(desc);
      card.appendChild(row);
    });
  }

  function buildConfigCommand(ui, value) {
    const tpl = ui.template || (ui.run || "");
    return tpl.replace("{value}", value).trim();
  }

  function configCard(action, opts) {
    opts = opts || {};
    const ui = action.ui || {};
    showCard((card, close) => {
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = action.name;
      const desc = document.createElement("div");
      desc.className = "desc";
      desc.textContent = ui.description || "";

      const row = document.createElement("div");
      row.className = "row";
      const field = document.createElement("input");
      field.type = "text";
      field.placeholder = ui.placeholder || "";
      field.value = opts.initial || "";
      field.setAttribute("aria-label", ui.label || action.name);
      const save = document.createElement("button");
      save.textContent = "Save & run";
      const cancel = document.createElement("button");
      cancel.className = "secondary";
      cancel.textContent = "Cancel";

      const submit = () => {
        const v = field.value.trim();
        if (!v && !ui.allow_empty) { field.focus(); return; }
        setPref(ui.key, v);
        close();
        send(buildConfigCommand(ui, v));
      };
      save.addEventListener("click", submit);
      cancel.addEventListener("click", close);
      field.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); submit(); }
      });

      row.appendChild(field);
      row.appendChild(save);
      row.appendChild(cancel);

      const labelEl = document.createElement("div");
      labelEl.className = "desc";
      labelEl.textContent = ui.label || "";

      card.appendChild(title);
      if (ui.description) card.appendChild(desc);
      if (ui.label) card.appendChild(labelEl);
      card.appendChild(row);
      setTimeout(() => field.focus(), 0);
    });
  }

  function handleActionClick(action) {
    const ui = action.ui || {};
    const type = ui.type || "input";

    if (type === "immediate") {
      send(ui.run || action.name);
      return;
    }
    if (type === "explain") {
      explainCard(action);
      return;
    }
    if (type === "config") {
      const saved = getPref(ui.key);
      if (saved !== null) {
        send(buildConfigCommand(ui, saved));
        return;
      }
      configCard(action, { initial: "" });
      return;
    }
    // Fallback: prefill the input so the user can edit and submit.
    const example = (action.examples && action.examples[0]) || action.name;
    input.value = example;
    input.focus();
  }

  async function loadActions() {
    try {
      const r = await fetch("/api/actions", { headers: headers() });
      if (!r.ok) return;
      const j = await r.json();
      actionsList.innerHTML = "";
      (j.actions || []).forEach(a => {
        const b = document.createElement("button");
        b.className = "action";
        const ui = a.ui || {};
        const hint = ui.description
          || (a.examples && a.examples[0])
          || a.name;
        b.title = hint;
        const saved = ui.type === "config" ? getPref(ui.key) : null;
        let sub;
        if (saved !== null) {
          sub = saved ? ("Saved: " + saved) : "Saved: (all)";
        } else {
          sub = ui.description || (a.examples && a.examples[0]) || a.name;
        }
        b.innerHTML = "<strong>" + escapeHTML(a.name) + "</strong>" +
                      "<small>" + escapeHTML(sub) + "</small>";
        b.addEventListener("click", () => handleActionClick(a));
        actionsList.appendChild(b);
      });
    } catch (e) {
      // swallow — actions are optional
    }
  }

  async function send(text) {
    addMessage(text, "user");
    sendBtn.disabled = true;
    input.value = "";
    try {
      const r = await fetch("/api/message", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ text: text })
      });
      const j = await r.json();
      if (!r.ok) {
        addMessage(j.detail || ("Error " + r.status), "err");
      } else {
        addMessage(j.response || "(no response)", "asst");
      }
    } catch (e) {
      addMessage("Network error: " + e.message, "err");
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", e => {
    e.preventDefault();
    const v = input.value.trim();
    if (v) send(v);
  });
  helpBtn.addEventListener("click", () => send("help"));

  const resetBtn = document.getElementById("reset-prefs");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      clearPrefs();
      loadActions();
      addMessage("Saved defaults cleared.", "asst");
    });
  }

  ping().then(ok => { if (ok) loadActions(); });
  setInterval(ping, 30000);
})();
</script>
</body>
</html>
"""


class WebChannel(BaseChannel):
    """Localhost web UI + JSON API."""

    name = "web"

    def __init__(
        self,
        engine: SafestClaw,
        host: str = "127.0.0.1",
        port: int = 8771,
        auth_token: str | None = None,
        user_id: str = "web_user",
    ):
        super().__init__(engine)
        if not HAS_FASTAPI:
            raise ImportError(
                "FastAPI is required for the web channel. "
                "Install with: pip install fastapi uvicorn"
            )
        # Refuse anything but a loopback bind. Anyone wanting remote access
        # should put a reverse proxy with TLS + auth in front.
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "WebChannel only binds to loopback (127.0.0.1, localhost, "
                f"::1). Got: {host!r}. Put a reverse proxy in front for "
                "remote access."
            )
        self.host = host
        self.port = int(port)
        self.auth_token = (auth_token or "").strip() or None
        self.user_id = user_id
        self._server = None
        self._server_task: asyncio.Task | None = None
        self.app = self._build_app()

    # ------------------------------------------------------------------
    # FastAPI app
    # ------------------------------------------------------------------

    def _build_app(self) -> Any:
        app = FastAPI(
            title="SafestClaw Web",
            description="Localhost UI + JSON API for the SafestClaw engine",
            version="1.0.0",
            docs_url=None,  # /docs disabled — no need to expose schema
            redoc_url=None,
        )

        # Loopback enforcement happens at construction time via the bind
        # address. Uvicorn bound to 127.0.0.1 won't accept off-host
        # connections; checking request.client.host per request adds no
        # real security and breaks in-process testing.

        def _check_auth(request: Request) -> None:
            if not self.auth_token:
                return
            header = (
                request.headers.get("authorization")
                or request.headers.get("x-safestclaw-token")
                or ""
            ).strip()
            if header.lower().startswith("bearer "):
                header = header[7:].strip()
            if header != self.auth_token:
                raise HTTPException(status_code=401, detail="Unauthorized")

        @app.get("/", response_class=HTMLResponse)
        async def index() -> Any:
            return HTMLResponse(_INDEX_HTML)

        @app.get("/api/health")
        async def health(request: Request) -> Any:
            _check_auth(request)
            sc = self.engine.config.get("safestclaw", {}) or {}
            needs_setup = False
            if hasattr(self.engine, "chat_setup"):
                try:
                    needs_setup = self.engine.chat_setup.needs_setup()
                except Exception:
                    needs_setup = False
            return {
                "status": "ok",
                "name": sc.get("name", "SafestClaw"),
                "actions": len(self.engine.actions),
                "channels": len(self.engine.channels),
                "needs_setup": needs_setup,
            }

        @app.get("/api/actions")
        async def actions(request: Request) -> Any:
            _check_auth(request)
            intents = getattr(self.engine.parser, "intents", {}) or {}
            payload = []
            for name in sorted(self.engine.actions.keys()):
                pat = intents.get(name)
                payload.append({
                    "name": name,
                    "examples": list(pat.examples) if pat else [],
                    "keywords": list(pat.keywords) if pat else [],
                    "ui": ACTION_UI.get(name, {"type": "input"}),
                })
            return {"actions": payload}

        @app.get("/api/help")
        async def help_text(request: Request) -> Any:
            _check_auth(request)
            return {"help": self.engine.get_help()}

        @app.post("/api/message")
        async def message(request: Request) -> Any:
            _check_auth(request)
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            text = (body.get("text") or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="Missing 'text'")
            user_id = (body.get("user_id") or self.user_id).strip()
            try:
                response = await self.engine.handle_message(
                    text=text,
                    channel=self.name,
                    user_id=user_id,
                )
            except Exception as e:
                logger.exception("Web message failed")
                raise HTTPException(status_code=500, detail=str(e))
            return {"response": response, "user_id": user_id}

        @app.get("/api/history")
        async def history(request: Request, user_id: str = "", limit: int = 20) -> Any:
            _check_auth(request)
            uid = (user_id or self.user_id).strip()
            limit = max(1, min(int(limit or 20), 200))
            try:
                getter = getattr(self.engine.memory, "get_history", None)
                items = await getter(uid, limit) if getter else []
            except Exception as e:
                logger.warning(f"history fetch failed: {e}")
                items = []
            return {"messages": items}

        return app

    # ------------------------------------------------------------------
    # BaseChannel
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the FastAPI server in-process."""
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        logger.info(
            f"SafestClaw web UI listening on http://{self.host}:{self.port}"
            + ("  (auth token required)" if self.auth_token else "")
        )
        try:
            await self._server.serve()
        except asyncio.CancelledError:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        self._server = None

    async def send(self, user_id: str, message: str) -> None:
        """No-op — the web UI polls; there's no push channel in v1."""
        return

    @classmethod
    def from_config(
        cls,
        engine: SafestClaw,
        cfg: dict[str, Any] | None,
    ) -> WebChannel:
        cfg = cfg or {}
        return cls(
            engine=engine,
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 8771)),
            auth_token=cfg.get("auth_token") or None,
            user_id=cfg.get("user_id", "web_user"),
        )
