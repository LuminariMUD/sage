"""Non-destructive, profile-isolated episode embedding evaluation."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any
from uuid import UUID

from src.db.embedding_profiles import embedding_profile_record
from src.llm.embeddings.validation import validate_embedding_batch
from src.llm.provider_config import EmbeddingProfile
from src.retrieval.benchmark import SourceSnapshot, summarize_source_snapshot

REGISTER_SHADOW_CONFIRMATION = "REGISTER_SHADOW_EMBEDDING_SPACE"
RUN_SHADOW_CONFIRMATION = "RUN_SHADOW_EMBEDDING_BACKFILL"
BUILD_SHADOW_INDEX_CONFIRMATION = "BUILD_SHADOW_EMBEDDING_INDEX"
RECOVER_SHADOW_RUN_CONFIRMATION = "RECOVER_SHADOW_EMBEDDING_RUN"

_PROFILE_FINGERPRINT = re.compile(r"^embedding:sha256:[0-9a-f]{64}$")
_INDEX_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_FAILURE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
_SOURCE_FINGERPRINT = re.compile(r"^sha256:v1:[0-9a-f]{64}$")
_SHADOW_LOCK_ID = 731047850174

SHADOW_TABLES_QUERY = """
    SELECT
        to_regclass('embedding_shadow_spaces')::text AS spaces_table,
        to_regclass('embedding_shadow_runs')::text AS runs_table,
        to_regclass('embedding_shadow_batches')::text AS batches_table,
        to_regclass('episode_embedding_shadows')::text AS vectors_table
"""

SOURCE_SNAPSHOT_QUERY = """
    SELECT
        episode.id AS episode_id,
        document.stable_id AS document_stable_id,
        episode.episode_index,
        job.desired_source_fingerprint AS source_fingerprint
    FROM episodes AS episode
    JOIN lore_documents AS document
      ON document.id = episode.document_id
    LEFT JOIN graph_sync_jobs AS job
      ON job.episode_id = episode.id
    ORDER BY document.stable_id, episode.episode_index
"""

PENDING_EPISODES_QUERY = """
    SELECT
        episode.id AS episode_id,
        document.stable_id AS document_stable_id,
        episode.episode_index,
        job.desired_source_fingerprint AS source_fingerprint,
        episode.text
    FROM episodes AS episode
    JOIN lore_documents AS document
      ON document.id = episode.document_id
    JOIN graph_sync_jobs AS job
      ON job.episode_id = episode.id
    LEFT JOIN episode_embedding_shadows AS shadow
      ON shadow.profile_fingerprint = $1
     AND shadow.episode_id = episode.id
    WHERE shadow.episode_id IS NULL
       OR shadow.source_fingerprint <> job.desired_source_fingerprint
    ORDER BY document.stable_id, episode.episode_index
    LIMIT $2
"""

SPACE_ROWS_QUERY = """
    SELECT
        space.profile_fingerprint,
        space.semantic_index,
        space.dimensions,
        space.distance_metric,
        space.index_name,
        space.state,
        space.ready_source_snapshot_fingerprint,
        space.ready_episode_count,
        space.ready_at,
        profile.provider,
        profile.endpoint_class,
        profile.implementation,
        profile.model,
        profile.model_revision,
        profile.output_encoding,
        profile.storage_type,
        profile.normalize,
        profile.input_type
    FROM embedding_shadow_spaces AS space
    JOIN embedding_profiles AS profile
      ON profile.fingerprint = space.profile_fingerprint
    WHERE ($1::text IS NULL OR space.profile_fingerprint = $1)
    ORDER BY space.created_at, space.profile_fingerprint
"""

SPACE_COVERAGE_QUERY = """
    SELECT
        count(*) AS stored_rows,
        count(*) FILTER (
            WHERE job.desired_source_fingerprint = shadow.source_fingerprint
        ) AS current_rows,
        count(*) FILTER (
            WHERE job.desired_source_fingerprint IS DISTINCT FROM shadow.source_fingerprint
        ) AS stale_rows
    FROM episode_embedding_shadows AS shadow
    LEFT JOIN graph_sync_jobs AS job
      ON job.episode_id = shadow.episode_id
    WHERE shadow.profile_fingerprint = $1
"""

INDEX_CATALOG_QUERY = """
    SELECT
        access_method.amname AS method,
        operator_class.opcname AS operator_class,
        index_relation.reloptions AS options,
        index_metadata.indisvalid AS valid,
        index_metadata.indisready AS ready,
        pg_get_indexdef(index_metadata.indexrelid) AS definition,
        pg_get_expr(index_metadata.indpred, index_metadata.indrelid) AS predicate
    FROM pg_index AS index_metadata
    JOIN pg_class AS index_relation
      ON index_relation.oid = index_metadata.indexrelid
    JOIN pg_am AS access_method
      ON access_method.oid = index_relation.relam
    LEFT JOIN pg_opclass AS operator_class
      ON operator_class.oid = index_metadata.indclass[0]
    WHERE index_metadata.indrelid = to_regclass('episode_embedding_shadows')
      AND index_relation.relname = $1
"""

CURRENT_COVERAGE_QUERY = """
    SELECT count(*)
    FROM episode_embedding_shadows AS shadow
    JOIN graph_sync_jobs AS job
      ON job.episode_id = shadow.episode_id
     AND job.desired_source_fingerprint = shadow.source_fingerprint
    WHERE shadow.profile_fingerprint = $1
