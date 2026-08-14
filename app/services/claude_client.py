"""Centralized Claude API client with retry and error classification."""

import asyncio
import json
import logging

import anthropic
import httpx
from pydantic import ValidationError

from app.config import settings

logger = logging.getLogger(__name__)


def _coerce_json_strings(value):
    """Recursively parse JSON-encoded strings inside a tool_use input.

    Sonnet 5 occasionally returns a nested array/object field as a JSON string
    (sometimes wrapping the whole payload into its own field, e.g.
    ``{"tables": "{\\"tables\\": [...]}"``). Plain strings stay untouched.
    """
    if isinstance(value, dict):
        fixed = {}
        for k, v in value.items():
            if isinstance(v, str) and v.strip()[:1] in ("[", "{"):
                try:
                    parsed = json.loads(v)
                except ValueError:
                    fixed[k] = v
                    continue
                if isinstance(parsed, dict) and list(parsed.keys()) == [k]:
                    parsed = parsed[k]
                fixed[k] = _coerce_json_strings(parsed)
            else:
                fixed[k] = _coerce_json_strings(v)
        return fixed
    if isinstance(value, list):
        return [_coerce_json_strings(v) for v in value]
    return value


def parse_tool_input(schema_class, raw):
    """Validate a tool_use input against a Pydantic schema.

    Tries the raw input first, then progressively repaired variants covering
    Sonnet 5's observed tool-input quirks: JSON-encoded string fields
    (see _coerce_json_strings) and a single-key envelope wrapping the real
    payload (e.g. ``{"api_spec": {...actual fields...}}``).
    """
    if isinstance(raw, str):
        raw = json.loads(raw)

    candidates = [raw, _coerce_json_strings(raw)]
    for c in list(candidates):
        if isinstance(c, dict) and len(c) == 1:
            inner = next(iter(c.values()))
            if isinstance(inner, dict):
                candidates.append(inner)

    last_err = None
    for i, candidate in enumerate(candidates):
        try:
            result = schema_class.model_validate(candidate)
            if i > 0:
                logger.warning(
                    "[%s] tool input accepted after repair variant %d", schema_class.__name__, i,
                )
            return result
        except ValidationError as exc:
            last_err = exc
    raise last_err


def log_cache_stats(usage, call_name: str) -> None:
    input_tokens = getattr(usage, "input_tokens", 0)
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    logger.info(
        "%s: input_tokens=%d, cache_creation_input_tokens=%d, cache_read_input_tokens=%d",
        call_name,
        input_tokens,
        cache_creation,
        cache_read,
    )


# Transient HTTP status codes worth retrying
_RETRYABLE_STATUS_CODES = {429, 503, 529}

# Retry config
MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0  # seconds
MAX_BACKOFF = 30.0


def get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(timeout=600.0, connect=10.0),
    )


class TransientAPIError(Exception):
    """Raised when Claude API returns a retryable error after all retries exhausted."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PermanentAPIError(Exception):
    """Raised when Claude API returns a non-retryable error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is transient and worth retrying."""
    # Anthropic SDK errors with retryable status codes
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS_CODES:
        return True
    # Timeout errors — SDK wrappers are NOT subclasses of the httpx types
    if isinstance(exc, (anthropic.APITimeoutError, httpx.TimeoutException, asyncio.TimeoutError)):
        return True
    # Connection errors — same, cover the SDK wrapper explicitly
    if isinstance(exc, (anthropic.APIConnectionError, httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    return False


async def call_claude(*, label: str = "claude", **kwargs) -> anthropic.types.Message:
    """Call Claude API with automatic retry on transient errors.

    Args:
        label: Human-readable label for logging (e.g. "detect_feature", "gaps_analysis")
        **kwargs: All arguments passed to client.messages.create()

    Returns:
        The Claude API response.

    Raises:
        TransientAPIError: After all retries exhausted on transient errors.
        PermanentAPIError: Immediately on permanent errors (4xx except 429).
    """
    client = get_client()
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await client.messages.create(**kwargs)
            if attempt > 1:
                logger.info("[%s] succeeded on attempt %d/%d", label, attempt, MAX_RETRIES)
            return response

        except Exception as exc:
            last_exc = exc
            status = getattr(exc, "status_code", None)

            if not _is_retryable(exc):
                logger.error("[%s] permanent error (status=%s): %s", label, status, exc)
                raise PermanentAPIError(str(exc), status_code=status) from exc

            if attempt >= MAX_RETRIES:
                logger.error("[%s] exhausted %d retries (last status=%s): %s", label, MAX_RETRIES, status, exc)
                raise TransientAPIError(str(exc), status_code=status) from exc

            backoff = min(INITIAL_BACKOFF * (2 ** (attempt - 1)), MAX_BACKOFF)
            # Use Retry-After header if available (429 responses)
            retry_after = (getattr(exc, "headers", None) or {}).get("retry-after")
            if retry_after:
                try:
                    backoff = max(backoff, float(retry_after))
                except (ValueError, TypeError):
                    pass

            logger.warning(
                "[%s] transient error (status=%s, attempt %d/%d), retrying in %.1fs: %s",
                label, status, attempt, MAX_RETRIES, backoff, exc,
            )
            await asyncio.sleep(backoff)

    # Should not reach here, but just in case
    raise TransientAPIError(str(last_exc))
