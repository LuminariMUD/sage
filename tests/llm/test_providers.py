"""Unit tests for LLM providers."""

import pytest

from src.llm.providers.factory import get_llm_provider, reset_provider_cache
from src.llm.providers.ollama_provider import OllamaProvider
from src.llm.providers.openai_provider import OpenAIProvider
from src.llm.providers.openrouter_provider import OpenRouterProvider


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset provider cache before each test."""
    reset_provider_cache()
    yield
    reset_provider_cache()


def test_factory_returns_ollama_provider(monkeypatch):
    """Test factory returns OllamaProvider when configured."""
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)


def test_factory_returns_openai_provider(monkeypatch):
    """Test factory returns OpenAIProvider when configured."""
    monkeypatch.setenv("TEXT_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")

    provider = get_llm_provider()
    assert isinstance(provider, OpenAIProvider)


def test_factory_returns_openrouter_provider(monkeypatch):
    """Test factory returns OpenRouterProvider only when explicitly selected."""
    monkeypatch.setenv("TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-key")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "qwen/qwen-test")

    provider = get_llm_provider()
    assert isinstance(provider, OpenRouterProvider)


def test_factory_caches_provider(monkeypatch):
    """Test factory returns same instance (singleton)."""
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")

    provider1 = get_llm_provider()
    provider2 = get_llm_provider()
    assert provider1 is provider2


def test_factory_force_refresh(monkeypatch):
    """Test factory recreates provider when forced."""
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")

    provider1 = get_llm_provider()
    provider2 = get_llm_provider(force_refresh=True)
    assert provider1 is not provider2


def test_ollama_provider_initialization(monkeypatch):
    """Test OllamaProvider initializes correctly."""
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://test:11434")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")

    provider = OllamaProvider()
    assert provider.base_url == "http://test:11434"
    assert provider.default_model == "qwen2.5:7b"


def test_provider_get_model_info(monkeypatch):
    """Test provider returns model info."""
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")

    provider = get_llm_provider()
    info = provider.get_model_info()

    assert "provider" in info
    assert info["provider"] == "ollama"


def test_factory_raises_for_unknown_provider(monkeypatch):
    """Test factory raises error for unknown provider."""
    monkeypatch.setenv("TEXT_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="TEXT_PROVIDER"):
        get_llm_provider()


def test_openai_provider_initialization(monkeypatch):
    """Test OpenAIProvider initializes correctly."""
    monkeypatch.setenv("TEXT_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

    provider = OpenAIProvider()
    assert provider.default_model == "gpt-4o-mini"


def test_ollama_provider_model_info_includes_all_models(monkeypatch):
    """Test OllamaProvider model info includes all model types."""
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_CREATIVE_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_REASONING_MODEL", "deepseek-r1:8b")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    provider = OllamaProvider()
    info = provider.get_model_info()

    assert info["chat_model"] == "qwen2.5:7b"
    assert info["creative_model"] == "qwen2.5:7b"
    assert info["reasoning_model"] == "deepseek-r1:8b"
    assert info["embedding_model"] == "nomic-embed-text"


def test_openai_provider_model_info_includes_models(monkeypatch):
    """Test OpenAIProvider model info includes model types."""
    monkeypatch.setenv("TEXT_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    provider = OpenAIProvider()
    info = provider.get_model_info()

    assert info["chat_model"] == "gpt-4o-mini"
    assert "embedding_model" not in info
