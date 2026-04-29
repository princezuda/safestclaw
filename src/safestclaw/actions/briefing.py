"""Daily briefing action."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from safestclaw.actions.base import BaseAction
from safestclaw.core.feeds import Feed, FeedReader

if TYPE_CHECKING:
    from safestclaw.core.engine import SafestClaw


class BriefingAction(BaseAction):
    """
    Generate daily briefings.

    Aggregates:
    - Weather (if configured)
    - Calendar events (if configured)
    - Pending reminders
    - News headlines from RSS feeds (no API key needed!)
    """

    name = "briefing"
    description = "Generate daily briefing"

    def __init__(
        self,
        weather_api_key: str | None = None,
        location: str = "New York",
        news_limit: int = 5,
    ):
        self.weather_api_key = weather_api_key
        self.location = location
        self.news_limit = news_limit
        self.feed_reader = FeedReader(
            summarize_items=False,  # Don't summarize for briefing (keep it short)
            max_items_per_feed=3,
        )

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: "SafestClaw",
    ) -> str:
        """Generate briefing."""
        now = datetime.now()
        greeting = self._get_greeting(now)

        sections = [
            f"**{greeting}!**",
            f"*{now.strftime('%A, %B %d, %Y')}*",
            "",
        ]

        # Weather
        weather = await self._get_weather()
        if weather:
            sections.extend(["**Weather:**", weather, ""])

        # Reminders
        reminders = await self._get_reminders(user_id, engine)
        if reminders:
            sections.extend(["**Today's Reminders:**", reminders, ""])

        # News from RSS feeds (no API key needed!)
        news = await self._get_news_from_feeds(user_id, engine)
        if news:
            sections.extend(["**Headlines:**", news, ""])

        return "\n".join(sections)

    def _get_greeting(self, now: datetime) -> str:
        """Get time-appropriate greeting."""
        hour = now.hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

    async def _get_weather(self) -> str | None:
        """Get weather summary."""
        if not self.weather_api_key:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "q": self.location,
                        "appid": self.weather_api_key,
                        "units": "metric",
                    },
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    return f"  {self.location}: {temp:.0f}°C, {desc}"

        except Exception:
            pass

        return None

    async def _get_reminders(self, user_id: str, engine: "SafestClaw") -> str | None:
        """Get today's reminders."""
        reminders = await engine.memory.get_pending_reminders()
        user_reminders = [r for r in reminders if r["user_id"] == user_id]

        if not user_reminders:
            return None

        lines = []
        for r in user_reminders[:5]:
            time_fmt = r["trigger_at"].strftime("%I:%M %p")
            lines.append(f"  • {time_fmt}: {r['task']}")

        return "\n".join(lines)

    async def _get_news_from_feeds(
        self,
        user_id: str,
        engine: "SafestClaw",
    ) -> str | None:
        """Get news headlines from RSS feeds."""
        # Load user's feed preferences
        prefs = await engine.memory.get_preference(user_id, "news_feeds", {})

        # Load enabled categories
        if "categories" in prefs:
            self.feed_reader.enabled_categories = set(prefs["categories"])
        else:
            # Default to tech news if no preferences set
            self.feed_reader.enabled_categories = {"tech"}

        # Load custom feeds
        if "custom_feeds" in prefs:
            self.feed_reader.custom_feeds = [
                Feed(**f) for f in prefs["custom_feeds"]
            ]

        try:
            items = await self.feed_reader.fetch_all_enabled()
            items = items[:self.news_limit]

            if not items:
                return None

            lines = []
            for item in items:
                lines.append(f"  • {item.title}")
                lines.append(f"    _{item.feed_name}_")

            return "\n".join(lines)

        except Exception:
            return None
