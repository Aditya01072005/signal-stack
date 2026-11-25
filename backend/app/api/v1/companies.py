import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.schemas.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    CompanyListResponse,
    normalize_website_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new company",
    description="Registers a new company for intelligence tracking with normalized website URL validation.",
)
def register_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
):
    try:
        # Check if an active company already exists with this normalized website URL
        stmt = select(Company).where(
            Company.is_deleted == False,
            Company.website_url == payload.website_url,
        )
        existing = db.execute(stmt).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A company with website '{payload.website_url}' is already registered.",
            )

        new_company = Company(
            name=payload.name,
            website_url=payload.website_url,
            industry=payload.industry,
            status="active",
        )
        db.add(new_company)
        db.commit()
        db.refresh(new_company)
        return new_company

    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A company with website '{payload.website_url}' is already registered.",
        )
    except Exception as e:
        db.rollback()
        logger.error("Failed to register company: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register company due to an internal database error.",
        )


@router.get(
    "",
    response_model=CompanyListResponse,
    summary="List registered companies",
    description="Retrieves a paginated list of non-deleted companies.",
)
def list_companies(
    skip: int = Query(0, ge=0, description="Records to skip for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    search: Optional[str] = Query(None, description="Optional search by company name or industry"),
    db: Session = Depends(get_db),
):
    try:
        query = select(Company).where(Company.is_deleted == False)

        if search:
            search_term = f"%{search.strip().lower()}%"
            query = query.where(
                func.lower(Company.name).like(search_term)
                | func.lower(Company.industry).like(search_term)
            )

        # Count total matching items
        total_stmt = select(func.count()).select_from(query.subquery())
        total = db.execute(total_stmt).scalar() or 0

        # Fetch paginated items ordered by creation date descending
        items_stmt = query.order_by(Company.created_at.desc()).offset(skip).limit(limit)
        items = list(db.execute(items_stmt).scalars().all())

        return CompanyListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        logger.error("Failed to list companies: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch companies list.",
        )


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Retrieve a company",
    description="Retrieves details for a single company by its unique identifier.",
)
def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    try:
        stmt = select(Company).where(
            Company.id == company_id,
            Company.is_deleted == False,
        )
        company = db.execute(stmt).scalar_one_or_none()

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID '{company_id}' was not found.",
            )
        return company

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve company %s: %s", company_id, type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving company record.",
        )


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Update company details",
    description="Updates editable attributes of a company (name, website, industry, status).",
)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
):
    try:
        stmt = select(Company).where(
            Company.id == company_id,
            Company.is_deleted == False,
        )
        company = db.execute(stmt).scalar_one_or_none()

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID '{company_id}' was not found.",
            )

        # Check for duplicate website URL if changing website
        if payload.website_url and payload.website_url != company.website_url:
            dup_stmt = select(Company).where(
                Company.id != company_id,
                Company.is_deleted == False,
                Company.website_url == payload.website_url,
            )
            existing_dup = db.execute(dup_stmt).scalar_one_or_none()
            if existing_dup:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Another company is already registered with website '{payload.website_url}'.",
                )
            company.website_url = payload.website_url

        if payload.name is not None:
            company.name = payload.name
        if payload.industry is not None:
            company.industry = payload.industry
        if payload.status is not None:
            company.status = payload.status

        db.commit()
        db.refresh(company)
        return company

    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another company is already registered with website '{payload.website_url}'.",
        )
    except Exception as e:
        db.rollback()
        logger.error("Failed to update company %s: %s", company_id, type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating company record.",
        )
