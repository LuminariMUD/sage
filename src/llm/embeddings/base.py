"""Base class for embedding models."""

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Abstract base class for embedding models."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Get the embedding dimension for this model.

        Returns:
            Dimension of embedding vectors
        """
