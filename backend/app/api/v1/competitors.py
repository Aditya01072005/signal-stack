"""
Competitor Intelligence API Endpoints (Phase 3, Module 6).

Provides full lifecycle management for competitor intelligence:
  - Add competitor with duplicate prevention (409 Conflict)
  - List competitors with category and active filters
  - Retrieve single competitor by ID
  - Update competitor fields and status
  - Deactivate competitor (soft deactivation preserving audit history)
  - Discover competitor suggestions via local Ollama without auto-saving
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.competitor import Competitor
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorDiscoveryResponse,
    CompetitorResponse,
    CompetitorType,
    CompetitorUpdate,
    normalize_competitor_type,
)
from app.services.ai import competitor_intelligence, llm_client
from app.services.ai.competitor_intelligence import (
    CompetitorLLMError,
    ProfileNotFoundError,
    extract_domain,
    normalize_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/companies/{company_id}/competitors",
    tags=["competitors"],
)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _get_active_company(company_id: uuid.UUID, db: Session) -> Company:
    """Ensure company exists and has not been soft-deleted."""
    stmt = select(Company).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    company = db.execute(stmt).scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found.",
        )
    return company


def _to_response(c: Competitor) -> CompetitorResponse:
    """Convert Competitor model instance to Pydantic CompetitorResponse."""
    meta = c.meta_dict if hasattr(c, "meta_dict") else {}
    description = meta.get("description") or getattr(c, "description", None)
    evidence_url = meta.get("evidence_url") or meta.get("source_url") or getattr(c, "evidence_url", None)
    is_active = meta.get("is_active", True)
    if hasattr(c, "is_active") and isinstance(c.is_active, bool):
        is_active = c.is_active
    is_verified = meta.get("is_verified", True)

    created_at = c.created_at or datetime.now(timezone.utc)
    updated_at = c.updated_at or created_at

    return CompetitorResponse(
        id=c.id,
        company_id=c.company_id,
        name=c.name,
        website_url=c.website_url,
        competitor_type=c.competitor_type,
        category=c.competitor_type,
        description=description,
        evidence_url=evidence_url,
        strengths=c.strengths or [],
        weaknesses=c.weaknesses or [],
        notes=c.notes,
        is_active=is_active,
        is_verified=is_verified,
        created_at=created_at,
        updated_at=updated_at,
    )


def _check_duplicate(
    company_id: uuid.UUID,
    name: str,
    website_url: Optional[str],
    db: Session,
    exclude_id: Optional[uuid.UUID] = None,
) -> None:
    """
    Prevent duplicate competitors for the same company:
    - Match normalized name against active competitors.
    - Match canonical domain against active competitors with websites.
    Raises HTTP 409 Conflict if a duplicate is found.
    """
    stmt = select(Competitor).where(Competitor.company_id == company_id)
    if exclude_id:
        stmt = stmt.where(Competitor.id != exclude_id)

    competitors = db.execute(stmt).scalars().all()

    target_norm_name = normalize_name(name)
    target_domain = extract_domain(website_url) if website_url else None

    for comp in competitors:
        # Check active status
        meta = comp.meta_dict if hasattr(comp, "meta_dict") else {}
        is_active = meta.get("is_active", True)
        if hasattr(comp, "is_active") and isinstance(comp.is_active, bool):
            is_active = comp.is_active

        if not is_active:
            continue

        if comp.name and normalize_name(comp.name) == target_norm_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A competitor with name '{name.strip()}' already exists for this company.",
            )

        if target_domain and comp.website_url:
            comp_domain = extract_domain(comp.website_url)
            if comp_domain and comp_domain == target_domain:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A competitor with website '{website_url.strip()}' already exists for this company.",
                )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=CompetitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a verified competitor",
)
def add_competitor(
    company_id: uuid.UUID,
    payload: CompetitorCreate,
    db: Session = Depends(get_db),
):
    """
    Register a new verified competitor for a company.
    Validates category ('direct', 'indirect', 'substitute') and prevents duplicates.
    """
    company = _get_active_company(company_id, db)
    comp_type = payload.resolved_type()

    _check_duplicate(company.id, payload.name, payload.website_url, db)

    competitor = Competitor(
        company_id=company.id,
        name=payload.name.strip(),
        website_url=payload.website_url.strip() if payload.website_url else None,
        competitor_type=comp_type,
        strengths=payload.strengths or [],
        weaknesses=payload.weaknesses or [],
    )

    # Store description, evidence_url, and active/verified flags safely in notes metadata
    competitor.set_meta(
        description=payload.description or payload.notes,
        evidence_url=payload.evidence_url,
        is_active=True,
        is_verified=bool(payload.evidence_url),
    )

    db.add(competitor)
    db.commit()
    db.refresh(competitor)

    logger.info("Added competitor '%s' (%s) for company '%s'.", competitor.name, comp_type, company.name)
    return _to_response(competitor)


@router.get(
    "",
    response_model=List[CompetitorResponse],
    status_code=status.HTTP_200_OK,
    summary="List competitors",
)
def list_competitors(
    company_id: uuid.UUID,
    category: Optional[str] = Query(None, description="Filter by tier: direct, indirect, substitute"),
    competitor_type: Optional[str] = Query(None, description="Alias for category filter"),
    include_inactive: bool = Query(False, description="Whether to include deactivated competitors"),
    db: Session = Depends(get_db),
):
    """
    Retrieve all competitors mapped to a company.
    Allows filtering by competitor tier and active status.
    """
    company = _get_active_company(company_id, db)

    filter_type = category or competitor_type
    if filter_type:
        filter_type = normalize_competitor_type(filter_type)

    stmt = select(Competitor).where(Competitor.company_id == company.id)
    if filter_type:
        stmt = stmt.where(Competitor.competitor_type == filter_type)

    stmt = stmt.order_by(Competitor.created_at.asc())
    competitors = db.execute(stmt).scalars().all()

    results = []
    for c in competitors:
        resp = _to_response(c)
        if not include_inactive and not resp.is_active:
            continue
        results.append(resp)

    return results


@router.get(
    "/{competitor_id}",
    response_model=CompetitorResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single competitor",
)
def get_competitor(
    company_id: uuid.UUID,
    competitor_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Retrieve details for a single competitor."""
    company = _get_active_company(company_id, db)

    stmt = select(Competitor).where(
        Competitor.id == competitor_id,
        Competitor.company_id == company.id,
    )
    competitor = db.execute(stmt).scalar_one_or_none()
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with ID '{competitor_id}' not found for this company.",
        )

    return _to_response(competitor)


