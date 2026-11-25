import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.brief import ActionItem, Brief, BriefSection
from app.models.company import Company
from app.models.signal import Signal
from app.models.source import Source
from app.services.ai.brief_generator import (
    BRIEF_SECTIONS,
    BriefGenerationError,
    generate_company_brief,
)


def _company():
    company = MagicMock(spec=Company)
    company.id = uuid.uuid4()
    company.name = "Example Company"
    company.is_deleted = False
    return company


def _signal(company_id, category, classification="neutral", rank=5.0):
    source = MagicMock(spec=Source)
    source.name = f"{category} source"
    source.category = category

    signal = MagicMock(spec=Signal)
    signal.id = uuid.uuid4()
    signal.company_id = company_id
    signal.source_id = uuid.uuid4()
    signal.title = f"Source fact from {category}"
    signal.content_snippet = (
        f"Example Company {category} evidence describes a specific verified event."
    )
    signal.verbatim_quote = signal.content_snippet
    signal.source_url = f"https://example.com/{category.lower()}"
    signal.is_verified = True
    signal.published_at = None
    signal.ai_interpretation = f"Stored analysis for {category}."
    signal.opportunity_threat = classification
    signal.business_area = "product"
    signal.business_impact_score = 8.0
    signal.urgency_score = 7.0
    signal.credibility_score = 9.0
    signal.relevance_score = 8.0
    signal.composite_rank = rank
    signal.discovered_at = datetime.now(timezone.utc)
    signal.source = source
    return signal


def _result(*, scalar=None, values=None, count=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = values or []
    result.scalar.return_value = count
    return result


def _brief_db(company, signals):
    db = MagicMock()
    db.execute.side_effect = [
        _result(scalar=company),
        _result(values=signals),
    ]
    return db


def _llm_response(signals):
    signal = signals[0]
    signal_id = str(signal.id)
    quote = signal.verbatim_quote
    return json.dumps(
        {
            "executive_summary": (
                "The stored evidence may indicate a relevant company development."
            ),
            "summary_evidence": [{"signal_id": signal_id, "quote": quote}],
            "assumptions": [
                {
                    "text": "The development may affect upcoming planning.",
                    "confidence": "low",
                    "signal_id": signal_id,
                    "evidence_quote": quote,
                }
            ],
            "interpretations": [
                {
                    "text": "This could warrant review by the product team.",
                    "signal_id": signal_id,
                    "evidence_quote": quote,
                }
            ],
            "actions": [
                {
                    "text": "Review the cited development in the next planning meeting.",
                    "priority": "medium",
                    "signal_id": signal_id,
                    "evidence_quote": quote,
                }
            ],
            "watch_items": [
                {
                    "text": "Monitor for further updates on the cited development.",
                    "signal_id": signal_id,
                    "evidence_quote": quote,
                }
            ],
        }
    )


def test_brief_generation_saves_exact_sections_actions_and_evidence():
    company = _company()
    signals = [
        _signal(company.id, "Customers", rank=10.0),
        _signal(company.id, "Competitors", "opportunity", rank=9.0),
        _signal(company.id, "Market", "opportunity", rank=8.0),
        _signal(company.id, "Internal", "threat", rank=7.0),
        _signal(company.id, "Customers", "opportunity", rank=6.0),
        _signal(company.id, "Market", rank=5.0),
    ]
    db = _brief_db(company, signals)
    briefing_date = datetime.now(timezone.utc).date()

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=_llm_response(signals),
    ) as generate:
        brief = generate_company_brief(
            company.id,
            db,
            briefing_date=briefing_date,
        )

    generate.assert_called_once()
    assert brief.briefing_date == briefing_date
    assert brief.delivery_status == "ready"
    assert [section.section_title for section in brief.sections] == [
        title for _, title in BRIEF_SECTIONS
    ]
    assert len(brief.sections) == 10
    assert all(section.brief_id == brief.id for section in brief.sections)
    assert len(brief.action_items) == 1
    action = brief.action_items[0]
    assert isinstance(action, ActionItem)
    assert action.brief_id == brief.id
    assert action.suggested_owner is None

    by_key = {section.section_key: section for section in brief.sections}
    assert "AI interpretation" in by_key["executive_summary"].content
    assert "top five signals" in by_key["executive_summary"].content
    assert "User-provided/internal-source information" in (
        by_key["internal_business_intelligence"].content
    )
    assert "3 supported opportunity signal(s)" not in by_key["opportunities"].content
    assert by_key["opportunities"].content.count(
        "Signal/evidence reference:"
    ) == 3
    assert by_key["executive_summary"].content.count(
        "Signal/evidence reference:"
    ) == 5
    assert "https://example.com" in by_key["source_appendix"].content
    assert all(
        signal_id in by_key["source_appendix"].referenced_signal_ids
        for signal_id in [str(signal.id) for signal in signals]
    )
    db.commit.assert_called_once()


