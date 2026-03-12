"""
SafeClaw CLI - Main entry point.

Usage:
    safeclaw              # Start interactive CLI
    safeclaw run          # Start with all configured channels
    safeclaw webhook      # Start webhook server only
    safeclaw summarize    # Summarize URL or text
    safeclaw crawl        # Crawl a URL
"""

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from safeclaw import __version__
from safeclaw.actions import weather as weather_action
from safeclaw.actions.blog import BlogAction
from safeclaw.actions.briefing import BriefingAction
from safeclaw.actions.calendar import CalendarAction
from safeclaw.actions.code import CodeAction
from safeclaw.actions.crawl import CrawlAction
from safeclaw.actions.email import EmailAction
from safeclaw.actions.files import FilesAction
from safeclaw.actions.news import NewsAction
from safeclaw.actions.reminder import ReminderAction
from safeclaw.actions.research import ResearchAction
from safeclaw.actions.shell import ShellAction
from safeclaw.actions.summarize import SummarizeAction
from safeclaw.channels.cli import CLIChannel
from safeclaw.core.analyzer import TextAnalyzer
from safeclaw.core.crawler import Crawler
from safeclaw.core.documents import DocumentReader
from safeclaw.core.engine import SafeClaw
from safeclaw.core.feeds import PRESET_FEEDS, FeedReader
from safeclaw.core.prompt_builder import PromptBuilder
from safeclaw.core.summarizer import Summarizer, SummaryMethod
from safeclaw.core.writing_style import (
    load_writing_profile,
    update_writing_profile,
)
from safeclaw.plugins import PluginLoader

app = typer.Typer(
    name="safeclaw",
    help="SafeClaw - Privacy-first personal automation assistant",
    no_args_is_help=False,
)
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


def create_engine(config_path: Path | None = None) -> SafeClaw:
    """Create and configure the SafeClaw engine."""
    engine = SafeClaw(config_path=config_path)

    # Register default actions
    files_action = FilesAction()
    shell_action = ShellAction()
    summarize_action = SummarizeAction()
    crawl_action = CrawlAction()
    reminder_action = ReminderAction()
    briefing_action = BriefingAction()
    news_action = NewsAction()
    email_action = EmailAction()
    calendar_action = CalendarAction()
    blog_action = BlogAction()
    research_action = ResearchAction()
    code_action = CodeAction()

    engine.register_action("files", files_action.execute)
    engine.register_action("shell", shell_action.execute)
    engine.register_action("summarize", summarize_action.execute)
    engine.register_action("crawl", crawl_action.execute)
    engine.register_action("reminder", reminder_action.execute)
    engine.register_action("briefing", briefing_action.execute)
    engine.register_action("news", news_action.execute)
    engine.register_action("email", email_action.execute)
    engine.register_action("calendar", calendar_action.execute)
    engine.register_action("weather", weather_action.execute)
    engine.register_action("blog", blog_action.execute)
    engine.register_action("research", research_action.execute)
    engine.register_action("code", code_action.execute)
    engine.register_action("help", lambda **_: engine.get_help())

    # Register style profile action (fuzzy learning)
    engine.register_action("style", _style_action)

    # Register auto-blog action
    engine.register_action("autoblog", _autoblog_action)

    # Register flow diagram action
    engine.register_action("flow", _flow_action)

    # Register LLM auto-installer action
    engine.register_action("llm_setup", _llm_setup_action)

    # Load plugins from plugins/official/ and plugins/community/
    plugin_loader = PluginLoader()
    plugin_loader.load_all(engine)

    return engine


async def _style_action(
    params: dict, user_id: str, channel: str, engine: SafeClaw
) -> str:
    """Handle writing style profile commands."""
    raw = params.get("raw_input", "").lower()

    if "learn" in raw:
        # Feed text to the profiler
        text = raw.split("learn", 1)[-1].strip()
        if not text:
            return (
                "Provide text to learn from:\n"
                "  `style learn <paste your writing here>`\n\n"
                "Or SafeClaw automatically learns from your blog posts."
            )
        profile = await update_writing_profile(engine.memory, user_id, text)
        return (
            f"Learned from your writing! ({profile.samples_analyzed} samples total)\n\n"
            f"{profile.get_summary()}"
        )

    # Show profile
    profile = await load_writing_profile(engine.memory, user_id)
    if not profile or profile.samples_analyzed == 0:
        return (
            "No writing profile yet. SafeClaw learns your style from:\n"
            "  1. Blog posts you write\n"
            "  2. Text you feed it: `style learn <your text>`\n\n"
            "The more you write, the better it matches your voice."
        )

    lines = [
        f"**Your Writing Profile** ({profile.samples_analyzed} samples)",
        "",
        profile.get_summary(),
        "",
        "**System Prompt Instructions (sent to LLM):**",
        profile.to_prompt_instructions(),
    ]
    return "\n".join(lines)


