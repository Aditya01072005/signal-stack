"""
Unit tests for Competitor Intelligence (Phase 3, Module 6).

All external dependencies are mocked:
  - No real database access.
  - No real network requests.
  - No Ollama.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.company import Company, CompanyProfile
from app.models.competitor import Competitor
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorDiscoveryResponse,
    CompetitorResponse,
    CompetitorType,
    CompetitorUpdate,
)
from app.services.ai import competitor_intelligence
from app.services.ai.competitor_intelligence import (
    CompetitorLLMError,
    ProfileNotFoundError,
    _build_company_context,
    _parse_json,
    discover_competitors,
    extract_domain,
    normalize_name,
)
from app.services.ai.llm_client import LLMResponseError, LLMUnavailableError


# ---------------------------------------------------------------------------
# Test Fixtures & Mock Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Ensure FastAPI dependency overrides are cleared after each test."""
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_company(deleted: bool = False, profile: Optional[CompanyProfile] = None) -> Company:
    c = MagicMock(spec=Company)
    c.id = uuid.uuid4()
    c.name = "MeetUniversity"
    c.website_url = "https://www.meetuniversity.com"
    c.industry = "EdTech"
    c.is_deleted = deleted
    c.profile = profile
    c.competitors = []
    return c


def _make_profile(
    business_summary="Leading student study-abroad guidance platform.",
    products=None,
    segments=None,
    value_prop="Personalized university matching",
    verified_facts=None,
) -> CompanyProfile:
    p = MagicMock(spec=CompanyProfile)
    p.id = uuid.uuid4()
    p.business_summary = business_summary
    p.products_services = products or [{"name": "University Search", "description": "Platform"}]
    p.customer_segments = segments or [{"segment": "Prospective Students", "description": "High school grads"}]
    p.positioning = {"value_proposition": value_prop} if value_prop else {}
    p.verified_facts = verified_facts or [
        {"fact": "Founded in 2013", "evidence_text": "Founded in 2013", "source_url": "https://www.meetuniversity.com"}
    ]
    p.assumptions = []
    return p


def _make_competitor(
    company_id: uuid.UUID,
    name: str = "Leap Scholar",
    website_url: Optional[str] = "https://leapscholar.com",
    competitor_type: str = "direct",
    description: str = "EdTech study abroad counseling",
    evidence_url: Optional[str] = "https://leapscholar.com/about",
    is_active: bool = True,
) -> Competitor:
    c = MagicMock(spec=Competitor)
    c.id = uuid.uuid4()
    c.company_id = company_id
    c.name = name
    c.website_url = website_url
    c.competitor_type = competitor_type
    c.strengths = [{"strength": "Strong test prep"}]
    c.weaknesses = [{"weakness": "High costs"}]
    c.notes = json.dumps({
        "description": description,
        "evidence_url": evidence_url,
        "is_active": is_active,
        "is_verified": True,
    })
    c.meta_dict = {
        "description": description,
        "evidence_url": evidence_url,
        "is_active": is_active,
        "is_verified": True,
    }
    c.description = description
    c.evidence_url = evidence_url
    c.is_active = is_active
    c.is_verified = True
    c.created_at = datetime.now(timezone.utc)
    c.updated_at = datetime.now(timezone.utc)

    def _set_meta(description=None, evidence_url=None, is_active=True, is_verified=True, extra=None):
        meta = dict(c.meta_dict)
        if description is not None:
            meta["description"] = description
        if evidence_url is not None:
            meta["evidence_url"] = evidence_url
        meta["is_active"] = is_active
        meta["is_verified"] = is_verified
        if extra:
            meta.update(extra)
        c.meta_dict = meta
        c.notes = json.dumps(meta)
        c.description = meta.get("description")
        c.evidence_url = meta.get("evidence_url")
        c.is_active = meta["is_active"]
        c.is_verified = meta["is_verified"]

    c.set_meta.side_effect = _set_meta
    return c


def _init_model_instance(obj) -> None:
    """Populate required fields on a real SQLAlchemy Competitor instance in tests."""
    if not isinstance(obj, Competitor):
        return
    if not isinstance(obj.id, uuid.UUID):
        obj.id = uuid.uuid4()
    if obj.created_at is None:
        obj.created_at = datetime.now(timezone.utc)
    if obj.updated_at is None:
        obj.updated_at = datetime.now(timezone.utc)


