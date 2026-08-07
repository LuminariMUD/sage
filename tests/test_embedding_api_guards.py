"""API regression tests for fail-closed embedding storage checks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api import main


def _blocked_report():
    return {
        "schema_version": 1,
        "semantic_index": "episodes",
        "status": "blocked",
        "ready": False,
        "findings": [
            {
                "code": "profile_fingerprint_mismatch",
                "severity": "error",
                "message": "Stored profile differs",
            }
        ],
    }


@pytest.mark.parametrize(
    ("endpoint", "api_request"),
    [
        (main.rag_query, main.RAGQueryRequest(query="offline query")),
        (main.validate_lore, main.ValidationRequest(content="offline content")),
    ],
)
async def test_vector_endpoints_block_before_provider_call(monkeypatch, endpoint, api_request):
    class ForbiddenEmbedder:
        async def embed_text(self, text):
            raise AssertionError("profile mismatch must block the provider call")

    postgres = object()
    monkeypatch.setattr(main, "embedder", ForbiddenEmbedder())
    monkeypatch.setattr(main, "get_postgres_db", AsyncMock(return_value=postgres))
    monkeypatch.setattr(
        main,
        "_episode_embedding_preflight",
        AsyncMock(return_value=_blocked_report()),
    )
    neo4j_getter = AsyncMock(side_effect=AssertionError("must fail before Neo4j"))
    monkeypatch.setattr(main, "get_neo4j_db", neo4j_getter)

    with pytest.raises(HTTPException) as raised:
        await endpoint(api_request)

    assert raised.value.status_code == 503
    assert "profile_fingerprint_mismatch" in str(raised.value.detail)
    neo4j_getter.assert_not_awaited()


async def test_validation_uses_episode_space_instead_of_legacy_chunks(monkeypatch):
    class FakeEmbedder:
        async def embed_text(self, text):
            return [0.0] * 768

    class FakePostgres:
        def __init__(self):
            self.queries = []

        async def fetch(self, query, *args):
            self.queries.append(query)
            return []

    postgres = FakePostgres()
    neo4j = SimpleNamespace(execute_query=AsyncMock(return_value=[]))
    monkeypatch.setattr(main, "embedder", FakeEmbedder())
    monkeypatch.setattr(main, "get_postgres_db", AsyncMock(return_value=postgres))
    monkeypatch.setattr(main, "get_neo4j_db", AsyncMock(return_value=neo4j))
    monkeypatch.setattr(
        main,
        "_require_episode_embedding_space",
        AsyncMock(return_value={"ready": True}),
    )

    response = await main.validate_lore(main.ValidationRequest(content="lowercase lore"))

    assert response.is_valid is True
    assert len(postgres.queries) == 1
    assert "FROM episodes e" in postgres.queries[0]
    assert "FROM chunks" not in postgres.queries[0]
