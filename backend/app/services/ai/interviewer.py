"""
Adaptive Interview Service — Phase 3, Module 5.

Orchestrates the 10-question adaptive interview pipeline:
  1. Generate the next question using the local Ollama LLM.
  2. Consider company profile and all previous Q&A when generating.
  3. Detect when a follow-up is needed (vague/short answers).
  4. Update CompanyProfile.assumptions with user-provided context.
  5. Never promote interview answers to verified_facts.

Safety guarantees:
  - Interview answers are stored as user-provided context only.
  - verified_facts in CompanyProfile are never modified by this service.
  - Existing profile fields are preserved when no new information is available.
  - LLM unavailability raises a structured error; no silent fallback.
"""

import json
import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.company import Company, CompanyProfile
from app.models.interview import Interview, InterviewQuestion
from app.services.ai import llm_client

logger = logging.getLogger(__name__)

# Maximum questions per interview session.
MAX_QUESTIONS = 10

# Minimum answer length (chars) before we consider generating a follow-up.
_FOLLOWUP_THRESHOLD = 30

# Task label for audit purposes.
_TASK_TYPE = "adaptive_interview"


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_FIRST_QUESTION_PROMPT = """\
You are conducting a strategic business intelligence interview with the founder \
of "{company_name}" ({website_url}).

Company context:
{profile_context}

Your task: Generate ONE focused, open-ended question to understand this business better.
The question should uncover strategic context that is NOT already in the company profile above.
Focus on: target customers, key pain points solved, competitive advantages, or growth priorities.

Rules:
- Ask exactly ONE question.
- The question must be specific to this company, not generic.
- Do not ask about information already present in the profile context.
- Return ONLY the question text. No preamble, no numbering, no explanation.
"""

_NEXT_QUESTION_PROMPT = """\
You are conducting a strategic business intelligence interview with the founder \
of "{company_name}" ({website_url}).

Company context:
{profile_context}

Interview so far ({answered_count} of {max_questions} questions answered):
{qa_history}

Your task: Generate the NEXT single focused question.
- Build on what has already been revealed.
- Do NOT repeat or rephrase any question already asked.
- Explore a different strategic dimension not yet covered.
- Focus on: {focus_areas}

Rules:
- Ask exactly ONE question.
- Return ONLY the question text. No preamble, no numbering, no explanation.
"""

_FOLLOWUP_PROMPT = """\
You are conducting a strategic business intelligence interview with the founder \
of "{company_name}".

The founder gave this answer to the question:
Question: {question_text}
Answer: {answer_text}

The answer is brief or unclear. Generate ONE concise follow-up question to \
get more specific, actionable detail.

Rules:
- Ask exactly ONE follow-up question.
- Return ONLY the question text. No preamble, no numbering, no explanation.
"""

_PROFILE_UPDATE_PROMPT = """\
You are updating a company intelligence profile for "{company_name}" based on \
interview answers provided directly by the company founder.

Current profile:
{profile_context}

New interview answers (user-provided, NOT externally verified):
{qa_summary}

Extract any new strategic context from the interview answers and return a JSON object.
Only include fields where the interview answers provide genuinely new information \
not already in the current profile.

Return ONLY a valid JSON object with these optional keys (omit keys where no new \
information exists):
{{
  "business_summary_addition": "<additional context to append, or empty string>",
  "new_assumptions": [
    {{"assumption": "<user-stated context>", "confidence": "high", "source": "interview"}}
  ]
}}

Rules:
- new_assumptions must only contain information stated by the founder in the interview.
- Never invent information not present in the interview answers.
- Mark all items with "source": "interview" to distinguish from web-scraped data.
- Return valid JSON only. No markdown, no explanation.
"""

