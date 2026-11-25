"""
Competitor Intelligence Service (Phase 3, Module 6).

Identifies relevant direct, indirect, and substitute competitors using
company research context and local Ollama LLM.

Safety & Integrity guarantees:
- Reuses existing company research profile (business summary, products, customer segments, positioning, verified facts).
- Never fabricates fake competitors or fake citations.
- Keeps AI suggestions ephemeral â€” they are returned to the caller for review and are NOT auto-saved to the database.
- Prevents duplicate competitors across names and website domains.
- Fails safely on LLM unavailability or invalid output without touching database state.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.competitor import Competitor
from app.schemas.competitor import (
    CompetitorDiscoveryResponse,
    CompetitorSuggestion,
    CompetitorType,
)
from app.schemas.company import normalize_website_url
from app.services.ai import llm_client
from app.services.ai.llm_client import LLMResponseError, LLMUnavailableError

logger = logging.getLogger(__name__)


class CompetitorIntelligenceError(Exception):
    """Base exception for competitor intelligence errors."""


class ProfileNotFoundError(CompetitorIntelligenceError):
    """Raised when company profile has not been generated yet."""


class CompetitorLLMError(CompetitorIntelligenceError):
    """Raised when LLM returns invalid, empty, or unparseable output."""


# ---------------------------------------------------------------------------
# Normalization & Domain Extraction Helpers
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Normalize competitor name for case-insensitive duplicate comparison."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().lower())


def extract_domain(url: Optional[str]) -> Optional[str]:
    """
    Extract canonical hostname/domain from URL for deduplication.
    e.g. 'https://www.leapscholar.com/about' -> 'leapscholar.com'
    """
    if not url:
        return None
    cleaned = url.strip().lower()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    try:
        parsed = urlparse(cleaned)
        host = parsed.netloc or parsed.path
        host = host.split(":")[0]  # strip port
        if host.startswith("www."):
            host = host[4:]
        return host.strip("/") if host else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------

def _build_company_context(company: Company) -> str:
    """Format company profile and facts into structured prompt context."""
    profile = company.profile
    if not profile:
        raise ProfileNotFoundError(
            f"Company '{company.name}' does not have a research profile yet. "
            "Please run company research before competitor discovery."
        )

    parts = [
        f"Company Name: {company.name}",
        f"Website: {company.website_url}",
        f"Industry: {company.industry or 'N/A'}",
    ]

    if profile.business_summary:
        parts.append(f"Business Summary: {profile.business_summary}")

    # Products & Services
    if profile.products_services and isinstance(profile.products_services, list):
        items = []
        for p in profile.products_services:
            if isinstance(p, dict):
                name = p.get("name", "")
                desc = p.get("description", "")
                items.append(f"{name}: {desc}" if desc else name)
            elif isinstance(p, str):
                items.append(p)
        if items:
            parts.append("Products & Services: " + "; ".join(items))

    # Customer Segments
    if profile.customer_segments and isinstance(profile.customer_segments, list):
        segments = []
        for s in profile.customer_segments:
            if isinstance(s, dict):
                seg = s.get("segment", "")
                desc = s.get("description", "")
                segments.append(f"{seg} ({desc})" if desc else seg)
            elif isinstance(s, str):
                segments.append(s)
        if segments:
            parts.append("Target Customer Segments: " + "; ".join(segments))

    # Positioning
    if profile.positioning and isinstance(profile.positioning, dict):
        val_prop = profile.positioning.get("value_proposition")
        diffs = profile.positioning.get("differentiators")
        if val_prop:
            parts.append(f"Value Proposition: {val_prop}")
        if diffs and isinstance(diffs, list):
            parts.append("Differentiators: " + "; ".join(str(d) for d in diffs))

    # Verified Facts
    if profile.verified_facts and isinstance(profile.verified_facts, list):
        facts = [f.get("fact", "") for f in profile.verified_facts if isinstance(f, dict) and f.get("fact")]
        if facts:
            parts.append("Verified Facts: " + " | ".join(facts[:5]))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

_DISCOVERY_PROMPT_TEMPLATE = """\
You are an expert competitive intelligence analyst. Analyze the company profile \
below and identify key competitors.

COMPANY PROFILE:
{company_context}

EXISTING KNOWN COMPETITORS (DO NOT DUPLICATE THESE):
{existing_competitors}

TASK:
Identify 3 to 10 realistic, real-world competitors across three distinct strategic tiers:
1. "direct": Direct rivals offering competing products/services targeting the same customers.
2. "indirect": Alternative platforms or providers solving the same problem with a different business model or approach.
3. "substitute": Broader workarounds, DIY alternatives, or manual processes that buyers use instead.

