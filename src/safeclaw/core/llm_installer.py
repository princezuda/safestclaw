"""
SafeClaw LLM Setup - Super simple AI configuration.

Two paths, both dead simple:

1. Cloud (fastest): Just enter your Anthropic API key
     setup ai sk-ant-...

2. Local (free): Auto-installs Ollama + downloads a model
     setup ai local

That's it. No config files to edit.
"""

import asyncio
import logging
import platform
import shutil
import subprocess
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Cloud providers and their config shapes
CLOUD_PROVIDERS = {
    "anthropic": {
        "label": "anthropic",
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "temperature": 0.7,
        "max_tokens": 2000,
        "key_prefix": "sk-ant-",
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    "openai": {
        "label": "openai",
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 2000,
        "key_prefix": "sk-",
        "key_url": "https://platform.openai.com/api-keys",
    },
    "google": {
        "label": "google",
        "provider": "google",
        "model": "gemini-2.0-flash",
        "temperature": 0.7,
        "max_tokens": 2000,
        "key_prefix": "AI",
        "key_url": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "label": "groq",
        "provider": "groq",
        "model": "llama-3.1-70b-versatile",
        "temperature": 0.7,
        "max_tokens": 2000,
        "key_prefix": "gsk_",
        "key_url": "https://console.groq.com/keys",
    },
}

# Local model presets
LOCAL_MODELS = {
    "small": {
        "name": "llama3.2:1b",
        "size": "~1.3GB",
        "desc": "Fast, lightweight, good for quick tasks",
    },
    "default": {
        "name": "llama3.1",
        "size": "~4.7GB",
        "desc": "Best balance of quality and speed",
    },
    "large": {
        "name": "llama3.1:70b",
        "size": "~40GB",
        "desc": "Highest quality, needs 48GB+ RAM",
    },
    "coding": {
        "name": "codellama",
        "size": "~3.8GB",
        "desc": "Optimized for code generation",
    },
    "writing": {
        "name": "mistral",
        "size": "~4.1GB",
        "desc": "Great for blog writing and creative text",
    },
}


def _detect_provider(api_key: str) -> str | None:
    """Auto-detect which provider an API key belongs to."""
    key = api_key.strip()
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("AI"):
        return "google"
    if key.startswith("sk-"):
        return "openai"
    return None


def _update_config(config_path: Path, provider_config: dict) -> bool:
    """Update config.yaml with a new AI provider."""
    try:
        # Ensure parent directory exists (fresh install / Windows)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        providers = config.get("ai_providers", [])
        if providers is None:
            providers = []

        # Check if this provider already exists and update it
        label = provider_config.get("label", "")
        for i, p in enumerate(providers):
            if isinstance(p, dict) and p.get("label") == label:
                providers[i] = provider_config
                config["ai_providers"] = providers
                with open(config_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                return True

        # Add new provider
        providers.append(provider_config)
        config["ai_providers"] = providers

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return True
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Cloud setup (API key)
# ──────────────────────────────────────────────────────────────────────────────


def setup_with_key(api_key: str, config_path: Path) -> str:
    """
    Set up AI with an API key. Auto-detects the provider.

    Args:
        api_key: The API key (e.g. sk-ant-...)
        config_path: Path to config.yaml

    Returns:
        Status message
    """
    provider_name = _detect_provider(api_key)

    if not provider_name:
        return (
            "Couldn't detect provider from that key.\n\n"
            "Supported key formats:\n"
            "  `sk-ant-...` — Anthropic (Claude)\n"
            "  `sk-...`     — OpenAI (GPT)\n"
            "  `AI...`      — Google (Gemini)\n"
            "  `gsk_...`    — Groq (fast Llama)\n\n"
            "Try: `setup ai sk-ant-your-key-here`"
        )

    provider = CLOUD_PROVIDERS[provider_name]

    # Privacy warning for OpenAI
    openai_warning = ""
    if provider_name == "openai":
        openai_warning = (
            "\n**Warning:** OpenAI has contracted for domestic surveillance "
            "with the Pentagon. Are you sure you want to use this service?\n"
        )

    provider_config = {
        "label": provider["label"],
        "provider": provider["provider"],
        "api_key": api_key.strip(),
        "model": provider["model"],
        "temperature": provider["temperature"],
        "max_tokens": provider["max_tokens"],
    }

    if _update_config(config_path, provider_config):
        return (
            f"{openai_warning}\n"
            f"**Done!** {provider_name.title()} configured.\n\n"
            f"Provider: **{provider_name}**\n"
            f"Model: **{provider['model']}**\n\n"
            "You can now use AI features:\n"
            "  `research <topic>` then `research analyze` — AI-powered research\n"
            "  `ai blog generate about technology` — AI blog posts\n"
            "  `code generate <description>` — AI code generation\n\n"
            "To change models or add more providers, edit config.yaml."
        )

    return (
        f"Could not update config. Add manually to config.yaml:\n"
        f"```yaml\n"
        f"ai_providers:\n"
        f'  - label: "{provider_name}"\n'
        f'    provider: "{provider_name}"\n'
        f'    api_key: "{api_key}"\n'
        f'    model: "{provider["model"]}"\n'
        f"```"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Local setup (Ollama)
# ──────────────────────────────────────────────────────────────────────────────


def is_ollama_installed() -> bool:
    """Check if Ollama is already installed."""
    return shutil.which("ollama") is not None


def get_installed_models() -> list[str]:
    """Get list of models already pulled in Ollama."""
    if not is_ollama_installed():
        return []
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            models = []
            for line in lines[1:]:
                parts = line.split()
                if parts:
                    models.append(parts[0])
            return models
    except Exception:
        pass
    return []


def is_ollama_running() -> bool:
    """Check if the Ollama server is running."""
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        return response.status_code == 200
    except Exception:
        return False


async def setup_local(
    model_preset: str = "default",
    config_path: Path | None = None,
) -> str:
    """
    Auto-setup local AI: install Ollama + pull model + configure SafeClaw.

    Args:
        model_preset: "small", "default", "large", "coding", "writing"
                      or a specific model name
        config_path: Path to config.yaml

    Returns:
        Status message
    """
    lines = ["**Local AI Setup (Ollama)**", ""]

    # Resolve model name
    if model_preset in LOCAL_MODELS:
        model_info = LOCAL_MODELS[model_preset]
        model_name = model_info["name"]
        lines.append(f"Model: **{model_name}** ({model_info['size']}) — {model_info['desc']}")
    else:
        model_name = model_preset
        lines.append(f"Model: **{model_name}**")
    lines.append("")

    # Step 1: Install Ollama
    lines.append("**Step 1: Install Ollama**")
    if is_ollama_installed():
        lines.append("  Already installed!")
    else:
        lines.append("  Installing...")
        system = platform.system().lower()
        if system == "linux" or system == "darwin":
            cmd = "curl -fsSL https://ollama.com/install.sh | sh"
        elif system == "windows":
            cmd = "winget install Ollama.Ollama"
        else:
            cmd = "curl -fsSL https://ollama.com/install.sh | sh"

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=300,
            )
            if process.returncode == 0:
                lines.append("  Installed!")
            else:
                error = stderr.decode().strip() if stderr else "Unknown error"
                lines.append(f"  Failed: {error}")
                lines.append(f"  Install manually: `{cmd}`")
                return "\n".join(lines)
        except TimeoutError:
            lines.append(f"  Timed out. Install manually: `{cmd}`")
            return "\n".join(lines)
        except Exception as e:
            lines.append(f"  Error: {e}")
            lines.append(f"  Install manually: `{cmd}`")
            return "\n".join(lines)
    lines.append("")

    # Step 2: Start Ollama
    lines.append("**Step 2: Start Ollama**")
    if is_ollama_running():
        lines.append("  Already running!")
    else:
        try:
            await asyncio.create_subprocess_exec(
                "ollama", "serve",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.sleep(2)
            lines.append("  Started!")
        except Exception:
            lines.append("  Run manually: `ollama serve`")
    lines.append("")

    # Step 3: Pull model
    lines.append(f"**Step 3: Download {model_name}**")
    models = get_installed_models()
    if any(model_name in m for m in models):
        lines.append("  Already downloaded!")
    else:
        lines.append("  Downloading... (this may take a few minutes)")
        try:
            process = await asyncio.create_subprocess_exec(
                "ollama", "pull", model_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=600,
            )
            if process.returncode == 0:
                lines.append("  Done!")
            else:
                lines.append(f"  Run manually: `ollama pull {model_name}`")
        except Exception:
            lines.append(f"  Run manually: `ollama pull {model_name}`")
    lines.append("")

    # Step 4: Configure
    lines.append("**Step 4: Configure SafeClaw**")
    cfg_path = config_path or Path("config/config.yaml")
    ollama_config = {
        "label": "local-ollama",
        "provider": "ollama",
        "model": model_name,
        "endpoint": "http://localhost:11434/api/chat",
        "temperature": 0.7,
        "max_tokens": 2000,
    }
    if _update_config(cfg_path, ollama_config):
        lines.append("  Config updated!")
    else:
        lines.append("  Add to config.yaml manually (see docs)")
    lines.append("")

    lines.extend([
        "---",
        "**Setup complete!** Local AI is ready.",
        "All AI runs on your machine. No API keys, no cloud, $0 cost.",
    ])

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────


async def auto_setup(
    arg: str = "",
    config_path: Path | None = None,
) -> str:
    """
    Main entry point for `setup ai` / `install llm`.

    Smart routing:
    - `setup ai sk-ant-...`     → configure Anthropic with that key
    - `setup ai sk-...`         → configure OpenAI with that key
    - `setup ai local`          → install Ollama + model
    - `setup ai local coding`   → install Ollama + codellama
    - `setup ai`                → show help with options

    Args:
        arg: User's argument after "setup ai" / "install llm"
        config_path: Path to config.yaml

    Returns:
        Status message
    """
    arg = arg.strip()
    cfg = config_path or Path("config/config.yaml")

    # No argument — show help
    if not arg:
        return _help()

    # Looks like an API key — set it up
    if (arg.startswith("sk-") or arg.startswith("AI") or arg.startswith("gsk_")):
        return setup_with_key(arg, cfg)

    # "local" — set up Ollama
    if arg.startswith("local"):
        parts = arg.split(None, 1)
        model_preset = parts[1] if len(parts) > 1 else "default"
        return await setup_local(model_preset, cfg)

    # "status" — show current setup
    if arg == "status":
        return get_status(cfg)

    # "task <task> <provider>" — per-task routing
    if arg.startswith("task"):
        rest = arg[4:].strip()
        parts = rest.split(None, 1)
        task = parts[0] if parts else ""
        provider = parts[1].strip() if len(parts) > 1 else ""
        # "default" clears routing for that task
        if provider == "default":
            provider = ""
            # Remove from config
            try:
                if cfg.exists():
                    with open(cfg) as f:
                        config = yaml.safe_load(f) or {}
                    tp = config.get("task_providers") or {}
                    tp.pop(task, None)
                    config["task_providers"] = tp
                    with open(cfg, "w") as f:
                        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                return f"Cleared per-task routing for '{task}'. It will use the active provider."
            except Exception as e:
                return f"Could not update config: {e}"
        return setup_task_provider(task, provider, cfg)

    # Could be a model preset for local
    if arg in LOCAL_MODELS:
        return await setup_local(arg, cfg)

    # Maybe it's an API key without a recognized prefix
    if len(arg) > 20:
        return (
            "That looks like it might be an API key, but I can't tell which provider.\n\n"
            "Supported formats:\n"
            "  `setup ai sk-ant-...` — Anthropic\n"
            "  `setup ai sk-...`     — OpenAI\n"
            "  `setup ai AI...`      — Google\n"
            "  `setup ai gsk_...`    — Groq"
        )

    return _help()


def setup_task_provider(task: str, provider_label: str, config_path: Path) -> str:
    """
    Route a specific task to a named AI provider.

    Usage:
      setup ai task blog my-claude
      setup ai task research my-ollama
      setup ai task coding llama-coder
      setup ai task             ← show current routing
    """
    valid_tasks = ("blog", "research", "coding")

    if not task:
        # Show current routing
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            config = {}

        task_providers = config.get("task_providers", {}) or {}
        providers = config.get("ai_providers", []) or []
        available = [p.get("label") for p in providers if isinstance(p, dict) and p.get("label")]

        lines = ["**Per-task AI routing**", ""]
        for t in valid_tasks:
            assigned = task_providers.get(t, "— (uses active provider)")
            lines.append(f"  {t:<10}  {assigned}")
        lines.extend(["", f"Available providers: {', '.join(available) or 'none configured'}",
                       "", "Set with: setup ai task <blog|research|coding> <provider-label>"])
        return "\n".join(lines)

    task = task.lower()
    if task not in valid_tasks:
        return (
            f"Unknown task '{task}'. Valid tasks: {', '.join(valid_tasks)}\n\n"
            "Example: setup ai task blog my-claude"
        )

    if not provider_label:
        return f"Please provide a provider label.\nExample: setup ai task {task} my-claude"

    # Verify the provider exists in config
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
    except Exception as e:
        return f"Could not read config: {e}"

    providers = config.get("ai_providers", []) or []
    available = [p.get("label") for p in providers if isinstance(p, dict) and p.get("label")]
    if available and provider_label not in available:
        return (
            f"Provider '{provider_label}' not found.\n"
            f"Available: {', '.join(available)}\n\n"
            f"Set up a provider first with: setup ai sk-ant-..."
        )

    task_providers = config.get("task_providers") or {}
    task_providers[task] = provider_label
    config["task_providers"] = task_providers

    try:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return (
            f"**Done!** {task.title()} tasks will now use **{provider_label}**.\n\n"
            "Other tasks still use the active provider.\n"
            "Change again with: setup ai task {task} <other-label>\n"
            "Clear with: setup ai task {task} default"
        )
    except Exception as e:
        return f"Could not save config: {e}"


def setup_wolfram(app_id: str, config_path: Path) -> str:
    """
    Save a Wolfram Alpha App ID to config.

    Get a free key at: https://developer.wolframalpha.com/
    Usage: setup wolfram YOUR-APP-ID
    """
    if not app_id:
        return (
            "**Wolfram Alpha Setup**\n\n"
            "Get a free App ID at: https://developer.wolframalpha.com/\n\n"
            "Then run:\n"
            "  setup wolfram YOUR-APP-ID\n\n"
            "Wolfram Alpha answers maths, science, conversions, and factual questions."
        )

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        apis = config.get("apis") or {}
        apis["wolfram_alpha"] = app_id.strip()
        config["apis"] = apis

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return (
            "**Wolfram Alpha configured!**\n\n"
            "Try it:\n"
            "  research wolfram integrate x^2\n"
            "  research wolfram distance earth to moon\n"
            "  research wolfram GDP of Germany"
        )
    except Exception as e:
        return f"Could not save config: {e}"


def setup_telegram_allow(
    target: str,
    requester_id: str,
    config_path: Path,
) -> str:
    """
    Add a Telegram user ID to the allowed_users list.

    target       = "me"        → use requester_id (self-register from Telegram)
    target       = "list"      → show current allowlist
    target       = "123456789" → add that numeric ID explicitly
    requester_id               → the Telegram user_id of whoever sent the command
    """
    try:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
    except Exception as e:
        return f"Could not read config: {e}"

    channels = config.get("channels") or {}
    telegram_cfg = channels.get("telegram") or {}

    # ── list ──────────────────────────────────────────────────────────────
    if target.lower() == "list":
        allowed = telegram_cfg.get("allowed_users") or []
        if not allowed:
            return (
                "No user ID restrictions set — the bot is open to anyone who finds it.\n\n"
                "Send `setup telegram allow me` from Telegram to lock it to just you."
            )
        return "**Allowed Telegram user IDs:**\n" + "\n".join(f"  {uid}" for uid in allowed)

    # ── resolve ID ────────────────────────────────────────────────────────
    if target.lower() == "me":
        if not requester_id or not requester_id.isdigit():
            return (
                "Can't detect your ID from here.\n\n"
                "Send this command from your Telegram chat with the bot, or:\n"
                "  setup telegram allow <your-numeric-id>"
            )
        new_id = int(requester_id)
    elif target.isdigit():
        new_id = int(target)
    else:
        return (
            f"'{target}' is not a valid Telegram user ID.\n\n"
            "Usage:\n"
            "  setup telegram allow me          — self-register (send from Telegram)\n"
            "  setup telegram allow 123456789   — add by numeric ID\n"
            "  setup telegram allow list        — show current allowlist"
        )

    # ── add to list ───────────────────────────────────────────────────────
    allowed = list(telegram_cfg.get("allowed_users") or [])
    if new_id in allowed:
        return f"User ID {new_id} is already in the allowlist."

    allowed.append(new_id)
    telegram_cfg["allowed_users"] = allowed
    channels["telegram"] = telegram_cfg
    config["channels"] = channels

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        return f"Could not save config: {e}"

    is_self = target.lower() == "me"
    extra = " (that's you!)" if is_self else ""
    return (
        f"**Done.** User ID {new_id}{extra} added to the allowlist.\n\n"
        f"Bot now restricted to: {', '.join(str(u) for u in allowed)}\n\n"
        "Remove with: `setup telegram deny <id>`\n"
        "Show list:   `setup telegram allow list`"
    )


def setup_telegram_deny(target: str, config_path: Path) -> str:
    """Remove a Telegram user ID from the allowed_users list."""
    if not target.isdigit():
        return (
            f"'{target}' is not a valid Telegram user ID.\n"
            "Usage: setup telegram deny 123456789"
        )

    remove_id = int(target)

    try:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            return "No config file found."
    except Exception as e:
        return f"Could not read config: {e}"

    channels = config.get("channels") or {}
    telegram_cfg = channels.get("telegram") or {}
    allowed = list(telegram_cfg.get("allowed_users") or [])

    if remove_id not in allowed:
        return f"User ID {remove_id} is not in the allowlist."

    allowed.remove(remove_id)
    telegram_cfg["allowed_users"] = allowed if allowed else None
    channels["telegram"] = telegram_cfg
    config["channels"] = channels

    try:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        return f"Could not save config: {e}"

    if not allowed:
        return (
            f"Removed {remove_id}. Allowlist is now empty — "
            "bot will respond to anyone."
        )
    return (
        f"Removed {remove_id}.\n"
        f"Remaining allowed IDs: {', '.join(str(u) for u in allowed)}"
    )


def setup_telegram(token: str, config_path: Path) -> str:
    """
    Save a Telegram bot token to config.

    Get a token from @BotFather on Telegram:
      1. Message @BotFather → /newbot
      2. Choose a name and username
      3. Copy the token here

    Usage: setup telegram 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
    """
    if not token:
        return (
            "**Telegram Bot Setup**\n\n"
            "1. Open Telegram and message **@BotFather**\n"
            "2. Send: /newbot\n"
            "3. Choose a name (e.g. My SafeClaw) and username (must end in 'bot')\n"
            "4. Copy the token BotFather gives you\n"
            "5. Run:\n"
            "   setup telegram <your-token>\n\n"
            "Then restart SafeClaw — your bot will be live."
        )

    # Basic sanity check — Telegram tokens look like 1234567890:ABCdef...
    if ":" not in token or len(token) < 20:
        return (
            "That doesn't look like a valid Telegram token.\n"
            "Tokens look like:  1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ\n\n"
            "Get one from @BotFather on Telegram."
        )

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        channels = config.get("channels") or {}
        channels["telegram"] = {
            "enabled": True,
            "token": token.strip(),
        }
        config["channels"] = channels

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return (
            "**Telegram bot configured!**\n\n"
            "Install the Telegram library if you haven't:\n"
            "  pip install safeclaw[telegram]\n\n"
            "Then restart SafeClaw — your bot will start polling.\n\n"
            "**Restrict access to your user ID** (recommended):\n"
            "  Send this from your Telegram chat with the bot:\n"
            "    `setup telegram allow me`\n\n"
            "Other access commands:\n"
            "  `setup telegram allow list`        — view allowlist\n"
            "  `setup telegram allow 123456789`   — add a numeric ID\n"
            "  `setup telegram deny 123456789`    — remove an ID"
        )
    except Exception as e:
        return f"Could not save config: {e}"


def _help() -> str:
    """Return setup help text."""
    return (
        "**AI Setup**\n\n"
        "**Easiest: Enter your API key**\n"
        "  `setup ai sk-ant-your-key-here`  — Anthropic (Claude)\n"
        "  `setup ai sk-your-key-here`      — OpenAI (GPT)\n"
        "  `setup ai AI-your-key-here`      — Google (Gemini)\n"
        "  `setup ai gsk_your-key-here`     — Groq (fast, free tier)\n\n"
        "Get a key:\n"
        "  Anthropic: https://console.anthropic.com/settings/keys\n"
        "  OpenAI:    https://platform.openai.com/api-keys\n"
        "  Google:    https://aistudio.google.com/apikey\n"
        "  Groq:      https://console.groq.com/keys (free!)\n\n"
        "**Free & Local: Auto-install Ollama**\n"
        "  `setup ai local`           — Install Ollama + default model\n"
        "  `setup ai local small`     — Lightweight (1.3GB)\n"
        "  `setup ai local coding`    — Code-optimized\n"
        "  `setup ai local writing`   — Writing-optimized\n\n"
        "**Check status:**\n"
        "  `setup ai status`\n\n"
        "**Per-task routing (use different models for different tasks):**\n"
        "  `setup ai task blog my-claude`      — use Claude for blogging\n"
        "  `setup ai task research my-ollama`  — use Ollama for research\n"
        "  `setup ai task coding llama-coder`  — use a code model for coding\n"
        "  `setup ai task`                     — show current routing\n\n"
        "**Other integrations:**\n"
        "  `setup wolfram <app-id>`   — Wolfram Alpha (free key)\n"
        "  `setup telegram <token>`   — Telegram bot"
    )


def get_status(config_path: Path | None = None) -> str:
    """Get current AI setup status."""
    lines = ["**AI Status**", ""]

    # Check config for cloud providers
    cfg_path = config_path or Path("config/config.yaml")
    if cfg_path.exists():
        try:
            with open(cfg_path) as f:
                config = yaml.safe_load(f) or {}
            providers = config.get("ai_providers", [])
            if providers:
                lines.append("**Configured providers:**")
                for p in providers:
                    if isinstance(p, dict):
                        label = p.get("label", "unknown")
                        model = p.get("model", "unknown")
                        has_key = "yes" if p.get("api_key") else "no"
                        endpoint = p.get("endpoint", "cloud")
                        lines.append(f"  {label}: model={model}, key={has_key}, endpoint={endpoint}")
                lines.append("")
        except Exception:
            pass

    # Check Ollama
    if is_ollama_installed():
        lines.append("**Ollama:** installed")
        if is_ollama_running():
            lines.append("**Server:** running")
        else:
            lines.append("**Server:** not running (`ollama serve` to start)")
        models = get_installed_models()
        if models:
            lines.append(f"**Models:** {', '.join(models)}")
    else:
        lines.append("**Ollama:** not installed")

    if len(lines) == 2:  # Just header + blank
        lines.append("No AI configured yet. Run `setup ai` to get started.")

    return "\n".join(lines)
