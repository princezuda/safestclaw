"""
SafestClaw CLI - Main entry point.

Usage:
    safestclaw              # Start interactive CLI
    safestclaw run          # Start with all configured channels
    safestclaw webhook      # Start webhook server only
    safestclaw summarize    # Summarize URL or text
    safestclaw crawl        # Crawl a URL
"""

import asyncio
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from safestclaw import __version__
from safestclaw.actions import weather as weather_action
from safestclaw.actions.blog import BlogAction
from safestclaw.actions.briefing import BriefingAction
from safestclaw.actions.calendar import CalendarAction
from safestclaw.actions.code import CodeAction
from safestclaw.actions.crawl import CrawlAction
from safestclaw.actions.email import EmailAction
from safestclaw.actions.files import FilesAction
from safestclaw.actions.news import NewsAction
from safestclaw.actions.reminder import ReminderAction
from safestclaw.actions.research import ResearchAction
from safestclaw.actions.shell import ShellAction
from safestclaw.actions.summarize import SummarizeAction
from safestclaw.channels.cli import CLIChannel
from safestclaw.core.analyzer import TextAnalyzer
from safestclaw.core.crawler import Crawler
from safestclaw.core.documents import DocumentReader
from safestclaw.core.engine import SafestClaw
from safestclaw.core.feeds import PRESET_FEEDS, FeedReader
from safestclaw.core.prompt_builder import PromptBuilder
from safestclaw.core.setup_wizard import offer_wizard_if_first_run, run_wizard
from safestclaw.core.summarizer import Summarizer, SummaryMethod
from safestclaw.core.writing_style import (
    load_writing_profile,
    update_writing_profile,
)
from safestclaw.plugins import PluginLoader

app = typer.Typer(
    name="safestclaw",
    help="SafestClaw - Privacy-first personal automation assistant",
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


def create_engine(config_path: Path | None = None) -> SafestClaw:
    """Create and configure the SafestClaw engine."""
    engine = SafestClaw(config_path=config_path)

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
    params: dict, user_id: str, channel: str, engine: SafestClaw
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
                "Or SafestClaw automatically learns from your blog posts."
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
            "No writing profile yet. SafestClaw learns your style from:\n"
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
    params: dict, user_id: str, channel: str, engine: SafestClaw
) -> str:
    """Handle auto-blog scheduling commands."""
    from safestclaw.core.blog_scheduler import AutoBlogConfig, BlogScheduler

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
    params: dict, user_id: str, channel: str, engine: SafestClaw
) -> str:
    """Show system architecture flow diagram."""
    return PromptBuilder.get_flow_diagram()


async def _llm_setup_action(
    params: dict, user_id: str, channel: str, engine: SafestClaw
) -> str:
    """Handle AI/integration setup commands."""
    from safestclaw.core.llm_installer import (
        auto_setup,
        setup_telegram,
        setup_telegram_allow,
        setup_telegram_deny,
        setup_wolfram,
    )

    raw = params.get("raw_input", "")
    lower = raw.lower().strip()

    # ── setup wolfram <app-id> ────────────────────────────────────────────
    if lower.startswith("setup wolfram"):
        app_id = raw[len("setup wolfram"):].strip()
        return setup_wolfram(app_id, engine.config_path)

    # ── setup telegram allow <target> ─────────────────────────────────────
    if lower.startswith("setup telegram allow"):
        target = raw[len("setup telegram allow"):].strip() or "list"
        return setup_telegram_allow(target, user_id, engine.config_path)

    # ── setup telegram deny <target> ──────────────────────────────────────
    if lower.startswith("setup telegram deny"):
        target = raw[len("setup telegram deny"):].strip()
        return setup_telegram_deny(target, engine.config_path)

    # ── setup telegram <token> ────────────────────────────────────────────
    if lower.startswith("setup telegram"):
        token = raw[len("setup telegram"):].strip()
        result = setup_telegram(token, engine.config_path)
        if token:
            engine.load_config()  # pick up new channel config immediately
        return result

    # ── setup ai … ────────────────────────────────────────────────────────
    arg = ""
    for keyword in ["setup ai", "install llm", "install ai", "install ollama",
                     "setup llm", "setup ollama", "llm status", "ai status",
                     "llm setup", "ai setup", "local ai", "get ollama"]:
        if keyword in lower:
            idx = lower.index(keyword) + len(keyword)
            arg = raw[idx:].strip()
            break

    # "llm status" / "ai status" → pass "status"
    if "status" in lower and not arg:
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
    SafestClaw - Privacy-first personal automation assistant.

    Run without arguments to start interactive CLI.
    """
    setup_logging(verbose)

    if version:
        console.print(f"SafestClaw v{__version__}")
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
    resolved_config = config_path or Path("config/config.yaml")
    if offer_wizard_if_first_run(resolved_config, console):
        await run_wizard(resolved_config, console)

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
    web: bool = typer.Option(False, "--web", help="Enable localhost web UI"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Start SafestClaw with configured channels."""
    setup_logging(verbose)
    try:
        asyncio.run(_run_all(config, webhook, telegram, web))
    except KeyboardInterrupt:
        pass
    finally:
        import os
        os._exit(0)


