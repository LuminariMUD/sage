"""Versioned, content-safe grounding policy for extracted entity names."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import BaseModel

from src.graphiti.semantic_audit import normalize_grounding_text

ENTITY_GROUNDING_POLICY_OFF = "off"
ENTITY_GROUNDING_POLICY_LITERAL_V1 = "literal_v1"
ENTITY_GROUNDING_POLICIES = frozenset(
    {ENTITY_GROUNDING_POLICY_OFF, ENTITY_GROUNDING_POLICY_LITERAL_V1}
)


class EntityGroundingPolicyError(ValueError):
    """Raised when enabled entity grounding cannot validate a response safely."""


@dataclass(frozen=True)
class EntityGroundingReport:
    """Content-free counts for one extraction response."""

    proposed: int
    accepted: int
    rejected_not_literal: int
    rejected_empty_name: int

    @property
    def rejected(self) -> int:
        return self.rejected_not_literal + self.rejected_empty_name

    def as_dict(self) -> dict[str, int]:
        report = asdict(self)
        report["rejected"] = self.rejected
        return report


def resolve_entity_grounding_policy(value: object) -> str:
    """Validate and normalize one configured policy identifier."""
    policy = str(value or ENTITY_GROUNDING_POLICY_OFF).strip().lower()
    if policy not in ENTITY_GROUNDING_POLICIES:
        raise EntityGroundingPolicyError("Entity grounding policy is unsupported")
    return policy


def _response_payload(response: object) -> dict[str, Any]:
    if isinstance(response, BaseModel):
        return response.model_dump()
    if isinstance(response, Mapping):
        return dict(response)
    raise EntityGroundingPolicyError("Entity extraction response is not an object")


def filter_entity_extraction_response(
    response: object,
    episode_text: str,
) -> tuple[dict[str, Any], EntityGroundingReport]:
    """Keep only entity names literally grounded in the current episode."""
    payload = _response_payload(response)
    entities = payload.get("extracted_entities")
    if not isinstance(entities, list):
        raise EntityGroundingPolicyError("Entity extraction response has no entity list")

    normalized_episode = normalize_grounding_text(episode_text)
    accepted: list[object] = []
    rejected_not_literal = 0
    rejected_empty_name = 0
    for entity in entities:
        entity_payload = _response_payload(entity)
        normalized_name = normalize_grounding_text(entity_payload.get("name"))
        if not normalized_name:
            rejected_empty_name += 1
        elif normalized_name not in normalized_episode:
            rejected_not_literal += 1
        else:
            accepted.append(entity_payload)

    filtered = dict(payload)
    filtered["extracted_entities"] = accepted
    return filtered, EntityGroundingReport(
        proposed=len(entities),
        accepted=len(accepted),
        rejected_not_literal=rejected_not_literal,
        rejected_empty_name=rejected_empty_name,
    )
