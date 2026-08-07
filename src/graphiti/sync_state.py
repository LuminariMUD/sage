"""Transactional repository for durable PostgreSQL Graphiti sync state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from src.db.postgres import PostgresDB
from src.graphiti.relationship_policy import RelationshipQualityReport
from src.graphiti.sync_models import (
    AttemptOutcome,
    CompletionStatus,
    FailureClass,
    FailureDisposition,
    FailureRecord,
    GraphCounts,
    GraphSyncPolicy,
    InvalidTransitionError,
    JobLease,
    JobState,
    LeaseLostError,
    ProviderCallIntent,
    ProviderCallLimitExceeded,
    ProviderCallOutcome,
    ProviderCallRecord,
    ProviderCallTicket,
    RunRecord,
    RunState,
    RunUnavailableError,
    StableIdVerification,
    deterministic_retry_delay,
    sanitize_summary,
    validate_failure_code,
    validate_label,
)
from src.graphiti.sync_progress import derive_run_progress

RUN_START_LOCK_ID = 731047850174
MAX_CLAIM_BATCH = 100
MAX_OPERATOR_BATCH = 500
DEFAULT_PROGRESS_WINDOW_SECONDS = 300
MIN_PROGRESS_WINDOW_SECONDS = 60
MAX_PROGRESS_WINDOW_SECONDS = 86_400


def _percentage(numerator: int, denominator: int) -> float | None:
    """Return a stable percentage while preserving an unavailable denominator."""
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 3)


class GraphSyncRepository:
    """Own atomic run, lease, attempt, and operator state transitions."""

    def __init__(self, postgres: PostgresDB):
        self.postgres = postgres

    @staticmethod
    def _run_record(row: Mapping[str, Any]) -> RunRecord:
        return RunRecord(
            id=row["id"],
            state=RunState(row["state"]),
            worker_id=row["worker_id"],
            sync_profile_fingerprint=row["sync_profile_fingerprint"],
            started_at=row["started_at"],
            heartbeat_at=row["heartbeat_at"],
        )

    async def profile_snapshot(self, sync_profile_fingerprint: str) -> dict[str, int]:
        """Return profile compatibility counts without claiming or changing jobs."""
        fingerprint = validate_label(sync_profile_fingerprint, "Sync profile fingerprint")
        row = await self.postgres.fetchrow(
            """
            SELECT count(*) FILTER (
                       WHERE sync_profile_fingerprint = $1
                   ) AS matching_jobs,
                   count(*) FILTER (
                       WHERE sync_profile_fingerprint = $1
                         AND (
                             state = 'pending'
                             OR (
                                 state = 'retry_wait'
                                 AND next_attempt_at <= clock_timestamp()
                             )
                         )
                   ) AS matching_eligible,
                   count(*) FILTER (
                       WHERE sync_profile_fingerprint = $1
                         AND state = 'leased'
                         AND lease_expires_at <= clock_timestamp()
                   ) AS matching_expired_leases,
                   count(*) FILTER (
                       WHERE sync_profile_fingerprint <> $1
                         AND state <> 'synced'
                   ) AS non_synced_other_profile
            FROM graph_sync_jobs
            """,
            fingerprint,
        )
        return {key: int(row[key]) for key in row.keys()}

    async def start_or_join_run(
        self, *, worker_id: str, sync_profile_fingerprint: str
    ) -> RunRecord:
        """Start one run or join the active compatible run under a DB lock."""
        worker_id = validate_label(worker_id, "Worker ID")
        sync_profile_fingerprint = validate_label(
            sync_profile_fingerprint, "Sync profile fingerprint"
        )

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", RUN_START_LOCK_ID)
                active = await connection.fetchrow("""
                    SELECT id, state, worker_id, sync_profile_fingerprint,
                           rebuild_operation_id, started_at, heartbeat_at
                    FROM graph_sync_runs
                    WHERE state <> 'stopped'
                    ORDER BY started_at
                    LIMIT 1
                    FOR UPDATE
                    """)
                if active is not None:
                    if active["sync_profile_fingerprint"] != sync_profile_fingerprint:
                        raise RunUnavailableError("Active run uses a different sync profile")
                    if active["state"] != RunState.RUNNING.value:
                        raise RunUnavailableError("Active run is not accepting claims")
                    refreshed = await connection.fetchrow(
                        """
                        UPDATE graph_sync_runs
                        SET heartbeat_at = clock_timestamp()
                        WHERE id = $1
                        RETURNING id, state, worker_id, sync_profile_fingerprint,
                                  started_at, heartbeat_at
                        """,
                        active["id"],
                    )
                    return self._run_record(refreshed)

                rebuild = await connection.fetchrow("""
                    SELECT id, state, target_sync_profile_fingerprint
                    FROM graph_rebuild_operations
                    WHERE state <> 'completed'
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE
                    """)
                rebuild_operation_id = None
                if rebuild is not None:
                    if rebuild["target_sync_profile_fingerprint"] != sync_profile_fingerprint:
                        raise RunUnavailableError("Active rebuild uses a different sync profile")
                    if rebuild["state"] == "jobs_requeued":
                        raise RunUnavailableError("Active rebuild has not completed graph clearing")
                    if rebuild["state"] == "running":
                        raise RunUnavailableError("Active rebuild run state is inconsistent")
                    if rebuild["state"] == "awaiting_audit":
                        remaining = await connection.fetchval(
                            """
                            SELECT count(*)
                            FROM graph_sync_jobs
                            WHERE state <> 'synced'
                               OR sync_profile_fingerprint <> $1
                            """,
                            sync_profile_fingerprint,
                        )
                        if not remaining:
                            raise RunUnavailableError("Active rebuild is awaiting its final audit")
                    await connection.execute(
                        """
                        UPDATE graph_rebuild_operations
                        SET state = 'running', run_count = run_count + 1
                        WHERE id = $1
                        """,
                        rebuild["id"],
                    )
                    rebuild_operation_id = rebuild["id"]

                created = await connection.fetchrow(
                    """
                    INSERT INTO graph_sync_runs (
                        worker_id, sync_profile_fingerprint,
                        rebuild_operation_id, heartbeat_at
                    )
                    VALUES ($1, $2, $3, clock_timestamp())
                    RETURNING id, state, worker_id, sync_profile_fingerprint,
                              started_at, heartbeat_at
                    """,
                    worker_id,
                    sync_profile_fingerprint,
                    rebuild_operation_id,
                )
                if rebuild_operation_id is not None:
                    next_sequence = await connection.fetchval(
                        """
                        SELECT COALESCE(max(sequence), 0) + 1
                        FROM graph_rebuild_events
                        WHERE rebuild_operation_id = $1
                        """,
                        rebuild_operation_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO graph_rebuild_events (
                            rebuild_operation_id, sequence, event_type, run_id
                        )
                        VALUES ($1, $2, 'run_started', $3)
                        """,
                        rebuild_operation_id,
                        next_sequence,
                        created["id"],
                    )
                return self._run_record(created)

    async def heartbeat_run(self, run_id: UUID) -> datetime:
        """Advance an active run heartbeat using database time."""
        heartbeat = await self.postgres.fetchval(
            """
            UPDATE graph_sync_runs
            SET heartbeat_at = clock_timestamp()
            WHERE id = $1 AND state = 'running'
            RETURNING heartbeat_at
            """,
            run_id,
        )
        if heartbeat is None:
            raise RunUnavailableError("Run is not accepting heartbeats")
        return heartbeat

    async def resume_run(self, run_id: UUID, *, readiness_verified: bool) -> RunRecord:
        """Resume a paused or draining run only after an external readiness proof."""
        if not readiness_verified:
            raise InvalidTransitionError("Run resume requires a successful readiness check")
        row = await self.postgres.fetchrow(
            """
            UPDATE graph_sync_runs
            SET state = 'running',
                heartbeat_at = clock_timestamp(),
                last_failure_class = NULL,
                last_failure_code = NULL,
                last_failure_summary = NULL
            WHERE id = $1 AND state IN ('paused_systemic', 'draining')
            RETURNING id, state, worker_id, sync_profile_fingerprint,
                      started_at, heartbeat_at
            """,
            run_id,
        )
        if row is None:
            raise InvalidTransitionError("Run cannot be resumed from its current state")
        return self._run_record(row)

    async def drain_run(self, run_id: UUID) -> RunRecord:
        """Stop new claims while allowing current leases to finish."""
        row = await self.postgres.fetchrow(
            """
            UPDATE graph_sync_runs
            SET state = 'draining', heartbeat_at = clock_timestamp()
            WHERE id = $1 AND state = 'running'
            RETURNING id, state, worker_id, sync_profile_fingerprint,
                      started_at, heartbeat_at
            """,
            run_id,
        )
        if row is None:
            raise InvalidTransitionError("Run cannot enter draining state")
        return self._run_record(row)

    async def stop_run(self, run_id: UUID) -> RunRecord:
        """Stop a run only when no job from that run still has an active lease."""
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", RUN_START_LOCK_ID)
                row = await connection.fetchrow(
                    """
                    SELECT id, state, rebuild_operation_id
                    FROM graph_sync_runs
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    run_id,
                )
                if row is None or row["state"] == RunState.STOPPED.value:
                    raise InvalidTransitionError("Run is missing or already stopped")
                active_leases = await connection.fetchval(
                    """
                    SELECT count(*)
                    FROM graph_sync_jobs AS job
                    JOIN graph_sync_attempts AS attempt
                      ON attempt.id = job.last_attempt_id
                    WHERE attempt.run_id = $1 AND job.state = 'leased'
                    """,
                    run_id,
                )
                if active_leases:
                    raise InvalidTransitionError("Run still owns active leases")
                stopped = await connection.fetchrow(
                    """
                    UPDATE graph_sync_runs
                    SET state = 'stopped',
                        stopped_at = clock_timestamp(),
                        heartbeat_at = clock_timestamp()
                    WHERE id = $1
                    RETURNING id, state, worker_id, sync_profile_fingerprint,
                              started_at, heartbeat_at
                    """,
                    run_id,
                )
                rebuild_operation_id = row["rebuild_operation_id"]
                if rebuild_operation_id is not None:
                    rebuild = await connection.fetchrow(
                        """
                        SELECT id, state, target_sync_profile_fingerprint
                        FROM graph_rebuild_operations
                        WHERE id = $1
                        FOR UPDATE
                        """,
                        rebuild_operation_id,
                    )
                    if rebuild is None or rebuild["state"] != "running":
                        raise InvalidTransitionError("Associated graph rebuild is not running")
                    remaining = await connection.fetchval(
                        """
                        SELECT count(*)
                        FROM graph_sync_jobs
                        WHERE state <> 'synced'
                           OR sync_profile_fingerprint <> $1
                        """,
                        rebuild["target_sync_profile_fingerprint"],
                    )
                    next_state = "ready" if remaining else "awaiting_audit"
                    await connection.execute(
                        """
                        UPDATE graph_rebuild_operations
                        SET state = $2
                        WHERE id = $1
                        """,
                        rebuild_operation_id,
                        next_state,
                    )
                    next_sequence = await connection.fetchval(
                        """
                        SELECT COALESCE(max(sequence), 0) + 1
                        FROM graph_rebuild_events
                        WHERE rebuild_operation_id = $1
                        """,
                        rebuild_operation_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO graph_rebuild_events (
                            rebuild_operation_id, sequence, event_type,
                            run_id, job_count
                        )
                        VALUES ($1, $2, 'run_stopped', $3, $4)
                        """,
                        rebuild_operation_id,
                        next_sequence,
                        run_id,
                        int(remaining),
                    )
                return self._run_record(stopped)

    async def claim_jobs(
        self,
        *,
        run_id: UUID,
        worker_id: str,
        route_fingerprint: str,
        policy: GraphSyncPolicy,
        limit: int = 1,
    ) -> list[JobLease]:
        """Atomically claim eligible jobs with row locks and database-time leases."""
        worker_id = validate_label(worker_id, "Worker ID")
        route_fingerprint = validate_label(route_fingerprint, "Route fingerprint")
        if not 1 <= limit <= MAX_CLAIM_BATCH:
            raise ValueError(f"Claim limit must be between 1 and {MAX_CLAIM_BATCH}")

        leases: list[JobLease] = []
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                run = await connection.fetchrow(
                    """
                    SELECT id, state, sync_profile_fingerprint
                    FROM graph_sync_runs
                    WHERE id = $1
                    FOR KEY SHARE
                    """,
                    run_id,
                )
                if run is None or run["state"] != RunState.RUNNING.value:
                    raise RunUnavailableError("Run is not accepting claims")

                candidates = await connection.fetch(
                    """
                    SELECT job.episode_id,
                           job.desired_source_fingerprint,
                           job.job_attempt_count,
                           job.attempt_budget_count,
                           job.retry_generation,
                           job.sync_profile_fingerprint,
                           episode.text,
                           episode.document_id,
                           episode.episode_index,
                           episode.created_at,
                           graph_sync_source_fingerprint(episode.text)
                               AS current_source_fingerprint
                    FROM graph_sync_jobs AS job
                    JOIN episodes AS episode ON episode.id = job.episode_id
                    WHERE job.sync_profile_fingerprint = $1
                      AND job.attempt_budget_count < $2
                      AND (
                          job.state = 'pending'
                          OR (
                              job.state = 'retry_wait'
                              AND job.next_attempt_at <= clock_timestamp()
                          )
                      )
                    ORDER BY
                        CASE WHEN job.state = 'pending' THEN 0 ELSE 1 END,
                        COALESCE(job.next_attempt_at, episode.created_at),
                        episode.created_at,
                        job.episode_id
                    FOR UPDATE OF job SKIP LOCKED
                    LIMIT $3
                    """,
                    run["sync_profile_fingerprint"],
                    policy.max_job_attempts,
                    limit,
                )

                for candidate in candidates:
                    if (
                        candidate["desired_source_fingerprint"]
                        != candidate["current_source_fingerprint"]
                    ):
                        raise InvalidTransitionError("Job source fingerprint is stale")

                    attempt_id = uuid4()
                    lease_token = uuid4()
                    attempt_number = candidate["job_attempt_count"] + 1
                    budget_attempt_number = candidate["attempt_budget_count"] + 1
                    retry_delay = deterministic_retry_delay(
                        candidate["episode_id"],
                        budget_attempt_number,
                        base_seconds=policy.retry_base_seconds,
                        maximum_seconds=policy.retry_max_seconds,
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
                            route_fingerprint,
                            retry_generation,
                            budget_attempt_number,
                            job_attempt_limit,
                            provider_call_limit,
                            retry_delay_seconds
                        )
                        VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9,
                            $10, $11, $12, $13, $14
                        )
                        """,
                        attempt_id,
                        candidate["episode_id"],
                        run_id,
                        attempt_number,
                        lease_token,
                        worker_id,
                        candidate["desired_source_fingerprint"],
                        candidate["sync_profile_fingerprint"],
                        route_fingerprint,
                        candidate["retry_generation"],
                        budget_attempt_number,
                        policy.max_job_attempts,
                        policy.max_provider_calls,
                        retry_delay,
                    )
                    updated = await connection.fetchrow(
                        """
                        UPDATE graph_sync_jobs
                        SET state = 'leased',
                            job_attempt_count = $2,
                            attempt_budget_count = $3,
                            next_attempt_at = NULL,
                            lease_owner = $4,
                            lease_token = $5,
                            lease_expires_at = clock_timestamp()
                                + ($6::double precision * interval '1 second'),
                            last_attempt_id = $7
                        WHERE episode_id = $1
                        RETURNING lease_expires_at
                        """,
                        candidate["episode_id"],
                        attempt_number,
                        budget_attempt_number,
                        worker_id,
                        lease_token,
                        policy.lease_seconds,
                        attempt_id,
                    )
                    leases.append(
                        JobLease(
                            episode_id=candidate["episode_id"],
                            attempt_id=attempt_id,
                            run_id=run_id,
                            lease_token=lease_token,
                            lease_owner=worker_id,
                            attempt_number=attempt_number,
                            budget_attempt_number=budget_attempt_number,
                            retry_generation=candidate["retry_generation"],
                            job_attempt_limit=policy.max_job_attempts,
                            provider_call_limit=policy.max_provider_calls,
                            retry_delay_seconds=retry_delay,
                            captured_source_fingerprint=candidate["desired_source_fingerprint"],
                            sync_profile_fingerprint=candidate["sync_profile_fingerprint"],
                            route_fingerprint=route_fingerprint,
                            lease_expires_at=updated["lease_expires_at"],
                            text=candidate["text"],
                            document_id=candidate["document_id"],
                            episode_index=candidate["episode_index"],
                            created_at=candidate["created_at"],
                        )
                    )

                await connection.execute(
                    """
                    UPDATE graph_sync_runs
                    SET heartbeat_at = clock_timestamp()
                    WHERE id = $1
                    """,
                    run_id,
                )
        return leases

    async def heartbeat_lease(self, lease: JobLease, *, lease_seconds: int) -> datetime:
        """Extend only a currently valid, token-fenced lease using database time."""
        if not 30 <= lease_seconds <= 86_400:
            raise ValueError("Lease seconds must be between 30 and 86400")
        expires_at = await self.postgres.fetchval(
            """
            UPDATE graph_sync_jobs
            SET lease_expires_at = clock_timestamp()
                + ($5::double precision * interval '1 second')
            WHERE episode_id = $1
              AND state = 'leased'
              AND last_attempt_id = $2
              AND lease_token = $3
              AND lease_owner = $4
              AND lease_expires_at > clock_timestamp()
            RETURNING lease_expires_at
            """,
            lease.episode_id,
            lease.attempt_id,
            lease.lease_token,
            lease.lease_owner,
            lease_seconds,
        )
        if expires_at is None:
            raise LeaseLostError("Lease is expired or no longer owned by this worker")
        return expires_at

    async def reserve_provider_call(
        self, lease: JobLease, intent: ProviderCallIntent
    ) -> ProviderCallTicket:
        """Commit a budgeted request intent before any provider network I/O."""
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                job = await connection.fetchrow(
                    """
                    SELECT state,
                           last_attempt_id,
                           lease_token,
                           lease_owner,
                           lease_expires_at > clock_timestamp() AS lease_is_valid
                    FROM graph_sync_jobs
                    WHERE episode_id = $1
                    FOR UPDATE
                    """,
                    lease.episode_id,
                )
                if (
                    job is None
                    or job["state"] != "leased"
                    or job["last_attempt_id"] != lease.attempt_id
                    or job["lease_token"] != lease.lease_token
                    or job["lease_owner"] != lease.lease_owner
                    or not job["lease_is_valid"]
                ):
                    raise LeaseLostError("Provider call requires a current valid lease")

                attempt = await connection.fetchrow(
                    """
                    SELECT attempt.lease_token,
                           attempt.lease_owner,
                           attempt.provider_call_limit,
                           result.attempt_id IS NOT NULL AS completed
                    FROM graph_sync_attempts AS attempt
                    LEFT JOIN graph_sync_attempt_results AS result
                      ON result.attempt_id = attempt.id
                    WHERE attempt.id = $1
                    FOR UPDATE OF attempt
                    """,
                    lease.attempt_id,
                )
                if (
                    attempt is None
                    or attempt["lease_token"] != lease.lease_token
                    or attempt["lease_owner"] != lease.lease_owner
                ):
                    raise LeaseLostError("Attempt identity does not match the lease")
                if attempt["completed"]:
                    raise InvalidTransitionError("Attempt already has a terminal result")
                if attempt["provider_call_limit"] != lease.provider_call_limit:
                    raise InvalidTransitionError("Lease provider-call policy does not match")

                call_number = await connection.fetchval(
                    """
                    SELECT COALESCE(max(call_number), 0) + 1
                    FROM graph_sync_provider_call_intents
                    WHERE attempt_id = $1
                    """,
                    lease.attempt_id,
                )
                if call_number > attempt["provider_call_limit"]:
                    raise ProviderCallLimitExceeded("Provider call limit is exhausted")

                await connection.execute(
                    """
                    INSERT INTO graph_sync_provider_call_intents (
                        attempt_id,
                        call_number,
                        logical_model_attempt,
                        transport_attempt,
                        provider,
                        model,
                        model_revision,
                        candidate_fingerprint,
                        prompt_version,
                        schema_version,
                        started_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    lease.attempt_id,
                    call_number,
                    intent.logical_model_attempt,
                    intent.transport_attempt,
                    intent.provider,
                    intent.model,
                    intent.model_revision,
                    intent.candidate_fingerprint,
                    intent.prompt_version,
                    intent.schema_version,
                    intent.started_at,
                )
                return ProviderCallTicket(
                    attempt_id=lease.attempt_id,
                    call_number=call_number,
                    intent=intent,
                )

    async def complete_provider_call(
        self,
        lease: JobLease,
        ticket: ProviderCallTicket,
        provider_call: ProviderCallRecord,
    ) -> int:
        """Append a sanitized completion for one durably reserved request."""
        if ticket.attempt_id != lease.attempt_id:
            raise InvalidTransitionError("Provider call ticket targets another attempt")
        intent = ticket.intent
        identity_fields = (
            "logical_model_attempt",
            "transport_attempt",
            "provider",
            "model",
            "model_revision",
            "candidate_fingerprint",
            "prompt_version",
            "schema_version",
            "started_at",
        )
        if any(
            getattr(provider_call, field) != getattr(intent, field) for field in identity_fields
        ):
            raise InvalidTransitionError("Provider call completion identity changed")

        optional_labels = (
            (provider_call.model_revision, "Model revision"),
            (provider_call.actual_model, "Actual model"),
            (provider_call.actual_upstream_provider, "Actual upstream provider"),
        )
        for value, label in optional_labels:
            if value is not None:
                validate_label(value, label)

        failure_code = provider_call.failure_code
        failure_summary = provider_call.failure_summary
        if failure_code is not None:
            failure_code = validate_failure_code(failure_code)

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                attempt = await connection.fetchrow(
                    """
                    SELECT attempt.id,
                           attempt.lease_token,
                           attempt.lease_owner,
                           result.attempt_id IS NOT NULL AS completed
                    FROM graph_sync_attempts AS attempt
                    LEFT JOIN graph_sync_attempt_results AS result
                      ON result.attempt_id = attempt.id
                    WHERE attempt.id = $1
                    FOR UPDATE OF attempt
                    """,
                    lease.attempt_id,
                )
                if (
                    attempt is None
                    or attempt["lease_token"] != lease.lease_token
                    or attempt["lease_owner"] != lease.lease_owner
                ):
                    raise LeaseLostError("Attempt identity does not match the lease")
                if attempt["completed"]:
                    raise InvalidTransitionError("Attempt already has a terminal result")
                already_completed = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM graph_sync_provider_calls
                        WHERE attempt_id = $1 AND call_number = $2
                    )
                    """,
                    lease.attempt_id,
                    ticket.call_number,
                )
                if already_completed:
                    raise InvalidTransitionError("Provider call already completed")

                await connection.execute(
                    """
                    INSERT INTO graph_sync_provider_calls (
                        attempt_id,
                        call_number,
                        logical_model_attempt,
                        transport_attempt,
                        provider,
                        model,
                        model_revision,
                        actual_model,
                        actual_upstream_provider,
                        candidate_fingerprint,
                        prompt_version,
                        schema_version,
                        started_at,
                        completed_at,
                        latency_ms,
                        outcome,
                        failure_class,
                        failure_code,
                        failure_summary,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
                    )
                    """,
                    lease.attempt_id,
                    ticket.call_number,
                    provider_call.logical_model_attempt,
                    provider_call.transport_attempt,
                    provider_call.provider,
                    provider_call.model,
                    provider_call.model_revision,
                    provider_call.actual_model,
                    provider_call.actual_upstream_provider,
                    provider_call.candidate_fingerprint,
                    provider_call.prompt_version,
                    provider_call.schema_version,
                    provider_call.started_at,
                    provider_call.completed_at,
                    provider_call.latency_ms,
                    provider_call.outcome.value,
                    (
                        provider_call.failure_class.value
                        if provider_call.failure_class is not None
                        else None
                    ),
                    failure_code,
                    failure_summary,
                    provider_call.prompt_tokens,
                    provider_call.completion_tokens,
                    provider_call.total_tokens,
                )
                return ticket.call_number

    async def record_provider_call(self, lease: JobLease, provider_call: ProviderCallRecord) -> int:
        """Reserve and immediately complete a call for non-network test callers."""
        ticket = await self.reserve_provider_call(
            lease, ProviderCallIntent.from_record(provider_call)
        )
        return await self.complete_provider_call(lease, ticket, provider_call)

    async def complete_verified_success(
        self,
        lease: JobLease,
        verification: StableIdVerification,
        *,
        degraded: bool = False,
        graph_counts: GraphCounts | None = None,
        relationship_quality: RelationshipQualityReport | None = None,
    ) -> CompletionStatus:
        """Commit success only after exact cross-store and source/profile proof."""
        if not verification.is_exact:
            raise InvalidTransitionError("Stable-ID verification is not exact")
        if verification.stable_id != str(lease.episode_id):
            raise InvalidTransitionError("Stable-ID verification targets another episode")
        if verification.source_fingerprint != lease.captured_source_fingerprint:
            raise InvalidTransitionError("Verified source fingerprint does not match the lease")
        if verification.sync_profile_fingerprint != lease.sync_profile_fingerprint:
            raise InvalidTransitionError("Verified sync profile does not match the lease")
        graph_counts = graph_counts or GraphCounts()
        if relationship_quality is not None:
            if any(
                value is None
                for value in (
                    relationship_quality.resolved_edges,
                    relationship_quality.new_edges,
                    relationship_quality.invalidated_edges,
                )
            ):
                raise InvalidTransitionError(
                    "Relationship quality requires complete graph-maintenance counts"
                )
            expected_counts = (
                relationship_quality.proposed_edges,
                relationship_quality.accepted_edges,
                relationship_quality.rejected_edges,
            )
            observed_counts = (
                graph_counts.proposed_edges,
                graph_counts.accepted_edges,
                graph_counts.rejected_edges,
            )
            if observed_counts != expected_counts:
                raise InvalidTransitionError(
                    "Relationship quality does not match the attempt graph counts"
                )

        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                state = await self._completion_state(connection, lease)
                if state["existing_outcome"] is not None:
                    return CompletionStatus.ALREADY_COMPLETED
                if self._source_changed(state, lease):
                    await self._record_source_change(connection, lease, state)
                    return CompletionStatus.SOURCE_CHANGED
                if not self._lease_is_current(state, lease) or not state["lease_is_valid"]:
                    if self._lease_is_current(state, lease):
                        return await self._expire_current_attempt(connection, lease, state)
                    raise LeaseLostError("Lease is no longer current")
                if state["job_sync_profile"] != lease.sync_profile_fingerprint:
                    raise InvalidTransitionError("Job sync profile changed during the lease")

                provider_call_count = await self._provider_call_count(connection, lease.attempt_id)
                outcome = (
                    AttemptOutcome.FALLBACK_SUCCESS if degraded else AttemptOutcome.PRIMARY_SUCCESS
                )
                await connection.execute(
                    """
                    INSERT INTO graph_sync_attempt_results (
                        attempt_id,
                        outcome,
                        degraded,
                        provider_call_count,
                        proposed_entity_count,
                        accepted_entity_count,
                        rejected_entity_count,
                        proposed_edge_count,
                        accepted_edge_count,
                        rejected_edge_count
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    lease.attempt_id,
                    outcome.value,
                    degraded,
                    provider_call_count,
                    graph_counts.proposed_entities,
                    graph_counts.accepted_entities,
                    graph_counts.rejected_entities,
                    graph_counts.proposed_edges,
                    graph_counts.accepted_edges,
                    graph_counts.rejected_edges,
                )
                if relationship_quality is not None:
                    await connection.execute(
                        """
                        INSERT INTO graph_sync_relationship_quality (
                            attempt_id,
                            vocabulary_fingerprint,
                            proposed_edge_count,
                            normalized_edge_count,
                            accepted_edge_count,
                            rejected_edge_count,
                            resolved_edge_count,
                            new_edge_count,
                            invalidated_edge_count,
                            rejected_unknown_type_count,
                            rejected_missing_endpoint_count,
                            rejected_ambiguous_endpoint_count,
                            rejected_self_edge_count,
                            rejected_empty_fact_count,
                            rejected_duplicate_count
                        )
                        VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8,
                            $9, $10, $11, $12, $13, $14, $15
                        )
                        """,
                        lease.attempt_id,
                        relationship_quality.vocabulary_fingerprint,
                        relationship_quality.proposed_edges,
                        relationship_quality.normalized_edges,
                        relationship_quality.accepted_edges,
                        relationship_quality.rejected_edges,
                        relationship_quality.resolved_edges,
                        relationship_quality.new_edges,
                        relationship_quality.invalidated_edges,
                        relationship_quality.rejected_unknown_type,
                        relationship_quality.rejected_missing_endpoint,
                        relationship_quality.rejected_ambiguous_endpoint,
                        relationship_quality.rejected_self_edge,
                        relationship_quality.rejected_empty_fact,
                        relationship_quality.rejected_duplicate,
                    )
                updated = await connection.execute(
                    """
                    UPDATE graph_sync_jobs
                    SET state = 'synced',
                        next_attempt_at = NULL,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        last_error_class = NULL,
                        last_error_code = NULL,
                        last_error_summary = NULL,
                        verified_source_fingerprint = $5,
                        verified_sync_profile_fingerprint = $6,
                        verified_at = clock_timestamp()
                    WHERE episode_id = $1
                      AND state = 'leased'
                      AND last_attempt_id = $2
                      AND lease_token = $3
                      AND lease_owner = $4
                    """,
                    lease.episode_id,
                    lease.attempt_id,
                    lease.lease_token,
                    lease.lease_owner,
                    lease.captured_source_fingerprint,
                    lease.sync_profile_fingerprint,
                )
                if updated != "UPDATE 1":
                    raise LeaseLostError("Lease changed during success completion")
                return CompletionStatus.SYNCED

    async def complete_failure(self, lease: JobLease, failure: FailureRecord) -> CompletionStatus:
        """Append a classified result and transition the token-fenced job."""
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                if failure.disposition is FailureDisposition.PAUSE_SYSTEMIC:
                    # Claims lock the run before jobs. Preserve that lock order
                    # here so a source-edit requeue cannot create a run/job
                    # deadlock with a systemic failure completion.
                    await connection.execute("SELECT pg_advisory_xact_lock($1)", RUN_START_LOCK_ID)
                    run_exists = await connection.fetchval(
                        "SELECT id FROM graph_sync_runs WHERE id = $1 FOR UPDATE",
                        lease.run_id,
                    )
                    if run_exists is None:
                        raise InvalidTransitionError("Attempt run does not exist")
                state = await self._completion_state(connection, lease)
                if state["existing_outcome"] is not None:
                    return CompletionStatus.ALREADY_COMPLETED

                source_changed = self._source_changed(state, lease)
                current_lease = self._lease_is_current(state, lease)
                if not current_lease and not source_changed:
                    raise LeaseLostError("Lease is no longer current")
                if current_lease and not state["lease_is_valid"]:
                    return await self._expire_current_attempt(connection, lease, state)

                outcome, job_state, consume_budget = self._failure_transition(failure, state)
                provider_call_count = await self._provider_call_count(connection, lease.attempt_id)
                await connection.execute(
                    """
                    INSERT INTO graph_sync_attempt_results (
                        attempt_id,
                        outcome,
                        degraded,
                        provider_call_count,
                        failure_class,
                        failure_code,
                        failure_summary
                    )
                    VALUES ($1, $2, FALSE, $3, $4, $5, $6)
                    """,
                    lease.attempt_id,
                    outcome.value,
                    provider_call_count,
                    failure.failure_class.value,
                    failure.code,
                    failure.summary,
                )

                if failure.disposition is FailureDisposition.PAUSE_SYSTEMIC:
                    await connection.execute(
                        """
                        UPDATE graph_sync_runs
                        SET state = 'paused_systemic',
                            heartbeat_at = clock_timestamp(),
                            last_failure_class = $2,
                            last_failure_code = $3,
                            last_failure_summary = $4
                        WHERE id = $1 AND state IN ('running', 'draining')
                        """,
                        lease.run_id,
                        failure.failure_class.value,
                        failure.code,
                        failure.summary,
                    )

                if source_changed:
                    return CompletionStatus.SOURCE_CHANGED

                next_attempt = job_state == "retry_wait"
                updated = await connection.execute(
                    """
                    UPDATE graph_sync_jobs
                    SET state = $5,
                        attempt_budget_count = CASE
                            WHEN $6 THEN attempt_budget_count
                            ELSE GREATEST(0, attempt_budget_count - 1)
                        END,
                        next_attempt_at = CASE
                            WHEN $7 THEN clock_timestamp()
                                + ($8::double precision * interval '1 second')
                            ELSE NULL
                        END,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        last_error_class = $9,
                        last_error_code = $10,
                        last_error_summary = $11
                    WHERE episode_id = $1
                      AND state = 'leased'
                      AND last_attempt_id = $2
                      AND lease_token = $3
                      AND lease_owner = $4
                    """,
                    lease.episode_id,
                    lease.attempt_id,
                    lease.lease_token,
                    lease.lease_owner,
                    job_state,
                    consume_budget,
                    next_attempt,
                    state["retry_delay_seconds"],
                    failure.failure_class.value,
                    failure.code,
                    failure.summary,
                )
                if updated != "UPDATE 1":
                    raise LeaseLostError("Lease changed during failure completion")
                return self._completion_status(outcome)

    async def recover_expired_leases(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Fence and requeue or quarantine expired attempts without manual edits."""
        if not 1 <= limit <= MAX_OPERATOR_BATCH:
            raise ValueError(f"Recovery limit must be between 1 and {MAX_OPERATOR_BATCH}")
        recovered: list[dict[str, Any]] = []
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT job.episode_id,
                           job.last_attempt_id,
                           job.lease_token,
                           job.lease_owner,
                           attempt.run_id,
                           attempt.budget_attempt_number,
                           attempt.job_attempt_limit,
                           attempt.retry_delay_seconds,
                           result.outcome AS existing_outcome
                    FROM graph_sync_jobs AS job
                    JOIN graph_sync_attempts AS attempt
                      ON attempt.id = job.last_attempt_id
                    LEFT JOIN graph_sync_attempt_results AS result
                      ON result.attempt_id = attempt.id
                    WHERE job.state = 'leased'
                      AND job.lease_expires_at <= clock_timestamp()
                    ORDER BY job.lease_expires_at, job.episode_id
                    FOR UPDATE OF job SKIP LOCKED
                    LIMIT $1
                    """,
                    limit,
                )
                for row in rows:
                    if row["existing_outcome"] is not None:
                        raise InvalidTransitionError("Expired lease already has a terminal result")
                    exhausted = row["budget_attempt_number"] >= row["job_attempt_limit"]
                    outcome = AttemptOutcome.QUARANTINED if exhausted else AttemptOutcome.RETRY_WAIT
                    provider_call_count = await self._provider_call_count(
                        connection, row["last_attempt_id"]
                    )
                    await connection.execute(
                        """
                        INSERT INTO graph_sync_attempt_results (
                            attempt_id,
                            outcome,
                            provider_call_count,
                            failure_class,
                            failure_code,
                            failure_summary
                        )
                        VALUES ($1, $2, $3, 'shutdown', 'lease_expired',
                                'Worker lease expired before terminal completion')
                        """,
                        row["last_attempt_id"],
                        outcome.value,
                        provider_call_count,
                    )
                    job_state = (
                        "quarantined" if outcome is AttemptOutcome.QUARANTINED else "retry_wait"
                    )
                    await connection.execute(
                        """
                        UPDATE graph_sync_jobs
                        SET state = $5,
                            next_attempt_at = CASE
                                WHEN $5 = 'retry_wait'
                                    THEN clock_timestamp()
                                        + ($6::double precision * interval '1 second')
                                ELSE NULL
                            END,
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            last_error_class = 'shutdown',
                            last_error_code = 'lease_expired',
                            last_error_summary =
                                'Worker lease expired before terminal completion'
                        WHERE episode_id = $1
                          AND state = 'leased'
                          AND last_attempt_id = $2
                          AND lease_token = $3
                          AND lease_owner = $4
                        """,
                        row["episode_id"],
                        row["last_attempt_id"],
                        row["lease_token"],
                        row["lease_owner"],
                        job_state,
                        row["retry_delay_seconds"],
                    )
                    recovered.append(
                        {
                            "episode_id": str(row["episode_id"]),
                            "attempt_id": str(row["last_attempt_id"]),
                            "state": job_state,
                        }
                    )
        return recovered

    async def retry_quarantined(self, episode_ids: Sequence[UUID]) -> int:
        """Explicitly open a new retry generation while preserving all history."""
        unique_ids = list(dict.fromkeys(episode_ids))
        if not unique_ids or len(unique_ids) > MAX_OPERATOR_BATCH:
            raise ValueError(f"Retry requires 1 to {MAX_OPERATOR_BATCH} episode IDs")
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT episode_id, state
                    FROM graph_sync_jobs
                    WHERE episode_id = ANY($1::uuid[])
                    ORDER BY episode_id
                    FOR UPDATE
                    """,
                    unique_ids,
                )
                if len(rows) != len(unique_ids):
                    raise InvalidTransitionError("One or more graph sync jobs do not exist")
                if any(row["state"] != "quarantined" for row in rows):
                    raise InvalidTransitionError("Every selected job must be quarantined")
                result = await connection.execute(
                    """
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
                        last_error_summary = NULL
                    WHERE episode_id = ANY($1::uuid[])
                    """,
                    unique_ids,
                )
                return int(result.split()[-1])

    async def retry_waiting(self, episode_ids: Sequence[UUID]) -> int:
        """Make selected retry-wait jobs immediately pending without resetting budget."""
        unique_ids = list(dict.fromkeys(episode_ids))
        if not unique_ids or len(unique_ids) > MAX_OPERATOR_BATCH:
            raise ValueError(f"Retry requires 1 to {MAX_OPERATOR_BATCH} episode IDs")
        async with self.postgres.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT episode_id, state
                    FROM graph_sync_jobs
                    WHERE episode_id = ANY($1::uuid[])
                    ORDER BY episode_id
                    FOR UPDATE
                    """,
                    unique_ids,
                )
                if len(rows) != len(unique_ids):
                    raise InvalidTransitionError("One or more graph sync jobs do not exist")
                if any(row["state"] != "retry_wait" for row in rows):
                    raise InvalidTransitionError("Every selected job must be in retry_wait")
                result = await connection.execute(
                    """
                    UPDATE graph_sync_jobs
                    SET state = 'pending', next_attempt_at = NULL
                    WHERE episode_id = ANY($1::uuid[])
                    """,
                    unique_ids,
                )
                return int(result.split()[-1])

    async def run_summary(
        self,
        run_id: UUID | None = None,
        *,
        rolling_window_seconds: int = DEFAULT_PROGRESS_WINDOW_SECONDS,
    ) -> dict[str, Any]:
        """Read one internally consistent summary from an explicit read-only snapshot."""
        async with self.postgres.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                return await self._run_summary(
                    connection,
                    run_id,
                    rolling_window_seconds=rolling_window_seconds,
                )

    async def _run_summary(
        self,
        connection: Any,
        run_id: UUID | None = None,
        *,
        rolling_window_seconds: int = DEFAULT_PROGRESS_WINDOW_SECONDS,
    ) -> dict[str, Any]:
        """Reconstruct one sanitized run summary entirely from durable ledger state."""
        if run_id is not None and not isinstance(run_id, UUID):
            raise ValueError("Run ID must be a UUID")
        if (
            isinstance(rolling_window_seconds, bool)
            or not isinstance(rolling_window_seconds, int)
            or not MIN_PROGRESS_WINDOW_SECONDS
            <= rolling_window_seconds
            <= MAX_PROGRESS_WINDOW_SECONDS
        ):
            raise ValueError("Rolling progress window must be between 60 and 86400 seconds")

        run = await connection.fetchrow(
            """
            SELECT id,
                   state,
                   worker_id,
                   sync_profile_fingerprint,
                   started_at,
                   updated_at,
                   heartbeat_at,
                   stopped_at,
                   last_failure_class,
                   last_failure_code,
                   last_failure_summary,
                   clock_timestamp() AS generated_at
            FROM graph_sync_runs
            WHERE $1::uuid IS NULL OR id = $1
            ORDER BY started_at DESC
            LIMIT 1
            """,
            run_id,
        )
        if run is None:
            if run_id is not None:
                raise InvalidTransitionError("Graph sync run does not exist")
            return {
                "schema_version": 1,
                "status": "no_runs",
                "run": None,
            }

        counts = await connection.fetchrow(
            """
            SELECT count(*) FILTER (WHERE state = 'pending') AS pending,
                   count(*) FILTER (WHERE state = 'leased') AS leased,
                   count(*) FILTER (WHERE state = 'retry_wait') AS retry_wait,
                   count(*) FILTER (WHERE state = 'quarantined') AS quarantined,
                   count(*) FILTER (WHERE state = 'synced') AS synced,
                   count(*) FILTER (
                       WHERE state = 'pending'
                          OR (
                              state = 'retry_wait'
                              AND next_attempt_at <= clock_timestamp()
                          )
                   ) AS eligible_now,
                   count(*) FILTER (
                       WHERE state = 'leased'
                         AND lease_expires_at <= clock_timestamp()
                   ) AS expired_leases
            FROM graph_sync_jobs
            WHERE sync_profile_fingerprint = $1
            """,
            run["sync_profile_fingerprint"],
        )
        job_counts = {state.value: int(counts[state.value]) for state in JobState}

        attempts = await connection.fetchrow(
            """
            SELECT count(attempt.id) AS attempts,
                   count(result.attempt_id) AS completed_attempts,
                   count(*) FILTER (
                       WHERE result.outcome = 'primary_success'
                   ) AS primary_success,
                   count(*) FILTER (
                       WHERE result.outcome = 'fallback_success'
                   ) AS fallback_success,
                   count(*) FILTER (
                       WHERE result.outcome = 'retry_wait'
                   ) AS retry_wait,
                   count(*) FILTER (
                       WHERE result.outcome = 'quarantined'
                   ) AS quarantined,
                   count(*) FILTER (
                       WHERE result.outcome = 'paused_systemic'
                   ) AS paused_systemic,
                   count(*) FILTER (
                       WHERE result.outcome = 'cancelled'
                   ) AS cancelled,
                   count(*) FILTER (
                       WHERE result.outcome = 'shutdown'
                   ) AS shutdown,
                   sum(result.proposed_entity_count) AS proposed_entities,
                   sum(result.accepted_entity_count) AS accepted_entities,
                   sum(result.rejected_entity_count) AS rejected_entities,
                   sum(result.proposed_edge_count) AS proposed_edges,
                   sum(result.accepted_edge_count) AS accepted_edges,
                   sum(result.rejected_edge_count) AS rejected_edges,
                   count(result.proposed_entity_count)
                       AS proposed_entities_reported_attempts,
                   count(result.accepted_entity_count)
                       AS accepted_entities_reported_attempts,
                   count(result.rejected_entity_count)
                       AS rejected_entities_reported_attempts,
                   count(result.proposed_edge_count)
                       AS proposed_edges_reported_attempts,
                   count(result.accepted_edge_count)
                       AS accepted_edges_reported_attempts,
                   count(result.rejected_edge_count)
                       AS rejected_edges_reported_attempts
            FROM graph_sync_attempts AS attempt
            LEFT JOIN graph_sync_attempt_results AS result
              ON result.attempt_id = attempt.id
            WHERE attempt.run_id = $1
            """,
            run["id"],
        )
        outcome_counts = {outcome.value: int(attempts[outcome.value]) for outcome in AttemptOutcome}

        provider = await connection.fetchrow(
            """
            SELECT count(intent.id) AS reserved,
                   count(provider_call.id) AS completed,
                   count(*) FILTER (
                       WHERE provider_call.outcome = 'success'
                   ) AS success,
                   count(*) FILTER (
                       WHERE provider_call.outcome = 'failure'
                   ) AS failure,
                   count(*) FILTER (
                       WHERE provider_call.outcome = 'cancelled'
                   ) AS cancelled,
                   sum(provider_call.prompt_tokens) AS prompt_tokens,
                   sum(provider_call.completion_tokens) AS completion_tokens,
                   sum(provider_call.total_tokens) AS total_tokens,
                   count(provider_call.prompt_tokens) AS prompt_tokens_reported_calls,
                   count(provider_call.completion_tokens)
                       AS completion_tokens_reported_calls,
                   count(provider_call.total_tokens) AS total_tokens_reported_calls
            FROM graph_sync_attempts AS attempt
            LEFT JOIN graph_sync_provider_call_intents AS intent
              ON intent.attempt_id = attempt.id
            LEFT JOIN graph_sync_provider_calls AS provider_call
              ON provider_call.attempt_id = intent.attempt_id
             AND provider_call.call_number = intent.call_number
            WHERE attempt.run_id = $1
            """,
            run["id"],
        )

        failure_rows = await connection.fetch(
            """
            SELECT scope, failure_class, count(*) AS count
            FROM (
                SELECT 'attempt'::text AS scope, result.failure_class
                FROM graph_sync_attempts AS attempt
                JOIN graph_sync_attempt_results AS result
                  ON result.attempt_id = attempt.id
                WHERE attempt.run_id = $1
                  AND result.failure_class IS NOT NULL
                UNION ALL
                SELECT 'provider'::text AS scope, provider_call.failure_class
                FROM graph_sync_attempts AS attempt
                JOIN graph_sync_provider_calls AS provider_call
                  ON provider_call.attempt_id = attempt.id
                WHERE attempt.run_id = $1
                  AND provider_call.failure_class IS NOT NULL
            ) AS failures
            GROUP BY scope, failure_class
            ORDER BY scope, failure_class
            """,
            run["id"],
        )
        failure_counts = {
            scope: {failure.value: 0 for failure in FailureClass}
            for scope in ("attempt", "provider")
        }
        for row in failure_rows:
            failure_counts[row["scope"]][row["failure_class"]] = int(row["count"])

        generated_at = run["generated_at"]
        measured_at = run["stopped_at"] or generated_at
        window_started_at = max(
            run["started_at"],
            measured_at - timedelta(seconds=rolling_window_seconds),
        )
        rolling_verified = int(
            await connection.fetchval(
                """
                SELECT count(*)
                FROM graph_sync_attempts AS attempt
                JOIN graph_sync_attempt_results AS result
                  ON result.attempt_id = attempt.id
                WHERE attempt.run_id = $1
                  AND result.outcome IN ('primary_success', 'fallback_success')
                  AND result.completed_at >= $2
                  AND result.completed_at <= $3
                """,
                run["id"],
                window_started_at,
                measured_at,
            )
        )
        progress = derive_run_progress(
            job_counts=job_counts,
            run_state=run["state"],
            started_at=run["started_at"],
            measured_at=measured_at,
            rolling_window_started_at=window_started_at,
            rolling_verified=rolling_verified,
        )
        progress.update(
            {
                "eligible_now": int(counts["eligible_now"]),
                "expired_leases": int(counts["expired_leases"]),
                "progress_scope": "current_sync_profile",
                "profile_state_observed_at": generated_at,
                "run_metrics_measured_at": measured_at,
            }
        )

        last_failure_summary = run["last_failure_summary"]
        if last_failure_summary is not None:
            last_failure_summary = sanitize_summary(last_failure_summary)
        return {
            "schema_version": 1,
            "status": "available",
            "generated_at": generated_at,
            "run": {
                "id": run["id"],
                "state": run["state"],
                "worker_id": run["worker_id"],
                "sync_profile_fingerprint": run["sync_profile_fingerprint"],
                "started_at": run["started_at"],
                "heartbeat_at": run["heartbeat_at"],
                "stopped_at": run["stopped_at"],
                "last_failure_class": run["last_failure_class"],
                "last_failure_code": run["last_failure_code"],
                "last_failure_summary": last_failure_summary,
            },
            "progress": progress,
            "attempts": {
                "attempts": int(attempts["attempts"]),
                "completed_attempts": int(attempts["completed_attempts"]),
                "outcomes": outcome_counts,
                "failure_classes": failure_counts["attempt"],
                "graph_counts": {
                    name: int(attempts[name]) if attempts[name] is not None else None
                    for name in (
                        "proposed_entities",
                        "accepted_entities",
                        "rejected_entities",
                        "proposed_edges",
                        "accepted_edges",
                        "rejected_edges",
                    )
                },
                "graph_count_reported_attempts": {
                    name: int(attempts[f"{name}_reported_attempts"])
                    for name in (
                        "proposed_entities",
                        "accepted_entities",
                        "rejected_entities",
                        "proposed_edges",
                        "accepted_edges",
                        "rejected_edges",
                    )
                },
            },
            "provider_calls": {
                "reserved": int(provider["reserved"]),
                "completed": int(provider["completed"]),
                "outcomes": {
                    outcome.value: int(provider[outcome.value]) for outcome in ProviderCallOutcome
                },
                "failure_classes": failure_counts["provider"],
                "usage": {
                    name: int(provider[name]) if provider[name] is not None else None
                    for name in (
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                    )
                },
                "usage_reported_calls": {
                    name: int(provider[f"{name}_reported_calls"])
                    for name in (
                        "prompt_tokens",
                        "completion_tokens",
                        "total_tokens",
                    )
                },
            },
        }

    async def relationship_quality_report(
        self,
        run_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Aggregate content-free relationship evidence separately from sync progress."""
        if run_id is not None and not isinstance(run_id, UUID):
            raise ValueError("Run ID must be a UUID")
        async with self.postgres.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                run = await connection.fetchrow(
                    """
                    SELECT id,
                           state,
                           sync_profile_fingerprint,
                           started_at,
                           stopped_at,
                           clock_timestamp() AS generated_at
                    FROM graph_sync_runs
                    WHERE $1::uuid IS NULL OR id = $1
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    run_id,
                )
                if run is None:
                    if run_id is not None:
                        raise InvalidTransitionError("Graph sync run does not exist")
                    return {
                        "schema_version": 1,
                        "status": "no_runs",
                        "run": None,
                    }

                metrics = await connection.fetchrow(
                    """
                    SELECT count(*) AS successful_attempts,
                           count(quality.attempt_id) AS reported_attempts,
                           COALESCE(sum(quality.proposed_edge_count), 0) AS proposed_edges,
                           COALESCE(sum(quality.normalized_edge_count), 0) AS normalized_edges,
                           COALESCE(sum(quality.accepted_edge_count), 0) AS accepted_edges,
                           COALESCE(sum(quality.rejected_edge_count), 0) AS rejected_edges,
                           COALESCE(sum(quality.resolved_edge_count), 0) AS resolved_edges,
                           COALESCE(sum(quality.new_edge_count), 0) AS new_edges,
                           COALESCE(sum(quality.invalidated_edge_count), 0)
                               AS invalidated_edges,
                           COALESCE(sum(quality.rejected_unknown_type_count), 0)
                               AS rejected_unknown_type,
                           COALESCE(sum(quality.rejected_missing_endpoint_count), 0)
                               AS rejected_missing_endpoint,
                           COALESCE(sum(quality.rejected_ambiguous_endpoint_count), 0)
                               AS rejected_ambiguous_endpoint,
                           COALESCE(sum(quality.rejected_self_edge_count), 0)
                               AS rejected_self_edge,
                           COALESCE(sum(quality.rejected_empty_fact_count), 0)
                               AS rejected_empty_fact,
                           COALESCE(sum(quality.rejected_duplicate_count), 0)
                               AS rejected_duplicate,
                           COALESCE(
                               array_agg(DISTINCT quality.vocabulary_fingerprint)
                                   FILTER (WHERE quality.vocabulary_fingerprint IS NOT NULL),
                               ARRAY[]::text[]
                           ) AS vocabulary_fingerprints
                    FROM graph_sync_attempts AS attempt
                    JOIN graph_sync_attempt_results AS result
                      ON result.attempt_id = attempt.id
                    LEFT JOIN graph_sync_relationship_quality AS quality
                      ON quality.attempt_id = attempt.id
                    WHERE attempt.run_id = $1
                      AND result.outcome IN ('primary_success', 'fallback_success')
                    """,
                    run["id"],
                )

        successful_attempts = int(metrics["successful_attempts"])
        reported_attempts = int(metrics["reported_attempts"])
        proposed_edges = int(metrics["proposed_edges"])
        normalized_edges = int(metrics["normalized_edges"])
        accepted_edges = int(metrics["accepted_edges"])
        rejected_edges = int(metrics["rejected_edges"])
        resolved_edges = int(metrics["resolved_edges"])
        new_edges = int(metrics["new_edges"])
        invalidated_edges = int(metrics["invalidated_edges"])
        if reported_attempts == 0:
            evidence_status = "none"
        elif reported_attempts == successful_attempts:
            evidence_status = "complete"
        else:
            evidence_status = "partial"
        fingerprints = list(metrics["vocabulary_fingerprints"])
        return {
            "schema_version": 1,
            "status": "available",
            "generated_at": run["generated_at"],
            "run": {
                "id": run["id"],
                "state": run["state"],
                "sync_profile_fingerprint": run["sync_profile_fingerprint"],
                "started_at": run["started_at"],
                "stopped_at": run["stopped_at"],
            },
            "evidence": {
                "status": evidence_status,
                "successful_attempts": successful_attempts,
                "reported_attempts": reported_attempts,
                "missing_attempts": successful_attempts - reported_attempts,
                "coverage_percent": _percentage(reported_attempts, successful_attempts),
            },
            "vocabulary": {
                "fingerprints": fingerprints,
                "mixed": len(fingerprints) > 1,
            },
            "relationships": {
                "proposed": proposed_edges,
                "normalized": normalized_edges,
                "accepted": accepted_edges,
                "rejected": rejected_edges,
                "resolved": resolved_edges,
                "new": new_edges,
                "invalidated": invalidated_edges,
            },
            "rates_percent": {
                "normalized_of_proposed": _percentage(normalized_edges, proposed_edges),
                "accepted_of_proposed": _percentage(accepted_edges, proposed_edges),
                "rejected_of_proposed": _percentage(rejected_edges, proposed_edges),
                "resolved_of_accepted": _percentage(resolved_edges, accepted_edges),
                "new_of_resolved": _percentage(new_edges, resolved_edges),
                "invalidated_of_resolved": _percentage(invalidated_edges, resolved_edges),
            },
            "rejection_reasons": {
                name: int(metrics[name])
                for name in (
                    "rejected_unknown_type",
                    "rejected_missing_endpoint",
                    "rejected_ambiguous_endpoint",
                    "rejected_self_edge",
                    "rejected_empty_fact",
                    "rejected_duplicate",
                )
            },
        }

    async def status_snapshot(self) -> dict[str, Any]:
        """Return bounded operator status without episode text or secrets."""
        counts = await self.postgres.fetch("""
            SELECT state, count(*) AS count
            FROM graph_sync_jobs
            GROUP BY state
            ORDER BY state
            """)
        active_run = await self.postgres.fetchrow("""
            SELECT id, state, worker_id, sync_profile_fingerprint,
                   started_at, updated_at, heartbeat_at,
                   last_failure_class, last_failure_code, last_failure_summary
            FROM graph_sync_runs
            WHERE state <> 'stopped'
            ORDER BY started_at
            LIMIT 1
            """)
        totals = await self.postgres.fetchrow("""
            SELECT count(*) AS total,
                   count(*) FILTER (
                       WHERE state = 'pending'
                          OR (state = 'retry_wait' AND next_attempt_at <= clock_timestamp())
                   ) AS eligible,
                   count(*) FILTER (
                       WHERE state = 'leased' AND lease_expires_at <= clock_timestamp()
                   ) AS expired_leases,
                   COALESCE(sum(job_attempt_count), 0) AS attempts
            FROM graph_sync_jobs
            """)
        attempt_totals = await self.postgres.fetchrow("""
            SELECT
                (SELECT count(*) FROM graph_sync_attempts) AS attempts,
                (SELECT count(*) FROM graph_sync_attempt_results)
                    AS completed_attempts,
                (SELECT count(*) FROM graph_sync_provider_call_intents)
                    AS provider_calls,
                (SELECT count(*) FROM graph_sync_provider_calls)
                    AS completed_provider_calls
            """)
        visible_run = dict(active_run) if active_run is not None else None
        if visible_run is not None and visible_run["last_failure_summary"] is not None:
            visible_run["last_failure_summary"] = sanitize_summary(
                visible_run["last_failure_summary"]
            )
        return {
            "counts": {row["state"]: row["count"] for row in counts},
            "total": totals["total"],
            "eligible": totals["eligible"],
            "expired_leases": totals["expired_leases"],
            "job_attempts": totals["attempts"],
            "ledger": dict(attempt_totals),
            "active_run": visible_run,
            "latest_run_summary": await self.run_summary(),
        }

    async def list_jobs(
        self, *, states: Sequence[str] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List bounded sanitized lifecycle rows without source content."""
        if not 1 <= limit <= MAX_OPERATOR_BATCH:
            raise ValueError(f"List limit must be between 1 and {MAX_OPERATOR_BATCH}")
        state_values = list(states or [])
        try:
            state_values = list(dict.fromkeys(JobState(state).value for state in state_values))
        except ValueError as error:
            raise ValueError("Unknown graph sync job state") from error
        rows = await self.postgres.fetch(
            """
            SELECT episode_id,
                   state,
                   job_attempt_count,
                   attempt_budget_count,
                   retry_generation,
                   next_attempt_at,
                   lease_owner,
                   lease_expires_at,
                   last_attempt_id,
                   last_error_class,
                   last_error_code,
                   last_error_summary,
                   sync_profile_fingerprint,
                   updated_at
            FROM graph_sync_jobs
            WHERE cardinality($1::text[]) = 0 OR state = ANY($1::text[])
            ORDER BY updated_at, episode_id
            LIMIT $2
            """,
            state_values,
            limit,
        )
        jobs = []
        for row in rows:
            item = dict(row)
            if item["last_error_summary"] is not None:
                item["last_error_summary"] = sanitize_summary(item["last_error_summary"])
            jobs.append(item)
        return jobs

    async def attempt_chain(self, episode_id: UUID, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return sanitized immutable attempt and provider-call provenance."""
        if not 1 <= limit <= MAX_OPERATOR_BATCH:
            raise ValueError(f"Attempt limit must be between 1 and {MAX_OPERATOR_BATCH}")
        rows = await self.postgres.fetch(
            """
            SELECT attempt.id,
                   attempt.run_id,
                   attempt.attempt_number,
                   attempt.retry_generation,
                   attempt.budget_attempt_number,
                   attempt.lease_owner,
                   attempt.captured_source_fingerprint,
                   attempt.sync_profile_fingerprint,
                   attempt.route_fingerprint,
                   attempt.job_attempt_limit,
                   attempt.provider_call_limit,
                   attempt.retry_delay_seconds,
                   attempt.started_at,
                   result.outcome,
                   result.degraded,
                   result.completed_at,
                   result.provider_call_count,
                   result.failure_class,
                   result.failure_code,
                   result.failure_summary
            FROM graph_sync_attempts AS attempt
            LEFT JOIN graph_sync_attempt_results AS result
              ON result.attempt_id = attempt.id
            WHERE attempt.episode_id = $1
            ORDER BY attempt.attempt_number DESC
            LIMIT $2
            """,
            episode_id,
            limit,
        )
        attempts = []
        for row in rows:
            item = dict(row)
            if item["failure_summary"] is not None:
                item["failure_summary"] = sanitize_summary(item["failure_summary"])
            calls = await self.postgres.fetch(
                """
                SELECT intent.call_number,
                       intent.logical_model_attempt,
                       intent.transport_attempt,
                       intent.provider,
                       intent.model,
                       intent.model_revision,
                       provider_call.actual_model,
                       provider_call.actual_upstream_provider,
                       intent.candidate_fingerprint,
                       intent.prompt_version,
                       intent.schema_version,
                       intent.started_at,
                       provider_call.completed_at,
                       provider_call.latency_ms,
                       provider_call.outcome,
                       provider_call.failure_class,
                       provider_call.failure_code,
                       provider_call.failure_summary,
                       provider_call.prompt_tokens,
                       provider_call.completion_tokens,
                       provider_call.total_tokens
                FROM graph_sync_provider_call_intents AS intent
                LEFT JOIN graph_sync_provider_calls AS provider_call
                  ON provider_call.attempt_id = intent.attempt_id
                 AND provider_call.call_number = intent.call_number
                WHERE intent.attempt_id = $1
                ORDER BY intent.call_number
                """,
                row["id"],
            )
            item["provider_calls"] = []
            for call in calls:
                provider_call = dict(call)
                if provider_call["failure_summary"] is not None:
                    provider_call["failure_summary"] = sanitize_summary(
                        provider_call["failure_summary"]
                    )
                item["provider_calls"].append(provider_call)
            attempts.append(item)
        return attempts

    async def _completion_state(self, connection, lease: JobLease):
        state = await connection.fetchrow(
            """
            SELECT attempt.id AS attempt_id,
                   attempt.lease_token AS attempt_lease_token,
                   attempt.lease_owner AS attempt_lease_owner,
                   attempt.captured_source_fingerprint,
                   attempt.sync_profile_fingerprint AS attempt_sync_profile,
                   attempt.budget_attempt_number,
                   attempt.job_attempt_limit,
                   attempt.retry_delay_seconds,
                   job.state AS job_state,
                   job.last_attempt_id,
                   job.lease_token AS job_lease_token,
                   job.lease_owner AS job_lease_owner,
                   job.desired_source_fingerprint,
                   job.sync_profile_fingerprint AS job_sync_profile,
                   job.lease_expires_at > clock_timestamp() AS lease_is_valid,
                   graph_sync_source_fingerprint(episode.text)
                       AS current_source_fingerprint,
                   result.outcome AS existing_outcome
            FROM graph_sync_attempts AS attempt
            JOIN graph_sync_jobs AS job ON job.episode_id = attempt.episode_id
            JOIN episodes AS episode ON episode.id = job.episode_id
            LEFT JOIN graph_sync_attempt_results AS result
              ON result.attempt_id = attempt.id
            WHERE attempt.id = $1 AND attempt.episode_id = $2
            FOR UPDATE OF job
            """,
            lease.attempt_id,
            lease.episode_id,
        )
        if (
            state is None
            or state["attempt_lease_token"] != lease.lease_token
            or state["attempt_lease_owner"] != lease.lease_owner
        ):
            raise LeaseLostError("Attempt identity does not match the lease")
        return state

    @staticmethod
    def _source_changed(state: Mapping[str, Any], lease: JobLease) -> bool:
        return (
            state["current_source_fingerprint"] != lease.captured_source_fingerprint
            or state["desired_source_fingerprint"] != lease.captured_source_fingerprint
        )

    @staticmethod
    def _lease_is_current(state: Mapping[str, Any], lease: JobLease) -> bool:
        return (
            state["job_state"] == "leased"
            and state["last_attempt_id"] == lease.attempt_id
            and state["job_lease_token"] == lease.lease_token
            and state["job_lease_owner"] == lease.lease_owner
        )

    async def _record_source_change(self, connection, lease: JobLease, state) -> None:
        provider_call_count = await self._provider_call_count(connection, lease.attempt_id)
        await connection.execute(
            """
            INSERT INTO graph_sync_attempt_results (
                attempt_id,
                outcome,
                provider_call_count,
                failure_class,
                failure_code,
                failure_summary
            )
            VALUES ($1, 'retry_wait', $2, 'verification', 'source_changed',
                    'Episode source changed while the attempt was active')
            """,
            lease.attempt_id,
            provider_call_count,
        )
        if self._lease_is_current(state, lease):
            await connection.execute(
                """
                UPDATE graph_sync_jobs
                SET desired_source_fingerprint = $5,
                    state = 'pending',
                    attempt_budget_count = 0,
                    retry_generation = retry_generation + 1,
                    next_attempt_at = NULL,
                    lease_owner = NULL,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    last_error_class = 'verification',
                    last_error_code = 'source_changed',
                    last_error_summary =
                        'Episode source changed while the attempt was active'
                WHERE episode_id = $1
                  AND last_attempt_id = $2
                  AND lease_token = $3
                  AND lease_owner = $4
                """,
                lease.episode_id,
                lease.attempt_id,
                lease.lease_token,
                lease.lease_owner,
                state["current_source_fingerprint"],
            )

    async def _expire_current_attempt(self, connection, lease: JobLease, state) -> CompletionStatus:
        exhausted = state["budget_attempt_number"] >= state["job_attempt_limit"]
        outcome = AttemptOutcome.QUARANTINED if exhausted else AttemptOutcome.RETRY_WAIT
        provider_call_count = await self._provider_call_count(connection, lease.attempt_id)
        await connection.execute(
            """
            INSERT INTO graph_sync_attempt_results (
                attempt_id,
                outcome,
                provider_call_count,
                failure_class,
                failure_code,
                failure_summary
            )
            VALUES ($1, $2, $3, 'shutdown', 'lease_expired',
                    'Worker lease expired before terminal completion')
            """,
            lease.attempt_id,
            outcome.value,
            provider_call_count,
        )
        job_state = "quarantined" if exhausted else "retry_wait"
        await connection.execute(
            """
            UPDATE graph_sync_jobs
            SET state = $5,
                next_attempt_at = CASE
                    WHEN $5 = 'retry_wait'
                        THEN clock_timestamp()
                            + ($6::double precision * interval '1 second')
                    ELSE NULL
                END,
                lease_owner = NULL,
                lease_token = NULL,
                lease_expires_at = NULL,
                last_error_class = 'shutdown',
                last_error_code = 'lease_expired',
                last_error_summary =
                    'Worker lease expired before terminal completion'
            WHERE episode_id = $1
              AND last_attempt_id = $2
              AND lease_token = $3
              AND lease_owner = $4
            """,
            lease.episode_id,
            lease.attempt_id,
            lease.lease_token,
            lease.lease_owner,
            job_state,
            state["retry_delay_seconds"],
        )
        return self._completion_status(outcome)

    @staticmethod
    def _failure_transition(
        failure: FailureRecord, state: Mapping[str, Any]
    ) -> tuple[AttemptOutcome, str, bool]:
        if failure.disposition is FailureDisposition.PAUSE_SYSTEMIC:
            return AttemptOutcome.PAUSED_SYSTEMIC, "retry_wait", False
        if failure.disposition is FailureDisposition.QUARANTINE:
            return AttemptOutcome.QUARANTINED, "quarantined", True
        if failure.disposition is FailureDisposition.CANCEL:
            return AttemptOutcome.CANCELLED, "retry_wait", False
        if failure.disposition is FailureDisposition.SHUTDOWN:
            return AttemptOutcome.SHUTDOWN, "retry_wait", False
        exhausted = state["budget_attempt_number"] >= state["job_attempt_limit"]
        if exhausted:
            return AttemptOutcome.QUARANTINED, "quarantined", True
        return AttemptOutcome.RETRY_WAIT, "retry_wait", True

    @staticmethod
    def _completion_status(outcome: AttemptOutcome) -> CompletionStatus:
        if outcome is AttemptOutcome.QUARANTINED:
            return CompletionStatus.QUARANTINED
        if outcome is AttemptOutcome.PAUSED_SYSTEMIC:
            return CompletionStatus.PAUSED_SYSTEMIC
        return CompletionStatus.RETRY_WAIT

    @staticmethod
    async def _provider_call_count(connection, attempt_id: UUID) -> int:
        return await connection.fetchval(
            "SELECT count(*) FROM graph_sync_provider_call_intents WHERE attempt_id = $1",
            attempt_id,
        )
