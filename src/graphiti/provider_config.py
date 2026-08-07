"""Provider-neutral Graphiti client construction from validated Sage profiles."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from typing import Any

from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from openai import AsyncOpenAI

from src.llm.config import get_graphiti_embedding_profile, get_graphiti_text_route
from src.llm.embeddings.factory import create_embedder
from src.llm.provider_config import EmbeddingProfile, TextModelCandidate

logger = logging.getLogger(__name__)


def _positive_output_tokens() -> int:
    raw = os.getenv("GRAPHITI_MAX_OUTPUT_TOKENS", "4096")
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("GRAPHITI_MAX_OUTPUT_TOKENS must be an integer") from error
    if not 1 <= value <= 1_000_000:
        raise ValueError("GRAPHITI_MAX_OUTPUT_TOKENS must be between 1 and 1000000")
    return value


def _openai_base_url(candidate: TextModelCandidate) -> str:
    base_url = candidate.connection.base_url
    if candidate.connection.provider == "ollama" and not base_url.endswith("/v1"):
        return f"{base_url}/v1"
    return base_url


def _merge_openrouter_body(candidate: TextModelCandidate, supplied: object) -> dict[str, object]:
    configured = candidate.provider_request_body()
    if supplied is None:
        return configured
    if not isinstance(supplied, Mapping):
        raise TypeError("extra_body must be a mapping")
    merged = dict(supplied)
    supplied_policy = merged.get("provider")
    if supplied_policy is not None and supplied_policy != configured.get("provider"):
        raise ValueError("Graphiti cannot override configured OpenRouter routing")
    merged.update(configured)
    return merged


def _graphiti_transport(candidate: TextModelCandidate) -> AsyncOpenAI:
    """Build a no-hidden-retry transport for durable provider accounting."""
    secret = candidate.connection.api_key
    api_key = secret.get_secret_value() if secret else "ollama"
    transport = AsyncOpenAI(
        api_key=api_key,
        base_url=_openai_base_url(candidate),
        timeout=candidate.connection.timeout_seconds,
        max_retries=0,
        default_headers=candidate.connection.default_headers,
    )
    if candidate.connection.provider == "openrouter":
        create = transport.chat.completions.create

        async def create_with_routing(*args: Any, **kwargs: Any) -> Any:
            kwargs["extra_body"] = _merge_openrouter_body(candidate, kwargs.get("extra_body"))
            return await create(*args, **kwargs)

        transport.chat.completions.create = create_with_routing
    return transport


class ProviderGraphitiEmbedder(EmbedderClient):
    """Adapt Sage's validated batch interface to Graphiti's embedder contract."""

    def __init__(self, profile: EmbeddingProfile):
        self.profile = profile
        self.embedder = create_embedder(profile, transport_max_retries=0)

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        if isinstance(input_data, str):
            return await self.embedder.embed_text(input_data)
        if (
            isinstance(input_data, list)
            and input_data
            and all(isinstance(value, str) for value in input_data)
        ):
            return (await self.embedder.embed_batch(input_data))[0]
        raise TypeError("Graphiti embedding input must contain text")

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await self.embedder.embed_batch(input_data_list)


def get_graphiti_llm_client(verbose: bool = False) -> LLMClient:
    """Construct Graphiti's primary extraction client from its independent route."""
    route = get_graphiti_text_route()
    candidate = route.primary
    if "structured_output" not in candidate.capabilities:
        raise ValueError("Graphiti extraction candidate lacks structured-output capability")
    max_tokens = _positive_output_tokens()
    secret = candidate.connection.api_key
    api_key = secret.get_secret_value() if secret else "ollama"
    llm_config = LLMConfig(
        api_key=api_key,
        model=candidate.model,
        small_model=candidate.model,
        base_url=_openai_base_url(candidate),
        temperature=candidate.temperature,
        max_tokens=max_tokens,
    )
    if verbose:
        logger.info(
            "Initializing Graphiti text route provider=%s model=%s route=%s",
            candidate.connection.provider,
            candidate.model,
            route.fingerprint,
        )
    return OpenAIGenericClient(
        config=llm_config,
        client=_graphiti_transport(candidate),
        max_tokens=max_tokens,
    )


def get_graphiti_embedding_client(verbose: bool = False) -> EmbedderClient:
    """Construct Graphiti's independently selected embedding client."""
    profile = get_graphiti_embedding_profile()
    if verbose:
        logger.info(
            "Initializing Graphiti embedding profile provider=%s model=%s dimensions=%s profile=%s",
            profile.connection.provider,
            profile.model,
            profile.dimensions,
            profile.fingerprint,
        )
    return ProviderGraphitiEmbedder(profile)


def get_graphiti_config_summary() -> dict[str, object]:
    """Return a secret-free summary with text and embedding identities separated."""
    route = get_graphiti_text_route()
    profile = get_graphiti_embedding_profile()
    return {
        "provider": route.primary.connection.provider,
        "text_provider": route.primary.connection.provider,
        "embedding_provider": profile.connection.provider,
        "llm_model": route.primary.model,
        "embedding_model": profile.model,
        "temperature": route.primary.temperature,
        "embedding_dim": profile.dimensions,
        "route_fingerprint": route.fingerprint,
        "candidate_fingerprints": [candidate.fingerprint for candidate in route.candidates],
        "embedding_profile_fingerprint": profile.fingerprint,
        "maximum_provider_calls": route.maximum_provider_calls,
    }
