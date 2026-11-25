import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.signal import Signal
from app.schemas.monitoring import MonitoringRunResponse, SignalListResponse
from app.services.monitoring.pipeline import (
    CompanyNotFoundError,
    run_company_monitoring,
)

router = APIRouter(prefix="/companies", tags=["Monitoring"])


def _require_active_company(company_id: uuid.UUID, db: Session) -> None:
    stmt = select(Company.id).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    if db.execute(stmt).scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )


@router.post(
    "/{company_id}/monitoring/run",
    response_model=MonitoringRunResponse,
    summary="Run monitoring for all active company sources",
)
def monitor_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MonitoringRunResponse:
    try:
        results = run_company_monitoring(company_id, db)
    except CompanyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )

    return MonitoringRunResponse(
        company_id=company_id,
        sources_checked=len(results),
        crawled=sum(result.crawl_status == "success" for result in results),
        blocked=sum(result.crawl_status == "blocked" for result in results),
        failed=sum(result.crawl_status == "failed" for result in results),
        new_signals=sum(result.content_changed for result in results),
        results=results,
    )


@router.get(
    "/{company_id}/signals",
    response_model=SignalListResponse,
    summary="List recorded signals for a company",
)
def list_company_signals(
    company_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SignalListResponse:
    _require_active_company(company_id, db)

    query = select(Signal).where(Signal.company_id == company_id)
    count_stmt = select(func.count()).select_from(query.subquery())
    total = db.execute(count_stmt).scalar() or 0
    items_stmt = (
        query.order_by(Signal.discovered_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = list(db.execute(items_stmt).scalars().all())
    return SignalListResponse(items=items, total=total, skip=skip, limit=limit)