def test_brief_generation_with_no_eligible_signals_creates_truthful_empty_brief():
    company = _company()
    db = _brief_db(company, [])

    with patch("app.services.ai.brief_generator.llm_client.generate") as generate:
        brief = generate_company_brief(company.id, db)

    generate.assert_not_called()
    assert len(brief.sections) == 10
    assert not brief.action_items
    assert "No verified, analyzed company signals" in brief.executive_summary
    assert all(not section.referenced_signal_ids for section in brief.sections)
    db.commit.assert_called_once()


def test_brief_generation_falls_back_when_summary_evidence_is_invalid():
    company = _company()
    signal = _signal(company.id, "Market")
    response = json.loads(_llm_response([signal]))
    response["summary_evidence"][0]["quote"] = "Invented evidence not in source."
    db = _brief_db(company, [signal])

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=json.dumps(response),
    ):
        brief = generate_company_brief(company.id, db)

    assert len(brief.sections) == 10
    assert not brief.action_items
    assert "Invented evidence" not in brief.executive_summary
    assert signal.verbatim_quote in brief.sections[-1].content
    assert str(signal.id) in brief.sections[-1].referenced_signal_ids
    assert "deterministic fallback" in brief.limitations_and_blind_spots
    db.commit.assert_called_once()


def test_brief_generation_fallback_omits_unsupported_actions():
    company = _company()
    signal = _signal(company.id, "Market")
    response = json.loads(_llm_response([signal]))
    response["actions"][0]["evidence_quote"] = "Unsupported recommendation basis."
    db = _brief_db(company, [signal])

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=json.dumps(response),
    ):
        brief = generate_company_brief(company.id, db)

    assert len(brief.sections) == 10
    assert not brief.action_items
    assert "Review the cited development" not in brief.sections[7].content
    assert signal.verbatim_quote in brief.sections[-1].content
    db.commit.assert_called_once()


def test_brief_generation_ignores_unverified_and_out_of_window_signals():
    company = _company()
    unverified = _signal(company.id, "Market")
    unverified.is_verified = False
    old_signal = _signal(company.id, "Customers")
    old_signal.discovered_at = datetime.now(timezone.utc) - timedelta(days=9)
    db = _brief_db(company, [unverified, old_signal])

    with patch("app.services.ai.brief_generator.llm_client.generate") as generate:
        brief = generate_company_brief(company.id, db)

    generate.assert_not_called()
    assert len(brief.sections) == 10
    db.commit.assert_called_once()


