"""Isolated PostgreSQL tests for durable Graphiti runtime transitions."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from src.graphiti.sync_models import (
    CompletionStatus,
    FailureClass,
    FailureDisposition,
    FailureRecord,
    GraphSyncPolicy,
    InvalidTransitionError,
    LeaseLostError,
    ProviderCallOutcome,
    ProviderCallRecord,
    RunUnavailableError,
    StableIdVerification,
)
from src.graphiti.sync_state import GraphSyncRepository

pytestmark = pytest.mark.integration
MIGRATION_DIRECTORY = Path(__file__).resolve().parents[1] / "schemas" / "migrations"
SYNC_PROFILE = "legacy:unversioned"


class SchemaPostgres:
    """Minimal PostgresDB-compatible pool pinned to one isolated schema."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        async with self.pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        async with self.acquire() as connection:
            return await connection.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.acquire() as connection:
            return await connection.fetchval(query, *args)


@pytest.fixture
async def state_store() -> (
    AsyncGenerator[tuple[SchemaPostgres, GraphSyncRepository, list[UUID]], None]
):
    connect_args = {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "database": os.environ["POSTGRES_DB"],
    }
    schema_name = f"graph_sync_runtime_{uuid4().hex}"
    admin = await asyncpg.connect(**connect_args)
    episode_ids = [uuid4(), uuid4(), uuid4()]
    try:
        await admin.execute(f'CREATE SCHEMA "{schema_name}"')
        await admin.execute(f'SET search_path TO "{schema_name}", public')
        await admin.execute("""
            CREATE TABLE episodes (
                id UUID PRIMARY KEY,
                text TEXT NOT NULL,
                document_id UUID NOT NULL,
                episode_index INTEGER NOT NULL,
                graphiti_synced BOOLEAN NOT NULL DEFAULT FALSE,
                graphiti_synced_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
            )
            """)
        await admin.executemany(
            """
            INSERT INTO episodes (id, text, document_id, episode_index)
            VALUES ($1, $2, $3, $4)
            """,
            [
                (episode_id, f"Episode {index}", uuid4(), index)
                for index, episode_id in enumerate(episode_ids)
            ],
        )
        for migration_path in sorted(MIGRATION_DIRECTORY.glob("*.sql")):
            await admin.execute(migration_path.read_text(encoding="ascii"))
    finally:
        await admin.close()

    pool = await asyncpg.create_pool(
        **connect_args,
        min_size=1,
        max_size=6,
        server_settings={"search_path": f'"{schema_name}", public'},
    )
    postgres = SchemaPostgres(pool)
    try:
        yield postgres, GraphSyncRepository(postgres), episode_ids
    finally:
        await pool.close()
        cleanup = await asyncpg.connect(**connect_args)
        try:
            await cleanup.execute(f'DROP SCHEMA "{schema_name}" CASCADE')
        finally:
            await cleanup.close()


def _verification(lease) -> StableIdVerification:
    return StableIdVerification(
        stable_id=str(lease.episode_id),
        candidate_count=1,
        stable_id_count=1,
        source_description_count=1,
        exact_count=1,
        source_fingerprint=lease.captured_source_fingerprint,
        sync_profile_fingerprint=lease.sync_profile_fingerprint,
    )


def _provider_call() -> ProviderCallRecord:
    now = datetime.now(UTC)
    return ProviderCallRecord(
        logical_model_attempt=1,
        transport_attempt=1,
        provider="ollama",
        model="qwen2.5:3b",
        candidate_fingerprint="candidate:test",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        started_at=now,
        completed_at=now,
        latency_ms=0,
        outcome=ProviderCallOutcome.SUCCESS,
    )


