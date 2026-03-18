"""Command-line interface channel."""

import asyncio
import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from safeclaw.channels.base import BaseChannel

if TYPE_CHECKING:
    from safeclaw.core.engine import SafeClaw


class CLIChannel(BaseChannel):
    """
    Interactive command-line interface.

    Features:
    - Rich text formatting
    - Markdown rendering
    - Command history
    - Async input handling
    """

    name = "cli"

    def __init__(self, engine: "SafeClaw"):
        super().__init__(engine)
        self.console = Console()
        self.running = False
        self.user_id = "cli_user"

    async def start(self) -> None:
        """Start the CLI interface."""
        self.running = True

        # Milestone celebration banner
        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold yellow]         100 STARS          [/bold yellow]\n"
                "[bold white]We hit 100 stars on GitHub![/bold white]\n"
                "\n"
                "[dim]Every huge milestone, we add something new.[/dim]\n"
                "[bold cyan]NEW:[/bold cyan] [white]Real Research + Auto LLM + Smart Learning[/white]\n"
                "[dim]arXiv & Semantic Scholar papers, Wolfram Alpha,[/dim]\n"
                "[dim]setup ai <your-key> instant config, auto-learning[/dim]\n"
                "[dim]from your mistakes (typos, word-numbers, corrections).[/dim]\n"
                "[dim]Type[/dim] [bold]help[/bold] [dim]to see all commands.[/dim]",
                border_style="yellow",
                title="[bold yellow] MILESTONE [/bold yellow]",
                subtitle="[dim]safeclaw 0.3.2[/dim]",
            )
        )
        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold green]SafeClaw[/bold green] - Privacy-first automation assistant\n"
                "Type [bold]setup ai <your-key>[/bold] to configure AI, "
                "[bold]research <topic>[/bold] for arXiv/Scholar,\n"
                "[bold]setup ai local[/bold] for free local AI, "
                "[bold]help[/bold] for all commands",
                border_style="green",
            )
        )
        self.console.print()

        while self.running:
            try:
                # Get input
                user_input = await self._async_input("[bold cyan]>[/bold cyan] ")

                if not user_input:
                    continue

                # Handle quit
                if user_input.lower() in ("quit", "exit", "q"):
                    self.console.print("[dim]Goodbye![/dim]")
                    break

                # Process message
                response = await self.handle_message(user_input, self.user_id)

                # Display response
                self._display_response(response)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Goodbye![/dim]")
                break
            except EOFError:
                break

        self.running = False

    async def stop(self) -> None:
        """Stop the CLI interface."""
        self.running = False

    async def send(self, user_id: str, message: str) -> None:
        """Send a message (display to console)."""
        if user_id == self.user_id:
            self._display_response(message)

    async def _async_input(self, prompt: str) -> str:
        """Get input asynchronously."""
        self.console.print(prompt, end="")

        loop = asyncio.get_event_loop()
        # Use a daemon thread so it won't block process exit
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            line = await loop.run_in_executor(executor, sys.stdin.readline)
        finally:
            executor.shutdown(wait=False)
        return line.strip()

    def _display_response(self, response: str) -> None:
        """Display response with formatting."""
        self.console.print()

        # Check if response looks like markdown
        if any(marker in response for marker in ["**", "•", "```", "- ", "# "]):
            self.console.print(Markdown(response))
        else:
            self.console.print(response)

        self.console.print()
