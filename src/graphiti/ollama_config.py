"""Deprecated import shim for provider-neutral Graphiti configuration."""

from src.graphiti.provider_config import (
    ProviderGraphitiEmbedder,
    create_graphiti_llm_client,
    get_graphiti_config_summary,
    get_graphiti_embedding_client,
    get_graphiti_llm_client,
)

__all__ = [
    "ProviderGraphitiEmbedder",
    "create_graphiti_llm_client",
    "get_graphiti_config_summary",
    "get_graphiti_embedding_client",
    "get_graphiti_llm_client",
]
