"""Sanitized provider identities exposed through API health metadata."""

from src.api.main import _provider_health_summary


def test_provider_health_summary_exposes_profiles_without_credentials(monkeypatch):
    monkeypatch.setenv("TEXT_PROVIDER", "openrouter")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-health-test-secret")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "qwen/qwen-test")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_EMBEDDING_DIMENSIONS", "768")

    summary = _provider_health_summary()

    assert summary["application_text"]["provider"] == "openrouter"
    assert summary["application_text"]["routes"]["chat"]["model"] == "qwen/qwen-test"
    assert summary["application_embedding"]["provider"] == "ollama"
    assert summary["application_embedding"]["dimensions"] == 768
    assert summary["graphiti_text"]["provider"] == "ollama"
    assert "offline-health-test-secret" not in str(summary)
    assert "api_key" not in str(summary).lower()
