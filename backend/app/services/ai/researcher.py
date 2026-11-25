"""
Company Research Service.

Orchestrates the initial automated research pipeline:
  1. Scrape the company's public website via EthicalScraper.
  2. Send cleaned text to the local Ollama LLM with a structured extraction prompt.
  3. Parse and validate the JSON response.
  4. Validate every proposed verified fact against the actual scraped text.
  5. Persist the CompanyProfile ONLY on full success.
  6. Write one AuditLog entry recording outcome, duration, and previous profile snapshot.

Safety guarantees:
  - An existing valid CompanyProfile is NEVER modified on any failure path.
  - A new empty CompanyProfile is NEVER created on any failure path.
  - All scraper security checks (SSRF, robots.txt, politeness) are preserved.
  - The LLM runs locally via Ollama — no external API calls, no paid services.
"""

import logging
import re
import time
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.company import Company, CompanyProfile
from app.services.ai import llm_client
from app.services.crawler.scraper import (
    EthicalScraper,
    ScraperError,
    ScrapeResult,
    SSRFBlockedError,
    RobotsBlockedError,
    RobotsUnavailableError,
)

logger = logging.getLogger(__name__)

# Task type label written to audit_logs.task_type
_TASK_TYPE = "company_research"

# Minimum character overlap required for a fact's evidence_text to be
# considered present in the scraped content (after whitespace normalisation).
_MIN_EVIDENCE_LENGTH = 10


# ---------------------------------------------------------------------------
# Structured result
# ---------------------------------------------------------------------------

@dataclass
class ResearchResult:
    """
    Structured output from the initial company research pipeline.

    scrape_status values:
      "success"           — full pipeline completed, profile written.
      "scrape_failed"     — network/timeout/HTTP error during scraping.
      "scrape_blocked"    — SSRF protection or robots.txt blocked the URL.
      "llm_unavailable"   — Ollama could not be reached.
      "llm_invalid_output"— LLM responded but JSON was unparseable or empty.

    verified_facts contains only facts whose evidence_text was found verbatim
    (whitespace-normalised) in the scraped content.
    """
    company_id: str
    company_name: str
    website_url: str
    business_summary: str
    products_services: list[dict[str, Any]] = field(default_factory=list)
    customer_segments: list[dict[str, Any]] = field(default_factory=list)
    positioning: dict[str, Any] = field(default_factory=dict)
    verified_facts: list[dict[str, Any]] = field(default_factory=list)
    facts_excluded: int = 0          # facts proposed by LLM but rejected by evidence check
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    scrape_status: str = "success"
    scrape_error: str | None = None
    raw_llm_response: str | None = None   # retained for debugging only


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_RESEARCH_PROMPT_TEMPLATE = """\
You are a business intelligence analyst. Analyze the following website content \
for the company "{company_name}" ({website_url}) and extract structured information.

WEBSITE CONTENT:
{content}

---

Return ONLY a valid JSON object with exactly these keys. Do not include any text \
before or after the JSON block.

{{
  "business_summary": "<2-3 sentence plain-English description of what the company does>",
  "products_services": [
    {{"name": "<product or service name>", "description": "<brief description>"}}
  ],
  "customer_segments": [
    {{"segment": "<target customer type>", "description": "<why they are targeted>"}}
  ],
  "positioning": {{
    "value_proposition": "<core value proposition>",
    "differentiators": ["<differentiator 1>", "<differentiator 2>"]
  }},
  "verified_facts": [
    {{
      "fact": "<directly stated fact from the website>",
      "evidence_text": "<verbatim or near-verbatim excerpt from the website content above that supports this fact>",
      "source_url": "{website_url}"
    }}
  ],
  "assumptions": [
    {{"assumption": "<inferred detail NOT explicitly stated on the website>", "confidence": "low|medium|high"}}
  ]
}}

Rules:
- verified_facts must only contain information explicitly stated on the website.
- evidence_text must be a verbatim or near-verbatim excerpt copied from the WEBSITE CONTENT above.
- assumptions must only contain inferences not directly stated; never repeat verified facts here.
- If information is not available, use an empty list [] or empty string "".
- Return valid JSON only. No markdown, no code fences, no explanation.
"""


# ---------------------------------------------------------------------------
# Core research function
# ---------------------------------------------------------------------------

