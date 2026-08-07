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

from src.graphiti.rebuild import GraphRebuildRepository
from src.graphiti.sync_models import (
    CompletionStatus,
    FailureClass,
    FailureDisposition,
    FailureRecord,
    GraphCounts,
    GraphSyncPolicy,
    InvalidTransitionError,
    LeaseLostError,
    ProviderCallIntent,
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
    migration_paths = [
        MIGRATION_DIRECTORY / "0001_graph_sync_lifecycle.sql",
        MIGRATION_DIRECTORY / "0002_graph_sync_runtime.sql",
        MIGRATION_DIRECTORY / "0003_graph_sync_provider_call_intents.sql",
        MIGRATION_DIRECTORY / "0006_graph_rebuild_operations.sql",
    ]
    if [path.name for path in migration_paths] != [
        "0001_graph_sync_lifecycle.sql",
        "0002_graph_sync_runtime.sql",
        "0003_graph_sync_provider_call_intents.sql",
        "0006_graph_rebuild_operations.sql",
    ]:
        raise RuntimeError("Graph sync integration migrations are unavailable or unexpected")
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
        for migration_path in migration_paths:
            await admin.execute(migration_path.read_text(encoding="ascii"))
        table_count = await admin.fetchval(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = $1
              AND table_name IN (
                  'episodes',
                  'graph_sync_runs',
                  'graph_sync_jobs',
                  'graph_sync_attempts',
                  'graph_sync_attempt_results',
                  'graph_sync_provider_call_intents',
                  'graph_sync_provider_calls',
                  'graph_rebuild_operations',
                  'graph_sync_profile_state',
                  'graph_rebuild_events'
              )
            """,
            schema_name,
        )
        if table_count != 10:
            raise RuntimeError("Graph sync integration schema was not created in isolation")
    except Exception:
        await admin.execute("SET search_path TO public")
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        raise
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
        async with pool.acquire() as connection:
            current_schema = await connection.fetchval("SELECT current_schema()")
            episode_count = await connection.fetchval("SELECT count(*) FROM episodes")
            job_count = await connection.fetchval("SELECT count(*) FROM graph_sync_jobs")
        if current_schema != schema_name or episode_count != 3 or job_count != 3:
            raise RuntimeError("Graph sync integration pool escaped its isolated schema")
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
        native_uuid_count=1,
        source_fingerprint_count=1,
        sync_profile_fingerprint_count=1,
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
    assert await repository.profile_snapshot(SYNC_PROFILE) == {
        "matching_jobs": 3,
        "matching_eligible": 3,
        "matching_expired_leases": 0,
        "non_synced_other_profile": 0,
    }
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
            INSERT INTO graph_sync_provider_call_intents (
                attempt_id, call_number, logical_model_attempt, transport_attempt,
                provider, model, candidate_fingerprint, prompt_version,
                schema_version, started_at
            )
            VALUES (
                $1, 2, 2, 1, 'ollama', 'qwen2.5:3b', 'candidate:test',
                'prompt:v1', 'schema:v1', clock_timestamp()
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
            INSERT INTO graph_sync_provider_call_intents (
                attempt_id, call_number, logical_model_attempt, transport_attempt,
                provider, model, candidate_fingerprint, prompt_version,
                schema_version, started_at
            )
            VALUES (
                $1, 2, 2, 1, 'ollama', 'qwen2.5:3b', 'candidate:test',
                'prompt:v1', 'schema:v1', clock_timestamp()
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


async def test_reserved_provider_call_survives_worker_crash_without_false_completion(
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
            policy=GraphSyncPolicy(max_job_attempts=2, max_provider_calls=1),
        )
    )[0]
    call_started_at = datetime.now(UTC)
    ticket = await repository.reserve_provider_call(
        lease,
        ProviderCallIntent(
            logical_model_attempt=1,
            transport_attempt=1,
            provider="ollama",
            model="qwen2.5:3b",
            candidate_fingerprint="candidate:test",
            prompt_version="prompt:v1",
            schema_version="schema:v1",
            started_at=call_started_at,
        ),
    )
    assert ticket.call_number == 1
    await postgres.execute(
        """
        UPDATE graph_sync_jobs
        SET lease_expires_at = clock_timestamp() - interval '1 second'
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )

    recovered = await repository.recover_expired_leases()
    assert recovered[0]["state"] == "retry_wait"
    result_count = await postgres.fetchval(
        """
        SELECT provider_call_count
        FROM graph_sync_attempt_results
        WHERE attempt_id = $1
        """,
        lease.attempt_id,
    )
    assert result_count == 1

    chain = await repository.attempt_chain(lease.episode_id)
    assert chain[0]["provider_call_count"] == 1
    assert chain[0]["provider_calls"][0]["call_number"] == 1
    assert chain[0]["provider_calls"][0]["outcome"] is None


async def test_run_summary_reconstructs_progress_throughput_and_failures_from_ledger(
    state_store,
):
    _, repository, _ = state_store
    run = await repository.start_or_join_run(
        worker_id="worker-a", sync_profile_fingerprint=SYNC_PROFILE
    )
    policy = GraphSyncPolicy(max_job_attempts=3, max_provider_calls=1)

    successful_lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=policy,
        )
    )[0]
    await repository.record_provider_call(successful_lease, _provider_call())
    assert (
        await repository.complete_verified_success(
            successful_lease,
            _verification(successful_lease),
            graph_counts=GraphCounts(accepted_entities=2, accepted_edges=1),
        )
        is CompletionStatus.SYNCED
    )

    failed_lease = (
        await repository.claim_jobs(
            run_id=run.id,
            worker_id="worker-a",
            route_fingerprint="route:test",
            policy=policy,
        )
    )[0]
    failure = FailureRecord.build(
        failure_class=FailureClass.MALFORMED_JSON,
        code="malformed_json",
        summary="synthetic parse failure",
        disposition=FailureDisposition.RETRY,
    )
    assert await repository.complete_failure(failed_lease, failure) is CompletionStatus.RETRY_WAIT

    summary = await repository.run_summary(run.id)

    assert summary["status"] == "available"
    assert summary["run"]["id"] == run.id
    assert summary["progress"]["job_counts"] == {
        "pending": 1,
        "leased": 0,
        "retry_wait": 1,
        "quarantined": 0,
        "synced": 1,
    }
    assert summary["progress"]["completion_percent"] == pytest.approx(33.333)
    assert summary["progress"]["remaining_jobs"] == 2
    assert summary["progress"]["rolling_verified"] == 1
    assert summary["progress"]["rolling_verified_per_minute"] > 0
    assert summary["progress"]["eta_status"] in {"warming_up", "available"}
    assert summary["attempts"]["outcomes"]["primary_success"] == 1
    assert summary["attempts"]["outcomes"]["retry_wait"] == 1
    assert summary["attempts"]["failure_classes"]["malformed_json"] == 1
    assert summary["attempts"]["graph_counts"]["accepted_entities"] == 2
    assert summary["attempts"]["graph_counts"]["proposed_entities"] is None
    assert summary["attempts"]["graph_count_reported_attempts"]["accepted_entities"] == 1
    assert summary["attempts"]["graph_count_reported_attempts"]["proposed_entities"] == 0
    assert summary["provider_calls"]["reserved"] == 1
    assert summary["provider_calls"]["completed"] == 1
    assert summary["provider_calls"]["usage"]["total_tokens"] is None
    assert summary["provider_calls"]["usage_reported_calls"]["total_tokens"] == 0
    assert "Episode 0" not in repr(summary)

    status = await repository.status_snapshot()
    assert status["latest_run_summary"]["run"]["id"] == run.id


