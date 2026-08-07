"""Versioned, content-free relationship normalization and endpoint policy."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

from src.graphiti.edge_types import EDGE_TYPES
from src.llm.retry import ModelSchemaValidationError

RELATIONSHIP_VOCABULARY_VERSION = "luminari-relationships:v1"
RELATIONSHIP_VOCABULARY = tuple(EDGE_TYPES)


def _relation_token(value: str) -> str:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value.strip())
    return re.sub(r"[^A-Za-z0-9]+", "_", separated).strip("_").upper()


_CANONICAL_BY_TOKEN = {_relation_token(name): name for name in RELATIONSHIP_VOCABULARY}
if len(_CANONICAL_BY_TOKEN) != len(RELATIONSHIP_VOCABULARY):  # pragma: no cover
    raise RuntimeError("Canonical relationship names have a normalized-token collision")

# Only spelling/case/separator variants are aliases. Semantic synonyms are not
# safe because they can change direction or meaning, so unknown predicates fail
# closed instead of being guessed into the vocabulary.
RELATIONSHIP_ALIASES = dict(sorted(_CANONICAL_BY_TOKEN.items()))


def _vocabulary_fingerprint() -> str:
    payload = {
        "version": RELATIONSHIP_VOCABULARY_VERSION,
        "canonical_types": RELATIONSHIP_VOCABULARY,
        "aliases": RELATIONSHIP_ALIASES,
        "endpoint_policy": {
            "known_name": True,
            "unambiguous_name": True,
            "distinct_uuid": True,
            "nonempty_fact": True,
            "deduplicate_exact_proposals": True,
        },
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("ascii")).hexdigest()
    return f"relationships:sha256:{digest}"


RELATIONSHIP_VOCABULARY_FINGERPRINT = _vocabulary_fingerprint()


class RelationshipPolicyError(ModelSchemaValidationError):
    """Raised when a structured edge response cannot be safely inspected."""


@dataclass(frozen=True)
class RelationshipQualityReport:
    """Content-free counts from proposal through graph maintenance."""

    vocabulary_fingerprint: str
    proposed_edges: int
    normalized_edges: int
    accepted_edges: int
    rejected_edges: int
    rejected_unknown_type: int = 0
    rejected_missing_endpoint: int = 0
    rejected_ambiguous_endpoint: int = 0
    rejected_self_edge: int = 0
    rejected_empty_fact: int = 0
    rejected_duplicate: int = 0
    resolved_edges: int | None = None
    new_edges: int | None = None
    invalidated_edges: int | None = None

    def __post_init__(self) -> None:
        counts = (
            self.proposed_edges,
            self.normalized_edges,
            self.accepted_edges,
            self.rejected_edges,
            self.rejected_unknown_type,
            self.rejected_missing_endpoint,
            self.rejected_ambiguous_endpoint,
            self.rejected_self_edge,
            self.rejected_empty_fact,
            self.rejected_duplicate,
        )
        optional_counts = (self.resolved_edges, self.new_edges, self.invalidated_edges)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            raise ValueError("Relationship quality counts must be nonnegative integers")
        if any(
            value is not None
            and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
            for value in optional_counts
        ):
            raise ValueError("Relationship maintenance counts must be nonnegative integers")
        if any(value is not None for value in optional_counts) and not all(
            value is not None for value in optional_counts
        ):
            raise ValueError("Relationship maintenance counts must be reported together")
        if self.accepted_edges + self.rejected_edges != self.proposed_edges:
            raise ValueError("Relationship proposal counts do not reconcile")
        rejection_total = sum(
            (
                self.rejected_unknown_type,
                self.rejected_missing_endpoint,
                self.rejected_ambiguous_endpoint,
                self.rejected_self_edge,
                self.rejected_empty_fact,
                self.rejected_duplicate,
            )
        )
        if rejection_total != self.rejected_edges:
            raise ValueError("Relationship rejection reasons do not reconcile")
        if self.normalized_edges > self.accepted_edges:
            raise ValueError("Normalized relationships cannot exceed accepted relationships")
        if (
            self.resolved_edges is not None
            and self.new_edges is not None
            and self.new_edges > self.resolved_edges
        ):
            raise ValueError("New relationships cannot exceed resolved relationships")

    def with_maintenance(
        self, *, resolved_edges: int, new_edges: int, invalidated_edges: int
    ) -> RelationshipQualityReport:
        """Return the same policy evidence with post-resolution counts."""
        return replace(
            self,
            resolved_edges=resolved_edges,
            new_edges=new_edges,
            invalidated_edges=invalidated_edges,
        )

    def as_dict(self) -> dict[str, str | int | None]:
        """Return only bounded-cardinality counts and the policy fingerprint."""
        return asdict(self)


def canonical_relationship_type(value: object) -> tuple[str | None, bool]:
    """Return a canonical type and whether a safe spelling alias was rewritten."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    if value in EDGE_TYPES:
        return value, False
    canonical = RELATIONSHIP_ALIASES.get(_relation_token(value))
    return canonical, canonical is not None


