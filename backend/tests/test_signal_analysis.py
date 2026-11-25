import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.company import Company
from app.models.signal import Signal
from app.services.ai.llm_client import LLMUnavailableError
from app.services.ai.signal_analyzer import (
    SignalAnalysisError,
    analyze_signal,
)


def _company():
    company = MagicMock(spec=Company)
    company.id = uuid.uuid4()
    company.name = "Example Company"
    company.industry = "Software"
    company.is_deleted = False
    return company


def _signal(company_id, content=None):
    signal = MagicMock(spec=Signal)
    signal.id = uuid.uuid4()
    signal.company_id = company_id
    signal.source_id = uuid.uuid4()
    signal.title = "Market updates"
    signal.content_snippet = content or (
        "Example Company launched its new platform on November 24, 2026. "
        "The platform is available to business customers."
    )
    signal.source_url = "https://example.com/news"
    signal.is_verified = True
    signal.verbatim_quote = signal.content_snippet
    signal.published_at = None
    signal.business_area = None
    signal.development_type = None
    signal.opportunity_threat = "neutral"
    signal.business_impact_score = 5.0
    signal.urgency_score = 5.0
    signal.credibility_score = 5.0
    signal.relevance_score = 5.0
    signal.composite_rank = 5.0
    signal.ai_interpretation = None
    signal.recommended_action = None
    signal.discovered_at = datetime.now(timezone.utc)
    return signal


def _analysis_payload(**overrides):
    payload = {
        "what_happened": "launched its new platform",
        "published_date": "November 24, 2026",
        "business_area": "product",
        "development_type": "product_launch",
        "opportunity_threat": "opportunity",
        "relevance_score": 6,
        "business_impact_score": 8,
        "urgency_score": 7,
        "credibility_score": 9,
        "interpretation": (
            "This launch could affect product competition in the stated market."
        ),
        "interpretation_evidence": "launched its new platform",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _db_with_peers(peers=()):
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = list(peers)
    return db


def test_analyze_signal_persists_only_grounded_analysis_and_rank_components():
    company = _company()
    signal = _signal(company.id)
    db = _db_with_peers()

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=_analysis_payload(),
    ) as generate:
        result = analyze_signal(signal, company, db)

    assert generate.call_count == 1
    assert "SOURCE EVIDENCE" in generate.call_args.args[0]
    assert signal.title == "launched its new platform"
    assert signal.published_at == datetime(
        2026, 11, 24, tzinfo=timezone.utc
    )
    assert signal.business_area == "product"
    assert signal.development_type == "product_launch"
    assert signal.opportunity_threat == "opportunity"
    assert signal.business_impact_score == 8
    assert signal.urgency_score == 7
    assert signal.credibility_score == 9
    assert signal.relevance_score == 6
    assert result.recency_score == 10
    assert result.novelty_score == 10
    assert signal.composite_rank == 8.3
    assert signal.ai_interpretation.startswith("This launch could")
    assert signal.recommended_action is None
    assert signal.content_snippet.startswith("Example Company launched")
    assert signal.verbatim_quote == signal.content_snippet
    db.commit.assert_called_once()


def test_analyze_signal_rejects_event_not_in_source_without_mutating_signal():
    company = _company()
    signal = _signal(company.id)
    original_title = signal.title
    db = _db_with_peers()

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=_analysis_payload(
            what_happened="The company acquired a competitor"
        ),
    ):
        with pytest.raises(SignalAnalysisError, match="not supported"):
            analyze_signal(signal, company, db)

    assert signal.title == original_title
    db.commit.assert_not_called()


def test_analyze_signal_omits_date_not_found_in_evidence():
    company = _company()
    signal = _signal(company.id)
    payload = json.loads(_analysis_payload())
    payload["published_date"] = "November 23, 2026"
    db = _db_with_peers()

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=json.dumps(payload),
    ):
        analyze_signal(signal, company, db)

    assert signal.published_at is None


