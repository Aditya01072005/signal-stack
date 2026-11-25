"""Response schemas for scheduled and manually triggered jobs."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScheduledJobStatus(BaseModel):
    id: str
    name: str
    trigger: str
    next_run_time: datetime | None = None


class SchedulerStatusResponse(BaseModel):
    is_running: bool
    timezone: str
    jobs: list[ScheduledJobStatus]


class CompanyJobOutcome(BaseModel):
    company_id: uuid.UUID
    status: Literal["success", "skipped", "partial_failure", "error"]
    details: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class SchedulerJobRunResponse(BaseModel):
    job_id: str
    status: Literal["success", "partial_failure", "error"]
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    companies_total: int
    succeeded: int
    skipped: int
    failed: int
    results: list[CompanyJobOutcome]