@router.patch(
    "/{competitor_id}",
    response_model=CompetitorResponse,
    status_code=status.HTTP_200_OK,
    summary="Update competitor",
)
def update_competitor(
    company_id: uuid.UUID,
    competitor_id: uuid.UUID,
    payload: CompetitorUpdate,
    db: Session = Depends(get_db),
):
    """Update details, category, or active status of an existing competitor."""
    company = _get_active_company(company_id, db)

    stmt = select(Competitor).where(
        Competitor.id == competitor_id,
        Competitor.company_id == company.id,
    )
    competitor = db.execute(stmt).scalar_one_or_none()
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with ID '{competitor_id}' not found for this company.",
        )

    new_name = payload.name or competitor.name
    new_url = payload.website_url if payload.website_url is not None else competitor.website_url

    if payload.name is not None or payload.website_url is not None:
        _check_duplicate(company.id, new_name, new_url, db, exclude_id=competitor.id)

    if payload.name is not None:
        competitor.name = payload.name.strip()
    if payload.website_url is not None:
        competitor.website_url = payload.website_url.strip() if payload.website_url else None

    resolved_type = payload.resolved_type()
    if resolved_type is not None:
        competitor.competitor_type = resolved_type

    if payload.strengths is not None:
        competitor.strengths = payload.strengths
    if payload.weaknesses is not None:
        competitor.weaknesses = payload.weaknesses

    # Update metadata
    meta = competitor.meta_dict
    if payload.description is not None:
        meta["description"] = payload.description
    elif payload.notes is not None:
        meta["description"] = payload.notes
    if payload.evidence_url is not None:
        meta["evidence_url"] = payload.evidence_url
        meta["is_verified"] = True
    if payload.is_active is not None:
        meta["is_active"] = payload.is_active

    competitor.set_meta(
        description=meta.get("description"),
        evidence_url=meta.get("evidence_url"),
        is_active=meta.get("is_active", True),
        is_verified=meta.get("is_verified", True),
    )

    db.commit()
    db.refresh(competitor)
    return _to_response(competitor)


@router.delete(
    "/{competitor_id}",
    response_model=CompetitorResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate competitor",
)
@router.post(
    "/{competitor_id}/deactivate",
    response_model=CompetitorResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate competitor (explicit POST)",
)
def deactivate_competitor(
    company_id: uuid.UUID,
    competitor_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Deactivate a competitor (soft deactivation).
    Preserves historical intelligence, briefs, and signal mappings while
    excluding it from active tracking.
    """
    company = _get_active_company(company_id, db)

    stmt = select(Competitor).where(
        Competitor.id == competitor_id,
        Competitor.company_id == company.id,
    )
    competitor = db.execute(stmt).scalar_one_or_none()
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competitor with ID '{competitor_id}' not found for this company.",
        )

    competitor.set_meta(
        description=competitor.description,
        evidence_url=competitor.evidence_url,
        is_active=False,
        is_verified=competitor.is_verified,
    )

    db.commit()
    db.refresh(competitor)
    logger.info("Deactivated competitor '%s' for company '%s'.", competitor.name, company.name)
    return _to_response(competitor)


@router.post(
    "/discover",
    response_model=CompetitorDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover competitors via AI",
)
def discover_competitors(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Analyze the company's research profile and generate suggested direct,
    indirect, and substitute competitors using local Ollama.

    AI suggestions are returned for review and are NOT persisted to the
    database until approved via the POST endpoint.
    """
    company = _get_active_company(company_id, db)

    if not company.profile:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Company research profile not found. Please run company research before competitor discovery.",
        )

    try:
        discovery_result = competitor_intelligence.discover_competitors(company, db)
        return discovery_result
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except llm_client.LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Local LLM service is currently unavailable for competitor discovery. Ensure Ollama is running. ({exc})",
        )
    except CompetitorLLMError as exc:
        logger.error("Competitor discovery failed for company '%s': %s", company.name, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to generate competitor suggestions: {exc}",
        )
