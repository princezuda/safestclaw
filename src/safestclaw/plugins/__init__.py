"""
SafestClaw Plugin System.

Plugins extend SafestClaw with new actions and intents.

Directory structure:
- plugins/official/  - Curated, tested plugins
- plugins/community/ - User-contributed plugins

To create a plugin, see plugins/base.py for documentation.
"""

from safestclaw.plugins.base import BasePlugin, PluginInfo
from safestclaw.plugins.loader import PluginLoader

__all__ = ["BasePlugin", "PluginInfo", "PluginLoader"]
