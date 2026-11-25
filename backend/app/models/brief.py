import uuid
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional, List, Any
from sqlalchemy import String, Text, Date, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company


class Brief(Base):
    """
    Weekly Monday Morning Intelligence Brief generated for leadership.
    Referential integrity is set to RESTRICT to protect historical executive briefs.
    """

    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    limitations_and_blind_spots: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_status: Mapped[str] = mapped_column(
        String(50), default="ready", nullable=False
    )  # draft, ready, sent
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="briefs")
    sections: Mapped[List["BriefSection"]] = relationship(
        "BriefSection", back_populates="brief", cascade="all, delete-orphan"
    )
    action_items: Mapped[List["ActionItem"]] = relationship(
        "ActionItem", back_populates="brief", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('draft', 'ready', 'sent')",
            name="ck_brief_delivery_status",
        ),
        Index("ix_briefs_company_date", "company_id", "briefing_date"),
    )


class BriefSection(Base):
    """
    Structured sections of the 10-section executive brief,
    with back-references to verified signals cited.
    """

    __tablename__ = "brief_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("briefs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    section_key: Mapped[str] = mapped_column(String(100), nullable=False)
    section_title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_signal_ids: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    brief: Mapped["Brief"] = relationship("Brief", back_populates="sections")

    __table_args__ = (
        Index("ix_brief_sections_brief_key", "brief_id", "section_key"),
    )


class ActionItem(Base):
    """Operational recommendations and action items extracted from the brief."""

    __tablename__ = "action_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("briefs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(50), default="medium", nullable=False
    )  # high, medium, low
    suggested_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, in_progress, completed

    # Relationships
    brief: Mapped["Brief"] = relationship("Brief", back_populates="action_items")

    __table_args__ = (
        CheckConstraint(
            "priority IN ('high', 'medium', 'low')",
            name="ck_action_item_priority",
        ),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed')",
            name="ck_action_item_status",
        ),
    )
