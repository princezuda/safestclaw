"""
SafestClaw Calendar Action - ICS/CalDAV calendar support.

Supports:
- Reading .ics files
- Parsing calendar events
- CalDAV server sync (Google, iCloud, etc.)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from safestclaw.actions.base import BaseAction

logger = logging.getLogger(__name__)

# Try imports
try:
    from icalendar import Calendar as ICalendar
    from icalendar import Event as ICalEvent
    HAS_ICALENDAR = True
except ImportError:
    HAS_ICALENDAR = False
    logger.warning("icalendar not installed")

try:
    import caldav
    HAS_CALDAV = True
except ImportError:
    HAS_CALDAV = False

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    uid: str
    summary: str
    description: str
    location: str
    start: datetime
    end: datetime
    all_day: bool
    recurring: bool
    organizer: str
    attendees: list[str]

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def is_today(self) -> bool:
        today = datetime.now().date()
        return self.start.date() == today

    @property
    def is_upcoming(self) -> bool:
        return self.start > datetime.now()


class CalendarParser:
    """
    Parse ICS/iCalendar files.

    No API keys required - standard format.
    """

    def __init__(self):
        if not HAS_ICALENDAR:
            raise ImportError("icalendar not installed. Run: pip install icalendar")

    def parse_file(self, path: str | Path) -> list[CalendarEvent]:
        """Parse an .ics file."""
        path = Path(path)

        if not path.exists():
            logger.error(f"File not found: {path}")
            return []

        with open(path, 'rb') as f:
            return self.parse_ics(f.read())

    def parse_ics(self, content: bytes | str) -> list[CalendarEvent]:
        """Parse ICS content."""
        if isinstance(content, str):
            content = content.encode('utf-8')

        try:
            cal = ICalendar.from_ical(content)
        except Exception as e:
            logger.error(f"Failed to parse ICS: {e}")
            return []

        events = []

        for component in cal.walk():
            if component.name == "VEVENT":
                event = self._parse_event(component)
                if event:
                    events.append(event)

        # Sort by start time
        events.sort(key=lambda e: e.start)

        return events

    def _parse_event(self, component) -> CalendarEvent | None:
        """Parse a VEVENT component."""
        try:
            # Get UID
            uid = str(component.get('uid', ''))

            # Get summary (title)
            summary = str(component.get('summary', 'Untitled'))

            # Get description
            description = str(component.get('description', ''))

            # Get location
            location = str(component.get('location', ''))

            # Get start/end times
            dtstart = component.get('dtstart')
            dtend = component.get('dtend')

            if not dtstart:
                return None

            start = dtstart.dt
            all_day = False

            # Check if all-day event (date vs datetime)
            if not isinstance(start, datetime):
                all_day = True
                start = datetime.combine(start, datetime.min.time())

            if dtend:
                end = dtend.dt
                if not isinstance(end, datetime):
                    end = datetime.combine(end, datetime.min.time())
            else:
                # Default duration of 1 hour
                end = start + timedelta(hours=1)

            # Make timezone-naive for comparison
            if start.tzinfo:
                start = start.replace(tzinfo=None)
            if end.tzinfo:
                end = end.replace(tzinfo=None)

            # Get organizer
            organizer = ""
            org = component.get('organizer')
            if org:
                organizer = str(org).replace('mailto:', '')

            # Get attendees
            attendees = []
            for att in component.get('attendee', []):
                attendees.append(str(att).replace('mailto:', ''))

            # Check if recurring
            recurring = component.get('rrule') is not None

            return CalendarEvent(
                uid=uid,
                summary=summary,
                description=description,
                location=location,
                start=start,
                end=end,
                all_day=all_day,
                recurring=recurring,
                organizer=organizer,
                attendees=attendees,
            )

        except Exception as e:
            logger.error(f"Failed to parse event: {e}")
            return None

    def filter_by_date_range(
        self,
        events: list[CalendarEvent],
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        """Filter events by date range."""
        return [
            e for e in events
            if e.start >= start and e.start <= end
        ]

    def get_today_events(self, events: list[CalendarEvent]) -> list[CalendarEvent]:
        """Get events for today."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.filter_by_date_range(events, today, tomorrow)

    def get_upcoming_events(
        self,
        events: list[CalendarEvent],
        days: int = 7,
    ) -> list[CalendarEvent]:
        """Get upcoming events for next N days."""
        now = datetime.now()
        end = now + timedelta(days=days)
        return self.filter_by_date_range(events, now, end)


