"""Deterministic execution profile for durable Graphiti synchronization."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from src.graphiti.sync_models import validate_label

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
        ):
            validate_label(value, label)
        if self.model_revision is not None:
            validate_label(self.model_revision, "Model revision")
        if self.max_entities <= 0 or self.max_relationships <= 0:
            raise ValueError("Graph extraction limits must be positive")

    @classmethod
    def from_environment(cls) -> GraphSyncExecutionProfile:
        """Resolve a deterministic, secret-free profile from current settings."""
        provider = _environment_value(
            "GRAPHITI_TEXT_PROVIDER",
            "GRAPHITI_PROVIDER",
            "TEXT_PROVIDER",
            "LLM_PROVIDER",
            default="ollama",
        ).lower()
        if provider not in {"ollama", "openrouter", "openai"}:
            raise ValueError("Graphiti text provider is unsupported")

        if provider == "ollama":
            default_model = _environment_value("OLLAMA_REASONING_MODEL", default="qwen2.5:3b")
        elif provider == "openrouter":
            default_model = _environment_value(
                "OPENROUTER_GRAPHITI_MODEL",
                "OPENROUTER_REASONING_MODEL",
            )
        else:
            default_model = _environment_value("GRAPHITI_LLM_MODEL", default="gpt-4o-mini")
        model = _environment_value("GRAPHITI_TEXT_MODEL", default=default_model)
        validate_label(model, "Graphiti text model")

        embedding_provider = _environment_value(
            "GRAPHITI_EMBEDDING_PROVIDER",
            "EMBEDDING_PROVIDER",
            "GRAPHITI_PROVIDER",
            default=provider,
        ).lower()
        if embedding_provider not in {"ollama", "openrouter", "openai"}:
            raise ValueError("Graphiti embedding provider is unsupported")
        if embedding_provider == "ollama":
            embedding_model = _environment_value(
                "OLLAMA_EMBEDDING_MODEL", default="nomic-embed-text"
            )
            default_dimensions = "768"
        elif embedding_provider == "openrouter":
            embedding_model = _environment_value("OPENROUTER_EMBEDDING_MODEL")
            default_dimensions = "1024"
        else:
            embedding_model = _environment_value(
                "EMBEDDING_MODEL", default="text-embedding-3-small"
            )
            default_dimensions = "1536"
        validate_label(embedding_model, "Graphiti embedding model")
        embedding_dimensions = _positive_int(
            _environment_value("GRAPHITI_EMBEDDING_DIMENSIONS", default=default_dimensions),
            "Graphiti embedding dimensions",
        )

        model_revision = _environment_value("GRAPHITI_TEXT_MODEL_REVISION") or None
        embedding_revision = _environment_value("GRAPHITI_EMBEDDING_MODEL_REVISION") or None
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

        embedding_payload = {
            "provider": embedding_provider,
            "implementation": "openai-compatible",
            "model": embedding_model,
            "revision": embedding_revision,
            "dimensions": embedding_dimensions,
            "encoding": "float",
            "distance": "cosine",
        }
        embedding_fingerprint = canonical_fingerprint("embedding", embedding_payload)
        candidate_payload = {
            "provider": provider,
            "model": model,
            "revision": model_revision,
            "protocol": "openai-chat-completions",
        }
        candidate_fingerprint = canonical_fingerprint("candidate", candidate_payload)
        route_fingerprint = canonical_fingerprint(
            "route",
            {"candidates": [candidate_fingerprint], "fallback_policy": "none:v1"},
        )

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
        }