async def test_two_workers_claim_distinct_jobs_and_verified_success_projects(
    state_store,
):
    postgres, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    policy = GraphSyncPolicy(max_job_attempts=2, max_provider_calls=1)

    first, second = await asyncio.gather(
        repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=policy,
        ),
        repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-b",
            route_fingerprint="route:test",
            policy=policy,
        ),
    )

    leases = [first[0], second[0]]
    assert len({lease.episode_id for lease in leases}) == 2
    assert all(lease.attempt_number == 1 for lease in leases)

    assert await repository.record_provider_call(leases[0], _provider_call()) == 1
    with pytest.raises(InvalidTransitionError, match="limit"):
        await repository.record_provider_call(leases[0], _provider_call())

    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            """
            INSERT INTO graph_sync_provider_calls (
                attempt_id, call_number, logical_model_attempt, transport_attempt,
                provider, model, candidate_fingerprint, prompt_version,
                schema_version, started_at, completed_at, latency_ms, outcome
            )
            VALUES (
                $1, 2, 2, 1, 'ollama', 'qwen2.5:3b', 'candidate:test',
                'prompt:v1', 'schema:v1', clock_timestamp(), clock_timestamp(),
                0, 'success'
            )
            """,
            leases[0].attempt_id,
        )

    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            """
            INSERT INTO graph_sync_attempt_results (
                attempt_id, outcome, provider_call_count,
                failure_class, failure_code, failure_summary
            )
            VALUES (
                $1, 'retry_wait', 1, 'malformed_json', 'malformed_json',
                'Incorrect direct ledger count'
            )
            """,
            leases[1].attempt_id,
        )

    assert (
        await repository.complete_verified_success(leases[0], _verification(leases[0]))
        is CompletionStatus.SYNCED
    )
    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            """
            INSERT INTO graph_sync_provider_calls (
                attempt_id, call_number, logical_model_attempt, transport_attempt,
                provider, model, candidate_fingerprint, prompt_version,
                schema_version, started_at, completed_at, latency_ms, outcome
            )
            VALUES (
                $1, 2, 2, 1, 'ollama', 'qwen2.5:3b', 'candidate:test',
                'prompt:v1', 'schema:v1', clock_timestamp(), clock_timestamp(),
                0, 'success'
            )
            """,
            leases[0].attempt_id,
        )
    failure = FailureRecord.build(
        failure_class=FailureClass.MALFORMED_JSON,
        code="malformed_json",
        summary="unterminated response",
        disposition=FailureDisposition.RETRY,
    )
    assert await repository.complete_failure(leases[1], failure) is CompletionStatus.RETRY_WAIT

    projected = await postgres.fetchrow("""
        SELECT count(*) FILTER (WHERE graphiti_synced) AS synced,
               count(*) FILTER (WHERE NOT graphiti_synced) AS pending
        FROM episodes
        """)
    assert dict(projected) == {"synced": 1, "pending": 2}


async def test_expired_lease_quarantines_then_explicit_retry_resets_only_budget(
    state_store,
):
    postgres, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(max_job_attempts=1),
        )
    )[0]
    await postgres.execute(
        """
        UPDATE graph_sync_jobs
        SET lease_expires_at = clock_timestamp() - interval '1 second'
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )

    recovered = await repository.recover_expired_leases()
    assert recovered == [
        {
            "episode_id": str(lease.episode_id),
            "attempt_id": str(lease.attempt_id),
            "state": "quarantined",
        }
    ]
    assert await repository.retry_quarantined([lease.episode_id]) == 1

    row = await postgres.fetchrow(
        """
        SELECT state, job_attempt_count, attempt_budget_count, retry_generation
        FROM graph_sync_jobs
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )
    assert dict(row) == {
        "state": "pending",
        "job_attempt_count": 1,
        "attempt_budget_count": 0,
        "retry_generation": 1,
    }
    retried = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-b",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(max_job_attempts=1),
        )
    )[0]
    assert retried.attempt_number == 2
    assert retried.budget_attempt_number == 1
    assert retried.retry_generation == 1


async def test_source_edit_during_lease_records_attempt_and_keeps_new_revision_pending(
    state_store,
):
    postgres, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(),
        )
    )[0]
    await postgres.execute(
        "UPDATE episodes SET text = text || ' revised' WHERE id = $1",
        lease.episode_id,
    )

    status = await repository.complete_verified_success(lease, _verification(lease))
    assert status is CompletionStatus.SOURCE_CHANGED
    row = await postgres.fetchrow(
        """
        SELECT job.state,
               job.attempt_budget_count,
               job.retry_generation,
               episode.graphiti_synced,
               result.failure_code
        FROM graph_sync_jobs AS job
        JOIN episodes AS episode ON episode.id = job.episode_id
        JOIN graph_sync_attempt_results AS result
          ON result.attempt_id = job.last_attempt_id
        WHERE job.episode_id = $1
        """,
        lease.episode_id,
    )
    assert dict(row) == {
        "state": "pending",
        "attempt_budget_count": 0,
        "retry_generation": 1,
        "graphiti_synced": False,
        "failure_code": "source_changed",
    }