async def test_rebuild_preserves_attempts_fences_runs_and_activates_profiles(state_store):
    postgres, sync_repository, _ = state_store
    run = await sync_repository.start_or_join_run(
        worker_id="history-worker", sync_profile_fingerprint=SYNC_PROFILE
    )
    lease = (
        await sync_repository.claim_jobs(
            run_id=run.id,
            worker_id="history-worker",
            route_fingerprint="route:test",
            policy=GraphSyncPolicy(max_job_attempts=2),
        )
    )[0]
    failure = FailureRecord.build(
        failure_class=FailureClass.MALFORMED_JSON,
        code="malformed_json",
        summary="preserved attempt",
        disposition=FailureDisposition.RETRY,
    )
    assert await sync_repository.complete_failure(lease, failure) is CompletionStatus.RETRY_WAIT
    await sync_repository.drain_run(run.id)
    await sync_repository.stop_run(run.id)
    before = await postgres.fetchrow(
        """
        SELECT job_attempt_count, attempt_budget_count, retry_generation,
               last_attempt_id
        FROM graph_sync_jobs
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )
    attempt_count = await postgres.fetchval("SELECT count(*) FROM graph_sync_attempts")

    rebuild_repository = GraphRebuildRepository(postgres)
    prepared = await rebuild_repository.prepare(
        target_sync_profile_fingerprint="sync:rebuilt",
        target_embedding_profile_fingerprint="embedding:rebuilt",
        backup_reference="backups/integration",
        backup_created_at=datetime.now(UTC),
        pre_audit_fingerprint="graph-audit:sha256:" + "a" * 64,
        pre_postgres_episode_count=3,
        pre_neo4j_node_count=12,
        pre_neo4j_relationship_count=18,
    )

    assert prepared["state"] == "jobs_requeued"
    after = await postgres.fetchrow(
        """
        SELECT job_attempt_count, attempt_budget_count, retry_generation,
               last_attempt_id, state, sync_profile_fingerprint
        FROM graph_sync_jobs
        WHERE episode_id = $1
        """,
        lease.episode_id,
    )
    assert after["job_attempt_count"] == before["job_attempt_count"] == 1
    assert after["attempt_budget_count"] == 0
    assert after["retry_generation"] == before["retry_generation"] + 1
    assert after["last_attempt_id"] == before["last_attempt_id"]
    assert after["state"] == "pending"
    assert after["sync_profile_fingerprint"] == "sync:rebuilt"
    assert await postgres.fetchval("SELECT count(*) FROM graph_sync_attempts") == attempt_count

    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute("""
            INSERT INTO graph_sync_runs (worker_id, sync_profile_fingerprint)
            VALUES ('bypass-worker', 'sync:rebuilt')
            """)
    with pytest.raises(RunUnavailableError, match="clearing"):
        await sync_repository.start_or_join_run(
            worker_id="blocked-worker",
            sync_profile_fingerprint="sync:rebuilt",
        )

    ready = await rebuild_repository.mark_graph_cleared(
        prepared["id"],
        cleared_node_count=12,
        cleared_relationship_count=18,
        post_clear_audit_fingerprint="graph-audit:sha256:" + "b" * 64,
    )
    assert ready["state"] == "ready"
    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            """
            UPDATE graph_rebuild_operations
            SET run_count = run_count + 1
            WHERE id = $1
            """,
            prepared["id"],
        )

    new_episode_id = uuid4()
    await postgres.execute(
        """
        INSERT INTO episodes (
            id, text, document_id, episode_index,
            graphiti_synced, graphiti_synced_at
        )
        VALUES ($1, 'New during rebuild', $2, 99, TRUE, clock_timestamp())
        """,
        new_episode_id,
        uuid4(),
    )
    during_rebuild = await postgres.fetchrow(
        """
        SELECT job.sync_profile_fingerprint, job.state, episode.graphiti_synced
        FROM graph_sync_jobs AS job
        JOIN episodes AS episode ON episode.id = job.episode_id
        WHERE job.episode_id = $1
        """,
        new_episode_id,
    )
    assert dict(during_rebuild) == {
        "sync_profile_fingerprint": "sync:rebuilt",
        "state": "pending",
        "graphiti_synced": False,
    }

    rebuild_run = await sync_repository.start_or_join_run(
        worker_id="rebuild-worker",
        sync_profile_fingerprint="sync:rebuilt",
    )
    associated = await postgres.fetchval(
        "SELECT rebuild_operation_id FROM graph_sync_runs WHERE id = $1",
        rebuild_run.id,
    )
    assert associated == prepared["id"]
    await sync_repository.drain_run(rebuild_run.id)
    await sync_repository.stop_run(rebuild_run.id)
    assert (await rebuild_repository.active_operation())["state"] == "ready"

    await postgres.execute("""
        UPDATE graph_sync_jobs
        SET state = 'synced',
            verified_source_fingerprint = desired_source_fingerprint,
            verified_sync_profile_fingerprint = sync_profile_fingerprint,
            verified_at = clock_timestamp()
        """)
    final_run = await sync_repository.start_or_join_run(
        worker_id="final-worker",
        sync_profile_fingerprint="sync:rebuilt",
    )
    await sync_repository.drain_run(final_run.id)
    await sync_repository.stop_run(final_run.id)
    assert (await rebuild_repository.active_operation())["state"] == "awaiting_audit"

    completed = await rebuild_repository.finalize(
        prepared["id"],
        final_audit_fingerprint="graph-audit:sha256:" + "c" * 64,
        audited_episode_count=4,
    )
    assert completed["state"] == "completed"
    active_profile = await postgres.fetchrow("""
        SELECT sync_profile_fingerprint, embedding_profile_fingerprint,
               rebuild_operation_id
        FROM graph_sync_profile_state
        WHERE scope = 'graphiti'
        """)
    assert dict(active_profile) == {
        "sync_profile_fingerprint": "sync:rebuilt",
        "embedding_profile_fingerprint": "embedding:rebuilt",
        "rebuild_operation_id": prepared["id"],
    }
    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute("""
            UPDATE graph_sync_profile_state
            SET sync_profile_fingerprint = 'sync:forged'
            WHERE scope = 'graphiti'
            """)
    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            "DELETE FROM graph_rebuild_operations WHERE id = $1",
            prepared["id"],
        )
    event_types = await postgres.fetch(
        """
        SELECT event_type
        FROM graph_rebuild_events
        WHERE rebuild_operation_id = $1
        ORDER BY sequence
        """,
        prepared["id"],
    )
    assert [row["event_type"] for row in event_types] == [
        "jobs_requeued",
        "graph_cleared",
        "run_started",
        "run_stopped",
        "run_started",
        "run_stopped",
        "final_audit_passed",
    ]
    snapshot = await rebuild_repository.status_snapshot(prepared["id"])
    assert snapshot["event_count"] == 7
    assert snapshot["events_truncated"] is False
    assert snapshot["active_profile"]["rebuild_operation_id"] == prepared["id"]
    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            """
            UPDATE graph_rebuild_events
            SET event_type = 'run_stopped'
            WHERE rebuild_operation_id = $1 AND sequence = 1
            """,
            prepared["id"],
        )
    with pytest.raises(asyncpg.PostgresError):
        await postgres.execute(
            """
            INSERT INTO graph_rebuild_events (
                rebuild_operation_id, sequence, event_type,
                audit_fingerprint, job_count
            )
            VALUES ($1, 99, 'final_audit_passed', $2, 4)
            """,
            prepared["id"],
            "graph-audit:sha256:" + "d" * 64,
        )

    post_rebuild_episode = uuid4()
    await postgres.execute(
        """
        INSERT INTO episodes (
            id, text, document_id, episode_index,
            graphiti_synced, graphiti_synced_at
        )
        VALUES ($1, 'New after rebuild', $2, 100, TRUE, clock_timestamp())
        """,
        post_rebuild_episode,
        uuid4(),
    )
    after_rebuild = await postgres.fetchrow(
        """
        SELECT job.sync_profile_fingerprint, job.state, episode.graphiti_synced
        FROM graph_sync_jobs AS job
        JOIN episodes AS episode ON episode.id = job.episode_id
        WHERE job.episode_id = $1
        """,
        post_rebuild_episode,
    )
    assert dict(after_rebuild) == {
        "sync_profile_fingerprint": "sync:rebuilt",
        "state": "pending",
        "graphiti_synced": False,
    }
