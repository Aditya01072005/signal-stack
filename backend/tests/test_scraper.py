"""
Unit tests for the Ethical Web Scraper (scraper.py).

All HTTP calls and DNS resolution are fully mocked.
No real network requests are made. No database access. No Ollama.
"""

import ipaddress
import socket
import threading
import time
import unittest
from datetime import timezone
from unittest.mock import MagicMock, patch

import httpx

from app.services.crawler.scraper import (
    EthicalScraper,
    FetchBlockedError,
    InvalidURLError,
    MaxRetriesExceededError,
    RateLimitedError,
    RedirectLoopError,
    RobotsBlockedError,
    RobotsUnavailableError,
    SSRFBlockedError,
    ScrapeResult,
    TooManyRedirectsError,
    _assert_ssrf_safe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(
    status_code: int,
    text: str = "",
    url: str = "https://example.com/page",
    headers: dict | None = None,
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.url = httpx.URL(url)
    resp.headers = httpx.Headers(headers or {})
    return resp


def _robots_allow(url: str = "https://example.com/robots.txt") -> MagicMock:
    return _make_response(200, "User-agent: *\nAllow: /", url=url)


def _robots_disallow(url: str = "https://example.com/robots.txt") -> MagicMock:
    return _make_response(200, "User-agent: *\nDisallow: /", url=url)


def _robots_404(url: str = "https://example.com/robots.txt") -> MagicMock:
    return _make_response(404, "", url=url)


def _scraper(**kwargs) -> EthicalScraper:
    defaults = dict(
        max_chars=200,
        timeout_connect=5,
        timeout_read=10,
        max_retries=2,
        politeness_delay=0.0,
        robots_cache_ttl=3600,
    )
    defaults.update(kwargs)
    return EthicalScraper(**defaults)


def _no_dns(host, *a, **kw):
    """Patch socket.getaddrinfo to simulate unresolvable host (safe path)."""
    raise socket.gaierror("mocked: no DNS")


# ---------------------------------------------------------------------------
# 1. robots.txt — allow
# ---------------------------------------------------------------------------

class TestRobotsAllow(unittest.TestCase):

    def test_allowed_url_proceeds_to_fetch(self):
        scraper = _scraper()
        page_html = "<html><body><p>Hello world</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, page_html)
            result = scraper.scrape("https://example.com/page")
        self.assertIsInstance(result, ScrapeResult)
        self.assertIn("Hello world", result.clean_text)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.requested_url, "https://example.com/page")

    def test_robots_404_treated_as_allow_all(self):
        scraper = _scraper()
        page_html = "<html><body><p>Content here</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_404()
            mock_get.return_value = _make_response(200, page_html)
            result = scraper.scrape("https://example.com/page")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Content here", result.clean_text)


# ---------------------------------------------------------------------------
# 2. robots.txt — disallow
# ---------------------------------------------------------------------------

class TestRobotsDisallow(unittest.TestCase):

    def test_disallowed_url_raises_robots_blocked_error(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_disallow()
            with self.assertRaises(RobotsBlockedError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertEqual(ctx.exception.domain, "example.com")

    def test_page_fetch_not_called_when_robots_disallows(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_disallow()
            with self.assertRaises(RobotsBlockedError):
                scraper.scrape("https://example.com/secret")
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# 3. robots.txt — unavailable / malformed
# ---------------------------------------------------------------------------

class TestRobotsUnavailable(unittest.TestCase):

    def test_network_error_on_robots_raises_unavailable(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.side_effect = httpx.ConnectError("refused")
            with self.assertRaises(RobotsUnavailableError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertEqual(ctx.exception.domain, "example.com")

    def test_non_200_non_404_robots_raises_unavailable(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _make_response(500, "", url="https://example.com/robots.txt")
            with self.assertRaises(RobotsUnavailableError):
                scraper.scrape("https://example.com/page")

    def test_malformed_robots_txt_raises_unavailable(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns), \
             patch("app.services.crawler.scraper.RobotFileParser.parse",
                   side_effect=Exception("parse error")):
            mock_send.return_value = _make_response(
                200, "GARBAGE\x00\x01\x02", url="https://example.com/robots.txt"
            )
            with self.assertRaises(RobotsUnavailableError):
                scraper.scrape("https://example.com/page")

    def test_page_not_fetched_when_robots_unavailable(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.side_effect = httpx.ConnectError("refused")
            with self.assertRaises(RobotsUnavailableError):
                scraper.scrape("https://example.com/page")
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# 4. HTTP 403
# ---------------------------------------------------------------------------

class TestHTTP403(unittest.TestCase):

    def test_403_raises_fetch_blocked_immediately(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(403)
            with self.assertRaises(FetchBlockedError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_403_does_not_retry(self):
        scraper = _scraper(max_retries=3)
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(403)
            with self.assertRaises(FetchBlockedError):
                scraper.scrape("https://example.com/page")
        self.assertEqual(mock_get.call_count, 1)


# ---------------------------------------------------------------------------
# 5. HTTP 429
# ---------------------------------------------------------------------------

class TestHTTP429(unittest.TestCase):

    def test_429_raises_rate_limited_with_retry_after(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(429, headers={"Retry-After": "60"})
            with self.assertRaises(RateLimitedError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertEqual(ctx.exception.retry_after, 60.0)

    def test_429_without_retry_after_header(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(429)
            with self.assertRaises(RateLimitedError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertIsNone(ctx.exception.retry_after)

    def test_429_does_not_retry(self):
        scraper = _scraper(max_retries=3)
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(429)
            with self.assertRaises(RateLimitedError):
                scraper.scrape("https://example.com/page")
        self.assertEqual(mock_get.call_count, 1)


# ---------------------------------------------------------------------------
# 6. HTTP 5xx retry behaviour
# ---------------------------------------------------------------------------

class TestHTTP5xxRetry(unittest.TestCase):

    def test_5xx_retries_and_eventually_succeeds(self):
        scraper = _scraper(max_retries=2)
        page_html = "<html><body><p>Finally works</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.time.sleep"), \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                _make_response(503),
                _make_response(503),
                _make_response(200, page_html),
            ]
            result = scraper.scrape("https://example.com/page")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Finally works", result.clean_text)

    def test_5xx_exhausts_retries_raises_max_retries_exceeded(self):
        scraper = _scraper(max_retries=2)
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.time.sleep"), \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                _make_response(500),
                _make_response(502),
                _make_response(503),
            ]
            with self.assertRaises(MaxRetriesExceededError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertEqual(ctx.exception.attempts, 3)

    def test_5xx_retry_count_is_correct(self):
        """max_retries=2 means 1 initial + 2 retries = 3 page fetches total."""
        scraper = _scraper(max_retries=2)
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.time.sleep"), \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                _make_response(500),
                _make_response(500),
                _make_response(500),
            ]
            with self.assertRaises(MaxRetriesExceededError):
                scraper.scrape("https://example.com/page")
        self.assertEqual(mock_get.call_count, 3)


# ---------------------------------------------------------------------------
# 7. Successful fetch and text extraction
# ---------------------------------------------------------------------------

class TestSuccessfulFetch(unittest.TestCase):

    def test_returns_scrape_result_with_correct_fields(self):
        scraper = _scraper()
        page_html = "<html><body><p>Signal Stack works.</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, page_html)
            result = scraper.scrape("https://example.com/page")
        self.assertEqual(result.requested_url, "https://example.com/page")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Signal Stack works", result.clean_text)
        self.assertIsNotNone(result.fetch_timestamp)
        self.assertEqual(result.fetch_timestamp.tzinfo, timezone.utc)
        self.assertFalse(result.redirect_occurred)
        self.assertEqual(result.redirect_count, 0)

    def test_scripts_styles_nav_footer_removed(self):
        scraper = _scraper(max_chars=500)
        page_html = """
        <html><head><style>body{color:red}</style></head>
        <body>
          <script>alert('xss')</script>
          <nav>Menu</nav>
          <p>Real content here.</p>
          <footer>Footer text</footer>
        </body></html>
        """
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, page_html)
            result = scraper.scrape("https://example.com/page")
        self.assertIn("Real content here", result.clean_text)
        self.assertNotIn("alert", result.clean_text)
        self.assertNotIn("color:red", result.clean_text)
        self.assertNotIn("Menu", result.clean_text)
        self.assertNotIn("Footer text", result.clean_text)

    def test_clean_text_truncated_to_max_chars(self):
        scraper = _scraper(max_chars=50)
        page_html = f"<html><body><p>{'A' * 500}</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, page_html)
            result = scraper.scrape("https://example.com/page")
        self.assertLessEqual(len(result.clean_text), 50)


# ---------------------------------------------------------------------------
# 8. Redirect behaviour — manual, pre-fetch robots checks
# ---------------------------------------------------------------------------

class TestRedirects(unittest.TestCase):

    def test_same_domain_redirect_robots_checked_before_each_hop(self):
        """
        A same-domain redirect: robots.txt is fetched once (cached),
        SSRF and robots are checked before each hop, content is from final URL.
        """
        scraper = _scraper()
        page_html = "<html><body><p>Final page</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            # First GET returns a 301 redirect to /final
            mock_get.side_effect = [
                _make_response(301, headers={"Location": "/final"},
                               url="https://example.com/page"),
                _make_response(200, page_html, url="https://example.com/final"),
            ]
            result = scraper.scrape("https://example.com/page")
        self.assertTrue(result.redirect_occurred)
        self.assertEqual(result.redirect_count, 1)
        self.assertEqual(result.final_url, "https://example.com/final")
        self.assertIn("Final page", result.clean_text)

    def test_cross_domain_redirect_robots_checked_before_fetching_destination(self):
        """
        Cross-domain redirect: robots.txt for the destination domain is checked
        BEFORE its content is fetched.
        """
        scraper = _scraper()
        page_html = "<html><body><p>Other domain</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            # send() is used for robots.txt fetches
            mock_send.side_effect = [
                _robots_allow("https://example.com/robots.txt"),   # origin robots
                _robots_allow("https://other.com/robots.txt"),     # destination robots
            ]
            mock_get.side_effect = [
                _make_response(302, headers={"Location": "https://other.com/landing"},
                               url="https://example.com/page"),
                _make_response(200, page_html, url="https://other.com/landing"),
            ]
            result = scraper.scrape("https://example.com/page")
        self.assertTrue(result.redirect_occurred)
        self.assertEqual(result.final_url, "https://other.com/landing")
        self.assertEqual(result.robots_source_domain, "other.com")
        self.assertIn("Other domain", result.clean_text)

    def test_redirect_destination_blocked_by_robots_never_fetched(self):
        """
        If the redirect destination's robots.txt disallows, the destination
        content must never be fetched.
        """
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.side_effect = [
                _robots_allow("https://example.com/robots.txt"),
                _robots_disallow("https://blocked.com/robots.txt"),
            ]
            mock_get.side_effect = [
                _make_response(301, headers={"Location": "https://blocked.com/page"},
                               url="https://example.com/page"),
            ]
            with self.assertRaises(RobotsBlockedError) as ctx:
                scraper.scrape("https://example.com/page")
        self.assertEqual(ctx.exception.domain, "blocked.com")
        # Only one GET was made (the redirect response); destination was never fetched
        self.assertEqual(mock_get.call_count, 1)

    def test_too_many_redirects_raises(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            # Always redirect to the next numbered URL
            mock_get.side_effect = [
                _make_response(301, headers={"Location": f"https://example.com/p{i}"},
                               url=f"https://example.com/p{i-1}")
                for i in range(1, 15)
            ]
            with self.assertRaises(TooManyRedirectsError):
                scraper.scrape("https://example.com/p0")

    def test_redirect_loop_raises(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            # A -> B -> A (loop)
            mock_get.side_effect = [
                _make_response(301, headers={"Location": "https://example.com/b"},
                               url="https://example.com/a"),
                _make_response(301, headers={"Location": "https://example.com/a"},
                               url="https://example.com/b"),
            ]
            with self.assertRaises(RedirectLoopError):
                scraper.scrape("https://example.com/a")

    def test_redirect_destination_ssrf_blocked_never_fetched(self):
        """
        If a redirect points to a private IP, SSRF protection must block it
        before any fetch is attempted.
        """
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                _make_response(301, headers={"Location": "http://192.168.1.1/admin"},
                               url="https://example.com/page"),
            ]
            with self.assertRaises(SSRFBlockedError):
                scraper.scrape("https://example.com/page")
        # Destination was never fetched
        self.assertEqual(mock_get.call_count, 1)


# ---------------------------------------------------------------------------
# 9. Connection timeout and network errors
# ---------------------------------------------------------------------------

class TestNetworkErrors(unittest.TestCase):

    def test_timeout_retries_then_raises(self):
        scraper = _scraper(max_retries=2)
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.time.sleep"), \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                httpx.TimeoutException("timed out"),
                httpx.TimeoutException("timed out"),
                httpx.TimeoutException("timed out"),
            ]
            with self.assertRaises(MaxRetriesExceededError):
                scraper.scrape("https://example.com/page")

    def test_connect_error_retries_then_raises(self):
        scraper = _scraper(max_retries=1)
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.time.sleep"), \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                httpx.ConnectError("refused"),
                httpx.ConnectError("refused"),
            ]
            with self.assertRaises(MaxRetriesExceededError):
                scraper.scrape("https://example.com/page")

    def test_network_error_then_success(self):
        scraper = _scraper(max_retries=2)
        page_html = "<html><body><p>Recovered</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.time.sleep"), \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                httpx.ConnectError("refused"),
                _make_response(200, page_html),
            ]
            result = scraper.scrape("https://example.com/page")
        self.assertIn("Recovered", result.clean_text)


# ---------------------------------------------------------------------------
# 10. Invalid URLs
# ---------------------------------------------------------------------------

class TestInvalidURLs(unittest.TestCase):

    def test_empty_string_raises_invalid_url(self):
        with self.assertRaises(InvalidURLError):
            _scraper().scrape("")

    def test_whitespace_only_raises_invalid_url(self):
        with self.assertRaises(InvalidURLError):
            _scraper().scrape("   ")

    def test_missing_scheme_raises_invalid_url(self):
        with self.assertRaises(InvalidURLError):
            _scraper().scrape("example.com/page")

    def test_ftp_scheme_raises_invalid_url(self):
        with self.assertRaises(InvalidURLError):
            _scraper().scrape("ftp://example.com/file")

    def test_no_host_raises_invalid_url(self):
        with self.assertRaises(InvalidURLError):
            _scraper().scrape("https://")


# ---------------------------------------------------------------------------
# 11. Malformed HTML
# ---------------------------------------------------------------------------

class TestMalformedHTML(unittest.TestCase):

    def test_malformed_html_does_not_raise(self):
        scraper = _scraper(max_chars=500)
        malformed = "<html><body><p>Unclosed <b>bold<p>Another</body>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, malformed)
            result = scraper.scrape("https://example.com/page")
        self.assertIsInstance(result.clean_text, str)
        self.assertIn("bold", result.clean_text)

    def test_empty_html_returns_empty_string(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, "")
            result = scraper.scrape("https://example.com/page")
        self.assertEqual(result.clean_text, "")

    def test_html_with_only_scripts_returns_empty(self):
        scraper = _scraper()
        html = "<html><head><script>var x=1;</script></head><body></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.return_value = _make_response(200, html)
            result = scraper.scrape("https://example.com/page")
        self.assertEqual(result.clean_text.strip(), "")


# ---------------------------------------------------------------------------
# 12. robots.txt caching
# ---------------------------------------------------------------------------

class TestRobotsCache(unittest.TestCase):

    def test_robots_fetched_only_once_for_same_domain(self):
        scraper = _scraper(robots_cache_ttl=3600)
        page_html = "<html><body><p>Page</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                _make_response(200, page_html),
                _make_response(200, page_html),
            ]
            scraper.scrape("https://example.com/page1")
            scraper.scrape("https://example.com/page2")
        # robots.txt fetched once; two page GETs
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_get.call_count, 2)

    def test_robots_refetched_after_ttl_expires(self):
        scraper = _scraper(robots_cache_ttl=0)
        page_html = "<html><body><p>Page</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.side_effect = [_robots_allow(), _robots_allow()]
            mock_get.side_effect = [
                _make_response(200, page_html),
                _make_response(200, page_html),
            ]
            scraper.scrape("https://example.com/page1")
            scraper.scrape("https://example.com/page2")
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(mock_get.call_count, 2)


# ---------------------------------------------------------------------------
# 13. SSRF protection
# ---------------------------------------------------------------------------

class TestSSRFProtection(unittest.TestCase):
    """
    Tests for _assert_ssrf_safe and integration with scrape().
    DNS resolution is mocked to return controlled IP addresses.
    """

    def _dns_returning(self, ip: str):
        """Return a getaddrinfo side_effect that resolves any host to ip."""
        def _resolve(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]
        return _resolve

    # --- Direct IP literal tests (no DNS needed) ---

    def test_loopback_ipv4_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://127.0.0.1/", resolve_host=False)

    def test_loopback_ipv6_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://[::1]/", resolve_host=False)

    def test_private_10_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://10.0.0.1/", resolve_host=False)

    def test_private_172_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://172.16.0.1/", resolve_host=False)

    def test_private_192_168_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://192.168.1.1/", resolve_host=False)

    def test_link_local_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://169.254.169.254/", resolve_host=False)

    def test_cloud_metadata_hostname_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://169.254.169.254/latest/meta-data/", resolve_host=False)

    def test_gcp_metadata_hostname_blocked(self):
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://metadata.google.internal/", resolve_host=False)

    def test_public_ip_allowed(self):
        # Should not raise
        _assert_ssrf_safe("https://93.184.216.34/", resolve_host=False)

    # --- DNS resolution tests ---

    def test_hostname_resolving_to_private_ip_blocked(self):
        """A public-looking hostname that resolves to a private IP must be blocked."""
        with patch("app.services.crawler.scraper.socket.getaddrinfo",
                   side_effect=self._dns_returning("10.0.0.5")):
            with self.assertRaises(SSRFBlockedError):
                _assert_ssrf_safe("https://totally-public.example.com/")

    def test_hostname_resolving_to_loopback_blocked(self):
        with patch("app.services.crawler.scraper.socket.getaddrinfo",
                   side_effect=self._dns_returning("127.0.0.1")):
            with self.assertRaises(SSRFBlockedError):
                _assert_ssrf_safe("https://evil.example.com/")

    def test_hostname_resolving_to_link_local_blocked(self):
        with patch("app.services.crawler.scraper.socket.getaddrinfo",
                   side_effect=self._dns_returning("169.254.1.1")):
            with self.assertRaises(SSRFBlockedError):
                _assert_ssrf_safe("https://evil.example.com/")

    def test_hostname_resolving_to_public_ip_allowed(self):
        with patch("app.services.crawler.scraper.socket.getaddrinfo",
                   side_effect=self._dns_returning("93.184.216.34")):
            # Should not raise
            _assert_ssrf_safe("https://example.com/")

    # --- Integration: SSRF blocks scrape() before any HTTP call ---

    def test_scrape_private_ip_url_blocked_before_http(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get:
            with self.assertRaises(SSRFBlockedError):
                scraper.scrape("http://192.168.1.1/page")
        mock_send.assert_not_called()
        mock_get.assert_not_called()

    def test_scrape_loopback_url_blocked_before_http(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get:
            with self.assertRaises(SSRFBlockedError):
                scraper.scrape("http://127.0.0.1/admin")
        mock_send.assert_not_called()
        mock_get.assert_not_called()

    def test_scrape_metadata_endpoint_blocked_before_http(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get:
            with self.assertRaises(SSRFBlockedError):
                scraper.scrape("http://169.254.169.254/latest/meta-data/")
        mock_send.assert_not_called()
        mock_get.assert_not_called()

    def test_scrape_hostname_resolving_to_private_blocked(self):
        scraper = _scraper()
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo",
                   side_effect=self._dns_returning("10.0.0.1")):
            with self.assertRaises(SSRFBlockedError):
                scraper.scrape("https://internal.corp.example.com/secret")
        mock_send.assert_not_called()
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# 14. Concurrent same-domain politeness
# ---------------------------------------------------------------------------

class TestConcurrentPoliteness(unittest.TestCase):

    def test_same_domain_requests_are_serialised(self):
        """
        Two threads scraping the same domain must be serialised by the
        per-domain lock + politeness delay.

        We verify this by measuring total elapsed time: if both ran truly
        concurrently the elapsed time would be ~delay; serialised it must
        be >= 2 * delay because the second thread waits for the first to
        finish AND then waits the politeness delay before its own fetch.
        """
        delay = 0.08  # 80 ms — large enough to measure reliably
        scraper = _scraper(politeness_delay=delay)
        page_html = "<html><body><p>ok</p></body></html>"

        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = _robots_allow()
            mock_get.side_effect = [
                _make_response(200, page_html),
                _make_response(200, page_html),
            ]
            results, errors = [], []

            def worker():
                try:
                    results.append(scraper.scrape("https://example.com/page"))
                except Exception as exc:
                    errors.append(exc)

            start = time.monotonic()
            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            elapsed = time.monotonic() - start

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        self.assertEqual(len(results), 2)
        # Serialised execution must take at least the politeness delay
        # (second thread waits for first to release the lock, then waits delay).
        self.assertGreaterEqual(
            elapsed,
            delay * 0.8,  # 20% tolerance for scheduling jitter
            "Same-domain requests completed too quickly — may not be serialised",
        )

    def test_different_domains_do_not_block_each_other(self):
        """Requests to different domains must run concurrently."""
        scraper = _scraper(politeness_delay=0.15)
        page_html = "<html><body><p>ok</p></body></html>"

        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.side_effect = [
                _robots_allow("https://alpha.com/robots.txt"),
                _robots_allow("https://beta.com/robots.txt"),
            ]
            mock_get.side_effect = [
                _make_response(200, page_html, url="https://alpha.com/page"),
                _make_response(200, page_html, url="https://beta.com/page"),
            ]
            results, errors = [], []

            def worker(url):
                try:
                    results.append(scraper.scrape(url))
                except Exception as exc:
                    errors.append(exc)

            start = time.monotonic()
            t1 = threading.Thread(target=worker, args=("https://alpha.com/page",))
            t2 = threading.Thread(target=worker, args=("https://beta.com/page",))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            elapsed = time.monotonic() - start

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        self.assertEqual(len(results), 2)
        self.assertLess(
            elapsed, 0.5,
            "Different-domain requests appear to be blocking each other",
        )


# ---------------------------------------------------------------------------
# 15. IPv4-mapped IPv6 SSRF protection
# ---------------------------------------------------------------------------

class TestIPv4MappedIPv6(unittest.TestCase):
    """::ffff:x.x.x.x addresses must be unwrapped and checked as IPv4."""

    def test_ipv4_mapped_private_blocked(self):
        """::ffff:192.168.1.1 maps to 192.168.1.1 — must be blocked."""
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://[::ffff:192.168.1.1]/", resolve_host=False)

    def test_ipv4_mapped_loopback_blocked(self):
        """::ffff:127.0.0.1 maps to 127.0.0.1 — must be blocked."""
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://[::ffff:127.0.0.1]/", resolve_host=False)


# ---------------------------------------------------------------------------
# 16. Multicast address blocking
# ---------------------------------------------------------------------------

class TestMulticastBlocked(unittest.TestCase):

    def test_ipv4_multicast_blocked(self):
        """224.0.0.1 is in 224.0.0.0/4 — must be blocked."""
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://224.0.0.1/", resolve_host=False)

    def test_ipv6_multicast_blocked(self):
        """ff02::1 is in ff00::/8 — must be blocked."""
        with self.assertRaises(SSRFBlockedError):
            _assert_ssrf_safe("http://[ff02::1]/", resolve_host=False)


# ---------------------------------------------------------------------------
# 17. robots.txt redirect SSRF protection
# ---------------------------------------------------------------------------

class TestRobotsRedirectSSRF(unittest.TestCase):
    """
    robots.txt redirects must be SSRF-validated before following.
    A redirect to a private address must block the crawl.
    """

    def test_robots_redirect_to_private_ip_blocks_crawl(self):
        """
        If robots.txt redirects to a private IP, the crawl must be blocked
        (conservative: unavailable = blocked).
        """
        scraper = _scraper()
        # First send() returns a 301 pointing to a private IP.
        redirect_resp = _make_response(
            301,
            url="https://example.com/robots.txt",
            headers={"Location": "http://192.168.1.1/robots.txt"},
        )
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.return_value = redirect_resp
            with self.assertRaises(RobotsUnavailableError):
                scraper.scrape("https://example.com/page")
        mock_get.assert_not_called()

    def test_robots_redirect_to_public_url_proceeds(self):
        """
        A robots.txt redirect to a public URL must be followed and the
        resulting allow/disallow decision must be respected.
        """
        scraper = _scraper()
        redirect_resp = _make_response(
            301,
            url="https://example.com/robots.txt",
            headers={"Location": "https://cdn.example.com/robots.txt"},
        )
        page_html = "<html><body><p>Allowed content</p></body></html>"
        with patch.object(scraper._http_client, "send") as mock_send, \
             patch.object(scraper._http_client, "get") as mock_get, \
             patch("app.services.crawler.scraper.socket.getaddrinfo", side_effect=_no_dns):
            mock_send.side_effect = [
                redirect_resp,
                _robots_allow("https://cdn.example.com/robots.txt"),
            ]
            mock_get.return_value = _make_response(200, page_html)
            result = scraper.scrape("https://example.com/page")
        self.assertIn("Allowed content", result.clean_text)


if __name__ == "__main__":
    unittest.main()