def test_analyze_signal_rejects_invalid_scores_without_saving():
    company = _company()
    signal = _signal(company.id)
    db = _db_with_peers()

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=_analysis_payload(business_impact_score=11),
    ):
        with pytest.raises(SignalAnalysisError, match="out-of-range"):
            analyze_signal(signal, company, db)

    db.commit.assert_not_called()


def test_analyze_signal_rejects_unverified_source_evidence():
    company = _company()
    signal = _signal(company.id)
    signal.is_verified = False
    db = _db_with_peers()

    with patch("app.services.ai.signal_analyzer.llm_client.generate") as generate:
        with pytest.raises(SignalAnalysisError, match="verified"):
            analyze_signal(signal, company, db)

    generate.assert_not_called()
    db.commit.assert_not_called()


def test_analyze_endpoint_maps_unsupported_output_to_422():
    company = _company()
    signal = _signal(company.id)
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=signal)),
    ]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            with patch(
                "app.services.ai.signal_analyzer.llm_client.generate",
                return_value=_analysis_payload(
                    what_happened="Unsupported market event"
                ),
            ):
                response = client.post(
                    f"/api/v1/companies/{company.id}/signals/{signal.id}/analyze"
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 422
    assert db.commit.call_count == 0


def test_analyze_endpoint_returns_503_when_local_ollama_is_unavailable():
    company = _company()
    signal = _signal(company.id)
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=signal)),
    ]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            with patch(
                "app.services.ai.signal_analyzer.llm_client.generate",
                side_effect=LLMUnavailableError("connection refused"),
            ):
                response = client.post(
                    f"/api/v1/companies/{company.id}/signals/{signal.id}/analyze"
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert db.commit.call_count == 0


def test_ranked_signals_endpoint_returns_results():
    company = _company()
    signal = _signal(company.id)
    signal.title = "launched its new platform"
    signal.business_area = "product"
    signal.development_type = "product_launch"
    signal.opportunity_threat = "opportunity"
    signal.business_impact_score = 8.0
    signal.urgency_score = 7.0
    signal.credibility_score = 9.0
    signal.relevance_score = 6.0
    signal.composite_rank = 8.3
    signal.ai_interpretation = "This launch could affect product competition."

    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
        MagicMock(scalar=MagicMock(return_value=1)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(
            all=MagicMock(return_value=[signal])
        ))),
    ]
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/companies/{company.id}/signals/ranked"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["composite_rank"] == 8.3


def test_analyze_signal_validates_excerpts_with_typographic_apostrophes():
    """Regression test: LLM returns ASCII apostrophes for source text with smart quotes."""
    company = _company()
    # Source text uses Unicode curly apostrophe \u2019
    source_content = (
        "Changes to US rules governing CPT risk limiting international students\u2019 "
        "access to work-based learning, while creating uncertainty for universities."
    )
    signal = _signal(company.id, content=source_content)
    db = _db_with_peers()

    # LLM returns ASCII apostrophe \u0027
    payload = {
        "what_happened": (
            "Changes to US rules governing CPT risk limiting international students' "
            "access to work-based learning"
        ),
        "published_date": None,
        "business_area": "market",
        "development_type": "regulation",
        "opportunity_threat": "threat",
        "relevance_score": 8,
        "business_impact_score": 7,
        "urgency_score": 8,
        "credibility_score": 9,
        "interpretation": "This change may impact international student recruitment.",
        "interpretation_evidence": "students' access to work-based learning",
    }

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=json.dumps(payload),
    ):
        result = analyze_signal(signal, company, db)

    assert result.signal.title.startswith("Changes to US rules")
    assert result.signal.business_area == "market"
    assert result.signal.development_type == "regulation"
    db.commit.assert_called_once()


