"""Centralized Claude API client: structured outputs, retry and error classification."""

import asyncio
import logging
from typing import TypeVar

import anthropic
import httpx
from anthropic.lib._parse._transform import transform_schema
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


def output_schema(schema_class: type[BaseModel]) -> dict:
    """JSON schema of a Pydantic model in the form structured outputs accept.

    The SDK transform sets ``additionalProperties: false`` on every object and
    moves unsupported constraints (``pattern``, ``minimum``…) into descriptions.
    Recursive models are rejected by the API — keep tree-shaped fields out of the
    schema (``SkipJsonSchema``) and rebuild the tree in code.
    """
    return transform_schema(schema_class)


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


class TruncatedOutputError(ValueError):
    """The response hit ``max_tokens`` before the structured output was complete."""


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


async def call_structured(
    schema: type[ModelT],
    *,
    label: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    system: str | None = None,
    effort: str | None = None,
) -> ModelT:
    """One Claude call whose answer is a ``schema`` instance.

    Structured outputs (``output_config.format``) make the API guarantee a
    schema-valid JSON document, so there is nothing to repair on this side:
    the text is validated into the model and returned. The only failure modes
    left are a truncated answer (``max_tokens``) and a refusal, both raised.
    """
    create_kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        output_config={"format": {"type": "json_schema", "schema": output_schema(schema)}},
    )
    if system:
        create_kwargs["system"] = system
    if effort:
        create_kwargs["output_config"]["effort"] = effort

    response = await call_claude(label=label, **create_kwargs)
    log_cache_stats(response.usage, label)

    if response.stop_reason == "max_tokens":
        raise TruncatedOutputError(
            f"Ответ Claude обрезан лимитом в {max_tokens} токенов — увеличьте лимит или уменьшите документ."
        )
    if response.stop_reason == "refusal":
        raise PermanentAPIError(f"[{label}] Claude отказался отвечать (refusal)")

    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    if not text.strip():
        raise ValueError(f"[{label}] пустой ответ Claude (stop_reason={response.stop_reason})")
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        logger.error("[%s] structured output failed validation: %s\n%s", label, exc, text[:500])
        raise