async def _autoblog_action(
    params: dict, user_id: str, channel: str, engine: SafeClaw
) -> str:
    """Handle auto-blog scheduling commands."""
    from safeclaw.core.blog_scheduler import AutoBlogConfig, BlogScheduler

    raw = params.get("raw_input", "").lower()

    if not engine.blog_scheduler:
        engine.blog_scheduler = BlogScheduler(engine)

    if "list" in raw or "show" in raw:
        schedules = engine.blog_scheduler.list_schedules()
        if not schedules:
            return "No auto-blog schedules configured."
        lines = ["**Auto-Blog Schedules**", ""]
        for s in schedules:
            status = "enabled" if s["enabled"] else "disabled"
            lines.append(
                f"  {s['name']} ({status}): {s['cron']} | "
                f"Template: {s['template']} | Next: {s['next_run']}"
            )
        return "\n".join(lines)

    if "remove" in raw or "delete" in raw:
        name = raw.split("remove", 1)[-1].strip() or raw.split("delete", 1)[-1].strip()
        if engine.blog_scheduler.remove_schedule(name.strip()):
            return f"Removed auto-blog schedule: {name}"
        return f"Schedule not found: {name}"

    # Show help / setup instructions
    return (
        "**Auto-Blog: Cron-Based Publishing (No LLM)**\n\n"
        "Auto-blog fetches content from RSS feeds, summarizes with sumy,\n"
        "formats into posts, and publishes on schedule. Zero AI cost.\n\n"
        "Configure in config.yaml:\n"
        "```yaml\n"
        "auto_blogs:\n"
        '  - name: "weekly-tech"\n'
        '    cron_expr: "0 9 * * 1"    # Every Monday at 9am\n'
        "    source_categories:\n"
        "      - tech\n"
        "      - programming\n"
        '    post_template: "digest"    # digest, single, or curated\n'
        "    summary_sentences: 5\n"
        "    max_items: 5\n"
        "    auto_publish: false        # true = publish, false = save draft\n"
        '    publish_target: ""         # target label or empty for local\n'
        "```\n\n"
        "Templates:\n"
        "  - **digest**: Multi-item roundup with categories\n"
        "  - **single**: Feature one story with related items\n"
        "  - **curated**: Numbered list with editorial excerpts\n\n"
        "Commands:\n"
        "  `auto blog list` — Show all schedules\n"
        "  `auto blog remove <name>` — Remove a schedule"
    )


async def _flow_action(
    params: dict, user_id: str, channel: str, engine: SafeClaw
) -> str:
    """Show system architecture flow diagram."""
    return PromptBuilder.get_flow_diagram()


async def _llm_setup_action(
    params: dict, user_id: str, channel: str, engine: SafeClaw
) -> str:
    """Handle AI setup — enter your key or install local AI."""
    from safeclaw.core.llm_installer import auto_setup

    raw = params.get("raw_input", "")

    # Extract everything after the trigger keyword
    arg = ""
    for keyword in ["setup ai", "install llm", "install ai", "install ollama",
                     "setup llm", "setup ollama", "llm status", "ai status",
                     "llm setup", "ai setup", "local ai", "get ollama"]:
        lower = raw.lower()
        if keyword in lower:
            idx = lower.index(keyword) + len(keyword)
            arg = raw[idx:].strip()
            break

    # "llm status" / "ai status" → pass "status"
    if "status" in raw.lower() and not arg:
        arg = "status"

    result = await auto_setup(
        arg=arg,
        config_path=engine.config_path,
    )

    # Reload in-memory config so blog/research/code actions pick up the new provider
    engine.load_config()

    # Reset lazy-initialized actions so they re-read the updated config
    for action_handler in engine.actions.values():
        # Action handlers are bound methods — get the underlying object
        obj = getattr(action_handler, "__self__", None)
        if obj and hasattr(obj, "_initialized"):
            obj._initialized = False

    return result


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Config file path"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose logging"),
):
    """
    SafeClaw - Privacy-first personal automation assistant.

    Run without arguments to start interactive CLI.
    """
    setup_logging(verbose)

    if version:
        console.print(f"SafeClaw v{__version__}")
        raise typer.Exit()

    # If no subcommand, start interactive CLI
    if ctx.invoked_subcommand is None:
        try:
            asyncio.run(run_cli(config))
        except KeyboardInterrupt:
            pass
        finally:
            # Force exit — prevents hanging from lingering threads
            import os
            os._exit(0)


