"""Mocked tests for scheduler registration and job execution."""

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.models.audit import AuditLog
from app.models.brief import Brief
from app.models.company import Company
from app.schemas.scheduler import (
    ScheduledJobStatus,
    SchedulerJobRunResponse,
    SchedulerStatusResponse,
)
from app.services.monitoring.pipeline import SourceMonitoringResult
from app.services.scheduler import jobs
from app.services.scheduler import scheduler as scheduler_service


@pytest.fixture(autouse=True)
def clear_scheduler_state(monkeypatch):
    monkeypatch.setattr(scheduler_service, "_scheduler", None)
    from app.main import app

    yield
    app.dependency_overrides.clear()


def _result(*, scalar=None, items=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = items or []
    return result


def _company():
    company = MagicMock(spec=Company)
    company.id = uuid.uuid4()
    company.status = "active"
    company.is_deleted = False
    return company


def _db(*results):
    db = MagicMock()
    db.execute.side_effect = list(results)
    return db


def _run_response(job_id="weekly_monday_briefs"):
    now = datetime.now(timezone.utc)
    return SchedulerJobRunResponse(
        job_id=job_id,
        status="success",
        started_at=now,
        finished_at=now,
        duration_ms=1,
        companies_total=0,
        succeeded=0,
        skipped=0,
        failed=0,
        results=[],
    )


class TestSchedulerRegistration:
    def test_start_is_idempotent_and_registers_stable_jobs(self, monkeypatch):
        class FakeScheduler:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.jobs = {}
                self.running = False

            def add_job(self, function, **kwargs):
                self.jobs[kwargs["id"]] = (function, kwargs)

            def start(self):
                self.running = True

            def get_jobs(self):
                return []

        fake_scheduler = FakeScheduler()
        constructor = MagicMock(return_value=fake_scheduler)
        monkeypatch.setattr(
            scheduler_service, "BackgroundScheduler", constructor
        )
        monkeypatch.setattr(
            scheduler_service.settings, "SCHEDULER_TIMEZONE", "Asia/Kolkata"
        )

        first = scheduler_service.start_scheduler()
        second = scheduler_service.start_scheduler()

        assert first is second
        assert constructor.call_count == 1
        assert set(fake_scheduler.jobs) == {
            jobs.WEEKLY_BRIEF_JOB_ID,
            jobs.MONTHLY_SOURCE_AUDIT_JOB_ID,
        }
        assert all(
            job_options["replace_existing"] is True
            for _, job_options in fake_scheduler.jobs.values()
        )
        assert constructor.call_args.kwargs["job_defaults"]["max_instances"] == 1
        assert "mon" in str(
            fake_scheduler.jobs[jobs.WEEKLY_BRIEF_JOB_ID][1]["trigger"]
        )
        assert "day='1'" in str(
            fake_scheduler.jobs[jobs.MONTHLY_SOURCE_AUDIT_JOB_ID][1]["trigger"]
        )

    def test_status_reports_configured_timezone_and_jobs(self, monkeypatch):
        fake_job = SimpleNamespace(
            id="weekly_monday_briefs",
            name="Monday Morning Executive Briefs",
            trigger="weekly trigger",
            next_run_time=datetime(2026, 11, 30, 8, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
        fake_scheduler = MagicMock()
        fake_scheduler.running = True
        fake_scheduler.get_jobs.return_value = [fake_job]
        monkeypatch.setattr(scheduler_service, "_scheduler", fake_scheduler)
        monkeypatch.setattr(
            scheduler_service.settings, "SCHEDULER_TIMEZONE", "Asia/Kolkata"
        )

        status = scheduler_service.get_scheduler_status()

        assert status.is_running is True
        assert status.timezone == "Asia/Kolkata"
        assert status.jobs[0].id == "weekly_monday_briefs"
        assert status.jobs[0].next_run_time == fake_job.next_run_time


class TestWeeklyBriefJob:
    def test_scheduled_run_owns_and_closes_its_session(self):
        db = _db(_result(items=[]))
        session_factory = MagicMock(return_value=db)

        result = jobs.run_weekly_brief_job(
            now=datetime(2026, 1, 7, tzinfo=timezone.utc),
            session_factory=session_factory,
        )

        session_factory.assert_called_once_with()
        db.close.assert_called_once_with()
        assert result.status == "success"
        assert result.companies_total == 0

    def test_generates_once_for_active_company_and_audits_success(self):
        company = _company()
        brief = MagicMock(spec=Brief)
        brief.id = uuid.uuid4()
        db = _db(
            _result(items=[company.id]),
            _result(scalar=company),
            _result(scalar=None),
        )
        run_at = datetime(2026, 1, 7, 10, tzinfo=timezone.utc)

        with patch.object(jobs, "generate_company_brief", return_value=brief) as generate:
            result = jobs.run_weekly_brief_job(db, now=run_at)

        generate.assert_called_once_with(
            company.id,
            db,
            briefing_date=date(2026, 1, 5),
        )
        assert result.status == "success"
        assert result.succeeded == 1
        audit = db.add.call_args.args[0]
        assert isinstance(audit, AuditLog)
        assert audit.status == "success"
        assert audit.task_type == "weekly_brief"
        assert audit.details["briefing_date"] == "2026-01-05"
        assert audit.executed_at.tzinfo is not None
        assert db.commit.called

    def test_skips_existing_brief_for_week(self):
        company = _company()
        existing_id = uuid.uuid4()
        db = _db(
            _result(items=[company.id]),
            _result(scalar=company),
            _result(scalar=existing_id),
        )

        with patch.object(jobs, "generate_company_brief") as generate:
            result = jobs.run_weekly_brief_job(
                db,
                now=datetime(2026, 1, 7, tzinfo=timezone.utc),
            )

        generate.assert_not_called()
        assert result.status == "success"
        assert result.skipped == 1
        assert result.results[0].status == "skipped"
        assert result.results[0].details["brief_id"] == str(existing_id)

    def test_records_generation_failure(self):
        company = _company()
        db = _db(
            _result(items=[company.id]),
            _result(scalar=company),
            _result(scalar=None),
        )

        with patch.object(
            jobs,
            "generate_company_brief",
            side_effect=RuntimeError("brief generation failed"),
        ):
            result = jobs.run_weekly_brief_job(db)

        assert result.status == "error"
        assert result.failed == 1
        assert result.results[0].error_message == (
            "RuntimeError: brief generation failed"
        )
        audit = db.add.call_args.args[0]
        assert audit.status == "error"
        assert audit.error_message == result.results[0].error_message
        assert db.rollback.called


class TestMonthlySourceAudit:
    def test_uses_monitoring_pipeline_and_records_partial_failure(self):
        company = _company()
        failed_source = SourceMonitoringResult(
            source_id=uuid.uuid4(),
            source_name="Company news",
            crawl_status="failed",
            content_changed=False,
            signal_id=None,
            characters_scraped=None,
            final_url=None,
            message="Fetch failed",
        )
        db = _db(_result(items=[company.id]))

        with patch.object(
            jobs,
            "run_company_monitoring",
            return_value=[failed_source],
        ) as monitor:
            result = jobs.run_monthly_source_health_audit_job(
                db,
                now=datetime(2026, 11, 1, tzinfo=timezone.utc),
            )

        monitor.assert_called_once_with(company.id, db)
        assert result.status == "partial_failure"
        assert result.results[0].status == "partial_failure"
        audit = db.add.call_args.args[0]
        assert audit.status == "partial_failure"
        assert audit.task_type == "monthly_health_audit"
        assert audit.details["sources_failed"] == 1


class TestSchedulerAPI:
    def test_status_endpoint(self, monkeypatch):
        from app.api.v1 import scheduler as scheduler_api
        from app.main import app

        expected = SchedulerStatusResponse(
            is_running=True,
            timezone="Asia/Kolkata",
            jobs=[
                ScheduledJobStatus(
                    id="weekly_monday_briefs",
                    name="Monday Morning Executive Briefs",
                    trigger="weekly",
                )
            ],
        )
        monkeypatch.setattr(
            scheduler_api, "get_scheduler_status", lambda: expected
        )

        response = TestClient(app).get("/api/v1/scheduler/status")

        assert response.status_code == 200
        assert response.json()["timezone"] == "Asia/Kolkata"
        assert response.json()["jobs"][0]["id"] == "weekly_monday_briefs"

    @pytest.mark.parametrize(
        ("path", "job_id", "function_name"),
        [
            (
                "/api/v1/scheduler/jobs/weekly-briefs/run",
                "weekly_monday_briefs",
                "run_weekly_brief_job",
            ),
            (
                "/api/v1/scheduler/jobs/monthly-source-health-audit/run",
                "monthly_source_health_audit",
                "run_monthly_source_health_audit_job",
            ),
        ],
    )
    def test_manual_trigger_endpoints(self, monkeypatch, path, job_id, function_name):
        from app.api.v1 import scheduler as scheduler_api
        from app.database import get_db
        from app.main import app

        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        monkeypatch.setattr(
            scheduler_api,
            function_name,
            lambda provided_db: _run_response(job_id),
        )

        response = TestClient(app).post(path)

        assert response.status_code == 200
        assert response.json()["job_id"] == job_id
        assert response.json()["status"] == "success"
