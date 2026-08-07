"""Profile-aware factory for single-candidate text adapters."""

from __future__ import annotations

from src.llm.base import BaseLLMProvider
from src.llm.cache import reset_provider_caches, text_provider_cache
from src.llm.config import get_text_route
from src.llm.provider_config import TextModelCandidate, TextTask
from src.llm.providers.ollama_provider import OllamaProvider
from src.llm.providers.openai_provider import OpenAIProvider
from src.llm.providers.openrouter_provider import OpenRouterProvider


def create_text_provider(candidate: TextModelCandidate) -> BaseLLMProvider:
    """Construct exactly one single-call adapter from a validated candidate."""
    provider_type = candidate.connection.provider
    if provider_type == "ollama":
        return OllamaProvider(candidate)
    if provider_type == "openrouter":
        return OpenRouterProvider(candidate)
    if provider_type == "openai":
        return OpenAIProvider(candidate)
    raise ValueError(f"Unknown text provider: {provider_type}")


def get_llm_provider(
    force_refresh: bool = False,
    *,
    task: TextTask = "chat",
    candidate: TextModelCandidate | None = None,
) -> BaseLLMProvider:
    """Return a provider cached by secret-free profile and credential identity."""
    selected = candidate or get_text_route(task).primary
    cache_key = (selected.fingerprint, selected.connection.cache_identity())
    if force_refresh:
        text_provider_cache.pop(cache_key, None)
    if cache_key not in text_provider_cache:
        text_provider_cache[cache_key] = create_text_provider(selected)
    return text_provider_cache[cache_key]


def get_text_provider(task: TextTask = "chat", *, force_refresh: bool = False) -> BaseLLMProvider:
    """Provider-neutral name for the legacy get_llm_provider entrypoint."""
    return get_llm_provider(force_refresh=force_refresh, task=task)


def reset_provider_cache() -> None:
    """Clear every provider capability cache for deterministic tests/reloads."""
    reset_provider_caches()
