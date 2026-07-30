"""Factory for embedding model selection."""

from src.llm.config import get_embedding_config
from src.llm.embeddings.base import BaseEmbedder
from src.llm.embeddings.ollama_embedder import OllamaEmbedder
from src.llm.embeddings.openai_embedder import OpenAIEmbedder
from src.llm.embeddings.sentence_transformers_embedder import SentenceTransformersEmbedder

_embedder_cache: BaseEmbedder | None = None


def get_embedder(force_refresh: bool = False) -> BaseEmbedder:
    """
    Get configured embedder (singleton pattern).

    Args:
        force_refresh: Recreate embedder instance

    Returns:
        Configured embedder
    """
    global _embedder_cache

    if _embedder_cache is None or force_refresh:
        config = get_embedding_config()
        provider = config["provider"]

        if provider == "ollama":
            _embedder_cache = OllamaEmbedder()
        elif provider == "openai":
            _embedder_cache = OpenAIEmbedder()
        elif provider == "sentence-transformers":
            _embedder_cache = SentenceTransformersEmbedder()
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")

    return _embedder_cache
