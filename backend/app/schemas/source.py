"""
Pydantic schemas for Source Manager endpoints.

Categories are strictly enforced to the 4 Signal Stack quadrants:
  Customers, Competitors, Market, Internal

URL validation rejects non-http/https schemes and bare IPs that look
like SSRF targets (the scraper enforces full SSRF protection at crawl time).
"""

import uuid
from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_CATEGORIES = frozenset({"Customers", "Competitors", "Market", "Internal"})
VALID_STATUSES = frozenset({"active", "inactive", "dead"})


def _validate_source_url(url: str) -> str:
    """Reject empty, non-http/https, or structurally invalid URLs."""
    if not url or not url.strip():
        raise ValueError("URL cannot be empty.")
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("URL scheme must be http or https.")
    if not parsed.netloc:
        raise ValueError("URL must contain a valid host.")
    return cleaned


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., description="Public URL of the source (http or https)")
    category: str = Field(..., description="One of: Customers, Competitors, Market, Internal")
    description: Optional[str] = Field(
        None,
        description="Why this source is relevant (stored as justification_reason)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("Source name cannot be blank.")
        return name

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _validate_source_url(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: "
                + ", ".join(sorted(VALID_CATEGORIES))
            )
        return v


class SourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = Field(
        None,
        description="Set false to deactivate (status → inactive), true to reactivate (status → active)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            name = v.strip()
            if not name:
                raise ValueError("Source name cannot be blank.")
            return name
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_source_url(v)
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: "
                + ", ".join(sorted(VALID_CATEGORIES))
            )
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SourceResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    url: str
    category: str
    description: Optional[str] = None   # alias for justification_reason
    source_type: str
    status: str
    health_score: int
    last_crawled_at: Optional[datetime] = None
    last_successful_crawl_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    consecutive_failures: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_source(cls, src) -> "SourceResponse":
        """Map ORM Source → SourceResponse, aliasing justification_reason → description."""
        return cls(
            id=src.id,
            company_id=src.company_id,
            name=src.name,
            url=src.url,
            category=src.category,
            description=src.justification_reason or None,
            source_type=src.source_type,
            status=src.status,
            health_score=src.health_score,
            last_crawled_at=src.last_crawled_at,
            last_successful_crawl_at=src.last_successful_crawl_at,
            last_error_message=src.last_error_message,
            consecutive_failures=src.consecutive_failures,
            created_at=src.created_at,
        )


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int
    skip: int
    limit: int


class CrawlResponse(BaseModel):
    source_id: uuid.UUID
    crawl_status: Literal["success", "blocked", "failed"]
    message: str
    characters_scraped: Optional[int] = None
    final_url: Optional[str] = None