def test_analyze_signal_handles_quoted_excerpts_and_custom_categories():
    """Regression test: LLM wraps excerpts in quotation marks and returns site category."""
    company = _company()
    source_content = (
        "New international enrolments in the US fell 17.7% in 2025/26. "
        "Eight countries sent record numbers of students."
    )
    signal = _signal(company.id, content=source_content)
    db = _db_with_peers()

    payload = {
        "what_happened": '"New international enrolments in the US fell 17.7% in 2025/26."',
        "published_date": None,
        "business_area": "Investor",  # Website category not in default _BUSINESS_AREAS
        "development_type": "Policy",  # Website tag not in default _DEVELOPMENT_TYPES
        "opportunity_threat": "neutral",
        "relevance_score": 8,
        "business_impact_score": 7,
        "urgency_score": 6,
        "credibility_score": 9,
        "interpretation": "The decline in admissions may affect overall international mobility.",
        "interpretation_evidence": "Eight countries sent record numbers of students.",
    }

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=json.dumps(payload),
    ):
        result = analyze_signal(signal, company, db)

    assert "New international enrolments" in result.signal.title
    assert not result.signal.title.startswith('"')
    assert result.signal.business_area == "other"
    assert result.signal.development_type == "other"
    db.commit.assert_called_once()



# ---------------------------------------------------------------------------
# Regression tests: evidence validation on multi-headline and typographic text
# ---------------------------------------------------------------------------

def test_analyze_signal_validates_typographic_apostrophes_and_quotes():
    """Verify smart/curly apostrophes in source match ASCII apostrophes from LLM."""
    company = _company()
    # Source text uses unicode right single quotation mark (smart apostrophe \u2019)
    source_content = (
        "Changes to US rules risk limiting international students’ access to work-based learning, "
        "while creating uncertainty for universities, argues Shaun Carver."
    )
    signal = _signal(company.id, content=source_content)
    db = _db_with_peers()

    # LLM outputs standard ASCII apostrophe (\u0027)
    payload = _analysis_payload(
        what_happened="limiting international students' access to work-based learning",
        interpretation_evidence="limiting international students' access to work-based learning",
        interpretation="The policy change could impact international students' employment access.",
        published_date=None,
    )

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=payload,
    ):
        result = analyze_signal(signal, company, db)

    assert result.signal.title == "limiting international students' access to work-based learning"
    assert result.signal.ai_interpretation.startswith("The policy change could impact")
    db.commit.assert_called_once()


def test_analyze_signal_validates_excerpts_with_enclosing_quotes_or_trailing_punctuation():
    """Verify excerpts wrapped in quotes or trailing punctuation by LLM match source."""
    company = _company()
    source_content = (
        "New international enrolments in the US fell 17.7% in 2025/26, "
        "yet eight countries sent record numbers of students."
    )
    signal = _signal(company.id, content=source_content)
    db = _db_with_peers()

    # LLM wraps excerpt in quotes and adds trailing period
    payload = _analysis_payload(
        what_happened='"New international enrolments in the US fell 17.7% in 2025/26."',
        interpretation_evidence='"New international enrolments in the US fell 17.7% in 2025/26."',
        published_date=None,
    )

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=payload,
    ):
        result = analyze_signal(signal, company, db)

    assert "New international enrolments in the US fell 17.7%" in result.signal.title
    db.commit.assert_called_once()


def test_analyze_signal_safe_taxonomy_fallback_for_custom_category():
    """Verify non-standard categories (e.g. site tags like 'Investor') safely default to 'other'."""
    company = _company()
    signal = _signal(company.id)
    db = _db_with_peers()

    payload = _analysis_payload(
        business_area="Investor",
        development_type="Investor",
    )

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=payload,
    ):
        result = analyze_signal(signal, company, db)

    assert result.signal.business_area == "other"
    assert result.signal.development_type == "other"
    db.commit.assert_called_once()


def test_analyze_signal_still_strictly_rejects_hallucinated_interpretation_evidence():
    """Verify evidence validation is not weakened: hallucinated evidence is strictly rejected."""
    company = _company()
    signal = _signal(company.id)
    db = _db_with_peers()

    payload = _analysis_payload(
        what_happened="launched its new platform",
        interpretation_evidence="A completely fabricated statement not present in the source article.",
    )

    with patch(
        "app.services.ai.signal_analyzer.llm_client.generate",
        return_value=payload,
    ):
        with pytest.raises(SignalAnalysisError, match="interpretation is not supported"):
            analyze_signal(signal, company, db)

    db.commit.assert_not_called()

