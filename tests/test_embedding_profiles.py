"""Offline coverage for PostgreSQL embedding profile and operation guards."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import AsyncMock, patch

import pytest

from src.db.embedding_profiles import (
    EPISODE_EMBEDDING_SPACE,
    EmbeddingSpaceError,
    embedding_profile_record,
    episode_embedding_space,
    preflight_embedding_space,
    require_embedding_space,
)
from src.llm.provider_config import resolve_provider_settings
from src.scripts import embedding_preflight, generate_embeddings


def _profile(*, dimensions: int = 768):
    return resolve_provider_settings(
        {
            "TEXT_PROVIDER": "ollama",
            "EMBEDDING_PROVIDER": "ollama",
            "GRAPHITI_TEXT_PROVIDER": "ollama",
            "GRAPHITI_EMBEDDING_PROVIDER": "ollama",
            "OLLAMA_CHAT_MODEL": "local/chat",
            "OLLAMA_EMBEDDING_MODEL": "local/embed",
            "OLLAMA_EMBEDDING_DIMENSIONS": str(dimensions),
        }
    ).embedding_profile


class FakePostgres:
    """Catalog-shaped fake that never stores vectors or source text."""

    def __init__(self, profile, *, formatted_type: str = "vector(768)", active: bool = True):
        record = embedding_profile_record(profile)
        self.formatted_type = formatted_type
        self.state = {
            "id": "00000000-0000-0000-0000-000000000001",
            "semantic_index": "episodes",
            "physical_space": "episodes.embedding",
            "table_name": "episodes",
            "column_name": "embedding",
            "expected_dimensions": 768,
            "distance_metric": "cosine",
            "index_name": "idx_episodes_embedding",
            "index_method": "hnsw",
            "operator_class": "vector_cosine_ops",
            "state": "active" if active else "unverified",
            "profile_fingerprint": record["fingerprint"] if active else None,
            "activated_at": "2026-08-07T00:00:00Z" if active else None,
            "stored_profile_fingerprint": record["fingerprint"] if active else None,
            **{f"profile_{key}": value for key, value in record.items() if key != "fingerprint"},
        }

    async def fetchrow(self, query, *args):
        if "to_regclass('embedding_profiles')" in query:
            return {
                "profiles_table": "embedding_profiles",
                "states_table": "embedding_index_states",
            }
        if "FROM pg_attribute" in query:
            return {"formatted_type": self.formatted_type}
        if "count(*) AS total_rows" in query:
            return {"total_rows": 5, "embedded_rows": 4}
        if "FROM pg_index" in query:
            return {
                "method": "hnsw",
                "operator_class": "vector_cosine_ops",
                "column_name": "embedding",
                "options": ["m=16", "ef_construction=64"],
                "valid": True,
                "ready": True,
                "key_columns": 1,
            }
        raise AssertionError("Unexpected fetchrow query")

    async def fetch(self, query, *args):
        assert "FROM embedding_index_states" in query
        return [self.state]

    async def fetchval(self, query, *args):
        assert "to_regclass($1)" in query
        return "episodes"

    async def connect(self):
        return None

    async def disconnect(self):
        return None


def test_profile_record_is_complete_and_secret_free():
    profile = _profile()

    record = embedding_profile_record(profile)

    assert record == {
        "fingerprint": profile.fingerprint,
        "provider": "ollama",
        "endpoint_class": "ollama-http",
        "implementation": "sage-provider-v1",
        "model": "local/embed",
        "model_revision": None,
        "dimensions": 768,
        "output_encoding": "float",
        "storage_type": "pgvector-vector-float4",
        "normalize": False,
        "distance_metric": "cosine",
        "input_type": None,
    }
    assert "base_url" not in record
    assert "api_key" not in record


def test_episode_space_uses_configured_profile_dimensions():
    assert episode_embedding_space(_profile(dimensions=1024)).dimensions == 1024
    assert EPISODE_EMBEDDING_SPACE.dimensions == 768


async def test_preflight_accepts_matching_active_profile_and_reports_coverage():
    profile = _profile()

    report = await preflight_embedding_space(
        FakePostgres(profile),
        EPISODE_EMBEDDING_SPACE,
        configured_profile=profile,
    )

    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["physical"]["dimensions"] == 768
    assert report["physical"]["missing_rows"] == 1
    assert [finding["code"] for finding in report["findings"]] == ["embedding_coverage_incomplete"]


async def test_preflight_blocks_configured_and_physical_dimension_mismatches():
    configured_profile = _profile(dimensions=1024)
    stored_profile = _profile()

    report = await preflight_embedding_space(
        FakePostgres(stored_profile, formatted_type="vector(384)"),
        EPISODE_EMBEDDING_SPACE,
        configured_profile=configured_profile,
    )

    codes = {finding["code"] for finding in report["findings"]}
    assert report["status"] == "blocked"
    assert "configured_dimension_mismatch" in codes
    assert "physical_dimension_mismatch" in codes
    assert "profile_fingerprint_mismatch" in codes
    assert "profile_dimensions_mismatch" in codes


def test_require_embedding_space_exposes_reason_codes_only():
    report = {
        "ready": False,
        "findings": [
            {"code": "profile_fingerprint_mismatch", "severity": "error"},
            {"code": "embedding_coverage_incomplete", "severity": "warning"},
        ],
    }

    with pytest.raises(EmbeddingSpaceError) as raised:
        require_embedding_space(report)

    assert "profile_fingerprint_mismatch" in str(raised.value)
    assert "embedding_coverage_incomplete" not in str(raised.value)


async def test_generation_guard_blocks_before_embedder_construction_or_provider_call():
    profile = _profile()
    embedder_factory = AsyncMock(side_effect=AssertionError("must not construct embedder"))
    blocked = {
        "ready": False,
        "findings": [{"code": "active_space_missing", "severity": "error"}],
    }

    with patch.object(
        generate_embeddings,
        "preflight_embedding_space",
        AsyncMock(return_value=blocked),
    ):
        with pytest.raises(EmbeddingSpaceError, match="active_space_missing"):
            await generate_embeddings.generate_embeddings(
                database_getter=AsyncMock(return_value=object()),
                profile_resolver=lambda: profile,
                embedder_factory=embedder_factory,
            )

    embedder_factory.assert_not_awaited()


async def test_status_cli_uses_read_only_connection(capsys):
    profile = _profile()
    read_only_values = []

    def postgres_factory(*, read_only):
        read_only_values.append(read_only)
        return FakePostgres(profile)

    result = await embedding_preflight.run(
        Namespace(command="status", scope="episodes", json=False),
        postgres_factory=postgres_factory,
        profile_resolver=lambda: profile,
    )

    assert result == 0
    assert read_only_values == [True]
    assert "Embedding preflight: READY" in capsys.readouterr().out


async def test_activation_cli_rejects_confirmation_before_database_connection(capsys):
    connected = False

    def postgres_factory(*, read_only):
        nonlocal connected
        connected = True
        raise AssertionError("invalid confirmation must not connect")

    result = await embedding_preflight.run(
        Namespace(
            command="activate",
            json=False,
            adopt_existing=True,
            confirm="wrong",
        ),
        postgres_factory=postgres_factory,
        profile_resolver=_profile,
    )

    assert result == 2
    assert connected is False
    assert "EmbeddingSpaceError" in capsys.readouterr().err


async def test_empty_initialization_cli_rejects_confirmation_before_database_connection(capsys):
    connected = False

    def postgres_factory(*, read_only):
        nonlocal connected
        connected = True
        raise AssertionError("invalid confirmation must not connect")

    result = await embedding_preflight.run(
        Namespace(command="initialize-empty", json=False, confirm="wrong"),
        postgres_factory=postgres_factory,
        profile_resolver=_profile,
    )

    assert result == 2
    assert connected is False
    assert "EmbeddingSpaceError" in capsys.readouterr().err
