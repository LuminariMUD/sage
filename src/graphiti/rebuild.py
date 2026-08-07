"""Durable state transitions for controlled whole-graph rebuilds."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from src.db.postgres import PostgresDB
from src.graphiti.sync_models import GraphSyncStateError, validate_label
from src.graphiti.sync_state import RUN_START_LOCK_ID

AUDIT_FINGERPRINT_PATTERN = re.compile(r"^graph-audit:sha256:[0-9a-f]{64}$")
BACKUP_REFERENCE_PATTERN = re.compile(r"^backups/[A-Za-z0-9._/:+-]{1,247}$")
MAX_STATUS_EVENTS = 200


class GraphRebuildError(GraphSyncStateError):
    """Raised when a graph rebuild invariant rejects an operation."""


def audit_fingerprint(report: Mapping[str, Any]) -> str:
    """Hash stable audit evidence without its wall-clock generation time."""
    stable_report = {key: value for key, value in report.items() if key != "generated_at"}
    serialized = json.dumps(
        stable_report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(serialized.encode("ascii")).hexdigest()
    return f"graph-audit:sha256:{digest}"


def _validate_audit_fingerprint(value: str) -> str:
    if not isinstance(value, str) or not AUDIT_FINGERPRINT_PATTERN.fullmatch(value):
        raise ValueError("Graph audit fingerprint is invalid")
    return value


def _validate_backup_reference(value: str) -> str:
    if (
        not isinstance(value, str)
        or not BACKUP_REFERENCE_PATTERN.fullmatch(value)
        or "//" in value
        or value.endswith("/")
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise ValueError("Backup reference is invalid")
    return value


def _nonnegative(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _record(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class GraphRebuildRepository:
    """Own transactional rebuild preparation, clear, and audit transitions."""

    def __init__(self, postgres: PostgresDB):
        self.postgres = postgres

    async def active_operation(self) -> dict[str, Any] | None:
        """Return the active rebuild without changing it."""
        return _record(await self.postgres.fetchrow("""
                SELECT *
                FROM graph_rebuild_operations
                WHERE state <> 'completed'
                ORDER BY created_at
                LIMIT 1
                """))

    async def status_snapshot(self, operation_id: UUID | None = None) -> dict[str, Any]:
        """Return sanitized rebuild, active-profile, and event state."""
        if operation_id is None:
            operation = await self.postgres.fetchrow("""
                SELECT *
                FROM graph_rebuild_operations
                ORDER BY created_at DESC
                LIMIT 1
                """)
        else:
            operation = await self.postgres.fetchrow(
                "SELECT * FROM graph_rebuild_operations WHERE id = $1",
                operation_id,
            )
        active_profile = await self.postgres.fetchrow("""
            SELECT scope, sync_profile_fingerprint, embedding_profile_fingerprint,
                   rebuild_operation_id, activated_at
            FROM graph_sync_profile_state
            WHERE scope = 'graphiti'
            """)
        events: list[dict[str, Any]] = []
        event_count = 0
        if operation is not None:
            event_count = int(
                await self.postgres.fetchval(
                    """
                    SELECT count(*)
                    FROM graph_rebuild_events
                    WHERE rebuild_operation_id = $1
                    """,
                    operation["id"],
                )
            )
            event_rows = await self.postgres.fetch(
                """
                SELECT *
                FROM (
                    SELECT sequence, event_type, run_id, audit_fingerprint,
                           job_count, node_count, relationship_count, recorded_at
                    FROM graph_rebuild_events
                    WHERE rebuild_operation_id = $1
                    ORDER BY sequence DESC
                    LIMIT $2
                ) AS recent_events
                ORDER BY sequence
                """,
                operation["id"],
                MAX_STATUS_EVENTS,
            )
            events = [dict(row) for row in event_rows]
        return {
            "schema_version": 1,
            "operation": _record(operation),
            "active_profile": _record(active_profile),
            "event_count": event_count,
            "events_truncated": event_count > len(events),
            "events": events,
        }

    async def prepare(
        self,
        *,
        target_sync_profile_fingerprint: str,
        target_embedding_profile_fingerprint: str,
        backup_reference: str,
        backup_created_at: datetime,
        pre_audit_fingerprint: str,
        pre_postgres_episode_count: int,
        pre_neo4j_node_count: int,
        pre_neo4j_relationship_count: int,
    ) -> dict[str, Any]:
        """Atomically record a rebuild and requeue all jobs under its profile."""
        sync_profile = validate_label(
            target_sync_profile_fingerprint, "Target sync profile fingerprint"
        )
        embedding_profile = validate_label(
            target_embedding_profile_fingerprint,
            "Target embedding profile fingerprint",
        )
        reference = _validate_backup_reference(backup_reference)
        audit = _validate_audit_fingerprint(pre_audit_fingerprint)
        episode_count = _nonnegative(pre_postgres_episode_count, "Pre-rebuild episode count")
        node_count = _nonnegative(pre_neo4j_node_count, "Pre-rebuild node count")
        relationship_count = _nonnegative(
            pre_neo4j_relationship_count, "Pre-rebuild relationship count"
        )
        if not isinstance(backup_created_at, datetime) or backup_created_at.tzinfo is None:
            raise ValueError("Backup creation time must be timezone-aware")

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", RUN_START_LOCK_ID)
                if await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM graph_sync_runs WHERE state <> 'stopped')"
                ):
                    raise GraphRebuildError("An active graph sync run blocks rebuild preparation")
                if await connection.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM graph_rebuild_operations WHERE state <> 'completed'
                    )
                    """):
                    raise GraphRebuildError("A graph rebuild is already active")
                if await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM graph_sync_jobs WHERE state = 'leased')"
                ):
                    raise GraphRebuildError("Leased graph jobs block rebuild preparation")

                inventory = await connection.fetchrow("""
                    SELECT (SELECT count(*) FROM episodes) AS episodes,
                           (SELECT count(*) FROM graph_sync_jobs) AS jobs,
                           (
                               SELECT count(*)
                               FROM graph_sync_jobs AS job
                               JOIN episodes AS episode ON episode.id = job.episode_id
                               WHERE job.desired_source_fingerprint IS DISTINCT FROM
                                     graph_sync_source_fingerprint(episode.text)
                           ) AS stale_sources
                    """)
                actual_episodes = int(inventory["episodes"])
                actual_jobs = int(inventory["jobs"])
                if actual_episodes != episode_count:
                    raise GraphRebuildError("Episode inventory changed after the pre-rebuild audit")
                if actual_jobs != actual_episodes or int(inventory["stale_sources"]):
                    raise GraphRebuildError("Episode and durable job state do not reconcile")

                operation = await connection.fetchrow(
                    """
                    INSERT INTO graph_rebuild_operations (
                        target_sync_profile_fingerprint,
                        target_embedding_profile_fingerprint,
                        backup_reference,
                        backup_created_at,
                        pre_audit_fingerprint,
                        pre_postgres_episode_count,
                        pre_neo4j_node_count,
                        pre_neo4j_relationship_count,
                        initial_requeued_job_count
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $6)
                    RETURNING *
                    """,
                    sync_profile,
                    embedding_profile,
                    reference,
                    backup_created_at,
                    audit,
                    episode_count,
                    node_count,
                    relationship_count,
                )

                updated = await connection.fetchval(
                    """
                    WITH requeued AS (
                        UPDATE graph_sync_jobs
                        SET state = 'pending',
                            attempt_budget_count = 0,
                            retry_generation = retry_generation + 1,
                            next_attempt_at = NULL,
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            last_error_class = NULL,
                            last_error_code = NULL,
                            last_error_summary = NULL,
                            sync_profile_fingerprint = $1,
                            verified_source_fingerprint = NULL,
                            verified_sync_profile_fingerprint = NULL,
                            verified_at = NULL
                        RETURNING episode_id
                    )
                    SELECT count(*) FROM requeued
                    """,
                    sync_profile,
                )
                if int(updated) != episode_count:
                    raise GraphRebuildError("Durable graph job requeue count changed")

                await connection.execute(
                    """
                    INSERT INTO graph_rebuild_events (
                        rebuild_operation_id, sequence, event_type,
                        audit_fingerprint, job_count, node_count,
                        relationship_count
                    )
                    VALUES ($1, 1, 'jobs_requeued', $2, $3, $4, $5)
                    """,
                    operation["id"],
                    audit,
                    episode_count,
                    node_count,
                    relationship_count,
                )
                return dict(operation)

    async def mark_graph_cleared(
        self,
        operation_id: UUID,
        *,
        cleared_node_count: int,
        cleared_relationship_count: int,
        post_clear_audit_fingerprint: str,
    ) -> dict[str, Any]:
        """Record independently verified empty-graph and pending-job evidence."""
        node_count = _nonnegative(cleared_node_count, "Cleared node count")
        relationship_count = _nonnegative(cleared_relationship_count, "Cleared relationship count")
        audit = _validate_audit_fingerprint(post_clear_audit_fingerprint)

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", RUN_START_LOCK_ID)
                operation = await connection.fetchrow(
                    """
                    SELECT *
                    FROM graph_rebuild_operations
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    operation_id,
                )
                if operation is None or operation["state"] != "jobs_requeued":
                    raise GraphRebuildError("Graph rebuild is not waiting for graph-clear evidence")
                if await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM graph_sync_runs WHERE state <> 'stopped')"
                ):
                    raise GraphRebuildError("An active graph sync run blocks clear completion")

                inventory = await connection.fetchrow(
                    """
                    SELECT count(*) AS jobs,
                           count(*) FILTER (WHERE state <> 'pending') AS non_pending,
                           count(*) FILTER (
                               WHERE sync_profile_fingerprint <> $1
                           ) AS profile_mismatches,
                           count(*) FILTER (
                               WHERE desired_source_fingerprint IS DISTINCT FROM
                                     graph_sync_source_fingerprint(episode.text)
                           ) AS stale_sources
                    FROM graph_sync_jobs AS job
                    JOIN episodes AS episode ON episode.id = job.episode_id
                    """,
                    operation["target_sync_profile_fingerprint"],
                )
                jobs = int(inventory["jobs"])
                if any(
                    int(inventory[key])
                    for key in ("non_pending", "profile_mismatches", "stale_sources")
                ):
                    raise GraphRebuildError("Durable jobs changed before graph-clear verification")
                if jobs != await connection.fetchval("SELECT count(*) FROM episodes"):
                    raise GraphRebuildError("Episode and durable job counts diverged")

                next_state = "awaiting_audit" if jobs == 0 else "ready"
                completed = await connection.fetchrow(
                    """
                    UPDATE graph_rebuild_operations
                    SET state = $2,
                        ready_job_count = $3,
                        cleared_node_count = $4,
                        cleared_relationship_count = $5,
                        post_clear_audit_fingerprint = $6,
                        graph_cleared_at = clock_timestamp()
                    WHERE id = $1
                    RETURNING *
                    """,
                    operation_id,
                    next_state,
                    jobs,
                    node_count,
                    relationship_count,
                    audit,
                )
                next_sequence = await connection.fetchval(
                    """
                    SELECT COALESCE(max(sequence), 0) + 1
                    FROM graph_rebuild_events
                    WHERE rebuild_operation_id = $1
                    """,
                    operation_id,
                )
                await connection.execute(
                    """
                    INSERT INTO graph_rebuild_events (
                        rebuild_operation_id, sequence, event_type,
                        audit_fingerprint, job_count, node_count,
                        relationship_count
                    )
                    VALUES ($1, $2, 'graph_cleared', $3, $4, 0, 0)
                    """,
                    operation_id,
                    next_sequence,
                    audit,
                    jobs,
                )
                return dict(completed)

    async def finalize(
        self,
        operation_id: UUID,
        *,
        final_audit_fingerprint: str,
        audited_episode_count: int,
    ) -> dict[str, Any]:
        """Activate the rebuilt profiles only after complete clean reconciliation."""
        audit = _validate_audit_fingerprint(final_audit_fingerprint)
        audited_count = _nonnegative(audited_episode_count, "Audited episode count")

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", RUN_START_LOCK_ID)
                operation = await connection.fetchrow(
                    """
                    SELECT *
                    FROM graph_rebuild_operations
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    operation_id,
                )
                if operation is None or operation["state"] != "awaiting_audit":
                    raise GraphRebuildError("Graph rebuild is not awaiting its final audit")
                if await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM graph_sync_runs WHERE state <> 'stopped')"
                ):
                    raise GraphRebuildError("An active graph sync run blocks finalization")

                inventory = await connection.fetchrow(
                    """
                    SELECT count(*) AS jobs,
                           count(*) FILTER (WHERE state <> 'synced') AS non_synced,
                           count(*) FILTER (
                               WHERE sync_profile_fingerprint <> $1
                           ) AS profile_mismatches,
                           count(*) FILTER (
                               WHERE desired_source_fingerprint IS DISTINCT FROM
                                     graph_sync_source_fingerprint(episode.text)
                           ) AS stale_sources
                    FROM graph_sync_jobs AS job
                    JOIN episodes AS episode ON episode.id = job.episode_id
                    """,
                    operation["target_sync_profile_fingerprint"],
                )
                jobs = int(inventory["jobs"])
                if jobs != audited_count or jobs != await connection.fetchval(
                    "SELECT count(*) FROM episodes"
                ):
                    raise GraphRebuildError("Final audit inventory changed")
                if any(
                    int(inventory[key])
                    for key in ("non_synced", "profile_mismatches", "stale_sources")
                ):
                    raise GraphRebuildError("Graph rebuild jobs are not completely synchronized")

                completed = await connection.fetchrow(
                    """
                    UPDATE graph_rebuild_operations
                    SET state = 'completed',
                        final_audit_fingerprint = $2,
                        completed_at = clock_timestamp()
                    WHERE id = $1
                    RETURNING *
                    """,
                    operation_id,
                    audit,
                )
                await connection.execute(
                    """
                    INSERT INTO graph_sync_profile_state (
                        scope, sync_profile_fingerprint,
                        embedding_profile_fingerprint,
                        rebuild_operation_id, activated_at
                    )
                    VALUES ('graphiti', $1, $2, $3, clock_timestamp())
                    ON CONFLICT (scope) DO UPDATE
                    SET sync_profile_fingerprint = EXCLUDED.sync_profile_fingerprint,
                        embedding_profile_fingerprint = EXCLUDED.embedding_profile_fingerprint,
                        rebuild_operation_id = EXCLUDED.rebuild_operation_id,
                        activated_at = EXCLUDED.activated_at
                    """,
                    operation["target_sync_profile_fingerprint"],
                    operation["target_embedding_profile_fingerprint"],
                    operation_id,
                )
                next_sequence = await connection.fetchval(
                    """
                    SELECT COALESCE(max(sequence), 0) + 1
                    FROM graph_rebuild_events
                    WHERE rebuild_operation_id = $1
                    """,
                    operation_id,
                )
                await connection.execute(
                    """
                    INSERT INTO graph_rebuild_events (
                        rebuild_operation_id, sequence, event_type,
                        audit_fingerprint, job_count
                    )
                    VALUES ($1, $2, 'final_audit_passed', $3, $4)
                    """,
                    operation_id,
                    next_sequence,
                    audit,
                    jobs,
                )
                return dict(completed)
