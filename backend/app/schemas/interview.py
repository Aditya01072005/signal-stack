"""
Pydantic schemas for the Adaptive Interview endpoints.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AnswerSubmit(BaseModel):
    """Payload for submitting or skipping an answer."""
    answer: Optional[str] = Field(
        None,
        description="The answer text. Omit or set null to skip the question.",
    )
    skip: bool = Field(
        False,
        description="Set true to mark this question as skipped (e.g. confidential).",
    )

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Answer text cannot be blank. Use skip=true to skip.")
            return stripped
        return v


class AnswerEdit(BaseModel):
    """Payload for editing a previously submitted answer."""
    answer: str = Field(..., description="The revised answer text.")

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Revised answer cannot be blank.")
        return stripped


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class QuestionResponse(BaseModel):
    """A single interview question."""
    id: uuid.UUID
    interview_id: uuid.UUID
    question_number: int
    category: Optional[str] = None
    question_text: str
    user_answer: Optional[str] = None
    is_skipped: bool
    is_follow_up: bool
    is_edited: bool
    previous_answers: Optional[list[dict[str, Any]]] = None
    answered_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InterviewResponse(BaseModel):
    """Full interview record with all questions."""
    id: uuid.UUID
    company_id: uuid.UUID
    status: str
    current_question_index: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    questions: list[QuestionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class InterviewStartResponse(BaseModel):
    """Response when starting a new interview — includes the first question."""
    interview: InterviewResponse
    current_question: QuestionResponse


class NextQuestionResponse(BaseModel):
    """Response when fetching the current/next question."""
    interview_id: uuid.UUID
    status: str
    current_question_index: int
    questions_answered: int
    questions_remaining: int
    current_question: Optional[QuestionResponse] = None
    is_complete: bool


class AnswerResponse(BaseModel):
    """Response after submitting or editing an answer."""
    question: QuestionResponse
    interview_status: str
    next_question: Optional[QuestionResponse] = None
    profile_updated: bool = False
    is_complete: bool = False