_FOCUS_AREAS = [
    "revenue model and pricing strategy",
    "primary customer acquisition channels",
    "biggest competitive threats",
    "key operational challenges",
    "product roadmap and future plans",
    "team structure and key hires needed",
    "current traction and metrics",
    "strategic partnerships or integrations",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_first_question(company: Company) -> str:
    """
    Generate the opening interview question for a company.

    Raises:
        llm_client.LLMUnavailableError — Ollama unreachable.
        llm_client.LLMResponseError    — Ollama returned unexpected HTTP status.
        InterviewLLMError              — LLM returned empty/unusable output.
    """
    profile_context = _build_profile_context(company)
    prompt = _FIRST_QUESTION_PROMPT.format(
        company_name=company.name,
        website_url=company.website_url,
        profile_context=profile_context,
    )
    return _call_llm_for_question(prompt, company.name, "first question")


def generate_next_question(
    company: Company,
    interview: Interview,
    answered_questions: list[InterviewQuestion],
) -> str:
    """
    Generate the next adaptive question based on prior answers.

    Raises:
        llm_client.LLMUnavailableError — Ollama unreachable.
        InterviewLLMError              — LLM returned empty/unusable output.
    """
    profile_context = _build_profile_context(company)
    qa_history = _build_qa_history(answered_questions)
    answered_count = len([q for q in answered_questions if not q.is_skipped])
    focus_idx = min(answered_count, len(_FOCUS_AREAS) - 1)
    focus_areas = ", ".join(_FOCUS_AREAS[focus_idx:focus_idx + 2])

    prompt = _NEXT_QUESTION_PROMPT.format(
        company_name=company.name,
        website_url=company.website_url,
        profile_context=profile_context,
        answered_count=answered_count,
        max_questions=MAX_QUESTIONS,
        qa_history=qa_history,
        focus_areas=focus_areas,
    )
    return _call_llm_for_question(prompt, company.name, "next question")


def generate_followup_question(
    company: Company,
    question: InterviewQuestion,
) -> str:
    """
    Generate a follow-up question when an answer is too brief or vague.

    Raises:
        llm_client.LLMUnavailableError — Ollama unreachable.
        InterviewLLMError              — LLM returned empty/unusable output.
    """
    prompt = _FOLLOWUP_PROMPT.format(
        company_name=company.name,
        question_text=question.question_text,
        answer_text=question.user_answer or "",
    )
    return _call_llm_for_question(prompt, company.name, "follow-up question")


def needs_followup(answer_text: str) -> bool:
    """Return True if the answer is short enough to warrant a follow-up."""
    return len(answer_text.strip()) < _FOLLOWUP_THRESHOLD


def update_profile_from_interview(
    company: Company,
    answered_questions: list[InterviewQuestion],
    db: Session,
) -> None:
    """
    Update CompanyProfile.assumptions with user-provided interview context.

    Safety rules enforced here:
    - verified_facts are NEVER modified.
    - All new items are tagged with "source": "interview".
    - Existing profile fields are preserved.
    - If LLM fails, the profile is left unchanged (no silent corruption).
    """
    if not answered_questions:
        return

    profile_context = _build_profile_context(company)
    qa_summary = _build_qa_history(answered_questions)

    prompt = _PROFILE_UPDATE_PROMPT.format(
        company_name=company.name,
        profile_context=profile_context,
        qa_summary=qa_summary,
    )

    try:
        raw = llm_client.generate(prompt)
    except llm_client.LLMError as exc:
        logger.warning(
            "LLM unavailable during profile update for '%s': %s — skipping update.",
            company.name, exc,
        )
        return

    parsed = _parse_json(raw)
    if not parsed:
        logger.warning(
            "Could not parse LLM profile update response for '%s' — skipping update.",
            company.name,
        )
        return

    new_assumptions = _ensure_list(parsed.get("new_assumptions"))
    # Enforce source tag on every item — never trust LLM to set it correctly.
    for item in new_assumptions:
        if isinstance(item, dict):
            item["source"] = "interview"

    if not new_assumptions:
        return

    # Merge into existing profile, creating one if needed.
    profile = company.profile
    if profile is None:
        profile = CompanyProfile(company_id=company.id)
        db.add(profile)

    existing = list(profile.assumptions or [])
    # Deduplicate by assumption text.
    existing_texts = {
        str(a.get("assumption", "")).strip().lower()
        for a in existing
        if isinstance(a, dict)
    }
    for item in new_assumptions:
        if isinstance(item, dict):
            text = str(item.get("assumption", "")).strip().lower()
            if text and text not in existing_texts:
                existing.append(item)
                existing_texts.add(text)

    profile.assumptions = existing or None

    try:
        db.commit()
        logger.info(
            "Profile assumptions updated from interview for '%s': %d new items.",
            company.name, len(new_assumptions),
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to persist profile update for '%s': %s", company.name, exc
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_llm_for_question(prompt: str, company_name: str, label: str) -> str:
    """
    Call the LLM and return a clean single-question string.

    Raises InterviewLLMError if the response is empty or unusable.
    """
    raw = llm_client.generate(prompt)
    question = _clean_question(raw)
    if not question:
        raise InterviewLLMError(
            f"LLM returned empty or unusable output for {label} "
            f"(company: {company_name!r})."
        )
    return question


def _clean_question(raw: str) -> str:
    """
    Strip preamble, numbering, and trailing whitespace from LLM output.
    Returns empty string if nothing usable remains.
    """
    text = raw.strip()
    # Remove leading numbering like "1." or "Q1:"
    text = re.sub(r"^(?:Q\s*)?\d+[.):\s]+", "", text, flags=re.IGNORECASE).strip()
    # Remove markdown bold/italic
    text = re.sub(r"\*+", "", text).strip()
    # Collapse internal whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def _build_profile_context(company: Company) -> str:
    """Build a concise text summary of the company profile for prompt injection."""
    parts = [f"Company: {company.name}", f"Website: {company.website_url}"]
    if company.industry:
        parts.append(f"Industry: {company.industry}")

    profile = company.profile
    if profile:
        if profile.business_summary:
            parts.append(f"Summary: {profile.business_summary}")
        if profile.products_services:
            names = [
                p.get("name", "") for p in (profile.products_services or [])
                if isinstance(p, dict)
            ]
            if names:
                parts.append(f"Products/Services: {', '.join(names)}")
        if profile.customer_segments:
            segs = [
                s.get("segment", "") for s in (profile.customer_segments or [])
                if isinstance(s, dict)
            ]
            if segs:
                parts.append(f"Customer segments: {', '.join(segs)}")
        if profile.positioning:
            vp = profile.positioning.get("value_proposition", "")
            if vp:
                parts.append(f"Value proposition: {vp}")

    return "\n".join(parts)


def _build_qa_history(questions: list[InterviewQuestion]) -> str:
    """Format answered/skipped questions as a readable Q&A block."""
    lines = []
    for q in questions:
        if q.is_skipped:
            lines.append(f"Q{q.question_number}: {q.question_text}\nA: [Skipped]")
        elif q.user_answer:
            lines.append(f"Q{q.question_number}: {q.question_text}\nA: {q.user_answer}")
    return "\n\n".join(lines) if lines else "(No answers yet)"


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM output. Returns {} on failure."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}


def _ensure_list(value: Any) -> list:
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class InterviewLLMError(Exception):
    """Raised when the LLM returns empty or unusable output for a question."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