async def _run_all(
    config_path: Path | None,
    enable_webhook: bool,
    enable_telegram: bool,
    enable_web: bool = False,
) -> None:
    """Run all configured channels."""
    engine = create_engine(config_path)

    # Add CLI channel
    cli_channel = CLIChannel(engine)
    engine.register_channel("cli", cli_channel)

    # Add webhook if enabled
    if enable_webhook:
        from safestclaw.triggers.webhook import WebhookServer
        webhook_server = WebhookServer()
        engine.register_channel("webhook", webhook_server)

    # Add Telegram if enabled
    if enable_telegram:
        token = engine.config.get("telegram", {}).get("token")
        if token:
            from safestclaw.channels.telegram import TelegramChannel
            telegram_channel = TelegramChannel(engine, token)
            engine.register_channel("telegram", telegram_channel)
        else:
            console.print("[yellow]Telegram token not configured[/yellow]")

    # Add localhost web UI if enabled (flag or config)
    web_cfg = (engine.config.get("channels") or {}).get("web") or {}
    if enable_web or web_cfg.get("enabled"):
        from safestclaw.channels.web import WebChannel
        try:
            web_channel = WebChannel.from_config(engine, web_cfg)
            engine.register_channel("web", web_channel)
            console.print(
                f"[green]Web UI:[/green] "
                f"http://{web_channel.host}:{web_channel.port}"
            )
        except (ImportError, ValueError) as e:
            console.print(f"[red]Could not start web UI: {e}[/red]")

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
    from safestclaw.triggers.webhook import WebhookServer

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
        from safestclaw.actions.calendar import CalendarParser
    except ImportError:
        console.print("[red]Calendar support not installed. Run: pip install icalendar[/red]")
        return

    parser = CalendarParser()

    def _print_events(events, title: str) -> None:
        if not events:
            console.print("[yellow]No events found.[/yellow]")
            return
        console.print(f"[bold]{title}[/bold]\n")
        current_date = None
        for event in events:
            event_date = event.start.date()
            if event_date != current_date:
                current_date = event_date
                console.print(f"[cyan]{event_date.strftime('%A, %B %d')}[/cyan]")
            time_str = "All day" if event.all_day else event.start.strftime("%H:%M")
            console.print(f"  {time_str} - {event.summary}")
            if event.location:
                console.print(f"    [dim]{event.location}[/dim]")

    if action == "import":
        if not path:
            console.print("[red]Use --file to specify an ICS file to import.[/red]")
            return
        if not path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            return

        events = parser.parse_file(path)
        if not events:
            console.print("[yellow]No events found in file.[/yellow]")
            return

        console.print(f"[green]Imported {len(events)} events from {path.name}[/green]\n")
        for event in events[:10]:
            date_str = event.start.strftime("%Y-%m-%d %H:%M")
            console.print(f"  {date_str} - {event.summary}")
            if event.location:
                console.print(f"    [dim]{event.location}[/dim]")
        if len(events) > 10:
            console.print(f"\n  [dim]... and {len(events) - 10} more events[/dim]")
        return

    if action in ("today", "upcoming", "week"):
        if not path:
            console.print(
                "[yellow]Provide --file to view events from an ICS file, "
                "or use the interactive CLI for CalDAV-synced events.[/yellow]"
            )
            return
        if not path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            return
        events = parser.parse_file(path)
        if action == "today":
            _print_events(parser.get_today_events(events), "Today's Schedule")
        else:  # upcoming or week
            window = 7 if action == "week" else days
            _print_events(
                parser.get_upcoming_events(events, window),
                f"Upcoming Events (next {window} days)",
            )
        return

    console.print(f"[red]Unknown calendar action: {action}[/red]")
    console.print("Available: today, upcoming, week, import")
    console.print("\nExamples:")
    console.print("  safestclaw calendar import --file calendar.ics")
    console.print("  safestclaw calendar today --file calendar.ics")
    console.print("  safestclaw calendar upcoming --file calendar.ics --days 14")


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
def publish(
    title: str = typer.Option(..., "--title", "-t", help="Blog post title"),
    file: Path | None = typer.Option(None, "--file", "-f", help="Path to content file"),
    content: str | None = typer.Option(None, "--content", "-c", help="Content as a string"),
    target: str | None = typer.Option(None, "--target", help="Named publish target from config"),
    sftp_host: str | None = typer.Option(None, "--sftp-host", help="SFTP host"),
    sftp_port: int = typer.Option(22, "--sftp-port", help="SFTP port"),
    sftp_user: str = typer.Option("", "--sftp-user", help="SFTP username"),
    sftp_password: str = typer.Option("", "--sftp-password", help="SFTP password"),
    sftp_key: str = typer.Option("", "--sftp-key", help="Path to SSH private key"),
    sftp_path: str = typer.Option("/var/www/html/blog", "--sftp-path", help="Remote directory"),
    config: Path | None = typer.Option(None, "--config", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Publish a blog post to SFTP (or other configured targets) non-interactively."""
    setup_logging(verbose)
    asyncio.run(_publish(
        title=title,
        file=file,
        content_str=content,
        target=target,
        sftp_host=sftp_host,
        sftp_port=sftp_port,
        sftp_user=sftp_user,
        sftp_password=sftp_password,
        sftp_key=sftp_key,
        sftp_path=sftp_path,
        config_path=config,
    ))


async def _publish(
    title: str,
    file: Path | None,
    content_str: str | None,
    target: str | None,
    sftp_host: str | None,
    sftp_port: int,
    sftp_user: str,
    sftp_password: str,
    sftp_key: str,
    sftp_path: str,
    config_path: Path | None,
) -> None:
    """Run a non-interactive publish to SFTP or configured targets."""
    import re

    import yaml

    from safestclaw.core.blog_publisher import BlogPublisher, PublishTarget, PublishTargetType

    # Resolve content
    body = ""
    if file:
        if not file.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        body = file.read_text()
    elif content_str:
        body = content_str
    else:
        console.print("[red]Provide content via --file or --content.[/red]")
        raise typer.Exit(1)

    if not body.strip():
        console.print("[red]Content is empty.[/red]")
        raise typer.Exit(1)

    # Build publisher — start from config if available
    if config_path and config_path.exists():
        raw_config = yaml.safe_load(config_path.read_text()) or {}
        publisher = BlogPublisher.from_config(raw_config)
    else:
        publisher = BlogPublisher()

    # If inline SFTP flags were given, add/override that target
    if sftp_host:
        inline = PublishTarget(
            label=f"sftp-{sftp_host}",
            target_type=PublishTargetType.SFTP,
            sftp_host=sftp_host,
            sftp_port=sftp_port,
            sftp_user=sftp_user,
            sftp_password=sftp_password,
            sftp_key_path=sftp_key,
            sftp_remote_path=sftp_path,
        )
        publisher.add_target(inline)

    if not publisher.targets:
        console.print(
            "[red]No publish targets found.[/red]\n"
            "Provide --sftp-host (and credentials), or configure publish_targets in config.yaml."
        )
        raise typer.Exit(1)

    slug = re.sub(r"[^\w\s-]", "", title)[:50].strip().replace(" ", "-").lower()
    excerpt = body[:160].strip()

    console.print(f"[dim]Publishing \"{title}\" → {target or 'all targets'}…[/dim]")

    results = await publisher.publish(
        title=title,
        content=body,
        target_label=target,
        excerpt=excerpt,
        slug=slug,
    )

    any_success = False
    for r in results:
        if r.success:
            any_success = True
            console.print(f"[green]✓ {r.target_label} ({r.target_type}): {r.message}[/green]")
            if r.url:
                console.print(f"  [blue]{r.url}[/blue]")
        else:
            console.print(f"[red]✗ {r.target_label} ({r.target_type}): {r.error}[/red]")

    if not any_success:
        raise typer.Exit(1)


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
    wizard: bool = typer.Option(
        True, "--wizard/--no-wizard", help="Run the interactive setup wizard"
    ),
):
    """Initialize SafestClaw configuration."""
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

    console.print("\n[bold]SafestClaw initialized![/bold]")

    if wizard and sys.stdin.isatty():
        console.print()
        asyncio.run(run_wizard(config_file, console))
    else:
        console.print("Edit config/config.yaml to configure your assistant,")
        console.print("or run [bold]safestclaw setup[/bold] to launch the wizard.")


@app.command()
def setup(
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Config file path"
    ),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Run the interactive setup wizard (local / LLM / hybrid)."""
    setup_logging(verbose)
    config_path = config or Path("config/config.yaml")
    asyncio.run(run_wizard(config_path, console))


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h",
                              help="Bind host (loopback only)"),
    port: int = typer.Option(8771, "--port", "-p", help="Port"),
    token: str = typer.Option("", "--token", help="Optional auth token"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """
    Start the localhost web UI.

    Exposes the entire SafestClaw engine — every action, plugin, and
    command — through a tiny chat interface plus a JSON API at
    http://127.0.0.1:8771.
    """
    setup_logging(verbose)

    async def _run() -> None:
        engine = create_engine(config)
        engine.load_config()
        await engine.memory.initialize()

        from safestclaw.channels.web import WebChannel
        cfg = (engine.config.get("channels") or {}).get("web") or {}
        try:
            channel = WebChannel(
                engine=engine,
                host=host or cfg.get("host", "127.0.0.1"),
                port=port or int(cfg.get("port", 8771)),
                auth_token=token or cfg.get("auth_token") or None,
                user_id=cfg.get("user_id", "web_user"),
            )
        except (ImportError, ValueError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        engine.register_channel("web", channel)
        console.print(
            f"[green]SafestClaw web UI:[/green] "
            f"http://{channel.host}:{channel.port}"
            + ("  (token required)" if channel.auth_token else "")
        )
        try:
            await channel.start()
        except KeyboardInterrupt:
            await channel.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


@app.command()
def security(
    subcommand: str = typer.Argument(
        "tools",
        help="tools | scan | bandit | pip-audit | safety | semgrep | trivy | "
             "secrets | gitleaks | help",
    ),
    path: Path | None = typer.Argument(None, help="Target path (when needed)"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """
    Run deterministic security scanners (bandit, pip-audit, semgrep, trivy,
    detect-secrets, gitleaks). No AI required.
    """
    setup_logging(verbose)
    from safestclaw.plugins.official.security import SecurityPlugin

    async def _run() -> None:
        engine = create_engine(config)
        engine.load_config()
        plugin = SecurityPlugin()
        plugin.on_load(engine)

        raw = subcommand if path is None else f"{subcommand} {path}"
        result = await plugin.execute(
            params={"raw_input": f"security {raw}"},
            user_id="cli",
            channel="cli",
            engine=engine,
        )
        console.print(result)

    asyncio.run(_run())


@app.command()
def mcp(
    transport: str = typer.Option(
        "stdio", "--transport", "-t",
        help="MCP transport: stdio (default), sse, streamable-http",
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="HTTP host"),
    port: int = typer.Option(8770, "--port", "-p", help="HTTP port"),
    server_name: str = typer.Option(
        "safestclaw", "--name", help="Name advertised to MCP clients"
    ),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """
    Run a Model Context Protocol server that exposes SafestClaw actions as tools.

    Use stdio (default) when an MCP client (Claude Desktop, IDE extensions, …)
    spawns SafestClaw as a subprocess. Use sse or streamable-http to expose
    actions over HTTP.
    """
    setup_logging(verbose)
    try:
        from safestclaw.core.mcp_server import HAS_FASTMCP, serve_mcp
    except Exception as e:
        console.print(f"[red]Could not load MCP module: {e}[/red]")
        raise typer.Exit(1)

    if not HAS_FASTMCP:
        console.print(
            "[red]fastmcp not installed.[/red] Install with: "
            "[bold]pip install fastmcp[/bold] "
            "(or, from a checkout: [bold]pip install -e \".[mcp]\"[/bold])"
        )
        raise typer.Exit(1)

    async def _run() -> None:
        engine = create_engine(config)
        engine.load_config()
        await serve_mcp(
            engine,
            transport=transport,
            host=host,
            port=port,
            server_name=server_name,
        )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


DEFAULT_CONFIG = """# SafestClaw Configuration

safestclaw:
  name: "SafestClaw"
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
