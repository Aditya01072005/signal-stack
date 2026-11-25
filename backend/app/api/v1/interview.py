"""
Adaptive Interview API — Phase 3, Module 5.

Endpoints:
  POST  /api/v1/companies/{company_id}/interview/start
  GET   /api/v1/companies/{company_id}/interview
  GET   /api/v1/companies/{company_id}/interview/{interview_id}
  POST  /api/v1/companies/{company_id}/interview/{interview_id}/answer
  PATCH /api/v1/companies/{company_id}/interview/{interview_id}/questions/{question_id}
  GET   /api/v1/companies/{company_id}/interviews

Design notes:
  - One active (in_progress) interview per company at a time.
  - Questions are generated one at a time by the local Ollama LLM.
  - Answers are user-provided context; they NEVER become verified_facts.
  - Profile assumptions are updated after each answered question.
  - Skipped questions are recorded with is_skipped=True; no answer stored.
  - Edit history is preserved in previous_answers (JSONB).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.interview import Interview, InterviewQuestion
from app.schemas.interview import (
    AnswerEdit,
    AnswerResponse,
    AnswerSubmit,
    InterviewResponse,
    InterviewStartResponse,
    NextQuestionResponse,
    QuestionResponse,
)
from app.services.ai import interviewer
from app.services.ai.interviewer import InterviewLLMError, MAX_QUESTIONS
from app.services.ai.llm_client import LLMUnavailableError, LLMResponseError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Interview"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_active_company(company_id: uuid.UUID, db: Session) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    company = db.execute(stmt).scalar_one_or_none()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )
    return company


def _get_interview(
    interview_id: uuid.UUID, company_id: uuid.UUID, db: Session
) -> Interview:
    stmt = select(Interview).where(
        Interview.id == interview_id,
        Interview.company_id == company_id,
    )
    interview = db.execute(stmt).scalar_one_or_none()
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview '{interview_id}' not found for this company.",
        )
    return interview


def _get_active_interview(company_id: uuid.UUID, db: Session) -> Optional[Interview]:
    stmt = select(Interview).where(
        Interview.company_id == company_id,
        Interview.status == "in_progress",
    )
    return db.execute(stmt).scalar_one_or_none()


def _to_question_response(q: InterviewQuestion) -> QuestionResponse:
    return QuestionResponse(
        id=q.id,
        interview_id=q.interview_id,
        question_number=q.question_number,
        category=q.category,
        question_text=q.question_text,
        user_answer=q.user_answer,
        is_skipped=q.is_skipped,
        is_follow_up=q.is_follow_up,
        is_edited=q.is_edited,
        previous_answers=q.previous_answers,
        answered_at=q.answered_at,
        edited_at=q.edited_at,
    )


def _to_interview_response(iv: Interview) -> InterviewResponse:
    return InterviewResponse(
        id=iv.id,
        company_id=iv.company_id,
        status=iv.status,
        current_question_index=iv.current_question_index,
        started_at=iv.started_at,
        completed_at=iv.completed_at,
        questions=[_to_question_response(q) for q in iv.questions],
    )


def _answered_questions(interview: Interview) -> list[InterviewQuestion]:
    """Return questions that have been answered or skipped (not pending)."""
    return [
        q for q in interview.questions
        if q.user_answer is not None or q.is_skipped
    ]


def _current_unanswered(interview: Interview) -> Optional[InterviewQuestion]:
    """Return the most recently generated but not yet answered question."""
    for q in reversed(interview.questions):
        if q.user_answer is None and not q.is_skipped:
            return q
    return None


def _handle_llm_error(exc: Exception, context: str) -> HTTPException:
    """Map LLM errors to appropriate HTTP responses without leaking internals."""
    if isinstance(exc, (LLMUnavailableError,)):
        logger.error("Ollama unavailable during %s: %s", context, exc)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is currently unavailable. Please try again later.",
        )
    if isinstance(exc, InterviewLLMError):
        logger.warning("LLM returned unusable output during %s: %s", context, exc)
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The AI returned an unusable response. Please try again.",
        )
    logger.error("Unexpected error during %s: %s", context, exc)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred.",
    )


# ---------------------------------------------------------------------------
# POST /companies/{company_id}/interview/start
# ---------------------------------------------------------------------------

@router.post(
    "/{company_id}/interview/start",
    response_model=InterviewStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new adaptive interview",
    description=(
        "Creates a new interview session and generates the first question. "
        "Only one active interview per company is allowed at a time."
    ),
)
def start_interview(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> InterviewStartResponse:
    company = _get_active_company(company_id, db)

    # Prevent duplicate active interviews.
    existing = _get_active_interview(company_id, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An interview is already in progress (id={existing.id}). "
                "Complete or retrieve it before starting a new one."
            ),
        )

    # Generate first question via LLM.
    try:
        question_text = interviewer.generate_first_question(company)
    except (LLMUnavailableError, LLMResponseError, InterviewLLMError) as exc:
        raise _handle_llm_error(exc, "start_interview")

    # Persist interview + first question.
    interview = Interview(
        company_id=company_id,
        status="in_progress",
        current_question_index=1,
    )
    db.add(interview)
    db.flush()  # get interview.id before creating question

    first_q = InterviewQuestion(
        interview_id=interview.id,
        question_number=1,
        category="business_context",
        question_text=question_text,
    )
    db.add(first_q)

    try:
        db.commit()
        db.refresh(interview)
        db.refresh(first_q)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist new interview: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create interview.",
        )

    return InterviewStartResponse(
        interview=_to_interview_response(interview),
        current_question=_to_question_response(first_q),
    )


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/interview  (active interview)
# ---------------------------------------------------------------------------

@router.get(
    "/{company_id}/interview",
    response_model=NextQuestionResponse,
    summary="Get the active interview and current question",
)
def get_active_interview(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> NextQuestionResponse:
    _get_active_company(company_id, db)
    interview = _get_active_interview(company_id, db)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active interview found for this company.",
        )
    return _build_next_question_response(interview)


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/interview/{interview_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{company_id}/interview/{interview_id}",
    response_model=InterviewResponse,
    summary="Retrieve a specific interview with all questions",
)
def get_interview(
    company_id: uuid.UUID,
    interview_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> InterviewResponse:
    _get_active_company(company_id, db)
    interview = _get_interview(interview_id, company_id, db)
    return _to_interview_response(interview)


# ---------------------------------------------------------------------------
# POST /companies/{company_id}/interview/{interview_id}/answer
# ---------------------------------------------------------------------------

@router.post(
    "/{company_id}/interview/{interview_id}/answer",
    response_model=AnswerResponse,
    summary="Submit an answer or skip the current question",
)
def submit_answer(
    company_id: uuid.UUID,
    interview_id: uuid.UUID,
    payload: AnswerSubmit,
    db: Session = Depends(get_db),
) -> AnswerResponse:
    company = _get_active_company(company_id, db)
    interview = _get_interview(interview_id, company_id, db)

    if interview.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview is already '{interview.status}' and cannot accept new answers.",
        )

    current_q = _current_unanswered(interview)
    if current_q is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No unanswered question found. The interview may already be complete.",
        )

    now = datetime.now(timezone.utc)
    is_skip = payload.skip or (payload.answer is None)

    if is_skip:
        current_q.is_skipped = True
        current_q.answered_at = now
    else:
        current_q.user_answer = payload.answer
        current_q.answered_at = now

    answered = _answered_questions(interview)
    # Include the question we just answered/skipped.
    if current_q not in answered:
        answered.append(current_q)

    profile_updated = False
    next_q_obj: Optional[InterviewQuestion] = None
    is_complete = False

    total_done = len(answered)

    # Decide: follow-up, next question, or complete.
    if (
        not is_skip
        and interviewer.needs_followup(payload.answer or "")
        and not current_q.is_follow_up
        and total_done < MAX_QUESTIONS
    ):
        # Generate a follow-up question.
        try:
            followup_text = interviewer.generate_followup_question(company, current_q)
        except (LLMUnavailableError, LLMResponseError, InterviewLLMError) as exc:
            db.rollback()
            raise _handle_llm_error(exc, "generate_followup")

        next_q_obj = InterviewQuestion(
            interview_id=interview.id,
            question_number=current_q.question_number + 1,
            category=current_q.category,
            question_text=followup_text,
            is_follow_up=True,
        )
        db.add(next_q_obj)
        interview.current_question_index = next_q_obj.question_number

    elif total_done < MAX_QUESTIONS:
        # Generate the next adaptive question.
        try:
            next_text = interviewer.generate_next_question(company, interview, answered)
        except (LLMUnavailableError, LLMResponseError, InterviewLLMError) as exc:
            db.rollback()
            raise _handle_llm_error(exc, "generate_next_question")

        next_q_obj = InterviewQuestion(
            interview_id=interview.id,
            question_number=total_done + 1,
            category="business_context",
            question_text=next_text,
        )
        db.add(next_q_obj)
        interview.current_question_index = next_q_obj.question_number

    else:
        # Interview complete.
        interview.status = "completed"
        interview.completed_at = now
        is_complete = True

    # Update profile assumptions from answered (non-skipped) questions.
    real_answers = [q for q in answered if not q.is_skipped and q.user_answer]
    if real_answers:
        try:
            interviewer.update_profile_from_interview(company, real_answers, db)
            profile_updated = True
        except Exception as exc:
            # Profile update failure must not abort the answer submission.
            logger.warning("Profile update failed after answer submission: %s", exc)

    try:
        db.commit()
        db.refresh(current_q)
        if next_q_obj:
            db.refresh(next_q_obj)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist answer: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save answer.",
        )

    return AnswerResponse(
        question=_to_question_response(current_q),
        interview_status=interview.status,
        next_question=_to_question_response(next_q_obj) if next_q_obj else None,
        profile_updated=profile_updated,
        is_complete=is_complete,
    )


# ---------------------------------------------------------------------------
# PATCH /companies/{company_id}/interview/{interview_id}/questions/{question_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/{company_id}/interview/{interview_id}/questions/{question_id}",
    response_model=QuestionResponse,
    summary="Edit a previously submitted answer",
)
def edit_answer(
    company_id: uuid.UUID,
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: AnswerEdit,
    db: Session = Depends(get_db),
) -> QuestionResponse:
    _get_active_company(company_id, db)
    interview = _get_interview(interview_id, company_id, db)

    # Find the question within this interview.
    question = next(
        (q for q in interview.questions if q.id == question_id), None
    )
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question '{question_id}' not found in this interview.",
        )

    if question.user_answer is None and not question.is_skipped:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit a question that has not been answered yet.",
        )

    now = datetime.now(timezone.utc)

    # Preserve edit history in previous_answers.
    history = list(question.previous_answers or [])
    if question.user_answer is not None:
        history.append({
            "answer": question.user_answer,
            "answered_at": question.answered_at.isoformat() if question.answered_at else None,
            "edited_at": question.edited_at.isoformat() if question.edited_at else None,
        })

    question.previous_answers = history or None
    question.user_answer = payload.answer
    question.is_skipped = False  # editing un-skips a previously skipped question
    question.is_edited = True
    question.edited_at = now

    try:
        db.commit()
        db.refresh(question)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to edit answer for question %s: %s", question_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save edited answer.",
        )

    return _to_question_response(question)


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/interviews  (history)
# ---------------------------------------------------------------------------

@router.get(
    "/{company_id}/interviews",
    response_model=list[InterviewResponse],
    summary="List all interviews for a company",
)
def list_interviews(
    company_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[InterviewResponse]:
    _get_active_company(company_id, db)
    stmt = (
        select(Interview)
        .where(Interview.company_id == company_id)
        .order_by(Interview.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    interviews = list(db.execute(stmt).scalars().all())
    return [_to_interview_response(iv) for iv in interviews]


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _build_next_question_response(interview: Interview) -> NextQuestionResponse:
    answered = _answered_questions(interview)
    current_q = _current_unanswered(interview)
    is_complete = interview.status == "completed"
    questions_remaining = MAX_QUESTIONS - len(answered)

    return NextQuestionResponse(
        interview_id=interview.id,
        status=interview.status,
        current_question_index=interview.current_question_index,
        questions_answered=len(answered),
        questions_remaining=max(0, questions_remaining),
        current_question=_to_question_response(current_q) if current_q else None,
        is_complete=is_complete,
    )
