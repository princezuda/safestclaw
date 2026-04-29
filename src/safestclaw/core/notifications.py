"""
SafestClaw Notifications - Desktop and system notifications.

Cross-platform support using desktop-notifier.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

try:
    from desktop_notifier import Button, DesktopNotifier, Urgency
    HAS_NOTIFIER = True
except ImportError:
    HAS_NOTIFIER = False
    logger.warning("desktop-notifier not installed")


class NotificationPriority(StrEnum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    """A notification to display."""
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    icon: str | None = None
    sound: bool = True
    actions: list[tuple[str, Callable]] | None = None
    timeout: int | None = None  # seconds, None = system default


class NotificationManager:
    """
    Cross-platform notification manager.

    Features:
    - Desktop notifications (macOS, Windows, Linux)
    - Priority levels
    - Action buttons
    - Notification history
    - Rate limiting
    """

    def __init__(
        self,
        app_name: str = "SafestClaw",
        rate_limit: float = 1.0,  # Min seconds between notifications
    ):
        self.app_name = app_name
        self.rate_limit = rate_limit
        self._last_notification = 0.0
        self._history: list[dict[str, Any]] = []

        if HAS_NOTIFIER:
            self._notifier = DesktopNotifier(app_name=app_name)
        else:
            self._notifier = None

    async def send(self, notification: Notification) -> bool:
        """
        Send a notification.

        Returns True if sent successfully.
        """
        # Rate limiting
        now = datetime.now().timestamp()
        if now - self._last_notification < self.rate_limit:
            logger.debug("Notification rate limited")
            return False

        self._last_notification = now

        # Record in history
        self._history.append({
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority.value,
            "timestamp": datetime.now().isoformat(),
        })

        # Trim history
        if len(self._history) > 100:
            self._history = self._history[-100:]

        if not self._notifier:
            logger.warning(f"[NOTIFICATION] {notification.title}: {notification.message}")
            return True

        try:
            # Map priority to urgency
            urgency_map = {
                NotificationPriority.LOW: Urgency.Low,
                NotificationPriority.NORMAL: Urgency.Normal,
                NotificationPriority.HIGH: Urgency.Normal,
                NotificationPriority.URGENT: Urgency.Critical,
            }
            urgency = urgency_map.get(notification.priority, Urgency.Normal)

            # Create buttons if actions provided
            buttons = []
            if notification.actions:
                for label, callback in notification.actions[:3]:  # Max 3 buttons
                    buttons.append(Button(title=label, on_pressed=callback))

            await self._notifier.send(
                title=notification.title,
                message=notification.message,
                urgency=urgency,
                buttons=buttons if buttons else None,
                sound=notification.sound,
            )

            logger.debug(f"Notification sent: {notification.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    async def notify(
        self,
        title: str,
        message: str,
        priority: str = "normal",
        sound: bool = True,
    ) -> bool:
        """Simple notification helper."""
        try:
            prio = NotificationPriority(priority.lower())
        except ValueError:
            prio = NotificationPriority.NORMAL

        return await self.send(Notification(
            title=title,
            message=message,
            priority=prio,
            sound=sound,
        ))

    async def notify_reminder(self, task: str) -> bool:
        """Send a reminder notification."""
        return await self.notify(
            title="⏰ Reminder",
            message=task,
            priority="high",
            sound=True,
        )

    async def notify_news(self, headline: str, source: str) -> bool:
        """Send a news notification."""
        return await self.notify(
            title=f"📰 {source}",
            message=headline,
            priority="low",
            sound=False,
        )

    async def notify_email(self, sender: str, subject: str) -> bool:
        """Send an email notification."""
        return await self.notify(
            title=f"📧 New email from {sender}",
            message=subject,
            priority="normal",
            sound=True,
        )

    async def notify_error(self, error: str) -> bool:
        """Send an error notification."""
        return await self.notify(
            title="❌ Error",
            message=error,
            priority="high",
            sound=True,
        )

    async def notify_success(self, message: str) -> bool:
        """Send a success notification."""
        return await self.notify(
            title="✅ Success",
            message=message,
            priority="normal",
            sound=False,
        )

    def get_history(self, limit: int = 20) -> list[dict]:
        """Get notification history."""
        return self._history[-limit:]

    def clear_history(self) -> None:
        """Clear notification history."""
        self._history = []

    @property
    def is_available(self) -> bool:
        """Check if notifications are available."""
        return HAS_NOTIFIER and self._notifier is not None
