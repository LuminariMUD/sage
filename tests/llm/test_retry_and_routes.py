"""Offline retry and ordered text-route orchestration tests."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.llm.provider_config import TransportRetryPolicy, resolve_provider_settings
from src.llm.retry import (
    ModelSchemaValidationError,
    classify_provider_failure,
    retry_after_seconds,
)
from src.llm.routes import TextRouteExecutionError, TextRouteExecutor


def _fallback_environment() -> dict[str, str]:
    return {
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://ollama:11434",
        "OLLAMA_CHAT_MODEL": "qwen2.5:7b",
        "OLLAMA_REASONING_MODEL": "qwen2.5:3b",
        "OLLAMA_EXTRACTION_MODEL": "qwen2.5:3b",
        "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
        "OLLAMA_EMBEDDING_DIMENSIONS": "768",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_MODEL": "qwen2.5:7b",
        "GRAPHITI_EXTRACTION_PRIMARY_ATTEMPTS": "2",
        "GRAPHITI_EXTRACTION_FALLBACK_ATTEMPTS": "1",
        "GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS": "3",
        "GRAPH_SYNC_MAX_PROVIDER_CALLS": "3",
    }


class _FakeProvider:
    def __init__(self, responses):
        self.responses = responses
        self.last_response_metadata = {}

    async def generate(self, *args, **kwargs):
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        self.last_response_metadata = {
            "actual_model": kwargs["model"],
            "upstream_provider": "offline-test",
        }
        return response


@pytest.mark.asyncio
async def test_route_retries_schema_failure_then_records_degraded_fallback():
    route = resolve_provider_settings(_fallback_environment()).graphiti_text_route
    providers = {
        "qwen2.5:3b": _FakeProvider(["invalid", "invalid"]),
        "qwen2.5:7b": _FakeProvider(["valid"]),
    }

    def validate(text: str) -> str:
        if text == "invalid":
            raise ModelSchemaValidationError("offline validation detail")
        return text

    result = await TextRouteExecutor(
        route,
        provider_factory=lambda candidate: providers[candidate.model],
    ).execute("offline prompt", validator=validate)

    assert result.text == "valid"
    assert result.degraded is True
    assert result.candidate_fingerprint == route.candidates[1].fingerprint
    assert [attempt.outcome for attempt in result.attempts] == [
        "failure",
        "failure",
        "success",
    ]
    assert [attempt.failure_class for attempt in result.attempts] == [
        "schema_validation",
        "schema_validation",
        None,
    ]
    assert "offline prompt" not in str(result.attempts)
    assert "offline validation detail" not in str(result.attempts)


@pytest.mark.asyncio
async def test_route_never_falls_back_on_authentication_failure():
    route = resolve_provider_settings(_fallback_environment()).graphiti_text_route
    calls = []

    class AuthenticationError(RuntimeError):
        status_code = 401

    def factory(candidate):
        calls.append(candidate.model)
        return _FakeProvider([AuthenticationError("offline secret-bearing detail")])

    with pytest.raises(TextRouteExecutionError) as raised:
        await TextRouteExecutor(route, provider_factory=factory).execute("offline prompt")

    assert raised.value.failure_class == "authentication"
    assert raised.value.failure_code == "provider_authentication"
    assert calls == ["qwen2.5:3b"]
    assert "offline secret-bearing detail" not in str(raised.value)


@pytest.mark.asyncio
async def test_route_transport_retry_respects_retry_after_and_hard_call_budget():
    environment = _fallback_environment() | {
        "TEXT_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "offline-route-secret",
        "OPENROUTER_CHAT_MODEL": "qwen/qwen-test",
        "OPENROUTER_TRANSPORT_MAX_ATTEMPTS": "3",
        "OPENROUTER_RETRY_BASE_SECONDS": "0.5",
        "OPENROUTER_RETRY_MAX_SECONDS": "2",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "",
    }
    route = resolve_provider_settings(environment).text_route("chat")

    class RateLimitError(RuntimeError):
        status_code = 429
        response = SimpleNamespace(headers={"Retry-After": "12"})

    provider = _FakeProvider([RateLimitError("offline detail"), "answer"])
    sleeps = []

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    result = await TextRouteExecutor(
        route,
        provider_factory=lambda candidate: provider,
        sleep=fake_sleep,
    ).execute("offline prompt")

    assert result.text == "answer"
    assert result.degraded is False
    assert route.maximum_provider_calls == 3
    assert [attempt.transport_attempt for attempt in result.attempts] == [1, 2]
    assert sleeps == [2]


@pytest.mark.asyncio
async def test_route_stops_after_declared_actual_call_limit():
    environment = _fallback_environment() | {
        "TEXT_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "offline-route-secret",
        "OPENROUTER_CHAT_MODEL": "qwen/qwen-test",
        "OPENROUTER_TRANSPORT_MAX_ATTEMPTS": "3",
        "OPENROUTER_RETRY_BASE_SECONDS": "0",
        "OPENROUTER_RETRY_MAX_SECONDS": "0",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "",
    }
    route = resolve_provider_settings(environment).text_route("chat")

    class RateLimitError(RuntimeError):
        status_code = 429

    provider = _FakeProvider([RateLimitError("sensitive detail") for _ in range(3)])

    with pytest.raises(TextRouteExecutionError) as raised:
        await TextRouteExecutor(
            route,
            provider_factory=lambda candidate: provider,
        ).execute("offline prompt")

    assert len(raised.value.attempts) == route.maximum_provider_calls == 3
    assert [attempt.transport_attempt for attempt in raised.value.attempts] == [1, 2, 3]
    assert raised.value.failure_class == "rate_limit"
    assert "sensitive detail" not in str(raised.value)


def test_retry_after_invalid_millisecond_header_uses_standard_fallback():
    error = RuntimeError("offline")
    error.response = SimpleNamespace(headers={"retry-after-ms": "invalid", "Retry-After": "1.25"})

    assert retry_after_seconds(error) == 1.25


def test_failure_classification_handles_quota_and_nonretryable_client_errors():
    quota = RuntimeError("offline")
    quota.status_code = 402
    bad_request = RuntimeError("offline")
    bad_request.status_code = 422

    assert classify_provider_failure(quota).failure_class == "resource_exhaustion"
    assert classify_provider_failure(bad_request).failure_class == "configuration"


def test_transport_retry_policy_rejects_nonfinite_delays():
    with pytest.raises(ValueError, match="finite"):
        TransportRetryPolicy(base_delay_seconds=float("nan"))


def test_retry_and_fallback_contracts_reject_authentication():
    with pytest.raises(ValueError, match="nonretryable"):
        TransportRetryPolicy(retry_on=frozenset({"authentication"}))

    route = resolve_provider_settings(_fallback_environment()).graphiti_text_route
    with pytest.raises(ValueError, match="prohibited"):
        replace(route, fallback_on=frozenset({"authentication"}))