def research_company(company: Company, db: Session) -> ResearchResult:
    """
    Run the full research pipeline for a company.

    The CompanyProfile is written ONLY when all of the following succeed:
      - Scraping returns non-empty content.
      - LLM responds successfully.
      - JSON parses to a non-empty dict.

    On any failure the existing profile is left completely unchanged.
    One AuditLog entry is always written (success or failure).
    """
    started_at = time.monotonic()

    result = ResearchResult(
        company_id=str(company.id),
        company_name=company.name,
        website_url=company.website_url,
        business_summary="",
    )

    # --- Step 1: Scrape ---
    scrape_result, scrape_error_msg, scrape_status = _scrape_website(company.website_url)

    if scrape_result is None:
        result.scrape_status = scrape_status
        result.scrape_error = scrape_error_msg
        _write_audit(company, result, started_at, db)
        return result

    content = scrape_result.clean_text.strip()
    if not content:
        result.scrape_status = "scrape_failed"
        result.scrape_error = "Scraped page returned no readable text."
        _write_audit(company, result, started_at, db)
        return result

    source_url = scrape_result.final_url

    # --- Step 2: LLM extraction ---
    prompt = _RESEARCH_PROMPT_TEMPLATE.format(
        company_name=company.name,
        website_url=source_url,
        content=content,
    )

    try:
        raw_response = llm_client.generate(prompt)
    except llm_client.LLMUnavailableError as exc:
        logger.error("Ollama unavailable for company '%s': %s", company.name, exc)
        result.scrape_status = "llm_unavailable"
        result.scrape_error = str(exc)
        _write_audit(company, result, started_at, db)
        return result
    except llm_client.LLMError as exc:
        logger.error("LLM error for company '%s': %s", company.name, exc)
        result.scrape_status = "llm_unavailable"
        result.scrape_error = str(exc)
        _write_audit(company, result, started_at, db)
        return result

    result.raw_llm_response = raw_response

    # --- Step 3: Parse JSON ---
    parsed = _parse_llm_json(raw_response)
    if not parsed:
        result.scrape_status = "llm_invalid_output"
        result.scrape_error = "LLM response could not be parsed as JSON."
        _write_audit(company, result, started_at, db)
        return result

    # --- Step 4: Populate result fields ---
    result.business_summary = parsed.get("business_summary", "")
    result.products_services = _ensure_list(parsed.get("products_services"))
    result.customer_segments = _ensure_list(parsed.get("customer_segments"))
    result.positioning = parsed.get("positioning") or {}
    result.assumptions = _ensure_list(parsed.get("assumptions"))

    # --- Step 5: Evidence-validate verified facts ---
    proposed_facts = _ensure_list(parsed.get("verified_facts"))
    validated, excluded = _validate_facts(proposed_facts, content, source_url)
    result.verified_facts = validated
    result.facts_excluded = excluded
    result.scrape_status = "success"

    # --- Step 6: Snapshot existing profile, then write new one ---
    previous_snapshot = _snapshot_profile(company.profile)
    _write_profile(company, result, db)
    _write_audit(company, result, started_at, db, previous_snapshot=previous_snapshot)

    return result