def _mapping(value: object, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        dumped = dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    raise RelationshipPolicyError(f"{label} is not a structured mapping")


def _node_index(nodes: Sequence[object]) -> dict[str, list[str]]:
    by_name: dict[str, list[str]] = {}
    for node in nodes:
        name = getattr(node, "name", None)
        node_uuid = getattr(node, "uuid", None)
        if not isinstance(name, str) or not name or not isinstance(node_uuid, str) or not node_uuid:
            raise RelationshipPolicyError("Extracted entity identity is incomplete")
        by_name.setdefault(name, []).append(node_uuid)
    return by_name


def validate_relationship_response(
    response: object,
    nodes: Sequence[object],
) -> tuple[dict[str, list[dict[str, Any]]], RelationshipQualityReport]:
    """Normalize and reject unsafe edge proposals before graph maintenance."""
    payload = _mapping(response, "Relationship response")
    raw_edges = payload.get("edges")
    if not isinstance(raw_edges, list):
        raise RelationshipPolicyError("Relationship response edges are not a list")

    endpoints = _node_index(nodes)
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    normalized_count = 0
    rejection_counts = {
        "rejected_unknown_type": 0,
        "rejected_missing_endpoint": 0,
        "rejected_ambiguous_endpoint": 0,
        "rejected_self_edge": 0,
        "rejected_empty_fact": 0,
        "rejected_duplicate": 0,
    }

    for raw_edge in raw_edges:
        edge = _mapping(raw_edge, "Relationship proposal")
        source_name = edge.get("source_entity_name")
        target_name = edge.get("target_entity_name")
        relation_type = edge.get("relation_type")
        fact = edge.get("fact")
        if not all(
            isinstance(value, str) for value in (source_name, target_name, relation_type, fact)
        ):
            raise RelationshipPolicyError("Relationship proposal fields are invalid")

        source_matches = endpoints.get(source_name, [])
        target_matches = endpoints.get(target_name, [])
        if not source_matches or not target_matches:
            rejection_counts["rejected_missing_endpoint"] += 1
            continue
        if len(source_matches) != 1 or len(target_matches) != 1:
            rejection_counts["rejected_ambiguous_endpoint"] += 1
            continue
        if source_matches[0] == target_matches[0]:
            rejection_counts["rejected_self_edge"] += 1
            continue
        if not fact.strip():
            rejection_counts["rejected_empty_fact"] += 1
            continue

        canonical_type, normalized = canonical_relationship_type(relation_type)
        if canonical_type is None:
            rejection_counts["rejected_unknown_type"] += 1
            continue
        duplicate_key = (
            source_matches[0],
            target_matches[0],
            canonical_type,
            " ".join(fact.split()).casefold(),
        )
        if duplicate_key in seen:
            rejection_counts["rejected_duplicate"] += 1
            continue
        seen.add(duplicate_key)

        normalized_count += int(normalized)
        edge["relation_type"] = canonical_type
        accepted.append(edge)

    rejected_count = sum(rejection_counts.values())
    report = RelationshipQualityReport(
        vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        proposed_edges=len(raw_edges),
        normalized_edges=normalized_count,
        accepted_edges=len(accepted),
        rejected_edges=rejected_count,
        **rejection_counts,
    )
    return {"edges": accepted}, report
