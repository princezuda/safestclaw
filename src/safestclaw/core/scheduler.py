"""
SafestClaw Scheduler - Cron jobs, triggers, and timed events.

Uses APScheduler for robust scheduling. No cloud required.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Task scheduler using APScheduler.

    Supports:
    - One-time scheduled tasks
    - Recurring tasks (cron syntax)
    - Interval-based tasks
    - Dynamic job management
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, str] = {}  # name -> job_id mapping

    async def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def add_job(
        self,
        name: str,
        func: Callable,
        trigger_type: str = "date",
        **trigger_args: Any,
    ) -> str:
        """
        Add a scheduled job.

        Args:
            name: Unique name for the job
            func: Async function to call
            trigger_type: "date", "interval", or "cron"
            **trigger_args: Arguments for the trigger

        Returns:
            Job ID
        """
        # Remove existing job with same name
        if name in self._jobs:
            self.remove_job(name)

        # Create trigger
        if trigger_type == "date":
            trigger = DateTrigger(**trigger_args)
        elif trigger_type == "interval":
            trigger = IntervalTrigger(**trigger_args)
        elif trigger_type == "cron":
            trigger = CronTrigger(**trigger_args)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")

        # Add job
        job = self._scheduler.add_job(func, trigger, id=name)
        self._jobs[name] = job.id
        logger.info(f"Added job: {name} ({trigger_type})")

        return job.id

    def add_one_time(
        self,
        name: str,
        func: Callable,
        run_at: datetime,
    ) -> str:
        """Add a one-time scheduled job."""
        return self.add_job(name, func, trigger_type="date", run_date=run_at)

    def add_interval(
        self,
        name: str,
        func: Callable,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        days: int | None = None,
    ) -> str:
        """Add an interval-based recurring job."""
        kwargs: dict[str, int] = {}
        if seconds:
            kwargs["seconds"] = seconds
        if minutes:
            kwargs["minutes"] = minutes
        if hours:
            kwargs["hours"] = hours
        if days:
            kwargs["days"] = days

        return self.add_job(name, func, trigger_type="interval", **kwargs)

    def add_cron(
        self,
        name: str,
        func: Callable,
        cron_expr: str | None = None,
        **cron_args: Any,
    ) -> str:
        """
        Add a cron-based recurring job.

        Args:
            name: Job name
            func: Function to call
            cron_expr: Cron expression (e.g., "0 9 * * *" for 9am daily)
            **cron_args: Individual cron fields (hour, minute, day, etc.)
        """
        if cron_expr:
            # Parse cron expression
            parts = cron_expr.split()
            if len(parts) == 5:
                cron_args = {
                    "minute": parts[0],
                    "hour": parts[1],
                    "day": parts[2],
                    "month": parts[3],
                    "day_of_week": parts[4],
                }

        return self.add_job(name, func, trigger_type="cron", **cron_args)

    def remove_job(self, name: str) -> bool:
        """Remove a job by name."""
        if name in self._jobs:
            try:
                self._scheduler.remove_job(self._jobs[name])
                del self._jobs[name]
                logger.info(f"Removed job: {name}")
                return True
            except Exception as e:
                logger.warning(f"Failed to remove job {name}: {e}")

        return False

    def pause_job(self, name: str) -> bool:
        """Pause a job."""
        if name in self._jobs:
            self._scheduler.pause_job(self._jobs[name])
            logger.info(f"Paused job: {name}")
            return True
        return False

    def resume_job(self, name: str) -> bool:
        """Resume a paused job."""
        if name in self._jobs:
            self._scheduler.resume_job(self._jobs[name])
            logger.info(f"Resumed job: {name}")
            return True
        return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.id,
                "next_run": job.next_run_time,
                "trigger": str(job.trigger),
            })
        return jobs

    def get_job(self, name: str) -> dict[str, Any] | None:
        """Get job details by name."""
        if name not in self._jobs:
            return None

        job = self._scheduler.get_job(self._jobs[name])
        if job:
            return {
                "id": job.id,
                "name": job.id,
                "next_run": job.next_run_time,
                "trigger": str(job.trigger),
            }
        return None