def _make_db(*scalar_returns, scalar_items=None) -> MagicMock:
    """Build a mock SQLAlchemy DB session."""
    db = MagicMock()
    returns = list(scalar_returns)
    call_count = [0]

    def _scalar_one_or_none():
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(returns):
            return returns[idx]
        return None

    def _scalars_all():
        if scalar_items is not None:
            return scalar_items
        return []

    db.execute.return_value.scalar_one_or_none.side_effect = _scalar_one_or_none
    db.execute.return_value.scalars.return_value.all.side_effect = _scalars_all
    db.add.side_effect = _init_model_instance
    db.refresh.side_effect = _init_model_instance
    return db


def _client(db_mock) -> TestClient:
    from app.database import get_db
    from app.main import app
    app.dependency_overrides[get_db] = lambda: db_mock
    return TestClient(app, raise_server_exceptions=False)


# ===========================================================================
# 1. Schema Validation Tests
# ===========================================================================

class TestCompetitorSchemas:

    def test_competitor_create_valid(self):
        c = CompetitorCreate(
            name="Leap Scholar",
            website_url="https://leapscholar.com",
            competitor_type=CompetitorType.DIRECT,
            description="Study abroad platform",
        )
        assert c.name == "Leap Scholar"
        assert c.website_url == "https://leapscholar.com"
        assert c.resolved_type() == "direct"

    def test_competitor_create_blank_name_raises(self):
        with pytest.raises(Exception):
            CompetitorCreate(name="   ", website_url="https://leapscholar.com")

    def test_competitor_create_normalizes_url(self):
        c = CompetitorCreate(
            name="Leverage Edu",
            website_url="leverageedu.com/",
            category=CompetitorType.DIRECT,
        )
        assert c.website_url == "https://leverageedu.com"
        assert c.resolved_type() == "direct"

    def test_competitor_create_normalizes_evidence_url(self):
        c = CompetitorCreate(name="Test Co", evidence_url="testco.com/about")
        assert c.evidence_url == "https://testco.com/about"

    def test_competitor_create_rejects_invalid_evidence_url(self):
        with pytest.raises(Exception):
            CompetitorCreate(name="Test Co", evidence_url="javascript:alert(1)")

    def test_competitor_create_category_and_type_interchangeable(self):
        c1 = CompetitorCreate(name="Alt1", category=CompetitorType.INDIRECT)
        assert c1.resolved_type() == "indirect"

        c2 = CompetitorCreate(name="Alt2", competitor_type=CompetitorType.SUBSTITUTE)
        assert c2.resolved_type() == "substitute"

    def test_competitor_update_valid(self):
        u = CompetitorUpdate(name="Updated Corp", is_active=False)
        assert u.name == "Updated Corp"
        assert u.is_active is False

    def test_competitor_response_serialization(self):
        cid = uuid.uuid4()
        comp_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        resp = CompetitorResponse(
            id=comp_id,
            company_id=cid,
            name="IDP Education",
            website_url="https://www.idp.com",
            competitor_type="direct",
            category="direct",
            description="International education services",
            evidence_url="https://www.idp.com",
            is_active=True,
            is_verified=True,
            created_at=now,
            updated_at=now,
        )
        assert resp.id == comp_id
        assert resp.name == "IDP Education"
        assert resp.is_active is True


# ===========================================================================
# 2. Competitor Service Unit Tests
# ===========================================================================

