"""
Unit tests for the Adaptive Interview Engine (Phase 3, Module 5).

All external dependencies are mocked:
  - No real Ollama server required.
  - No real network requests.
  - No database access required for unit tests.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from app.models.company import Company, CompanyProfile
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
from app.services.ai.interviewer import (
    InterviewLLMError,
    MAX_QUESTIONS,
    _build_profile_context,
    _build_qa_history,
    _clean_question,
    _parse_json,
    generate_first_question,
    generate_followup_question,
    generate_next_question,
    needs_followup,
    update_profile_from_interview,
)
from app.services.ai.llm_client import LLMResponseError, LLMUnavailableError


# ---------------------------------------------------------------------------
# Test Fixtures & Mock Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Ensure FastAPI dependency overrides are cleared after each test."""
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_company(deleted: bool = False, profile: CompanyProfile = None) -> Company:
    c = MagicMock(spec=Company)
    c.id = uuid.uuid4()
    c.name = "MeetUniversity"
    c.website_url = "https://www.meetuniversity.com"
    c.industry = "EdTech"
    c.is_deleted = deleted
    c.profile = profile
    return c


def _make_profile(
    business_summary="Leading student study-abroad guidance platform.",
    products=None,
    segments=None,
    value_prop="Personalized university matching",
    verified_facts=None,
    assumptions=None,
) -> CompanyProfile:
    p = MagicMock(spec=CompanyProfile)
    p.id = uuid.uuid4()
    p.business_summary = business_summary
    p.products_services = products or [{"name": "University Search", "description": "Platform"}]
    p.customer_segments = segments or [{"segment": "Prospective Students", "description": "High school grads"}]
    p.positioning = {"value_proposition": value_prop} if value_prop else {}
    p.verified_facts = verified_facts or [
        {"fact": "Founded in 2013", "evidence_text": "Founded in 2013", "source_url": "https://www.meetuniversity.com"}
    ]
    p.assumptions = assumptions or []
    return p


def _make_interview(
    company_id: uuid.UUID,
    status: str = "in_progress",
    current_index: int = 1,
    questions: list = None,
) -> Interview:
    iv = MagicMock(spec=Interview)
    iv.id = uuid.uuid4()
    iv.company_id = company_id
    iv.status = status
    iv.current_question_index = current_index
    iv.started_at = datetime.now(timezone.utc)
    iv.completed_at = None
    iv.questions = questions or []
    return iv


def _make_question(
    interview_id: uuid.UUID,
    question_number: int = 1,
    question_text: str = "What are your top 3 target international destinations?",
    category: str = "business_context",
    user_answer: str = None,
    is_skipped: bool = False,
    is_follow_up: bool = False,
    is_edited: bool = False,
    previous_answers: list = None,
) -> InterviewQuestion:
    q = MagicMock(spec=InterviewQuestion)
    q.id = uuid.uuid4()
    q.interview_id = interview_id
    q.question_number = question_number
    q.question_text = question_text
    q.category = category
    q.user_answer = user_answer
    q.is_skipped = is_skipped
    q.is_follow_up = is_follow_up
    q.is_edited = is_edited
    q.previous_answers = previous_answers
    q.answered_at = datetime.now(timezone.utc) if (user_answer or is_skipped) else None
    q.edited_at = None
    return q


def _make_db(*scalar_returns, scalar_items=None) -> MagicMock:
    """Build a mock SQLAlchemy DB session."""
    db = MagicMock()
    returns = list(scalar_returns)
    call_count = [0]
    added_objects = []

    def _scalar_one_or_none():
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(returns):
            return returns[idx]
        return None

    def _apply_persistence_defaults():
        for obj in added_objects:
            if isinstance(obj, Interview):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                if obj.started_at is None:
                    obj.started_at = datetime.now(timezone.utc)
            elif isinstance(obj, InterviewQuestion):
                if obj.id is None:
                    obj.id = uuid.uuid4()
                if obj.is_skipped is None:
                    obj.is_skipped = False
                if obj.is_follow_up is None:
                    obj.is_follow_up = False
                if obj.is_edited is None:
                    obj.is_edited = False

    db.execute.return_value.scalar_one_or_none.side_effect = _scalar_one_or_none
    db.execute.return_value.scalars.return_value.all.return_value = scalar_items or []
    db.add.side_effect = added_objects.append
    db.flush.side_effect = _apply_persistence_defaults
    db.commit.side_effect = _apply_persistence_defaults
    return db


