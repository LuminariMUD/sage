"""OpenRouter embeddings adapter using the installed OpenAI-compatible client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from openai import AsyncOpenAI

from src.llm.config import get_embedding_profile
from src.llm.embeddings.base import BaseEmbedder
from src.llm.embeddings.validation import EmbeddingValidationError, validate_embedding_batch
from src.llm.provider_config import EmbeddingProfile


class OpenRouterEmbedder(BaseEmbedder):
    """Validated, ordered, no-cross-model-fallback OpenRouter embedder."""

    def __init__(
        self,
        profile: EmbeddingProfile | None = None,
        *,
        transport_max_retries: int | None = None,
    ):
        self.profile = profile or get_embedding_profile()
        if self.profile.connection.provider != "openrouter":
            raise ValueError("OpenRouterEmbedder requires an OpenRouter embedding profile")
        secret = self.profile.connection.api_key
        if secret is None:  # Protected by ProviderConnection validation.
            raise ValueError("OpenRouter API credentials are required")
        retry_count = (
            self.profile.connection.transport_retry.maximum_attempts - 1
            if transport_max_retries is None
            else transport_max_retries
        )
        if retry_count < 0:
            raise ValueError("Transport retries cannot be negative")
        self.client = AsyncOpenAI(
            api_key=secret.get_secret_value(),
            base_url=self.profile.connection.base_url,
            timeout=self.profile.connection.timeout_seconds,
            max_retries=retry_count,
            default_headers=self.profile.connection.default_headers,
        )
        self.model = self.profile.model
        self.dimension = self.profile.dimensions
        self.batch_size = self.profile.batch_size
        self.last_usage: dict[str, int] = {}
        self.last_actual_model: str | None = None

    def _extra_body(self) -> dict[str, object]:
        body = self.profile.provider_request_body()
        if self.profile.input_type:
            body["input_type"] = self.profile.input_type
        return body

    async def _request_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimension,
            encoding_format="float",
            extra_body=self._extra_body(),
        )
        actual_model = getattr(response, "model", None)
        if actual_model and actual_model != self.model:
            raise EmbeddingValidationError("Embedding response model does not match profile")
        indexed: dict[int, list[float]] = {}
        for item in response.data:
            index = getattr(item, "index", None)
            vector = getattr(item, "embedding", None)
            if not isinstance(index, int) or index in indexed:
                raise EmbeddingValidationError("Embedding response indices are invalid")
            indexed[index] = vector
        if set(indexed) != set(range(len(texts))):
            raise EmbeddingValidationError("Embedding response indices do not match request order")
        usage = getattr(response, "usage", None)
        usage_dump = getattr(usage, "model_dump", None)
        dumped = usage_dump() if callable(usage_dump) else {}
        if isinstance(dumped, Mapping):
            self.last_usage = {
                str(key): value
                for key, value in dumped.items()
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            }
        self.last_actual_model = actual_model
        return validate_embedding_batch(
            (indexed[index] for index in range(len(texts))),
            expected_count=len(texts),
            dimensions=self.dimension,
        )

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            embeddings.extend(await self._request_batch(texts[start : start + self.batch_size]))
        return embeddings

    def get_dimension(self) -> int:
        return self.dimension

    def sanitized_metadata(self) -> dict[str, Any]:
        return {
            "profile_fingerprint": self.profile.fingerprint,
            "requested_model": self.model,
            "actual_model": self.last_actual_model,
            "usage": dict(self.last_usage),
        }
