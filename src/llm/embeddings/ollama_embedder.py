"""Ollama embedding model implementation."""

import aiohttp

from src.llm.config import get_embedding_config
from src.llm.embeddings.base import BaseEmbedder


class OllamaEmbedder(BaseEmbedder):
    """Ollama local embedding model."""

    def __init__(self):
        """Initialize Ollama embedder."""
        self.config = get_embedding_config()
        self.base_url = self.config["base_url"]
        self.model = self.config["model"]  # nomic-embed-text
        self.dimension = self.config["dimension"]  # 768 for nomic-embed-text
        self.batch_size = self.config.get("batch_size", 32)
        self.timeout = aiohttp.ClientTimeout(total=60)

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": text}
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama embedding request failed with status {response.status}"
                    )

                result = await response.json()
                return result["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []

        # Process in batches to avoid overwhelming Ollama
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Process batch items
                batch_embeddings = []
                for text in batch:
                    async with session.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(
                                f"Ollama embedding request failed with status {response.status}"
                            )

                        result = await response.json()
                        batch_embeddings.append(result["embedding"])

                embeddings.extend(batch_embeddings)

        return embeddings

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Dimension of embedding vectors
        """
        return self.dimension