def _client(db_mock) -> TestClient:
    from app.database import get_db
    from app.main import app
    app.dependency_overrides[get_db] = lambda: db_mock
    return TestClient(app, raise_server_exceptions=False)


# ===========================================================================
# 1. Schema Validation Tests
# ===========================================================================

class TestInterviewSchemas:

    def test_answer_submit_valid(self):
        sub = AnswerSubmit(answer="Our main customers are Indian high school graduates looking for UK universities.")
        assert sub.answer == "Our main customers are Indian high school graduates looking for UK universities."
        assert not sub.skip

    def test_answer_submit_strips_whitespace(self):
        sub = AnswerSubmit(answer="   Detailed response here.   ")
        assert sub.answer == "Detailed response here."

    def test_answer_submit_blank_raises_validation_error(self):
        with pytest.raises(Exception):
            AnswerSubmit(answer="   ", skip=False)

    def test_answer_submit_skip_allows_none(self):
        sub = AnswerSubmit(answer=None, skip=True)
        assert sub.skip is True
        assert sub.answer is None

    def test_answer_edit_valid(self):
        edit = AnswerEdit(answer="Updated strategic priorities.")
        assert edit.answer == "Updated strategic priorities."

    def test_answer_edit_blank_raises_error(self):
        with pytest.raises(Exception):
            AnswerEdit(answer="  ")

    def test_question_response_serialization(self):
        qid = uuid.uuid4()
        ivid = uuid.uuid4()
        resp = QuestionResponse(
            id=qid,
            interview_id=ivid,
            question_number=1,
            question_text="Tell us about your monetization?",
            is_skipped=False,
            is_follow_up=False,
            is_edited=False,
        )
        assert resp.id == qid
        assert resp.question_number == 1
        assert resp.user_answer is None


# ===========================================================================
# 2. Interviewer Service Unit Tests
# ===========================================================================

