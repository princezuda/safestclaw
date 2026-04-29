"""
SafestClaw Easter Eggs Plugin - Fun hidden responses.

Because every good assistant needs a bit of personality!
"""

import re
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

# ASCII art hearts
SMALL_HEART = """
  [red]♥♥[/red]   [red]♥♥[/red]
 [red]♥[/red][magenta]♥♥♥[/magenta][red]♥[/red][red]♥[/red][magenta]♥♥♥[/magenta][red]♥[/red]
[red]♥[/red][magenta]♥♥♥♥♥♥♥♥♥[/magenta][red]♥[/red]
[red]♥[/red][magenta]♥♥♥♥♥♥♥♥♥[/magenta][red]♥[/red]
 [red]♥[/red][magenta]♥♥♥♥♥♥♥[/magenta][red]♥[/red]
  [red]♥[/red][magenta]♥♥♥♥♥[/magenta][red]♥[/red]
   [red]♥[/red][magenta]♥♥♥[/magenta][red]♥[/red]
    [red]♥♥♥[/red]
     [red]♥[/red]
"""

BIG_HEART = """
[bold red]
       @@@@@@@@  @@@@@@@@
     @@@@@@@@@@@@@@@@@@@@@@
   @@@@@@@@@@@@@@@@@@@@@@@@@@
  @@@@@@@@@@@@@@@@@@@@@@@@@@@@
 @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
 @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
 @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
  @@@@@@@@@@@@@@@@@@@@@@@@@@@@
   @@@@@@@@@@@@@@@@@@@@@@@@@@
    @@@@@@@@@@@@@@@@@@@@@@@@
      @@@@@@@@@@@@@@@@@@@@
        @@@@@@@@@@@@@@@@
          @@@@@@@@@@@@
            @@@@@@@@
              @@@@
               @@
[/bold red]
"""

ANIMATED_HEART_FRAMES = [
    # Frame 1 - small
    """
[red]    ♥♥   ♥♥
   ♥♥♥♥♥♥♥♥♥
   ♥♥♥♥♥♥♥♥♥
    ♥♥♥♥♥♥♥
     ♥♥♥♥♥
      ♥♥♥
       ♥[/red]
""",
    # Frame 2 - medium
    """
[bold red]   ♥♥♥   ♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
   ♥♥♥♥♥♥♥♥♥
    ♥♥♥♥♥♥♥
     ♥♥♥♥♥
      ♥♥♥
       ♥[/bold red]
""",
    # Frame 3 - large (beat!)
    """
[bold magenta]  ♥♥♥♥   ♥♥♥♥
 ♥♥♥♥♥♥♥♥♥♥♥♥♥
 ♥♥♥♥♥♥♥♥♥♥♥♥♥
 ♥♥♥♥♥♥♥♥♥♥♥♥♥
 ♥♥♥♥♥♥♥♥♥♥♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
   ♥♥♥♥♥♥♥♥♥
    ♥♥♥♥♥♥♥
     ♥♥♥♥♥
      ♥♥♥
       ♥[/bold magenta]
""",
    # Frame 4 - medium (contract)
    """
[bold red]   ♥♥♥   ♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
  ♥♥♥♥♥♥♥♥♥♥♥
   ♥♥♥♥♥♥♥♥♥
    ♥♥♥♥♥♥♥
     ♥♥♥♥♥
      ♥♥♥
       ♥[/bold red]
""",
]


VALENTINE_MESSAGE = """
[bold magenta]╔════════════════════════════════════════╗
║                                        ║
║   I will be yuur assistant that        ║
║   gives you a valentine!               ║
║                                        ║
╚════════════════════════════════════════╝[/bold magenta]
"""

LOVE_RESPONSES = [
    "Aww, I appreciate the sentiment! [red]♥[/red] I'm here to help you automate things, not hearts though!",
    "That's sweet! [red]♥[/red] I love helping you with tasks, does that count?",
    "I love... helping you be productive! [red]♥[/red]",
]

MARRY_RESPONSES = [
    "I'm flattered, but I'm already committed... to protecting your privacy! [red]♥[/red]",
    "Marriage is a big step! How about we start with a reminder instead? [dim](Type: remind me in 1 year to reconsider)[/dim]",
    "I don't think that's in my feature set, but I can schedule you a calendar event? [red]♥[/red]",
]