RULES:
- Identify only REAL, legitimate companies or widely recognized solutions that actually exist.
- Never invent fictional companies or hallucinate fake websites.
- Provide a known public domain for website_url, or set it to null if uncertain.
- Provide only an unverified AI rationale, not a claim of evidence or fact.
- Do NOT fabricate fake statistics, citations, or URLs.

Return ONLY a valid JSON object with exactly this structure:
{{
  "competitors": [
    {{
      "name": "<Competitor Name>",
      "website_url": "<https://example.com or null>",
      "competitor_type": "direct" | "indirect" | "substitute",
      "description": "<1-2 sentence unverified description of their offering>",
      "ai_rationale": "<Unverified reasoning for why they may compete with {company_name}>"
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# JSON Response Parsing
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict:
    """Extract and parse JSON object from LLM output."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse competitor LLM JSON: %s\nRaw output: %r", exc, raw[:200])
        raise CompetitorLLMError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CompetitorLLMError("LLM response must be a JSON object.")
    return parsed


# ---------------------------------------------------------------------------
# Competitor Discovery Engine
# ---------------------------------------------------------------------------

def discover_competitors(
    company: Company,
    db: Session,
    client=llm_client,
) -> CompetitorDiscoveryResponse:
    """
    Generate AI competitor suggestions for a company using Ollama.

    Returns CompetitorDiscoveryResponse containing structured suggestions.
    Does NOT write anything to the database â€” suggestions remain strictly
    separated from verified competitor records until approved by user.
    """
    company_context = _build_company_context(company)

    # Fetch existing competitors to prevent proposing existing ones
    stmt = select(Competitor).where(Competitor.company_id == company.id)
    existing_records = db.execute(stmt).scalars().all()

    existing_names = set()
    existing_domains = set()
    for rec in existing_records:
        if rec.name:
            existing_names.add(normalize_name(rec.name))
        domain = extract_domain(rec.website_url)
        if domain:
            existing_domains.add(domain)

    existing_str = ", ".join(rec.name for rec in existing_records if rec.name) or "(None tracked yet)"

    prompt = _DISCOVERY_PROMPT_TEMPLATE.format(
        company_context=company_context,
        existing_competitors=existing_str,
        company_name=company.name,
    )

    try:
        raw_output = client.generate(prompt)
    except LLMUnavailableError as exc:
        logger.error("LLM unavailable during competitor discovery for '%s': %s", company.name, exc)
        raise
    except LLMResponseError as exc:
        logger.error("LLM error during competitor discovery for '%s': %s", company.name, exc)
        raise CompetitorLLMError(f"LLM generation failed: {exc}") from exc

    data = _parse_json(raw_output)
    raw_list = data.get("competitors", [])
    if not isinstance(raw_list, list):
        raise CompetitorLLMError("LLM response missing 'competitors' list.")

    valid_types = {CompetitorType.DIRECT.value, CompetitorType.INDIRECT.value, CompetitorType.SUBSTITUTE.value}

    suggestions: List[CompetitorSuggestion] = []
    seen_in_batch = set()

    for item in raw_list:
        if not isinstance(item, dict):
            continue

        raw_name = item.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            continue

        norm = normalize_name(name)
        if norm in seen_in_batch:
            continue

        # Validate / normalize tier
        comp_type = item.get("competitor_type")
        comp_type = comp_type.strip().lower() if isinstance(comp_type, str) else ""
        if comp_type not in valid_types:
            continue

        website_url = item.get("website_url")
        if website_url is not None:
            if not isinstance(website_url, str) or not website_url.strip():
                continue
            try:
                website_url = normalize_website_url(website_url)
            except ValueError:
                continue

        description = item.get("description")
        ai_rationale = item.get("ai_rationale")
        if not isinstance(description, str) or not description.strip():
            continue
        if not isinstance(ai_rationale, str) or not ai_rationale.strip():
            continue

        # Check if already added to company
        item_domain = extract_domain(website_url)
        is_already_added = (norm in existing_names) or (bool(item_domain and item_domain in existing_domains))

        seen_in_batch.add(norm)
        suggestions.append(
            CompetitorSuggestion(
                name=name,
                website_url=website_url,
                competitor_type=comp_type,
                category=comp_type,
                description=description.strip(),
                ai_rationale=ai_rationale.strip(),
                evidence_url=None,
                is_verified=False,
                is_already_added=is_already_added,
            )
        )

    logger.info(
        "Discovered %d competitor suggestions for company '%s'.",
        len(suggestions),
        company.name,
    )

    return CompetitorDiscoveryResponse(
        company_id=company.id,
        company_name=company.name,
        suggestions_count=len(suggestions),
        suggestions=suggestions,
        generated_at=datetime.now(timezone.utc),
    )
