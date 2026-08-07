"""Tests for canonical relationship normalization and endpoint policy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.graphiti import policy_graphiti
from src.graphiti.edge_types import EDGE_TYPES
from src.graphiti.policy_graphiti import PolicyGraphiti, RelationshipPolicyLLMProxy
from src.graphiti.relationship_policy import (
    RELATIONSHIP_VOCABULARY,
    RELATIONSHIP_VOCABULARY_FINGERPRINT,
    RelationshipPolicyError,
    canonical_relationship_type,
    validate_relationship_response,
)


def _edge(source: str, target: str, relation: str, fact: str) -> dict[str, object]:
    return {
        "source_entity_name": source,
        "target_entity_name": target,
        "relation_type": relation,
        "fact": fact,
        "valid_at": None,
        "invalid_at": None,
        "episode_indices": [0],
    }


def _nodes() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(name="Alpha", uuid="node-alpha"),
        SimpleNamespace(name="Beta", uuid="node-beta"),
        SimpleNamespace(name="Twin", uuid="node-twin-1"),
        SimpleNamespace(name="Twin", uuid="node-twin-2"),
    ]


def test_vocabulary_is_exactly_the_versioned_edge_contract():
    assert RELATIONSHIP_VOCABULARY == tuple(EDGE_TYPES)
    assert RELATIONSHIP_VOCABULARY_FINGERPRINT.startswith("relationships:sha256:")
    assert len(RELATIONSHIP_VOCABULARY_FINGERPRINT) == 85


@pytest.mark.parametrize(
    ("value", "expected", "normalized"),
    [
        ("OpposedTo", "OpposedTo", False),
        ("OPPOSED_TO", "OpposedTo", True),
        ("opposed-to", "OpposedTo", True),
        ("opposed to", "OpposedTo", True),
        ("RELATES_TO", None, False),
        ("opposes", None, False),
    ],
)
def test_only_safe_spelling_aliases_are_normalized(value, expected, normalized):
    assert canonical_relationship_type(value) == (expected, normalized)


def test_policy_normalizes_and_rejects_before_maintenance_without_content_evidence():
    response = {
        "edges": [
            _edge("Alpha", "Beta", "OpposedTo", "Alpha opposes Beta"),
            _edge("Alpha", "Beta", "opposed_to", "Alpha challenges Beta"),
            _edge("Alpha", "Beta", "RELATES_TO", "Unknown predicate"),
            _edge("Alpha", "Missing", "OpposedTo", "Missing endpoint"),
            _edge("Alpha", "Twin", "OpposedTo", "Ambiguous endpoint"),
            _edge("Alpha", "Alpha", "OpposedTo", "Self edge"),
            _edge("Alpha", "Beta", "OpposedTo", "  "),
            _edge("Alpha", "Beta", "OPPOSED_TO", " alpha   opposes beta "),
        ]
    }

    normalized, report = validate_relationship_response(response, _nodes())

    assert [edge["relation_type"] for edge in normalized["edges"]] == [
        "OpposedTo",
        "OpposedTo",
    ]
    assert report.as_dict() == {
        "vocabulary_fingerprint": RELATIONSHIP_VOCABULARY_FINGERPRINT,
        "proposed_edges": 8,
        "normalized_edges": 1,
        "accepted_edges": 2,
        "rejected_edges": 6,
        "rejected_unknown_type": 1,
        "rejected_missing_endpoint": 1,
        "rejected_ambiguous_endpoint": 1,
        "rejected_self_edge": 1,
        "rejected_empty_fact": 1,
        "rejected_duplicate": 1,
        "resolved_edges": None,
        "new_edges": None,
        "invalidated_edges": None,
    }
    maintenance = report.with_maintenance(
        resolved_edges=2,
        new_edges=1,
        invalidated_edges=1,
    )
    assert maintenance.new_edges == 1
    assert "Alpha" not in repr(report)
    assert "Unknown predicate" not in repr(report)


@pytest.mark.parametrize("response", [None, {}, {"edges": "not-a-list"}])
def test_malformed_relationship_response_fails_closed(response):
    with pytest.raises(RelationshipPolicyError):
        validate_relationship_response(response, _nodes())


def test_relationship_maintenance_counts_must_be_reported_together():
    _, report = validate_relationship_response({"edges": []}, _nodes())

    with pytest.raises(ValueError, match="reported together"):
        report.with_maintenance(resolved_edges=0, new_edges=0, invalidated_edges=None)


async def test_llm_proxy_filters_only_the_edge_extraction_boundary():
    class Delegate:
        def __init__(self):
            self.calls = 0

        async def generate_response(self, *args, **kwargs):
            self.calls += 1
            return {"edges": [_edge("Alpha", "Beta", "OPPOSED_TO", "A fact")]}

    delegate = Delegate()
    proxy = RelationshipPolicyLLMProxy(delegate, _nodes())

    untouched = await proxy.generate_response([], prompt_name="extract_nodes.extract_message")
    assert untouched["edges"][0]["relation_type"] == "OPPOSED_TO"
    assert proxy.report is None

    normalized = await proxy.generate_response([], prompt_name="extract_edges.edge")
    assert normalized["edges"][0]["relation_type"] == "OpposedTo"
    assert proxy.report is not None
    assert proxy.report.normalized_edges == 1
    assert delegate.calls == 2


async def test_policy_graphiti_filters_edges_before_pointer_resolution(monkeypatch):
    class Delegate:
        async def generate_response(self, *args, **kwargs):
            return {
                "edges": [
                    _edge("Alpha", "Beta", "OPPOSED_TO", "A valid fact"),
                    _edge("Alpha", "Beta", "RELATES_TO", "An unknown predicate"),
                ]
            }

    class Clients:
        llm_client = Delegate()

        def model_copy(self, *, update):
            return SimpleNamespace(llm_client=update["llm_client"])

    async def fake_extract_edges(clients, *args):
        response = await clients.llm_client.generate_response([], prompt_name="extract_edges.edge")
        return [SimpleNamespace(name=edge["relation_type"]) for edge in response["edges"]]

    def fake_resolve_edge_pointers(edges, uuid_map):
        assert [edge.name for edge in edges] == ["OpposedTo"]
        return edges

    async def fake_resolve_extracted_edges(clients, edges, *args):
        return edges, [], edges

    monkeypatch.setattr(policy_graphiti, "extract_edges", fake_extract_edges)
    monkeypatch.setattr(policy_graphiti, "resolve_edge_pointers", fake_resolve_edge_pointers)
    monkeypatch.setattr(
        policy_graphiti,
        "resolve_extracted_edges",
        fake_resolve_extracted_edges,
    )

    graphiti = object.__new__(PolicyGraphiti)
    graphiti.clients = Clients()
    graphiti._relationship_quality = {}
    episode = SimpleNamespace(uuid="episode-id")

    resolved, invalidated, new = await graphiti._extract_and_resolve_edges(
        episode,
        _nodes()[:2],
        [],
        {("Entity", "Entity"): list(EDGE_TYPES)},
        "group-id",
        None,
        _nodes()[:2],
        {},
    )

    assert len(resolved) == 1
    assert invalidated == []
    assert new == resolved
    report = graphiti.consume_relationship_quality("episode-id")
    assert report is not None
    assert report.proposed_edges == 2
    assert report.accepted_edges == 1
    assert report.rejected_unknown_type == 1
    assert report.resolved_edges == 1
