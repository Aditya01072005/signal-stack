"""Execution logic shared by scheduled jobs and manual API triggers."""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.audit import AuditLog
from app.models.brief import Brief
from app.models.company import Company
from app.schemas.scheduler import CompanyJobOutcome, SchedulerJobRunResponse
from app.services.ai.brief_generator import generate_company_brief
from app.services.monitoring.pipeline import run_company_monitoring

logger = logging.getLogger(__name__)

WEEKLY_BRIEF_JOB_ID = "weekly_monday_briefs"
MONTHLY_SOURCE_AUDIT_JOB_ID = "monthly_source_health_audit"
_WEEKLY_TASK_TYPE = "weekly_brief"
_MONTHLY_TASK_TYPE = "monthly_health_audit"


@dataclass
class _CompanyOutcome:
    status: str
    details: dict[str, Any]
    error_message: str | None = None


def _timezone() -> ZoneInfo:
    return ZoneInfo(settings.SCHEDULER_TIMEZONE)


def _local_now(value: datetime | None = None) -> datetime:
    timezone = _timezone()
    if value is None:
        return datetime.now(timezone)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def _week_start(value: datetime) -> date:
    return value.date() - timedelta(days=value.weekday())


def _active_company_ids(db: Session) -> list[uuid.UUID]:
    statement = select(Company.id).where(
        Company.status == "active",
        Company.is_deleted.is_(False),
    )
    return list(db.execute(statement).scalars().all())


def _execute_weekly_brief(
    db: Session,
    company_id: uuid.UUID,
    briefing_date: date,
) -> _CompanyOutcome:
    company_statement = (
        select(Company)
        .where(
            Company.id == company_id,
            Company.status == "active",
            Company.is_deleted.is_(False),
        )
        .with_for_update()
    )
    company = db.execute(company_statement).scalar_one_or_none()
    if company is None:
        return _CompanyOutcome(
            status="skipped",
            details={"reason": "company_is_no_longer_active"},
        )

    existing_statement = (
        select(Brief.id)
        .where(
            Brief.company_id == company_id,
            Brief.briefing_date >= briefing_date,
            Brief.briefing_date < briefing_date + timedelta(days=7),
        )
        .limit(1)
    )
    existing_brief_id = db.execute(existing_statement).scalar_one_or_none()
    if existing_brief_id is not None:
        return _CompanyOutcome(
            status="skipped",
            details={
                "reason": "brief_already_generated_for_week",
                "brief_id": str(existing_brief_id),
                "briefing_date": briefing_date.isoformat(),
            },
        )

    brief = generate_company_brief(
        company_id,
        db,
        briefing_date=briefing_date,
    )
    return _CompanyOutcome(
        status="success",
        details={
            "brief_id": str(brief.id),
            "briefing_date": briefing_date.isoformat(),
        },
    )


def _execute_monthly_source_audit(
    db: Session,
    company_id: uuid.UUID,
) -> _CompanyOutcome:
    results = run_company_monitoring(company_id, db)
    serialized_results = [
        {
            "source_id": str(result.source_id),
            "source_name": result.source_name,
            "crawl_status": result.crawl_status,
            "content_changed": result.content_changed,
            "message": result.message,
        }
        for result in results
    ]
    failed_results = [
        result for result in results if result.crawl_status != "success"
    ]
    status = "partial_failure" if failed_results else "success"
    error_message = (
        f"{len(failed_results)} of {len(results)} active source checks failed."
        if failed_results
        else None
    )
    return _CompanyOutcome(
        status=status,
        details={
            "sources_checked": len(results),
            "sources_failed": len(failed_results),
            "results": serialized_results,
        },
        error_message=error_message,
    )


