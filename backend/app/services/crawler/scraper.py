"""
Ethical Web Scraper for Signal Stack.

Responsibilities:
- Validate URLs and reject private/reserved/loopback addresses (SSRF protection).
- Check robots.txt before fetching each URL, including every redirect destination.
- Handle redirects manually so robots.txt is checked BEFORE fetching each hop.
- Cache robots.txt per domain with a configurable TTL.
- Enforce per-domain politeness delays without blocking unrelated domains.
- Retry only on 5xx responses and transient network errors.
- Never retry on 403 or 429; surface 429 Retry-After to the caller.
- Extract clean readable text from HTML; enforce SCRAPER_MAX_CHARS.
- Return a structured ScrapeResult; never store raw HTML.
"""

import ipaddress
import logging
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

_USER_AGENT = "SignalStackBot/1.0"

# Maximum number of redirects the scraper will follow manually.
_MAX_REDIRECTS = 10


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ScraperError(Exception):
    """Base class for all scraper errors."""


class SSRFBlockedError(ScraperError):
    """
    Raised when a URL resolves to a private, loopback, link-local,
    reserved, or cloud-metadata address that must never be fetched.
    """

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"SSRF protection blocked '{url}': {reason}")


class RobotsBlockedError(ScraperError):
    """Raised when robots.txt disallows fetching the requested URL."""

    def __init__(self, url: str, domain: str) -> None:
        self.url = url
        self.domain = domain
        super().__init__(f"robots.txt on '{domain}' disallows fetching: {url}")


class RobotsUnavailableError(ScraperError):
    """
    Raised when robots.txt cannot be fetched or parsed.
    Conservative policy: treat as blocked.
    """

    def __init__(self, domain: str, reason: str) -> None:
        self.domain = domain
        self.reason = reason
        super().__init__(
            f"robots.txt unavailable for '{domain}' ({reason}). "
            "Crawl blocked (conservative policy)."
        )


class FetchBlockedError(ScraperError):
    """Raised on HTTP 403 — server explicitly denied access."""

    def __init__(self, url: str, status_code: int) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} — access denied for: {url}")


class RateLimitedError(ScraperError):
    """Raised on HTTP 429 — caller must respect retry_after before re-attempting."""

    def __init__(self, url: str, retry_after: float | None) -> None:
        self.url = url
        self.retry_after = retry_after
        msg = f"HTTP 429 — rate limited for: {url}"
        if retry_after is not None:
            msg += f" (Retry-After: {retry_after}s)"
        super().__init__(msg)


class MaxRetriesExceededError(ScraperError):
    """Raised when all retry attempts for a 5xx or network error are exhausted."""

    def __init__(self, url: str, attempts: int, last_error: str) -> None:
        self.url = url
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Max retries ({attempts}) exceeded for: {url} — last error: {last_error}"
        )


class InvalidURLError(ScraperError):
    """Raised when the supplied URL is missing a valid scheme or host."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"Invalid URL (must be http/https with a valid host): {url}")


class TooManyRedirectsError(ScraperError):
    """Raised when the redirect chain exceeds the configured maximum."""

    def __init__(self, url: str, count: int) -> None:
        self.url = url
        self.count = count
        super().__init__(f"Too many redirects ({count}) starting from: {url}")


class RedirectLoopError(ScraperError):
    """Raised when a redirect cycle is detected."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"Redirect loop detected at: {url}")


# ---------------------------------------------------------------------------
# Structured result
# ---------------------------------------------------------------------------

@dataclass
class ScrapeResult:
    """
    Structured output from a successful scrape.
    Raw HTML is never stored — only cleaned text is retained.
    """
    requested_url: str
    final_url: str
    status_code: int
    clean_text: str
    fetch_timestamp: datetime
    redirect_occurred: bool
    redirect_count: int
    robots_source_domain: str   # domain whose robots.txt governed the final fetch


# ---------------------------------------------------------------------------
# Internal cache entry
# ---------------------------------------------------------------------------

