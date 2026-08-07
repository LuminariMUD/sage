"""Offline coverage for isolated, bounded shadow embedding operations."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from unittest.mock import Mock, patch
from uuid import UUID

import pytest

from src.llm.config import get_embedding_profile_for_provider
from src.llm.provider_config import resolve_provider_settings
from src.retrieval.benchmark import SourceSnapshot
from src.retrieval.shadow_embeddings import (
    BUILD_SHADOW_INDEX_CONFIRMATION,
    RECOVER_SHADOW_RUN_CONFIRMATION,
    REGISTER_SHADOW_CONFIRMATION,
    RUN_SHADOW_CONFIRMATION,
    ShadowEmbeddingError,
    ShadowEpisode,
    execute_shadow_backfill,
    planned_backfill_requests,
    shadow_search_query,
)
from src.scripts import shadow_embeddings

PROFILE_FINGERPRINT = "embedding:sha256:" + "a" * 64
SOURCE_FINGERPRINT = "sha256:v1:" + "b" * 64
SNAPSHOT_FINGERPRINT = "source-snapshot:sha256:" + "c" * 64
RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
EPISODE_ID = UUID("00000000-0000-0000-0000-000000000002")


def _profile(*, dimensions: int = 3, batch_size: int = 2):
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OLLAMA_EMBEDDING_DIMENSIONS": str(dimensions),
            "OLLAMA_EMBEDDING_BATCH_SIZE": str(batch_size),
        }
    ).embedding_profile


def _snapshot() -> SourceSnapshot:
    return SourceSnapshot(episode_count=1, document_count=1, fingerprint=SNAPSHOT_FINGERPRINT)


def _episode() -> ShadowEpisode:
    return ShadowEpisode(
        episode_id=EPISODE_ID,
        document_stable_id="doc_alpha",
        episode_index=0,
        source_fingerprint=SOURCE_FINGERPRINT,
        text="Sensitive source text must never enter the report.",
    )


class FakeRepository:
    def __init__(
        self, *, always_pending: bool = False, registration_error: Exception | None = None
    ):
        self.always_pending = always_pending
        self.registration_error = registration_error
        self.pending_calls = 0
        self.reserved: list[tuple[UUID, int]] = []
        self.finalized: list[tuple[int, int]] = []
        self.failed: list[tuple[int, str]] = []

    async def require_registered(self, profile):
        if self.registration_error:
            raise self.registration_error
        return {"ready": False}

    async def current_snapshot(self):
        return _snapshot()

    async def start_run(self, profile, snapshot, *, provider_request_limit):
        assert snapshot == _snapshot()
        assert provider_request_limit >= 1
        return RUN_ID

    async def pending_episodes(self, profile, *, limit):
        assert limit == profile.batch_size
        self.pending_calls += 1
        if self.always_pending or self.pending_calls == 1:
            return [_episode()]
        return []

    async def reserve_batch(self, run_id, profile, episodes):
        assert run_id == RUN_ID
        self.reserved.append((run_id, len(episodes)))
        return len(self.reserved)

    async def finalize_batch_success(
        self,
        run_id,
        ordinal,
        profile,
        episodes,
        vectors,
        *,
        latency_ms,
        metadata,
    ):
        assert run_id == RUN_ID
        assert metadata["total_tokens"] == 4
        assert latency_ms >= 0
        self.finalized.append((ordinal, len(vectors)))
        return True

    async def finalize_batch_failure(self, run_id, ordinal, error):
        self.failed.append((ordinal, type(error).__name__))

    async def finish_run(self, run_id, profile, target_snapshot):
        return {
            "schema_version": 1,
            "operation": "embedding_shadow_backfill",
            "status": "completed" if not self.always_pending else "stopped",
            "run_id": str(run_id),
            "profile_fingerprint": profile.fingerprint,
            "target_source_snapshot_fingerprint": target_snapshot.fingerprint,
            "target_episode_count": 1,
            "stored_episode_count": len(self.finalized),
            "provider_requests": {
                "maximum": len(self.reserved),
                "reserved": len(self.reserved),
                "succeeded": len(self.finalized),
            },
            "usage": {"input_tokens": 2, "total_tokens": 4},
            "estimated_cost_usd": None,
            "failure_type": None,
            "failure_code": None,
        }


class FakeEmbedder:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[list[str]] = []

    async def embed_batch(self, texts):
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("upstream-secret-detail")
        return [[1.0, 0.0, 0.0] for _ in texts]

    def sanitized_metadata(self):
        return {
            "actual_model": "local/embed",
            "usage": {"input_tokens": 2, "total_tokens": 4},
        }


def test_shadow_search_is_fixed_to_profile_dimension_and_current_sources():
    profile = _profile(dimensions=1024)

    query = shadow_search_query(profile)

    assert f"embedding::vector({profile.dimensions})" in query
    assert profile.fingerprint in query
    assert "desired_source_fingerprint = shadow.source_fingerprint" in query
    assert "$1::vector(1024)" in query


def test_planned_backfill_requests_uses_profile_batch_size():
    assert planned_backfill_requests(0, _profile(batch_size=2)) == 0
    assert planned_backfill_requests(5, _profile(batch_size=2)) == 3


def test_target_profile_resolution_does_not_mutate_active_selector():
    environment = {
        "TEXT_PROVIDER": "unrelated-invalid-value",
        "EMBEDDING_PROVIDER": "ollama",
        "GRAPHITI_TEXT_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
        "OLLAMA_CHAT_MODEL": "local/chat",
        "OLLAMA_EMBEDDING_MODEL": "local/embed",
        "OLLAMA_EMBEDDING_DIMENSIONS": "768",
        "OPENROUTER_KEY": "offline-unit-test-secret",
        "OPENROUTER_EMBEDDING_MODEL": "perplexity/test-embedding",
        "OPENROUTER_EMBEDDING_DIMENSIONS": "1024",
    }

    with patch.dict(os.environ, environment, clear=True):
        profile = get_embedding_profile_for_provider("openrouter")

        assert profile.connection.provider == "openrouter"
        assert profile.dimensions == 1024
        assert os.environ["EMBEDDING_PROVIDER"] == "ollama"


async def test_backfill_reserves_before_each_call_and_emits_no_content():
    repository = FakeRepository()
    embedder = FakeEmbedder()

    report = await execute_shadow_backfill(
        repository,
        _profile(),
        embedder,
        maximum_provider_requests=2,
    )

    assert repository.reserved == [(RUN_ID, 1)]
    assert repository.finalized == [(1, 1)]
    assert embedder.calls == [[_episode().text]]
    serialized = json.dumps(report)
    assert _episode().text not in serialized
    assert str(EPISODE_ID) not in serialized


async def test_backfill_enforces_request_ceiling_without_hidden_retry():
    repository = FakeRepository(always_pending=True)
    embedder = FakeEmbedder()

    report = await execute_shadow_backfill(
        repository,
        _profile(),
        embedder,
        maximum_provider_requests=1,
    )

    assert len(repository.reserved) == 1
    assert len(embedder.calls) == 1
    assert report["status"] == "stopped"


async def test_backfill_records_failure_without_exposing_provider_detail():
    repository = FakeRepository()

    with pytest.raises(ShadowEmbeddingError) as raised:
        await execute_shadow_backfill(
            repository,
            _profile(),
            FakeEmbedder(fail=True),
            maximum_provider_requests=1,
        )

    assert "upstream-secret-detail" not in str(raised.value)
    assert repository.failed == [(1, "RuntimeError")]


@pytest.mark.parametrize(
    ("command", "required"),
    [
        ("register", REGISTER_SHADOW_CONFIRMATION),
        ("backfill", RUN_SHADOW_CONFIRMATION),
        ("build-index", BUILD_SHADOW_INDEX_CONFIRMATION),
        ("recover-run", RECOVER_SHADOW_RUN_CONFIRMATION),
    ],
)
async def test_cli_refuses_mutations_before_profile_or_database_access(command, required, capsys):
    profile_resolver = Mock(side_effect=AssertionError("must not resolve profile"))
    postgres_factory = Mock(side_effect=AssertionError("must not connect"))
    arguments = {
        "command": command,
        "provider": "openrouter",
        "confirm": "",
        "json": False,
    }
    if command == "backfill":
        arguments["max_provider_requests"] = 1

    result = await shadow_embeddings.run(
        Namespace(**arguments),
        postgres_factory=postgres_factory,
        profile_resolver=profile_resolver,
    )

    assert result == 2
    assert required in capsys.readouterr().err
    profile_resolver.assert_not_called()
    postgres_factory.assert_not_called()


async def test_cli_status_is_read_only_and_resolves_no_provider(capsys):
    read_only_values: list[bool] = []
    profile_resolver = Mock(side_effect=AssertionError("status has no provider access"))

    class FakePostgres:
        async def connect(self):
            return None

        async def disconnect(self):
            return None

    class FakeStatusRepository:
        async def inventory(self, *, profile_fingerprint=None):
            assert profile_fingerprint is None
            return {
                "schema_version": 1,
                "operation": "embedding_shadow_status",
                "status": "inventory",
                "source_snapshot": None,
                "spaces": [],
                "findings": [],
            }

    def postgres_factory(*, read_only):
        read_only_values.append(read_only)
        return FakePostgres()

    result = await shadow_embeddings.run(
        Namespace(command="status", profile_fingerprint=None, json=False),
        postgres_factory=postgres_factory,
        profile_resolver=profile_resolver,
        repository_factory=lambda postgres: FakeStatusRepository(),
    )

    assert result == 0
    assert read_only_values == [True]
    profile_resolver.assert_not_called()
    assert "Embedding shadow status: INVENTORY" in capsys.readouterr().out


async def test_cli_blocks_adapter_construction_until_profile_is_registered(capsys):
    embedder_factory = Mock(side_effect=AssertionError("must not construct adapter"))

    class FakePostgres:
        async def connect(self):
            return None

        async def disconnect(self):
            return None

    repository = FakeRepository(
        registration_error=ShadowEmbeddingError("Shadow embedding profile is not registered")
    )
    result = await shadow_embeddings.run(
        Namespace(
            command="backfill",
            provider="ollama",
            confirm=RUN_SHADOW_CONFIRMATION,
            max_provider_requests=1,
            json=False,
        ),
        postgres_factory=lambda **kwargs: FakePostgres(),
        profile_resolver=lambda provider: _profile(),
        embedder_factory=embedder_factory,
        repository_factory=lambda postgres: repository,
    )

    assert result == 2
    embedder_factory.assert_not_called()
    assert "not registered" in capsys.readouterr().err


async def test_cli_recovers_run_without_resolving_provider_or_building_adapter(capsys):
    profile_resolver = Mock(side_effect=AssertionError("recovery has no provider access"))
    embedder_factory = Mock(side_effect=AssertionError("recovery has no adapter"))

    class FakePostgres:
        async def connect(self):
            return None

        async def disconnect(self):
            return None

    class FakeRecoveryRepository:
        async def recover_run(self, run_id):
            assert run_id == RUN_ID
            return {
                "schema_version": 1,
                "operation": "embedding_shadow_backfill",
                "status": "stopped",
                "run_id": str(run_id),
                "target_episode_count": 1,
                "stored_episode_count": 0,
                "provider_requests": {"maximum": 1, "reserved": 1, "succeeded": 0},
                "failure_code": "operator_recovery",
            }

    result = await shadow_embeddings.run(
        Namespace(
            command="recover-run",
            run_id=RUN_ID,
            confirm=RECOVER_SHADOW_RUN_CONFIRMATION,
            json=False,
        ),
        postgres_factory=lambda **kwargs: FakePostgres(),
        profile_resolver=profile_resolver,
        embedder_factory=embedder_factory,
        repository_factory=lambda postgres: FakeRecoveryRepository(),
    )

    assert result == 0
    profile_resolver.assert_not_called()
    embedder_factory.assert_not_called()
    assert "operator_recovery" in capsys.readouterr().out
