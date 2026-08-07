"""Idempotent Neo4j episode writes and independent durable-sync verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from graphiti_core.nodes import EpisodeType

from src.graphiti.edge_types import EDGE_TYPES
from src.graphiti.entity_types import ENTITY_TYPES
from src.graphiti.sync_models import GraphCounts, JobLease, StableIdVerification
from src.graphiti.sync_profile import GraphSyncExecutionProfile


class GraphEpisodeError(RuntimeError):
    """Base error for an episode write that cannot be proven safe."""


class GraphIdentityConflictError(GraphEpisodeError):
    """Raised when existing Neo4j identity or content is ambiguous or conflicting."""


class GraphVerificationError(GraphEpisodeError):
    """Raised when a write does not produce the exact expected Neo4j record."""


@dataclass(frozen=True)
class GraphProcessingResult:
    verification: StableIdVerification
    graph_counts: GraphCounts
    reused_existing: bool
    degraded: bool = False


@dataclass(frozen=True)
class _EpisodeState:
    candidate_count: int
    native_uuid_count: int
    stable_id_count: int
    source_description_count: int
    source_fingerprint_count: int
    sync_profile_fingerprint_count: int
    embedding_profile_fingerprint_count: int
    exact_count: int
    stable_id_conflict_count: int
    candidate_content: str | None


def _records(result: Any) -> list[Any]:
    if hasattr(result, "records"):
        return list(result.records)
    if result is None:
        return []
    return list(result)


class GraphitiEpisodeProcessor:
    """Converge one leased PostgreSQL episode onto one Neo4j Episodic node."""

    def __init__(self, graphiti: Any, profile: GraphSyncExecutionProfile):
        self.graphiti = graphiti
        self.profile = profile

    async def verify_readiness(self) -> None:
        """Fail closed on connectivity or pre-existing duplicate stable identities."""
        verify_connectivity = getattr(self.graphiti.driver, "verify_connectivity", None)
        if callable(verify_connectivity):
            await verify_connectivity()
        result = await self.graphiti.driver.execute_query("""
            /* graph_sync:readiness */
            MATCH (ep:Episodic)
            WHERE ep.stable_id IS NOT NULL
            WITH ep.stable_id AS stable_id, count(*) AS count
            WHERE count > 1
            RETURN count(*) AS duplicate_stable_ids
            """)
        records = _records(result)
        duplicate_count = int(records[0]["duplicate_stable_ids"]) if records else 0
        if duplicate_count:
            raise GraphIdentityConflictError(
                "Neo4j contains duplicate episode stable IDs; synchronization is unsafe"
            )

    async def process(self, lease: JobLease) -> GraphProcessingResult:
        """Reuse, adopt, or create one node and return independently queried proof."""
        state = await self._inspect(lease)
        if state.candidate_count > 1 or state.stable_id_conflict_count:
            raise GraphIdentityConflictError("Neo4j episode identity is ambiguous or conflicting")
        if state.candidate_count == 1 and state.candidate_content != lease.text:
            raise GraphIdentityConflictError(
                "Neo4j episode content conflicts with the source revision"
            )

        verification = self._verification(lease, state)
        if verification.is_exact:
            return GraphProcessingResult(
                verification=verification,
                graph_counts=GraphCounts(),
                reused_existing=True,
            )

        graph_counts = GraphCounts()
        reused_existing = state.candidate_count == 1
        if state.candidate_count == 0:
            result = await self._add_episode(lease)
            graph_counts = self._graph_counts(result)

        updated = await self._stamp_metadata(lease)
        if updated != 1:
            raise GraphIdentityConflictError(
                "Neo4j episode could not be adopted without overwriting conflicting metadata"
            )

        verified_state = await self._inspect(lease)
        verification = self._verification(lease, verified_state)
        if verified_state.candidate_content != lease.text or not verification.is_exact:
            raise GraphVerificationError("Neo4j episode failed exact post-write verification")
        return GraphProcessingResult(
            verification=verification,
            graph_counts=graph_counts,
            reused_existing=reused_existing,
        )

    async def _inspect(self, lease: JobLease) -> _EpisodeState:
        stable_id = str(lease.episode_id)
        source_description = f"episode_{stable_id}"
        result = await self.graphiti.driver.execute_query(
            """
            /* graph_sync:inspect_episode */
            MATCH (ep:Episodic)
            WHERE ep.uuid = $stable_id
               OR ep.stable_id = $stable_id
               OR ep.source_description = $source_description
            WITH collect(DISTINCT ep) AS candidates
            RETURN size(candidates) AS candidate_count,
                   size([ep IN candidates WHERE ep.uuid = $stable_id])
                       AS native_uuid_count,
                   size([ep IN candidates WHERE ep.stable_id = $stable_id])
                       AS stable_id_count,
                   size([ep IN candidates
                         WHERE ep.source_description = $source_description])
                       AS source_description_count,
                   size([ep IN candidates
                         WHERE ep.source_fingerprint = $source_fingerprint])
                       AS source_fingerprint_count,
                   size([ep IN candidates
                         WHERE ep.sync_profile_fingerprint = $sync_profile_fingerprint])
                       AS sync_profile_fingerprint_count,
                   size([ep IN candidates
                         WHERE ep.embedding_profile_fingerprint =
                               $embedding_profile_fingerprint])
                       AS embedding_profile_fingerprint_count,
                   size([ep IN candidates
                         WHERE ep.stable_id = $stable_id
                           AND ep.source_description = $source_description
                           AND ep.source_fingerprint = $source_fingerprint
                           AND ep.sync_profile_fingerprint = $sync_profile_fingerprint
                           AND ep.embedding_profile_fingerprint =
                               $embedding_profile_fingerprint]) AS exact_count,
                   size([ep IN candidates
                         WHERE ep.stable_id IS NOT NULL
                           AND ep.stable_id <> $stable_id]) AS stable_id_conflict_count,
                   head([ep IN candidates | ep.content]) AS candidate_content
            """,
            {
                "stable_id": stable_id,
                "source_description": source_description,
                "source_fingerprint": lease.captured_source_fingerprint,
                "sync_profile_fingerprint": lease.sync_profile_fingerprint,
                "embedding_profile_fingerprint": self.profile.embedding_profile_fingerprint,
            },
        )
        records = _records(result)
        if not records:
            raise GraphVerificationError("Neo4j episode inspection returned no aggregate row")
        row = records[0]
        return _EpisodeState(
            candidate_count=int(row["candidate_count"]),
            native_uuid_count=int(row["native_uuid_count"]),
            stable_id_count=int(row["stable_id_count"]),
            source_description_count=int(row["source_description_count"]),
            source_fingerprint_count=int(row["source_fingerprint_count"]),
            sync_profile_fingerprint_count=int(row["sync_profile_fingerprint_count"]),
            embedding_profile_fingerprint_count=int(row["embedding_profile_fingerprint_count"]),
            exact_count=int(row["exact_count"]),
            stable_id_conflict_count=int(row["stable_id_conflict_count"]),
            candidate_content=row["candidate_content"],
        )

    async def _stamp_metadata(self, lease: JobLease) -> int:
        stable_id = str(lease.episode_id)
        result = await self.graphiti.driver.execute_query(
            """
            /* graph_sync:stamp_episode */
            MATCH (ep:Episodic)
            WHERE ep.uuid = $stable_id
               OR ep.stable_id = $stable_id
               OR ep.source_description = $source_description
            WITH collect(DISTINCT ep) AS candidates
            WITH candidates, head(candidates) AS ep
            WHERE size(candidates) = 1
              AND ep.content = $content
              AND (ep.stable_id IS NULL OR ep.stable_id = $stable_id)
              AND (ep.source_fingerprint IS NULL
                   OR ep.source_fingerprint = $source_fingerprint)
              AND (ep.sync_profile_fingerprint IS NULL
                   OR ep.sync_profile_fingerprint = $sync_profile_fingerprint)
              AND (ep.embedding_profile_fingerprint IS NULL
                   OR ep.embedding_profile_fingerprint =
                      $embedding_profile_fingerprint)
              AND NOT EXISTS {
                  MATCH (other:Episodic {uuid: $stable_id})
                  WHERE other <> ep
              }
            SET ep.uuid = $stable_id,
                ep.stable_id = $stable_id,
                ep.source_description = $source_description,
                ep.source_fingerprint = $source_fingerprint,
                ep.sync_profile_fingerprint = $sync_profile_fingerprint,
                ep.embedding_profile_fingerprint = $embedding_profile_fingerprint,
                ep.document_id = $document_id,
                ep.episode_index = $episode_index,
                ep.synced_at = $synced_at
            RETURN count(ep) AS updated_count
            """,
            {
                "stable_id": stable_id,
                "source_description": f"episode_{stable_id}",
                "content": lease.text,
                "source_fingerprint": lease.captured_source_fingerprint,
                "sync_profile_fingerprint": lease.sync_profile_fingerprint,
                "embedding_profile_fingerprint": self.profile.embedding_profile_fingerprint,
                "document_id": str(lease.document_id),
                "episode_index": lease.episode_index,
                "synced_at": datetime.now(UTC),
            },
        )
        records = _records(result)
        return int(records[0]["updated_count"]) if records else 0

    async def _add_episode(self, lease: JobLease) -> Any:
        stable_id = str(lease.episode_id)
        reference_time = lease.created_at
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            reference_time = reference_time.replace(tzinfo=UTC)
        instructions = (
            "Return only the most important facts from this episode. "
            f"Extract at most {self.profile.max_entities} entities and at most "
            f"{self.profile.max_relationships} relationships. "
            "Do not repeat equivalent entities or relationships."
        )
        return await self.graphiti.graphiti.add_episode(
            uuid=stable_id,
            name=f"episode_{stable_id}",
            episode_body=lease.text,
            source=EpisodeType.text,
            source_description=f"episode_{stable_id}",
            reference_time=reference_time,
            entity_types=ENTITY_TYPES,
            edge_types=EDGE_TYPES,
            edge_type_map={("Entity", "Entity"): list(EDGE_TYPES)},
            custom_extraction_instructions=instructions,
        )

    def _verification(self, lease: JobLease, state: _EpisodeState) -> StableIdVerification:
        return StableIdVerification(
            stable_id=str(lease.episode_id),
            candidate_count=state.candidate_count,
            stable_id_count=state.stable_id_count,
            source_description_count=state.source_description_count,
            exact_count=state.exact_count,
            source_fingerprint=lease.captured_source_fingerprint,
            sync_profile_fingerprint=lease.sync_profile_fingerprint,
            native_uuid_count=state.native_uuid_count,
            source_fingerprint_count=state.source_fingerprint_count,
            sync_profile_fingerprint_count=state.sync_profile_fingerprint_count,
            embedding_profile_fingerprint=self.profile.embedding_profile_fingerprint,
            embedding_profile_fingerprint_count=state.embedding_profile_fingerprint_count,
        )

    @staticmethod
    def _graph_counts(result: Any) -> GraphCounts:
        if result is None:
            return GraphCounts()
        nodes = getattr(result, "nodes", None)
        edges = getattr(result, "edges", None)
        return GraphCounts(
            accepted_entities=len(nodes) if nodes is not None else None,
            accepted_edges=len(edges) if edges is not None else None,
        )
