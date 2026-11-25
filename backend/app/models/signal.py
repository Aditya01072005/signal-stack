import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, Boolean, Float, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.source import Source


class Signal(Base):
    """
    Crawled and analyzed intelligence item evaluated across the 9 dimensions:
    1. What happened (title, content_snippet)
    2. When it happened (published_at)
    3. Source & Evidence verification (source_url, is_verified, verbatim_quote, evidence_strength_score)
    4. Business area affected (business_area)
    5. Development classification (development_type)
    6. Opportunity vs Threat vs Neutral (opportunity_threat)
    7. Urgency (1-10) & Impact (1-10)
    8. Credibility & Relevance
    9. Recommended executive action & strategic interpretation
    """

    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RESTRICT prevents accidental data wipeout of evidence
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # SHA-256 hash of normalized content
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verbatim_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_strength_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    business_area: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    development_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Opportunity vs Threat vs Neutral
    opportunity_threat: Mapped[str] = mapped_column(
        String(20), default="neutral", nullable=False
    )  # opportunity, threat, neutral

    # Multi-dimensional scoring metrics (1-10)
    urgency_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    business_impact_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    credibility_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    composite_rank: Mapped[float] = mapped_column(
        Float, default=5.0, index=True, nullable=False
    )

    # Strategic AI Interpretation & Recommended Action
    ai_interpretation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="signals")
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="signals")

    __table_args__ = (
        CheckConstraint(
            "opportunity_threat IN ('opportunity', 'threat', 'neutral')",
            name="ck_signal_opportunity_threat",
        ),
        # Unique constraint guarantees no duplicate signals per company
        UniqueConstraint("company_id", "content_hash", name="uq_company_signal_content_hash"),
        Index("ix_signals_company_composite_rank", "company_id", "composite_rank"),
    )
