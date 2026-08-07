"""Profile-aware embedding adapter factory."""

from __future__ import annotations

from src.llm.cache import embedder_cache
from src.llm.config import get_embedding_profile
from src.llm.embeddings.base import BaseEmbedder
from src.llm.provider_config import EmbeddingProfile


def create_embedder(
    profile: EmbeddingProfile,
    *,
    transport_max_retries: int | None = None,
) -> BaseEmbedder:
    """Construct one embedding adapter from a validated profile."""
    provider = profile.connection.provider
    if provider == "ollama":
        from src.llm.embeddings.ollama_embedder import OllamaEmbedder

        if transport_max_retries not in {None, 0}:
            raise ValueError("Ollama native embedder owns no hidden transport retries")
        return OllamaEmbedder(profile)
    if provider == "openrouter":
        from src.llm.embeddings.openrouter_embedder import OpenRouterEmbedder

        return OpenRouterEmbedder(profile, transport_max_retries=transport_max_retries)
    if provider == "openai":
        from src.llm.embeddings.openai_embedder import OpenAIEmbedder

        return OpenAIEmbedder(profile, transport_max_retries=transport_max_retries)
    if provider == "sentence-transformers":
        from src.llm.embeddings.sentence_transformers_embedder import (
            SentenceTransformersEmbedder,
        )

        if transport_max_retries is not None:
            raise ValueError("Sentence Transformers has no HTTP transport retries")
        return SentenceTransformersEmbedder(profile)
    raise ValueError(f"Unknown embedding provider: {provider}")


def get_embedder(
    force_refresh: bool = False,
    *,
    profile: EmbeddingProfile | None = None,
) -> BaseEmbedder:
    """Return an embedder cached by vector profile and credential identity."""
    selected = profile or get_embedding_profile()
    cache_key = (selected.fingerprint, selected.connection.cache_identity())
    if force_refresh:
        embedder_cache.pop(cache_key, None)
    if cache_key not in embedder_cache:
        embedder_cache[cache_key] = create_embedder(selected)
    return embedder_cache[cache_key]


def reset_embedder_cache() -> None:
    """Clear all cached embedding profiles."""
    embedder_cache.clear()
