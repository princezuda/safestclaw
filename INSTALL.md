# Installing SafestClaw

SafestClaw is on PyPI — `pip install safestclaw`. The core install gives
you every feature that doesn't need an external service or library
(summaries, news, crawl, briefings, blog, calendar from `.ics`, the web
UI, the webhook server, all rule-based parsing). Channels and heavier
features are opt-in via extras.

## Requirements

- Python **3.11** or newer
- pip 23+ (older pip works but produces noisier output)
- Roughly 200 MB of disk space for the core install. Optional extras add
  more — `[vision]` alone pulls ~2 GB because of PyTorch.

## Quick install

```bash
pip install safestclaw
safestclaw setup
```

`safestclaw setup` walks through choosing local-only or LLM mode,
configuring Telegram (and auto-installing the cron tick so the bot keeps
replying when the app is off), and enabling the localhost web UI (with
an auto-start service so it returns at login).

## Choosing extras

`pip install safestclaw[<extra>]` to add a feature, or combine extras
with commas: `pip install "safestclaw[telegram,sftp]"`.

| Command | What it adds |
|---|---|
| `pip install safestclaw` | Core only. Summaries, news, crawl, weather, calendar (.ics), briefings, blog, web UI, webhook server, deterministic parser. No channels. |
| `pip install safestclaw[telegram]` | The Telegram bot (`safestclaw telegram`, `telegram-tick`). |
| `pip install safestclaw[discord]` | Discord channel. |
| `pip install safestclaw[slack]` | Slack channel. |
| `pip install safestclaw[matrix]` | Matrix channel. |
| `pip install safestclaw[email]` | IMAP read + SMTP send (`email check`, `send email …`). |
| `pip install safestclaw[caldav]` | CalDAV calendar sync (Nextcloud, Radicale, iCloud, Fastmail, …). |
| `pip install safestclaw[sftp]` | SFTP-based blog publishing (`paramiko`). |
| `pip install safestclaw[smarthome]` | Hue lights + MQTT. |
| `pip install safestclaw[browser]` | Playwright browser automation. |
| `pip install safestclaw[mcp]` | FastMCP server (`safestclaw mcp`) — exposes every action as an MCP tool for Claude Desktop / IDE clients. |
| `pip install safestclaw[ocr]` | Lightweight OCR via tesseract. |
| `pip install safestclaw[nlp]` | spaCy NER (~50 MB). |
| `pip install safestclaw[vision]` | YOLO object detection + OCR (~2 GB, drags in PyTorch). |
| `pip install safestclaw[all]` | Every channel + plugin extra (`telegram`, `discord`, `slack`, `matrix`, `email`, `smarthome`, `browser`, `caldav`, `sftp`, `mcp`). Excludes ML. |
| `pip install safestclaw[ml]` | All ML extras (`nlp`, `vision`). |
| `pip install "safestclaw[all,ml]"` | Absolutely everything. Big download. |

The most common path is **core + Telegram + the web UI**:

```bash
pip install "safestclaw[telegram]"
safestclaw setup
```

## Recommended: install into a virtual environment

Avoid mixing SafestClaw with system Python packages. Either pipx (one-line)
or a venv (a couple of lines):

```bash
# pipx — keeps SafestClaw isolated, puts the `safestclaw` command on PATH
pipx install "safestclaw[telegram]"

# or a venv
python -m venv ~/.local/safestclaw
source ~/.local/safestclaw/bin/activate    # Windows: .\Scripts\activate
pip install "safestclaw[telegram]"
```

If you want extras with pipx, use:

```bash
pipx install "safestclaw[telegram,mcp]"
# or, if SafestClaw is already installed and you want to add an extra:
pipx inject safestclaw 'safestclaw[telegram]'
```

## Verifying the install

```bash
safestclaw --version
safestclaw --help
```

Then either run the wizard:

```bash
safestclaw setup
```

…or jump straight into the interactive CLI:

```bash
safestclaw
```

## Platform notes

### Linux

- Auto-start of the web UI uses a **systemd user service** at
  `~/.config/systemd/user/safestclaw-web.service`. To make it survive
  logout, run once:

  ```bash
  loginctl enable-linger "$USER"
  ```

- The Telegram tick is registered as a tagged crontab entry
  (`# safestclaw-telegram-tick`). `crontab -l` shows it; `safestclaw
  telegram-tick --uninstall` removes just our line.

### macOS

- Auto-start of the web UI uses a **launchd agent** at
  `~/Library/LaunchAgents/com.safestclaw.web.plist`.
- The Telegram tick uses crontab. macOS may prompt for permission the
  first time cron runs new commands — approve "Full Disk Access" for
  cron in System Settings → Privacy & Security if your config / data
  paths require it.

### Windows

- Auto-start of the web UI uses a **Task Scheduler** entry named
  `SafestClaw Web` (trigger: "At log on").
- The Telegram tick uses a Task Scheduler entry named `SafestClaw
  Telegram Tick` (trigger: "Every N minutes").
- Both can be inspected from `taskschd.msc`.

## Upgrading

```bash
pip install -U safestclaw
# or, with pipx:
pipx upgrade safestclaw
```

After upgrading, re-running `safestclaw setup` is optional — your
config in `config/config.yaml` is preserved.

## Uninstalling

```bash
# remove auto-start entries first so nothing is left running
safestclaw web --uninstall
safestclaw telegram-tick --uninstall

# then the package
pip uninstall safestclaw
# or, with pipx:
pipx uninstall safestclaw
```

`config/config.yaml` and the SQLite memory at `~/.safestclaw/memory.db`
are left alone — delete them by hand if you want a fully clean slate.

## Troubleshooting

**`safestclaw: command not found`** — pip put the script in a directory
that isn't on `PATH`. With pipx this is rare; with a system pip, run
`python -m safestclaw` instead, or add `~/.local/bin` (Linux/macOS) or
the Python `Scripts` folder (Windows) to your `PATH`.

**`Telegram library missing. Install with: pip install safestclaw[telegram]`** —
exactly what it says. Re-install with the extra: `pip install -U
"safestclaw[telegram]"`.

**`getaddrinfo failed` from the Telegram bot** — DNS / network problem
on the host (Telegram itself isn't down). Try `nslookup
api.telegram.org`. The bot retries on its own once DNS recovers.

**`ConnectError`, `Connection refused`, `409 Conflict` from Telegram** —
409 means another `getUpdates` consumer is active. If you have both
`safestclaw telegram` and the cron tick installed, pick one:

```bash
safestclaw telegram-tick --uninstall   # if you want long polling instead
# or
# stop the long-polling process if you want the cron tick to handle Telegram
```

**The `[vision]` extra is huge / I don't need it** — skip it. None of
the default features depend on PyTorch. Use `[ocr]` if you only want
text-from-image (lightweight).

**Permission denied writing `config/config.yaml`** — you're probably
running from a directory that isn't writable. Either `cd` into your
home directory first, or pass `--config ~/.config/safestclaw.yaml` to
every command.
