"""Offline batching and validation tests for provider-neutral embedders."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.llm.embeddings.ollama_embedder import OllamaEmbedder
from src.llm.embeddings.openrouter_embedder import OpenRouterEmbedder
from src.llm.embeddings.validation import EmbeddingValidationError, validate_embedding_batch
from src.llm.provider_config import resolve_provider_settings


def _ollama_environment() -> dict[str, str]:
    return {
        "TEXT_PROVIDER": "ollama",
        "EMBEDDING_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://ollama:11434",
        "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
        "OLLAMA_EMBEDDING_DIMENSIONS": "2",
        "OLLAMA_EMBEDDING_BATCH_SIZE": "8",
    }


def _openrouter_embedding_environment() -> dict[str, str]:
    return _ollama_environment() | {
        "EMBEDDING_PROVIDER": "openrouter",
        "OPENROUTER_KEY": "offline-unit-test-secret",
        "OPENROUTER_EMBEDDING_MODEL": "perplexity/pplx-embed-test",
        "OPENROUTER_EMBEDDING_DIMENSIONS": "2",
        "OPENROUTER_EMBEDDING_BATCH_SIZE": "8",
        "OPENROUTER_EMBEDDING_ALLOW_FALLBACKS": "false",
        "OPENROUTER_EMBEDDING_REQUIRE_PARAMETERS": "true",
        "OPENROUTER_EMBEDDING_DATA_COLLECTION": "deny",
    }


@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0]],
        [[0.0, 0.0]],
        [[float("nan"), 1.0]],
        [["not-a-number", 1.0]],
        [],
    ],
)
def test_shared_vector_validation_rejects_wrong_or_unsafe_values(vectors):
    with pytest.raises(EmbeddingValidationError):
        validate_embedding_batch(vectors, expected_count=1, dimensions=2)


def test_shared_vector_validation_normalizes_numeric_types_without_reordering():
    assert validate_embedding_batch([[1, 2.5], [3.0, 4]], expected_count=2, dimensions=2) == [
        [1.0, 2.5],
        [3.0, 4.0],
    ]


@pytest.mark.asyncio
async def test_ollama_uses_one_modern_batch_request_with_dimensions(monkeypatch):
    profile = resolve_provider_settings(_ollama_environment()).embedding_profile
    embedder = OllamaEmbedder(profile)
    calls = []

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def json(self):
            return {"embeddings": [[1.0, 0.5], [0.25, 1.0]]}

    class FakeSession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, json):
            calls.append((url, json))
            return FakeResponse()

    monkeypatch.setattr("src.llm.embeddings.ollama_embedder.aiohttp.ClientSession", FakeSession)

    vectors = await embedder.embed_batch(["first", "second"])

    assert vectors == [[1.0, 0.5], [0.25, 1.0]]
    assert calls == [
        (
            "http://ollama:11434/api/embed",
            {
                "model": "nomic-embed-text",
                "input": ["first", "second"],
                "dimensions": 2,
                "truncate": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_openrouter_embedding_response_is_reordered_by_explicit_index():
    profile = resolve_provider_settings(_openrouter_embedding_environment()).embedding_profile
    embedder = OpenRouterEmbedder(profile)
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model="perplexity/pplx-embed-test",
            data=[
                SimpleNamespace(index=1, embedding=[0.2, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.1]),
            ],
            usage=SimpleNamespace(
                model_dump=lambda: {
                    "prompt_tokens": 4,
                    "total_tokens": 4,
                    "cost": 0.0012,
                }
            ),
        )

    embedder.client.embeddings.create = fake_create

    vectors = await embedder.embed_batch(["first", "second"])

    assert vectors == [[1.0, 0.1], [0.2, 1.0]]
    assert captured == {
        "model": "perplexity/pplx-embed-test",
        "input": ["first", "second"],
        "dimensions": 2,
        "encoding_format": "float",
        "extra_body": {
            "provider": {
                "allow_fallbacks": False,
                "require_parameters": True,
                "data_collection": "deny",
            }
        },
    }
    assert embedder.last_usage == {"prompt_tokens": 4, "total_tokens": 4}
    assert embedder.sanitized_metadata()["estimated_cost_usd"] == 0.0012


@pytest.mark.asyncio
async def test_openrouter_embedding_accepts_provider_stripped_response_model():
    profile = resolve_provider_settings(_openrouter_embedding_environment()).embedding_profile
    embedder = OpenRouterEmbedder(profile)

    async def provider_stripped_model(**kwargs):
        return SimpleNamespace(
            model="pplx-embed-test",
            data=[SimpleNamespace(index=0, embedding=[1.0, 0.1])],
            usage=None,
        )

    embedder.client.embeddings.create = provider_stripped_model

    assert await embedder.embed_batch(["first"]) == [[1.0, 0.1]]
    assert embedder.last_actual_model == "pplx-embed-test"


@pytest.mark.asyncio
async def test_openrouter_embedding_rejects_model_or_index_drift():
    profile = resolve_provider_settings(_openrouter_embedding_environment()).embedding_profile
    embedder = OpenRouterEmbedder(profile)

    async def wrong_model(**kwargs):
        return SimpleNamespace(
            model="different/model",
            data=[SimpleNamespace(index=0, embedding=[1.0, 0.1])],
            usage=None,
        )

    embedder.client.embeddings.create = wrong_model
    with pytest.raises(EmbeddingValidationError, match="model"):
        await embedder.embed_batch(["first"])

    async def wrong_indices(**kwargs):
        return SimpleNamespace(
            model="perplexity/pplx-embed-test",
            data=[
                SimpleNamespace(index=0, embedding=[1.0, 0.1]),
                SimpleNamespace(index=0, embedding=[0.2, 1.0]),
            ],
            usage=None,
        )

    embedder.client.embeddings.create = wrong_indices
    with pytest.raises(EmbeddingValidationError, match="indices"):
        await embedder.embed_batch(["first", "second"])


@pytest.mark.asyncio
async def test_openrouter_embedding_retries_same_profile_without_fallback():
    environment = _openrouter_embedding_environment() | {
        "OPENROUTER_TRANSPORT_MAX_ATTEMPTS": "2",
        "OPENROUTER_RETRY_BASE_SECONDS": "0",
        "OPENROUTER_RETRY_MAX_SECONDS": "0",
    }
    profile = resolve_provider_settings(environment).embedding_profile
    embedder = OpenRouterEmbedder(profile)
    calls = 0

    async def fake_create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("offline timeout")
        return SimpleNamespace(
            model="perplexity/pplx-embed-test",
            data=[SimpleNamespace(index=0, embedding=[1.0, 0.1])],
            usage=None,
        )

    embedder.client.embeddings.create = fake_create

    assert await embedder.embed_batch(["first"]) == [[1.0, 0.1]]
    assert calls == 2
    assert embedder.last_transport_attempts == 2
