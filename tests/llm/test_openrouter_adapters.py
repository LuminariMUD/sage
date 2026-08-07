"""Offline response-path tests for the OpenRouter text adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.llm.providers.factory import get_llm_provider, reset_provider_cache
from src.llm.providers.openrouter_provider import OpenRouterProvider, OpenRouterStreamError


@pytest.fixture(autouse=True)
def _reset_caches():
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.fixture
def openrouter_environment(monkeypatch):
    monkeypatch.setenv("TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-unit-test-secret")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://sage.example.test")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Luminari Sage Tests")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "qwen/qwen-test")
    monkeypatch.setenv("OPENROUTER_TEXT_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_TEXT_REQUIRE_PARAMETERS", "true")
    monkeypatch.setenv("OPENROUTER_TEXT_DATA_COLLECTION", "deny")


def _completion(*, content="answer", model="qwen/qwen-test", provider="Test Upstream"):
    usage = SimpleNamespace(
        model_dump=lambda: {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=model,
        provider=provider,
        usage=usage,
        model_extra={},
    )


@pytest.mark.asyncio
async def test_non_streaming_request_preserves_tools_format_routing_and_usage(
    openrouter_environment,
):
    provider = OpenRouterProvider()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion()

    provider.client.chat.completions.create = fake_create
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    response_format = {"type": "json_object"}

    result = await provider.generate(
        "hello",
        max_tokens=64,
        tools=tools,
        response_format=response_format,
    )

    assert result == "answer"
    assert captured["model"] == "qwen/qwen-test"
    assert captured["max_tokens"] == 64
    assert captured["tools"] == tools
    assert captured["response_format"] == response_format
    assert captured["extra_body"] == {
        "provider": {
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
        }
    }
    assert provider.last_response_metadata == {
        "requested_model": "qwen/qwen-test",
        "actual_model": "qwen/qwen-test",
        "upstream_provider": "Test Upstream",
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "candidate_fingerprint": provider.candidate.fingerprint,
        "transport_attempts": 1,
    }


@pytest.mark.asyncio
async def test_pre_response_rate_limit_retries_are_bounded(openrouter_environment, monkeypatch):
    monkeypatch.setenv("OPENROUTER_TRANSPORT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("OPENROUTER_RETRY_BASE_SECONDS", "0")
    monkeypatch.setenv("OPENROUTER_RETRY_MAX_SECONDS", "0")
    provider = OpenRouterProvider()
    calls = 0

    class RateLimitError(RuntimeError):
        status_code = 429
        response = SimpleNamespace(headers={"Retry-After": "0"})

    async def fake_create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError("redacted upstream detail")
        return _completion()

    provider.client.chat.completions.create = fake_create

    assert await provider.generate("hello") == "answer"
    assert calls == 2
    assert provider.last_transport_attempts == 2


@pytest.mark.asyncio
async def test_configured_openrouter_routing_cannot_be_overridden(openrouter_environment):
    provider = OpenRouterProvider()

    with pytest.raises(ValueError, match="cannot override"):
        await provider.generate(
            "hello",
            extra_body={"provider": {"allow_fallbacks": True}},
        )


@pytest.mark.asyncio
async def test_stream_surfaces_in_band_error_after_partial_content(openrouter_environment):
    provider = OpenRouterProvider()
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="partial "))],
            model="qwen/qwen-test",
            provider="Test Upstream",
            model_extra={},
        ),
        SimpleNamespace(
            choices=[],
            model="qwen/qwen-test",
            provider="Test Upstream",
            model_extra={
                "error": {
                    "code": 429,
                    "metadata": {"error_type": "rate_limit_exceeded"},
                }
            },
        ),
    ]

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not chunks:
                raise StopAsyncIteration
            return chunks.pop(0)

    async def fake_create(**kwargs):
        assert kwargs["stream"] is True
        return FakeStream()

    provider.client.chat.completions.create = fake_create
    stream = provider.stream("hello")

    assert await anext(stream) == "partial "
    with pytest.raises(OpenRouterStreamError) as raised:
        await anext(stream)
    assert raised.value.error_type == "rate_limit_exceeded"
    assert "offline-unit-test-secret" not in str(raised.value)


@pytest.mark.asyncio
async def test_stream_creation_retry_is_bounded_before_first_chunk(
    openrouter_environment, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_TRANSPORT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("OPENROUTER_RETRY_BASE_SECONDS", "0")
    monkeypatch.setenv("OPENROUTER_RETRY_MAX_SECONDS", "0")
    provider = OpenRouterProvider()
    calls = 0
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="answer"))],
            model="qwen/qwen-test",
            provider="Test Upstream",
            model_extra={},
        )
    ]

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not chunks:
                raise StopAsyncIteration
            return chunks.pop(0)

    async def fake_create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("offline detail")
        return FakeStream()

    provider.client.chat.completions.create = fake_create

    assert [part async for part in provider.stream("hello")] == ["answer"]
    assert calls == 2
    assert provider.last_transport_attempts == 2


def test_stream_error_type_does_not_echo_untrusted_upstream_detail():
    error = OpenRouterStreamError("credential-like-untrusted-detail")

    assert error.error_type == "stream_error"
    assert "credential-like-untrusted-detail" not in str(error)


def test_transport_and_factory_cache_are_profile_aware(openrouter_environment, monkeypatch):
    chat = get_llm_provider(task="chat")
    same_chat = get_llm_provider(task="chat")
    monkeypatch.setenv("OPENROUTER_REASONING_MODEL", "openai/reasoning-test")
    reasoning = get_llm_provider(task="reasoning")

    assert chat is same_chat
    assert chat is not reasoning
    assert chat.client.max_retries == 0
    assert str(chat.client.base_url) == "https://openrouter.ai/api/v1/"
    assert chat.client.default_headers["HTTP-Referer"] == "https://sage.example.test"
    assert "Authorization" not in chat.candidate.connection.default_headers