"""

LATEST_RUN_QUERY = """
    SELECT id::text, profile_fingerprint, state,
           target_source_snapshot_fingerprint, target_episode_count,
           provider_request_limit, provider_requests_reserved,
           provider_requests_succeeded, stored_episode_count,
           input_tokens, total_tokens, estimated_cost_usd,
           failure_type, failure_code
    FROM embedding_shadow_runs
    WHERE profile_fingerprint = $1
    ORDER BY started_at DESC, id DESC
    LIMIT 1
"""


class ShadowEmbeddingError(RuntimeError):
    """Raised when shadow registration, backfill, indexing, or search is unsafe."""


@dataclass(frozen=True)
class ShadowEpisode:
    episode_id: UUID
    document_stable_id: str
    episode_index: int
    source_fingerprint: str
    text: str


def _row_dict(row: Any | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _profile_fingerprint(value: object) -> str:
    if not isinstance(value, str) or not _PROFILE_FINGERPRINT.fullmatch(value):
        raise ShadowEmbeddingError("Embedding profile fingerprint is invalid")
    return value


def _dimensions(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65_536:
        raise ShadowEmbeddingError("Embedding dimensions are invalid")
    return value


def _source_fingerprint(value: object) -> str:
    if not isinstance(value, str) or not _SOURCE_FINGERPRINT.fullmatch(value):
        raise ShadowEmbeddingError("Episode source fingerprint is invalid")
    return value


def _shadow_index_name(profile: EmbeddingProfile) -> str:
    digest = hashlib.sha256(profile.fingerprint.encode("ascii")).hexdigest()[:20]
    name = f"idx_ep_shadow_{profile.dimensions}_{digest}"
    if not _INDEX_NAME.fullmatch(name):
        raise ShadowEmbeddingError("Shadow index name is invalid")
    return name


def _profile_literal(profile_fingerprint: str) -> str:
    # The exact fingerprint grammar contains no SQL quoting characters.
    return "'" + _profile_fingerprint(profile_fingerprint) + "'"


def _index_statement(profile: EmbeddingProfile, index_name: str) -> str:
    if not _INDEX_NAME.fullmatch(index_name):
        raise ShadowEmbeddingError("Shadow index name is invalid")
    dimensions = _dimensions(profile.dimensions)
    fingerprint = _profile_literal(profile.fingerprint)
    return f"""
        CREATE INDEX {index_name}
        ON episode_embedding_shadows
        USING hnsw ((embedding::vector({dimensions})) vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE profile_fingerprint = {fingerprint}
    """


def shadow_search_query(profile: EmbeddingProfile) -> str:
    """Return a fixed-profile query eligible for the profile-specific HNSW index."""
    dimensions = _dimensions(profile.dimensions)
    fingerprint = _profile_literal(profile.fingerprint)
    return f"""
        SELECT
            document.stable_id AS document_stable_id,
            episode.episode_index,
            1 - (shadow.embedding::vector({dimensions}) <=> $1::vector({dimensions}))
                AS similarity
        FROM episode_embedding_shadows AS shadow
        JOIN episodes AS episode
          ON episode.id = shadow.episode_id
        JOIN lore_documents AS document
          ON document.id = episode.document_id
        JOIN graph_sync_jobs AS job
          ON job.episode_id = episode.id
         AND job.desired_source_fingerprint = shadow.source_fingerprint
        WHERE shadow.profile_fingerprint = {fingerprint}
        ORDER BY shadow.embedding::vector({dimensions}) <=> $1::vector({dimensions}),
                 document.stable_id,
                 episode.episode_index
        LIMIT $2
    """


def _index_matches(
    row: Mapping[str, object] | None,
    *,
    profile_fingerprint: str,
    dimensions: int,
) -> bool:
    if row is None:
        return False
    fingerprint = _profile_fingerprint(profile_fingerprint)
    definition = str(row.get("definition") or "")
    predicate = str(row.get("predicate") or "")
    options = set(row.get("options") or [])
    expected_predicate = f"(profile_fingerprint = '{fingerprint}'::text)"
    return bool(
        row.get("method") == "hnsw"
        and row.get("operator_class") == "vector_cosine_ops"
        and row.get("valid") is True
        and row.get("ready") is True
        and f"(((embedding)::vector({dimensions})) vector_cosine_ops)" in definition
        and {"m=16", "ef_construction=64"}.issubset(options)
        and predicate == expected_predicate
    )


def _validated_batch_metadata(
    metadata: Mapping[str, object], profile: EmbeddingProfile
) -> dict[str, object]:
    input_tokens = metadata.get("input_tokens", 0)
    total_tokens = metadata.get("total_tokens", input_tokens)
    if (
        not isinstance(input_tokens, int)
        or isinstance(input_tokens, bool)
        or input_tokens < 0
        or not isinstance(total_tokens, int)
        or isinstance(total_tokens, bool)
        or total_tokens < input_tokens
    ):
        raise ShadowEmbeddingError("Embedding usage metadata is invalid")

    actual_model = metadata.get("actual_model")
    if actual_model is not None and actual_model != profile.model:
        raise ShadowEmbeddingError("Embedding response model does not match shadow profile")

    cost = metadata.get("estimated_cost_usd")
    safe_cost: Decimal | None = None
    if cost is not None:
        if isinstance(cost, bool) or not isinstance(cost, (int, float, Decimal)):
            raise ShadowEmbeddingError("Embedding cost metadata is invalid")
        try:
            safe_cost = Decimal(str(cost))
        except Exception as error:
            raise ShadowEmbeddingError("Embedding cost metadata is invalid") from error
        if not safe_cost.is_finite() or safe_cost < 0:
            raise ShadowEmbeddingError("Embedding cost metadata is invalid")
    return {
        "input_tokens": input_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": safe_cost,
        "actual_model": actual_model,
    }


def _usage_metadata(embedder: Any, profile: EmbeddingProfile) -> dict[str, object]:
    reader = getattr(embedder, "sanitized_metadata", None)
    metadata = reader() if callable(reader) else {}
    if not isinstance(metadata, Mapping):
        return _validated_batch_metadata({}, profile)

    actual_model = metadata.get("actual_model")
    usage = metadata.get("usage")
    safe_usage: dict[str, int] = {}
    if isinstance(usage, Mapping):
        for name in ("input_tokens", "prompt_tokens", "total_tokens"):
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                safe_usage[name] = value
    input_tokens = safe_usage.get("input_tokens", safe_usage.get("prompt_tokens", 0))
    total_tokens = safe_usage.get("total_tokens", input_tokens)
    return _validated_batch_metadata(
        {
            "input_tokens": input_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": metadata.get("estimated_cost_usd"),
            "actual_model": actual_model,
        },
        profile,
    )


def _public_run(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "run_id": row["id"],
        "status": row["state"],
        "profile_fingerprint": row["profile_fingerprint"],
        "target_source_snapshot_fingerprint": row["target_source_snapshot_fingerprint"],
        "target_episode_count": row["target_episode_count"],
        "stored_episode_count": row["stored_episode_count"],
        "provider_requests": {
            "maximum": row["provider_request_limit"],
            "reserved": row["provider_requests_reserved"],
            "succeeded": row["provider_requests_succeeded"],
        },
        "usage": {
            "input_tokens": row["input_tokens"],
            "total_tokens": row["total_tokens"],
        },
        "estimated_cost_usd": (
            float(row["estimated_cost_usd"]) if row["estimated_cost_usd"] is not None else None
        ),
        "failure_type": row["failure_type"],
        "failure_code": row["failure_code"],
    }


class ShadowEmbeddingRepository:
    """Transactional storage boundary for one shadow embedding generation."""

    def __init__(self, postgres: Any):
        self.postgres = postgres

    async def _tables_available(self) -> bool:
        row = _row_dict(await self.postgres.fetchrow(SHADOW_TABLES_QUERY)) or {}
        return all(
            row.get(name)
            for name in ("spaces_table", "runs_table", "batches_table", "vectors_table")
        )

    async def current_snapshot(self, *, connection: Any | None = None) -> SourceSnapshot:
        database = connection or self.postgres
        rows = await database.fetch(SOURCE_SNAPSHOT_QUERY)
        try:
            snapshot, _ = summarize_source_snapshot(rows)
        except ValueError as error:
            raise ShadowEmbeddingError("Source snapshot cannot be fingerprinted") from error
        return snapshot

    async def inventory(
        self,
        profile: EmbeddingProfile | None = None,
        *,
        profile_fingerprint: str | None = None,
    ) -> dict[str, object]:
        """Return content-free source, coverage, profile, and index state."""
        if profile is not None and profile_fingerprint is not None:
            raise ShadowEmbeddingError("Shadow inventory profile selection is ambiguous")
        requested_fingerprint = profile.fingerprint if profile is not None else profile_fingerprint
        if requested_fingerprint is not None:
            _profile_fingerprint(requested_fingerprint)
        if not await self._tables_available():
            return {
                "schema_version": 1,
                "operation": "embedding_shadow_status",
                "status": "unavailable",
                "source_snapshot": None,
                "spaces": [],
                "findings": [
                    {
                        "code": "shadow_tables_missing",
                        "severity": "error",
                        "message": "Embedding shadow migration has not been applied",
                    }
                ],
            }

        snapshot = await self.current_snapshot()
        rows = await self.postgres.fetch(SPACE_ROWS_QUERY, requested_fingerprint)
        spaces: list[dict[str, object]] = []
        for raw in rows:
            row = dict(raw)
            fingerprint = _profile_fingerprint(row["profile_fingerprint"])
            dimensions = _dimensions(row["dimensions"])
            coverage = _row_dict(
                await self.postgres.fetchrow(SPACE_COVERAGE_QUERY, fingerprint)
            ) or {"stored_rows": 0, "current_rows": 0, "stale_rows": 0}
            index = _row_dict(await self.postgres.fetchrow(INDEX_CATALOG_QUERY, row["index_name"]))
            latest_run_row = _row_dict(await self.postgres.fetchrow(LATEST_RUN_QUERY, fingerprint))
            index_ready = _index_matches(
                index,
                profile_fingerprint=fingerprint,
                dimensions=dimensions,
            )
            current_rows = int(coverage["current_rows"])
            stale_rows = int(coverage["stale_rows"])
            findings: list[dict[str, str]] = []

            def add(code: str, message: str) -> None:
                findings.append({"code": code, "severity": "error", "message": message})

            if profile is not None:
                stored = {
                    "fingerprint": fingerprint,
                    "provider": row["provider"],
                    "endpoint_class": row["endpoint_class"],
                    "implementation": row["implementation"],
                    "model": row["model"],
                    "model_revision": row["model_revision"],
                    "dimensions": dimensions,
                    "output_encoding": row["output_encoding"],
                    "storage_type": row["storage_type"],
                    "normalize": row["normalize"],
                    "distance_metric": row["distance_metric"],
                    "input_type": row["input_type"],
                }
                if stored != embedding_profile_record(profile):
                    add(
                        "shadow_profile_mismatch",
                        "Stored shadow profile differs from configuration",
                    )
            if row["state"] == "retired":
                add("shadow_space_retired", "Shadow space is retired")
            if stale_rows:
                add("shadow_source_stale", "Some shadow vectors target stale source revisions")
            if current_rows != snapshot.episode_count:
                add("shadow_coverage_incomplete", "Shadow vectors do not cover the source snapshot")
            if row["state"] == "ready":
                if row["ready_source_snapshot_fingerprint"] != snapshot.fingerprint:
                    add("shadow_snapshot_mismatch", "Ready shadow snapshot differs from source")
                if row["ready_episode_count"] != snapshot.episode_count:
                    add("shadow_ready_count_mismatch", "Ready shadow count differs from source")
                if not index_ready:
                    add("shadow_index_invalid", "Ready shadow index is missing or invalid")

            spaces.append(
                {
                    "profile": {
                        "fingerprint": fingerprint,
                        "provider": row["provider"],
                        "model": row["model"],
                        "revision": row["model_revision"],
                        "dimensions": dimensions,
                        "distance_metric": row["distance_metric"],
                    },
                    "state": row["state"],
                    "index": {
                        "name": row["index_name"],
                        "method": index.get("method") if index else None,
                        "operator_class": index.get("operator_class") if index else None,
                        "valid": bool(index.get("valid")) if index else False,
                        "ready": index_ready,
                    },
                    "coverage": {
                        "source_rows": snapshot.episode_count,
                        "stored_rows": int(coverage["stored_rows"]),
                        "current_rows": current_rows,
                        "stale_rows": stale_rows,
                        "missing_rows": max(0, snapshot.episode_count - current_rows),
                    },
                    "ready_source_snapshot_fingerprint": row["ready_source_snapshot_fingerprint"],
                    "latest_run": _public_run(latest_run_row) if latest_run_row else None,
                    "ready": row["state"] == "ready" and not findings,
                    "findings": sorted(findings, key=lambda item: item["code"]),
                }
            )

        top_findings: list[dict[str, str]] = []
        if profile is not None and not spaces:
            top_findings.append(
                {
                    "code": "shadow_profile_not_registered",
                    "severity": "error",
                    "message": "Configured shadow profile is not registered",
                }
            )
        return {
            "schema_version": 1,
            "operation": "embedding_shadow_status",
            "status": (
                "ready" if spaces and all(space["ready"] for space in spaces) else "inventory"
            ),
            "source_snapshot": {
                "episode_count": snapshot.episode_count,
                "document_count": snapshot.document_count,
                "fingerprint": snapshot.fingerprint,
            },
            "spaces": spaces,
            "findings": top_findings,
        }

    async def require_registered(self, profile: EmbeddingProfile) -> dict[str, object]:
        report = await self.inventory(profile)
        if report["findings"] or len(report["spaces"]) != 1:
            raise ShadowEmbeddingError("Shadow embedding profile is not registered")
        space = report["spaces"][0]
        if any(
            finding["code"] in {"shadow_profile_mismatch", "shadow_space_retired"}
            for finding in space["findings"]
        ):
            raise ShadowEmbeddingError("Shadow embedding profile is unavailable")
        return space

    async def require_ready(self, profile: EmbeddingProfile) -> dict[str, object]:
        space = await self.require_registered(profile)
        if not space["ready"]:
            codes = ",".join(finding["code"] for finding in space["findings"])
            raise ShadowEmbeddingError(
                f"Shadow embedding space is not ready ({codes or 'not_ready'})"
            )
        return space

    async def register(self, profile: EmbeddingProfile) -> dict[str, object]:
        """Register immutable profile metadata without creating vectors or an index."""
        record = embedding_profile_record(profile)
        columns = tuple(record)
        values = tuple(record[column] for column in columns)
        placeholders = ", ".join(f"${position}" for position in range(1, len(values) + 1))
        index_name = _shadow_index_name(profile)
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", _SHADOW_LOCK_ID)
                tables = _row_dict(await connection.fetchrow(SHADOW_TABLES_QUERY)) or {}
                if not all(tables.values()):
                    raise ShadowEmbeddingError("Embedding shadow migration has not been applied")
                await connection.execute(
                    f"""
                    INSERT INTO embedding_profiles ({', '.join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT (fingerprint) DO NOTHING
                    """,
                    *values,
                )
                stored = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT fingerprint, provider, endpoint_class, implementation, model,
                               model_revision, dimensions, output_encoding, storage_type,
                               normalize, distance_metric, input_type
                        FROM embedding_profiles
                        WHERE fingerprint = $1
                        """,
                        profile.fingerprint,
                    )
                )
                if stored != record:
                    raise ShadowEmbeddingError("Stored embedding profile identity is inconsistent")
                collision = await connection.fetchval("SELECT to_regclass($1)::text", index_name)
                existing = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT profile_fingerprint, dimensions, distance_metric, index_name, state
                        FROM embedding_shadow_spaces
                        WHERE profile_fingerprint = $1
                        FOR UPDATE
                        """,
                        profile.fingerprint,
                    )
                )
                if existing is None:
                    if collision is not None:
                        raise ShadowEmbeddingError("Shadow index name is already in use")
                    await connection.execute(
                        """
                        INSERT INTO embedding_shadow_spaces (
                            profile_fingerprint, dimensions, distance_metric, index_name
                        )
                        VALUES ($1, $2, $3, $4)
                        """,
                        profile.fingerprint,
                        profile.dimensions,
                        profile.distance_metric,
                        index_name,
                    )
                elif existing != {
                    "profile_fingerprint": profile.fingerprint,
                    "dimensions": profile.dimensions,
                    "distance_metric": profile.distance_metric,
                    "index_name": index_name,
                    "state": existing["state"],
                }:
                    raise ShadowEmbeddingError("Registered shadow identity is inconsistent")
                elif existing["state"] == "retired":
                    raise ShadowEmbeddingError("Retired shadow spaces cannot be reused")
        return await self.inventory(profile)

    async def pending_episodes(
        self, profile: EmbeddingProfile, *, limit: int
    ) -> list[ShadowEpisode]:
        if not 1 <= limit <= profile.batch_size:
            raise ShadowEmbeddingError("Shadow batch limit is invalid")
        rows = await self.postgres.fetch(PENDING_EPISODES_QUERY, profile.fingerprint, limit)
        episodes: list[ShadowEpisode] = []
        for row in rows:
            value = dict(row)
            text = value.get("text")
            if not isinstance(text, str) or not text:
                raise ShadowEmbeddingError("Episode text is invalid")
            episodes.append(
                ShadowEpisode(
                    episode_id=UUID(str(value["episode_id"])),
                    document_stable_id=str(value["document_stable_id"]),
                    episode_index=int(value["episode_index"]),
                    source_fingerprint=_source_fingerprint(value["source_fingerprint"]),
                    text=text,
                )
            )
        return episodes

    async def start_run(
        self,
        profile: EmbeddingProfile,
        snapshot: SourceSnapshot,
        *,
        provider_request_limit: int,
    ) -> UUID:
        if not 1 <= provider_request_limit <= 100:
            raise ShadowEmbeddingError("Shadow provider-request limit is invalid")
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", _SHADOW_LOCK_ID)
                space = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT state
                        FROM embedding_shadow_spaces
                        WHERE profile_fingerprint = $1
                        FOR UPDATE
                        """,
                        profile.fingerprint,
                    )
                )
                if space is None or space["state"] == "retired":
                    raise ShadowEmbeddingError("Shadow embedding profile is unavailable")
                running = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM embedding_shadow_runs
                        WHERE profile_fingerprint = $1 AND state = 'running'
                    )
                    """,
                    profile.fingerprint,
                )
                if running:
                    raise ShadowEmbeddingError("A shadow backfill run is already active")
                await connection.execute(
                    """
                    UPDATE embedding_shadow_spaces
                    SET state = 'backfilling',
                        ready_source_snapshot_fingerprint = NULL,
                        ready_episode_count = NULL,
                        ready_at = NULL,
                        retired_at = NULL
                    WHERE profile_fingerprint = $1
                    """,
                    profile.fingerprint,
                )
                run_id = await connection.fetchval(
                    """
                    INSERT INTO embedding_shadow_runs (
                        profile_fingerprint, target_source_snapshot_fingerprint,
                        target_episode_count, provider_request_limit
                    )
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    profile.fingerprint,
                    snapshot.fingerprint,
                    snapshot.episode_count,
                    provider_request_limit,
                )
        return UUID(str(run_id))

    async def reserve_batch(
        self,
        run_id: UUID,
        profile: EmbeddingProfile,
        episodes: Sequence[ShadowEpisode],
    ) -> int:
        if not episodes or len(episodes) > profile.batch_size:
            raise ShadowEmbeddingError("Shadow batch is empty or too large")
        episode_ids = [episode.episode_id for episode in episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise ShadowEmbeddingError("Shadow batch contains duplicate episodes")
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                run = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT profile_fingerprint, state, provider_request_limit,
                               provider_requests_reserved
                        FROM embedding_shadow_runs
                        WHERE id = $1
                        FOR UPDATE
                        """,
                        run_id,
                    )
                )
                if run is None or run["profile_fingerprint"] != profile.fingerprint:
                    raise ShadowEmbeddingError("Shadow backfill run identity is invalid")
                if run["state"] != "running":
                    raise ShadowEmbeddingError("Shadow backfill run is not active")
                if run["provider_requests_reserved"] >= run["provider_request_limit"]:
                    raise ShadowEmbeddingError("Shadow provider-request ceiling is exhausted")
                current_rows = await connection.fetch(
                    """
                    SELECT episode.id AS episode_id, job.desired_source_fingerprint
                    FROM episodes AS episode
                    JOIN graph_sync_jobs AS job ON job.episode_id = episode.id
                    WHERE episode.id = ANY($1::uuid[])
                    """,
                    episode_ids,
                )
                current = {
                    UUID(str(row["episode_id"])): row["desired_source_fingerprint"]
                    for row in current_rows
                }
                if len(current) != len(episodes) or any(
                    current.get(episode.episode_id) != episode.source_fingerprint
                    for episode in episodes
                ):
                    raise ShadowEmbeddingError("Shadow batch source changed before reservation")
                ordinal = int(run["provider_requests_reserved"]) + 1
                await connection.execute(
                    """
                    INSERT INTO embedding_shadow_batches (
                        run_id, profile_fingerprint, ordinal, episode_count
                    )
                    VALUES ($1, $2, $3, $4)
                    """,
                    run_id,
                    profile.fingerprint,
                    ordinal,
                    len(episodes),
                )
                await connection.executemany(
                    """
                    INSERT INTO embedding_shadow_batch_items (
                        run_id, batch_ordinal, position, episode_id, source_fingerprint
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    [
                        (
                            run_id,
                            ordinal,
                            position,
                            episode.episode_id,
                            episode.source_fingerprint,
                        )
                        for position, episode in enumerate(episodes)
                    ],
                )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_runs
                    SET provider_requests_reserved = provider_requests_reserved + 1,
                        updated_at = clock_timestamp()
                    WHERE id = $1
                    """,
                    run_id,
                )
        return ordinal

    async def finalize_batch_success(
        self,
        run_id: UUID,
        ordinal: int,
        profile: EmbeddingProfile,
        episodes: Sequence[ShadowEpisode],
        vectors: Sequence[Sequence[float]],
        *,
        latency_ms: int,
        metadata: Mapping[str, object],
    ) -> bool:
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or latency_ms < 0:
            raise ShadowEmbeddingError("Shadow batch latency is invalid")
        safe_metadata = _validated_batch_metadata(metadata, profile)
        validated = validate_embedding_batch(
            vectors,
            expected_count=len(episodes),
            dimensions=profile.dimensions,
        )
        episode_ids = [episode.episode_id for episode in episodes]
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                batch = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT state, profile_fingerprint, episode_count
                        FROM embedding_shadow_batches
                        WHERE run_id = $1 AND ordinal = $2
                        FOR UPDATE
                        """,
                        run_id,
                        ordinal,
                    )
                )
                if (
                    batch is None
                    or batch["state"] != "reserved"
                    or batch["profile_fingerprint"] != profile.fingerprint
                    or batch["episode_count"] != len(episodes)
                ):
                    raise ShadowEmbeddingError("Shadow batch reservation is invalid")
                reserved_rows = await connection.fetch(
                    """
                    SELECT position, episode_id, source_fingerprint
                    FROM embedding_shadow_batch_items
                    WHERE run_id = $1 AND batch_ordinal = $2
                    ORDER BY position
                    """,
                    run_id,
                    ordinal,
                )
                reserved = [
                    (
                        int(row["position"]),
                        UUID(str(row["episode_id"])),
                        row["source_fingerprint"],
                    )
                    for row in reserved_rows
                ]
                expected = [
                    (position, episode.episode_id, episode.source_fingerprint)
                    for position, episode in enumerate(episodes)
                ]
                if reserved != expected:
                    raise ShadowEmbeddingError("Shadow batch items differ from reservation")
                current_rows = await connection.fetch(
                    """
                    SELECT episode.id AS episode_id, job.desired_source_fingerprint
                    FROM episodes AS episode
                    JOIN graph_sync_jobs AS job ON job.episode_id = episode.id
                    WHERE episode.id = ANY($1::uuid[])
                    """,
                    episode_ids,
                )
                current = {
                    UUID(str(row["episode_id"])): row["desired_source_fingerprint"]
                    for row in current_rows
                }
                source_changed = len(current) != len(episodes) or any(
                    current.get(episode.episode_id) != episode.source_fingerprint
                    for episode in episodes
                )
                state = "source_changed" if source_changed else "succeeded"
                if not source_changed:
                    await connection.executemany(
                        """
                        INSERT INTO episode_embedding_shadows (
                            profile_fingerprint, episode_id, source_fingerprint,
                            dimensions, embedding, run_id, batch_ordinal
                        )
                        VALUES ($1, $2, $3, $4, $5::vector, $6, $7)
                        ON CONFLICT (profile_fingerprint, episode_id) DO UPDATE
                        SET source_fingerprint = EXCLUDED.source_fingerprint,
                            dimensions = EXCLUDED.dimensions,
                            embedding = EXCLUDED.embedding,
                            run_id = EXCLUDED.run_id,
                            batch_ordinal = EXCLUDED.batch_ordinal,
                            updated_at = clock_timestamp()
                        """,
                        [
                            (
                                profile.fingerprint,
                                episode.episode_id,
                                episode.source_fingerprint,
                                profile.dimensions,
                                "[" + ",".join(map(str, vector)) + "]",
                                run_id,
                                ordinal,
                            )
                            for episode, vector in zip(episodes, validated, strict=True)
                        ],
                    )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_batches
                    SET state = $3,
                        latency_ms = $4,
                        input_tokens = $5,
                        total_tokens = $6,
                        estimated_cost_usd = $7,
                        actual_model = $8,
                        completed_at = clock_timestamp()
                    WHERE run_id = $1 AND ordinal = $2
                    """,
                    run_id,
                    ordinal,
                    state,
                    latency_ms,
                    safe_metadata["input_tokens"],
                    safe_metadata["total_tokens"],
                    safe_metadata["estimated_cost_usd"],
                    safe_metadata["actual_model"],
                )
                stored_count = await connection.fetchval(
                    CURRENT_COVERAGE_QUERY, profile.fingerprint
                )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_runs
                    SET provider_requests_succeeded = provider_requests_succeeded + 1,
                        stored_episode_count = $2,
                        input_tokens = input_tokens + $3,
                        total_tokens = total_tokens + $4,
                        estimated_cost_usd = CASE
                            WHEN $5::numeric IS NULL THEN estimated_cost_usd
                            ELSE COALESCE(estimated_cost_usd, 0) + $5::numeric
                        END,
                        updated_at = clock_timestamp()
                    WHERE id = $1
                    """,
                    run_id,
                    int(stored_count),
                    safe_metadata["input_tokens"],
                    safe_metadata["total_tokens"],
                    safe_metadata["estimated_cost_usd"],
                )
        return not source_changed

    async def finalize_batch_failure(
        self,
        run_id: UUID,
        ordinal: int,
        error: Exception,
    ) -> None:
        failure_type = type(error).__name__
        if not _FAILURE_TYPE.fullmatch(failure_type):
            failure_type = "Exception"
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                batch = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT state
                        FROM embedding_shadow_batches
                        WHERE run_id = $1 AND ordinal = $2
                        FOR UPDATE
                        """,
                        run_id,
                        ordinal,
                    )
                )
                if batch is None or batch["state"] != "reserved":
                    raise ShadowEmbeddingError("Shadow batch is not reserved")
                await connection.execute(
                    """
                    UPDATE embedding_shadow_batches
                    SET state = 'failed',
                        failure_type = $3,
                        failure_code = 'provider_request_failed',
                        completed_at = clock_timestamp()
                    WHERE run_id = $1 AND ordinal = $2 AND state = 'reserved'
                    """,
                    run_id,
                    ordinal,
                    failure_type,
                )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_runs
                    SET state = 'failed',
                        failure_type = $2,
                        failure_code = 'provider_request_failed',
                        updated_at = clock_timestamp(),
                        finished_at = clock_timestamp()
                    WHERE id = $1 AND state = 'running'
                    """,
                    run_id,
                    failure_type,
                )

    async def recover_run(self, run_id: UUID) -> dict[str, object]:
        """Finalize an explicitly abandoned invocation so a new run can resume."""
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", _SHADOW_LOCK_ID)
                run = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT profile_fingerprint, state
                        FROM embedding_shadow_runs
                        WHERE id = $1
                        FOR UPDATE
                        """,
                        run_id,
                    )
                )
                if run is None:
                    raise ShadowEmbeddingError("Shadow backfill run does not exist")
                if run["state"] != "running":
                    raise ShadowEmbeddingError("Only a running shadow backfill can be recovered")
                await connection.execute(
                    """
                    UPDATE embedding_shadow_batches
                    SET state = 'abandoned',
                        failure_code = 'operator_recovery',
                        completed_at = clock_timestamp()
                    WHERE run_id = $1 AND state = 'reserved'
                    """,
                    run_id,
                )
                current_count = int(
                    await connection.fetchval(
                        CURRENT_COVERAGE_QUERY,
                        run["profile_fingerprint"],
                    )
                )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_runs
                    SET state = 'stopped',
                        stored_episode_count = LEAST(target_episode_count, $2),
                        failure_code = 'operator_recovery',
                        updated_at = clock_timestamp(),
                        finished_at = clock_timestamp()
                    WHERE id = $1
                    """,
                    run_id,
                    current_count,
                )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_spaces
                    SET state = 'backfilling',
                        ready_source_snapshot_fingerprint = NULL,
                        ready_episode_count = NULL,
                        ready_at = NULL
                    WHERE profile_fingerprint = $1
                    """,
                    run["profile_fingerprint"],
                )
        return await self.run_report(run_id)

    async def finish_run(
        self,
        run_id: UUID,
        profile: EmbeddingProfile,
        target_snapshot: SourceSnapshot,
    ) -> dict[str, object]:
        current_snapshot = await self.current_snapshot()
        current_count = int(
            await self.postgres.fetchval(CURRENT_COVERAGE_QUERY, profile.fingerprint)
        )
        complete = (
            current_snapshot == target_snapshot and current_count == target_snapshot.episode_count
        )
        final_state = "completed" if complete else "stopped"
        stop_code = (
            "source_snapshot_changed"
            if current_snapshot != target_snapshot
            else "provider_request_limit_reached"
        )
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                run = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT state FROM embedding_shadow_runs WHERE id = $1 FOR UPDATE
                        """,
                        run_id,
                    )
                )
                if run is None or run["state"] != "running":
                    raise ShadowEmbeddingError("Shadow backfill run is not active")
                reserved_batches = await connection.fetchval(
                    """
                    SELECT count(*) FROM embedding_shadow_batches
                    WHERE run_id = $1 AND state = 'reserved'
                    """,
                    run_id,
                )
                if reserved_batches:
                    raise ShadowEmbeddingError(
                        "Shadow backfill run has an unresolved provider reservation"
                    )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_runs
                    SET state = $2,
                        stored_episode_count = $3,
                        failure_code = CASE WHEN $2 = 'stopped' THEN $4 ELSE NULL END,
                        updated_at = clock_timestamp(),
                        finished_at = clock_timestamp()
                    WHERE id = $1
                    """,
                    run_id,
                    final_state,
                    current_count,
                    stop_code,
                )
                await connection.execute(
                    """
                    UPDATE embedding_shadow_spaces
                    SET state = $2,
                        ready_source_snapshot_fingerprint = NULL,
                        ready_episode_count = NULL,
                        ready_at = NULL
                    WHERE profile_fingerprint = $1
                    """,
                    profile.fingerprint,
                    "indexing" if complete else "backfilling",
                )
        return await self.run_report(run_id)

    async def run_report(self, run_id: UUID) -> dict[str, object]:
        row = _row_dict(
            await self.postgres.fetchrow(
                """
                SELECT id::text, profile_fingerprint, state,
                       target_source_snapshot_fingerprint, target_episode_count,
                       provider_request_limit, provider_requests_reserved,
                       provider_requests_succeeded, stored_episode_count,
                       input_tokens, total_tokens, estimated_cost_usd,
                       failure_type, failure_code
                FROM embedding_shadow_runs
                WHERE id = $1
                """,
                run_id,
            )
        )
        if row is None:
            raise ShadowEmbeddingError("Shadow backfill run does not exist")
        return {
            "schema_version": 1,
            "operation": "embedding_shadow_backfill",
            **_public_run(row),
        }

    async def build_index(self, profile: EmbeddingProfile) -> dict[str, object]:
        """Build and attest a profile-specific HNSW index without touching active vectors."""
        await self.require_registered(profile)
        expected_index_name = _shadow_index_name(profile)
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", _SHADOW_LOCK_ID)
                running = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM embedding_shadow_runs
                        WHERE profile_fingerprint = $1 AND state = 'running'
                    )
                    """,
                    profile.fingerprint,
                )
                if running:
                    raise ShadowEmbeddingError("Shadow index cannot build during a backfill run")
                space = _row_dict(
                    await connection.fetchrow(
                        """
                        SELECT state, index_name
                        FROM embedding_shadow_spaces
                        WHERE profile_fingerprint = $1
                        FOR UPDATE
                        """,
                        profile.fingerprint,
                    )
                )
                if space is None or space["state"] == "retired":
                    raise ShadowEmbeddingError("Shadow embedding profile is unavailable")
                if space["index_name"] != expected_index_name:
                    raise ShadowEmbeddingError("Shadow index identity is inconsistent")

                before_snapshot = await self.current_snapshot(connection=connection)
                coverage = int(
                    await connection.fetchval(CURRENT_COVERAGE_QUERY, profile.fingerprint)
                )
                if coverage != before_snapshot.episode_count:
                    raise ShadowEmbeddingError("Shadow index requires complete current coverage")
                await connection.execute(
                    """
                    UPDATE embedding_shadow_spaces
                    SET state = 'indexing',
                        ready_source_snapshot_fingerprint = NULL,
                        ready_episode_count = NULL,
                        ready_at = NULL
                    WHERE profile_fingerprint = $1
                    """,
                    profile.fingerprint,
                )
                existing = _row_dict(
                    await connection.fetchrow(INDEX_CATALOG_QUERY, expected_index_name)
                )
                if existing is None:
                    await connection.execute(_index_statement(profile, expected_index_name))
                elif not _index_matches(
                    existing,
                    profile_fingerprint=profile.fingerprint,
                    dimensions=profile.dimensions,
                ):
                    raise ShadowEmbeddingError("Existing shadow index is incompatible")

                index = _row_dict(
                    await connection.fetchrow(INDEX_CATALOG_QUERY, expected_index_name)
                )
                after_snapshot = await self.current_snapshot(connection=connection)
                after_coverage = int(
                    await connection.fetchval(CURRENT_COVERAGE_QUERY, profile.fingerprint)
                )
                if (
                    after_snapshot != before_snapshot
                    or after_coverage != after_snapshot.episode_count
                    or not _index_matches(
                        index,
                        profile_fingerprint=profile.fingerprint,
                        dimensions=profile.dimensions,
                    )
                ):
                    await connection.execute(
                        """
                        UPDATE embedding_shadow_spaces
                        SET state = 'backfilling',
                            ready_source_snapshot_fingerprint = NULL,
                            ready_episode_count = NULL,
                            ready_at = NULL
                        WHERE profile_fingerprint = $1
                        """,
                        profile.fingerprint,
                    )
                    raise ShadowEmbeddingError("Shadow index attestation changed during build")
                await connection.execute(
                    """
                    UPDATE embedding_shadow_spaces
                    SET state = 'ready',
                        ready_source_snapshot_fingerprint = $2,
                        ready_episode_count = $3,
                        ready_at = clock_timestamp()
                    WHERE profile_fingerprint = $1
                    """,
                    profile.fingerprint,
                    after_snapshot.fingerprint,
                    after_snapshot.episode_count,
                )
        return await self.inventory(profile)


