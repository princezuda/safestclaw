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
    from fastapi.responses import HTMLResponse, JSONResponse
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover - already a core dep, but be defensive
    FastAPI = None  # type: ignore[assignment]
    HAS_FASTAPI = False


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
  </aside>
  <main>
    <header>
      <span class="dot" id="status-dot"></span>
      <h1>Chat</h1>
      <span class="meta" id="status-text">Connecting…</span>
    </header>
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
        return true;
      }
      throw new Error("status " + r.status);
    } catch (e) {
      dot.classList.add("bad");
      statusText.textContent = "Disconnected (" + e.message + ")";
      return false;
    }
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
        b.title = a.examples && a.examples[0] ? a.examples[0] : a.name;
        const example = (a.examples && a.examples[0]) || a.name;
        b.innerHTML = "<strong>" + escapeHTML(a.name) + "</strong>" +
                      "<small>" + escapeHTML(example) + "</small>";
        b.addEventListener("click", () => {
          input.value = example;
          input.focus();
        });
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
        engine: "SafestClaw",
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
            return {
                "status": "ok",
                "name": sc.get("name", "SafestClaw"),
                "actions": len(self.engine.actions),
                "channels": len(self.engine.channels),
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
        engine: "SafestClaw",
        cfg: dict[str, Any] | None,
    ) -> "WebChannel":
        cfg = cfg or {}
        return cls(
            engine=engine,
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 8771)),
            auth_token=cfg.get("auth_token") or None,
            user_id=cfg.get("user_id", "web_user"),
        )
