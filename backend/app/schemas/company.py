import re
from datetime import datetime
from typing import Optional, List
from urllib.parse import urlparse
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_website_url(url: str) -> str:
    """
    Validates and normalizes website URLs:
    - Strips surrounding whitespace
    - Ensures valid http/https scheme (normalized to lowercase)
    - Ensures valid host with at least one domain dot or localhost (normalized to lowercase)
    - Preserves case of the URL path (since paths can be case-sensitive)
    - Preserves case of query parameters and fragments
    - Strips trailing slashes consistently (e.g. /About/ -> /About, / -> '')
    """
    if not url:
        raise ValueError("Website URL cannot be empty.")

    cleaned = url.strip()

    # Prepend https:// if user omitted scheme (case-insensitive check)
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("URL scheme must be http or https.")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if not netloc:
        raise ValueError("URL must contain a valid domain name.")

    # Validate domain structure (e.g., domain.tld or localhost)
    domain_pattern = r"^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$|^localhost(:\d+)?$"
    host_without_port = netloc.split(":")[0]
    if not re.match(domain_pattern, host_without_port):
        raise ValueError(f"'{netloc}' is not a valid domain format.")

    # Preserve exact case of path, strip trailing slash consistently
    path = parsed.path.rstrip("/") if parsed.path else ""

    normalized = f"{scheme}://{netloc}{path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    if parsed.fragment:
        normalized = f"{normalized}#{parsed.fragment}"

    return normalized


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Official company name")
    website_url: str = Field(..., description="Company public website URL (http or https)")
    industry: Optional[str] = Field(None, max_length=100, description="Industry sector")


class CompanyCreate(CompanyBase):
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("Company name cannot be blank or empty whitespace.")
        return name

    @field_validator("website_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return normalize_website_url(v)


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    website_url: Optional[str] = None
    industry: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            name = v.strip()
            if not name:
                raise ValueError("Company name cannot be blank.")
            return name
        return v

    @field_validator("website_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return normalize_website_url(v)
        return v


class CompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    website_url: str
    industry: Optional[str] = None
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyListResponse(BaseModel):
    items: List[CompanyResponse]
    total: int
    skip: int
    limit: int