async def execute_shadow_backfill(
    repository: ShadowEmbeddingRepository,
    profile: EmbeddingProfile,
    embedder: Any,
    *,
    maximum_provider_requests: int,
) -> dict[str, object]:
    """Run bounded batches with durable pre-call reservation and source fencing."""
    if not 1 <= maximum_provider_requests <= 100:
        raise ShadowEmbeddingError("Shadow provider-request limit is invalid")
    await repository.require_registered(profile)
    target_snapshot = await repository.current_snapshot()
    run_id = await repository.start_run(
        profile,
        target_snapshot,
        provider_request_limit=maximum_provider_requests,
    )

    for _ in range(maximum_provider_requests):
        episodes = await repository.pending_episodes(profile, limit=profile.batch_size)
        if not episodes:
            break
        ordinal = await repository.reserve_batch(run_id, profile, episodes)
        started = perf_counter()
        try:
            vectors = await embedder.embed_batch([episode.text for episode in episodes])
            validated = validate_embedding_batch(
                vectors,
                expected_count=len(episodes),
                dimensions=profile.dimensions,
            )
            metadata = _usage_metadata(embedder, profile)
            await repository.finalize_batch_success(
                run_id,
                ordinal,
                profile,
                episodes,
                validated,
                latency_ms=max(0, round((perf_counter() - started) * 1_000)),
                metadata=metadata,
            )
        except Exception as error:
            await repository.finalize_batch_failure(run_id, ordinal, error)
            raise ShadowEmbeddingError("Shadow embedding provider request failed") from error

    return await repository.finish_run(run_id, profile, target_snapshot)


def planned_backfill_requests(pending_episode_count: int, profile: EmbeddingProfile) -> int:
    if pending_episode_count < 0:
        raise ShadowEmbeddingError("Pending episode count is invalid")
    return math.ceil(pending_episode_count / profile.batch_size)
