"""SafestClaw actions - things the assistant can do."""

from safestclaw.actions.blog import BlogAction
from safestclaw.actions.briefing import BriefingAction
from safestclaw.actions.calendar import CalendarAction
from safestclaw.actions.crawl import CrawlAction
from safestclaw.actions.email import EmailAction
from safestclaw.actions.files import FilesAction
from safestclaw.actions.news import NewsAction
from safestclaw.actions.reminder import ReminderAction
from safestclaw.actions.shell import ShellAction
from safestclaw.actions.summarize import SummarizeAction

__all__ = [
    "BlogAction",
    "FilesAction",
    "ShellAction",
    "SummarizeAction",
    "CrawlAction",
    "ReminderAction",
    "BriefingAction",
    "NewsAction",
    "EmailAction",
    "CalendarAction",
]
