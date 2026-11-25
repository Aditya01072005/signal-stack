"""
Unit tests for Source Manager (Phase 3, Module 4).

All external dependencies are mocked:
  - No real database access.
  - No real network requests.
  - No Ollama.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.crawler.scraper import (
    FetchBlockedError,
    MaxRetriesExceededError,
    RobotsBlockedError,
    RobotsUnavailableError,
    SSRFBlockedError,
    ScrapeResult,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_company(deleted: bool = False) -> MagicMock:
    from app.models.company import Company
    c = MagicMock(spec=Company)
    c.id = uuid.uuid4()
    c.name = "Test Corp"
    c.website_url = "https://testcorp.com"
    c.is_deleted = deleted
    return c


def _make_source(company_id=None, status="active", url="https://example.com") -> MagicMock:
    from app.models.source import Source
    s = MagicMock(spec=Source)
    s.id = uuid.uuid4()
    s.company_id = company_id or uuid.uuid4()
    s.name = "Test Source"
    s.url = url
    s.category = "Market"
    s.justification_reason = "Relevant market news"
    s.source_type = "html"
    s.status = status
    s.health_score = 100
    s.last_crawled_at = None
    s.last_successful_crawl_at = None
    s.last_error_message = None
    s.consecutive_failures = 0
    s.created_at = datetime.now(timezone.utc)
    return s


def _make_scrape_result(url: str = "https://example.com", text: str = "Some content") -> ScrapeResult:
    return ScrapeResult(
        requested_url=url,
        final_url=url,
        status_code=200,
        clean_text=text,
        fetch_timestamp=datetime.now(timezone.utc),
        redirect_occurred=False,
        redirect_count=0,
        robots_source_domain="example.com",
    )


def _make_db(*scalar_returns, scalar_count=0, scalar_items=None) -> MagicMock:
    """
    Build a mock DB session.

    scalar_returns: positional values returned by scalar_one_or_none() in order.
    scalar_count:   value returned by scalar() (for COUNT queries).
    scalar_items:   list returned by scalars().all() (for list queries).

    Usage examples:
      _make_db(company)                    # only company lookup
      _make_db(company, source)            # company then source lookup
      _make_db(company, dup_source)        # company then dup-check (add source)
      _make_db(company, source, dup)       # company, source, then dup-check (update)
    """
    db = MagicMock()
    returns = list(scalar_returns)
    call_count = [0]

    def _scalar_one_or_none():
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(returns):
            return returns[idx]
        return None

    db.execute.return_value.scalar_one_or_none.side_effect = _scalar_one_or_none
    db.execute.return_value.scalar.return_value = scalar_count
    db.execute.return_value.scalars.return_value.all.return_value = scalar_items or []
    return db


def _client(db_mock) -> TestClient:
    from app.main import app
    from app.database import get_db
    app.dependency_overrides[get_db] = lambda: db_mock
    return TestClient(app, raise_server_exceptions=False)


# ===========================================================================
# 1. Schema validation — URL and category
# ===========================================================================

class TestSourceSchemaValidation:

    def test_invalid_url_scheme_rejected(self):
        from app.schemas.source import SourceCreate
        with pytest.raises(Exception):
            SourceCreate(name="S", url="ftp://example.com", category="Market")

    def test_empty_url_rejected(self):
        from app.schemas.source import SourceCreate
        with pytest.raises(Exception):
            SourceCreate(name="S", url="", category="Market")

    def test_missing_scheme_rejected(self):
        from app.schemas.source import SourceCreate
        with pytest.raises(Exception):
            SourceCreate(name="S", url="example.com", category="Market")

    def test_invalid_category_rejected(self):
        from app.schemas.source import SourceCreate
        with pytest.raises(Exception):
            SourceCreate(name="S", url="https://example.com", category="Finance")

    def test_valid_categories_accepted(self):
        from app.schemas.source import SourceCreate
        for cat in ("Customers", "Competitors", "Market", "Internal"):
            obj = SourceCreate(name="S", url="https://example.com", category=cat)
            assert obj.category == cat

    def test_valid_http_url_accepted(self):
        from app.schemas.source import SourceCreate
        obj = SourceCreate(name="S", url="http://example.com", category="Market")
        assert obj.url == "http://example.com"

    def test_blank_name_rejected(self):
        from app.schemas.source import SourceCreate
        with pytest.raises(Exception):
            SourceCreate(name="   ", url="https://example.com", category="Market")


# ===========================================================================
# 2. Add Source endpoint
# ===========================================================================

class TestAddSource:

    def _post(self, company_id, payload, db):
        return _client(db).post(f"/api/v1/companies/{company_id}/sources", json=payload)

    def test_add_source_success_returns_201(self):
        company = _make_company()
        db = _make_db(company, None)  # company lookup, then dup check → None
        added = []
        db.add.side_effect = added.append

        def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.source_type = "html"
            obj.status = "active"
            obj.health_score = 100
            obj.consecutive_failures = 0
            obj.last_crawled_at = None
            obj.last_successful_crawl_at = None
            obj.last_error_message = None
            obj.created_at = datetime.now(timezone.utc)

        db.refresh.side_effect = _refresh

        resp = self._post(company.id, {
            "name": "TechCrunch",
            "url": "https://techcrunch.com",
            "category": "Market",
            "description": "Tech news",
        }, db)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "TechCrunch"
        assert body["category"] == "Market"
        assert body["status"] == "active"

    def test_add_source_company_not_found_returns_404(self):
        db = _make_db(None)
        resp = _client(db).post(
            f"/api/v1/companies/{uuid.uuid4()}/sources",
            json={"name": "S", "url": "https://example.com", "category": "Market"},
        )
        assert resp.status_code == 404

    def test_add_source_deleted_company_returns_404(self):
        company = _make_company(deleted=True)
        db = _make_db(None)  # soft-deleted → not returned
        resp = _client(db).post(
            f"/api/v1/companies/{company.id}/sources",
            json={"name": "S", "url": "https://example.com", "category": "Market"},
        )
        assert resp.status_code == 404

    def test_add_source_duplicate_url_returns_409(self):
        company = _make_company()
        existing_source = _make_source(company_id=company.id)
        db = _make_db(company, existing_source)  # company lookup, then dup check → existing
        resp = self._post(company.id, {
            "name": "Duplicate",
            "url": existing_source.url,
            "category": "Market",
        }, db)
        assert resp.status_code == 409

    def test_add_source_invalid_category_returns_422(self):
        company = _make_company()
        db = _make_db(company)
        resp = self._post(company.id, {
            "name": "S",
            "url": "https://example.com",
            "category": "Finance",
        }, db)
        assert resp.status_code == 422

    def test_add_source_invalid_url_returns_422(self):
        company = _make_company()
        db = _make_db(company)
        resp = self._post(company.id, {
            "name": "S",
            "url": "ftp://example.com",
            "category": "Market",
        }, db)
        assert resp.status_code == 422

    def test_add_source_description_optional(self):
        company = _make_company()
        db = _make_db(company, None)  # company lookup, then dup check → None
        added = []
        db.add.side_effect = added.append

        def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.source_type = "html"
            obj.status = "active"
            obj.health_score = 100
            obj.consecutive_failures = 0
            obj.last_crawled_at = None
            obj.last_successful_crawl_at = None
            obj.last_error_message = None
            obj.created_at = datetime.now(timezone.utc)

        db.refresh.side_effect = _refresh
        resp = self._post(company.id, {
            "name": "No Desc",
            "url": "https://nodesc.com",
            "category": "Competitors",
        }, db)
        assert resp.status_code == 201


# ===========================================================================
# 3. List Sources endpoint
# ===========================================================================

class TestListSources:

    def test_list_returns_200_with_items(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, scalar_count=1, scalar_items=[src])

        resp = _client(db).get(f"/api/v1/companies/{company.id}/sources")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "Test Source"

    def test_list_company_not_found_returns_404(self):
        db = _make_db(None)
        resp = _client(db).get(f"/api/v1/companies/{uuid.uuid4()}/sources")
        assert resp.status_code == 404

    def test_list_category_filter_invalid_returns_422(self):
        company = _make_company()
        db = _make_db(company)
        resp = _client(db).get(
            f"/api/v1/companies/{company.id}/sources?category=Finance"
        )
        assert resp.status_code == 422

    def test_list_category_filter_valid(self):
        company = _make_company()
        db = _make_db(company)
        resp = _client(db).get(
            f"/api/v1/companies/{company.id}/sources?category=Customers"
        )
        assert resp.status_code == 200

    def test_list_pagination_params(self):
        company = _make_company()
        db = _make_db(company)
        resp = _client(db).get(
            f"/api/v1/companies/{company.id}/sources?skip=5&limit=10"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["skip"] == 5
        assert body["limit"] == 10

    def test_list_empty_returns_zero_total(self):
        company = _make_company()
        db = _make_db(company)
        resp = _client(db).get(f"/api/v1/companies/{company.id}/sources")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ===========================================================================
# 4. Get Source endpoint
# ===========================================================================

class TestGetSource:

    def test_get_source_success(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, src)  # company lookup, then source lookup
        resp = _client(db).get(
            f"/api/v1/companies/{company.id}/sources/{src.id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(src.id)

    def test_get_source_company_not_found_returns_404(self):
        db = _make_db(None)
        resp = _client(db).get(
            f"/api/v1/companies/{uuid.uuid4()}/sources/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_get_source_wrong_company_returns_404(self):
        company = _make_company()
        db = _make_db(company, None)  # company found, source not found
        resp = _client(db).get(
            f"/api/v1/companies/{company.id}/sources/{uuid.uuid4()}"
        )
        assert resp.status_code == 404


# ===========================================================================
# 5. Update Source endpoint
# ===========================================================================

class TestUpdateSource:

    def _patch(self, company_id, source_id, payload, db):
        return _client(db).patch(
            f"/api/v1/companies/{company_id}/sources/{source_id}", json=payload
        )

    def test_update_name_succeeds(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, src)  # company, then source
        db.refresh.side_effect = lambda obj: None
        resp = self._patch(company.id, src.id, {"name": "New Name"}, db)
        assert resp.status_code == 200
        assert src.name == "New Name"

    def test_update_category_succeeds(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        resp = self._patch(company.id, src.id, {"category": "Competitors"}, db)
        assert resp.status_code == 200
        assert src.category == "Competitors"

    def test_update_description_succeeds(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        resp = self._patch(company.id, src.id, {"description": "Updated reason"}, db)
        assert resp.status_code == 200
        assert src.justification_reason == "Updated reason"

    def test_update_active_false_sets_inactive(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        resp = self._patch(company.id, src.id, {"active": False}, db)
        assert resp.status_code == 200
        assert src.status == "inactive"

    def test_update_active_true_sets_active(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="inactive")
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        resp = self._patch(company.id, src.id, {"active": True}, db)
        assert resp.status_code == 200
        assert src.status == "active"

    def test_update_invalid_category_returns_422(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, src)
        resp = self._patch(company.id, src.id, {"category": "Finance"}, db)
        assert resp.status_code == 422

    def test_update_invalid_url_returns_422(self):
        company = _make_company()
        src = _make_source(company_id=company.id)
        db = _make_db(company, src)
        resp = self._patch(company.id, src.id, {"url": "ftp://bad.com"}, db)
        assert resp.status_code == 422

    def test_update_company_not_found_returns_404(self):
        db = _make_db(None)
        resp = self._patch(uuid.uuid4(), uuid.uuid4(), {"name": "X"}, db)
        assert resp.status_code == 404

    def test_update_source_not_found_returns_404(self):
        company = _make_company()
        db = _make_db(company, None)  # company found, source not found
        resp = self._patch(company.id, uuid.uuid4(), {"name": "X"}, db)
        assert resp.status_code == 404

    def test_update_duplicate_url_returns_409(self):
        company = _make_company()
        src = _make_source(company_id=company.id, url="https://original.com")
        other = _make_source(company_id=company.id, url="https://taken.com")
        # PATCH call order: company lookup → source lookup → dup check returns other
        db = _make_db(company, src, other)

        resp = self._patch(company.id, src.id, {"url": "https://taken.com"}, db)
        assert resp.status_code == 409


# ===========================================================================
# 6. Deactivate Source endpoint
# ===========================================================================

class TestDeactivateSource:

    def test_deactivate_active_source_returns_200(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        resp = _client(db).delete(
            f"/api/v1/companies/{company.id}/sources/{src.id}"
        )
        assert resp.status_code == 200
        assert src.status == "inactive"

    def test_deactivate_already_inactive_returns_409(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="inactive")
        db = _make_db(company, src)
        resp = _client(db).delete(
            f"/api/v1/companies/{company.id}/sources/{src.id}"
        )
        assert resp.status_code == 409

    def test_deactivate_preserves_source_record(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        original_url = src.url
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        _client(db).delete(f"/api/v1/companies/{company.id}/sources/{src.id}")
        # Source row still exists with original URL intact
        assert src.url == original_url

    def test_deactivate_company_not_found_returns_404(self):
        db = _make_db(None)
        resp = _client(db).delete(
            f"/api/v1/companies/{uuid.uuid4()}/sources/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    def test_deactivate_source_not_found_returns_404(self):
        company = _make_company()
        db = _make_db(company, None)  # company found, source not found
        resp = _client(db).delete(
            f"/api/v1/companies/{company.id}/sources/{uuid.uuid4()}"
        )
        assert resp.status_code == 404


# ===========================================================================
# 7. Crawl Source endpoint
# ===========================================================================

class TestCrawlSource:

    def _crawl(self, company_id, source_id, db):
        return _client(db).post(
            f"/api/v1/companies/{company_id}/sources/{source_id}/crawl"
        )

    def test_crawl_success_returns_200(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        scrape_result = _make_scrape_result(url=src.url, text="Market intelligence content")

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.return_value = scrape_result
            resp = self._crawl(company.id, src.id, db)

        assert resp.status_code == 200
        body = resp.json()
        assert body["crawl_status"] == "success"
        assert body["characters_scraped"] == len("Market intelligence content")
        assert body["final_url"] == src.url

    def test_crawl_updates_last_crawled_at(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        scrape_result = _make_scrape_result()

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.return_value = scrape_result
            self._crawl(company.id, src.id, db)

        assert src.last_crawled_at is not None

    def test_crawl_success_resets_consecutive_failures(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        src.consecutive_failures = 3
        db = _make_db(company, src)
        db.refresh.side_effect = lambda obj: None
        scrape_result = _make_scrape_result()

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.return_value = scrape_result
            self._crawl(company.id, src.id, db)

        assert src.consecutive_failures == 0

    def test_crawl_robots_blocked_returns_blocked_status(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                RobotsBlockedError(src.url, "example.com")
            )
            resp = self._crawl(company.id, src.id, db)

        assert resp.status_code == 200
        body = resp.json()
        assert body["crawl_status"] == "blocked"
        assert body["characters_scraped"] is None

    def test_crawl_robots_unavailable_returns_blocked_status(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                RobotsUnavailableError("example.com", "timeout")
            )
            resp = self._crawl(company.id, src.id, db)

        assert resp.status_code == 200
        assert resp.json()["crawl_status"] == "blocked"

    def test_crawl_ssrf_blocked_returns_blocked_status(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active", url="http://192.168.1.1")
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                SSRFBlockedError("http://192.168.1.1", "private IP")
            )
            resp = self._crawl(company.id, src.id, db)

        assert resp.status_code == 200
        assert resp.json()["crawl_status"] == "blocked"

    def test_crawl_fetch_blocked_returns_blocked_status(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                FetchBlockedError(src.url, 403)
            )
            resp = self._crawl(company.id, src.id, db)

        assert resp.status_code == 200
        assert resp.json()["crawl_status"] == "blocked"

    def test_crawl_network_failure_returns_failed_status(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                MaxRetriesExceededError(src.url, 3, "connection refused")
            )
            resp = self._crawl(company.id, src.id, db)

        assert resp.status_code == 200
        assert resp.json()["crawl_status"] == "failed"

    def test_crawl_blocked_increments_consecutive_failures(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        src.consecutive_failures = 1
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                RobotsBlockedError(src.url, "example.com")
            )
            self._crawl(company.id, src.id, db)

        assert src.consecutive_failures == 2

    def test_crawl_blocked_decrements_health_score(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        src.health_score = 80
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                RobotsBlockedError(src.url, "example.com")
            )
            self._crawl(company.id, src.id, db)

        assert src.health_score == 60

    def test_crawl_failed_stores_error_message(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="active")
        db = _make_db(company, src)

        with patch("app.api.v1.sources.EthicalScraper") as mock_cls:
            mock_cls.return_value.__enter__.return_value.scrape.side_effect = (
                MaxRetriesExceededError(src.url, 3, "timeout")
            )
            self._crawl(company.id, src.id, db)

        assert src.last_error_message is not None
        assert len(src.last_error_message) > 0

    def test_crawl_inactive_source_returns_422(self):
        company = _make_company()
        src = _make_source(company_id=company.id, status="inactive")
        db = _make_db(company, src)
        resp = self._crawl(company.id, src.id, db)
        assert resp.status_code == 422

    def test_crawl_company_not_found_returns_404(self):
        db = _make_db(None)
        resp = self._crawl(uuid.uuid4(), uuid.uuid4(), db)
        assert resp.status_code == 404

    def test_crawl_source_not_found_returns_404(self):
        company = _make_company()
        db = _make_db(company, None)
        resp = self._crawl(company.id, uuid.uuid4(), db)
        assert resp.status_code == 404


# ===========================================================================
# 8. Company/source ownership validation
# ===========================================================================

class TestOwnershipValidation:

    def test_source_from_different_company_not_accessible(self):
        """A source belonging to company B must not be accessible via company A's URL."""
        company_a = _make_company()
        company_b_id = uuid.uuid4()
        # Source belongs to company_b, but we query via company_a
        src = _make_source(company_id=company_b_id)

        # DB returns company_a on first call, then None for source lookup
        # (because the WHERE clause includes company_id = company_a.id)
        db = _make_db(company_a, None)
        resp = _client(db).get(
            f"/api/v1/companies/{company_a.id}/sources/{src.id}"
        )
        assert resp.status_code == 404

    def test_crawl_source_from_different_company_not_accessible(self):
        company_a = _make_company()
        db = _make_db(company_a, None)
        resp = _client(db).post(
            f"/api/v1/companies/{company_a.id}/sources/{uuid.uuid4()}/crawl"
        )
        assert resp.status_code == 404

    def test_update_source_from_different_company_not_accessible(self):
        company_a = _make_company()
        db = _make_db(company_a, None)
        resp = _client(db).patch(
            f"/api/v1/companies/{company_a.id}/sources/{uuid.uuid4()}",
            json={"name": "Hijack"},
        )
        assert resp.status_code == 404

    def test_deactivate_source_from_different_company_not_accessible(self):
        company_a = _make_company()
        db = _make_db(company_a, None)
        resp = _client(db).delete(
            f"/api/v1/companies/{company_a.id}/sources/{uuid.uuid4()}"
        )
        assert resp.status_code == 404
