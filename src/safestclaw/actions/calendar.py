"""
SafestClaw Calendar Action - ICS/CalDAV calendar support.

Supports:
- Reading .ics files
- Parsing calendar events
- CalDAV server sync (Google, iCloud, Nextcloud, Radicale, etc.)
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


class CalDAVClient:
    """
    Sync events from a CalDAV server.

    Works with Nextcloud, Radicale, iCloud, Fastmail, Google Calendar
    (via app password + caldav.icloud.com-style endpoint), etc.
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        calendar_name: str | None = None,
    ):
        if not HAS_CALDAV:
            raise ImportError(
                "caldav not installed. Run: pip install caldav "
                "(or, from a checkout: pip install -e \".[caldav]\")"
            )
        self.url = url
        self.username = username
        self.password = password
        self.calendar_name = calendar_name

    def _connect(self):
        return caldav.DAVClient(
            url=self.url,
            username=self.username,
            password=self.password,
        )

    def list_calendars(self) -> list[str]:
        """Return the names of calendars available on the server."""
        client = self._connect()
        principal = client.principal()
        return [c.name or str(c.url) for c in principal.calendars()]

    def fetch_events(self, days: int = 30) -> list[CalendarEvent]:
        """
        Fetch events for the next N days from the configured CalDAV calendar.

        If no `calendar_name` was given, all calendars on the principal
        are merged into a single list.
        """
        parser = CalendarParser()
        client = self._connect()
        principal = client.principal()

        calendars = principal.calendars()
        if self.calendar_name:
            calendars = [
                c for c in calendars
                if (c.name or "").lower() == self.calendar_name.lower()
            ]
            if not calendars:
                logger.warning(
                    f"CalDAV calendar '{self.calendar_name}' not found"
                )
                return []

        start = datetime.now()
        end = start + timedelta(days=days)

        all_events: list[CalendarEvent] = []
        for cal in calendars:
            try:
                results = cal.date_search(start=start, end=end, expand=True)
            except Exception as e:
                logger.warning(f"CalDAV search failed for {cal.name}: {e}")
                continue
            for item in results:
                try:
                    raw = item.data
                    if isinstance(raw, str):
                        raw = raw.encode("utf-8")
                    all_events.extend(parser.parse_ics(raw))
                except Exception as e:
                    logger.warning(f"Failed to parse CalDAV event: {e}")

        all_events.sort(key=lambda e: e.start)
        return all_events


