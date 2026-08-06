"""Graphiti configuration for Ollama and multi-provider support."""

import logging
import os

from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import (  # For Ollama compatibility
    OpenAIGenericClient,
)
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def _graphiti_openai_transport(*, api_key: str, base_url: str | None = None) -> AsyncOpenAI:
    """Build a one-request transport so durable call accounting stays authoritative."""
    timeout = float(os.getenv("GRAPHITI_REQUEST_TIMEOUT", "600"))
    if timeout <= 0:
        raise ValueError("GRAPHITI_REQUEST_TIMEOUT must be positive")
    options = {
        "api_key": api_key,
        "max_retries": 0,
        "timeout": timeout,
    }
    if base_url is not None:
        options["base_url"] = base_url
    return AsyncOpenAI(**options)


def get_graphiti_llm_client(verbose: bool = False) -> LLMClient:
    """
    Get configured Graphiti LLM client based on provider.

    Supports:
    - Ollama via OpenAI-compatible API
    - OpenAI direct

    The provider can be overridden with GRAPHITI_PROVIDER env var,
    otherwise uses LLM_PROVIDER.

    Args:
        verbose: Enable verbose logging

    Returns:
        Configured LLM client for Graphiti
    """
    # Check for Graphiti-specific provider override
    provider = os.getenv("GRAPHITI_PROVIDER", os.getenv("LLM_PROVIDER", "ollama")).lower()

    if verbose:
        logger.info("Initializing Graphiti LLM client")

    if provider == "ollama":
        # Ollama configuration using OpenAI-compatible endpoints
        # NOTE: Use OpenAIGenericClient (not OpenAIClient) because:
        # - OpenAIClient uses client.responses.parse (OpenAI Responses API)
        # - OpenAIGenericClient uses client.chat.completions.create (standard API)
        # - Ollama only supports the standard chat completions API
        base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
        # Add /v1 suffix for OpenAI compatibility
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        # Graphiti requires reliable structured JSON. Qwen supports constrained
        # output without spending the response budget on a hidden reasoning trace.
        model = os.getenv("OLLAMA_REASONING_MODEL", "qwen2.5:3b")
        temperature = float(os.getenv("OLLAMA_EXTRACTION_TEMPERATURE", "0.3"))

        llm_config = LLMConfig(
            api_key="ollama",  # Placeholder (not actually used by Ollama)
            model=model,
            small_model=model,  # Use same model for all tasks
            base_url=base_url,
            temperature=temperature,
            max_tokens=8192,
        )

        if verbose:
            logger.info("  Custom LLM base URL configured")
            logger.info(f"  Temperature: {temperature}")
            logger.info("  Client: OpenAIGenericClient (chat.completions API)")

        transport = _graphiti_openai_transport(api_key="ollama", base_url=base_url)
        return OpenAIGenericClient(config=llm_config, client=transport, max_tokens=8192)

    elif provider == "openai":
        # OpenAI configuration
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable required for OpenAI provider")

        model = os.getenv("GRAPHITI_LLM_MODEL", "gpt-4o-mini")
        temperature = float(os.getenv("GRAPHITI_EXTRACTION_TEMPERATURE", "0.3"))

        llm_config = LLMConfig(
            api_key=api_key,
            model=model,
            small_model=model,
            temperature=temperature,
            max_tokens=8192,
        )

        if verbose:
            logger.info(f"  Temperature: {temperature}")

        transport = _graphiti_openai_transport(api_key=api_key)
        return OpenAIGenericClient(config=llm_config, client=transport, max_tokens=8192)

    else:
        raise ValueError("Unknown Graphiti provider; use 'ollama' or 'openai'")


def get_graphiti_embedding_client(verbose: bool = False) -> EmbedderClient:
    """
    Get configured Graphiti embedding client.

    Supports:
    - Ollama embeddings via OpenAI-compatible API
    - OpenAI embeddings

    The provider can be overridden with GRAPHITI_PROVIDER env var,
    otherwise uses LLM_PROVIDER.

    Args:
        verbose: Enable verbose logging

    Returns:
        Configured embedding client for Graphiti
    """
    # Check for Graphiti-specific provider override
    provider = os.getenv("GRAPHITI_PROVIDER", os.getenv("LLM_PROVIDER", "ollama")).lower()

    if verbose:
        logger.info("Initializing Graphiti embedding client")

    if provider == "ollama":
        # Ollama configuration using OpenAI-compatible endpoints
        base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
        # Add /v1 suffix for OpenAI compatibility
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

        # nomic-embed-text produces 768-dimensional embeddings
        embedding_dim = 768

        embedding_config = OpenAIEmbedderConfig(
            api_key="ollama",  # Placeholder (not actually used by Ollama)
            embedding_model=model,
            embedding_dim=embedding_dim,
            base_url=base_url,
        )

        if verbose:
            logger.info("  Custom embedding base URL configured")
            logger.info(f"  Dimension: {embedding_dim}")

        return OpenAIEmbedder(config=embedding_config)

    elif provider == "openai":
        # OpenAI configuration
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable required for OpenAI provider")

        model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

        # text-embedding-3-small produces 1536-dimensional embeddings
        embedding_dim = 1536

        embedding_config = OpenAIEmbedderConfig(
            api_key=api_key,
            embedding_model=model,
            embedding_dim=embedding_dim,
        )

        if verbose:
            logger.info(f"  Dimension: {embedding_dim}")

        return OpenAIEmbedder(config=embedding_config)

    else:
        raise ValueError("Unknown embedding provider; use 'ollama' or 'openai'")


def get_graphiti_config_summary() -> dict:
    """
    Get a summary of current Graphiti configuration.

    Useful for debugging and logging.

    Returns:
        Configuration summary dictionary
    """
    provider = os.getenv("GRAPHITI_PROVIDER", os.getenv("LLM_PROVIDER", "ollama")).lower()

    if provider == "ollama":
        return {
            "provider": "ollama",
            "llm_model": os.getenv("OLLAMA_REASONING_MODEL", "qwen2.5:3b"),
            "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            "temperature": float(os.getenv("OLLAMA_EXTRACTION_TEMPERATURE", "0.3")),
            "embedding_dim": 768,
        }
    else:
        return {
            "provider": "openai",
            "llm_model": os.getenv("GRAPHITI_LLM_MODEL", "gpt-4o-mini"),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            "temperature": float(os.getenv("GRAPHITI_EXTRACTION_TEMPERATURE", "0.3")),
            "embedding_dim": 1536,
        }