class TestInterviewerService:

    def test_needs_followup_short_answer(self):
        assert needs_followup("Yes") is True
        assert needs_followup("Students from Asia") is True  # 18 chars < 30
        assert needs_followup("   Short text   ") is True

    def test_needs_followup_long_answer(self):
        long_ans = "We primarily charge institutions an annual subscription fee of $5,000 plus per-lead commission."
        assert needs_followup(long_ans) is False

    def test_clean_question_strips_preamble_and_markdown(self):
        assert _clean_question("1. What is your primary pricing tier?") == "What is your primary pricing tier?"
        assert _clean_question("Q1: Who are your main competitors?") == "Who are your main competitors?"
        assert _clean_question("**What are your goals?**") == "What are your goals?"
        assert _clean_question("   How   do   you   scale?   ") == "How do you scale?"

    def test_build_profile_context(self):
        profile = _make_profile(
            business_summary="EdTech platform.",
            products=[{"name": "App"}, {"name": "Portal"}],
            segments=[{"segment": "Undergrads"}],
            value_prop="Fast admissions",
        )
        company = _make_company(profile=profile)
        ctx = _build_profile_context(company)
        assert "Company: MeetUniversity" in ctx
        assert "EdTech platform" in ctx
        assert "App, Portal" in ctx
        assert "Undergrads" in ctx
        assert "Fast admissions" in ctx

    def test_build_profile_context_none_profile(self):
        company = _make_company(profile=None)
        ctx = _build_profile_context(company)
        assert "Company: MeetUniversity" in ctx
        assert "Summary" not in ctx

    def test_build_qa_history(self):
        q1 = _make_question(uuid.uuid4(), 1, "Question 1?", user_answer="Answer 1")
        q2 = _make_question(uuid.uuid4(), 2, "Question 2?", is_skipped=True)
        history = _build_qa_history([q1, q2])
        assert "Q1: Question 1?\nA: Answer 1" in history
        assert "Q2: Question 2?\nA: [Skipped]" in history

    def test_build_qa_history_empty(self):
        assert _build_qa_history([]) == "(No answers yet)"

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_generate_first_question_success(self, mock_gen):
        mock_gen.return_value = "What is your most important strategic metric for this quarter?"
        company = _make_company()
        q = generate_first_question(company)
        assert q == "What is your most important strategic metric for this quarter?"
        assert mock_gen.called

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_generate_first_question_llm_unavailable(self, mock_gen):
        mock_gen.side_effect = LLMUnavailableError("Ollama down")
        company = _make_company()
        with pytest.raises(LLMUnavailableError):
            generate_first_question(company)

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_generate_first_question_empty_output_raises_error(self, mock_gen):
        mock_gen.return_value = "   "
        company = _make_company()
        with pytest.raises(InterviewLLMError):
            generate_first_question(company)

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_generate_next_question_success(self, mock_gen):
        mock_gen.return_value = "How do you handle student lead conversion?"
        company = _make_company()
        iv = _make_interview(company.id)
        q1 = _make_question(iv.id, 1, "Q1?", user_answer="A1")
        next_q = generate_next_question(company, iv, [q1])
        assert next_q == "How do you handle student lead conversion?"

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_generate_followup_question_success(self, mock_gen):
        mock_gen.return_value = "Could you specify which universities you have direct partnerships with?"
        company = _make_company()
        q = _make_question(uuid.uuid4(), 1, "Partners?", user_answer="UK schools")
        fup = generate_followup_question(company, q)
        assert fup == "Could you specify which universities you have direct partnerships with?"

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_update_profile_from_interview_adds_assumptions(self, mock_gen):
        mock_gen.return_value = json.dumps({
            "new_assumptions": [
                {"assumption": "Planning expansion to Canada in 2027", "confidence": "high"}
            ]
        })
        profile = _make_profile(assumptions=[{"assumption": "Existing assumption", "source": "research"}])
        company = _make_company(profile=profile)
        db = MagicMock()
        q = _make_question(uuid.uuid4(), 1, "Expansion?", user_answer="We plan to expand to Canada in 2027.")

        update_profile_from_interview(company, [q], db)

        assert db.commit.called
        # Check that verified_facts was NEVER touched
        assert len(profile.verified_facts) == 1
        # Check that assumptions were updated with interview source
        assert len(profile.assumptions) == 2
        new_item = profile.assumptions[-1]
        assert new_item["assumption"] == "Planning expansion to Canada in 2027"
        assert new_item["source"] == "interview"

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_update_profile_from_interview_deduplicates(self, mock_gen):
        mock_gen.return_value = json.dumps({
            "new_assumptions": [
                {"assumption": "Canada expansion in 2027", "confidence": "high"}
            ]
        })
        profile = _make_profile(assumptions=[{"assumption": "Canada expansion in 2027", "source": "interview"}])
        company = _make_company(profile=profile)
        db = MagicMock()
        q = _make_question(uuid.uuid4(), 1, "Expansion?", user_answer="Canada expansion in 2027.")

        update_profile_from_interview(company, [q], db)
        assert len(profile.assumptions) == 1  # No duplicate added

    @patch("app.services.ai.interviewer.llm_client.generate")
    def test_update_profile_llm_error_fails_safely(self, mock_gen):
        mock_gen.side_effect = LLMUnavailableError("Ollama disconnected")
        profile = _make_profile(assumptions=[])
        company = _make_company(profile=profile)
        db = MagicMock()
        q = _make_question(uuid.uuid4(), 1, "Q?", user_answer="Answer.")

        # Should log warning and return without raising exception or modifying profile
        update_profile_from_interview(company, [q], db)
        assert profile.assumptions == []
        assert not db.commit.called


# ===========================================================================
# 3. Start Interview API Endpoint Tests
# ===========================================================================

