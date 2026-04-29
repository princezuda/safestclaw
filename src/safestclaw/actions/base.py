"""Base class for SafestClaw actions."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class BaseAction(ABC):
    """
    Base class for all SafestClaw actions.

    Actions are the "verbs" - things SafestClaw can do:
    - Read/write files
    - Execute shell commands
    - Send emails
    - Control smart home devices
    - etc.
    """

    name: str = "base"
    description: str = "Base action"

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """
        Execute the action.

        Args:
            params: Parameters extracted from user command
            user_id: ID of the user who triggered the action
            channel: Channel the command came from
            engine: Reference to the SafestClaw engine

        Returns:
            Response message to send back to user
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate parameters before execution.

        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, ""
