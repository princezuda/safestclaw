"""
SafeClaw LLM Auto-Installer - One-command local AI setup.

Makes it dead simple to get a local LLM running:
  1. Detects your platform (Linux, macOS, Windows)
  2. Installs Ollama (the easiest local LLM runtime)
  3. Pulls a model (default: llama3.1)
  4. Auto-configures SafeClaw to use it

No API keys. No cloud. No cost. Just type: install llm
"""

import asyncio
import logging
import platform
import shutil
import subprocess
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Recommended models by use case (smallest first)
RECOMMENDED_MODELS = {
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
            # Skip header line
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


def get_install_command() -> tuple[str, str]:
    """
    Get the appropriate Ollama install command for this platform.

    Returns:
        Tuple of (command, description)
    """
    system = platform.system().lower()

    if system == "linux":
        return (
            "curl -fsSL https://ollama.com/install.sh | sh",
            "Install Ollama on Linux (official installer)",
        )
    elif system == "darwin":  # macOS
        if shutil.which("brew"):
            return (
                "brew install ollama",
                "Install Ollama via Homebrew on macOS",
            )
        return (
            "curl -fsSL https://ollama.com/install.sh | sh",
            "Install Ollama on macOS (official installer)",
        )
    elif system == "windows":
        return (
            "winget install Ollama.Ollama",
            "Install Ollama via winget on Windows",
        )
    else:
        return (
            "curl -fsSL https://ollama.com/install.sh | sh",
            "Install Ollama (generic)",
        )


async def install_ollama() -> tuple[bool, str]:
    """
    Install Ollama on the current system.

    Returns:
        Tuple of (success, message)
    """
    if is_ollama_installed():
        return True, "Ollama is already installed!"

    command, desc = get_install_command()
    system = platform.system().lower()

    try:
        if system == "windows":
            # Windows: use winget
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            # Linux/macOS: use shell installer
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=300,  # 5 minute timeout
        )

        if process.returncode == 0:
            return True, "Ollama installed successfully!"
        else:
            error = stderr.decode().strip() if stderr else "Unknown error"
            return False, f"Installation failed: {error}"

    except TimeoutError:
        return False, "Installation timed out (5 minutes). Try running manually:\n" + command
    except Exception as e:
        return False, f"Installation error: {e}\n\nTry running manually:\n{command}"


async def pull_model(model: str = "llama3.1") -> tuple[bool, str]:
    """
    Pull a model in Ollama.

    Args:
        model: Model name (default: llama3.1)

    Returns:
        Tuple of (success, message)
    """
    if not is_ollama_installed():
        return False, "Ollama is not installed. Run `install llm` first."

    try:
        process = await asyncio.create_subprocess_exec(
            "ollama", "pull", model,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=600,  # 10 minute timeout for model download
        )

        if process.returncode == 0:
            return True, f"Model '{model}' downloaded successfully!"
        else:
            error = stderr.decode().strip() if stderr else "Unknown error"
            return False, f"Model pull failed: {error}"

    except TimeoutError:
        return False, f"Model download timed out. Try running manually:\n  ollama pull {model}"
    except Exception as e:
        return False, f"Error pulling model: {e}"