# ---------------------------------------------------------------------------
# Evidence validation
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Collapse all whitespace runs to a single space and lowercase."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _validate_facts(
    proposed: list[dict[str, Any]],
    scraped_content: str,
    source_url: str,
) -> tuple[list[dict[str, Any]], int]:
    """
    Validate each proposed verified fact against the actual scraped text.

    A fact is accepted only when:
      - It has a non-empty 'evidence_text' field.
      - The normalised evidence_text is at least _MIN_EVIDENCE_LENGTH chars.
      - The normalised evidence_text is a substring of the normalised scraped content.

    Accepted facts have their source_url set to the actual crawled URL.
    Rejected facts are counted but never included in the output.

    Returns (accepted_facts, excluded_count).
    """
    normalised_content = _normalise(scraped_content)
    accepted: list[dict[str, Any]] = []
    excluded = 0

    for item in proposed:
        if not isinstance(item, dict):
            excluded += 1
            continue

        evidence = str(item.get("evidence_text", "")).strip()
        fact_text = str(item.get("fact", "")).strip()

        if not fact_text:
            excluded += 1
            continue

        normalised_evidence = _normalise(evidence)

        if (
            len(normalised_evidence) < _MIN_EVIDENCE_LENGTH
            or normalised_evidence not in normalised_content
        ):
            logger.debug(
                "Fact excluded — evidence not found in scraped content: %r", fact_text
            )
            excluded += 1
            continue

        accepted.append({
            "fact": fact_text,
            "evidence_text": evidence,
            "source_url": item.get("source_url") or source_url,
        })

    return accepted, excluded


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def _scrape_website(
    url: str,
) -> tuple[ScrapeResult | None, str | None, str]:
    """
    Scrape the URL using EthicalScraper.

    Returns (ScrapeResult, None, "success") on success.
    Returns (None, error_message, status_code) on failure.
    status_code is one of "scrape_blocked" or "scrape_failed".
    """
    try:
        with EthicalScraper() as scraper:
            return scraper.scrape(url), None, "success"
    except (SSRFBlockedError, RobotsBlockedError, RobotsUnavailableError) as exc:
        logger.warning("Scrape blocked for '%s': %s", url, exc)
        return None, str(exc), "scrape_blocked"
    except ScraperError as exc:
        logger.warning("Scrape failed for '%s': %s", url, exc)
        return None, str(exc), "scrape_failed"
    except Exception as exc:
        logger.error("Unexpected scraper error for '%s': %s", url, exc)
        return None, str(exc), "scrape_failed"


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str) -> dict[str, Any]:
    """
    Extract and parse the JSON object from the LLM response.
    Handles markdown code fences and preamble text.
    Returns an empty dict on any parse failure.
    """
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse LLM JSON response: %s", exc)
        return {}


def _ensure_list(value: Any) -> list:
    """Return value if it's a list, else an empty list."""
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Profile persistence — called ONLY on full success
# ---------------------------------------------------------------------------

def _write_profile(company: Company, result: ResearchResult, db: Session) -> None:
    """
    Insert or update the CompanyProfile row.
    Called ONLY when the full pipeline succeeded.
    """
    try:
        profile = company.profile
        if profile is None:
            profile = CompanyProfile(company_id=company.id)
            db.add(profile)

        profile.business_summary = result.business_summary or None
        profile.products_services = result.products_services or None
        profile.customer_segments = result.customer_segments or None
        profile.positioning = result.positioning or None
        profile.verified_facts = result.verified_facts or None
        profile.assumptions = result.assumptions or None

        db.commit()
        db.refresh(profile)
        logger.info("CompanyProfile written for company '%s'.", company.name)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to write CompanyProfile for '%s': %s", company.name, exc)
        raise


# ---------------------------------------------------------------------------
# Profile snapshot — JSON-serialisable capture of existing profile
# ---------------------------------------------------------------------------

def _snapshot_profile(profile: CompanyProfile | None) -> dict[str, Any] | None:
    """
    Capture the current profile fields as a plain JSON-serialisable dict.
    Returns None if no profile exists yet.
    """
    if profile is None:
        return None
    return {
        "business_summary": profile.business_summary,
        "products_services": profile.products_services,
        "customer_segments": profile.customer_segments,
        "positioning": profile.positioning,
        "verified_facts": profile.verified_facts,
        "assumptions": profile.assumptions,
    }


# ---------------------------------------------------------------------------
# Audit logging — always written, one entry per execution
# ---------------------------------------------------------------------------

def _write_audit(
    company: Company,
    result: ResearchResult,
    started_at: float,
    db: Session,
    previous_snapshot: dict[str, Any] | None = None,
) -> None:
    """
    Write one AuditLog row recording the outcome of this research execution.
    Never raises — audit failure must not mask the primary result.
    """
    duration_ms = int((time.monotonic() - started_at) * 1000)
    is_success = result.scrape_status == "success"

    details: dict[str, Any] = {
        "company_id": result.company_id,
        "website_url": result.website_url,
        "scrape_status": result.scrape_status,
        "facts_accepted": len(result.verified_facts),
        "facts_excluded": result.facts_excluded,
    }
    if previous_snapshot is not None:
        details["previous_profile_snapshot"] = previous_snapshot

    try:
        log_entry = AuditLog(
            company_id=company.id,
            task_type=_TASK_TYPE,
            status="success" if is_success else "error",
            details=details,
            error_message=result.scrape_error if not is_success else None,
            duration_ms=duration_ms,
        )
        db.add(log_entry)
        db.commit()
        logger.debug(
            "AuditLog written for company '%s': status=%s duration=%dms",
            company.name,
            log_entry.status,
            duration_ms,
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to write AuditLog for company '%s': %s", company.name, exc
        )
