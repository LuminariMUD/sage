"""Deterministic execution profile for durable Graphiti synchronization."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from src.graphiti.relationship_policy import RELATIONSHIP_VOCABULARY_FINGERPRINT
from src.graphiti.sync_models import validate_label
from src.llm.provider_config import resolve_provider_settings

SYNC_IMPLEMENTATION_VERSION = "sage-graph-sync:v1"
EXTRACTION_INSTRUCTIONS_VERSION = "lore-extraction:v1"
OUTPUT_SCHEMA_VERSION = "graphiti-core-output:v1"
NORMALIZATION_RULES_VERSION = "graphiti-core-defaults:v1"


def canonical_fingerprint(namespace: str, payload: dict[str, Any]) -> str:
    """Hash a secret-free JSON contract into a bounded operator-safe label."""
    validate_label(namespace, "Fingerprint namespace", maximum=64)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("ascii")).hexdigest()
    return f"{namespace}:sha256:{digest}"


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not-installed"


def _type_contract(type_map: dict[str, type]) -> dict[str, Any]:
    contract: dict[str, Any] = {}
    for name, model in sorted(type_map.items()):
        schema_factory = getattr(model, "model_json_schema", None)
        contract[name] = schema_factory() if callable(schema_factory) else model.__name__
    return contract


def _positive_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an integer") from error
    if parsed <= 0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _environment_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class GraphSyncExecutionProfile:
    """Resolved provider, graph-write, and provenance identity for one worker."""

    sync_profile_fingerprint: str
    route_fingerprint: str
    candidate_fingerprint: str
    embedding_profile_fingerprint: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    max_entities: int
    max_relationships: int
    model_revision: str | None = None
    relationship_vocabulary_fingerprint: str = RELATIONSHIP_VOCABULARY_FINGERPRINT

    def __post_init__(self) -> None:
        for value, label in (
            (self.sync_profile_fingerprint, "Sync profile fingerprint"),
            (self.route_fingerprint, "Route fingerprint"),
            (self.candidate_fingerprint, "Candidate fingerprint"),
            (self.embedding_profile_fingerprint, "Embedding profile fingerprint"),
            (self.provider, "Provider"),
            (self.model, "Model"),
            (self.prompt_version, "Prompt version"),
            (self.schema_version, "Schema version"),
            (
                self.relationship_vocabulary_fingerprint,
                "Relationship vocabulary fingerprint",
            ),
        ):
            validate_label(value, label)
        if self.model_revision is not None:
            validate_label(self.model_revision, "Model revision")
        if self.max_entities <= 0 or self.max_relationships <= 0:
            raise ValueError("Graph extraction limits must be positive")

    @classmethod
    def from_environment(cls) -> GraphSyncExecutionProfile:
        """Resolve a deterministic, secret-free profile from current settings."""
        settings = resolve_provider_settings()
        route = settings.graphiti_text_route
        candidate = route.primary
        embedding_profile = settings.graphiti_embedding_profile
        provider = candidate.connection.provider
        model = candidate.model
        model_revision = candidate.revision
        prompt_version = _environment_value(
            "GRAPH_SYNC_PROMPT_VERSION", default=EXTRACTION_INSTRUCTIONS_VERSION
        )
        schema_version = _environment_value(
            "GRAPH_SYNC_SCHEMA_VERSION", default=OUTPUT_SCHEMA_VERSION
        )
        max_entities = _positive_int(
            _environment_value("GRAPHITI_MAX_ENTITIES_PER_EPISODE", default="25"),
            "Maximum entities per episode",
        )
        max_relationships = _positive_int(
            _environment_value("GRAPHITI_MAX_RELATIONSHIPS_PER_EPISODE", default="25"),
            "Maximum relationships per episode",
        )

        embedding_fingerprint = embedding_profile.fingerprint
        candidate_fingerprint = candidate.fingerprint
        route_fingerprint = route.fingerprint

        from src.graphiti.edge_types import EDGE_TYPES
        from src.graphiti.entity_types import ENTITY_TYPES

        sync_payload = {
            "implementation": SYNC_IMPLEMENTATION_VERSION,
            "graphiti_core": _package_version("graphiti-core"),
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "entity_types": _type_contract(ENTITY_TYPES),
            "edge_types": _type_contract(EDGE_TYPES),
            "normalization": NORMALIZATION_RULES_VERSION,
            "relationship_vocabulary_fingerprint": RELATIONSHIP_VOCABULARY_FINGERPRINT,
            "route_fingerprint": route_fingerprint,
            "embedding_profile_fingerprint": embedding_fingerprint,
            "max_entities": max_entities,
            "max_relationships": max_relationships,
        }
        sync_fingerprint = canonical_fingerprint("sync", sync_payload)
        configured_fingerprint = os.getenv("GRAPH_SYNC_PROFILE_FINGERPRINT")
        if configured_fingerprint and configured_fingerprint != sync_fingerprint:
            raise ValueError("Configured graph sync fingerprint does not match resolved settings")

        return cls(
            sync_profile_fingerprint=sync_fingerprint,
            route_fingerprint=route_fingerprint,
            candidate_fingerprint=candidate_fingerprint,
            embedding_profile_fingerprint=embedding_fingerprint,
            provider=provider,
            model=model,
            model_revision=model_revision,
            prompt_version=prompt_version,
            schema_version=schema_version,
            max_entities=max_entities,
            max_relationships=max_relationships,
            relationship_vocabulary_fingerprint=RELATIONSHIP_VOCABULARY_FINGERPRINT,
        )

    def sanitized_summary(self) -> dict[str, str | int | None]:
        """Return profile details that are safe for logs and operator output."""
        return {
            "sync_profile_fingerprint": self.sync_profile_fingerprint,
            "route_fingerprint": self.route_fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
            "embedding_profile_fingerprint": self.embedding_profile_fingerprint,
            "provider": self.provider,
            "model": self.model,
            "model_revision": self.model_revision,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "max_entities": self.max_entities,
            "max_relationships": self.max_relationships,
            "relationship_vocabulary_fingerprint": self.relationship_vocabulary_fingerprint,
        }