def update_config_for_ollama(
    config_path: Path,
    model: str = "llama3.1",
) -> bool:
    """
    Update SafeClaw config.yaml to enable Ollama as a provider.

    Args:
        config_path: Path to config.yaml
        model: Ollama model name

    Returns:
        True if config was updated
    """
    try:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        # Add Ollama to ai_providers
        providers = config.get("ai_providers", [])
        if providers is None:
            providers = []

        # Check if Ollama is already configured
        for provider in providers:
            if isinstance(provider, dict) and provider.get("provider") == "ollama":
                # Already configured, just update model
                provider["model"] = model
                with open(config_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                return True

        # Add new Ollama provider
        ollama_config = {
            "label": "local-ollama",
            "provider": "ollama",
            "model": model,
            "endpoint": "http://localhost:11434/api/chat",
            "temperature": 0.7,
            "max_tokens": 2000,
        }
        providers.append(ollama_config)
        config["ai_providers"] = providers

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return True

    except Exception as e:
        logger.error(f"Config update failed: {e}")
        return False


async def auto_setup(
    model: str = "default",
    config_path: Path | None = None,
) -> str:
    """
    Complete auto-setup: install Ollama + pull model + configure SafeClaw.

    This is the one-command experience: just type "install llm" and everything works.

    Args:
        model: Model preset ("small", "default", "large", "coding", "writing")
               or a specific model name
        config_path: Path to config.yaml (auto-detected if None)

    Returns:
        Status message
    """
    lines = ["**Auto LLM Setup**", ""]

    # Resolve model name
    if model in RECOMMENDED_MODELS:
        model_info = RECOMMENDED_MODELS[model]
        model_name = model_info["name"]
        lines.append(f"Model: **{model_name}** ({model_info['size']}) — {model_info['desc']}")
    else:
        model_name = model
        lines.append(f"Model: **{model_name}**")
    lines.append("")

    # Step 1: Install Ollama
    lines.append("**Step 1: Install Ollama**")
    if is_ollama_installed():
        lines.append("  Already installed!")
    else:
        lines.append("  Installing...")
        success, msg = await install_ollama()
        lines.append(f"  {msg}")
        if not success:
            lines.append("")
            lines.append("You can install manually:")
            cmd, _ = get_install_command()
            lines.append(f"  `{cmd}`")
            return "\n".join(lines)
    lines.append("")

    # Step 2: Start Ollama if not running
    lines.append("**Step 2: Start Ollama**")
    if is_ollama_running():
        lines.append("  Already running!")
    else:
        lines.append("  Starting Ollama server...")
        try:
            # Start Ollama in background
            await asyncio.create_subprocess_exec(
                "ollama", "serve",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Wait a moment for it to start
            await asyncio.sleep(2)
            if is_ollama_running():
                lines.append("  Started!")
            else:
                lines.append("  Server starting... (may take a few seconds)")
        except Exception as e:
            lines.append(f"  Could not auto-start: {e}")
            lines.append("  Run manually: `ollama serve`")
    lines.append("")

    # Step 3: Pull model
    lines.append(f"**Step 3: Download model ({model_name})**")
    models = get_installed_models()
    if any(model_name in m for m in models):
        lines.append("  Already downloaded!")
    else:
        lines.append(f"  Downloading {model_name}... (this may take a few minutes)")
        success, msg = await pull_model(model_name)
        lines.append(f"  {msg}")
        if not success:
            lines.append(f"  Run manually: `ollama pull {model_name}`")
    lines.append("")

    # Step 4: Configure SafeClaw
    lines.append("**Step 4: Configure SafeClaw**")
    cfg_path = config_path or Path("config/config.yaml")
    if update_config_for_ollama(cfg_path, model_name):
        lines.append("  Config updated! Ollama is now your AI provider.")
    else:
        lines.append("  Could not auto-update config. Add manually to config.yaml:")
        lines.append("  ```yaml")
        lines.append("  ai_providers:")
        lines.append('    - label: "local-ollama"')
        lines.append('      provider: "ollama"')
        lines.append(f'      model: "{model_name}"')
        lines.append('      endpoint: "http://localhost:11434/api/chat"')
        lines.append("  ```")
    lines.append("")

    # Done!
    lines.extend([
        "---",
        "**Setup complete!** You can now use AI features:",
        "  `ai blog generate about technology` — AI blog post",
        "  `research <topic>` then `research analyze` — AI research",
        "  `code generate <description>` — AI code generation",
        "",
        "All AI runs locally on your machine. No API keys, no cloud, $0 cost.",
    ])

    return "\n".join(lines)


def get_status() -> str:
    """Get current LLM setup status."""
    lines = ["**Local LLM Status**", ""]

    if is_ollama_installed():
        lines.append("Ollama: **installed**")

        if is_ollama_running():
            lines.append("Server: **running**")
        else:
            lines.append("Server: **not running** (start with `ollama serve`)")

        models = get_installed_models()
        if models:
            lines.append(f"Models: {', '.join(models)}")
        else:
            lines.append("Models: none downloaded (run `install llm`)")
    else:
        lines.append("Ollama: **not installed**")
        lines.append("")
        lines.append("Run `install llm` to set up local AI in one command.")

    lines.append("")
    lines.append("**Available model presets:**")
    for key, info in RECOMMENDED_MODELS.items():
        lines.append(f"  `install llm {key}` — {info['name']} ({info['size']}) — {info['desc']}")

    return "\n".join(lines)
