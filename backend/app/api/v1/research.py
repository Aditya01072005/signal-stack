"""
Company Research API endpoint.

POST /api/v1/companies/{company_id}/research
  - Looks up the registered company (404 if not found or soft-deleted).
  - Runs the automated research pipeline (scrape + LLM extraction).
  - Writes CompanyProfile ONLY on full success.
  - Always writes one AuditLog entry.
  - Returns a structured ResearchResponse.

HTTP status mapping:
  200  — full pipeline succeeded, profile written.
  404  — company not found or soft-deleted.
  422  — scraping failed, scraping blocked, or LLM output was invalid.
  503  — Ollama could not be reached.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.schemas.research import ResearchResponse
from app.services.ai.researcher import research_company

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Research"])

# Map scrape_status values to HTTP status codes.
_STATUS_TO_HTTP: dict[str, int] = {
    "success":            status.HTTP_200_OK,
    "scrape_failed":      status.HTTP_422_UNPROCESSABLE_ENTITY,
    "scrape_blocked":     status.HTTP_422_UNPROCESSABLE_ENTITY,
    "llm_unavailable":    status.HTTP_503_SERVICE_UNAVAILABLE,
    "llm_invalid_output": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@router.post(
    "/{company_id}/research",
    summary="Run automated company research",
    description=(
        "Scrapes the company's public website, extracts structured intelligence "
        "using the local Ollama LLM, and persists the result as a CompanyProfile. "
        "Returns HTTP 200 on success. Returns HTTP 422 for scrape/parse failures "
        "and HTTP 503 when Ollama is unreachable. "
        "An existing valid profile is never overwritten on failure."
    ),
)
def run_research(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ResearchResponse:
    # --- Fetch company (soft-delete aware) ---
    stmt = select(Company).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    company = db.execute(stmt).scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )

    logger.info(
        "Starting research pipeline for company '%s' (%s).",
        company.name,
        company.website_url,
    )

    result = research_company(company, db)

    http_status = _STATUS_TO_HTTP.get(result.scrape_status, status.HTTP_422_UNPROCESSABLE_ENTITY)

    response = ResearchResponse(
        company_id=result.company_id,
        company_name=result.company_name,
        website_url=result.website_url,
        scrape_status=result.scrape_status,
        scrape_error=result.scrape_error,
        business_summary=result.business_summary,
        products_services=result.products_services,
        customer_segments=result.customer_segments,
        positioning=result.positioning,
        verified_facts=result.verified_facts,
        facts_excluded=result.facts_excluded,
        assumptions=result.assumptions,
    )

    if http_status != status.HTTP_200_OK:
        raise HTTPException(status_code=http_status, detail=response.model_dump(mode="json"))

    return response
