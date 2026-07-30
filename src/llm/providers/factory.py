"""Provider factory for LLM provider selection."""

from src.llm.base import BaseLLMProvider
from src.llm.config import get_llm_provider_config
from src.llm.providers.ollama_provider import OllamaProvider
from src.llm.providers.openai_provider import OpenAIProvider

# Singleton instance cache
_provider_cache: BaseLLMProvider | None = None


def get_llm_provider(force_refresh: bool = False) -> BaseLLMProvider:
    """
    Get configured LLM provider (singleton pattern).

    Args:
        force_refresh: If True, recreate provider instance

    Returns:
        Configured LLM provider instance
    """
    global _provider_cache

    if _provider_cache is None or force_refresh:
        config = get_llm_provider_config()
        provider_type = config["provider"]

        if provider_type == "ollama":
            _provider_cache = OllamaProvider()
        elif provider_type == "openai":
            _provider_cache = OpenAIProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_type}")

    return _provider_cache


def reset_provider_cache():
    """Reset the provider cache (useful for testing)."""
    global _provider_cache
    _provider_cache = None
