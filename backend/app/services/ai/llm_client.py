"""
Ollama LLM client for Signal Stack.

Wraps the Ollama /api/generate endpoint with:
- Configurable model and base URL drawn from settings.
- Retry logic on transient network/5xx errors.
- Structured exceptions so callers can handle failures cleanly.
- No streaming — waits for the full response before returning.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GENERATE_PATH = "/api/generate"
_MAX_RETRIES = 2
_RETRY_BACKOFF = 2  # seconds; doubles each attempt


class LLMError(Exception):
    """Base class for LLM client errors."""


class LLMUnavailableError(LLMError):
    """Raised when Ollama cannot be reached after all retries."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ollama unavailable: {reason}")


class LLMResponseError(LLMError):
    """Raised when Ollama returns an unexpected HTTP status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Ollama returned HTTP {status_code}: {body[:200]}")


def generate(
    prompt: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 120.0,
) -> str:
    """
    Send a prompt to Ollama and return the complete response text.

    Args:
        prompt:   The full prompt string to send.
        model:    Override the model name (defaults to settings.OLLAMA_MODEL).
        base_url: Override the Ollama base URL (defaults to settings.OLLAMA_BASE_URL).
        timeout:  Total seconds to wait for the response.

    Returns:
        The model's response as a plain string.

    Raises:
        LLMUnavailableError  — network error or all retries exhausted.
        LLMResponseError     — non-200 HTTP response from Ollama.
    """
    _model = model or settings.OLLAMA_MODEL
    _base = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
    url = f"{_base}{_GENERATE_PATH}"

    payload = {
        "model": _model,
        "prompt": prompt,
        "stream": False,
    }

    last_error: str = ""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload)
        except httpx.RequestError as exc:
            last_error = str(exc)
            logger.warning("Ollama request error (attempt %d): %s", attempt + 1, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
            continue

        if response.status_code == 200:
            data = response.json()
            return data.get("response", "")

        if 500 <= response.status_code < 600:
            last_error = f"HTTP {response.status_code}"
            logger.warning(
                "Ollama 5xx (attempt %d): %s", attempt + 1, response.status_code
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
            continue

        # 4xx — not retryable
        raise LLMResponseError(response.status_code, response.text)

    raise LLMUnavailableError(last_error)
