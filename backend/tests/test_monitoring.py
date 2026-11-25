import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.company import Company
from app.models.signal import Signal
from app.models.source import Source
from app.services.crawler.scraper import (
    MaxRetriesExceededError,
    RobotsBlockedError,
    ScrapeResult,
)
from app.services.monitoring.pipeline import run_company_monitoring


def _company():
    company = MagicMock(spec=Company)
    company.id = uuid.uuid4()
    company.name = "Example Company"
    company.is_deleted = False
    return company


def _source(company_id):
    source = MagicMock(spec=Source)
    source.id = uuid.uuid4()
    source.company_id = company_id
    source.name = "Market updates"
    source.url = "https://example.com/updates"
    source.status = "active"
    source.health_score = 80
    source.consecutive_failures = 2
    source.last_crawled_at = None
    source.last_successful_crawl_at = None
    source.last_error_message = None
    source.created_at = datetime.now(timezone.utc)
    return source


def _scrape_result(content="A verified update from the source."):
    return ScrapeResult(
        requested_url="https://example.com/updates",
        final_url="https://example.com/updates",
        status_code=200,
        clean_text=content,
        fetch_timestamp=datetime.now(timezone.utc),
        redirect_occurred=False,
        redirect_count=0,
        robots_source_domain="example.com",
    )


def _db_result(*, scalar=None, values=None, count=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = values or []
    result.scalar.return_value = count
    return result


def _monitoring_db(company, sources, hashes=()):
    db = MagicMock()
    db.execute.side_effect = [
        _db_result(scalar=company),
        _db_result(values=sources),
        _db_result(values=list(hashes)),
    ]
    return db


def test_monitoring_creates_evidence_signal_and_updates_source_health():
    company = _company()
    source = _source(company.id)
    db = _monitoring_db(company, [source])

    with patch("app.services.monitoring.pipeline.EthicalScraper") as scraper_type:
        scraper_type.return_value.__enter__.return_value.scrape.return_value = (
            _scrape_result()
        )
        results = run_company_monitoring(company.id, db)

    assert len(results) == 1
    result = results[0]
    assert result.crawl_status == "success"
    assert result.content_changed is True
    assert result.signal_id is not None
    assert result.final_url == source.url
    assert source.last_crawled_at is not None
    assert source.last_successful_crawl_at is not None
    assert source.last_error_message is None
    assert source.consecutive_failures == 0
    assert source.health_score == 90
    db.commit.assert_called_once()

    signal = db.add.call_args.args[0]
    assert isinstance(signal, Signal)
    assert signal.company_id == company.id
    assert signal.source_id == source.id
    assert signal.source_url == "https://example.com/updates"
    assert signal.content_snippet == "A verified update from the source."
    assert signal.verbatim_quote == signal.content_snippet
    assert signal.is_verified is True
    assert signal.ai_interpretation is None
    assert signal.recommended_action is None
    assert len(signal.content_hash) == 64


def test_monitoring_skips_content_hash_already_recorded():
    company = _company()
    source = _source(company.id)
    content = "A verified update from the source."
    from app.services.monitoring.pipeline import _content_hash

    db = _monitoring_db(company, [source], [_content_hash(content)])

    with patch("app.services.monitoring.pipeline.EthicalScraper") as scraper_type:
        scraper_type.return_value.__enter__.return_value.scrape.return_value = (
            _scrape_result(content)
        )
        results = run_company_monitoring(company.id, db)

    assert results[0].content_changed is False
    assert results[0].signal_id is None
    db.add.assert_not_called()
    db.commit.assert_called_once()


def test_monitoring_records_robots_block_and_degrades_source_health():
    company = _company()
    source = _source(company.id)
    db = _monitoring_db(company, [source])

    with patch("app.services.monitoring.pipeline.EthicalScraper") as scraper_type:
        scraper_type.return_value.__enter__.return_value.scrape.side_effect = (
            RobotsBlockedError(source.url, "example.com")
        )
        results = run_company_monitoring(company.id, db)

    assert results[0].crawl_status == "blocked"
    assert results[0].content_changed is False
    assert source.last_crawled_at is not None
    assert source.last_error_message
    assert source.consecutive_failures == 3
    assert source.health_score == 60
    db.add.assert_not_called()
    db.commit.assert_called_once()


def test_monitoring_records_network_failure_and_degrades_source_health():
    company = _company()
    source = _source(company.id)
    db = _monitoring_db(company, [source])

    with patch("app.services.monitoring.pipeline.EthicalScraper") as scraper_type:
        scraper_type.return_value.__enter__.return_value.scrape.side_effect = (
            MaxRetriesExceededError(source.url, 3, "timeout")
        )
        results = run_company_monitoring(company.id, db)

    assert results[0].crawl_status == "failed"
    assert source.last_crawled_at is not None
    assert source.last_successful_crawl_at is None
    assert source.last_error_message
    assert source.consecutive_failures == 3
    assert source.health_score == 70
    db.add.assert_not_called()
    db.commit.assert_called_once()


def test_monitoring_with_no_active_sources_does_not_create_scraper():
    company = _company()
    db = _monitoring_db(company, [])

    with patch("app.services.monitoring.pipeline.EthicalScraper") as scraper_type:
        results = run_company_monitoring(company.id, db)

    assert results == []
    scraper_type.assert_not_called()


def test_monitoring_run_endpoint_returns_per_source_results():
    company = _company()
    source = _source(company.id)
    db = _monitoring_db(company, [source])
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            with patch(
                "app.services.monitoring.pipeline.EthicalScraper"
            ) as scraper_type:
                scraper_type.return_value.__enter__.return_value.scrape.return_value = (
                    _scrape_result()
                )
                response = client.post(
                    f"/api/v1/companies/{company.id}/monitoring/run"
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == str(company.id)
    assert body["sources_checked"] == 1
    assert body["crawled"] == 1
    assert body["new_signals"] == 1
    assert body["results"][0]["source_id"] == str(source.id)


def test_signal_list_endpoint_returns_company_evidence():
    company = _company()
    signal = MagicMock(spec=Signal)
    signal.id = uuid.uuid4()
    signal.company_id = company.id
    signal.source_id = uuid.uuid4()
    signal.title = "Market updates"
    signal.content_snippet = "A verified update from the source."
    signal.source_url = "https://example.com/updates"
    signal.content_hash = "a" * 64
    signal.is_verified = True
    signal.verbatim_quote = signal.content_snippet
    signal.discovered_at = datetime.now(timezone.utc)

    db = MagicMock()
    db.execute.side_effect = [
        _db_result(scalar=company.id),
        _db_result(count=1),
        _db_result(values=[signal]),
    ]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/companies/{company.id}/signals?limit=10"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["source_id"] == str(signal.source_id)
    assert body["items"][0]["verbatim_quote"] == signal.verbatim_quote


def test_monitoring_run_endpoint_returns_404_for_missing_company():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/companies/{uuid.uuid4()}/monitoring/run"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