def test_brief_generation_endpoint_returns_saved_brief():
    company = _company()
    signals = [_signal(company.id, "Customers")]
    db = _brief_db(company, signals)
    app.dependency_overrides[get_db] = lambda: db

    try:
        with TestClient(app) as client:
            with patch(
                "app.services.ai.brief_generator.llm_client.generate",
                return_value=_llm_response(signals),
            ):
                response = client.post(
                    f"/api/v1/companies/{company.id}/briefs/generate"
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    assert len(response.json()["sections"]) == 10
    assert response.json()["sections"][0]["section_title"] == "Executive Summary"


def test_current_and_historical_brief_endpoints_retrieve_saved_brief():
    company = _company()
    brief = Brief(
        id=uuid.uuid4(),
        company_id=company.id,
        title="Monday Morning Executive Brief",
        briefing_date=datetime.now(timezone.utc).date(),
        executive_summary="Evidence-backed summary.",
        limitations_and_blind_spots="No unsupported items included.",
        delivery_status="ready",
        generated_at=datetime.now(timezone.utc),
        sections=[
            BriefSection(
                id=uuid.uuid4(),
                brief_id=uuid.uuid4(),
                section_key=key,
                section_title=title,
                content="Stored section content.",
                referenced_signal_ids=[],
            )
            for key, title in BRIEF_SECTIONS
        ],
        action_items=[],
    )
    current_db = MagicMock()
    current_db.execute.side_effect = [
        _result(scalar=company.id),
        _result(scalar=brief),
    ]
    history_db = MagicMock()
    history_db.execute.side_effect = [
        _result(scalar=company.id),
        _result(count=1),
        _result(values=[brief]),
    ]
    detail_db = MagicMock()
    detail_db.execute.side_effect = [
        _result(scalar=company.id),
        _result(scalar=brief),
    ]
    app.dependency_overrides[get_db] = lambda: current_db

    try:
        with TestClient(app) as client:
            current_response = client.get(
                f"/api/v1/companies/{company.id}/briefs/current"
            )
            app.dependency_overrides[get_db] = lambda: history_db
            history_response = client.get(
                f"/api/v1/companies/{company.id}/briefs"
            )
            app.dependency_overrides[get_db] = lambda: detail_db
            detail_response = client.get(
                f"/api/v1/companies/{company.id}/briefs/{brief.id}"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert current_response.status_code == 200
    assert len(current_response.json()["sections"]) == 10
    assert history_response.status_code == 200
    assert history_response.json()["total"] == 1
    assert history_response.json()["items"][0]["id"] == str(brief.id)
    assert detail_response.status_code == 200
    assert len(detail_response.json()["sections"]) == 10


def test_brief_generation_validates_smart_quotes_and_typographic_replacements():
    """Regression test: source evidence has smart quotes; LLM response has ASCII quotes."""
    company = _company()
    signal = _signal(company.id, "Market")
    signal.verbatim_quote = (
        "Changes to US rules risk limiting international students\u2019 access to "
        "work-based learning \u2014 creating Brazil\u2019s bilingual boom."
    )
    signal.content_snippet = signal.verbatim_quote
    db = _brief_db(company, [signal])
    signal_id = str(signal.id)

    # LLM quotes with ASCII apostrophe ' and hyphen -
    quote = "students' access to work-based learning - creating Brazil's bilingual boom"
    response = {
        "executive_summary": "The policy change may affect international student mobility.",
        "summary_evidence": [{"signal_id": signal_id, "quote": quote}],
        "assumptions": [],
        "interpretations": [
            {
                "text": "This could affect enrollment numbers.",
                "signal_id": signal_id,
                "evidence_quote": quote,
            }
        ],
        "actions": [
            {
                "text": "Review partnership options in Brazil.",
                "priority": "medium",
                "signal_id": signal_id,
                "evidence_quote": quote,
            }
        ],
        "watch_items": [],
    }

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=json.dumps(response),
    ):
        brief = generate_company_brief(company.id, db)

    assert brief.delivery_status == "ready"
    assert len(brief.sections) == 10
    db.commit.assert_called_once()


def test_brief_generation_handles_enclosing_quotes_and_trailing_punctuation():
    """Regression test: LLM wraps quotes in double-quotes and adds trailing period."""
    company = _company()
    signal = _signal(company.id, "Market")
    signal.verbatim_quote = "Enrolments in the US fell 17.7% in 2025/26."
    signal.content_snippet = signal.verbatim_quote
    db = _brief_db(company, [signal])
    signal_id = str(signal.id)

    # LLM wraps in quotes and includes trailing period
    quote = '"Enrolments in the US fell 17.7% in 2025/26."'
    response = {
        "executive_summary": "US enrolments showed a notable shift.",
        "summary_evidence": [{"signal_id": signal_id, "quote": quote}],
        "assumptions": [],
        "interpretations": [],
        "actions": [],
        "watch_items": [
            {
                "text": "Monitor official census numbers.",
                "signal_id": signal_id,
                "evidence_quote": quote,
            }
        ],
    }

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=json.dumps(response),
    ):
        brief = generate_company_brief(company.id, db)

    assert brief.delivery_status == "ready"
    assert len(brief.sections) == 10
    db.commit.assert_called_once()


def test_brief_generation_recovers_missing_trailing_root_brace_when_structurally_valid():
    """Regression test: valid JSON payload with only the trailing root brace omitted."""
    company = _company()
    signal = _signal(company.id, "Market")
    db = _brief_db(company, [signal])
    valid_json = _llm_response([signal])
    # Omit the final closing brace '}'
    truncated_json = valid_json.rstrip()
    if truncated_json.endswith("}"):
        truncated_json = truncated_json[:-1]

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=truncated_json,
    ):
        brief = generate_company_brief(company.id, db)

    assert brief.delivery_status == "ready"
    assert len(brief.sections) == 10
    db.commit.assert_called_once()


def test_brief_generation_falls_back_on_truly_incomplete_or_invalid_json():
    """Invalid LLM JSON uses only stored evidence and creates no actions."""
    company = _company()
    signal = _signal(company.id, "Market")
    db = _brief_db(company, [signal])
    # Cut off in the middle of a string/key
    bad_json = '{"executive_summary": "Incomplete synthesis that cut off mid'

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=bad_json,
    ):
        brief = generate_company_brief(company.id, db)

    assert len(brief.sections) == 10
    assert not brief.action_items
    assert signal.verbatim_quote in brief.sections[-1].content
    db.commit.assert_called_once()


def test_brief_generation_excludes_ai_interpretation_from_llm_payload():
    """Regression test: stored_ai_interpretation is not passed in the LLM signals_json payload."""
    company = _company()
    signal = _signal(company.id, "Market")
    signal.ai_interpretation = "Sensitive internal AI interpretation from earlier radar analysis."
    db = _brief_db(company, [signal])

    with patch(
        "app.services.ai.brief_generator.llm_client.generate",
        return_value=_llm_response([signal]),
    ) as mock_generate:
        generate_company_brief(company.id, db)

    mock_generate.assert_called_once()
    prompt_text = mock_generate.call_args[0][0]
    # The prompt payload must NOT contain stored_ai_interpretation
    assert "stored_ai_interpretation" not in prompt_text
    assert "Sensitive internal AI interpretation" not in prompt_text
