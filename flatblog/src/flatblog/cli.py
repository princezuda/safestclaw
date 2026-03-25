"""flatblog CLI — standalone flat-file AI blogging system."""
from __future__ import annotations

import asyncio
import http.server
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="flatblog",
    help="Flat-file AI blogging system. Run `flatblog init` to get started.",
    no_args_is_help=True,
)
console = Console()


def _load(config_path: Path | None = None):
    from flatblog.core.config import find_config, load_config
    try:
        cfg_path = config_path or find_config()
        return load_config(cfg_path), cfg_path
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


def _root(cfg_path: Path) -> Path:
    return cfg_path.parent


# ── init ──────────────────────────────────────────────────────────────────────

@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialise"),
):
    """Initialise a new flatblog repository."""
    path = path.resolve()
    pkg_root = Path(__file__).parent.parent.parent  # flatblog/ repo root

    # Copy config template
    cfg_src = pkg_root / "config.yaml"
    cfg_dst = path / "config.yaml"
    if cfg_dst.exists():
        console.print(f"[yellow]config.yaml already exists[/yellow]")
    else:
        shutil.copy(cfg_src, cfg_dst)
        console.print(f"[green]Created config.yaml[/green]")

    # Copy default theme
    theme_src = pkg_root / "themes" / "default"
    theme_dst = path / "themes" / "default"
    if theme_dst.exists():
        console.print("[yellow]themes/default already exists[/yellow]")
    else:
        shutil.copytree(theme_src, theme_dst)
        console.print("[green]Created themes/default/[/green]")

    # Create posts/ and output/
    for d in ("posts", "output"):
        (path / d).mkdir(exist_ok=True)
        console.print(f"[green]Created {d}/[/green]")

    # Create .gitignore
    gi = path / ".gitignore"
    if not gi.exists():
        gi.write_text("output/\n*.pyc\n__pycache__/\n.flatblog/\n")
        console.print("[green]Created .gitignore[/green]")

    console.print("\n[bold]Done![/bold] Next steps:")
    console.print("  1. Edit [cyan]config.yaml[/cyan] — set blog title, author, url")
    console.print("  2. [cyan]flatblog setup ai anthropic sk-ant-...[/cyan]  (or openai/ollama)")
    console.print("  3. [cyan]flatblog new \"My first post\"[/cyan]")
    console.print("  4. [cyan]flatblog build && flatblog serve[/cyan]")


# ── new ───────────────────────────────────────────────────────────────────────