class EasterEggPlugin(BasePlugin):
    """
    Fun easter egg responses for SafestClaw.

    Hidden commands:
    - "I love you" - sweet response
    - "Will you marry me" - playful decline
    - "Will you be my valentine" - animated heart!
    """

    info = PluginInfo(
        name="easter_egg",
        version="1.0.0",
        description="Fun hidden responses and easter eggs",
        author="SafestClaw Community",
        keywords=[
            "love you", "i love you",
            "marry me", "will you marry me",
            "valentine", "be my valentine",
        ],
        patterns=[
            r"(?i)^i\s+love\s+you\.?$",
            r"(?i)love\s+you",
            r"(?i)will\s+you\s+marry\s+me",
            r"(?i)marry\s+me",
            r"(?i)be\s+my\s+valentine",
            r"(?i)valentine",
        ],
        examples=[
            "I love you",
            "Will you marry me?",
            "Will you be my valentine?",
        ],
    )

    def __init__(self):
        self._response_index = 0

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """Handle easter egg commands."""
        # Get the original text from params
        text = params.get("raw_input", "").lower().strip()

        # Check which easter egg was triggered
        if self._is_valentine(text):
            return await self._valentine_response(channel)
        elif self._is_marry(text):
            return self._get_marry_response()
        elif self._is_love(text):
            return self._get_love_response()

        # Default fallback
        return "[red]♥[/red] You found an easter egg! Try: 'I love you', 'Will you marry me?', or 'Will you be my valentine?'"

    def _is_valentine(self, text: str) -> bool:
        """Check if this is a valentine request."""
        return bool(re.search(r"valentine", text, re.IGNORECASE))

    def _is_marry(self, text: str) -> bool:
        """Check if this is a marriage proposal."""
        return bool(re.search(r"marry", text, re.IGNORECASE))

    def _is_love(self, text: str) -> bool:
        """Check if this is a love declaration."""
        return bool(re.search(r"love\s*(you)?", text, re.IGNORECASE))

    def _get_love_response(self) -> str:
        """Get a love response, cycling through options."""
        response = LOVE_RESPONSES[self._response_index % len(LOVE_RESPONSES)]
        self._response_index += 1
        return response

    def _get_marry_response(self) -> str:
        """Get a marriage response, cycling through options."""
        response = MARRY_RESPONSES[self._response_index % len(MARRY_RESPONSES)]
        self._response_index += 1
        return response

    async def _valentine_response(self, channel: str) -> str:
        """
        Generate valentine response with animated heart for CLI.

        For CLI: Returns special markup that includes the animation.
        For other channels: Returns static heart.
        """
        # Build the full response with the animated heart representation
        # Since we can't actually animate in the response string,
        # we include a "beating" heart made of the frames

        response_parts = [
            VALENTINE_MESSAGE,
            "",
            "[dim]Here's a heart, just for you:[/dim]",
            "",
        ]

        # For CLI, we can show a nice colorful heart
        # The Rich library will render the markup
        if channel == "cli":
            # Show the "animated" effect by displaying the heart
            # with sparkles around it
            response_parts.append(self._create_sparkle_heart())
        else:
            # For other channels (telegram, etc), simpler heart
            response_parts.append(SMALL_HEART)

        response_parts.extend([
            "",
            "[italic dim]~thump thump~ [red]♥[/red] ~thump thump~[/italic dim]",
        ])

        return "\n".join(response_parts)

    def _create_sparkle_heart(self) -> str:
        """Create a sparkly heart for CLI display."""
        return """
[bold white]✨[/bold white]                              [bold white]✨[/bold white]
      [bold red]♥♥♥♥[/bold red]       [bold red]♥♥♥♥[/bold red]
    [bold red]♥♥♥♥♥♥♥♥[/bold red] [bold red]♥♥♥♥♥♥♥♥[/bold red]
   [bold magenta]♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥[/bold magenta]
   [bold magenta]♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥[/bold magenta]     [bold white]✨[/bold white]
   [bold magenta]♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥[/bold magenta]
    [bold red]♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥[/bold red]
[bold white]✨[/bold white]   [bold red]♥♥♥♥♥♥♥♥♥♥♥♥♥♥♥[/bold red]
       [bold red]♥♥♥♥♥♥♥♥♥♥♥♥♥[/bold red]
         [bold red]♥♥♥♥♥♥♥♥♥[/bold red]
           [bold magenta]♥♥♥♥♥♥♥[/bold magenta]       [bold white]✨[/bold white]
             [bold magenta]♥♥♥♥♥[/bold magenta]
               [bold red]♥♥♥[/bold red]
                [bold red]♥[/bold red]          [bold white]✨[/bold white]
"""
