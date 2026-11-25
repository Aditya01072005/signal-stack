"""
Unit tests for the Company Research Engine.

All external dependencies are mocked:
  - No real Ollama server required.
  - No real network requests.
  - No database access.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.ai import llm_client
from app.services.ai.llm_client import LLMResponseError, LLMUnavailableError, generate
from app.services.ai.researcher import (
    ResearchResult,
    _ensure_list,
    _normalise,
    _parse_llm_json,
    _scrape_website,
    _snapshot_profile,
    _validate_facts,
    research_company,
)
from app.services.crawler.scraper import (
    RobotsBlockedError,
    RobotsUnavailableError,
    SSRFBlockedError,
    ScrapeResult,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SCRAPED_TEXT = (
    "Example Corp builds CRM software for small businesses. "
    "Founded in 2015 by Jane Smith. "
    "Over 1000 customers worldwide. "
    "Affordable pricing with no setup fee."
)


def _make_scrape(text: str = _SCRAPED_TEXT, url: str = "https://example.com") -> ScrapeResult:
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


def _make_company(name: str = "Example Corp", url: str = "https://example.com") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = name
    c.website_url = url
    c.profile = None
    return c


def _make_db() -> MagicMock:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    return db


def _valid_llm_json(source_url: str = "https://example.com") -> dict:
    return {
        "business_summary": "Example Corp builds CRM software for small businesses.",
        "products_services": [{"name": "CRM Pro", "description": "Customer management"}],
        "customer_segments": [{"segment": "SMBs", "description": "Small businesses"}],
        "positioning": {
            "value_proposition": "Affordable CRM",
            "differentiators": ["No setup fee"],
        },
        "verified_facts": [
            {
                "fact": "Founded in 2015",
                "evidence_text": "Founded in 2015 by Jane Smith.",
                "source_url": source_url,
            }
        ],
        "assumptions": [{"assumption": "Targets US market", "confidence": "medium"}],
    }


# ===========================================================================
# 1. LLM client
# ===========================================================================

class TestLLMClientGenerate:

    def test_success_returns_response_text(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Hello"}
        with patch("app.services.ai.llm_client.httpx.Client") as cls:
            cls.return_value.__enter__.return_value.post.return_value = mock_resp
            assert generate("prompt") == "Hello"

    def test_missing_response_key_returns_empty_string(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch("app.services.ai.llm_client.httpx.Client") as cls:
            cls.return_value.__enter__.return_value.post.return_value = mock_resp
            assert generate("prompt") == ""

    def test_network_error_retries_then_raises(self):
        with patch("app.services.ai.llm_client.httpx.Client") as cls, \
             patch("app.services.ai.llm_client.time.sleep"):
            cls.return_value.__enter__.return_value.post.side_effect = httpx.ConnectError("x")
            with pytest.raises(LLMUnavailableError):
                generate("prompt")

    def test_5xx_retries_then_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "down"
        with patch("app.services.ai.llm_client.httpx.Client") as cls, \
             patch("app.services.ai.llm_client.time.sleep"):
            cls.return_value.__enter__.return_value.post.return_value = mock_resp
            with pytest.raises(LLMUnavailableError):
                generate("prompt")

    def test_4xx_raises_immediately_no_retry(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad"
        with patch("app.services.ai.llm_client.httpx.Client") as cls:
            post = cls.return_value.__enter__.return_value.post
            post.return_value = mock_resp
            with pytest.raises(LLMResponseError) as exc_info:
                generate("prompt")
        assert exc_info.value.status_code == 400
        assert post.call_count == 1

    def test_custom_model_and_base_url(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok"}
        with patch("app.services.ai.llm_client.httpx.Client") as cls:
            post = cls.return_value.__enter__.return_value.post
            post.return_value = mock_resp
            generate("p", model="mistral", base_url="http://custom:11434")
        assert "custom:11434" in post.call_args[0][0]
        assert post.call_args[1]["json"]["model"] == "mistral"


# ===========================================================================
# 2. JSON parsing helpers
# ===========================================================================

class TestParseLLMJson:

    def test_plain_json(self):
        d = {"business_summary": "hello"}
        assert _parse_llm_json(json.dumps(d))["business_summary"] == "hello"

    def test_markdown_fence(self):
        d = {"business_summary": "hello"}
        raw = f"```json\n{json.dumps(d)}\n```"
        assert _parse_llm_json(raw)["business_summary"] == "hello"

    def test_preamble_text(self):
        d = {"business_summary": "hello"}
        raw = f"Here you go:\n{json.dumps(d)}"
        assert "business_summary" in _parse_llm_json(raw)

    def test_invalid_returns_empty(self):
        assert _parse_llm_json("not json") == {}

    def test_empty_returns_empty(self):
        assert _parse_llm_json("") == {}


class TestEnsureList:

    def test_list_passthrough(self):
        assert _ensure_list([1, 2]) == [1, 2]

    def test_none_gives_empty(self):
        assert _ensure_list(None) == []

    def test_dict_gives_empty(self):
        assert _ensure_list({"a": 1}) == []

    def test_string_gives_empty(self):
        assert _ensure_list("oops") == []


# ===========================================================================
# 3. Evidence validation
# ===========================================================================

class TestValidateFacts:

    def test_supported_fact_accepted(self):
        facts = [{"fact": "Founded 2015", "evidence_text": "Founded in 2015 by Jane Smith.", "source_url": "https://example.com"}]
        accepted, excluded = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com")
        assert len(accepted) == 1
        assert excluded == 0
        assert accepted[0]["evidence_text"] == "Founded in 2015 by Jane Smith."
        assert accepted[0]["source_url"] == "https://example.com"

    def test_unsupported_fact_excluded(self):
        facts = [{"fact": "IPO in 2020", "evidence_text": "The company went public in 2020.", "source_url": "https://example.com"}]
        accepted, excluded = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com")
        assert len(accepted) == 0
        assert excluded == 1

    def test_empty_evidence_excluded(self):
        facts = [{"fact": "Some fact", "evidence_text": "", "source_url": "https://example.com"}]
        accepted, excluded = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com")
        assert excluded == 1

    def test_short_evidence_excluded(self):
        facts = [{"fact": "Some fact", "evidence_text": "hi", "source_url": "https://example.com"}]
        accepted, excluded = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com")
        assert excluded == 1

    def test_missing_evidence_text_key_excluded(self):
        facts = [{"fact": "Some fact", "source_url": "https://example.com"}]
        accepted, excluded = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com")
        assert excluded == 1

    def test_source_url_falls_back_to_scraped_url(self):
        facts = [{"fact": "Founded 2015", "evidence_text": "Founded in 2015 by Jane Smith."}]
        accepted, _ = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com/fallback")
        assert accepted[0]["source_url"] == "https://example.com/fallback"

    def test_whitespace_normalisation_allows_match(self):
        content = "Founded  in   2015  by  Jane   Smith."
        facts = [{"fact": "Founded 2015", "evidence_text": "Founded in 2015 by Jane Smith.", "source_url": "https://x.com"}]
        accepted, excluded = _validate_facts(facts, content, "https://x.com")
        assert len(accepted) == 1
        assert excluded == 0

    def test_mixed_supported_and_unsupported(self):
        facts = [
            {"fact": "Founded 2015", "evidence_text": "Founded in 2015 by Jane Smith.", "source_url": "https://example.com"},
            {"fact": "Listed on NYSE", "evidence_text": "Traded on the New York Stock Exchange.", "source_url": "https://example.com"},
        ]
        accepted, excluded = _validate_facts(facts, _SCRAPED_TEXT, "https://example.com")
        assert len(accepted) == 1
        assert excluded == 1

    def test_non_dict_item_excluded(self):
        _, excluded = _validate_facts(["not a dict"], _SCRAPED_TEXT, "https://example.com")
        assert excluded == 1


# ===========================================================================
# 4. Profile snapshot
# ===========================================================================

class TestSnapshotProfile:

    def test_none_profile_returns_none(self):
        assert _snapshot_profile(None) is None

    def test_existing_profile_captured(self):
        profile = MagicMock()
        profile.business_summary = "Summary"
        profile.products_services = [{"name": "P"}]
        profile.customer_segments = None
        profile.positioning = {}
        profile.verified_facts = [{"fact": "f", "evidence_text": "e", "source_url": "u"}]
        profile.assumptions = []
        snap = _snapshot_profile(profile)
        assert snap["business_summary"] == "Summary"
        assert snap["verified_facts"] == [{"fact": "f", "evidence_text": "e", "source_url": "u"}]

    def test_snapshot_is_json_serialisable(self):
        profile = MagicMock()
        profile.business_summary = "Summary"
        profile.products_services = [{"name": "P"}]
        profile.customer_segments = []
        profile.positioning = {"value_proposition": "VP"}
        profile.verified_facts = []
        profile.assumptions = []
        snap = _snapshot_profile(profile)
        json.dumps(snap)  # must not raise


# ===========================================================================
# 5. _scrape_website helper
# ===========================================================================

class TestScrapeWebsiteHelper:

    def test_success_returns_scrape_result(self):
        expected = _make_scrape()
        with patch("app.services.ai.researcher.EthicalScraper") as cls:
            cls.return_value.__enter__.return_value.scrape.return_value = expected
            result, err, status = _scrape_website("https://example.com")
        assert result is expected
        assert err is None
        assert status == "success"

    def test_ssrf_blocked_returns_scrape_blocked(self):
        with patch("app.services.ai.researcher.EthicalScraper") as cls:
            cls.return_value.__enter__.return_value.scrape.side_effect = (
                SSRFBlockedError("https://192.168.1.1", "private IP")
            )
            result, err, status = _scrape_website("https://192.168.1.1")
        assert result is None
        assert status == "scrape_blocked"
        assert err is not None

    def test_robots_blocked_returns_scrape_blocked(self):
        with patch("app.services.ai.researcher.EthicalScraper") as cls:
            cls.return_value.__enter__.return_value.scrape.side_effect = (
                RobotsBlockedError("https://example.com/page", "example.com")
            )
            result, err, status = _scrape_website("https://example.com/page")
        assert result is None
        assert status == "scrape_blocked"

    def test_robots_unavailable_returns_scrape_blocked(self):
        with patch("app.services.ai.researcher.EthicalScraper") as cls:
            cls.return_value.__enter__.return_value.scrape.side_effect = (
                RobotsUnavailableError("example.com", "timeout")
            )
            result, err, status = _scrape_website("https://example.com")
        assert result is None
        assert status == "scrape_blocked"

    def test_network_error_returns_scrape_failed(self):
        from app.services.crawler.scraper import MaxRetriesExceededError
        with patch("app.services.ai.researcher.EthicalScraper") as cls:
            cls.return_value.__enter__.return_value.scrape.side_effect = (
                MaxRetriesExceededError("https://example.com", 3, "timeout")
            )
            result, err, status = _scrape_website("https://example.com")
        assert result is None
        assert status == "scrape_failed"


# ===========================================================================
# 6. research_company pipeline — profile preservation on failure
# ===========================================================================

class TestResearchCompanyPipeline:

    # --- helpers ---

    def _run(self, scrape_return, llm_return="", company=None, db=None):
        c = company or _make_company()
        d = db or _make_db()
        with patch("app.services.ai.researcher._scrape_website", return_value=scrape_return), \
             patch("app.services.ai.researcher.llm_client.generate", return_value=llm_return):
            return research_company(c, d), c, d

    def _scrape_ok(self):
        return _make_scrape(), None, "success"

    def _scrape_blocked(self):
        return None, "robots.txt blocked", "scrape_blocked"

    def _scrape_failed(self):
        return None, "connection refused", "scrape_failed"

    # --- Req 1: successful research creates a profile ---

    def _profile_adds(self, db) -> list:
        """Return only CompanyProfile objects passed to db.add()."""
        from app.models.company import CompanyProfile
        return [c.args[0] for c in db.add.call_args_list
                if isinstance(c.args[0], CompanyProfile)]

    def test_success_creates_profile_when_none_exists(self):
        company = _make_company()
        company.profile = None
        db = _make_db()
        llm_raw = json.dumps(_valid_llm_json())
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate", return_value=llm_raw):
            result = research_company(company, db)
        assert result.scrape_status == "success"
        assert len(self._profile_adds(db)) == 1
        db.commit.assert_called()

    # --- Req 2: successful research updates an existing profile ---

    def test_success_updates_existing_profile_not_duplicated(self):
        company = _make_company()
        existing = MagicMock()
        company.profile = existing
        db = _make_db()
        llm_raw = json.dumps(_valid_llm_json())
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate", return_value=llm_raw):
            result = research_company(company, db)
        assert result.scrape_status == "success"
        assert len(self._profile_adds(db)) == 0   # no new CompanyProfile row inserted
        assert existing.business_summary is not None

    # --- Req 3: scraping failure preserves every existing profile field ---

    def test_scrape_failure_does_not_touch_existing_profile(self):
        company = _make_company()
        existing = MagicMock()
        existing.business_summary = "Old summary"
        existing.verified_facts = [{"fact": "old", "evidence_text": "old", "source_url": "u"}]
        company.profile = existing
        db = _make_db()
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_failed()):
            result = research_company(company, db)
        assert result.scrape_status == "scrape_failed"
        # profile fields must be completely untouched
        assert existing.business_summary == "Old summary"
        assert existing.verified_facts == [{"fact": "old", "evidence_text": "old", "source_url": "u"}]
        assert len(self._profile_adds(db)) == 0

    def test_scrape_blocked_does_not_touch_existing_profile(self):
        company = _make_company()
        existing = MagicMock()
        existing.business_summary = "Keep me"
        company.profile = existing
        db = _make_db()
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_blocked()):
            result = research_company(company, db)
        assert result.scrape_status == "scrape_blocked"
        assert existing.business_summary == "Keep me"
        assert len(self._profile_adds(db)) == 0

    # --- Req 4: Ollama failure preserves every existing profile field ---

    def test_llm_unavailable_does_not_touch_existing_profile(self):
        company = _make_company()
        existing = MagicMock()
        existing.business_summary = "Preserved"
        company.profile = existing
        db = _make_db()
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate",
                   side_effect=LLMUnavailableError("Ollama down")):
            result = research_company(company, db)
        assert result.scrape_status == "llm_unavailable"
        assert existing.business_summary == "Preserved"
        assert len(self._profile_adds(db)) == 0

    # --- Req 5: invalid JSON preserves every existing profile field ---

    def test_invalid_json_does_not_touch_existing_profile(self):
        company = _make_company()
        existing = MagicMock()
        existing.business_summary = "Still here"
        company.profile = existing
        db = _make_db()
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate",
                   return_value="Sorry, I cannot help."):
            result = research_company(company, db)
        assert result.scrape_status == "llm_invalid_output"
        assert existing.business_summary == "Still here"
        assert len(self._profile_adds(db)) == 0

    # --- Req 6: empty page text preserves existing profile ---

    def test_empty_page_text_does_not_touch_existing_profile(self):
        company = _make_company()
        existing = MagicMock()
        existing.business_summary = "Untouched"
        company.profile = existing
        db = _make_db()
        empty_scrape = _make_scrape(text="")
        with patch("app.services.ai.researcher._scrape_website",
                   return_value=(empty_scrape, None, "success")):
            result = research_company(company, db)
        assert result.scrape_status == "scrape_failed"
        assert existing.business_summary == "Untouched"
        assert len(self._profile_adds(db)) == 0

    # --- Req 7: unsupported facts are excluded ---

    def test_unsupported_facts_excluded_from_result(self):
        llm_data = _valid_llm_json()
        llm_data["verified_facts"].append({
            "fact": "Listed on NYSE",
            "evidence_text": "Traded on the New York Stock Exchange since 2018.",
            "source_url": "https://example.com",
        })
        result, _, _ = self._run(self._scrape_ok(), json.dumps(llm_data))
        assert result.scrape_status == "success"
        assert result.facts_excluded == 1
        assert len(result.verified_facts) == 1
        assert result.verified_facts[0]["fact"] == "Founded in 2015"

    # --- Req 8: supported facts retain evidence_text and source_url ---

    def test_supported_facts_have_evidence_and_source_url(self):
        result, _, _ = self._run(self._scrape_ok(), json.dumps(_valid_llm_json()))
        assert result.scrape_status == "success"
        assert len(result.verified_facts) == 1
        fact = result.verified_facts[0]
        assert "evidence_text" in fact
        assert fact["evidence_text"] == "Founded in 2015 by Jane Smith."
        assert "source_url" in fact
        assert fact["source_url"] == "https://example.com"


# ===========================================================================
# 7. AuditLog
# ===========================================================================

class TestAuditLog:

    def _run_with_audit_capture(self, scrape_return, llm_return="", company=None):
        c = company or _make_company()
        db = _make_db()
        added_objects = []
        db.add.side_effect = added_objects.append
        with patch("app.services.ai.researcher._scrape_website", return_value=scrape_return), \
             patch("app.services.ai.researcher.llm_client.generate", return_value=llm_return):
            result = research_company(c, db)
        audit_entries = [o for o in added_objects if hasattr(o, "task_type")]
        return result, audit_entries, db

    def _scrape_ok(self):
        return _make_scrape(), None, "success"

    def _scrape_failed(self):
        return None, "connection refused", "scrape_failed"

    # --- Req 9: AuditLog records successful research ---

    def test_audit_written_on_success(self):
        result, audits, _ = self._run_with_audit_capture(
            self._scrape_ok(), json.dumps(_valid_llm_json())
        )
        assert result.scrape_status == "success"
        assert len(audits) == 1
        assert audits[0].task_type == "company_research"
        assert audits[0].status == "success"
        assert audits[0].error_message is None

    # --- Req 10: AuditLog records failed research ---

    def test_audit_written_on_scrape_failure(self):
        result, audits, _ = self._run_with_audit_capture(self._scrape_failed())
        assert result.scrape_status == "scrape_failed"
        assert len(audits) == 1
        assert audits[0].status == "error"
        assert audits[0].error_message is not None

    def test_audit_written_on_llm_failure(self):
        c = _make_company()
        db = _make_db()
        added_objects = []
        db.add.side_effect = added_objects.append
        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate",
                   side_effect=LLMUnavailableError("down")):
            result = research_company(c, db)
        audits = [o for o in added_objects if hasattr(o, "task_type")]
        assert result.scrape_status == "llm_unavailable"
        assert len(audits) == 1
        assert audits[0].status == "error"

    def test_audit_written_on_invalid_json(self):
        result, audits, _ = self._run_with_audit_capture(
            self._scrape_ok(), "not json at all"
        )
        assert result.scrape_status == "llm_invalid_output"
        assert len(audits) == 1
        assert audits[0].status == "error"

    # --- Req 11: previous profile snapshot recorded before successful update ---

    def test_previous_profile_snapshot_in_audit_details(self):
        company = _make_company()
        existing = MagicMock()
        existing.business_summary = "Old summary"
        existing.products_services = [{"name": "Old product"}]
        existing.customer_segments = []
        existing.positioning = {}
        existing.verified_facts = []
        existing.assumptions = []
        company.profile = existing

        db = _make_db()
        added_objects = []
        db.add.side_effect = added_objects.append

        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate",
                   return_value=json.dumps(_valid_llm_json())):
            result = research_company(company, db)

        assert result.scrape_status == "success"
        audits = [o for o in added_objects if hasattr(o, "task_type")]
        assert len(audits) == 1
        snap = audits[0].details.get("previous_profile_snapshot")
        assert snap is not None
        assert snap["business_summary"] == "Old summary"

    def test_no_snapshot_when_no_prior_profile(self):
        company = _make_company()
        company.profile = None
        db = _make_db()
        added_objects = []
        db.add.side_effect = added_objects.append

        with patch("app.services.ai.researcher._scrape_website", return_value=self._scrape_ok()), \
             patch("app.services.ai.researcher.llm_client.generate",
                   return_value=json.dumps(_valid_llm_json())):
            research_company(company, db)

        audits = [o for o in added_objects if hasattr(o, "task_type")]
        assert "previous_profile_snapshot" not in audits[0].details

    # --- Req 12: duration is recorded ---

    def test_duration_ms_recorded_and_positive(self):
        result, audits, _ = self._run_with_audit_capture(
            self._scrape_ok(), json.dumps(_valid_llm_json())
        )
        assert audits[0].duration_ms is not None
        assert audits[0].duration_ms >= 0

    def test_duration_ms_recorded_on_failure(self):
        result, audits, _ = self._run_with_audit_capture(self._scrape_failed())
        assert audits[0].duration_ms is not None
        assert audits[0].duration_ms >= 0

    # --- Only one audit entry per execution ---

    def test_exactly_one_audit_entry_per_run(self):
        result, audits, _ = self._run_with_audit_capture(
            self._scrape_ok(), json.dumps(_valid_llm_json())
        )
        assert len(audits) == 1

    def test_exactly_one_audit_entry_on_failure(self):
        result, audits, _ = self._run_with_audit_capture(self._scrape_failed())
        assert len(audits) == 1


# ===========================================================================
# 8. Research API endpoint
# ===========================================================================

class TestResearchEndpoint:

    def _client(self, db_mock):
        from app.main import app
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: db_mock
        return TestClient(app, raise_server_exceptions=False)

    def _db_with(self, company=None):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = company
        return db

    def _company_mock(self, deleted=False):
        from app.models.company import Company as CM
        c = MagicMock(spec=CM)
        c.id = uuid.uuid4()
        c.name = "Test Corp"
        c.website_url = "https://test.com"
        c.is_deleted = deleted
        c.profile = None
        return c

    # --- Req 13: soft-deleted companies remain inaccessible ---

    def test_404_for_unknown_company(self):
        db = self._db_with(None)
        resp = self._client(db).post(f"/api/v1/companies/{uuid.uuid4()}/research")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_200_on_success(self):
        company = self._company_mock()
        db = self._db_with(company)
        mock_result = ResearchResult(
            company_id=str(company.id),
            company_name="Test Corp",
            website_url="https://test.com",
            business_summary="Test Corp does things.",
            verified_facts=[{"fact": "f", "evidence_text": "e", "source_url": "https://test.com"}],
            assumptions=[{"assumption": "a", "confidence": "low"}],
            scrape_status="success",
        )
        with patch("app.api.v1.research.research_company", return_value=mock_result):
            resp = self._client(db).post(f"/api/v1/companies/{company.id}/research")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scrape_status"] == "success"
        assert body["business_summary"] == "Test Corp does things."
        assert len(body["verified_facts"]) == 1
        assert "evidence_text" in body["verified_facts"][0]

    def test_422_on_scrape_failure(self):
        company = self._company_mock()
        db = self._db_with(company)
        mock_result = ResearchResult(
            company_id=str(company.id),
            company_name="Test Corp",
            website_url="https://test.com",
            business_summary="",
            scrape_status="scrape_failed",
            scrape_error="connection refused",
        )
        with patch("app.api.v1.research.research_company", return_value=mock_result):
            resp = self._client(db).post(f"/api/v1/companies/{company.id}/research")
        assert resp.status_code == 422

    def test_422_on_scrape_blocked(self):
        company = self._company_mock()
        db = self._db_with(company)
        mock_result = ResearchResult(
            company_id=str(company.id),
            company_name="Test Corp",
            website_url="https://test.com",
            business_summary="",
            scrape_status="scrape_blocked",
            scrape_error="robots.txt disallows",
        )
        with patch("app.api.v1.research.research_company", return_value=mock_result):
            resp = self._client(db).post(f"/api/v1/companies/{company.id}/research")
        assert resp.status_code == 422

    def test_503_on_llm_unavailable(self):
        company = self._company_mock()
        db = self._db_with(company)
        mock_result = ResearchResult(
            company_id=str(company.id),
            company_name="Test Corp",
            website_url="https://test.com",
            business_summary="",
            scrape_status="llm_unavailable",
            scrape_error="Ollama unavailable: connection refused",
        )
        with patch("app.api.v1.research.research_company", return_value=mock_result):
            resp = self._client(db).post(f"/api/v1/companies/{company.id}/research")
        assert resp.status_code == 503

    def test_422_on_invalid_llm_output(self):
        company = self._company_mock()
        db = self._db_with(company)
        mock_result = ResearchResult(
            company_id=str(company.id),
            company_name="Test Corp",
            website_url="https://test.com",
            business_summary="",
            scrape_status="llm_invalid_output",
            scrape_error="LLM response could not be parsed as JSON.",
        )
        with patch("app.api.v1.research.research_company", return_value=mock_result):
            resp = self._client(db).post(f"/api/v1/companies/{company.id}/research")
        assert resp.status_code == 422

    def test_response_includes_facts_excluded_count(self):
        company = self._company_mock()
        db = self._db_with(company)
        mock_result = ResearchResult(
            company_id=str(company.id),
            company_name="Test Corp",
            website_url="https://test.com",
            business_summary="Does things.",
            verified_facts=[],
            facts_excluded=3,
            scrape_status="success",
        )
        with patch("app.api.v1.research.research_company", return_value=mock_result):
            resp = self._client(db).post(f"/api/v1/companies/{company.id}/research")
        assert resp.status_code == 200
        assert resp.json()["facts_excluded"] == 3
