"""Reminder action."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import dateparser

from safestclaw.actions.base import BaseAction

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class ReminderAction(BaseAction):
    """
    Set and manage reminders.

    Uses dateparser for natural language time parsing.
    """

    name = "reminder"
    description = "Set reminders and alerts"

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute reminder action."""
        task = params.get("task", "")
        time_str = params.get("time", "")

        # Check for datetime in entities
        entities = params.get("entities", {})
        trigger_time = entities.get("datetime")

        if not task:
            return "What would you like to be reminded about?"

        # Parse time if not already parsed
        if not trigger_time and time_str:
            trigger_time = dateparser.parse(
                time_str,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": datetime.now(),
                }
            )

        if not trigger_time:
            # Default to 1 hour from now
            trigger_time = datetime.now() + timedelta(hours=1)

        # Ensure it's in the future
        if trigger_time <= datetime.now():
            return "Please specify a time in the future"

        # Store the reminder
        reminder_id = await engine.memory.add_reminder(
            user_id=user_id,
            channel=channel,
            task=task,
            trigger_at=trigger_time,
        )

        # Schedule the reminder
        async def send_reminder():
            # Get channel handler and send message
            if channel in engine.channels:
                ch = engine.channels[channel]
                if hasattr(ch, "send"):
                    await ch.send(user_id, f"⏰ Reminder: {task}")
            # Mark as complete
            await engine.memory.complete_reminder(reminder_id)

        engine.scheduler.add_one_time(
            name=f"reminder_{reminder_id}",
            func=send_reminder,
            run_at=trigger_time,
        )

        # Format response
        time_fmt = trigger_time.strftime("%B %d at %I:%M %p")
        return f"✓ Reminder set for {time_fmt}: {task}"

    async def list_reminders(
        self,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """List pending reminders for a user."""
        # Get all pending reminders
        reminders = await engine.memory.get_pending_reminders()

        # Filter by user
        user_reminders = [r for r in reminders if r["user_id"] == user_id]

        if not user_reminders:
            return "You have no pending reminders"

        lines = ["**Your reminders:**", ""]
        for r in user_reminders:
            time_fmt = r["trigger_at"].strftime("%B %d at %I:%M %p")
            lines.append(f"• {r['task']} - {time_fmt}")

        return "\n".join(lines)
