"""
Stable config-path resolution.

Historical bug: callers used the relative ``Path("config/config.yaml")`` as
the default path. Whenever SafestClaw ran from a different working
directory — Task Scheduler / systemd / launchd entries, cron, a shortcut,
a fresh terminal in a different folder — that relative path landed on a
different file, so previously-saved LLM keys, Telegram tokens, and the
`setup_completed` flag effectively vanished. Each launch felt like a
fresh install.

This module centralises the resolution. The new stable default is
``~/.safestclaw/config.yaml`` — the same parent directory we already use
for the SQLite memory db. Any legacy ``./config/config.yaml`` is
migrated on first use so existing setups don't lose their state.

Resolution order:
  1. Explicit path passed by the caller (e.g. ``safestclaw --config …``).
  2. ``~/.safestclaw/config.yaml`` if it exists.
  3. ``./config/config.yaml`` if it exists — copied to (2) and used.
  4. ``~/.safestclaw/config.yaml`` (created on first write).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HOME_CONFIG = Path.home() / ".safestclaw" / "config.yaml"
LEGACY_LOCAL_CONFIG = Path("config/config.yaml")


def default_config_path() -> Path:
    """Return the SafestClaw config path used when none is specified.

    Migrates a legacy ``./config/config.yaml`` to
    ``~/.safestclaw/config.yaml`` on first call so users who set up the
    bot under the old project-local layout keep their settings the next
    time they launch from a different directory.
    """
    home = DEFAULT_HOME_CONFIG
    if home.exists():
        return home

    legacy = LEGACY_LOCAL_CONFIG
    try:
        legacy_resolved = legacy.resolve()
    except OSError:
        legacy_resolved = legacy

    if legacy.exists() and legacy_resolved != home:
        try:
            home.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, home)
            logger.info(
                "Migrated config %s → %s so settings persist across launches.",
                legacy_resolved, home,
            )
        except Exception as e:
            logger.warning("Could not migrate legacy config to %s: %s", home, e)

    return home


def resolve_config_path(explicit: Path | None) -> Path:
    """Return the path to read/write, given an optional ``--config`` value."""
    if explicit is not None:
        return Path(explicit)
    return default_config_path()
