"""Scheduler status and manual execution endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.scheduler import SchedulerJobRunResponse, SchedulerStatusResponse
from app.services.scheduler.jobs import (
    run_monthly_source_health_audit_job,
    run_weekly_brief_job,
)
from app.services.scheduler.scheduler import get_scheduler_status

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


@router.get("/status", response_model=SchedulerStatusResponse)
def scheduler_status() -> SchedulerStatusResponse:
    return get_scheduler_status()


@router.post(
    "/jobs/weekly-briefs/run",
    response_model=SchedulerJobRunResponse,
    summary="Manually run weekly brief generation",
)
def trigger_weekly_briefs(
    db: Session = Depends(get_db),
) -> SchedulerJobRunResponse:
    return run_weekly_brief_job(db)


@router.post(
    "/jobs/monthly-source-health-audit/run",
    response_model=SchedulerJobRunResponse,
    summary="Manually run the monthly source health audit",
)
def trigger_monthly_source_health_audit(
    db: Session = Depends(get_db),
) -> SchedulerJobRunResponse:
    return run_monthly_source_health_audit_job(db)
