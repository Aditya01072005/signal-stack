import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class SignalAnalysisResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    source_id: Optional[uuid.UUID]
    title: str
    content_snippet: str
    source_url: str
    verbatim_quote: Optional[str]
    published_at: Optional[datetime]
    business_area: Optional[str]
    development_type: Optional[str]
    opportunity_threat: Literal["opportunity", "threat", "neutral"]
    business_impact_score: float
    urgency_score: float
    credibility_score: float
    relevance_score: float
    recency_score: float
    novelty_score: float
    composite_rank: float
    ai_interpretation: Optional[str]
    recommended_action: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class RankedSignalResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    source_id: Optional[uuid.UUID]
    title: str
    content_snippet: str
    source_url: str
    verbatim_quote: Optional[str]
    published_at: Optional[datetime]
    business_area: Optional[str]
    development_type: Optional[str]
    opportunity_threat: Literal["opportunity", "threat", "neutral"]
    business_impact_score: float
    urgency_score: float
    credibility_score: float
    relevance_score: float
    composite_rank: float
    ai_interpretation: Optional[str]
    recommended_action: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class RankedSignalListResponse(BaseModel):
    items: list[RankedSignalResponse]
    total: int
    skip: int
    limit: int
