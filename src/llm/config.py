"""Compatibility accessors over the typed provider configuration boundary."""

from __future__ import annotations

import os
from typing import Any, cast

from src.llm.provider_config import (
    EmbeddingProfile,
    ProviderSettings,
    TextRouteProfile,
    TextTask,
    is_text_profile_ready,
    resolve_embedding_profile,
    resolve_provider_settings,
)

_TASK_ALIASES: dict[str, TextTask] = {
    "chat": "chat",
    "qa": "chat",
    "factual": "chat",
    "creative": "creative",
    "brainstorm": "creative",
    "reasoning": "reasoning",
    "extraction": "extraction",
    "tools": "tools",
}


def _text_task(task: str) -> TextTask:
    try:
        return _TASK_ALIASES[task.lower()]
    except KeyError as error:
        raise ValueError(f"Unknown text task: {task}") from error


def get_provider_settings() -> ProviderSettings:
    """Resolve the complete immutable provider configuration."""
    return resolve_provider_settings()


def get_text_route(task: str = "chat") -> TextRouteProfile:
    """Return the active ordered route for one application text task."""
    return get_provider_settings().text_route(_text_task(task))


def get_embedding_profile() -> EmbeddingProfile:
    """Return the active application embedding profile."""
    return get_provider_settings().embedding_profile


def get_embedding_profile_for_provider(provider: str) -> EmbeddingProfile:
    """Resolve an evaluation profile without changing the active selector."""
    return resolve_embedding_profile(provider, os.environ)


def get_graphiti_text_route() -> TextRouteProfile:
    """Return Graphiti's independently resolved extraction route."""
    return get_provider_settings().graphiti_text_route


def get_graphiti_embedding_profile() -> EmbeddingProfile:
    """Return Graphiti's independently resolved embedding profile."""
    return get_provider_settings().graphiti_embedding_profile


def get_llm_provider_config() -> dict[str, Any]:
    """Return the deprecated dictionary view used by transitional call sites."""
    settings = get_provider_settings()
    routes = settings.text_routes
    chat = routes["chat"].primary
    secret = chat.connection.api_key
    if settings.text_provider == "ollama":
        legacy_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    elif settings.text_provider == "openrouter":
        legacy_embedding_model = os.getenv("OPENROUTER_EMBEDDING_MODEL", "")
    else:
        legacy_embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    return {
        "provider": settings.text_provider,
        "base_url": chat.connection.base_url,
        "api_key": secret.get_secret_value() if secret else None,
        "chat_model": routes["chat"].primary.model,
        "creative_model": routes["creative"].primary.model,
        "reasoning_model": routes["reasoning"].primary.model,
        "extraction_model": routes["extraction"].primary.model,
        "tools_model": routes["tools"].primary.model,
        "embedding_model": legacy_embedding_model,
        "temperature": chat.temperature,
        "max_context_tokens": chat.context_limit,
        "timeout": chat.connection.timeout_seconds,
        "max_tokens": None,
        "candidate_fingerprint": chat.fingerprint,
    }


def get_embedding_config() -> dict[str, Any]:
    """Return the deprecated dictionary view of the embedding profile."""
    profile = get_embedding_profile()
    secret = profile.connection.api_key
    return {
        "provider": profile.connection.provider,
        "model": profile.model,
        "base_url": profile.connection.base_url,
        "api_key": secret.get_secret_value() if secret else None,
        "batch_size": profile.batch_size,
        "dimension": profile.dimensions,
        "dimensions": profile.dimensions,
        "encoding_format": profile.encoding_format,
        "revision": profile.revision,
        "fingerprint": profile.fingerprint,
    }


def get_model_for_task(task: str) -> str:
    """Return the active model for a text task or the embedding capability."""
    if task.lower() == "embedding":
        return get_embedding_profile().model
    return get_text_route(task).primary.model


def get_temperature_for_task(task: str) -> float:
    """Return the active candidate temperature for a legacy or canonical task."""
    return get_text_route(task).primary.temperature


def get_prompt_profile_for_task(task: str) -> str:
    """Return model-family prompt selection independent of transport provider."""
    return get_text_route(task).primary.prompt_profile


def text_profile_is_ready(task: str = "chat") -> bool:
    """Compatibility wrapper for shared provider readiness checks."""
    try:
        normalized = _text_task(task)
    except ValueError:
        return False
    return is_text_profile_ready(cast(TextTask, normalized))
