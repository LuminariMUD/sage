"""Transactional integration tests for the durable graph-sync migration."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from src.graphiti.audit import source_content_fingerprint

pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "migrations" / "0001_graph_sync_lifecycle.sql"
)


async def _expect_database_rejection(connection, statement: str, *args) -> None:
    """Run one expected failure in a savepoint so the outer test stays usable."""
    savepoint = connection.transaction()
    await savepoint.start()
    try:
        with pytest.raises(asyncpg.PostgresError):
            await connection.execute(statement, *args)
    finally:
        await savepoint.rollback()


@pytest.mark.asyncio
async def test_graph_sync_migration_seed_guards_and_immutable_ledgers():
    schema_name = f"graph_sync_test_{uuid4().hex}"
    connection = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
    )
    outer = connection.transaction()
    await outer.start()
    try:
        await connection.execute(f'CREATE SCHEMA "{schema_name}"')
        await connection.execute(f'SET LOCAL search_path TO "{schema_name}", public')
        await connection.execute("""
            CREATE TABLE episodes (
                id UUID PRIMARY KEY,
                text TEXT NOT NULL,
                graphiti_synced BOOLEAN DEFAULT FALSE,
                graphiti_synced_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT clock_timestamp(),
                updated_at TIMESTAMPTZ DEFAULT clock_timestamp()
            )
            """)
        synced_id = uuid4()
        pending_id = uuid4()
        await connection.executemany(
            """
            INSERT INTO episodes (id, text, graphiti_synced, graphiti_synced_at)
            VALUES ($1, $2, $3, CASE WHEN $3 THEN clock_timestamp() ELSE NULL END)
            """,
            [
                (synced_id, "Verified lore", True),
                (pending_id, "Pending lore", False),
            ],
        )

        await connection.execute(MIGRATION_PATH.read_text(encoding="ascii"))

        counts = await connection.fetchrow("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE state = 'synced') AS synced,
                   count(*) FILTER (WHERE state = 'pending') AS pending
            FROM graph_sync_jobs
            """)
        assert dict(counts) == {"total": 2, "synced": 1, "pending": 1}
        sql_fingerprint = await connection.fetchval(
            "SELECT graph_sync_source_fingerprint($1)", "Verified lore"
        )
        assert sql_fingerprint == source_content_fingerprint("Verified lore")

        await _expect_database_rejection(
            connection,
            "UPDATE episodes SET graphiti_synced = TRUE WHERE id = $1",
            pending_id,
        )

        run_id = await connection.fetchval("""
            INSERT INTO graph_sync_runs (worker_id, sync_profile_fingerprint)
            VALUES ('test-worker', 'sync:test')
            RETURNING id
            """)
        await _expect_database_rejection(
            connection,
            """
            INSERT INTO graph_sync_runs (worker_id, sync_profile_fingerprint)
            VALUES ('second-worker', 'sync:test')
            """,
        )

        attempt_id = uuid4()
        lease_token = uuid4()
        await connection.execute(
            """
            UPDATE graph_sync_jobs
            SET state = 'leased',
                job_attempt_count = 1,
                lease_owner = 'test-worker',
                lease_token = $2,
                lease_expires_at = clock_timestamp() + interval '15 minutes',
                last_attempt_id = $3,
                sync_profile_fingerprint = 'sync:test'
            WHERE episode_id = $1
            """,
            pending_id,
            lease_token,
            attempt_id,
        )
        await connection.execute(
            """
            INSERT INTO graph_sync_attempts (
                id,
                episode_id,
                run_id,
                attempt_number,
                lease_token,
                lease_owner,
                captured_source_fingerprint,
                sync_profile_fingerprint,
                route_fingerprint
            )
            SELECT $1, episode_id, $2, 1, $3, 'test-worker',
                   desired_source_fingerprint, 'sync:test', 'route:test'
            FROM graph_sync_jobs
            WHERE episode_id = $4
            """,
            attempt_id,
            run_id,
            lease_token,
            pending_id,
        )
        await connection.execute(
            """
            INSERT INTO graph_sync_provider_calls (
                attempt_id,
                call_number,
                logical_model_attempt,
                transport_attempt,
                provider,
                model,
                candidate_fingerprint,
                prompt_version,
                schema_version,
                started_at,
                completed_at,
                latency_ms,
                outcome
            )
            VALUES (
                $1, 1, 1, 1, 'ollama', 'test-model', 'candidate:test',
                'prompt:v1', 'schema:v1', clock_timestamp(), clock_timestamp(),
                0, 'success'
            )
            """,
            attempt_id,
        )
        await connection.execute(
            """
            INSERT INTO graph_sync_attempt_results (
                attempt_id, outcome, provider_call_count
            )
            VALUES ($1, 'primary_success', 1)
            """,
            attempt_id,
        )

        await _expect_database_rejection(
            connection,
            "UPDATE graph_sync_attempts SET route_fingerprint = 'changed' WHERE id = $1",
            attempt_id,
        )
        await _expect_database_rejection(
            connection,
            "DELETE FROM graph_sync_provider_calls WHERE attempt_id = $1",
            attempt_id,
        )

        fingerprint = source_content_fingerprint("Pending lore")
        await connection.execute(
            """
            UPDATE graph_sync_jobs
            SET state = 'synced',
                lease_owner = NULL,
                lease_token = NULL,
                lease_expires_at = NULL,
                verified_source_fingerprint = $2,
                verified_sync_profile_fingerprint = 'sync:test',
                verified_at = clock_timestamp()
            WHERE episode_id = $1
            """,
            pending_id,
            fingerprint,
        )
        projected = await connection.fetchrow(
            """
            SELECT graphiti_synced, graphiti_synced_at IS NOT NULL AS has_timestamp
            FROM episodes
            WHERE id = $1
            """,
            pending_id,
        )
        assert dict(projected) == {"graphiti_synced": True, "has_timestamp": True}

        await connection.execute(
            "UPDATE episodes SET text = text || ' revised' WHERE id = $1",
            pending_id,
        )
        requeued = await connection.fetchrow(
            """
            SELECT job.state,
                   job.verified_at,
                   episode.graphiti_synced,
                   job.desired_source_fingerprint
            FROM graph_sync_jobs AS job
            JOIN episodes AS episode ON episode.id = job.episode_id
            WHERE job.episode_id = $1
            """,
            pending_id,
        )
        assert requeued["state"] == "pending"
        assert requeued["verified_at"] is None
        assert requeued["graphiti_synced"] is False
        assert requeued["desired_source_fingerprint"] == source_content_fingerprint(
            "Pending lore revised"
        )
    finally:
        await outer.rollback()
        await connection.close()
