"""Regression tests for the fully local LangChain service selection path."""

import sys
from types import ModuleType

from src.agents.langchain.service_selector import get_chat_service


def test_ollama_react_service_does_not_require_openai_key(monkeypatch):
    """Ollama mode must not fall back merely because no cloud key exists."""

    class FakeReactService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = ModuleType("src.agents.langchain.react_service")
    fake_module.ReactService = FakeReactService

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("ENABLE_REACT", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)

    service = get_chat_service()

    assert isinstance(service, FakeReactService)


def test_openrouter_react_service_uses_shared_readiness(monkeypatch):
    """OpenRouter selection must not be gated on a direct OpenAI credential."""

    class FakeReactService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = ModuleType("src.agents.langchain.react_service")
    fake_module.ReactService = FakeReactService

    monkeypatch.setenv("TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-unit-test-secret")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "qwen/qwen-test")
    monkeypatch.setenv("ENABLE_REACT", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)

    service = get_chat_service()

    assert isinstance(service, FakeReactService)
