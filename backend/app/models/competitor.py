import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company


class Competitor(Base):
    """
    Competitor entity mapped to a company across three tiers:
    - direct (direct rivals)
    - indirect (alternative solutions addressing same pain)
    - substitute (broader workarounds / manual processes)
    """

    __tablename__ = "competitors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    competitor_type: Mapped[str] = mapped_column(
        String(50), default="direct", nullable=False
    )  # direct, indirect, substitute
    strengths: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    weaknesses: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="competitors")

    __table_args__ = (
        CheckConstraint(
            "competitor_type IN ('direct', 'indirect', 'substitute')",
            name="ck_competitor_type",
        ),
        Index("ix_competitors_company_type", "company_id", "competitor_type"),
    )

    # -----------------------------------------------------------------------
    # Metadata helpers (safe storage in notes column without schema migration)
    # -----------------------------------------------------------------------

    @property
    def meta_dict(self) -> Dict[str, Any]:
        """Parse structured metadata stored in `notes`."""
        if not self.notes:
            return {}
        try:
            parsed = json.loads(self.notes)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"description": self.notes}

    def set_meta(
        self,
        description: Optional[str] = None,
        evidence_url: Optional[str] = None,
        is_active: bool = True,
        is_verified: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store structured metadata safely in `notes` without modifying database columns."""
        current = self.meta_dict
        if description is not None:
            current["description"] = description
        if evidence_url is not None:
            current["evidence_url"] = evidence_url
        current["is_active"] = is_active
        current["is_verified"] = is_verified
        if extra:
            current.update(extra)
        self.notes = json.dumps(current)

    @property
    def description(self) -> Optional[str]:
        return self.meta_dict.get("description")

    @property
    def evidence_url(self) -> Optional[str]:
        return self.meta_dict.get("evidence_url") or self.meta_dict.get("source_url")

    @property
    def is_active(self) -> bool:
        return self.meta_dict.get("is_active", True)

    @property
    def is_verified(self) -> bool:
        return self.meta_dict.get("is_verified", True)