class TestStartInterviewEndpoint:

    @patch("app.services.ai.interviewer.generate_first_question")
    def test_start_interview_success_201(self, mock_gen):
        mock_gen.return_value = "What is your core business model?"
        company = _make_company()
        # db returns company, then existing active interview -> None
        db = _make_db(company, None)

        def _refresh(obj):
            if isinstance(obj, Interview):
                obj.questions = [obj.questions[0]] if hasattr(obj, "questions") and obj.questions else []

        db.refresh.side_effect = _refresh

        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/start")
        assert resp.status_code == 201
        data = resp.json()
        assert "interview" in data
        assert "current_question" in data
        assert data["interview"]["status"] == "in_progress"
        assert data["interview"]["current_question_index"] == 1
        assert data["current_question"]["question_text"] == "What is your core business model?"
        assert db.commit.called

    def test_start_interview_company_not_found_404(self):
        db = _make_db(None)
        resp = _client(db).post(f"/api/v1/companies/{uuid.uuid4()}/interview/start")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_start_interview_company_soft_deleted_404(self):
        # Company exists but is_deleted = True -> _get_active_company returns None
        db = _make_db(None)
        resp = _client(db).post(f"/api/v1/companies/{uuid.uuid4()}/interview/start")
        assert resp.status_code == 404

    def test_start_interview_active_conflict_409(self):
        company = _make_company()
        existing_active = _make_interview(company.id, status="in_progress")
        # db returns company, then existing active interview -> existing_active
        db = _make_db(company, existing_active)

        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/start")
        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"].lower()

    @patch("app.services.ai.interviewer.generate_first_question")
    def test_start_interview_llm_unavailable_503(self, mock_gen):
        mock_gen.side_effect = LLMUnavailableError("Connection refused")
        company = _make_company()
        db = _make_db(company, None)

        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/start")
        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()

    @patch("app.services.ai.interviewer.generate_first_question")
    def test_start_interview_llm_invalid_response_422(self, mock_gen):
        mock_gen.side_effect = InterviewLLMError("Empty response")
        company = _make_company()
        db = _make_db(company, None)

        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/start")
        assert resp.status_code == 422
        assert "unusable response" in resp.json()["detail"].lower()


# ===========================================================================
# 4. Get Active Interview API Endpoint Tests
# ===========================================================================

