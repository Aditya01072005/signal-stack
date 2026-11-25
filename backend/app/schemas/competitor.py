"""
Pydantic schemas for Competitor Intelligence (Phase 3, Module 6).
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.company import normalize_website_url


class CompetitorType(str, Enum):
    """Classification of competitors by strategic tier."""
    DIRECT = "direct"
    INDIRECT = "indirect"
    SUBSTITUTE = "substitute"


def normalize_competitor_type(val: Optional[str]) -> Optional[str]:
    """Normalize input string to valid competitor type or None."""
    if not val:
        return None
    cleaned = str(val).strip().lower()
    if cleaned in ("direct", "indirect", "substitute"):
        return cleaned
    raise ValueError(f"Invalid competitor type '{val}'. Must be one of: direct, indirect, substitute.")


class CompetitorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Competitor company name")
    website_url: Optional[str] = Field(None, max_length=500, description="Competitor website URL")
    competitor_type: CompetitorType = Field(CompetitorType.DIRECT, description="Competitor tier: direct, indirect, substitute")
    category: Optional[CompetitorType] = Field(None, description="Alias for competitor_type")
    description: Optional[str] = Field(None, description="Brief description of competitor offering")
    evidence_url: Optional[str] = Field(None, max_length=1000, description="Evidence or source URL justifying competitor status")
    strengths: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Known strengths")
    weaknesses: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Known weaknesses")
    notes: Optional[str] = Field(None, description="Additional notes or comments")


class CompetitorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Competitor company name")
    website_url: Optional[str] = Field(None, max_length=500, description="Competitor website URL")
    competitor_type: Optional[CompetitorType] = Field(None, description="Competitor tier: direct, indirect, substitute")
    category: Optional[CompetitorType] = Field(None, description="Alias for competitor_type")
    description: Optional[str] = Field(None, description="Brief description of competitor offering")
    evidence_url: Optional[str] = Field(None, max_length=1000, description="Evidence or source URL")
    strengths: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    weaknesses: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    notes: Optional[str] = Field(None)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip() if v else ""
        if not cleaned:
            raise ValueError("Competitor name cannot be blank.")
        return cleaned

    @field_validator("website_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return normalize_website_url(v)
        return None

    @field_validator("evidence_url")
    @classmethod
    def validate_evidence_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return normalize_website_url(v)
        return None

    def resolved_type(self) -> str:
        """Resolve either category or competitor_type to standard string."""
        target = self.category or self.competitor_type or CompetitorType.DIRECT
        return target.value if isinstance(target, CompetitorType) else str(target)


class CompetitorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    website_url: Optional[str] = Field(None, max_length=500)
    competitor_type: Optional[CompetitorType] = None
    category: Optional[CompetitorType] = None
    description: Optional[str] = None
    evidence_url: Optional[str] = None
    strengths: Optional[List[Dict[str, Any]]] = None
    weaknesses: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Competitor name cannot be blank.")
            return cleaned
        return None

    @field_validator("website_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return normalize_website_url(v)
        return None

    @field_validator("evidence_url")
    @classmethod
    def validate_evidence_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return normalize_website_url(v)
        return None

    def resolved_type(self) -> Optional[str]:
        target = self.category or self.competitor_type
        if target is None:
            return None
        return target.value if isinstance(target, CompetitorType) else str(target)


class CompetitorResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    website_url: Optional[str] = None
    competitor_type: str
    category: str
    description: Optional[str] = None
    evidence_url: Optional[str] = None
    strengths: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    weaknesses: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    notes: Optional[str] = None
    is_active: bool = True
    is_verified: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompetitorSuggestion(BaseModel):
    name: str
    website_url: Optional[str] = None
    competitor_type: str
    category: str
    description: str
    ai_rationale: str
    evidence_url: Optional[str] = None
    is_verified: bool = False
    is_already_added: bool = False


class CompetitorDiscoveryResponse(BaseModel):
    company_id: uuid.UUID
    company_name: str
    suggestions_count: int
    suggestions: List[CompetitorSuggestion]
    generated_at: datetime