class TestCompetitorService:

    def test_normalize_name(self):
        assert normalize_name("  Leap   Scholar  ") == "leap scholar"
        assert normalize_name("IDP Education") == "idp education"
        assert normalize_name("") == ""

    def test_extract_domain(self):
        assert extract_domain("https://www.leapscholar.com/about/") == "leapscholar.com"
        assert extract_domain("http://idp.com:8080/test") == "idp.com"
        assert extract_domain("leverageedu.com") == "leverageedu.com"
        assert extract_domain(None) is None

    def test_build_company_context_success(self):
        profile = _make_profile(
            business_summary="Leading student study-abroad guidance platform.",
            products=[{"name": "University Search", "description": "Fast matching"}],
            segments=[{"segment": "Undergrads"}],
            value_prop="Fast admissions",
        )
        company = _make_company(profile=profile)
        ctx = _build_company_context(company)
        assert "MeetUniversity" in ctx
        assert "Leading student study-abroad" in ctx
        assert "University Search" in ctx
        assert "Undergrads" in ctx

    def test_build_company_context_no_profile_raises(self):
        company = _make_company(profile=None)
        with pytest.raises(ProfileNotFoundError):
            _build_company_context(company)

    def test_parse_json_markdown_fences(self):
        raw = """```json
        {
          "competitors": [
            {"name": "Leap Scholar", "competitor_type": "direct", "description": "Counseling platform"}
          ]
        }
        ```"""
        data = _parse_json(raw)
        assert "competitors" in data
        assert len(data["competitors"]) == 1

    def test_parse_json_invalid_raises_error(self):
        with pytest.raises(CompetitorLLMError):
            _parse_json("Not a valid json output.")

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_success(self, mock_gen):
        mock_gen.return_value = json.dumps({
            "competitors": [
                {
                    "name": "Leap Scholar",
                    "website_url": "https://leapscholar.com",
                    "competitor_type": "direct",
                    "description": "Direct rival offering study abroad counseling",
                    "ai_rationale": "May serve students seeking overseas university admissions",
                },
                {
                    "name": "Coursera",
                    "website_url": "https://coursera.org",
                    "competitor_type": "indirect",
                    "description": "Online degrees platform",
                    "ai_rationale": "May be an alternative for students seeking international education",
                },
                {
                    "name": "Direct University Website Applications",
                    "website_url": None,
                    "competitor_type": "substitute",
                    "description": "Self-application process by students",
                    "ai_rationale": "May substitute for assisted university applications",
                },
            ]
        })
        profile = _make_profile()
        company = _make_company(profile=profile)
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        res = discover_competitors(company, db)
        assert res.suggestions_count == 3
        assert len(res.suggestions) == 3
        assert res.suggestions[0].name == "Leap Scholar"
        assert res.suggestions[0].competitor_type == "direct"
        assert res.suggestions[1].competitor_type == "indirect"
        assert res.suggestions[2].competitor_type == "substitute"
        assert res.suggestions[0].is_already_added is False
        assert res.suggestions[0].is_verified is False
        assert res.suggestions[0].evidence_url is None

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_detects_already_added(self, mock_gen):
        mock_gen.return_value = json.dumps({
            "competitors": [
                {
                    "name": "Leap Scholar",
                    "website_url": "https://leapscholar.com",
                    "competitor_type": "direct",
                    "description": "Test description",
                    "ai_rationale": "Test AI rationale",
                }
            ]
        })
        profile = _make_profile()
        company = _make_company(profile=profile)
        existing_comp = _make_competitor(company.id, name="Leap Scholar", website_url="https://leapscholar.com")

        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [existing_comp]

        res = discover_competitors(company, db)
        assert res.suggestions_count == 1
        assert res.suggestions[0].is_already_added is True

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_llm_unavailable(self, mock_gen):
        mock_gen.side_effect = LLMUnavailableError("Ollama offline")
        profile = _make_profile()
        company = _make_company(profile=profile)
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        with pytest.raises(LLMUnavailableError):
            discover_competitors(company, db)

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_drops_unsubstantiated_items(self, mock_gen):
        mock_gen.return_value = json.dumps({
            "competitors": [
                {
                    "name": "Made Up Company",
                    "website_url": "not a valid URL",
                    "competitor_type": "unknown",
                    "description": "Generated description",
                },
                {
                    "name": "Incomplete Candidate",
                    "competitor_type": "direct",
                    "description": "Generated description",
                },
            ]
        })
        company = _make_company(profile=_make_profile())
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []

        result = discover_competitors(company, db)

        assert result.suggestions == []
        assert result.suggestions_count == 0


# ===========================================================================
# 3. Add Competitor API Endpoint Tests
# ===========================================================================