class TestGetActiveInterviewEndpoint:

    def test_get_active_interview_success(self):
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=1)
        q1 = _make_question(iv.id, 1, "First question?")
        iv.questions = [q1]

        # db returns company, then active interview -> iv
        db = _make_db(company, iv)

        resp = _client(db).get(f"/api/v1/companies/{company.id}/interview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "in_progress"
        assert data["current_question_index"] == 1
        assert data["questions_answered"] == 0
        assert data["questions_remaining"] == 10
        assert data["current_question"]["question_text"] == "First question?"
        assert data["is_complete"] is False

    def test_get_active_interview_not_found_404(self):
        company = _make_company()
        # db returns company, then active interview -> None
        db = _make_db(company, None)

        resp = _client(db).get(f"/api/v1/companies/{company.id}/interview")
        assert resp.status_code == 404
        assert "no active interview" in resp.json()["detail"].lower()

    def test_get_active_interview_company_not_found_404(self):
        db = _make_db(None)
        resp = _client(db).get(f"/api/v1/companies/{uuid.uuid4()}/interview")
        assert resp.status_code == 404


# ===========================================================================
# 5. Get Specific Interview API Endpoint Tests
# ===========================================================================

class TestGetInterviewEndpoint:

    def test_get_interview_by_id_success(self):
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=2)
        q1 = _make_question(iv.id, 1, "Q1?", user_answer="A1")
        q2 = _make_question(iv.id, 2, "Q2?")
        iv.questions = [q1, q2]

        db = _make_db(company, iv)
        resp = _client(db).get(f"/api/v1/companies/{company.id}/interview/{iv.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(iv.id)
        assert len(data["questions"]) == 2
        assert data["questions"][0]["user_answer"] == "A1"

    def test_get_interview_not_found_404(self):
        company = _make_company()
        db = _make_db(company, None)
        resp = _client(db).get(f"/api/v1/companies/{company.id}/interview/{uuid.uuid4()}")
        assert resp.status_code == 404


# ===========================================================================
# 6. Submit Answer Endpoint Tests
# ===========================================================================

class TestSubmitAnswerEndpoint:

    @patch("app.services.ai.interviewer.update_profile_from_interview")
    @patch("app.services.ai.interviewer.generate_next_question")
    def test_submit_answer_normal_advances_to_next_question(self, mock_next, mock_update):
        mock_next.return_value = "What are your primary acquisition channels?"
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=1)
        q1 = _make_question(iv.id, 1, "What is your main product?")
        iv.questions = [q1]

        db = _make_db(company, iv)

        payload = {"answer": "We provide an end-to-end AI platform for study-abroad guidance and admissions.", "skip": False}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["question"]["user_answer"] == payload["answer"]
        assert data["question"]["is_skipped"] is False
        assert data["next_question"]["question_text"] == "What are your primary acquisition channels?"
        assert data["next_question"]["question_number"] == 2
        assert data["is_complete"] is False
        assert db.commit.called

    @patch("app.services.ai.interviewer.generate_followup_question")
    def test_submit_answer_short_triggers_followup(self, mock_fup):
        mock_fup.return_value = "Could you elaborate on how your admissions guidance works?"
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=1)
        q1 = _make_question(iv.id, 1, "What is your main product?", is_follow_up=False)
        iv.questions = [q1]

        db = _make_db(company, iv)

        # Short answer (< 30 chars) -> triggers follow-up
        payload = {"answer": "Admissions guidance.", "skip": False}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["next_question"]["is_follow_up"] is True
        assert data["next_question"]["question_text"] == "Could you elaborate on how your admissions guidance works?"

    @patch("app.services.ai.interviewer.generate_next_question")
    def test_submit_answer_skip_confidential(self, mock_next):
        mock_next.return_value = "What is your customer retention strategy?"
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=1)
        q1 = _make_question(iv.id, 1, "What is your exact revenue breakdown?")
        iv.questions = [q1]

        db = _make_db(company, iv)

        payload = {"skip": True}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["question"]["is_skipped"] is True
        assert data["question"]["user_answer"] is None
        assert data["next_question"]["question_text"] == "What is your customer retention strategy?"

    @patch("app.services.ai.interviewer.update_profile_from_interview")
    def test_submit_tenth_question_completes_interview(self, mock_update):
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=10)
        # 9 already answered
        existing_qs = [
            _make_question(iv.id, i, f"Q{i}?", user_answer=f"Detailed Answer {i} with sufficient length.")
            for i in range(1, 10)
        ]
        q10 = _make_question(iv.id, 10, "Final question on future vision?")
        iv.questions = existing_qs + [q10]

        db = _make_db(company, iv)

        payload = {"answer": "Our vision is to be the global operating system for international student mobility.", "skip": False}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["interview_status"] == "completed"
        assert data["is_complete"] is True
        assert data["next_question"] is None
        assert iv.status == "completed"
        assert iv.completed_at is not None

    def test_submit_answer_already_completed_conflict_409(self):
        company = _make_company()
        iv = _make_interview(company.id, status="completed", current_index=10)
        db = _make_db(company, iv)

        payload = {"answer": "Another answer."}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 409
        assert "completed" in resp.json()["detail"].lower()

    def test_submit_answer_no_unanswered_question_conflict_409(self):
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress")
        q1 = _make_question(iv.id, 1, "Q1?", user_answer="Already answered.")
        iv.questions = [q1]
        db = _make_db(company, iv)

        payload = {"answer": "Another answer."}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 409
        assert "no unanswered question" in resp.json()["detail"].lower()

    @patch("app.services.ai.interviewer.generate_next_question")
    def test_submit_answer_llm_unavailable_503(self, mock_next):
        mock_next.side_effect = LLMUnavailableError("Ollama connection timed out")
        company = _make_company()
        iv = _make_interview(company.id, status="in_progress", current_index=1)
        q1 = _make_question(iv.id, 1, "Q1?")
        iv.questions = [q1]

        db = _make_db(company, iv)

        payload = {"answer": "Detailed answer exceeding the thirty-character minimum threshold.", "skip": False}
        resp = _client(db).post(f"/api/v1/companies/{company.id}/interview/{iv.id}/answer", json=payload)
        assert resp.status_code == 503
        assert db.rollback.called


