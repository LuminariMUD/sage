"""Graphiti subclass that applies Sage relationship policy before maintenance."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.utils.bulk_utils import resolve_edge_pointers
from graphiti_core.utils.maintenance.edge_operations import (
    extract_edges,
    resolve_extracted_edges,
)
from pydantic import BaseModel

from src.graphiti.entity_grounding_policy import (
    ENTITY_GROUNDING_POLICY_LITERAL_V1,
    EntityGroundingReport,
    filter_entity_extraction_response,
    resolve_entity_grounding_policy,
)
from src.graphiti.relationship_policy import (
    RelationshipPolicyError,
    RelationshipQualityReport,
    validate_relationship_response,
)

logger = logging.getLogger(__name__)
_CURRENT_EPISODE_TEXT: ContextVar[str | None] = ContextVar(
    "graphiti_current_episode_text",
    default=None,
)


@contextmanager
def bind_entity_grounding_episode(episode_text: str) -> Iterator[None]:
    """Bind source text only for the duration of one extraction boundary."""
    token = _CURRENT_EPISODE_TEXT.set(episode_text)
    try:
        yield
    finally:
        _CURRENT_EPISODE_TEXT.reset(token)


class EntityGroundingLLMProxy:
    """Filter only entity-extraction responses against the current episode."""

    def __init__(self, delegate: Any):
        self.delegate = delegate
        self.report: EntityGroundingReport | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
        response = await self.delegate.generate_response(*args, **kwargs)
        prompt_name = str(kwargs.get("prompt_name") or "")
        if not prompt_name.startswith("extract_nodes."):
            return response
        episode_text = _CURRENT_EPISODE_TEXT.get()
        if episode_text is None:
            raise RuntimeError("Entity grounding has no current episode context")
        filtered, self.report = filter_entity_extraction_response(response, episode_text)
        logger.info(
            "Entity grounding accepted %d/%d proposals",
            self.report.accepted,
            self.report.proposed,
        )
        return filtered


class RelationshipPolicyLLMProxy:
    """Delegate provider calls while filtering only structured edge extraction."""

    def __init__(self, delegate: Any, nodes: list[EntityNode]):
        self.delegate = delegate
        self.nodes = nodes
        self.report: RelationshipQualityReport | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    async def generate_response(self, *args: Any, **kwargs: Any) -> Any:
        response = await self.delegate.generate_response(*args, **kwargs)
        if kwargs.get("prompt_name") != "extract_edges.edge":
            return response
        normalized, self.report = validate_relationship_response(response, self.nodes)
        return normalized


class PolicyGraphiti(Graphiti):
    """Apply canonical vocabulary and endpoint policy before edge resolution."""

    def __init__(
        self,
        *args: Any,
        entity_grounding_policy: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._relationship_quality: dict[str, RelationshipQualityReport] = {}
        self._entity_grounding_quality: dict[str, EntityGroundingReport] = {}
        self._entity_grounding_proxy: EntityGroundingLLMProxy | None = None
        self.entity_grounding_policy = resolve_entity_grounding_policy(
            entity_grounding_policy
            if entity_grounding_policy is not None
            else os.getenv("GRAPH_ENTITY_GROUNDING_POLICY")
        )
        if self.entity_grounding_policy == ENTITY_GROUNDING_POLICY_LITERAL_V1:
            grounding_proxy = EntityGroundingLLMProxy(self.llm_client)
            self._entity_grounding_proxy = grounding_proxy
            self.llm_client = grounding_proxy
            self.clients = self.clients.model_copy(update={"llm_client": grounding_proxy})

    async def add_episode(self, *args: Any, **kwargs: Any) -> Any:
        """Bind the current episode text while an enabled grounding proxy runs."""
        if self.entity_grounding_policy != ENTITY_GROUNDING_POLICY_LITERAL_V1:
            return await super().add_episode(*args, **kwargs)
        grounding_proxy = self._entity_grounding_proxy
        if grounding_proxy is None:
            raise RuntimeError("Entity grounding proxy is unavailable")
        episode_body = kwargs.get("episode_body")
        if episode_body is None and len(args) >= 2:
            episode_body = args[1]
        if not isinstance(episode_body, str):
            raise ValueError("Entity grounding requires episode text")
        grounding_proxy.report = None
        with bind_entity_grounding_episode(episode_body):
            result = await super().add_episode(*args, **kwargs)
        if grounding_proxy.report is None:
            raise RuntimeError("Entity grounding produced no quality evidence")
        episode = getattr(result, "episode", None)
        episode_uuid = getattr(episode, "uuid", None)
        if not isinstance(episode_uuid, str) or not episode_uuid:
            raise RuntimeError("Entity grounding result has no episode identity")
        self._entity_grounding_quality[episode_uuid] = grounding_proxy.report
        return result

    async def _extract_and_resolve_edges(
        self,
        episode: EpisodicNode | list[EpisodicNode],
        extracted_nodes: list[EntityNode],
        previous_episodes: list[EpisodicNode],
        edge_type_map: dict[tuple[str, str], list[str]],
        group_id: str,
        edge_types: dict[str, type[BaseModel]] | None,
        nodes: list[EntityNode],
        uuid_map: dict[str, str],
        custom_extraction_instructions: str | None = None,
    ) -> tuple[list[EntityEdge], list[EntityEdge], list[EntityEdge]]:
        """Normalize and validate proposals before Graphiti graph maintenance."""
        episodes = episode if isinstance(episode, list) else [episode]
        primary_episode = episodes[0]
        proxy = RelationshipPolicyLLMProxy(self.clients.llm_client, extracted_nodes)
        policy_clients = self.clients.model_copy(update={"llm_client": proxy})
        extracted_edges = await extract_edges(
            policy_clients,
            episode,
            extracted_nodes,
            previous_episodes,
            edge_type_map,
            group_id,
            edge_types,
            custom_extraction_instructions,
        )
        if proxy.report is None:
            raise RelationshipPolicyError("Relationship extraction policy did not produce evidence")

        edges = resolve_edge_pointers(extracted_edges, uuid_map)
        resolved_edges, invalidated_edges, new_edges = await resolve_extracted_edges(
            self.clients,
            edges,
            primary_episode,
            nodes,
            edge_types or {},
            edge_type_map,
        )
        self._relationship_quality[primary_episode.uuid] = proxy.report.with_maintenance(
            resolved_edges=len(resolved_edges),
            new_edges=len(new_edges),
            invalidated_edges=len(invalidated_edges),
        )
        return resolved_edges, invalidated_edges, new_edges

    def consume_relationship_quality(self, episode_uuid: str) -> RelationshipQualityReport | None:
        """Consume one content-free report after exact episode verification."""
        return self._relationship_quality.pop(episode_uuid, None)

    def consume_entity_grounding_quality(
        self,
        episode_uuid: str,
    ) -> EntityGroundingReport | None:
        """Consume one content-free grounding report after exact verification."""
        return self._entity_grounding_quality.pop(episode_uuid, None)