class TestAddCompetitorEndpoint:

    def test_add_competitor_success_201(self):
        company = _make_company()
        # db returns company, then existing competitors for company -> []
        db = _make_db(company, scalar_items=[])

        payload = {
            "name": "Leap Scholar",
            "website_url": "https://leapscholar.com",
            "category": "direct",
            "description": "Direct competitor in overseas education admissions",
            "evidence_url": "https://leapscholar.com/about",
        }
        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Leap Scholar"
        assert data["competitor_type"] == "direct"
        assert data["category"] == "direct"
        assert data["description"] == payload["description"]
        assert data["evidence_url"] == payload["evidence_url"]
        assert data["is_active"] is True
        assert data["is_verified"] is True
        assert db.commit.called

    def test_add_competitor_duplicate_name_409(self):
        company = _make_company()
        existing = _make_competitor(company.id, name="Leap Scholar")
        db = _make_db(company, scalar_items=[existing])

        payload = {
            "name": "leap scholar",  # case-insensitive duplicate
            "category": "direct",
        }
        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors", json=payload)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_add_competitor_duplicate_website_409(self):
        company = _make_company()
        existing = _make_competitor(company.id, name="Leap Scholar Inc", website_url="https://leapscholar.com")
        db = _make_db(company, scalar_items=[existing])

        payload = {
            "name": "Different Name",
            "website_url": "http://www.leapscholar.com/path",  # same canonical domain
            "category": "direct",
        }
        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors", json=payload)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_add_competitor_company_not_found_404(self):
        db = _make_db(None)
        payload = {"name": "Leap Scholar", "category": "direct"}
        resp = _client(db).post(f"/api/v1/companies/{uuid.uuid4()}/competitors", json=payload)
        assert resp.status_code == 404

    def test_add_competitor_blank_name_422(self):
        company = _make_company()
        db = _make_db(company)
        payload = {"name": "   ", "category": "direct"}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors", json=payload)
        assert resp.status_code == 422

    def test_add_competitor_without_evidence_is_unverified(self):
        company = _make_company()
        db = _make_db(company, scalar_items=[])

        resp = _client(db).post(
            f"/api/v1/companies/{company.id}/competitors",
            json={"name": "Leap Scholar", "category": "direct"},
        )
        assert resp.status_code == 201
        assert resp.json()["is_verified"] is False


# ===========================================================================
# 4. List Competitors API Endpoint Tests
# ===========================================================================