@app.command()
def new(
    title: str = typer.Argument(..., help="Post title"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """Create a new blank post."""
    from flatblog.core.post import write_post, _slugify

    cfg, cfg_path = _load(config)
    root = _root(cfg_path)
    posts_dir = root / "posts"
    author = cfg.get("blog", {}).get("author", "")
    today = datetime.today().date()
    slug = _slugify(title)
    filename = f"{today}-{slug}.md"
    path = posts_dir / filename

    if path.exists():
        console.print(f"[yellow]Already exists: {path}[/yellow]")
        raise typer.Exit(1)

    write_post(path, title=title, author=author, draft=True)
    console.print(f"[green]Created:[/green] {path.relative_to(root)}")
    console.print(f"Edit it, then run [cyan]flatblog build[/cyan] to preview.")


# ── write ─────────────────────────────────────────────────────────────────────

@app.command()
def write(
    topic: str = typer.Argument(..., help="Topic to write about"),
    draft: bool = typer.Option(True, help="Save as draft (default true)"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """AI-generate a blog post from a topic and save to posts/."""
    asyncio.run(_write(topic, draft, config))


async def _write(topic: str, draft: bool, config: Path | None) -> None:
    from flatblog.core.ai import AIWriter
    from flatblog.core.post import write_post, _slugify

    cfg, cfg_path = _load(config)
    root = _root(cfg_path)

    writer = AIWriter(cfg)
    if not writer.is_configured():
        console.print("[red]AI not configured.[/red] Run: flatblog setup ai")
        raise typer.Exit(1)

    console.print(f"Writing post about: [bold]{topic}[/bold] ...")
    try:
        title, body = await writer.generate(topic)
    except Exception as e:
        console.print(f"[red]AI error:[/red] {e}")
        raise typer.Exit(1)

    today = datetime.today().date()
    slug = _slugify(title)
    path = root / "posts" / f"{today}-{slug}.md"
    author = cfg.get("blog", {}).get("author", "")
    write_post(path, title=title, body=body, author=author, draft=draft)

    console.print(f"[green]Saved:[/green] {path.relative_to(root)}")
    console.print(f"Title: {title}")
    if draft:
        console.print("Saved as [yellow]draft[/yellow] — set draft: false to publish.")


# ── build ─────────────────────────────────────────────────────────────────────

@app.command()
def build(
    drafts: bool = typer.Option(False, "--drafts", help="Include draft posts"),
    config: Optional[Path] = typer.Option(None, "--config"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Build the static site into output/."""
    from flatblog.core.builder import build_site

    cfg, cfg_path = _load(config)
    root = _root(cfg_path)
    output_dir = root / cfg.get("output_dir", "output")

    console.print(f"Building site → [cyan]{output_dir.relative_to(root)}[/cyan]")
    try:
        count = build_site(root, cfg, include_drafts=drafts, verbose=verbose)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Built {count} posts[/green] + index.html + feed.xml")
    console.print(f"Preview: [cyan]flatblog serve[/cyan]")


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    port: int = typer.Option(4000, "--port", "-p"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """Serve the output/ directory locally for preview."""
    cfg, cfg_path = _load(config)
    root = _root(cfg_path)
    output_dir = root / cfg.get("output_dir", "output")

    if not output_dir.exists() or not any(output_dir.iterdir()):
        console.print("[yellow]output/ is empty — run `flatblog build` first.[/yellow]")
        raise typer.Exit(1)

    import os
    os.chdir(output_dir)
    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *a: None  # silence request logs

    console.print(f"Serving [cyan]http://localhost:{port}[/cyan]  (Ctrl-C to stop)")
    with http.server.HTTPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("\nStopped.")


# ── publish ───────────────────────────────────────────────────────────────────

@app.command()
def publish(
    target: str = typer.Option("", "--target", "-t", help="Target label (default: all)"),
    build_first: bool = typer.Option(True, "--build/--no-build", help="Build before publishing"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """Build (optional) then publish output/ to configured targets."""
    asyncio.run(_publish(target, build_first, config))


async def _publish(target: str, build_first: bool, config: Path | None) -> None:
    from flatblog.core.builder import build_site
    from flatblog.core.publisher import publish_all

    cfg, cfg_path = _load(config)
    root = _root(cfg_path)

    if build_first:
        console.print("Building...")
        build_site(root, cfg)

    output_dir = root / cfg.get("output_dir", "output")
    console.print("Publishing...")
    results = await publish_all(output_dir, cfg, target_label=target)
    for line in results:
        color = "green" if "error" not in line.lower() and "failed" not in line.lower() else "red"
        console.print(f"[{color}]{line}[/{color}]")


# ── run (one-shot, for cron) ──────────────────────────────────────────────────

@app.command()
def run(
    target: str = typer.Option("", "--target"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """One-shot: write next topic post, build, publish. Designed for cron."""
    asyncio.run(_run(target, config))


async def _run(target: str, config: Path | None) -> None:
    from flatblog.core.ai import AIWriter
    from flatblog.core.builder import build_site
    from flatblog.core.post import write_post, _slugify
    from flatblog.core.publisher import publish_all
    from flatblog.core.scheduler import next_topic

    cfg, cfg_path = _load(config)
    root = _root(cfg_path)

    topics_cfg = cfg.get("topics", {})
    topic_list = topics_cfg.get("list", [])

    if topic_list:
        topic = next_topic(topic_list)
        console.print(f"[blue]Topic:[/blue] {topic}")
        writer = AIWriter(cfg)
        if writer.is_configured():
            try:
                title, body = await writer.generate(topic)
                today = datetime.today().date()
                slug = _slugify(title)
                path = root / "posts" / f"{today}-{slug}.md"
                author = cfg.get("blog", {}).get("author", "")
                write_post(path, title=title, body=body, author=author, draft=False)
                console.print(f"[green]Written:[/green] {path.name}")
            except Exception as e:
                console.print(f"[yellow]AI failed ({e}), skipping write[/yellow]")
        else:
            console.print("[yellow]AI not configured, skipping write[/yellow]")
    else:
        console.print("[blue]No topics configured — building from existing posts[/blue]")

    build_site(root, cfg)
    output_dir = root / cfg.get("output_dir", "output")
    results = await publish_all(output_dir, cfg, target_label=target)
    for line in results:
        console.print(line)


# ── topics ────────────────────────────────────────────────────────────────────

@app.command()
def topics(
    action: str = typer.Argument("list", help="list | add | set | clear | tone | words"),
    value: str = typer.Argument("", help="Topic(s), tone name, or word count"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """
    Manage the AI topic rotation list.

    \b
    flatblog topics list
    flatblog topics add "Python tips"
    flatblog topics set "Python tips,AI news,Security"
    flatblog topics clear
    flatblog topics tone conversational
    flatblog topics words 900
    """
    from flatblog.core.config import save_config

    cfg, cfg_path = _load(config)
    topics_cfg = cfg.setdefault("topics", {})
    topic_list: list[str] = topics_cfg.get("list", [])

    if action == "list" or (not action):
        if not topic_list:
            console.print("No topics yet. Use: flatblog topics add \"My topic\"")
            return
        t = Table("#", "Topic")
        for i, tp in enumerate(topic_list, 1):
            t.add_row(str(i), tp)
        console.print(t)
        if topics_cfg.get("tone"):
            console.print(f"Tone: {topics_cfg['tone']}")
        if topics_cfg.get("word_count"):
            console.print(f"Words: {topics_cfg['word_count']}")

    elif action == "add":
        if not value:
            console.print("[red]Provide a topic to add.[/red]")
            raise typer.Exit(1)
        new = [t.strip() for t in value.split(",") if t.strip()]
        for tp in new:
            if tp not in topic_list:
                topic_list.append(tp)
        topics_cfg["list"] = topic_list
        save_config(cfg, cfg_path)
        console.print(f"[green]Added {len(new)} topic(s). Total: {len(topic_list)}[/green]")

    elif action == "set":
        if not value:
            console.print("[red]Provide comma-separated topics.[/red]")
            raise typer.Exit(1)
        new = [t.strip() for t in value.split(",") if t.strip()]
        topics_cfg["list"] = new
        save_config(cfg, cfg_path)
        console.print(f"[green]Set {len(new)} topics.[/green]")

    elif action == "clear":
        topics_cfg["list"] = []
        save_config(cfg, cfg_path)
        console.print("[green]Topics cleared.[/green]")

    elif action == "tone":
        topics_cfg["tone"] = value
        save_config(cfg, cfg_path)
        console.print(f"[green]Tone set to: {value}[/green]")

    elif action in ("words", "word_count", "wordcount"):
        try:
            topics_cfg["word_count"] = int(value)
            save_config(cfg, cfg_path)
            console.print(f"[green]Word count set to: {value}[/green]")
        except ValueError:
            console.print("[red]Provide a number.[/red]")

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


# ── daemon ────────────────────────────────────────────────────────────────────

@app.command()
def daemon(
    action: str = typer.Argument("help", help="daily|weekly|status|remove"),
    schedule: list[str] = typer.Argument(None, help="e.g. daily 9am  or  weekly monday 9am"),
    target: str = typer.Option("", "--target"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """
    Install a system cron job so posts publish even when flatblog is off.

    \b
    flatblog daemon daily 9am
    flatblog daemon daily 9am --target my-server
    flatblog daemon weekly monday 9am
    flatblog daemon status
    flatblog daemon remove
    """
    from flatblog.core.scheduler import install_cron, remove_cron, status_cron

    cfg, cfg_path = _load(config)
    root = _root(cfg_path)

    if action == "status":
        console.print(status_cron())
        return

    if action == "remove":
        console.print(remove_cron())
        return

    # Build schedule string from action + remaining args
    schedule_parts = [action] + list(schedule or [])
    schedule_str = " ".join(schedule_parts)

    msg = install_cron(root, schedule_str, target)
    console.print(msg)


# ── setup ─────────────────────────────────────────────────────────────────────

@app.command()
def setup(
    what: str = typer.Argument("", help="ai | publish | style"),
    args: list[str] = typer.Argument(None),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """
    Configure flatblog interactively.

    \b
    flatblog setup ai anthropic sk-ant-...
    flatblog setup ai openai sk-...
    flatblog setup ai ollama llama3.2
    flatblog setup ai status
    flatblog setup publish sftp://user:pass@host/remote/path
    flatblog setup publish wp://user:pass@mysite.com
    flatblog setup publish list
    flatblog setup style ~/my-style.md
    """
    from flatblog.core.config import save_config

    cfg, cfg_path = _load(config)
    args = args or []

    if what == "ai":
        _setup_ai(cfg, cfg_path, args)
    elif what == "publish":
        _setup_publish(cfg, cfg_path, args)
    elif what == "style":
        _setup_style(cfg, cfg_path, args)
    else:
        console.print(Panel(
            "flatblog setup ai anthropic sk-ant-...\n"
            "flatblog setup ai openai sk-...\n"
            "flatblog setup ai ollama llama3.2\n"
            "flatblog setup publish sftp://user:pass@host/path\n"
            "flatblog setup publish wp://user:pass@mysite.com\n"
            "flatblog setup style ~/my-style.md",
            title="setup options",
        ))


def _setup_ai(cfg: dict, cfg_path: Path, args: list[str]) -> None:
    from flatblog.core.config import save_config

    if not args or args[0] == "status":
        ai = cfg.get("ai", {})
        console.print(f"Provider: {ai.get('provider') or 'not set'}")
        console.print(f"Model:    {ai.get('model') or 'not set'}")
        key = ai.get("api_key", "")
        console.print(f"API key:  {'set' if key else 'not set'}")
        return

    provider = args[0].lower()
    rest = args[1:]

    models = {
        "anthropic": "claude-haiku-4-5-20251001",
        "openai": "gpt-4o-mini",
        "ollama": "llama3.2",
    }

    cfg.setdefault("ai", {})["provider"] = provider

    if provider == "ollama":
        model = rest[0] if rest else "llama3.2"
        cfg["ai"]["model"] = model
        cfg["ai"]["base_url"] = "http://localhost:11434/api"
        save_config(cfg, cfg_path)
        console.print(f"[green]Ollama configured: {model}[/green]")
        return

    # API key providers
    api_key = rest[0] if rest else ""
    model = rest[1] if len(rest) > 1 else models.get(provider, "")
    if api_key:
        cfg["ai"]["api_key"] = api_key
    if model:
        cfg["ai"]["model"] = model
    save_config(cfg, cfg_path)
    console.print(f"[green]{provider} configured (model: {cfg['ai']['model']})[/green]")


def _setup_publish(cfg: dict, cfg_path: Path, args: list[str]) -> None:
    from flatblog.core.config import save_config

    if not args or args[0] in ("list", "ls", "show"):
        targets = cfg.get("publish", {}).get("targets", [])
        if not targets:
            console.print("No targets configured.")
            return
        t = Table("label", "type", "host/url")
        for tgt in targets:
            t.add_row(
                tgt.get("label", ""),
                tgt.get("type", ""),
                tgt.get("host") or tgt.get("url", ""),
            )
        console.print(t)
        return

    if args[0] in ("remove", "rm", "delete") and len(args) > 1:
        label = args[1]
        targets = cfg.get("publish", {}).get("targets", [])
        before = len(targets)
        targets = [t for t in targets if t.get("label") != label]
        cfg.setdefault("publish", {})["targets"] = targets
        save_config(cfg, cfg_path)
        removed = before - len(targets)
        console.print(f"[green]Removed {removed} target(s).[/green]")
        return

    # Parse URL: sftp://user:pass@host:port/path or wp://user:pass@site
    url_str = args[0]
    m = re.match(
        r"(sftp|wp|wordpress|api)://(?:([^:@]*)(?::([^@]*))?@)?"
        r"([^:/]+)(?::(\d+))?(/.+)?",
        url_str,
    )
    if not m:
        console.print(
            "[red]Could not parse URL.[/red]\n"
            "Format: sftp://user:pass@host/path  or  wp://user:pass@mysite.com"
        )
        return

    scheme, user, password, host, port, path_ = m.groups()
    label = args[1] if len(args) > 1 else host

    if scheme == "sftp":
        target = {
            "label": label,
            "type": "sftp",
            "host": host,
            "port": int(port or 22),
            "user": user or "",
            "password": password or "",
            "remote_path": path_ or "/var/www/blog",
        }
    else:  # wordpress
        site_url = f"https://{host}{path_ or ''}"
        target = {
            "label": label,
            "type": "wordpress",
            "url": site_url,
            "user": user or "",
            "app_password": password or "",
        }

    targets = cfg.setdefault("publish", {}).setdefault("targets", [])
    targets = [t for t in targets if t.get("label") != target["label"]]
    targets.append(target)
    cfg["publish"]["targets"] = targets
    save_config(cfg, cfg_path)
    console.print(f"[green]Target '{label}' saved.[/green]")


def _setup_style(cfg: dict, cfg_path: Path, args: list[str]) -> None:
    from flatblog.core.config import save_config

    if not args or args[0] in ("show", "status"):
        style = cfg.get("topics", {}).get("style_file", "")
        console.print(f"Style file: {style or 'not set'}")
        return

    if args[0] in ("clear", "remove", "reset"):
        cfg.setdefault("topics", {}).pop("style_file", None)
        save_config(cfg, cfg_path)
        console.print("[green]Style file cleared.[/green]")
        return

    path_str = args[0]
    p = Path(path_str).expanduser()
    if not p.exists():
        console.print(f"[red]File not found: {p}[/red]")
        return

    cfg.setdefault("topics", {})["style_file"] = str(p)
    save_config(cfg, cfg_path)
    preview = p.read_text(encoding="utf-8")[:200]
    console.print(f"[green]Style file set: {p}[/green]")
    console.print(f"Preview: {preview}...")


# ── status ────────────────────────────────────────────────────────────────────

@app.command()
def status(config: Optional[Path] = typer.Option(None, "--config")):
    """Show flatblog configuration summary."""
    cfg, cfg_path = _load(config)
    root = _root(cfg_path)
    posts_dir = root / "posts"

    blog = cfg.get("blog", {})
    ai = cfg.get("ai", {})
    topics_cfg = cfg.get("topics", {})
    publish_cfg = cfg.get("publish", {})

    from flatblog.core.post import load_all_posts
    posts = load_all_posts(posts_dir, include_drafts=True)
    published = [p for p in posts if not p.draft]
    drafts = [p for p in posts if p.draft]

    console.print(Panel(
        f"[bold]{blog.get('title', 'Untitled')}[/bold]\n"
        f"Author: {blog.get('author', '?')}\n"
        f"URL:    {blog.get('url', 'not set')}",
        title="blog",
    ))
    console.print(Panel(
        f"Provider: {ai.get('provider') or '[yellow]not set[/yellow]'}\n"
        f"Model:    {ai.get('model') or '[yellow]not set[/yellow]'}\n"
        f"Key:      {'set' if ai.get('api_key') else '[yellow]not set[/yellow]'}",
        title="AI",
    ))
    topics_list = topics_cfg.get("list", [])
    console.print(Panel(
        f"Topics: {len(topics_list)}  "
        f"({'none' if not topics_list else ', '.join(topics_list[:3])}{'...' if len(topics_list) > 3 else ''})\n"
        f"Tone:   {topics_cfg.get('tone') or 'default'}\n"
        f"Words:  {topics_cfg.get('word_count', 800)}",
        title="topics",
    ))
    targets = publish_cfg.get("targets", [])
    console.print(Panel(
        "\n".join(
            f"  {t.get('label')}: {t.get('type')} → {t.get('host') or t.get('url')}"
            for t in targets
        ) or "[yellow]no targets — run: flatblog setup publish[/yellow]",
        title="publish targets",
    ))
    console.print(Panel(
        f"Posts:  {len(published)}\nDrafts: {len(drafts)}",
        title="content",
    ))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
