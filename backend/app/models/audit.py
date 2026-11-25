import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Dict, Any
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company


class AuditLog(Base):
    """
    Execution logs for weekly brief generation, monthly health checks,
    dead URL tracking, and crawler operations.
    Referential integrity is set to RESTRICT to preserve audit history.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # weekly_brief, monthly_health_audit, crawl, source_discovery
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # success, partial_failure, error
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_company_task", "company_id", "task_type"),
    )