class TestListCompetitorsEndpoint:

    def test_list_competitors_success_200(self):
        company = _make_company()
        c1 = _make_competitor(company.id, name="Leap Scholar", competitor_type="direct")
        c2 = _make_competitor(company.id, name="Coursera", competitor_type="indirect")
        db = _make_db(company, scalar_items=[c1, c2])

        resp = _client(db).get(f"/api/v1/companies/{company.id}/competitors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Leap Scholar"
        assert data[1]["name"] == "Coursera"

    def test_list_competitors_filter_category(self):
        company = _make_company()
        c1 = _make_competitor(company.id, name="Leap Scholar", competitor_type="direct")
        db = _make_db(company, scalar_items=[c1])

        resp = _client(db).get(f"/api/v1/companies/{company.id}/competitors?category=direct")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["competitor_type"] == "direct"

    def test_list_competitors_filter_include_inactive(self):
        company = _make_company()
        active = _make_competitor(company.id, name="Active Corp", is_active=True)
        inactive = _make_competitor(company.id, name="Inactive Corp", is_active=False)

        # By default, inactive is excluded
        db = _make_db(company, scalar_items=[active, inactive])
        resp = _client(db).get(f"/api/v1/companies/{company.id}/competitors")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # With include_inactive=True, both are returned
        db2 = _make_db(company, scalar_items=[active, inactive])
        resp2 = _client(db2).get(f"/api/v1/companies/{company.id}/competitors?include_inactive=true")
        assert resp2.status_code == 200
        assert len(resp2.json()) == 2


# ===========================================================================
# 5. Get and Update Competitor API Tests
# ===========================================================================

class TestGetAndUpdateCompetitorEndpoint:

    def test_get_competitor_success_200(self):
        company = _make_company()
        comp = _make_competitor(company.id, name="Leap Scholar")
        db = _make_db(company, comp)

        resp = _client(db).get(f"/api/v1/companies/{company.id}/competitors/{comp.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(comp.id)
        assert data["name"] == "Leap Scholar"

    def test_get_competitor_not_found_404(self):
        company = _make_company()
        db = _make_db(company, None)

        resp = _client(db).get(f"/api/v1/companies/{company.id}/competitors/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_update_competitor_success_200(self):
        company = _make_company()
        comp = _make_competitor(company.id, name="Leap Scholar", competitor_type="direct")
        # db returns company, competitor, then other competitors for company -> []
        db = _make_db(company, comp, scalar_items=[])

        payload = {
            "name": "Leap Scholar Global",
            "category": "direct",
            "description": "Expanded study abroad services",
        }
        resp = _client(db).patch(f"/api/v1/companies/{company.id}/competitors/{comp.id}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Leap Scholar Global"
        assert db.commit.called

    def test_update_competitor_duplicate_name_409(self):
        company = _make_company()
        comp1 = _make_competitor(company.id, name="Leap Scholar")
        comp2 = _make_competitor(company.id, name="Leverage Edu")

        # scalar_returns: company, comp1; scalars_all: [comp2]
        db = _make_db(company, comp1, scalar_items=[comp2])

        payload = {"name": "Leverage Edu"}
        resp = _client(db).patch(f"/api/v1/companies/{company.id}/competitors/{comp1.id}", json=payload)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()


# ===========================================================================
# 6. Deactivate Competitor Endpoint Tests
# ===========================================================================

class TestDeactivateCompetitorEndpoint:

    def test_deactivate_competitor_delete_success(self):
        company = _make_company()
        comp = _make_competitor(company.id, name="Old Competitor", is_active=True)
        db = _make_db(company, comp)

        resp = _client(db).delete(f"/api/v1/companies/{company.id}/competitors/{comp.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
        assert db.commit.called

    def test_deactivate_competitor_post_success(self):
        company = _make_company()
        comp = _make_competitor(company.id, name="Old Competitor", is_active=True)
        db = _make_db(company, comp)

        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors/{comp.id}/deactivate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
        assert db.commit.called

    def test_deactivate_competitor_not_found_404(self):
        company = _make_company()
        db = _make_db(company, None)

        resp = _client(db).delete(f"/api/v1/companies/{company.id}/competitors/{uuid.uuid4()}")
        assert resp.status_code == 404


# ===========================================================================
# 7. AI Discover Competitors Endpoint Tests
# ===========================================================================

class TestDiscoverCompetitorsEndpoint:

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_success_200(self, mock_gen):
        mock_gen.return_value = json.dumps({
            "competitors": [
                {
                    "name": "Leap Scholar",
                    "website_url": "https://leapscholar.com",
                    "competitor_type": "direct",
                    "description": "Competitor platform",
                    "ai_rationale": "May compete in student recruitment",
                }
            ]
        })
        profile = _make_profile()
        company = _make_company(profile=profile)
        db = _make_db(company, scalar_items=[])

        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions_count"] == 1
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["name"] == "Leap Scholar"
        assert data["suggestions"][0]["category"] == "direct"
        assert data["suggestions"][0]["is_verified"] is False
        assert data["suggestions"][0]["evidence_url"] is None
        # Assert AI suggestions were NOT saved to DB
        assert not db.commit.called

    def test_discover_competitors_missing_profile_422(self):
        company = _make_company(profile=None)
        db = _make_db(company)

        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors/discover")
        assert resp.status_code == 422
        assert "profile not found" in resp.json()["detail"].lower()

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_llm_unavailable_503(self, mock_gen):
        mock_gen.side_effect = LLMUnavailableError("Ollama connection refused")
        profile = _make_profile()
        company = _make_company(profile=profile)
        db = _make_db(company, scalar_items=[])

        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors/discover")
        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()

    @patch("app.services.ai.competitor_intelligence.llm_client.generate")
    def test_discover_competitors_llm_invalid_output_422(self, mock_gen):
        mock_gen.return_value = "Non-JSON response from LLM"
        profile = _make_profile()
        company = _make_company(profile=profile)
        db = _make_db(company, scalar_items=[])

        resp = _client(db).post(f"/api/v1/companies/{company.id}/competitors/discover")
        assert resp.status_code == 422
        assert "failed to generate competitor suggestions" in resp.json()["detail"].lower()