async def run_cli(config_path: Path | None = None) -> None:
    """Run interactive CLI."""
    engine = create_engine(config_path)

    # Add CLI channel
    cli_channel = CLIChannel(engine)
    engine.register_channel("cli", cli_channel)

    await engine.start()


@app.command()
def run(
    config: Path | None = typer.Option(None, "--config", "-c"),
    webhook: bool = typer.Option(False, "--webhook", help="Enable webhook server"),
    telegram: bool = typer.Option(False, "--telegram", help="Enable Telegram bot"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Start SafeClaw with configured channels."""
    setup_logging(verbose)
    try:
        asyncio.run(_run_all(config, webhook, telegram))
    except KeyboardInterrupt:
        pass
    finally:
        import os
        os._exit(0)


async def _run_all(
    config_path: Path | None,
    enable_webhook: bool,
    enable_telegram: bool,
) -> None:
    """Run all configured channels."""
    engine = create_engine(config_path)

    # Add CLI channel
    cli_channel = CLIChannel(engine)
    engine.register_channel("cli", cli_channel)

    # Add webhook if enabled
    if enable_webhook:
        from safeclaw.triggers.webhook import WebhookServer
        webhook_server = WebhookServer()
        engine.register_channel("webhook", webhook_server)

    # Add Telegram if enabled
    if enable_telegram:
        token = engine.config.get("telegram", {}).get("token")
        if token:
            from safeclaw.channels.telegram import TelegramChannel
            telegram_channel = TelegramChannel(engine, token)
            engine.register_channel("telegram", telegram_channel)
        else:
            console.print("[yellow]Telegram token not configured[/yellow]")

    await engine.start()


@app.command()
def summarize(
    target: str = typer.Argument(..., help="URL or text to summarize"),
    sentences: int = typer.Option(5, "--sentences", "-n", help="Number of sentences"),
    method: str = typer.Option("lexrank", "--method", "-m", help="Algorithm to use"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Summarize a URL or text."""
    setup_logging(verbose)
    asyncio.run(_summarize(target, sentences, method))


async def _summarize(target: str, sentences: int, method: str) -> None:
    """Run summarization."""
    summarizer = Summarizer()

    # Check if URL
    if target.startswith(("http://", "https://")):
        async with Crawler() as crawler:
            result = await crawler.fetch(target)

        if result.error:
            console.print(f"[red]Error fetching URL: {result.error}[/red]")
            return

        text = result.text
        title = result.title or target
        console.print(f"[bold]{title}[/bold]\n")
    else:
        text = target

    # Get method enum
    try:
        method_enum = SummaryMethod(method.lower())
    except ValueError:
        method_enum = SummaryMethod.LEXRANK

    # Summarize
    summary = summarizer.summarize(text, sentences, method_enum)
    console.print(summary)


@app.command()
def crawl(
    url: str = typer.Argument(..., help="URL to crawl"),
    depth: int = typer.Option(0, "--depth", "-d", help="Crawl depth (0 = single page)"),
    same_domain: bool = typer.Option(True, "--same-domain/--all-domains"),
    pattern: str | None = typer.Option(None, "--pattern", "-p", help="URL filter pattern"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Crawl a URL and extract links."""
    setup_logging(verbose)
    asyncio.run(_crawl(url, depth, same_domain, pattern))


async def _crawl(
    url: str,
    depth: int,
    same_domain: bool,
    pattern: str | None,
) -> None:
    """Run crawler."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    crawler = Crawler(max_depth=depth)

    if depth == 0:
        # Single page
        links = await crawler.get_links(url, same_domain, pattern)
        console.print(f"[bold]Links from {url}:[/bold]\n")
        for link in links[:50]:
            console.print(f"  • {link}")
        if len(links) > 50:
            console.print(f"\n  ... and {len(links) - 50} more")
    else:
        # Multi-page crawl
        results = await crawler.crawl(url, same_domain=same_domain, pattern=pattern)
        console.print(f"[bold]Crawled {len(results)} pages from {url}:[/bold]\n")
        for result in results[:20]:
            status = "✓" if not result.error else f"✗ {result.error}"
            console.print(f"  [{result.depth}] {status} {result.title or result.url}")


@app.command()
def webhook(
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Start the webhook server only."""
    setup_logging(verbose)
    asyncio.run(_run_webhook(host, port))


async def _run_webhook(host: str, port: int) -> None:
    """Run webhook server."""
    from safeclaw.triggers.webhook import WebhookServer

    server = WebhookServer(host=host, port=port)
    console.print(f"[green]Starting webhook server on {host}:{port}[/green]")
    await server.start()


@app.command()
def news(
    category: str | None = typer.Argument(None, help="Category to fetch (tech, world, science, etc.)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of headlines"),
    list_categories: bool = typer.Option(False, "--categories", "-c", help="List available categories"),
    add_feed: str | None = typer.Option(None, "--add", "-a", help="Add custom RSS feed URL"),
    feed_name: str | None = typer.Option(None, "--name", help="Name for custom feed"),
    enable: str | None = typer.Option(None, "--enable", "-e", help="Enable a category"),
    disable: str | None = typer.Option(None, "--disable", "-d", help="Disable a category"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Summarize articles"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Fetch news from RSS feeds."""
    setup_logging(verbose)
    asyncio.run(_news(category, limit, list_categories, add_feed, feed_name, enable, disable, summarize))


async def _news(
    category: str | None,
    limit: int,
    list_categories: bool,
    add_feed: str | None,
    feed_name: str | None,
    enable: str | None,
    disable: str | None,
    summarize: bool,
) -> None:
    """Run news commands."""
    feed_reader = FeedReader(
        summarize_items=summarize,
        max_items_per_feed=limit,
    )

    # List categories
    if list_categories:
        console.print("[bold]📂 Available News Categories[/bold]\n")
        for cat, feeds in sorted(PRESET_FEEDS.items()):
            status = "✅" if cat in feed_reader.enabled_categories else "⬜"
            console.print(f"{status} [bold]{cat}[/bold] ({len(feeds)} feeds)")
            for feed in feeds[:3]:
                console.print(f"   • {feed.name}")
            if len(feeds) > 3:
                console.print(f"   • ... and {len(feeds) - 3} more")
            console.print()
        return

    # Enable category
    if enable:
        if enable in PRESET_FEEDS:
            console.print(f"[green]✅ Enabled category: {enable}[/green]")
        else:
            console.print(f"[red]Unknown category: {enable}[/red]")
        return

    # Disable category
    if disable:
        console.print(f"[yellow]⬜ Disabled category: {disable}[/yellow]")
        return

    # Add custom feed
    if add_feed:
        name = feed_name or "Custom Feed"
        console.print(f"[dim]Fetching feed: {add_feed}...[/dim]")
        feed_reader.add_custom_feed(name, add_feed)
        items = await feed_reader.fetch_feeds(feed_reader.custom_feeds)
        if items:
            console.print(f"[green]✅ Added feed: {name} ({len(items)} items)[/green]")
        else:
            console.print(f"[red]Could not fetch items from {add_feed}[/red]")
        return

    # Fetch news
    console.print("[dim]Fetching news...[/dim]\n")

    if category:
        if category not in PRESET_FEEDS:
            console.print(f"[red]Unknown category: {category}[/red]")
            console.print(f"Available: {', '.join(PRESET_FEEDS.keys())}")
            return
        items = await feed_reader.fetch_category(category)
    else:
        items = await feed_reader.fetch_all_enabled()

    if not items:
        console.print("[yellow]No news items found. Try a different category.[/yellow]")
        return

    items = items[:limit]

    console.print("[bold]📰 News Headlines[/bold]\n")

    current_cat = None
    for item in items:
        if item.feed_category != current_cat:
            current_cat = item.feed_category
            console.print(f"[bold cyan]── {current_cat.upper()} ──[/bold cyan]\n")

        console.print(f"[bold]{item.title}[/bold]")
        time_str = ""
        if item.published:
            time_str = item.published.strftime(" • %b %d, %H:%M")
        console.print(f"[dim]{item.feed_name}{time_str}[/dim]")

        if summarize and item.summary:
            console.print(f"[italic]{item.summary}[/italic]")
        elif item.description:
            console.print(f"[dim]{item.description[:150]}...[/dim]")

        console.print(f"[blue]{item.link}[/blue]")
        console.print()


@app.command()
def analyze(
    target: str = typer.Argument(..., help="Text or file path to analyze"),
    sentiment: bool = typer.Option(True, "--sentiment/--no-sentiment", help="Analyze sentiment"),
    keywords: bool = typer.Option(True, "--keywords/--no-keywords", help="Extract keywords"),
    readability: bool = typer.Option(True, "--readability/--no-readability", help="Analyze readability"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Analyze text for sentiment, keywords, and readability."""
    setup_logging(verbose)
    asyncio.run(_analyze(target, sentiment, keywords, readability))


async def _analyze(target: str, sentiment: bool, keywords: bool, readability: bool) -> None:
    """Run text analysis."""
    analyzer = TextAnalyzer()

    # Check if file path
    path = Path(target)
    if path.exists() and path.is_file():
        doc_reader = DocumentReader()
        result = doc_reader.read(path)
        if result.error:
            console.print(f"[red]Error reading file: {result.error}[/red]")
            return
        text = result.text
        console.print(f"[dim]Analyzing: {path.name} ({result.word_count} words)[/dim]\n")
    else:
        text = target

    if sentiment:
        sent_result = analyzer.analyze_sentiment(text)
        console.print("[bold]Sentiment Analysis[/bold]")
        color = "green" if sent_result.label == "positive" else "red" if sent_result.label == "negative" else "yellow"
        console.print(f"  Label: [{color}]{sent_result.label.upper()}[/{color}]")
        console.print(f"  Compound: {sent_result.compound:.3f}")
        console.print(f"  Positive: {sent_result.positive:.1%}")
        console.print(f"  Negative: {sent_result.negative:.1%}")
        console.print(f"  Neutral: {sent_result.neutral:.1%}")
        console.print()

    if keywords:
        kw_result = analyzer.extract_keywords(text, top_n=10)
        console.print("[bold]Keywords[/bold]")
        console.print(f"  {', '.join(kw_result)}")
        console.print()

    if readability:
        read_result = analyzer.analyze_readability(text)
        console.print("[bold]Readability[/bold]")
        console.print(f"  Flesch Reading Ease: {read_result.flesch_reading_ease:.1f}/100")
        console.print(f"  Grade Level: {read_result.flesch_kincaid_grade:.1f}")
        console.print(f"  Reading Level: {read_result.reading_level.upper()}")
        console.print(f"  Words: {read_result.word_count} | Sentences: {read_result.sentence_count}")
        console.print(f"  Avg Word Length: {read_result.avg_word_length:.1f} | Avg Sentence: {read_result.avg_sentence_length:.1f}")


@app.command()
def document(
    path: Path = typer.Argument(..., help="Path to document (PDF, DOCX, TXT, etc.)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save extracted text to file"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Summarize the document"),
    sentences: int = typer.Option(5, "--sentences", "-n", help="Sentences for summary"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Read and extract text from documents (PDF, DOCX, TXT, MD, HTML)."""
    setup_logging(verbose)
    asyncio.run(_document(path, output, summarize, sentences))


async def _document(path: Path, output: Path | None, do_summarize: bool, sentences: int) -> None:
    """Read document."""
    reader = DocumentReader()

    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        return

    console.print(f"[dim]Reading: {path}...[/dim]")
    result = reader.read(path)

    if result.error:
        console.print(f"[red]Error: {result.error}[/red]")
        return

    console.print(f"\n[bold]{result.title or path.name}[/bold]")
    if result.author:
        console.print(f"[dim]Author: {result.author}[/dim]")
    console.print(f"[dim]Format: {result.format} | Pages: {result.page_count} | Words: {result.word_count}[/dim]\n")

    if do_summarize:
        summarizer = Summarizer()
        summary = summarizer.summarize(result.text, sentences)
        console.print("[bold]Summary:[/bold]")
        console.print(summary)
    else:
        # Show preview
        preview = result.text[:2000]
        if len(result.text) > 2000:
            preview += "\n\n[dim]... (truncated, use --output to save full text)[/dim]"
        console.print(preview)

    if output:
        output.write_text(result.text)
        console.print(f"\n[green]Saved to: {output}[/green]")


@app.command()
def calendar(
    action: str = typer.Argument("today", help="Action: today, upcoming, week, import"),
    path: Path | None = typer.Option(None, "--file", "-f", help="ICS file to import"),
    days: int = typer.Option(7, "--days", "-d", help="Days for upcoming events"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """View and manage calendar events from ICS files."""
    setup_logging(verbose)
    asyncio.run(_calendar(action, path, days))


async def _calendar(action: str, path: Path | None, days: int) -> None:
    """Run calendar command."""
    try:
        from safeclaw.actions.calendar import CalendarEvent, CalendarParser
    except ImportError:
        console.print("[red]Calendar support not installed. Run: pip install icalendar[/red]")
        return

    parser = CalendarParser()

    if action == "import" and path:
        if not path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            return

        events = parser.parse_file(path)
        if not events:
            console.print("[yellow]No events found in file.[/yellow]")
            return

        console.print(f"[green]Imported {len(events)} events from {path.name}[/green]\n")

        # Show preview
        for event in events[:10]:
            date_str = event.start.strftime("%Y-%m-%d %H:%M")
            console.print(f"  {date_str} - {event.summary}")
            if event.location:
                console.print(f"    [dim]{event.location}[/dim]")

        if len(events) > 10:
            console.print(f"\n  [dim]... and {len(events) - 10} more events[/dim]")
    else:
        console.print("[yellow]Use --file to specify an ICS file to import.[/yellow]")
        console.print("\nExamples:")
        console.print("  safeclaw calendar import --file calendar.ics")
        console.print("  safeclaw calendar today")
        console.print("  safeclaw calendar upcoming --days 14")


@app.command()
def blog(
    action: str = typer.Argument("help", help="Action: write, show, title, publish, help"),
    content: list[str] | None = typer.Argument(None, help="Blog content or title"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Blog without a language model. 50-star milestone feature."""
    setup_logging(verbose)
    asyncio.run(_blog(action, content))


async def _blog(action: str, content: list[str] | None) -> None:
    """Run blog command."""
    blog_action = BlogAction()
    user_id = "cli_user"

    # Build raw_input from action + content
    content_str = " ".join(content) if content else ""

    if action == "help":
        raw = "blog help"
    elif action in ("write", "news", "add", "post"):
        raw = f"write blog news {content_str}"
    elif action in ("show", "list", "view"):
        raw = "show blog"
    elif action == "title":
        raw = "blog title"
    elif action in ("publish", "save", "export"):
        raw = f"publish blog {content_str}"
    else:
        # Treat action as part of content
        raw = f"write blog news {action} {content_str}"

    # Execute without engine (standalone mode)
    result = await blog_action.execute(
        params={"raw_input": raw},
        user_id=user_id,
        channel="cli",
        engine=None,  # type: ignore[arg-type]
    )
    console.print(result)


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
):
    """Initialize SafeClaw configuration."""
    config_dir = path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        config_file.write_text(DEFAULT_CONFIG)
        console.print(f"[green]Created {config_file}[/green]")
    else:
        console.print(f"[yellow]Config already exists: {config_file}[/yellow]")

    intents_file = config_dir / "intents.yaml"
    if not intents_file.exists():
        intents_file.write_text(DEFAULT_INTENTS)
        console.print(f"[green]Created {intents_file}[/green]")

    console.print("\n[bold]SafeClaw initialized![/bold]")
    console.print("Edit config/config.yaml to configure your assistant.")


DEFAULT_CONFIG = """# SafeClaw Configuration

safeclaw:
  name: "SafeClaw"
  language: "en"
  timezone: "UTC"

# Channels
channels:
  cli:
    enabled: true
  webhook:
    enabled: true
    port: 8765
    host: "0.0.0.0"
  telegram:
    enabled: false
    token: ""  # Get from @BotFather
    allowed_users: []  # List of user IDs, empty = allow all

# Actions
actions:
  shell:
    enabled: true
    sandboxed: true
    timeout: 30
  files:
    enabled: true
    allowed_paths:
      - "~"
      - "/tmp"
  browser:
    enabled: false

# Memory
memory:
  max_history: 1000
  retention_days: 365

# Optional API keys
apis:
  openweathermap: ""  # For weather in briefings
  newsapi: ""  # For news in briefings

# Per-task LLM routing (100-star feature)
# task_providers:
#   blog: "local-ollama"
#   research: "openai"
#   coding: "anthropic"

# Auto-blog scheduler (100-star feature, no LLM)
# auto_blogs:
#   - name: "weekly-tech"
#     cron_expr: "0 9 * * 1"
#     source_categories: [tech]
#     post_template: "digest"
"""

DEFAULT_INTENTS = """# Custom intent patterns
# Add your own commands here

intents:
  # Example custom intent
  # deploy:
  #   keywords: ["deploy", "release", "ship"]
  #   patterns:
  #     - "deploy to (production|staging)"
  #   examples:
  #     - "deploy to production"
  #   action: "webhook"
  #   params:
  #     webhook_name: "deploy"
"""


def main_cli():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main_cli()