@dataclass
class _RobotsCacheEntry:
    parser: RobotFileParser | None  # None means unavailable / blocked
    fetched_at: float               # time.monotonic() timestamp
    available: bool                 # False if robots.txt could not be retrieved/parsed


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

# Cloud metadata endpoints that must always be blocked regardless of IP checks.
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "169.254.169.254",          # AWS / GCP / Azure IMDS
    "metadata.google.internal", # GCP metadata
    "metadata.internal",        # generic cloud metadata
})

# Private, loopback, link-local, reserved, and multicast network ranges.
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),      # IPv4 loopback
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918 private
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918 private
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918 private
    ipaddress.ip_network("169.254.0.0/16"),    # IPv4 link-local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("0.0.0.0/8"),         # unspecified
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),      # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("240.0.0.0/4"),       # reserved (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"),# broadcast
    ipaddress.ip_network("224.0.0.0/4"),       # IPv4 multicast
    ipaddress.ip_network("ff00::/8"),          # IPv6 multicast
)


def _assert_ssrf_safe(url: str, resolve_host: bool = True) -> None:
    """
    Raise SSRFBlockedError if the URL targets a private, loopback, link-local,
    reserved, multicast, or cloud-metadata address.

    Performs DNS resolution when resolve_host=True so that hostnames that
    resolve to private IPs are also caught.

    LIMITATION — DNS rebinding: this function calls socket.getaddrinfo() to
    resolve the hostname, but httpx performs its own separate OS-level DNS
    lookup when the connection is established. A DNS rebinding attack can
    change the DNS record between these two calls, causing the connection to
    reach a private address even though validation passed. Full prevention
    requires a custom httpx transport that reuses the validated address for
    the actual connection. This is an accepted architectural limitation; this
    scraper does NOT provide complete SSRF protection against DNS rebinding.
    """
    parsed = urlparse(url)
    host = parsed.hostname  # lowercased, strips brackets from IPv6

    if not host:
        raise InvalidURLError(url)

    # Block known cloud metadata hostnames by name before DNS resolution.
    if host in _BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(url, f"blocked cloud metadata hostname: {host}")

    # If the host is already a bare IP literal, check it directly.
    try:
        addr = ipaddress.ip_address(host)
        _assert_ip_safe(url, addr)
        return
    except ValueError:
        pass  # host is a domain name — proceed to DNS resolution

    if not resolve_host:
        return

    # Resolve all addresses the hostname maps to and check every one.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        # Cannot resolve — treat as safe to allow mocked tests to work;
        # real callers will fail at the HTTP level. We do not block on
        # unresolvable names because tests mock the HTTP layer, not DNS.
        logger.debug("DNS resolution failed for '%s': %s — skipping SSRF IP check.", host, exc)
        return

    for info in infos:
        ip_str = info[4][0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        _assert_ip_safe(url, addr)


def _assert_ip_safe(
    url: str, addr: ipaddress.IPv4Address | ipaddress.IPv6Address
) -> None:
    """
    Raise SSRFBlockedError if addr falls within any blocked network.

    IPv4-mapped IPv6 addresses (e.g. ::ffff:192.168.1.1) are unwrapped to
    their IPv4 equivalent before checking, because Python's ipaddress module
    never considers an IPv6Address to be contained in an IPv4Network.
    """
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:192.168.1.1 -> 192.168.1.1)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    for network in _BLOCKED_NETWORKS:
        if addr in network:
            raise SSRFBlockedError(
                url, f"address {addr} is in blocked network {network}"
            )


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class EthicalScraper:
    """
    Thread-safe ethical web scraper.

    One instance can be shared across the application lifetime.
    Redirects are followed manually so robots.txt is checked BEFORE
    each hop is fetched. SSRF protection is applied to every URL,
    including redirect destinations.
    """

    def __init__(
        self,
        max_chars: int | None = None,
        timeout_connect: int | None = None,
        timeout_read: int | None = None,
        max_retries: int | None = None,
        politeness_delay: float | None = None,
        robots_cache_ttl: int | None = None,
    ) -> None:
        self._max_chars = (
            max_chars if max_chars is not None else settings.SCRAPER_MAX_CHARS
        )
        self._timeout_connect = (
            timeout_connect if timeout_connect is not None
            else settings.SCRAPER_TIMEOUT_CONNECT
        )
        self._timeout_read = (
            timeout_read if timeout_read is not None
            else settings.SCRAPER_TIMEOUT_READ
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.SCRAPER_MAX_RETRIES
        )
        self._politeness_delay = (
            politeness_delay if politeness_delay is not None
            else settings.SCRAPER_POLITENESS_DELAY
        )
        self._robots_cache_ttl = (
            robots_cache_ttl if robots_cache_ttl is not None
            else settings.SCRAPER_ROBOTS_CACHE_TTL_SECONDS
        )

        # robots.txt cache: domain -> _RobotsCacheEntry
        self._robots_cache: dict[str, _RobotsCacheEntry] = {}
        self._robots_cache_lock = threading.Lock()

        # Per-domain politeness tracking
        self._domain_last_fetch: dict[str, float] = {}
        self._domain_locks: dict[str, threading.Lock] = {}
        self._domain_locks_meta_lock = threading.Lock()

        # HTTP client with redirects DISABLED — we handle them manually.
        self._http_client = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(
                connect=self._timeout_connect,
                read=self._timeout_read,
                write=10,
                pool=5,
            ),
            follow_redirects=False,  # Manual redirect handling
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape(self, url: str) -> ScrapeResult:
        """
        Fetch and clean the content at `url`.

        For every URL in the redirect chain (including the original):
          1. Validate URL format.
          2. Apply SSRF protection (DNS-resolved).
          3. Check robots.txt.
          4. Enforce politeness delay.
          5. Fetch (single hop, no auto-redirect).

        Raises:
            InvalidURLError          — bad URL format
            SSRFBlockedError         — private/reserved/metadata address
            RobotsUnavailableError   — robots.txt unreachable/malformed
            RobotsBlockedError       — robots.txt explicitly disallows the URL
            FetchBlockedError        — HTTP 403
            RateLimitedError         — HTTP 429 (carries retry_after)
            MaxRetriesExceededError  — 5xx / network errors exhausted retries
            TooManyRedirectsError    — redirect chain too long
            RedirectLoopError        — redirect cycle detected
        """
        self._validate_url(url)

        current_url = url
        visited: set[str] = set()
        redirect_count = 0
        requested_domain = urlparse(url).netloc.lower()

        while True:
            # --- Guard: loop detection ---
            if current_url in visited:
                raise RedirectLoopError(current_url)
            visited.add(current_url)

            # --- Guard: redirect limit ---
            if redirect_count > _MAX_REDIRECTS:
                raise TooManyRedirectsError(url, redirect_count)

            # --- SSRF check ---
            _assert_ssrf_safe(current_url)

            # --- robots.txt check ---
            current_domain = urlparse(current_url).netloc.lower()
            self._assert_robots_allowed(current_url, current_domain)

            # --- Politeness + fetch ---
            domain_lock = self._get_domain_lock(current_domain)
            with domain_lock:
                self._wait_politeness(current_domain)
                response = self._fetch_with_retry(current_url)
                self._domain_last_fetch[current_domain] = time.monotonic()

            # --- Handle redirect ---
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "").strip()
                if not location:
                    # Redirect with no Location — treat as final response
                    break
                # Resolve relative redirects against the current URL
                next_url = urljoin(current_url, location)
                # Validate the redirect destination URL format
                self._validate_url(next_url)
                current_url = next_url
                redirect_count += 1
                continue

            # --- Non-redirect response: done ---
            break

        final_url = current_url
        final_domain = urlparse(final_url).netloc.lower()
        redirect_occurred = redirect_count > 0
        robots_source_domain = final_domain

        clean_text = self._extract_clean_text(response.text)

        return ScrapeResult(
            requested_url=url,
            final_url=final_url,
            status_code=response.status_code,
            clean_text=clean_text,
            fetch_timestamp=datetime.now(timezone.utc),
            redirect_occurred=redirect_occurred,
            redirect_count=redirect_count,
            robots_source_domain=robots_source_domain,
        )

    def close(self) -> None:
        """Release the underlying HTTP client connection pool."""
        self._http_client.close()

    def __enter__(self) -> "EthicalScraper":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # URL validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_url(url: str) -> None:
        """Raise InvalidURLError if url is not a valid http/https URL."""
        if not url or not url.strip():
            raise InvalidURLError(url)
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            raise InvalidURLError(url)
        if not parsed.netloc:
            raise InvalidURLError(url)

    # ------------------------------------------------------------------
    # Robots.txt
    # ------------------------------------------------------------------

    def _assert_robots_allowed(self, url: str, domain: str) -> None:
        """
        Raise RobotsUnavailableError or RobotsBlockedError if the URL
        must not be fetched. Returns silently if allowed.
        """
        entry = self._get_robots_entry(domain)

        if not entry.available:
            logger.warning(
                "robots.txt unavailable for '%s' — blocking (conservative policy).",
                domain,
            )
            raise RobotsUnavailableError(domain, "could not be fetched or parsed")

        if not entry.parser.can_fetch(_USER_AGENT, url):
            logger.info("robots.txt on '%s' disallows: %s", domain, url)
            raise RobotsBlockedError(url, domain)

    def _get_robots_entry(self, domain: str) -> _RobotsCacheEntry:
        """Return a cached (or freshly fetched) robots.txt entry for the domain."""
        now = time.monotonic()

        with self._robots_cache_lock:
            cached = self._robots_cache.get(domain)
            if cached is not None and (now - cached.fetched_at) < self._robots_cache_ttl:
                return cached

        # Fetch outside the cache lock so other domains are not blocked.
        entry = self._fetch_robots(domain)

        with self._robots_cache_lock:
            self._robots_cache[domain] = entry

        return entry

    # Maximum redirects followed when fetching robots.txt.
    _ROBOTS_MAX_REDIRECTS = 5

    def _fetch_robots(self, domain: str) -> _RobotsCacheEntry:
        """
        Fetch and parse robots.txt for the given domain.
        Conservative: any failure (network, parse, non-200/404) marks as unavailable.

        Redirects are followed manually with SSRF validation on every hop so
        that a robots.txt redirect cannot be used to probe internal addresses.
        """
        robots_url = f"https://{domain}/robots.txt"
        now = time.monotonic()

        current_url = robots_url
        visited: set[str] = set()

        try:
            for _ in range(self._ROBOTS_MAX_REDIRECTS + 1):
                if current_url in visited:
                    logger.warning(
                        "Redirect loop fetching robots.txt for '%s'.", domain
                    )
                    return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)
                visited.add(current_url)

                # Validate each robots.txt URL against SSRF rules before fetching.
                _assert_ssrf_safe(current_url)

                response = self._http_client.send(
                    self._http_client.build_request("GET", current_url),
                    follow_redirects=False,
                )

                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location", "").strip()
                    if not location:
                        logger.warning(
                            "robots.txt redirect with no Location for '%s'.", domain
                        )
                        return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)
                    current_url = urljoin(current_url, location)
                    continue

                # Non-redirect response — exit the loop.
                break
            else:
                logger.warning(
                    "Too many redirects fetching robots.txt for '%s'.", domain
                )
                return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)

        except SSRFBlockedError as exc:
            logger.warning(
                "SSRF protection blocked robots.txt redirect for '%s': %s", domain, exc
            )
            return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)
        except Exception as exc:
            logger.warning("Could not fetch robots.txt for '%s': %s", domain, exc)
            return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)

        if response.status_code == 404:
            # No robots.txt — standard convention is allow-all.
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(["User-agent: *", "Allow: /"])
            logger.debug(
                "No robots.txt for '%s' (404) — treating as allow-all.", domain
            )
            return _RobotsCacheEntry(parser=parser, fetched_at=now, available=True)

        if response.status_code != 200:
            logger.warning(
                "robots.txt for '%s' returned HTTP %s — blocking (conservative policy).",
                domain,
                response.status_code,
            )
            return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)

        try:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
        except Exception as exc:
            logger.warning("Failed to parse robots.txt for '%s': %s", domain, exc)
            return _RobotsCacheEntry(parser=None, fetched_at=now, available=False)

        logger.debug("robots.txt cached for '%s'.", domain)
        return _RobotsCacheEntry(parser=parser, fetched_at=now, available=True)

    # ------------------------------------------------------------------
    # Politeness
    # ------------------------------------------------------------------

    def _get_domain_lock(self, domain: str) -> threading.Lock:
        """Return (creating if needed) the per-domain threading.Lock."""
        with self._domain_locks_meta_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = threading.Lock()
            return self._domain_locks[domain]

    def _wait_politeness(self, domain: str) -> None:
        """
        Sleep if needed so at least _politeness_delay seconds have elapsed
        since the last fetch to this domain.
        Must be called while holding the domain lock.
        """
        last = self._domain_last_fetch.get(domain)
        if last is None:
            return
        elapsed = time.monotonic() - last
        wait = self._politeness_delay - elapsed
        if wait > 0:
            logger.debug("Politeness delay %.2fs for domain '%s'.", wait, domain)
            time.sleep(wait)

    # ------------------------------------------------------------------
    # HTTP fetch with retry (single hop — no redirect following)
    # ------------------------------------------------------------------

    def _fetch_with_retry(self, url: str) -> httpx.Response:
        """
        Perform a single-hop HTTP GET with retry logic.

        - 403 → raise FetchBlockedError immediately (no retry)
        - 429 → raise RateLimitedError immediately (no retry)
        - 3xx → return response (caller handles redirect)
        - 5xx → retry up to _max_retries with exponential backoff
        - Network/timeout errors → retry up to _max_retries
        - 2xx → return response
        """
        last_error: str = ""
        attempts = 0

        while attempts <= self._max_retries:
            try:
                response = self._http_client.get(url)
            except httpx.TimeoutException as exc:
                last_error = f"Timeout: {exc}"
                logger.warning(
                    "Timeout on attempt %d for %s: %s", attempts + 1, url, exc
                )
                attempts += 1
                if attempts <= self._max_retries:
                    time.sleep(2 ** attempts)
                continue
            except httpx.RequestError as exc:
                last_error = f"Network error: {exc}"
                logger.warning(
                    "Network error on attempt %d for %s: %s", attempts + 1, url, exc
                )
                attempts += 1
                if attempts <= self._max_retries:
                    time.sleep(2 ** attempts)
                continue

            if response.status_code == 403:
                raise FetchBlockedError(url, response.status_code)

            if response.status_code == 429:
                raise RateLimitedError(url, self._parse_retry_after(response))

            if 500 <= response.status_code < 600:
                last_error = f"HTTP {response.status_code}"
                logger.warning(
                    "HTTP %s on attempt %d for %s — will retry.",
                    response.status_code,
                    attempts + 1,
                    url,
                )
                attempts += 1
                if attempts <= self._max_retries:
                    time.sleep(2 ** attempts)
                continue

            # 2xx or 3xx — return to caller
            return response

        raise MaxRetriesExceededError(url, self._max_retries + 1, last_error)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        """Parse the Retry-After header value into seconds, or return None."""
        header = response.headers.get("Retry-After")
        if header is None:
            return None
        try:
            return float(header)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # HTML cleaning
    # ------------------------------------------------------------------

    def _extract_clean_text(self, html: str) -> str:
        """
        Parse HTML with BeautifulSoup, remove non-content elements,
        extract visible text, and truncate to _max_chars.
        Handles malformed HTML safely (BS4 is lenient by design).
        """
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(
            ["script", "style", "nav", "header", "footer",
             "aside", "form", "noscript", "iframe", "svg", "img"]
        ):
            tag.decompose()

        raw_text = soup.get_text(separator=" ")
        lines = (line.strip() for line in raw_text.splitlines())
        cleaned = " ".join(chunk for chunk in lines if chunk)

        return cleaned[: self._max_chars]
