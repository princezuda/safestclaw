"""
SafestClaw Setup Wizard - First-run interactive configuration.

Guides users through choosing one of:
  1) Local-only       — no LLM, deterministic features only
  2) Cloud LLM        — single cloud provider (Anthropic/OpenAI/Google/Groq)
  3) Hybrid           — local Ollama + cloud, with per-task routing

Writes config/config.yaml and sets `safestclaw.setup_completed: true` so the
wizard does not prompt again on subsequent launches.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from safestclaw.core.llm_installer import (
    CLOUD_PROVIDERS,
    LOCAL_MODELS,
    _detect_provider,
    _update_config,
    is_ollama_installed,
    is_ollama_running,
    setup_local,
    setup_with_key,
)

DEFAULT_CONFIG_TEMPLATE = """# SafestClaw Configuration

safestclaw:
  name: "SafestClaw"
  language: "en"
  timezone: "UTC"
  setup_completed: true

# Channels
channels:
  cli:
    enabled: true
  webhook:
    enabled: true
    port: 8765
    host: "127.0.0.1"
  telegram:
    enabled: false
    token: ""
    allowed_users: []

# Actions
actions:
  shell:
    enabled: true
    sandboxed: true
    timeout: 30
  files:
    enabled: true
    allowed_paths:
      - "~"
      - "/tmp"
  browser:
    enabled: false

# Memory
memory:
  max_history: 1000
  retention_days: 365

# Optional API keys
apis:
  openweathermap: ""
  newsapi: ""
  wolfram_alpha: ""
"""

VALID_TASKS = ("blog", "research", "coding", "general")


def is_first_run(config_path: Path) -> bool:
    """True if no config exists or `safestclaw.setup_completed` is not set."""
    if not config_path.exists():
        return True
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        return True
    return not bool((config.get("safestclaw") or {}).get("setup_completed"))


def _ensure_default_config(config_path: Path) -> None:
    """Create a baseline config file if one doesn't exist."""
    if config_path.exists():
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG_TEMPLATE)


def _mark_completed(config_path: Path) -> None:
    """Set safestclaw.setup_completed: true in the config file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            config = {}
    sc = config.get("safestclaw") or {}
    sc["setup_completed"] = True
    config["safestclaw"] = sc
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def _save_task_routing(config_path: Path, routing: dict[str, str]) -> None:
    """Merge a task_providers mapping into config.yaml."""
    config: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    existing = config.get("task_providers") or {}
    existing.update({k: v for k, v in routing.items() if v})
    if existing:
        config["task_providers"] = existing
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def _list_provider_labels(config_path: Path) -> list[str]:
    """Return all provider labels currently in config.yaml."""
    if not config_path.exists():
        return []
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        return []
    providers = config.get("ai_providers") or []
    return [p.get("label") for p in providers if isinstance(p, dict) and p.get("label")]


def _welcome(console: Console) -> None:
    console.print(
        Panel.fit(
            "[bold]Welcome to SafestClaw[/bold]\n\n"
            "Privacy-first personal automation.\n"
            "All deterministic features (summarize, crawl, news, blog, calendar, etc.)\n"
            "work fully offline — no LLM required.\n\n"
            "This wizard will help you decide whether to add an LLM\n"
            "for blogging, research, and code generation.",
            title="SafestClaw Setup",
            border_style="cyan",
        )
    )


def _choose_mode(console: Console) -> int:
    """Prompt the user to pick one of the four modes."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]1[/bold]", "Local-only", "No LLM. Free, fully private. Recommended start.")
    table.add_row("[bold]2[/bold]", "Cloud LLM", "Anthropic / OpenAI / Google / Groq. Needs an API key.")
    table.add_row("[bold]3[/bold]", "Hybrid", "Local Ollama + cloud, with per-task routing.")
    table.add_row("[bold]4[/bold]", "Skip", "I'll edit config.yaml myself.")
    console.print()
    console.print(table)
    console.print()
    return IntPrompt.ask(
        "[bold]Choose a setup mode[/bold]",
        choices=["1", "2", "3", "4"],
        default=1,
        console=console,
    )


