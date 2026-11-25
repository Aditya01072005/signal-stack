"""
Source Manager API — Phase 3, Module 4.

Endpoints:
  POST   /api/v1/companies/{company_id}/sources
  GET    /api/v1/companies/{company_id}/sources
  GET    /api/v1/companies/{company_id}/sources/{source_id}
  PATCH  /api/v1/companies/{company_id}/sources/{source_id}
  DELETE /api/v1/companies/{company_id}/sources/{source_id}
  POST   /api/v1/companies/{company_id}/sources/{source_id}/crawl

Crawl limitation:
  The existing `sources` table stores per-source crawl metadata
  (last_crawled_at, last_successful_crawl_at, last_error_message,
  consecutive_failures, health_score) but has no crawl-history table.
  Each crawl therefore overwrites the previous crawl metadata on the
  source row.  Full crawl history would require a separate table and
  a new migration — that is out of scope for this module.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.source import Source
from app.schemas.source import (
    CrawlResponse,
    SourceCreate,
    SourceListResponse,
    SourceResponse,
    SourceUpdate,
)
from app.services.crawler.scraper import (
    EthicalScraper,
    FetchBlockedError,
    MaxRetriesExceededError,
    RateLimitedError,
    RobotsBlockedError,
    RobotsUnavailableError,
    SSRFBlockedError,
    ScraperError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Sources"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_active_company(company_id: uuid.UUID, db: Session) -> Company:
    """Return the company or raise 404 if not found / soft-deleted."""
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
    return company


def _get_source(source_id: uuid.UUID, company_id: uuid.UUID, db: Session) -> Source:
    """Return the source belonging to the company or raise 404."""
    stmt = select(Source).where(
        Source.id == source_id,
        Source.company_id == company_id,
    )
    src = db.execute(stmt).scalar_one_or_none()
    if not src:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' not found for this company.",
        )
    return src


def _check_duplicate_url(
    url: str,
    company_id: uuid.UUID,
    db: Session,
    exclude_id: Optional[uuid.UUID] = None,
) -> None:
    """Raise 409 if an active source with the same URL already exists for this company."""
    stmt = select(Source).where(
        Source.company_id == company_id,
        Source.url == url,
        Source.status == "active",
    )
    if exclude_id is not None:
        stmt = stmt.where(Source.id != exclude_id)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active source with URL '{url}' already exists for this company.",
        )


# ---------------------------------------------------------------------------
# POST /companies/{company_id}/sources — Add source
# ---------------------------------------------------------------------------

@router.post(
    "/{company_id}/sources",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a source to a company",
)
def add_source(
    company_id: uuid.UUID,
    payload: SourceCreate,
    db: Session = Depends(get_db),
) -> SourceResponse:
    _get_active_company(company_id, db)
    _check_duplicate_url(payload.url, company_id, db)

    src = Source(
        company_id=company_id,
        name=payload.name,
        url=payload.url,
        category=payload.category,
        justification_reason=payload.description or "",
        source_type="html",
        status="active",
        health_score=100,
        consecutive_failures=0,
    )
    try:
        db.add(src)
        db.commit()
        db.refresh(src)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to add source: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save source.",
        )
    return SourceResponse.from_orm_source(src)


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/sources — List sources
# ---------------------------------------------------------------------------

@router.get(
    "/{company_id}/sources",
    response_model=SourceListResponse,
    summary="List sources for a company",
)
def list_sources(
    company_id: uuid.UUID,
    category: Optional[str] = Query(None, description="Filter by category"),
    include_inactive: bool = Query(False, description="Include inactive/dead sources"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SourceListResponse:
    _get_active_company(company_id, db)

    if category is not None and category not in ("Customers", "Competitors", "Market", "Internal"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category '{category}'. Must be one of: Customers, Competitors, Market, Internal",
        )

    query = select(Source).where(Source.company_id == company_id)
    if not include_inactive:
        query = query.where(Source.status == "active")
    if category:
        query = query.where(Source.category == category)

    total_stmt = select(func.count()).select_from(query.subquery())
    total = db.execute(total_stmt).scalar() or 0

    items_stmt = query.order_by(Source.created_at.desc()).offset(skip).limit(limit)
    items = list(db.execute(items_stmt).scalars().all())

    return SourceListResponse(
        items=[SourceResponse.from_orm_source(s) for s in items],
        total=total,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/sources/{source_id} — Get one source
# ---------------------------------------------------------------------------

@router.get(
    "/{company_id}/sources/{source_id}",
    response_model=SourceResponse,
    summary="Retrieve a single source",
)
def get_source(
    company_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SourceResponse:
    _get_active_company(company_id, db)
    src = _get_source(source_id, company_id, db)
    return SourceResponse.from_orm_source(src)


# ---------------------------------------------------------------------------
# PATCH /companies/{company_id}/sources/{source_id} — Update source
# ---------------------------------------------------------------------------

@router.patch(
    "/{company_id}/sources/{source_id}",
    response_model=SourceResponse,
    summary="Update a source",
)
def update_source(
    company_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
) -> SourceResponse:
    _get_active_company(company_id, db)
    src = _get_source(source_id, company_id, db)

    if payload.url is not None and payload.url != src.url:
        _check_duplicate_url(payload.url, company_id, db, exclude_id=source_id)
        src.url = payload.url

    if payload.name is not None:
        src.name = payload.name
    if payload.category is not None:
        src.category = payload.category
    if payload.description is not None:
        src.justification_reason = payload.description
    if payload.active is not None:
        src.status = "active" if payload.active else "inactive"

    try:
        db.commit()
        db.refresh(src)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to update source %s: %s", source_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update source.",
        )
    return SourceResponse.from_orm_source(src)


# ---------------------------------------------------------------------------
# DELETE /companies/{company_id}/sources/{source_id} — Deactivate source
# ---------------------------------------------------------------------------

@router.delete(
    "/{company_id}/sources/{source_id}",
    response_model=SourceResponse,
    summary="Deactivate a source (soft delete)",
    description=(
        "Sets the source status to 'inactive'. "
        "Historical crawl metadata and any associated signals are preserved."
    ),
)
def deactivate_source(
    company_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SourceResponse:
    _get_active_company(company_id, db)
    src = _get_source(source_id, company_id, db)

    if src.status == "inactive":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source is already inactive.",
        )

    src.status = "inactive"
    try:
        db.commit()
        db.refresh(src)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to deactivate source %s: %s", source_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate source.",
        )
    return SourceResponse.from_orm_source(src)


# ---------------------------------------------------------------------------
# POST /companies/{company_id}/sources/{source_id}/crawl — Crawl source
# ---------------------------------------------------------------------------

@router.post(
    "/{company_id}/sources/{source_id}/crawl",
    response_model=CrawlResponse,
    summary="Crawl a source URL",
    description=(
        "Fetches the source URL using the ethical scraper. "
        "Respects robots.txt, rate limits, SSRF protection, and retry rules. "
        "Updates crawl metadata on the source row. "
        "NOTE: The current schema stores only the most recent crawl metadata "
        "per source. Full crawl history requires a separate crawl_history table "
        "which is not yet implemented."
    ),
)
def crawl_source(
    company_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> CrawlResponse:
    _get_active_company(company_id, db)
    src = _get_source(source_id, company_id, db)

    if src.status != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot crawl an inactive source (status='{src.status}'). Reactivate it first.",
        )

    now = datetime.now(timezone.utc)
    src.last_crawled_at = now

    try:
        with EthicalScraper() as scraper:
            result = scraper.scrape(src.url)

        # Success path
        src.last_successful_crawl_at = now
        src.last_error_message = None
        src.consecutive_failures = 0
        src.health_score = min(100, src.health_score + 10)

        db.commit()
        db.refresh(src)

        logger.info(
            "Crawl succeeded for source '%s' (%s): %d chars.",
            src.name,
            src.url,
            len(result.clean_text),
        )
        return CrawlResponse(
            source_id=src.id,
            crawl_status="success",
            message=f"Crawled successfully. {len(result.clean_text)} characters extracted.",
            characters_scraped=len(result.clean_text),
            final_url=result.final_url,
        )

    except (SSRFBlockedError, RobotsBlockedError, RobotsUnavailableError, FetchBlockedError) as exc:
        error_msg = str(exc)
        src.last_error_message = error_msg
        src.consecutive_failures += 1
        src.health_score = max(0, src.health_score - 20)
        db.commit()

        logger.warning("Crawl blocked for source '%s': %s", src.name, error_msg)
        return CrawlResponse(
            source_id=src.id,
            crawl_status="blocked",
            message=error_msg,
        )

    except (MaxRetriesExceededError, RateLimitedError, ScraperError) as exc:
        error_msg = str(exc)
        src.last_error_message = error_msg
        src.consecutive_failures += 1
        src.health_score = max(0, src.health_score - 10)
        db.commit()

        logger.warning("Crawl failed for source '%s': %s", src.name, error_msg)
        return CrawlResponse(
            source_id=src.id,
            crawl_status="failed",
            message=error_msg,
        )

    except Exception as exc:
        error_msg = f"Unexpected error: {type(exc).__name__}: {exc}"
        src.last_error_message = error_msg
        src.consecutive_failures += 1
        src.health_score = max(0, src.health_score - 10)
        try:
            db.commit()
        except Exception:
            db.rollback()

        logger.error("Unexpected crawl error for source '%s': %s", src.name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during crawling.",
        )
