"""Pure semantic-quality signals for a synchronized Graphiti subgraph."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

NORMALIZATION_POLICY = "unicode_nfkc_casefold_collapsed_whitespace_v1"


def normalize_grounding_text(value: object) -> str:
    """Normalize text for transparent literal grounding checks."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(normalized.split())


def _strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _entity_sample(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "uuid": entity["uuid"] or None,
        "name": entity["name"] or None,
        "entity_types": entity["entity_types"],
        "linked_episode_count": len(entity["episode_ids"]),
    }


def build_semantic_graph_audit(
    episode_rows: Sequence[Mapping[str, Any]],
    document_rows: Sequence[Mapping[str, Any]],
    entity_rows: Sequence[Mapping[str, Any]],
    *,
    sample_limit: int = 20,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build deterministic review signals without treating aliases as errors."""
    bounded_sample_limit = max(0, int(sample_limit))
    episode_texts = {
        str(row["stable_id"]): normalize_grounding_text(row.get("text")) for row in episode_rows
    }
    canonical_documents = [normalize_grounding_text(row.get("body_md")) for row in document_rows]

    entities: list[dict[str, Any]] = []
    for position, row in enumerate(entity_rows):
        entity_uuid = str(row.get("uuid") or "").strip()
        name = str(row.get("name") or "").strip()
        entity_types = sorted(
            {
                item.strip()
                for item in _strings(row.get("entity_types"))
                if item.strip() and item not in {"Entity", "Entity_"}
            },
            key=str.casefold,
        )
        episode_ids = sorted(
            {item.strip() for item in _strings(row.get("episode_ids")) if item.strip()}
        )
        entities.append(
            {
                "position": position,
                "uuid": entity_uuid,
                "name": name,
                "normalized_name": normalize_grounding_text(name),
                "entity_types": entity_types,
                "episode_ids": episode_ids,
            }
        )

    entities.sort(
        key=lambda entity: (
            entity["normalized_name"],
            entity["name"].casefold(),
            entity["uuid"],
            tuple(entity["entity_types"]),
            tuple(entity["episode_ids"]),
            entity["position"],
        )
    )

    missing_uuid_entities = [entity for entity in entities if not entity["uuid"]]
    missing_name_entities = [entity for entity in entities if not entity["normalized_name"]]
    missing_type_entities = [entity for entity in entities if not entity["entity_types"]]

    uuid_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    name_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        if entity["uuid"]:
            uuid_groups[entity["uuid"]].append(entity)
        if entity["normalized_name"]:
            name_groups[entity["normalized_name"]].append(entity)

    duplicate_uuid_groups = [
        {
            "uuid": entity_uuid,
            "count": len(members),
            "names": sorted({member["name"] for member in members}, key=str.casefold),
        }
        for entity_uuid, members in sorted(uuid_groups.items())
        if len(members) > 1
    ]

    duplicate_name_groups: list[dict[str, Any]] = []
    conflicting_type_groups: list[dict[str, Any]] = []
    for normalized_name, members in sorted(name_groups.items()):
        if len(members) < 2:
            continue
        member_types = sorted(
            {entity_type for member in members for entity_type in member["entity_types"]},
            key=str.casefold,
        )
        group = {
            "normalized_name": normalized_name,
            "observed_names": sorted({member["name"] for member in members}, key=str.casefold),
            "count": len(members),
            "entity_types": member_types,
            "entity_uuid_sample": sorted({member["uuid"] for member in members if member["uuid"]})[
                :bounded_sample_limit
            ],
        }
        duplicate_name_groups.append(group)
        if len(member_types) > 1:
            conflicting_type_groups.append(group)

    entity_positions_present_in_canon = {
        entity["position"]
        for entity in entities
        if entity["normalized_name"]
        and any(entity["normalized_name"] in document_text for document_text in canonical_documents)
    }
    absent_from_canon = [
        entity
        for entity in entities
        if entity["normalized_name"] and entity["position"] not in entity_positions_present_in_canon
    ]

    grounded_links = 0
    entities_with_grounded_links: set[int] = set()
    ungrounded_links: list[dict[str, Any]] = []
    ungrounded_links_absent_from_canon = 0
    ungrounded_links_present_elsewhere_in_canon = 0
    missing_episode_source_links: list[dict[str, Any]] = []
    linked_episode_ids: set[str] = set()
    for entity in entities:
        for episode_id in entity["episode_ids"]:
            linked_episode_ids.add(episode_id)
            episode_text = episode_texts.get(episode_id)
            signal = {
                "entity_uuid": entity["uuid"] or None,
                "entity_name": entity["name"] or None,
                "entity_types": entity["entity_types"],
                "episode_id": episode_id,
            }
            if episode_text is None:
                missing_episode_source_links.append(signal)
            elif entity["normalized_name"] and entity["normalized_name"] in episode_text:
                grounded_links += 1
                entities_with_grounded_links.add(entity["position"])
            elif entity["normalized_name"]:
                ungrounded_links.append(signal)
                if entity["position"] in entity_positions_present_in_canon:
                    ungrounded_links_present_elsewhere_in_canon += 1
                else:
                    ungrounded_links_absent_from_canon += 1

    synced_episodes_without_entities = sorted(set(episode_texts) - linked_episode_ids)
    entity_episode_links = sum(len(entity["episode_ids"]) for entity in entities)
    literal_policy_evaluable_links = grounded_links + len(ungrounded_links)
    literal_policy_evaluable_entities = [
        entity
        for entity in entities
        if entity["normalized_name"]
        and any(episode_id in episode_texts for episode_id in entity["episode_ids"])
    ]
    entities_without_grounded_links = [
        entity
        for entity in literal_policy_evaluable_entities
        if entity["position"] not in entities_with_grounded_links
    ]

    def percent(numerator: int, denominator: int) -> float | None:
        return round((numerator / denominator) * 100, 3) if denominator else None

    counts = {
        "canonical_documents": len(document_rows),
        "synced_episodes": len(episode_texts),
        "graph_entities": len(entities),
        "entities_with_populated_uuid": len(entities) - len(missing_uuid_entities),
        "entities_with_populated_name": len(entities) - len(missing_name_entities),
        "entities_with_types": len(entities) - len(missing_type_entities),
        "entity_episode_links": entity_episode_links,
        "grounded_entity_episode_links": grounded_links,
        "ungrounded_entity_episode_links": len(ungrounded_links),
        "ungrounded_links_for_entities_absent_from_canon": (ungrounded_links_absent_from_canon),
        "ungrounded_links_for_entities_present_elsewhere_in_canon": (
            ungrounded_links_present_elsewhere_in_canon
        ),
        "literal_policy_evaluable_entity_episode_links": literal_policy_evaluable_links,
        "literal_policy_evaluable_entities": len(literal_policy_evaluable_entities),
        "entities_with_grounded_episode_links": len(entities_with_grounded_links),
        "entities_without_grounded_episode_links": len(entities_without_grounded_links),
        "missing_episode_source_links": len(missing_episode_source_links),
        "synced_episodes_without_entities": len(synced_episodes_without_entities),
        "entities_absent_from_canon": len(absent_from_canon),
        "duplicate_entity_uuid_groups": len(duplicate_uuid_groups),
        "duplicate_name_groups": len(duplicate_name_groups),
        "entities_in_duplicate_name_groups": sum(group["count"] for group in duplicate_name_groups),
        "conflicting_type_name_groups": len(conflicting_type_groups),
        "entities_missing_uuid": len(missing_uuid_entities),
        "entities_missing_name": len(missing_name_entities),
        "entities_missing_type": len(missing_type_entities),
    }
    rates_percent = {
        "literal_policy_projected_link_retention": percent(
            grounded_links,
            literal_policy_evaluable_links,
        ),
        "literal_policy_projected_entity_retention": percent(
            len(entities_with_grounded_links),
            len(literal_policy_evaluable_entities),
        ),
    }

    review_categories = []
    if not document_rows:
        review_categories.append("canonical_corpus_empty")
    for category in (
        "entities_missing_uuid",
        "entities_missing_name",
        "entities_missing_type",
        "duplicate_entity_uuid_groups",
        "duplicate_name_groups",
        "conflicting_type_name_groups",
        "entities_absent_from_canon",
        "ungrounded_entity_episode_links",
        "entities_without_grounded_episode_links",
        "missing_episode_source_links",
        "synced_episodes_without_entities",
    ):
        if counts[category]:
            review_categories.append(category)

    return {
        "schema_version": 1,
        "status": "review_required" if review_categories else "clean",
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "scope": "entities mentioned by durable synced episodes",
        "grounding_policy": {
            "normalization": NORMALIZATION_POLICY,
            "match": "normalized entity name is a literal substring of normalized source",
            "alias_resolution": "none",
            "interpretation": "review signal; absence is not automatic proof of hallucination",
            "projection": (
                "existing-link estimate over named entities with available episode sources; "
                "a policy-enabled rebuild may resolve identities differently"
            ),
        },
        "sample_limit": bounded_sample_limit,
        "review_categories": review_categories,
        "counts": counts,
        "rates_percent": rates_percent,
        "samples": {
            "entities_missing_uuid": [
                _entity_sample(entity) for entity in missing_uuid_entities[:bounded_sample_limit]
            ],
            "entities_missing_name": [
                _entity_sample(entity) for entity in missing_name_entities[:bounded_sample_limit]
            ],
            "entities_missing_type": [
                _entity_sample(entity) for entity in missing_type_entities[:bounded_sample_limit]
            ],
            "duplicate_entity_uuid_groups": duplicate_uuid_groups[:bounded_sample_limit],
            "duplicate_name_groups": duplicate_name_groups[:bounded_sample_limit],
            "conflicting_type_name_groups": conflicting_type_groups[:bounded_sample_limit],
            "entities_absent_from_canon": [
                _entity_sample(entity) for entity in absent_from_canon[:bounded_sample_limit]
            ],
            "ungrounded_entity_episode_links": ungrounded_links[:bounded_sample_limit],
            "entities_without_grounded_episode_links": [
                _entity_sample(entity)
                for entity in entities_without_grounded_links[:bounded_sample_limit]
            ],
            "missing_episode_source_links": missing_episode_source_links[:bounded_sample_limit],
            "synced_episodes_without_entities": synced_episodes_without_entities[
                :bounded_sample_limit
            ],
        },
    }
