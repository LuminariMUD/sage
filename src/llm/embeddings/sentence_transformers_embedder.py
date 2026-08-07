"""Sentence Transformers embedding model implementation."""

import asyncio

from sentence_transformers import SentenceTransformer

from src.llm.config import get_embedding_profile
from src.llm.embeddings.base import BaseEmbedder
from src.llm.embeddings.validation import validate_embedding_batch
from src.llm.provider_config import EmbeddingProfile


class SentenceTransformersEmbedder(BaseEmbedder):
    """Local sentence-transformers embedding model."""

    def __init__(self, profile: EmbeddingProfile | None = None):
        """Initialize Sentence Transformers embedder."""
        self.profile = profile or get_embedding_profile()
        if self.profile.connection.provider != "sentence-transformers":
            raise ValueError(
                "SentenceTransformersEmbedder requires a Sentence Transformers profile"
            )
        self.model_name = self.profile.model
        self.dimension = self.profile.dimensions
        self.model = SentenceTransformer(self.model_name, revision=self.profile.revision)

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        # Run in executor to avoid blocking async loop
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None, lambda: self.model.encode(text, show_progress_bar=False)
        )
        return validate_embedding_batch(
            [embedding.tolist()], expected_count=1, dimensions=self.dimension
        )[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # Run in executor to avoid blocking async loop
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: self.model.encode(texts, show_progress_bar=False)
        )
        return validate_embedding_batch(
            embeddings.tolist(), expected_count=len(texts), dimensions=self.dimension
        )

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Dimension of embedding vectors
        """
        return self.dimension
