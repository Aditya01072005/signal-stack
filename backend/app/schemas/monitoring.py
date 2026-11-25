import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class SourceMonitoringResponse(BaseModel):
    source_id: uuid.UUID
    source_name: str
    crawl_status: Literal["success", "blocked", "failed"]
    content_changed: bool
    signal_id: Optional[uuid.UUID] = None
    characters_scraped: Optional[int] = None
    final_url: Optional[str] = None
    message: str

    model_config = ConfigDict(from_attributes=True)


class MonitoringRunResponse(BaseModel):
    company_id: uuid.UUID
    sources_checked: int
    crawled: int
    blocked: int
    failed: int
    new_signals: int
    results: list[SourceMonitoringResponse]


class SignalResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    source_id: Optional[uuid.UUID]
    title: str
    content_snippet: str
    source_url: str
    content_hash: str
    is_verified: bool
    verbatim_quote: Optional[str]
    discovered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SignalListResponse(BaseModel):
    items: list[SignalResponse]
    total: int
    skip: int
    limit: int
