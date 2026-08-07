"""Bounded, provider-neutral transport retry helpers."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypeVar

from src.llm.provider_config import FailureClassName, TransportRetryPolicy

T = TypeVar("T")


class MalformedModelOutputError(ValueError):
    """Model output could not be decoded into the required format."""


class ModelSchemaValidationError(ValueError):
    """Decoded model output failed the required schema."""


class ModelOutputLimitError(RuntimeError):
    """Model output ended because the configured output limit was reached."""


@dataclass(frozen=True)
class ClassifiedProviderFailure:
    """Stable failure identity safe for retry policy and provenance."""

    failure_class: FailureClassName
    code: str
    status_code: int | None = None


def _status_code(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def classify_provider_failure(error: BaseException) -> ClassifiedProviderFailure:
    """Classify an exception without retaining its potentially sensitive text."""
    status = _status_code(error)
    name = type(error).__name__.lower()
    if (
        isinstance(error, (MalformedModelOutputError, json.JSONDecodeError))
        or "emptyresponse" in name
    ):
        return ClassifiedProviderFailure("malformed_json", "malformed_model_output", status)
    if isinstance(error, ModelSchemaValidationError) or "validationerror" in name:
        return ClassifiedProviderFailure("schema_validation", "model_schema_invalid", status)
    if isinstance(error, ModelOutputLimitError):
        return ClassifiedProviderFailure("output_limit", "model_output_limit", status)
    if status == 401 or "authentication" in name or "autherror" in name:
        return ClassifiedProviderFailure("authentication", "provider_authentication", status)
    if status == 403 or "permissiondenied" in name or "authorization" in name:
        return ClassifiedProviderFailure("authorization", "provider_authorization", status)
    if status == 402 or any(
        marker in name for marker in ("insufficientquota", "quotaexceeded", "resourceexhausted")
    ):
        return ClassifiedProviderFailure(
            "resource_exhaustion", "provider_resource_exhausted", status
        )
    if status == 429 or "ratelimit" in name:
        return ClassifiedProviderFailure("rate_limit", "provider_rate_limit", status)
    if status in {408, 409} or (status is not None and status >= 500):
        return ClassifiedProviderFailure("transport", "provider_http_transient", status)
    if isinstance(error, (TimeoutError, ConnectionError)) or any(
        marker in name for marker in ("timeout", "connect", "transport", "network")
    ):
        return ClassifiedProviderFailure("transport", "provider_transport", status)
    if status is not None and 400 <= status < 500:
        return ClassifiedProviderFailure("configuration", "provider_request_rejected", status)
    if isinstance(error, ValueError) or "configuration" in name:
        return ClassifiedProviderFailure("configuration", "invalid_configuration", status)
    return ClassifiedProviderFailure("internal", "provider_internal", status)


def _headers(error: BaseException) -> Mapping[str, str]:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None)
    return headers if isinstance(headers, Mapping) else {}


def _header(headers: Mapping[str, str], name: str) -> str | None:
    direct = headers.get(name)
    if direct is not None:
        return str(direct)
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return None


def retry_after_seconds(error: BaseException, *, now: datetime | None = None) -> float | None:
    """Parse standard and OpenAI-compatible retry delay headers."""
    headers = _headers(error)
    retry_after_ms = _header(headers, "retry-after-ms")
    if retry_after_ms is not None:
        try:
            value = float(retry_after_ms) / 1000
        except ValueError:
            value = -1.0
        if math.isfinite(value) and value >= 0:
            return value

    retry_after = _header(headers, "retry-after")
    if retry_after is None:
        return None
    try:
        value = float(retry_after)
    except ValueError:
        try:
            target = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError, OverflowError):
            return None
        if target.tzinfo is None or target.utcoffset() is None:
            target = target.replace(tzinfo=UTC)
        value = (target - (now or datetime.now(UTC))).total_seconds()
    return max(0.0, value) if math.isfinite(value) else None


def retry_delay_seconds(
    error: BaseException,
    policy: TransportRetryPolicy,
    *,
    failed_attempt: int,
) -> float:
    """Use Retry-After when present, otherwise bounded exponential backoff."""
    supplied = retry_after_seconds(error)
    if supplied is not None:
        return min(supplied, policy.maximum_delay_seconds)
    exponential = policy.base_delay_seconds * (2 ** max(0, failed_attempt - 1))
    return min(exponential, policy.maximum_delay_seconds)


async def execute_with_transport_retry(
    operation: Callable[[], Awaitable[T]],
    policy: TransportRetryPolicy,
    *,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    on_attempt: Callable[[int], None] | None = None,
) -> T:
    """Execute one logical call with a strict, classified transport budget."""
    for attempt in range(1, policy.maximum_attempts + 1):
        if on_attempt is not None:
            on_attempt(attempt)
        try:
            return await operation()
        except Exception as error:
            failure = classify_provider_failure(error)
            if attempt >= policy.maximum_attempts or failure.failure_class not in policy.retry_on:
                raise
            delay = retry_delay_seconds(error, policy, failed_attempt=attempt)
            if delay:
                await sleep(delay)
    raise RuntimeError("Transport retry loop exited without a result")
