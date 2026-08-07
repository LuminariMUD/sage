"""Unit tests for durable worker orchestration and shutdown behavior."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.graphiti.sync_graph import GraphProcessingResult
from src.graphiti.sync_models import (
    CompletionStatus,
    GraphCounts,
    GraphSyncPolicy,
    JobLease,
    ProfileMismatchError,
    RunRecord,
    RunState,
    StableIdVerification,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.graphiti.sync_worker import GraphSyncWorker


def _profile():
    return GraphSyncExecutionProfile(
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        candidate_fingerprint="candidate:test",
        embedding_profile_fingerprint="embedding:test",
        provider="ollama",
        model="qwen2.5:3b",
        prompt_version="prompt:v1",
        schema_version="schema:v1",
        max_entities=25,
        max_relationships=25,
    )


def _lease():
    now = datetime.now(UTC)
    return JobLease(
        episode_id=uuid4(),
        attempt_id=uuid4(),
        run_id=uuid4(),
        lease_token=uuid4(),
        lease_owner="worker-a",
        attempt_number=1,
        budget_attempt_number=1,
        retry_generation=0,
        job_attempt_limit=3,
        provider_call_limit=3,
        retry_delay_seconds=60,
        captured_source_fingerprint="sha256:v1:test",
        sync_profile_fingerprint="sync:test",
        route_fingerprint="route:test",
        lease_expires_at=now + timedelta(minutes=15),
        text="Lore",
        document_id=uuid4(),
        episode_index=1,
        created_at=now,
    )


def _verification(lease):
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
        embedding_profile_fingerprint="embedding:test",
        embedding_profile_fingerprint_count=1,
    )


def _llm_client():
    async def create(**kwargs):
        raise AssertionError("processor should not call the provider in this unit test")

    return SimpleNamespace(
        client=SimpleNamespace(
            max_retries=0,
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        )
    )


class FakeRepository:
    def __init__(self, lease):
        self.lease = lease
        self.claimed = asyncio.Event()
        self.claim_count = 0
        self.failures = []
        self.successes = []
        self.events = []
        self.profile_state = {
            "matching_jobs": 1,
            "matching_eligible": 1,
            "matching_expired_leases": 0,
            "non_synced_other_profile": 0,
        }

    async def profile_snapshot(self, fingerprint):
        self.events.append("profile")
        return self.profile_state

    async def recover_expired_leases(self):
        self.events.append("recover")
        return []

    async def start_or_join_run(self, **kwargs):
        self.events.append("start")
        now = datetime.now(UTC)
        return RunRecord(
            id=self.lease.run_id,
            state=RunState.RUNNING,
            worker_id=kwargs["worker_id"],
            sync_profile_fingerprint=kwargs["sync_profile_fingerprint"],
            started_at=now,
            heartbeat_at=now,
        )

    async def claim_jobs(self, **kwargs):
        self.events.append("claim")
        self.claim_count += 1
        if self.claim_count == 1:
            self.claimed.set()
            return [self.lease]
        return []

    async def complete_verified_success(self, lease, verification, **kwargs):
        self.events.append("success")
        self.successes.append(kwargs)
        return CompletionStatus.SYNCED

    async def complete_failure(self, lease, failure):
        self.events.append("failure")
        self.failures.append(failure)
        if failure.disposition.value == "pause_systemic":
            return CompletionStatus.PAUSED_SYSTEMIC
        return CompletionStatus.RETRY_WAIT

    async def heartbeat_run(self, run_id):
        self.events.append("heartbeat_run")

    async def heartbeat_lease(self, lease, *, lease_seconds):
        self.events.append("heartbeat_lease")

    async def drain_run(self, run_id):
        self.events.append("drain")

    async def stop_run(self, run_id):
        self.events.append("stop")


class FakeProcessor:
    def __init__(self, lease, *, error=None, block=False, ready_error=None):
        self.lease = lease
        self.error = error
        self.block = block
        self.ready_error = ready_error
        self.cancelled = False

    async def verify_readiness(self):
        if self.ready_error:
            raise self.ready_error

    async def process(self, lease):
        if self.error:
            raise self.error
        if self.block:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return GraphProcessingResult(
            verification=_verification(lease),
            graph_counts=GraphCounts(accepted_entities=2, accepted_edges=1),
            reused_existing=False,
        )


def _worker(repository, processor, *, llm_client=None):
    return GraphSyncWorker(
        repository=repository,
        graph_processor=processor,
        llm_client=llm_client or _llm_client(),
        profile=_profile(),
        policy=GraphSyncPolicy(lease_seconds=30),
        worker_id="worker-a",
    )


async def test_worker_recovers_claims_verifies_and_stops_owned_run():
    lease = _lease()
    repository = FakeRepository(lease)
    worker = _worker(repository, FakeProcessor(lease))

    summary = await worker.run(max_episodes=1)

    assert summary.attempted == 1
    assert summary.synced == 1
    assert repository.events == [
        "profile",
        "recover",
        "start",
        "claim",
        "success",
        "drain",
        "stop",
    ]


async def test_worker_records_routed_fallback_as_degraded_success():
    lease = _lease()
    repository = FakeRepository(lease)
    llm_client = _llm_client()
    llm_client.last_operation_degraded = False

    @asynccontextmanager
    async def operation():
        try:
            yield llm_client
        finally:
            llm_client.last_operation_degraded = True

    llm_client.operation = operation
    worker = _worker(
        repository,
        FakeProcessor(lease),
        llm_client=llm_client,
    )

    summary = await worker.run(max_episodes=1)

    assert summary.synced == 1
    assert summary.degraded_synced == 1
    assert repository.successes[0]["degraded"] is True


async def test_systemic_configuration_failure_pauses_without_stopping_run():
    lease = _lease()
    repository = FakeRepository(lease)
    worker = _worker(repository, FakeProcessor(lease, error=ValueError("bad profile")))

    summary = await worker.run(max_episodes=1)

    assert summary.paused_systemic == 1
    assert repository.failures[0].failure_class.value == "configuration"
    assert repository.events[-1] == "failure"
    assert "drain" not in repository.events


async def test_shutdown_cancels_active_work_records_shutdown_and_releases_run():
    lease = _lease()
    repository = FakeRepository(lease)
    processor = FakeProcessor(lease, block=True)
    worker = _worker(repository, processor)

    task = asyncio.create_task(worker.run(max_episodes=1))
    await asyncio.wait_for(repository.claimed.wait(), timeout=1)
    worker.request_shutdown()
    summary = await asyncio.wait_for(task, timeout=1)

    assert processor.cancelled
    assert summary.retrying == 1
    assert repository.failures[0].failure_class.value == "shutdown"
    assert repository.events[-2:] == ["drain", "stop"]


async def test_readiness_failure_occurs_before_run_or_claim():
    lease = _lease()
    repository = FakeRepository(lease)
    worker = _worker(
        repository,
        FakeProcessor(lease, ready_error=RuntimeError("duplicate stable ids")),
    )

    with pytest.raises(RuntimeError, match="duplicate stable ids"):
        await worker.run()

    assert repository.events == []


async def test_profile_mismatch_fails_before_recovery_or_run():
    lease = _lease()
    repository = FakeRepository(lease)
    repository.profile_state["non_synced_other_profile"] = 3
    worker = _worker(repository, FakeProcessor(lease))

    with pytest.raises(ProfileMismatchError, match="different graph sync profile"):
        await worker.run()

    assert repository.events == ["profile"]