def _write_audit_log(
    db: Session,
    *,
    company_id: uuid.UUID,
    task_type: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    details: dict[str, Any],
    error_message: str | None,
) -> None:
    audit_details = {
        **details,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
    db.add(
        AuditLog(
            company_id=company_id,
            task_type=task_type,
            status=status,
            details=audit_details,
            error_message=error_message,
            duration_ms=duration_ms,
            executed_at=started_at,
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to write scheduler audit log for company %s (%s).",
            company_id,
            task_type,
        )
        raise


def _run_job(
    *,
    job_id: str,
    task_type: str,
    execute_company: Callable[[Session, uuid.UUID], _CompanyOutcome],
    db: Session | None,
    session_factory: Callable[[], Session] | None,
    now: datetime | None,
) -> SchedulerJobRunResponse:
    owns_session = db is None
    started_at = _local_now(now)
    run_started = time.perf_counter()
    outcomes: list[CompanyJobOutcome] = []
    session = db

    logger.info("Scheduler job %s started at %s.", job_id, started_at.isoformat())
    try:
        if session is None:
            session = (session_factory or SessionLocal)()
        company_ids = _active_company_ids(session)
        for company_id in company_ids:
            company_started = _local_now()
            company_run_started = time.perf_counter()
            try:
                outcome = execute_company(session, company_id)
            except Exception as exc:
                session.rollback()
                company_finished = _local_now()
                error_message = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "Scheduler job %s failed for company %s.",
                    job_id,
                    company_id,
                )
                _write_audit_log(
                    session,
                    company_id=company_id,
                    task_type=task_type,
                    status="error",
                    started_at=company_started,
                    finished_at=company_finished,
                    duration_ms=int((time.perf_counter() - company_run_started) * 1000),
                    details={"job_id": job_id, "exception_type": type(exc).__name__},
                    error_message=error_message,
                )
                outcomes.append(
                    CompanyJobOutcome(
                        company_id=company_id,
                        status="error",
                        details={},
                        error_message=error_message,
                    )
                )
                continue

            company_finished = _local_now()
            audit_status = (
                "success"
                if outcome.status in {"success", "skipped"}
                else outcome.status
            )
            _write_audit_log(
                session,
                company_id=company_id,
                task_type=task_type,
                status=audit_status,
                started_at=company_started,
                finished_at=company_finished,
                duration_ms=int((time.perf_counter() - company_run_started) * 1000),
                details={"job_id": job_id, **outcome.details},
                error_message=outcome.error_message,
            )
            outcomes.append(
                CompanyJobOutcome(
                    company_id=company_id,
                    status=outcome.status,
                    details=outcome.details,
                    error_message=outcome.error_message,
                )
            )

        failed = sum(
            outcome.status in {"error", "partial_failure"}
            for outcome in outcomes
        )
        successful = sum(outcome.status == "success" for outcome in outcomes)
        skipped = sum(outcome.status == "skipped" for outcome in outcomes)
        if not failed:
            overall_status = "success"
        elif all(outcome.status == "error" for outcome in outcomes):
            overall_status = "error"
        else:
            overall_status = "partial_failure"

        finished_at = _local_now()
        duration_ms = int((time.perf_counter() - run_started) * 1000)
        logger.info(
            "Scheduler job %s finished with status=%s, companies=%d, "
            "failed=%d, started_at=%s, finished_at=%s, duration_ms=%d.",
            job_id,
            overall_status,
            len(outcomes),
            failed,
            started_at.isoformat(),
            finished_at.isoformat(),
            duration_ms,
        )
        return SchedulerJobRunResponse(
            job_id=job_id,
            status=overall_status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            companies_total=len(outcomes),
            succeeded=successful,
            skipped=skipped,
            failed=failed,
            results=outcomes,
        )
    except Exception:
        if session is not None:
            session.rollback()
        logger.exception(
            "Scheduler job %s failed before completion; started_at=%s, "
            "finished_at=%s, duration_ms=%d.",
            job_id,
            started_at.isoformat(),
            _local_now().isoformat(),
            int((time.perf_counter() - run_started) * 1000),
        )
        raise
    finally:
        if owns_session and session is not None:
            session.close()


def run_weekly_brief_job(
    db: Session | None = None,
    *,
    now: datetime | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> SchedulerJobRunResponse:
    started_at = _local_now(now)
    briefing_date = _week_start(started_at)

    return _run_job(
        job_id=WEEKLY_BRIEF_JOB_ID,
        task_type=_WEEKLY_TASK_TYPE,
        execute_company=lambda session, company_id: _execute_weekly_brief(
            session,
            company_id,
            briefing_date,
        ),
        db=db,
        session_factory=session_factory,
        now=started_at,
    )


def run_monthly_source_health_audit_job(
    db: Session | None = None,
    *,
    now: datetime | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> SchedulerJobRunResponse:
    return _run_job(
        job_id=MONTHLY_SOURCE_AUDIT_JOB_ID,
        task_type=_MONTHLY_TASK_TYPE,
        execute_company=_execute_monthly_source_audit,
        db=db,
        session_factory=session_factory,
        now=now,
    )