class CalendarAction(BaseAction):
    """
    Calendar action for SafestClaw.

    Subcommands:
    - today / schedule  — events for today (default)
    - upcoming [N]      — events for next N days (default 7)
    - week              — alias for "upcoming 7"
    - import <path>     — import events from an .ics file
    - sync              — fetch from CalDAV (requires config)
    - calendars         — list calendars available on the CalDAV server
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

    @staticmethod
    def _parse_subcommand(raw: str) -> tuple[str, str]:
        """
        Extract a subcommand and its argument from free-form text like
        "calendar today", "show my schedule for tomorrow",
        "calendar import ~/cal.ics", "calendar upcoming 14", "calendar sync".

        Returns (subcommand, argument). Defaults to ("today", "").
        """
        if not raw:
            return "today", ""

        text = raw.strip().lower()
        for keyword in ("calendar", "schedule", "agenda"):
            if text.startswith(keyword + " "):
                text = text[len(keyword) + 1:].strip()
                break
            if text == keyword:
                text = ""
                break

        # Remove common filler so "show my upcoming events" still routes.
        for filler in ("show me ", "show ", "what's on ", "whats on ",
                       "what is on ", "my "):
            if text.startswith(filler):
                text = text[len(filler):].strip()

        if not text:
            return "today", ""

        first, _, rest = text.partition(" ")
        rest = rest.strip()

        if first in ("today", "schedule"):
            return "today", rest
        if first == "tomorrow":
            return "upcoming", "1"
        if first in ("upcoming", "next"):
            return "upcoming", rest
        if first == "week":
            return "week", rest
        if first == "import":
            return "import", rest
        if first in ("sync", "refresh", "pull"):
            return "sync", rest
        if first in ("calendars", "list"):
            return "calendars", rest

        return "today", text

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

        # Prefer explicit params (e.g. from MCP/CLI), fall back to raw_input.
        subcommand = params.get("subcommand")
        argument = ""

        if not subcommand:
            subcommand, argument = self._parse_subcommand(
                params.get("raw_input", "")
            )

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
            try:
                days = int(params.get("days") or argument or 7)
            except (TypeError, ValueError):
                days = 7
            return self._show_upcoming(days)
        elif subcommand == "import":
            path = params.get("path") or argument
            return await self._import_file(path, user_id, engine)
        elif subcommand == "week":
            return self._show_upcoming(7)
        elif subcommand == "sync":
            try:
                days = int(params.get("days") or argument or 30)
            except (TypeError, ValueError):
                days = 30
            return await self._sync_caldav(user_id, engine, days)
        elif subcommand == "calendars":
            return self._list_caldav_calendars(engine)
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

        await self._cache_events(user_id, engine)

        return f"✅ Imported {len(events)} events from {file_path.name}"

    # ------------------------------------------------------------------
    # CalDAV
    # ------------------------------------------------------------------

    def _build_caldav_client(self, engine: "SafestClaw") -> CalDAVClient | None:
        """Build a CalDAVClient from engine config, or return None."""
        cfg = ((engine.config.get("actions") or {}).get("calendar") or {}).get(
            "caldav"
        ) or {}
        url = cfg.get("url")
        username = cfg.get("username")
        password = cfg.get("password")
        calendar_name = cfg.get("calendar")

        if not (url and username and password):
            return None

        return CalDAVClient(
            url=url,
            username=username,
            password=password,
            calendar_name=calendar_name,
        )

    async def _sync_caldav(
        self,
        user_id: str,
        engine: "SafestClaw",
        days: int,
    ) -> str:
        """Pull events from a configured CalDAV server."""
        if not HAS_CALDAV:
            return (
                "CalDAV support not installed. "
                "Run: pip install caldav "
                "(or, from a checkout: pip install -e \".[caldav]\")"
            )

        client = self._build_caldav_client(engine)
        if client is None:
            return (
                "CalDAV not configured. Add to config.yaml:\n"
                "actions:\n"
                "  calendar:\n"
                "    caldav:\n"
                "      url: \"https://nextcloud.example.com/remote.php/dav\"\n"
                "      username: \"you\"\n"
                "      password: \"app-password\"\n"
                "      calendar: \"personal\"  # optional"
            )

        try:
            import asyncio
            events = await asyncio.to_thread(client.fetch_events, days)
        except Exception as e:
            logger.error(f"CalDAV sync failed: {e}")
            return f"CalDAV sync failed: {e}"

        if not events:
            return "📅 CalDAV sync completed — no events in that window."

        self._events = events
        await self._cache_events(user_id, engine)

        return f"✅ Synced {len(events)} events from CalDAV (next {days} days)"

    def _list_caldav_calendars(self, engine: "SafestClaw") -> str:
        """List calendar names on the configured CalDAV server."""
        if not HAS_CALDAV:
            return (
                "CalDAV support not installed. "
                "Run: pip install caldav "
                "(or, from a checkout: pip install -e \".[caldav]\")"
            )

        client = self._build_caldav_client(engine)
        if client is None:
            return "CalDAV not configured. See `calendar sync` for the config shape."

        try:
            names = client.list_calendars()
        except Exception as e:
            logger.error(f"CalDAV list failed: {e}")
            return f"CalDAV list failed: {e}"

        if not names:
            return "No calendars available on that CalDAV server."

        return "📅 Available calendars:\n" + "\n".join(f"  • {n}" for n in names)

    async def _cache_events(self, user_id: str, engine: "SafestClaw") -> None:
        """Persist current events to engine memory."""
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
            for e in self._events
        ]
        await engine.memory.set(f"calendar_{user_id}", cached_data)
