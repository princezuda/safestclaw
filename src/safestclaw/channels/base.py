"""Base class for SafestClaw channels."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class BaseChannel(ABC):
    """
    Base class for communication channels.

    Channels handle:
    - Receiving messages from users
    - Sending responses back
    - Channel-specific formatting
    """

    name: str = "base"

    def __init__(self, engine: "SafestClaw"):
        self.engine = engine

    @abstractmethod
    async def start(self) -> None:
        """Start the channel."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel."""
        pass

    @abstractmethod
    async def send(self, user_id: str, message: str) -> None:
        """Send a message to a user."""
        pass

    async def handle_message(self, text: str, user_id: str) -> str:
        """
        Handle incoming message and get response.

        This delegates to the engine for processing.
        """
        return await self.engine.handle_message(
            text=text,
            channel=self.name,
            user_id=user_id,
        )
