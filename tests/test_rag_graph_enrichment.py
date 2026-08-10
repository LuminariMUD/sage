"""Regression coverage for RAG graph relationship enrichment."""

from src.api.main import EntityResponse, _resolve_relationship_target


def test_relationship_target_uses_fetched_entity_identity():
    target = EntityResponse(uuid="entity-2", type="Location", name="Nagburim")

    name, entity_type = _resolve_relationship_target(
        target.uuid,
        {target.uuid: target},
        {"name": "BoundTo", "type": "relationship"},
    )

    assert (name, entity_type) == ("Nagburim", "Location")


def test_relationship_target_uses_only_explicit_endpoint_fallbacks():
    assert _resolve_relationship_target(
        "missing",
        {},
        {"target_name": "Known endpoint", "target_type": "Faction"},
    ) == ("Known endpoint", "Faction")
    assert _resolve_relationship_target(
        "missing",
        {},
        {"name": "Edge predicate", "type": "relationship"},
    ) == ("Unknown", "unknown")
