"""OpenAI embedding model implementation."""

from openai import AsyncOpenAI

from src.llm.config import get_embedding_config
from src.llm.embeddings.base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI cloud embedding model."""

    def __init__(self):
        """Initialize OpenAI embedder."""
        config = get_embedding_config()
        self.model = config["model"]
        self.dimension = config["dimension"]
        self.client = AsyncOpenAI(api_key=config["api_key"])

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        response = await self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # OpenAI API handles batching efficiently
        response = await self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Dimension of embedding vectors
        """
        return self.dimension