def _prompt_cloud_provider(console: Console) -> tuple[str, str] | None:
    """Ask which cloud provider to use and prompt for an API key.

    Returns (provider_name, api_key) on success, or None if the user skipped.
    """
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#")
    table.add_column("Provider")
    table.add_column("Default model")
    table.add_column("Key prefix")
    table.add_column("Get a key")
    options = list(CLOUD_PROVIDERS.items())
    for i, (name, info) in enumerate(options, start=1):
        table.add_row(
            str(i), name, info["model"], info["key_prefix"] + "…", info["key_url"]
        )
    console.print()
    console.print(table)
    console.print()

    choices = [str(i) for i in range(1, len(options) + 1)] + ["s"]
    raw = Prompt.ask(
        "[bold]Pick a provider[/bold] (or 's' to skip)",
        choices=choices,
        default="1",
        console=console,
    )
    if raw == "s":
        return None

    name, info = options[int(raw) - 1]
    key = Prompt.ask(
        f"Paste your [bold]{name}[/bold] API key (starts with [cyan]{info['key_prefix']}[/cyan])",
        password=True,
        console=console,
    ).strip()
    if not key:
        console.print("[yellow]No key entered — skipping this provider.[/yellow]")
        return None

    detected = _detect_provider(key)
    if detected and detected != name:
        console.print(
            f"[yellow]That key looks like a [bold]{detected}[/bold] key, "
            f"not [bold]{name}[/bold]. Saving as {detected}.[/yellow]"
        )
        name = detected
    elif not detected:
        if not Confirm.ask(
            f"Key prefix doesn't match {info['key_prefix']}. Save it anyway?",
            default=False,
            console=console,
        ):
            return None
    return name, key


def _prompt_local_model(console: Console) -> str:
    """Ask which Ollama preset to use."""
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#")
    table.add_column("Preset")
    table.add_column("Model")
    table.add_column("Size")
    table.add_column("Description")
    presets = list(LOCAL_MODELS.items())
    for i, (preset, info) in enumerate(presets, start=1):
        table.add_row(str(i), preset, info["name"], info["size"], info["desc"])
    console.print()
    console.print(table)
    console.print()
    raw = IntPrompt.ask(
        "[bold]Pick a local model[/bold]",
        choices=[str(i) for i in range(1, len(presets) + 1)],
        default=2,  # "default" preset
        console=console,
    )
    return presets[raw - 1][0]


def _prompt_task_routing(
    console: Console, available_labels: list[str]
) -> dict[str, str]:
    """Ask which provider to use for each task. Returns task -> label."""
    if len(available_labels) < 2:
        return {}

    console.print()
    console.print(
        Panel.fit(
            "Assign a provider to each task. Press Enter to use the default\n"
            "(first provider) — you can change this any time in config.yaml.",
            title="Per-task routing",
            border_style="cyan",
        )
    )

    routing: dict[str, str] = {}
    for task in VALID_TASKS:
        label = Prompt.ask(
            f"  [bold]{task:<9}[/bold] provider",
            choices=available_labels,
            default=available_labels[0],
            console=console,
        )
        routing[task] = label
    return routing


async def _run_cloud_mode(console: Console, config_path: Path) -> None:
    """Mode 2: pick a single cloud provider and save it."""
    result = _prompt_cloud_provider(console)
    if result is None:
        console.print("[yellow]Skipped cloud setup.[/yellow]")
        return
    name, key = result
    console.print()
    console.print(setup_with_key(key, config_path))