async def test_systemic_failure_pauses_claims_until_readiness_verified(state_store):
    postgres, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(),
        )
    )[0]
    failure = FailureRecord.build(
        failure_class=FailureClass.AUTHENTICATION,
        code="provider_authentication",
        summary="Authorization: Bearer not-a-real-secret-token",
        disposition=FailureDisposition.PAUSE_SYSTEMIC,
    )

    assert await repository.complete_failure(lease, failure) is CompletionStatus.PAUSED_SYSTEMIC
    attempt_counts = await postgres.fetchrow(
        """
        SELECT job_attempt_count, attempt_budget_count
        FROM graph_sync_jobs
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )
    assert dict(attempt_counts) == {
        "job_attempt_count": 1,
        "attempt_budget_count": 0,
    }
    with pytest.raises(RunUnavailableError):
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-b",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(),
        )
    with pytest.raises(InvalidTransitionError, match="readiness"):
        await repository.resume_run(run.id, readiness_verified=False)
    resumed = await repository.resume_run(run.id, readiness_verified=True)
    assert resumed.state.value == "running"


async def test_operator_attempt_chain_is_sanitized_and_contains_no_source_text(state_store):
    _, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(),
        )
    )[0]
    secret = "sk_test_abcdefghijklmnopqrstuvwxyz"
    failure = FailureRecord.build(
        failure_class=FailureClass.CONFIGURATION,
        code="invalid_configuration",
        summary=f"api_key={secret}",
        disposition=FailureDisposition.QUARANTINE,
    )
    await repository.complete_failure(lease, failure)

    chain = await repository.attempt_chain(lease.episode_id)
    rendered = repr(chain)
    assert secret not in rendered
    assert "<redacted>" in rendered
    assert lease.text not in rendered


async def test_expired_lease_rejects_heartbeat_and_fences_worker_failure(state_store):
    postgres, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(max_job_attempts=2),
        )
    )[0]
    await postgres.execute(
        """
        UPDATE graph_sync_jobs
        SET lease_expires_at = clock_timestamp() - interval '1 second'
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )

    with pytest.raises(LeaseLostError, match="expired"):
        await repository.heartbeat_lease(lease, lease_seconds=60)

    arbitrary_failure = FailureRecord.build(
        failure_class=FailureClass.GRAPH_VALIDATION,
        code="graph_validation",
        summary="This stale worker no longer owns the lease",
        disposition=FailureDisposition.QUARANTINE,
    )
    assert (
        await repository.complete_failure(lease, arbitrary_failure) is CompletionStatus.RETRY_WAIT
    )
    row = await postgres.fetchrow(
        """
        SELECT state, last_error_code
        FROM graph_sync_jobs
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )
    assert dict(row) == {"state": "retry_wait", "last_error_code": "lease_expired"}


async def test_retry_waiting_selection_is_atomic_and_state_filters_are_validated(
    state_store,
):
    postgres, repository, episode_ids = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(),
        )
    )[0]
    failure = FailureRecord.build(
        failure_class=FailureClass.MALFORMED_JSON,
        code="malformed_json",
        summary="retryable output",
        disposition=FailureDisposition.RETRY,
    )
    await repository.complete_failure(lease, failure)
    pending_id = next(episode_id for episode_id in episode_ids if episode_id != lease.episode_id)

    with pytest.raises(InvalidTransitionError, match="Every selected"):
        await repository.retry_waiting([lease.episode_id, pending_id])

    states = await postgres.fetch(
        """
        SELECT episode_id, state
        FROM graph_sync_jobs
        WHERE episode_id = ANY($1::uuid[])
        """,
        [lease.episode_id, pending_id],
    )
    assert {row["episode_id"]: row["state"] for row in states} == {
        lease.episode_id: "retry_wait",
        pending_id: "pending",
    }
    with pytest.raises(ValueError, match="Unknown"):
        await repository.list_jobs(states=["not-a-state"])
