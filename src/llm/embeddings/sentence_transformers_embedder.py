"""Sentence Transformers embedding model implementation."""

import asyncio
import os

from sentence_transformers import SentenceTransformer

from src.llm.config import get_embedding_config
from src.llm.embeddings.base import BaseEmbedder


class SentenceTransformersEmbedder(BaseEmbedder):
    """Local sentence-transformers embedding model."""

    def __init__(self):
        """Initialize Sentence Transformers embedder."""
        self.config = get_embedding_config()
        self.model_name = self.config["model"]
        self.dimension = self.config["dimension"]
        revision = os.getenv("SAGE_SENTENCE_TRANSFORMERS_REVISION")
        self.model = SentenceTransformer(self.model_name, revision=revision)

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
        return embedding.tolist()

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
        return embeddings.tolist()

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Dimension of embedding vectors
        """
        return self.dimension