async def _run_hybrid_mode(console: Console, config_path: Path) -> None:
    """Mode 3: set up local Ollama, then a cloud provider, then route tasks."""
    console.print()
    console.print("[bold cyan]Step 1: Local AI (Ollama)[/bold cyan]")

    if is_ollama_installed():
        console.print(
            f"  Ollama already installed (running: {'yes' if is_ollama_running() else 'no'})."
        )
    else:
        console.print(
            "  Ollama is not installed. The next step will download and install it."
        )

    if Confirm.ask("Install / configure local Ollama now?", default=True, console=console):
        preset = _prompt_local_model(console)
        console.print()
        message = await setup_local(preset, config_path)
        console.print(message)
    else:
        console.print("[yellow]Skipped local setup.[/yellow]")

    console.print()
    console.print("[bold cyan]Step 2: Cloud provider[/bold cyan]")
    if Confirm.ask("Add a cloud LLM provider?", default=True, console=console):
        result = _prompt_cloud_provider(console)
        if result is not None:
            _, key = result
            console.print()
            console.print(setup_with_key(key, config_path))
        else:
            console.print("[yellow]Skipped cloud setup.[/yellow]")

    labels = _list_provider_labels(config_path)
    if len(labels) >= 2:
        routing = _prompt_task_routing(console, labels)
        if routing:
            _save_task_routing(config_path, routing)
            console.print("[green]Task routing saved.[/green]")
    elif labels:
        console.print(
            f"\n[dim]Only one provider configured ([bold]{labels[0]}[/bold]); "
            "skipping per-task routing.[/dim]"
        )


def _summary(console: Console, config_path: Path) -> None:
    """Print a final status summary."""
    labels = _list_provider_labels(config_path)
    lines = [f"Config file: [bold]{config_path}[/bold]"]
    if labels:
        lines.append(f"Providers:   {', '.join(labels)}")
    else:
        lines.append("Providers:   none (local-only — deterministic features ready)")
    lines.append("")
    lines.append("Run [bold]safestclaw[/bold] to start the interactive CLI.")
    lines.append("Run [bold]safestclaw setup[/bold] any time to re-run this wizard.")
    console.print()
    console.print(
        Panel.fit("\n".join(lines), title="Setup complete", border_style="green")
    )


async def run_wizard(
    config_path: Path,
    console: Console | None = None,
) -> None:
    """Run the interactive setup wizard.

    Writes a baseline config if none exists, then walks the user through
    choosing local-only / cloud / hybrid and (optionally) per-task routing.
    Marks `safestclaw.setup_completed: true` at the end so subsequent launches
    don't re-prompt.
    """
    console = console or Console()
    _ensure_default_config(config_path)
    _welcome(console)

    mode = _choose_mode(console)

    if mode == 1:
        console.print(
            "\n[green]Local-only mode selected.[/green] "
            "All deterministic features are ready to use."
        )
    elif mode == 2:
        await _run_cloud_mode(console, config_path)
    elif mode == 3:
        await _run_hybrid_mode(console, config_path)
    else:  # mode == 4
        console.print(
            "\n[yellow]Skipped setup.[/yellow] "
            f"Edit [bold]{config_path}[/bold] manually, then run "
            "[bold]safestclaw setup[/bold] when you're ready."
        )

    _mark_completed(config_path)
    _summary(console, config_path)


def offer_wizard_if_first_run(
    config_path: Path,
    console: Console | None = None,
) -> bool:
    """Return True if the wizard should run.

    Skipped silently when stdin is not a TTY (scripts, CI) or when the user
    declines. Marks setup as completed if the user declines, so we don't ask
    again next launch.
    """
    if not is_first_run(config_path):
        return False
    if not sys.stdin.isatty():
        return False
    console = console or Console()
    console.print()
    console.print(
        Panel.fit(
            "Looks like this is your first time running SafestClaw.\n"
            "I can walk you through picking local-only, cloud LLM, or hybrid.",
            title="First-run setup",
            border_style="cyan",
        )
    )
    if Confirm.ask("Run the setup wizard now?", default=True, console=console):
        return True
    console.print(
        "[dim]No worries — run [bold]safestclaw setup[/bold] any time.[/dim]"
    )
    _ensure_default_config(config_path)
    _mark_completed(config_path)
    return False
