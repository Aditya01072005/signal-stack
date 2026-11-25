from typing import Any, Optional
from pydantic import BaseModel, ConfigDict
import uuid


class ResearchResponse(BaseModel):
    """
    API response schema for the company research endpoint.

    scrape_status values:
      "success"            — full pipeline completed, profile written.
      "scrape_failed"      — network/timeout/HTTP error during scraping.
      "scrape_blocked"     — SSRF or robots.txt blocked the URL.
      "llm_unavailable"    — Ollama could not be reached.
      "llm_invalid_output" — LLM responded but output was unparseable.

    verified_facts entries each contain:
      - fact:          the stated fact
      - evidence_text: verbatim excerpt from the scraped page that supports it
      - source_url:    the URL of the page the evidence was taken from

    assumptions are inferences NOT directly stated on the website and are
    explicitly labelled as unverified interpretations.
    """

    company_id: uuid.UUID
    company_name: str
    website_url: str
    scrape_status: str
    scrape_error: Optional[str] = None
    business_summary: str = ""
    products_services: list[dict[str, Any]] = []
    customer_segments: list[dict[str, Any]] = []
    positioning: dict[str, Any] = {}
    verified_facts: list[dict[str, Any]] = []
    facts_excluded: int = 0
    assumptions: list[dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)
