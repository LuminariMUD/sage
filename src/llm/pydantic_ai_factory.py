"""Provider-neutral PydanticAI model construction without environment mutation."""

from __future__ import annotations

import warnings

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider

from src.llm.config import get_text_route
from src.llm.provider_config import TextModelCandidate, TextTask


def _openai_compatible_base_url(candidate: TextModelCandidate) -> str:
    base_url = candidate.connection.base_url
    if candidate.connection.provider == "ollama" and not base_url.endswith("/v1"):
        return f"{base_url}/v1"
    return base_url


def create_text_model(
    task: TextTask = "chat",
    *,
    candidate: TextModelCandidate | None = None,
    legacy_openai_api_key: str | None = None,
    legacy_openai_model: str = "gpt-4o",
) -> OpenAIChatModel:
    """Create a PydanticAI model from a validated provider-neutral candidate.

    ``legacy_openai_api_key`` preserves positional constructor compatibility for
    legacy agents during the deprecation window. New callers should omit it and
    configure the selected provider through the shared settings contract.
    """
    if legacy_openai_api_key:
        if candidate is not None:
            raise ValueError("candidate and legacy_openai_api_key cannot be configured together")
        warnings.warn(
            "Passing an OpenAI API key into an agent constructor is deprecated; "
            "configure the shared text provider instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return create_openai_chat_model(legacy_openai_api_key, legacy_openai_model)

    selected = candidate or get_text_route(task).primary
    secret = selected.connection.api_key
    api_key = secret.get_secret_value() if secret else "ollama"
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=_openai_compatible_base_url(selected),
        timeout=selected.connection.timeout_seconds,
        max_retries=selected.connection.transport_retry.maximum_attempts - 1,
        default_headers=selected.connection.default_headers,
    )
    settings = OpenAIChatModelSettings(
        temperature=selected.temperature,
        timeout=selected.connection.timeout_seconds,
        extra_body=selected.provider_request_body() or None,
    )
    return OpenAIChatModel(
        selected.model,
        provider=PydanticOpenAIProvider(openai_client=client),
        settings=settings,
    )


def create_openai_chat_model(
    api_key: str,
    model_name: str = "gpt-4o",
) -> OpenAIChatModel:
    """Deprecated direct-OpenAI compatibility wrapper for existing imports."""
    if not api_key:
        raise ValueError("OpenAI API key is required")
    client = AsyncOpenAI(api_key=api_key)
    return OpenAIChatModel(
        model_name,
        provider=PydanticOpenAIProvider(openai_client=client),
    )