# ===========================================================================
# 7. Edit Answer Endpoint Tests
# ===========================================================================

class TestEditAnswerEndpoint:

    def test_edit_answer_success_preserves_history(self):
        company = _make_company()
        iv = _make_interview(company.id)
        original_answer = "Initial answer from first submission."
        q1 = _make_question(
            iv.id, 1, "What are your key metrics?",
            user_answer=original_answer,
            previous_answers=None,
        )
        iv.questions = [q1]

        db = _make_db(company, iv)

        payload = {"answer": "Updated answer: We reached 2,500 active partner universities."}
        resp = _client(db).patch(
            f"/api/v1/companies/{company.id}/interview/{iv.id}/questions/{q1.id}",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_answer"] == payload["answer"]
        assert data["is_edited"] is True
        assert data["previous_answers"] is not None
        assert len(data["previous_answers"]) == 1
        assert data["previous_answers"][0]["answer"] == original_answer
        assert db.commit.called

    def test_edit_previously_skipped_question_unskips(self):
        company = _make_company()
        iv = _make_interview(company.id)
        q1 = _make_question(iv.id, 1, "Revenue question?", is_skipped=True, user_answer=None)
        iv.questions = [q1]

        db = _make_db(company, iv)

        payload = {"answer": "We are now ready to disclose: $1.2M ARR."}
        resp = _client(db).patch(
            f"/api/v1/companies/{company.id}/interview/{iv.id}/questions/{q1.id}",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_skipped"] is False
        assert data["is_edited"] is True
        assert data["user_answer"] == payload["answer"]

    def test_edit_unanswered_question_conflict_409(self):
        company = _make_company()
        iv = _make_interview(company.id)
        # Question not yet answered or skipped
        q1 = _make_question(iv.id, 1, "Pending question?", user_answer=None, is_skipped=False)
        iv.questions = [q1]

        db = _make_db(company, iv)

        payload = {"answer": "Attempting to edit before answering."}
        resp = _client(db).patch(
            f"/api/v1/companies/{company.id}/interview/{iv.id}/questions/{q1.id}",
            json=payload,
        )
        assert resp.status_code == 409
        assert "has not been answered yet" in resp.json()["detail"].lower()

    def test_edit_question_not_in_interview_404(self):
        company = _make_company()
        iv = _make_interview(company.id)
        iv.questions = []  # No questions in interview
        db = _make_db(company, iv)

        payload = {"answer": "Answer for missing question."}
        resp = _client(db).patch(
            f"/api/v1/companies/{company.id}/interview/{iv.id}/questions/{uuid.uuid4()}",
            json=payload,
        )
        assert resp.status_code == 404
        assert "not found in this interview" in resp.json()["detail"].lower()


# ===========================================================================
# 8. List Interviews Endpoint Tests
# ===========================================================================

class TestListInterviewsEndpoint:

    def test_list_interviews_success(self):
        company = _make_company()
        iv1 = _make_interview(company.id, status="completed", current_index=10)
        iv2 = _make_interview(company.id, status="in_progress", current_index=3)

        db = _make_db(company, scalar_items=[iv1, iv2])

        resp = _client(db).get(f"/api/v1/companies/{company.id}/interviews?skip=0&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["status"] == "completed"
        assert data[1]["status"] == "in_progress"

    def test_list_interviews_company_not_found_404(self):
        db = _make_db(None)
        resp = _client(db).get(f"/api/v1/companies/{uuid.uuid4()}/interviews")
        assert resp.status_code == 404
