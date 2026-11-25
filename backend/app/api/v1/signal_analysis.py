import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.signal import Signal
from app.schemas.signal_analysis import (
    RankedSignalListResponse,
    SignalAnalysisResponse,
)
from app.services.ai import llm_client
from app.services.ai.signal_analyzer import (
    SignalAnalysisError,
    analyze_signal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Signal Analysis"])


def _get_company(company_id: uuid.UUID, db: Session) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    company = db.execute(stmt).scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )
    return company


def _analysis_response(result) -> SignalAnalysisResponse:
    return SignalAnalysisResponse(
        id=result.signal.id,
        company_id=result.signal.company_id,
        source_id=result.signal.source_id,
        title=result.signal.title,
        content_snippet=result.signal.content_snippet,
        source_url=result.signal.source_url,
        verbatim_quote=result.signal.verbatim_quote,
        published_at=result.signal.published_at,
        business_area=result.signal.business_area,
        development_type=result.signal.development_type,
        opportunity_threat=result.signal.opportunity_threat,
        business_impact_score=result.signal.business_impact_score,
        urgency_score=result.signal.urgency_score,
        credibility_score=result.signal.credibility_score,
        relevance_score=result.signal.relevance_score,
        recency_score=result.recency_score,
        novelty_score=result.novelty_score,
        composite_rank=result.signal.composite_rank,
        ai_interpretation=result.signal.ai_interpretation,
        recommended_action=result.signal.recommended_action,
    )


@router.post(
    "/{company_id}/signals/{signal_id}/analyze",
    response_model=SignalAnalysisResponse,
    summary="Analyze a signal using local Ollama",
)
def analyze_company_signal(
    company_id: uuid.UUID,
    signal_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SignalAnalysisResponse:
    company = _get_company(company_id, db)
    signal_stmt = select(Signal).where(
        Signal.id == signal_id,
        Signal.company_id == company_id,
    )
    signal = db.execute(signal_stmt).scalar_one_or_none()
    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal '{signal_id}' not found for this company.",
        )

    try:
        result = analyze_signal(signal, company, db)
    except llm_client.LLMError as exc:
        logger.error("Local Ollama analysis failed for signal %s: %s", signal_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local AI service is unavailable. The signal was not changed.",
        )
    except SignalAnalysisError as exc:
        logger.warning("Signal %s analysis was rejected: %s", signal_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The AI response could not be validated against source evidence. "
                "The signal was not changed."
            ),
        )
    return _analysis_response(result)


@router.get(
    "/{company_id}/signals/ranked",
    response_model=RankedSignalListResponse,
    summary="List analyzed signals by composite rank",
)
def list_ranked_signals(
    company_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RankedSignalListResponse:
    _get_company(company_id, db)

    query = select(Signal).where(
        Signal.company_id == company_id,
        Signal.ai_interpretation.is_not(None),
    )
    count_stmt = select(func.count()).select_from(query.subquery())
    total = db.execute(count_stmt).scalar() or 0
    items_stmt = (
        query.order_by(Signal.composite_rank.desc(), Signal.discovered_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = list(db.execute(items_stmt).scalars().all())
    return RankedSignalListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )
