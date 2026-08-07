"""Unit tests for pre-network Graphiti provider-call accounting."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from graphiti_core.llm_client.config import LLMConfig

from src.graphiti.ollama_config import get_graphiti_llm_client
from src.graphiti.provider_config import GraphitiTextRouteClient
from src.graphiti.provider_tracking import ProviderCallTracker, ProviderTrackingError
from src.graphiti.sync_models import (
    FailureClass,
    JobLease,
    ProviderCallLimitExceeded,
    ProviderCallTicket,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.llm.provider_config import resolve_provider_settings
from src.llm.retry import ModelSchemaValidationError


def _profile():
    return GraphSyncExecutionProfile(
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        candidate_fingerprint="candidate:test",
        embedding_profile_fingerprint="embedding:test",
        provider="ollama",
        model="qwen2.5:3b",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        max_entities=25,
        max_relationships=25,
    )


def _lease():
    now = datetime.now(UTC)
    return JobLease(
        episode_id=uuid4(),
        attempt_id=uuid4(),
        run_id=uuid4(),
        lease_token=uuid4(),
        lease_owner="worker-a",
        attempt_number=1,
        budget_attempt_number=1,
        retry_generation=0,
        job_attempt_limit=3,
        provider_call_limit=3,
        retry_delay_seconds=60,
        captured_source_fingerprint="sha256:v1:test",
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        lease_expires_at=now + timedelta(minutes=15),
        text="Lore",
        document_id=uuid4(),
        episode_index=1,
        created_at=now,
    )


class FakeRepository:
    def __init__(self, events):
        self.events = events
        self.intents = []
        self.records = []
        self.reject_reservation = False

    async def reserve_provider_call(self, lease, intent):
        self.events.append("reserve")
        self.intents.append(intent)
        if self.reject_reservation:
            raise ProviderCallLimitExceeded("limit")
        return ProviderCallTicket(
            attempt_id=lease.attempt_id,
            call_number=len(self.records) + 1,
            intent=intent,
        )

    async def complete_provider_call(self, lease, ticket, record):
        self.events.append("complete")
        self.records.append(record)
        return ticket.call_number


def _client(events, *, error=None, max_retries=0):
    async def create(**kwargs):
        events.append("network")
        if error is not None:
            raise error
        return SimpleNamespace(
            model="qwen2.5:3b-build-7",
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
            model_extra={"provider": "local-ollama"},
        )

    completions = SimpleNamespace(create=create)
    transport = SimpleNamespace(
        max_retries=max_retries,
        chat=SimpleNamespace(completions=completions),
    )
    return SimpleNamespace(client=transport), completions, create


async def test_tracker_reserves_before_network_and_records_sanitized_usage():
    events = []
    repository = FakeRepository(events)
    client, completions, original = _client(events)
    tracker = ProviderCallTracker(repository, _lease(), client, _profile())

    async with tracker.installed():
        response = await completions.create(model="qwen2.5:3b", messages=[])

    assert response.model == "qwen2.5:3b-build-7"
    assert events == ["reserve", "network", "complete"]
    assert completions.create is original
    record = repository.records[0]
    assert record.actual_model == "qwen2.5:3b-build-7"
    assert record.actual_upstream_provider == "local-ollama"
    assert record.total_tokens == 18


async def test_tracker_records_failed_request_then_preserves_original_error():
    events = []
    repository = FakeRepository(events)
    client, completions, _ = _client(events, error=TimeoutError("timed out"))
    tracker = ProviderCallTracker(repository, _lease(), client, _profile())

    with pytest.raises(TimeoutError):
        async with tracker.installed():
            await completions.create(model="qwen2.5:3b", messages=[])

    assert events == ["reserve", "network", "complete"]
    record = repository.records[0]
    assert record.failure_class is FailureClass.TRANSPORT
    assert record.failure_code == "provider_transport"


async def test_tracker_discards_untrusted_response_metadata():
    events = []
    repository = FakeRepository(events)

    async def create(**kwargs):
        events.append("network")
        return SimpleNamespace(
            model="private\nmodel output",
            usage=SimpleNamespace(
                prompt_tokens=-1,
                completion_tokens="private",
                total_tokens=2**63,
            ),
            model_extra={"provider": "private\nupstream"},
        )

    transport = SimpleNamespace(
        max_retries=0,
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )
    client = SimpleNamespace(client=transport)
    tracker = ProviderCallTracker(repository, _lease(), client, _profile())

    async with tracker.installed():
        await transport.chat.completions.create(model="qwen2.5:3b", messages=[])

    record = repository.records[0]
    assert record.actual_model == "qwen2.5:3b"
    assert record.actual_upstream_provider is None
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.total_tokens is None


async def test_budget_rejection_occurs_before_network_io():
    events = []
    repository = FakeRepository(events)
    repository.reject_reservation = True
    client, completions, _ = _client(events)
    tracker = ProviderCallTracker(repository, _lease(), client, _profile())

    with pytest.raises(ProviderCallLimitExceeded):
        async with tracker.installed():
            await completions.create(model="qwen2.5:3b", messages=[])

    assert events == ["reserve"]
    assert repository.records == []


def test_tracker_refuses_opaque_transport_retries():
    events = []
    repository = FakeRepository(events)
    client, _, _ = _client(events, max_retries=2)
    tracker = ProviderCallTracker(repository, _lease(), client, _profile())

    with pytest.raises(ProviderTrackingError, match="retries must be disabled"):
        tracker.verify_ready()


async def test_tracker_refuses_profile_model_drift_before_reservation():
    events = []
    repository = FakeRepository(events)
    client, completions, _ = _client(events)
    tracker = ProviderCallTracker(repository, _lease(), client, _profile())

    with pytest.raises(ProviderTrackingError, match="model does not match"):
        async with tracker.installed():
            await completions.create(model="unexpected-model", messages=[])

    assert events == []


async def test_tracker_records_primary_and_fallback_candidate_identity():
    environment = {
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
        "OLLAMA_CHAT_MODEL": "local/chat",
        "OLLAMA_EXTRACTION_MODEL": "local/primary",
        "OLLAMA_EMBEDDING_MODEL": "local/embed",
        "GRAPHITI_EXTRACTION_PRIMARY_ATTEMPTS": "1",
        "GRAPHITI_EXTRACTION_FALLBACK_PROVIDER": "ollama",
        "GRAPHITI_EXTRACTION_FALLBACK_MODEL": "local/fallback",
        "GRAPHITI_EXTRACTION_FALLBACK_ATTEMPTS": "1",
        "GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS": "2",
        "GRAPH_SYNC_MAX_PROVIDER_CALLS": "2",
    }
    route = resolve_provider_settings(environment).graphiti_text_route
    events = []
    responses = {
        "local/primary": [
            SimpleNamespace(
                model="local/primary",
                usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=4),
            )
        ],
        "local/fallback": [
            SimpleNamespace(
                model="local/fallback",
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
            )
        ],
    }

    class CandidateClient:
        def __init__(self, candidate):
            self.model = candidate.model
            self.config = LLMConfig(model=candidate.model, small_model=candidate.model)
            self.transport_response = None

            async def create(**kwargs):
                events.append(f"network:{self.model}")
                response = responses[self.model].pop(0)
                if isinstance(response, BaseException):
                    raise response
                self.transport_response = response
                return response

            self.client = SimpleNamespace(
                max_retries=0,
                chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            )

        async def _generate_response(self, messages, response_model, max_tokens, model_size):
            response = await self.client.chat.completions.create(model=self.model, messages=[])
            if self.model == "local/primary":
                raise ModelSchemaValidationError("private malformed output")
            return response

        def take_transport_response(self):
            response = self.transport_response
            self.transport_response = None
            return response

    routed = GraphitiTextRouteClient(route, client_factory=CandidateClient)
    profile = replace(
        _profile(),
        route_fingerprint=route.fingerprint,
        candidate_fingerprint=route.primary.fingerprint,
        provider=route.primary.connection.provider,
        model=route.primary.model,
    )
    lease = replace(_lease(), route_fingerprint=route.fingerprint, provider_call_limit=2)
    repository = FakeRepository(events)
    tracker = ProviderCallTracker(repository, lease, routed, profile)

    async with routed.operation():
        async with tracker.installed():
            response = await routed._generate_response([], None, 128, None)

    assert response.model == "local/fallback"
    assert routed.last_operation_degraded is True
    assert [intent.model for intent in repository.intents] == [
        "local/primary",
        "local/fallback",
    ]
    assert [intent.candidate_fingerprint for intent in repository.intents] == [
        route.candidates[0].fingerprint,
        route.candidates[1].fingerprint,
    ]
    assert [record.outcome.value for record in repository.records] == ["failure", "success"]
    assert repository.records[0].failure_class is FailureClass.SCHEMA_VALIDATION
    assert repository.records[0].actual_model == "local/primary"
    assert repository.records[0].total_tokens == 4
    assert "private malformed output" not in repository.records[0].failure_summary


async def test_ollama_graphiti_transport_disables_opaque_retries(monkeypatch):
    monkeypatch.setenv("GRAPHITI_PROVIDER", "ollama")
    client = get_graphiti_llm_client()
    try:
        assert client.client.max_retries == 0
        ProviderCallTracker.verify_client(client)
    finally:
        await client.client.close()


async def test_openai_graphiti_uses_trackable_chat_completions(monkeypatch):
    monkeypatch.setenv("GRAPHITI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    client = get_graphiti_llm_client()
    try:
        assert client.client.max_retries == 0
        ProviderCallTracker.verify_client(client)
    finally:
        await client.client.close()
