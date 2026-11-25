import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.signal import Signal
from app.models.source import Source
from app.services.crawler.scraper import (
    EthicalScraper,
    FetchBlockedError,
    RobotsBlockedError,
    RobotsUnavailableError,
    ScraperError,
    SSRFBlockedError,
)

logger = logging.getLogger(__name__)

_BLOCKED_ERRORS = (
    SSRFBlockedError,
    RobotsBlockedError,
    RobotsUnavailableError,
    FetchBlockedError,
)


class CompanyNotFoundError(Exception):
    """Raised when a monitoring request targets a missing or deleted company."""


@dataclass
class SourceMonitoringResult:
    source_id: uuid.UUID
    source_name: str
    crawl_status: str
    content_changed: bool
    signal_id: uuid.UUID | None
    characters_scraped: int | None
    final_url: str | None
    message: str


def _content_hash(content: str) -> str:
    normalized = " ".join(content.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_company_monitoring(
    company_id: uuid.UUID,
    db: Session,
) -> list[SourceMonitoringResult]:
    """Crawl active sources and persist new, evidence-backed content signals."""
    company_stmt = select(Company).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    company = db.execute(company_stmt).scalar_one_or_none()
    if company is None:
        raise CompanyNotFoundError(str(company_id))

    sources_stmt = (
        select(Source)
        .where(
            Source.company_id == company_id,
            Source.status == "active",
        )
        .order_by(Source.created_at.asc())
    )
    sources = list(db.execute(sources_stmt).scalars().all())
    if not sources:
        return []

    hashes_stmt = select(Signal.content_hash).where(Signal.company_id == company_id)
    known_hashes = set(db.execute(hashes_stmt).scalars().all())
    results: list[SourceMonitoringResult] = []

    # Reuse one scraper so per-domain politeness delays apply across this run.
    with EthicalScraper() as scraper:
        for source in sources:
            crawled_at = datetime.now(timezone.utc)
            source.last_crawled_at = crawled_at

            try:
                scrape_result = scraper.scrape(source.url)
            except _BLOCKED_ERRORS as exc:
                source.last_error_message = str(exc)
                source.consecutive_failures += 1
                source.health_score = max(0, source.health_score - 20)
                db.commit()
                results.append(
                    SourceMonitoringResult(
                        source_id=source.id,
                        source_name=source.name,
                        crawl_status="blocked",
                        content_changed=False,
                        signal_id=None,
                        characters_scraped=None,
                        final_url=None,
                        message=str(exc),
                    )
                )
                continue
            except ScraperError as exc:
                source.last_error_message = str(exc)
                source.consecutive_failures += 1
                source.health_score = max(0, source.health_score - 10)
                db.commit()
                results.append(
                    SourceMonitoringResult(
                        source_id=source.id,
                        source_name=source.name,
                        crawl_status="failed",
                        content_changed=False,
                        signal_id=None,
                        characters_scraped=None,
                        final_url=None,
                        message=str(exc),
                    )
                )
                continue
            except Exception as exc:
                logger.exception(
                    "Unexpected monitoring crawl error for source %s.", source.id
                )
                error_message = f"Unexpected crawl error ({type(exc).__name__})."
                source.last_error_message = error_message
                source.consecutive_failures += 1
                source.health_score = max(0, source.health_score - 10)
                db.commit()
                results.append(
                    SourceMonitoringResult(
                        source_id=source.id,
                        source_name=source.name,
                        crawl_status="failed",
                        content_changed=False,
                        signal_id=None,
                        characters_scraped=None,
                        final_url=None,
                        message=error_message,
                    )
                )
                continue

            content = scrape_result.clean_text.strip()
            source.last_successful_crawl_at = crawled_at
            source.last_error_message = None
            source.consecutive_failures = 0
            source.health_score = min(100, source.health_score + 10)

            signal_id = None
            content_changed = False
            message = "Crawl succeeded; no readable content was returned."
            if content:
                content_hash = _content_hash(content)
                if content_hash not in known_hashes:
                    signal_id = uuid.uuid4()
                    db.add(
                        Signal(
                            id=signal_id,
                            company_id=company_id,
                            source_id=source.id,
                            title=source.name,
                            content_snippet=content,
                            source_url=scrape_result.final_url,
                            content_hash=content_hash,
                            is_verified=True,
                            verbatim_quote=content,
                            opportunity_threat="neutral",
                        )
                    )
                    known_hashes.add(content_hash)
                    content_changed = True
                    message = "Crawl succeeded; new source content was recorded."
                else:
                    message = "Crawl succeeded; this content is already recorded."

            db.commit()
            results.append(
                SourceMonitoringResult(
                    source_id=source.id,
                    source_name=source.name,
                    crawl_status="success",
                    content_changed=content_changed,
                    signal_id=signal_id,
                    characters_scraped=len(content),
                    final_url=scrape_result.final_url,
                    message=message,
                )
            )

    return results
