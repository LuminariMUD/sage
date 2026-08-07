"""Construction tests for provider-neutral LangChain and PydanticAI adapters."""

from __future__ import annotations

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.llm.langchain_helpers import get_chat_model
from src.llm.prompts import get_optimized_prompt
from src.llm.pydantic_ai_factory import create_text_model


def _select_openrouter(monkeypatch, *, model="qwen/qwen-test"):
    monkeypatch.setenv("TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_EXTRACTION_FALLBACK_PROVIDER", "")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-unit-test-secret")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://sage.example.test")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Luminari Sage Tests")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", model)


def _select_ollama(monkeypatch):
    monkeypatch.setenv("TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_EXTRACTION_FALLBACK_PROVIDER", "")


def test_langchain_ollama_keeps_native_chat_adapter(monkeypatch):
    _select_ollama(monkeypatch)
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")

    model = get_chat_model(streaming=False)

    assert isinstance(model, ChatOllama)
    assert model.model == "qwen2.5:7b"
    assert model.disable_streaming is True


def test_langchain_openrouter_uses_explicit_connection_headers_and_body(monkeypatch):
    _select_openrouter(monkeypatch)

    model = get_chat_model(streaming=False, max_tokens=64)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "qwen/qwen-test"
    assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"
    assert model.default_headers == {
        "HTTP-Referer": "https://sage.example.test",
        "X-OpenRouter-Title": "Luminari Sage Tests",
    }
    assert model.extra_body == {
        "provider": {
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
        },
        "max_tokens": 64,
    }
    assert model.max_tokens is None
    payload = model._get_request_payload("ready")
    assert "max_completion_tokens" not in payload
    assert payload["extra_body"]["max_tokens"] == 64
    assert model.max_retries == 0
    assert model.use_responses_api is False


def test_langchain_openrouter_can_disable_default_reasoning(monkeypatch):
    _select_openrouter(monkeypatch)

    model = get_chat_model(streaming=False, max_tokens=64, reasoning_effort="none")
    payload = model._get_request_payload("ready")

    assert payload["extra_body"]["reasoning"] == {"effort": "none"}
    assert payload["extra_body"]["max_tokens"] == 64


def test_pydantic_ai_openrouter_uses_same_validated_candidate(monkeypatch):
    _select_openrouter(monkeypatch)

    model = create_text_model()

    assert model.model_name == "qwen/qwen-test"
    assert model.provider.base_url == "https://openrouter.ai/api/v1/"
    assert model.provider.client.max_retries == 0
    assert model.settings["extra_body"] == {
        "provider": {
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
        }
    }


def test_pydantic_ai_ollama_needs_no_remote_key(monkeypatch):
    _select_ollama(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    model = create_text_model()

    assert model.provider.base_url == "http://ollama:11434/v1/"
    assert model.provider.client.max_retries == 0


def test_prompt_selection_follows_openrouter_model_family(monkeypatch):
    _select_openrouter(monkeypatch, model="qwen/qwen-test")

    prompt = get_optimized_prompt("chat", context="Lore", question="Who?")

    assert prompt.startswith("CONTEXT:")
    assert "ANSWER:" in prompt