class CalendarAction(BaseAction):
    """
    Calendar action for SafestClaw.

    Commands:
    - show calendar / today / schedule
    - upcoming events
    - import calendar file.ics
    """

    name = "calendar"
    description = "View and manage calendar events"

    def __init__(self, allowed_paths: list[str] | None = None):
        self._parser: CalendarParser | None = None
        self._events: list[CalendarEvent] = []
        # Default to home directory for security
        self.allowed_paths = [
            Path(p).expanduser().resolve()
            for p in (allowed_paths or ["~"])
        ]

    def _is_allowed_path(self, path: Path) -> bool:
        """Check if path is within allowed directories."""
        try:
            resolved = path.expanduser().resolve()
            for allowed in self.allowed_paths:
                try:
                    if resolved == allowed or resolved.is_relative_to(allowed):
                        return True
                except ValueError:
                    continue
            return False
        except (OSError, ValueError):
            return False

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Execute calendar action."""
        if not HAS_ICALENDAR:
            return "Calendar support not installed. Run: pip install icalendar"

        self._parser = CalendarParser()

        subcommand = params.get("subcommand", "today")

        # Load cached events
        cached = await engine.memory.get(f"calendar_{user_id}")
        if cached:
            # Reconstruct events from cached data
            self._events = []
            for e in cached:
                try:
                    self._events.append(CalendarEvent(
                        uid=e['uid'],
                        summary=e['summary'],
                        description=e.get('description', ''),
                        location=e.get('location', ''),
                        start=datetime.fromisoformat(e['start']),
                        end=datetime.fromisoformat(e['end']),
                        all_day=e.get('all_day', False),
                        recurring=e.get('recurring', False),
                        organizer=e.get('organizer', ''),
                        attendees=e.get('attendees', []),
                    ))
                except Exception:
                    pass

        if subcommand == "today":
            return self._show_today()
        elif subcommand == "upcoming":
            days = params.get("days", 7)
            return self._show_upcoming(days)
        elif subcommand == "import":
            path = params.get("path", "")
            return await self._import_file(path, user_id, engine)
        elif subcommand == "week":
            return self._show_upcoming(7)
        else:
            return self._show_today()

    def _show_today(self) -> str:
        """Show today's events."""
        if not self._events:
            return "📅 No calendar imported. Use `calendar import file.ics`"

        today_events = self._parser.get_today_events(self._events)

        if not today_events:
            return "📅 No events scheduled for today."

        lines = [f"📅 **Today's Schedule** ({len(today_events)} events)", ""]

        for event in today_events:
            if event.all_day:
                time_str = "All day"
            else:
                time_str = event.start.strftime("%H:%M")
                if event.end:
                    time_str += f" - {event.end.strftime('%H:%M')}"

            lines.append(f"**{time_str}** - {event.summary}")
            if event.location:
                lines.append(f"  📍 {event.location}")
            if event.description:
                lines.append(f"  _{event.description[:100]}_")
            lines.append("")

        return "\n".join(lines)

    def _show_upcoming(self, days: int) -> str:
        """Show upcoming events."""
        if not self._events:
            return "📅 No calendar imported. Use `calendar import file.ics`"

        upcoming = self._parser.get_upcoming_events(self._events, days)

        if not upcoming:
            return f"📅 No events in the next {days} days."

        lines = [f"📅 **Upcoming Events** (next {days} days)", ""]

        current_date = None
        for event in upcoming:
            event_date = event.start.date()

            # Add date header
            if event_date != current_date:
                current_date = event_date
                date_str = event_date.strftime("%A, %B %d")
                lines.append(f"**{date_str}**")

            if event.all_day:
                time_str = "All day"
            else:
                time_str = event.start.strftime("%H:%M")

            lines.append(f"  • {time_str} - {event.summary}")
            if event.location:
                lines.append(f"    📍 {event.location}")

        lines.append("")
        return "\n".join(lines)

    async def _import_file(
        self,
        path: str,
        user_id: str,
        engine: "SafestClaw",
    ) -> str:
        """Import a calendar file."""
        if not path:
            return "Please specify a path to an .ics file."

        file_path = Path(path).expanduser()

        # Security: validate path is within allowed directories
        if not self._is_allowed_path(file_path):
            return f"Access denied: {path} is outside allowed directories"

        if not file_path.exists():
            return f"File not found: {file_path}"

        if not file_path.suffix.lower() == '.ics':
            return "Only .ics files are supported."

        events = self._parser.parse_file(file_path)

        if not events:
            return "No events found in the file."

        self._events = events

        # Cache events
        cached_data = [
            {
                'uid': e.uid,
                'summary': e.summary,
                'description': e.description,
                'location': e.location,
                'start': e.start.isoformat(),
                'end': e.end.isoformat(),
                'all_day': e.all_day,
                'recurring': e.recurring,
                'organizer': e.organizer,
                'attendees': e.attendees,
            }
            for e in events
        ]

        await engine.memory.set(f"calendar_{user_id}", cached_data)

        return f"✅ Imported {len(events)} events from {file_path.name}"
