"""
SQLAlchemy models registration package.
Importing all models here ensures Base.metadata is fully populated for Alembic migrations.
"""

from app.models.company import Company, CompanyProfile
from app.models.interview import Interview, InterviewQuestion
from app.models.competitor import Competitor
from app.models.source import Source
from app.models.document import Document
from app.models.signal import Signal
from app.models.brief import Brief, BriefSection, ActionItem
from app.models.audit import AuditLog

__all__ = [
    "Company",
    "CompanyProfile",
    "Interview",
    "InterviewQuestion",
    "Competitor",
    "Source",
    "Document",
    "Signal",
    "Brief",
    "BriefSection",
    "ActionItem",
    "AuditLog",
]
