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
    monkeypatch.delenv("GRAPH_ENTITY_GROUNDING_POLICY", raising=False)
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
    assert first.entity_grounding_policy == "off"
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


def test_enabled_entity_grounding_changes_sync_identity_only(monkeypatch):
    _ollama_environment(monkeypatch)
    baseline = GraphSyncExecutionProfile.from_environment()
    monkeypatch.setenv("GRAPH_ENTITY_GROUNDING_POLICY", "literal_v1")

    grounded = GraphSyncExecutionProfile.from_environment()

    assert grounded.entity_grounding_policy == "literal_v1"
    assert grounded.sync_profile_fingerprint != baseline.sync_profile_fingerprint
    assert grounded.route_fingerprint == baseline.route_fingerprint
    assert grounded.embedding_profile_fingerprint == baseline.embedding_profile_fingerprint


def test_configured_profile_must_match_resolved_contract(monkeypatch):
    _ollama_environment(monkeypatch)
    monkeypatch.setenv("GRAPH_SYNC_PROFILE_FINGERPRINT", "sync:stale")

    with pytest.raises(ValueError, match="does not match"):
        GraphSyncExecutionProfile.from_environment()


def test_manual_profile_rejects_unknown_entity_grounding_policy():
    with pytest.raises(ValueError, match="unsupported"):
        GraphSyncExecutionProfile(
            sync_profile_fingerprint="sync:test",
            route_fingerprint="route:test",
            candidate_fingerprint="candidate:test",
            embedding_profile_fingerprint="embedding:test",
            provider="ollama",
            model="test",
            prompt_version="prompt:v1",
            schema_version="schema:v1",
            max_entities=1,
            max_relationships=1,
            entity_grounding_policy="unknown",
        )
