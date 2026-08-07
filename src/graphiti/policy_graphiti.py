"""Graphiti subclass that applies Sage relationship policy before maintenance."""

from __future__ import annotations

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

from src.graphiti.relationship_policy import (
    RelationshipPolicyError,
    RelationshipQualityReport,
    validate_relationship_response,
)


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

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._relationship_quality: dict[str, RelationshipQualityReport] = {}

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
