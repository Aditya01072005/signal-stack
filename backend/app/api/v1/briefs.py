import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.brief import Brief
from app.models.company import Company
from app.schemas.brief import (
    BriefDetailResponse,
    BriefHistoryItemResponse,
    BriefHistoryListResponse,
)
from app.services.ai import llm_client
from app.services.ai.brief_generator import (
    BRIEF_SECTIONS,
    BriefGenerationError,
    CompanyNotFoundError,
    generate_company_brief,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Executive Briefs"])


def _get_company(company_id: uuid.UUID, db: Session) -> None:
    stmt = select(Company.id).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    if db.execute(stmt).scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )


def _detail_response(brief: Brief) -> BriefDetailResponse:
    section_order = {
        key: index for index, (key, _) in enumerate(BRIEF_SECTIONS)
    }
    sections = sorted(
        brief.sections,
        key=lambda section: section_order.get(section.section_key, len(section_order)),
    )
    return BriefDetailResponse(
        id=brief.id,
        company_id=brief.company_id,
        title=brief.title,
        briefing_date=brief.briefing_date,
        executive_summary=brief.executive_summary,
        limitations_and_blind_spots=brief.limitations_and_blind_spots,
        delivery_status=brief.delivery_status,
        generated_at=brief.generated_at,
        sections=sections,
        action_items=brief.action_items,
    )


@router.post(
    "/{company_id}/briefs/generate",
    response_model=BriefDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a ten-section executive brief",
)
def generate_brief(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BriefDetailResponse:
    try:
        brief = generate_company_brief(company_id, db)
    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )
    except llm_client.LLMError as exc:
        logger.error("Local Ollama brief generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local AI service is unavailable. No brief was created.",
        )
    except BriefGenerationError as exc:
        logger.warning("Brief generation rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The AI response could not be validated against stored signal "
                "evidence. No brief was created."
            ),
        )
    return _detail_response(brief)


@router.get(
    "/{company_id}/briefs",
    response_model=BriefHistoryListResponse,
    summary="List historical executive briefs",
)
def list_briefs(
    company_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> BriefHistoryListResponse:
    _get_company(company_id, db)
    query = select(Brief).where(Brief.company_id == company_id)
    total = db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar() or 0
    briefs = list(
        db.execute(
            query.order_by(Brief.briefing_date.desc(), Brief.generated_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
    )
    return BriefHistoryListResponse(
        items=[BriefHistoryItemResponse.model_validate(brief) for brief in briefs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{company_id}/briefs/current",
    response_model=BriefDetailResponse,
    summary="Retrieve the latest executive brief",
)
def get_current_brief(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BriefDetailResponse:
    _get_company(company_id, db)
    stmt = (
        select(Brief)
        .options(selectinload(Brief.sections), selectinload(Brief.action_items))
        .where(Brief.company_id == company_id)
        .order_by(Brief.briefing_date.desc(), Brief.generated_at.desc())
        .limit(1)
    )
    brief = db.execute(stmt).scalar_one_or_none()
    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No executive brief has been generated for this company.",
        )
    return _detail_response(brief)


@router.get(
    "/{company_id}/briefs/{brief_id}",
    response_model=BriefDetailResponse,
    summary="Retrieve a historical executive brief",
)
def get_brief(
    company_id: uuid.UUID,
    brief_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BriefDetailResponse:
    _get_company(company_id, db)
    stmt = (
        select(Brief)
        .options(selectinload(Brief.sections), selectinload(Brief.action_items))
        .where(
            Brief.id == brief_id,
            Brief.company_id == company_id,
        )
    )
    brief = db.execute(stmt).scalar_one_or_none()
    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brief '{brief_id}' not found for this company.",
        )
    return _detail_response(brief)
