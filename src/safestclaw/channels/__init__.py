"""SafestClaw channels - input/output adapters."""

from safestclaw.channels.base import BaseChannel
from safestclaw.channels.cli import CLIChannel

__all__ = ["BaseChannel", "CLIChannel"]
