"""Tests for deterministic, secret-free graph synchronization profiles."""

import pytest

from src.graphiti.relationship_policy import RELATIONSHIP_VOCABULARY_FINGERPRINT
from src.graphiti.sync_profile import GraphSyncExecutionProfile


def _ollama_environment(monkeypatch):
    monkeypatch.setenv("GRAPHITI_TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("GRAPHITI_TEXT_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_DIMENSIONS", "768")
    monkeypatch.delenv("GRAPH_SYNC_PROFILE_FINGERPRINT", raising=False)


def test_resolved_profile_is_deterministic_and_secret_free(monkeypatch):
    _ollama_environment(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "should-not-appear")

    first = GraphSyncExecutionProfile.from_environment()
    second = GraphSyncExecutionProfile.from_environment()

    assert first == second
    assert first.sync_profile_fingerprint.startswith("sync:sha256:")
    assert first.embedding_profile_fingerprint.startswith("embedding:sha256:")
    assert first.relationship_vocabulary_fingerprint == RELATIONSHIP_VOCABULARY_FINGERPRINT
    assert (
        first.sanitized_summary()["relationship_vocabulary_fingerprint"]
        == RELATIONSHIP_VOCABULARY_FINGERPRINT
    )
    assert "should-not-appear" not in str(first.sanitized_summary())


def test_model_change_changes_candidate_route_and_sync_identity(monkeypatch):
    _ollama_environment(monkeypatch)
    first = GraphSyncExecutionProfile.from_environment()
    monkeypatch.setenv("GRAPHITI_TEXT_MODEL", "qwen2.5:7b")

    changed = GraphSyncExecutionProfile.from_environment()

    assert changed.candidate_fingerprint != first.candidate_fingerprint
    assert changed.route_fingerprint != first.route_fingerprint
    assert changed.sync_profile_fingerprint != first.sync_profile_fingerprint
    assert changed.embedding_profile_fingerprint == first.embedding_profile_fingerprint


def test_configured_profile_must_match_resolved_contract(monkeypatch):
    _ollama_environment(monkeypatch)
    monkeypatch.setenv("GRAPH_SYNC_PROFILE_FINGERPRINT", "sync:stale")

    with pytest.raises(ValueError, match="does not match"):
        GraphSyncExecutionProfile.from_environment()
