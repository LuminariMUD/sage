"""Abstract base classes for LLM providers and embedders."""

import warnings
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: Input text prompt
            model: Model name (uses default if None)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text completion
        """

    @abstractmethod
    async def stream(
        self, prompt: str, model: str | None = None, temperature: float = 0.7, **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion tokens as they're generated.

        Args:
            prompt: Input text prompt
            model: Model name (uses default if None)
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters

        Yields:
            Text tokens as they're generated
        """

    async def embed(self, text: str | list[str], **kwargs) -> list[float] | list[list[float]]:
        """Deprecated compatibility shim delegated to the embedding factory."""
        warnings.warn(
            "Embedding through a text provider is deprecated; use get_embedder()",
            DeprecationWarning,
            stacklevel=2,
        )
        if kwargs:
            raise TypeError("Text-provider embedding compatibility does not accept options")
        from src.llm.embeddings.factory import get_embedder

        embedder = get_embedder()
        if isinstance(text, list):
            return await embedder.embed_batch(text)
        return await embedder.embed_text(text)

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """
        Get information about the current model configuration.

        Returns:
            Dict with model name, context length, capabilities, etc.
        """


class BaseEmbedder(ABC):
    """Abstract base class for embedding models."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this embedder.

        Returns:
            Embedding dimension (e.g., 384, 768, 1536)
        """
