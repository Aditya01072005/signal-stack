import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.interview import Interview
    from app.models.competitor import Competitor
    from app.models.source import Source
    from app.models.document import Document
    from app.models.signal import Signal
    from app.models.brief import Brief
    from app.models.audit import AuditLog


class Company(Base):
    """
    Master record for companies tracked in Signal Stack.
    Implements soft deletion to preserve historical intelligence and auditability.
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website_url: Mapped[str] = mapped_column(String(500), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    # Soft deletion flags to avoid accidental loss of intelligence records
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Direct setup / context relationships (cascaded on hard company cleanup)
    profile: Mapped[Optional["CompanyProfile"]] = relationship(
        "CompanyProfile", back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    interviews: Mapped[List["Interview"]] = relationship(
        "Interview", back_populates="company", cascade="all, delete-orphan"
    )
    competitors: Mapped[List["Competitor"]] = relationship(
        "Competitor", back_populates="company", cascade="all, delete-orphan"
    )
    sources: Mapped[List["Source"]] = relationship(
        "Source", back_populates="company", cascade="all, delete-orphan"
    )

    # Historical intelligence & audit logs are RESTRICTED from deletion
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="company"
    )
    signals: Mapped[List["Signal"]] = relationship(
        "Signal", back_populates="company"
    )
    briefs: Mapped[List["Brief"]] = relationship(
        "Brief", back_populates="company"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="company"
    )

    __table_args__ = (
        Index(
            "uq_companies_active_website_canonical",
            text("(lower(substring(website_url from '^([a-zA-Z]+://[^/?#]+)')) || regexp_replace(coalesce(substring(website_url from '^[a-zA-Z]+://[^/?#]+(.*)$'), ''), '/+(?=[?#]|$)', '', 'g'))"),
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )


class CompanyProfile(Base):
    """
    Initial automated research output distinguishing verified public facts
    from inferred assumptions.
    """

    __tablename__ = "company_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    business_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    products_services: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    customer_segments: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    positioning: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    verified_facts: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    assumptions: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="profile")
