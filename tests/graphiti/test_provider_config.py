"""Offline Graphiti provider-matrix and transport-policy tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.graphiti.provider_config import (
    ProviderGraphitiEmbedder,
    SingleAttemptOpenAIGenericClient,
    get_graphiti_config_summary,
    get_graphiti_embedding_client,
    get_graphiti_llm_client,
)
from src.llm.embeddings.ollama_embedder import OllamaEmbedder
from src.llm.embeddings.openrouter_embedder import OpenRouterEmbedder


def _configure(monkeypatch, text_provider: str, embedding_provider: str) -> None:
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", text_provider)
    monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", embedding_provider)
    monkeypatch.setenv("OLLAMA_EXTRACTION_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_EMBEDDING_DIMENSIONS", "2")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_DIMENSIONS", "2")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-unit-test-secret")
    monkeypatch.setenv("OPENROUTER_GRAPHITI_MODEL", "qwen/graph-test")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "qwen/chat-test")
    monkeypatch.setenv("OPENROUTER_EMBEDDING_MODEL", "perplexity/embed-test")
    monkeypatch.setenv("OPENROUTER_EMBEDDING_DIMENSIONS", "2")


@pytest.mark.parametrize(
    ("text_provider", "embedding_provider"),
    [
        ("ollama", "ollama"),
        ("ollama", "openrouter"),
        ("openrouter", "ollama"),
        ("openrouter", "openrouter"),
    ],
)
def test_graphiti_provider_matrix_constructs_independent_clients(
    monkeypatch, text_provider, embedding_provider
):
    _configure(monkeypatch, text_provider, embedding_provider)

    llm = get_graphiti_llm_client()
    embedding = get_graphiti_embedding_client()
    summary = get_graphiti_config_summary()

    assert llm.client.max_retries == 0
    assert isinstance(llm, SingleAttemptOpenAIGenericClient)
    assert isinstance(embedding, ProviderGraphitiEmbedder)
    assert summary["text_provider"] == text_provider
    assert summary["embedding_provider"] == embedding_provider
    assert summary["embedding_dim"] == 2
    if embedding_provider == "ollama":
        assert isinstance(embedding.embedder, OllamaEmbedder)
    else:
        assert isinstance(embedding.embedder, OpenRouterEmbedder)
        assert embedding.embedder.client.max_retries == 0
    assert "offline-unit-test-secret" not in str(summary)


@pytest.mark.asyncio
async def test_graphiti_openrouter_transport_injects_fixed_routing(monkeypatch):
    _configure(monkeypatch, "openrouter", "ollama")
    captured = {}

    async def original_create(*args, **kwargs):
        captured.update(kwargs)
        return "response"

    fake_transport = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=original_create)),
        max_retries=0,
    )
    monkeypatch.setattr(
        "src.graphiti.provider_config.AsyncOpenAI",
        lambda **kwargs: fake_transport,
    )

    llm = get_graphiti_llm_client()
    result = await llm.client.chat.completions.create(
        model="qwen/graph-test",
        messages=[{"role": "user", "content": "test"}],
    )

    assert result == "response"
    assert captured["extra_body"] == {
        "provider": {
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
        }
    }
