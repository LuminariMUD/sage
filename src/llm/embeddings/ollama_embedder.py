"""Batch-capable Ollama embedding adapter using the modern native endpoint."""

from __future__ import annotations

from typing import Any

import aiohttp

from src.llm.config import get_embedding_profile
from src.llm.embeddings.base import BaseEmbedder
from src.llm.embeddings.validation import EmbeddingValidationError, validate_embedding_batch
from src.llm.provider_config import EmbeddingProfile


class OllamaEmbedder(BaseEmbedder):
    """Validated Ollama `/api/embed` client."""

    def __init__(self, profile: EmbeddingProfile | None = None):
        self.profile = profile or get_embedding_profile()
        if self.profile.connection.provider != "ollama":
            raise ValueError("OllamaEmbedder requires an Ollama embedding profile")
        self.base_url = self.profile.connection.base_url
        self.model = self.profile.model
        self.dimension = self.profile.dimensions
        self.batch_size = self.profile.batch_size
        self.timeout = aiohttp.ClientTimeout(total=self.profile.connection.timeout_seconds)

    async def _request_batch(
        self, session: aiohttp.ClientSession, texts: list[str]
    ) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimension,
            "truncate": False,
        }
        async with session.post(f"{self.base_url}/api/embed", json=payload) as response:
            if response.status != 200:
                raise RuntimeError(f"Ollama embedding request failed with status {response.status}")
            result = await response.json()
        if not isinstance(result, dict) or not isinstance(result.get("embeddings"), list):
            raise EmbeddingValidationError("Ollama embedding response is malformed")
        return validate_embedding_batch(
            result["embeddings"],
            expected_count=len(texts),
            dimensions=self.dimension,
        )

    async def embed_text(self, text: str) -> list[float]:
        """Generate and validate one embedding."""
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Send true batches without dropping or reordering any input."""
        if not texts:
            return []
        if any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")
        embeddings: list[list[float]] = []
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            for start in range(0, len(texts), self.batch_size):
                batch = texts[start : start + self.batch_size]
                embeddings.extend(await self._request_batch(session, batch))
        return embeddings

    def get_dimension(self) -> int:
        return self.dimension
