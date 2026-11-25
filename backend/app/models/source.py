import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.signal import Signal
    from app.models.document import Document


class Source(Base):
    """
    4-Quadrant Signal Stack intelligence source:
    - Customers: buyer pain points, complaints, review channels
    - Competitors: rival updates, pricing, feature releases
    - Market: regulatory, industry news, macroeconomic
    - Internal: customer support logs, CRM exports, sales notes
    """

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Strictly enforced 4-quadrant categories
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # Customers, Competitors, Market, Internal
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    justification_reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(50), default="rss", nullable=False
    )  # rss, html, api, document
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )  # active, inactive, dead

    # Health & crawling diagnostics for monthly audits
    health_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_successful_crawl_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="sources")
    signals: Mapped[List["Signal"]] = relationship(
        "Signal", back_populates="source"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="source"
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('Customers', 'Competitors', 'Market', 'Internal')",
            name="ck_source_category",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'dead')",
            name="ck_source_status",
        ),
        Index("ix_sources_company_category", "company_id", "category"),
    )
