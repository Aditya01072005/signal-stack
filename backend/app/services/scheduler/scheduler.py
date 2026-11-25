"""APScheduler lifecycle and schedule inspection."""

import logging
from threading import RLock
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.schemas.scheduler import ScheduledJobStatus, SchedulerStatusResponse
from app.services.scheduler.jobs import (
    MONTHLY_SOURCE_AUDIT_JOB_ID,
    WEEKLY_BRIEF_JOB_ID,
    run_monthly_source_health_audit_job,
    run_weekly_brief_job,
)

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = RLock()


def start_scheduler() -> BackgroundScheduler:
    """Start one in-process scheduler with stable, replaceable job IDs."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return _scheduler

        timezone = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        scheduler = BackgroundScheduler(
            timezone=timezone,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 6 * 60 * 60,
            },
        )
        scheduler.add_job(
            run_weekly_brief_job,
            trigger=CronTrigger(
                day_of_week="mon",
                hour=8,
                minute=0,
                timezone=timezone,
            ),
            id=WEEKLY_BRIEF_JOB_ID,
            name="Monday Morning Executive Briefs",
            replace_existing=True,
        )
        scheduler.add_job(
            run_monthly_source_health_audit_job,
            trigger=CronTrigger(
                day=1,
                hour=9,
                minute=0,
                timezone=timezone,
            ),
            id=MONTHLY_SOURCE_AUDIT_JOB_ID,
            name="Monthly Source Health Audit",
            replace_existing=True,
        )
        scheduler.start()
        _scheduler = scheduler
        logger.info("Background scheduler started in timezone %s.", timezone)
        return scheduler


def shutdown_scheduler() -> None:
    """Stop the scheduler during application shutdown."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            if _scheduler.running:
                _scheduler.shutdown(wait=False)
            _scheduler = None
            logger.info("Background scheduler stopped.")


def get_scheduler_status() -> SchedulerStatusResponse:
    with _scheduler_lock:
        scheduler = _scheduler
        if scheduler is None:
            return SchedulerStatusResponse(
                is_running=False,
                timezone=settings.SCHEDULER_TIMEZONE,
                jobs=[],
            )

        jobs = [
            ScheduledJobStatus(
                id=job.id,
                name=job.name,
                trigger=str(job.trigger),
                next_run_time=job.next_run_time,
            )
            for job in scheduler.get_jobs()
        ]
        return SchedulerStatusResponse(
            is_running=scheduler.running,
            timezone=settings.SCHEDULER_TIMEZONE,
            jobs=jobs,
        )
