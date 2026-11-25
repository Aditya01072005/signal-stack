import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BriefSectionResponse(BaseModel):
    id: uuid.UUID
    brief_id: uuid.UUID
    section_key: str
    section_title: str
    content: str
    referenced_signal_ids: Optional[list[str]] = None

    model_config = ConfigDict(from_attributes=True)


class BriefActionItemResponse(BaseModel):
    id: uuid.UUID
    brief_id: uuid.UUID
    action_text: str
    priority: str
    suggested_owner: Optional[str]
    status: str

    model_config = ConfigDict(from_attributes=True)


class BriefHistoryItemResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    briefing_date: date
    executive_summary: Optional[str]
    limitations_and_blind_spots: Optional[str]
    delivery_status: str
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BriefDetailResponse(BriefHistoryItemResponse):
    sections: list[BriefSectionResponse]
    action_items: list[BriefActionItemResponse]


class BriefHistoryListResponse(BaseModel):
    items: list[BriefHistoryItemResponse]
    total: int
    skip: int
    limit: int
