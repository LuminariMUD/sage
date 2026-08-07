"""Offline tests for bounded Graphiti candidate retry and fallback routing."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.models import Message
from pydantic import BaseModel

from src.graphiti.provider_config import (
    GraphitiRouteError,
    GraphitiTextRouteClient,
    SingleAttemptOpenAIGenericClient,
)
from src.graphiti.sync_models import ProviderCallLimitExceeded
from src.llm.provider_config import resolve_provider_settings
from src.llm.retry import ModelOutputLimitError, ModelSchemaValidationError


def _route_environment() -> dict[str, str]:
    return {
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
        "OLLAMA_CHAT_MODEL": "local/chat",
        "OLLAMA_EXTRACTION_MODEL": "local/primary",
        "OLLAMA_EMBEDDING_MODEL": "local/embed",
        "GRAPHITI_EXTRACTION_PRIMARY_ATTEMPTS": "2",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_MODEL": "local/fallback",
        "GRAPHITI_EXTRACTION_FALLBACK_ATTEMPTS": "1",
        "GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS": "3",
        "GRAPH_SYNC_MAX_PROVIDER_CALLS": "3",
    }


def _route():
    return resolve_provider_settings(_route_environment()).graphiti_text_route


class FakeCandidateClient:
    def __init__(self, candidate, responses, events):
        self.model = candidate.model
        self.config = LLMConfig(model=candidate.model, small_model=candidate.model)
        self.responses = responses
        self.events = events

    async def _generate_response(self, messages, response_model, max_tokens, model_size):
        self.events.append(self.model)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if response_model is not None:
            response_model.model_validate(response)
        return response


def _router(responses):
    events = []

    def factory(candidate):
        return FakeCandidateClient(candidate, responses[candidate.model], events)

    return GraphitiTextRouteClient(_route(), client_factory=factory), events


async def test_route_retries_primary_then_records_fallback_as_degraded():
    router, events = _router(
        {
            "local/primary": [
                ModelSchemaValidationError("private detail"),
                ModelSchemaValidationError("private detail"),
            ],
            "local/fallback": [{"status": "valid"}],
        }
    )

    async with router.operation():
        result = await router._generate_response([], None, 128, None)

    assert result == {"status": "valid"}
    assert events == ["local/primary", "local/primary", "local/fallback"]
    assert router.last_operation_calls == 3
    assert router.last_operation_degraded is True


async def test_route_never_retries_or_falls_back_on_authentication():
    class AuthenticationError(RuntimeError):
        status_code = 401

    router, events = _router(
        {
            "local/primary": [AuthenticationError("credential-bearing detail")],
            "local/fallback": [{"status": "must-not-run"}],
        }
    )

    with pytest.raises(AuthenticationError):
        async with router.operation():
            await router._generate_response([], None, 128, None)

    assert events == ["local/primary"]
    assert router.last_operation_calls == 1
    assert router.last_operation_degraded is False


async def test_route_treats_an_empty_model_response_as_malformed_output():
    class EmptyResponseError(RuntimeError):
        pass

    router, events = _router(
        {
            "local/primary": [
                EmptyResponseError("private detail"),
                EmptyResponseError("private detail"),
            ],
            "local/fallback": [{"status": "valid"}],
        }
    )

    async with router.operation():
        result = await router._generate_response([], None, 128, None)

    assert result == {"status": "valid"}
    assert events == ["local/primary", "local/primary", "local/fallback"]
    assert router.last_operation_degraded is True


async def test_route_enforces_one_ceiling_across_parallel_graphiti_calls():
    router, events = _router(
        {
            "local/primary": [{"ok": True} for _ in range(5)],
            "local/fallback": [],
        }
    )

    async with router.operation():
        results = await asyncio.gather(
            *(router._generate_response([], None, 128, None) for _ in range(5)),
            return_exceptions=True,
        )

    assert sum(result == {"ok": True} for result in results) == 3
    assert sum(isinstance(result, ProviderCallLimitExceeded) for result in results) == 2
    assert len(events) == router.route.maximum_provider_calls == 3
    assert router.last_operation_calls == 3


async def test_route_refuses_unbounded_use_before_any_candidate_call():
    router, events = _router(
        {
            "local/primary": [{"ok": True}],
            "local/fallback": [],
        }
    )

    with pytest.raises(GraphitiRouteError, match="bounded operation"):
        await router._generate_response([], None, 128, None)

    assert events == []


async def test_single_attempt_client_disables_graphiti_core_retry_loop():
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("private upstream detail")

    transport = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        max_retries=0,
    )
    client = SingleAttemptOpenAIGenericClient(
        config=LLMConfig(model="local/model", small_model="local/model"),
        client=transport,
    )

    with pytest.raises(TimeoutError):
        await client.generate_response([Message(role="user", content="private prompt")])

    assert calls == 1


async def test_single_attempt_client_independently_validates_structured_response():
    class RequiredResponse(BaseModel):
        required_value: int

    async def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"wrong": 1}'))]
        )

    transport = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        max_retries=0,
    )
    client = SingleAttemptOpenAIGenericClient(
        config=LLMConfig(model="local/model", small_model="local/model"),
        client=transport,
    )

    with pytest.raises(ModelSchemaValidationError, match="failed schema validation") as captured:
        await client.generate_response(
            [Message(role="user", content="private prompt")],
            response_model=RequiredResponse,
        )

    assert "wrong" not in str(captured.value)


async def test_single_attempt_client_classifies_length_finish_reason():
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(content='{"partial": true}'),
                )
            ]
        )

    transport = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        max_retries=0,
    )
    client = SingleAttemptOpenAIGenericClient(
        config=LLMConfig(model="local/model", small_model="local/model"),
        client=transport,
    )

    with pytest.raises(ModelOutputLimitError, match="configured limit"):
        await client.generate_response([Message(role="user", content="private prompt")])

    assert calls == 1
