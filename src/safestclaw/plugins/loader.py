"""
SafestClaw Plugin Loader - Discovers and loads plugins from directories.
"""

import importlib.util
import logging
from pathlib import Path
from typing import Any

from safestclaw.core.parser import IntentPattern
from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Discovers and loads plugins from the plugins directories.

    Scans:
    - plugins/official/ - Curated, tested plugins
    - plugins/community/ - User-contributed plugins
    - Custom paths via load_from_path()
    """

    def __init__(self):
        self.plugins: dict[str, BasePlugin] = {}
        self._plugin_dir = Path(__file__).parent

    def discover_plugins(self) -> list[str]:
        """
        Discover all available plugins.

        Returns list of plugin names found.
        """
        found = []

        # Scan official and community directories
        for subdir in ["official", "community"]:
            plugin_path = self._plugin_dir / subdir
            if plugin_path.exists():
                for py_file in plugin_path.glob("*.py"):
                    if py_file.name.startswith("_"):
                        continue
                    found.append(f"{subdir}/{py_file.stem}")

        return found

    def load_all(self, engine: Any) -> dict[str, BasePlugin]:
        """
        Load all discovered plugins.

        Returns dict of loaded plugins {name: instance}.
        """
        discovered = self.discover_plugins()

        for plugin_path in discovered:
            try:
                self.load_plugin(plugin_path, engine)
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_path}: {e}")

        return self.plugins

    def load_plugin(
        self,
        plugin_path: str,
        engine: Any,
    ) -> BasePlugin | None:
        """
        Load a single plugin by path.

        Args:
            plugin_path: Path like "official/smarthome" or "community/myplugin"
            engine: SafestClaw engine instance

        Returns:
            Loaded plugin instance or None if failed
        """
        # Parse path
        parts = plugin_path.split("/")
        if len(parts) == 2:
            subdir, name = parts
            file_path = self._plugin_dir / subdir / f"{name}.py"
        else:
            # Direct file path
            file_path = Path(plugin_path)
            name = file_path.stem

        if not file_path.exists():
            logger.error(f"Plugin file not found: {file_path}")
            return None

        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(name, file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Could not load spec for {file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find plugin class (subclass of BasePlugin)
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                ):
                    plugin_class = attr
                    break

            if plugin_class is None:
                logger.error(f"No BasePlugin subclass found in {file_path}")
                return None

            # Instantiate and register
            instance = plugin_class()
            plugin_name = instance.info.name

            # Call on_load hook
            instance.on_load(engine)

            # Register with engine
            engine.register_action(plugin_name, instance.execute)

            # Register intent pattern with parser if defined
            intent_data = plugin_class.get_intent_pattern()
            if intent_data:
                pattern = IntentPattern(
                    intent=intent_data["intent"],
                    keywords=intent_data["keywords"],
                    patterns=intent_data["patterns"],
                    examples=intent_data["examples"],
                    slots=intent_data.get("slots", []),
                )
                engine.parser.register_intent(pattern)

            self.plugins[plugin_name] = instance
            logger.info(f"Loaded plugin: {plugin_name} v{instance.info.version}")
            return instance

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_path}: {e}")
            return None

    def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin by name.

        Returns True if successfully unloaded.
        """
        if name not in self.plugins:
            return False

        plugin = self.plugins[name]
        plugin.on_unload()
        del self.plugins[name]
        logger.info(f"Unloaded plugin: {name}")
        return True

    def get_plugin(self, name: str) -> BasePlugin | None:
        """Get a loaded plugin by name."""
        return self.plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """List all loaded plugins with their info."""
        return [p.info for p in self.plugins.values()]
