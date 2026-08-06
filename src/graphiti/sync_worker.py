"""Single-worker durable Graphiti synchronization orchestration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import asdict, dataclass
from time import perf_counter

from src.graphiti.provider_tracking import ProviderCallTracker
from src.graphiti.sync_failures import classify_sync_failure
from src.graphiti.sync_graph import GraphitiEpisodeProcessor, GraphProcessingResult
from src.graphiti.sync_models import (
    CompletionStatus,
    GraphSyncPolicy,
    JobLease,
    ProfileMismatchError,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.graphiti.sync_state import GraphSyncRepository

logger = logging.getLogger(__name__)


class WorkerShutdownRequested(RuntimeError):
    """Raised internally when a graceful stop interrupts an active episode."""


@dataclass
class WorkerRunSummary:
    run_id: str | None = None
    recovered_expired: int = 0
    attempted: int = 0
    synced: int = 0
    reused_existing: int = 0
    retrying: int = 0
    quarantined: int = 0
    source_changed: int = 0
    paused_systemic: int = 0
    already_completed: int = 0
    elapsed_seconds: float = 0.0

    def as_dict(self) -> dict[str, str | int | float | None]:
        return asdict(self)


class GraphSyncWorker:
    """Claim and complete one durable Graphiti episode at a time."""

    def __init__(
        self,
        *,
        repository: GraphSyncRepository,
        graph_processor: GraphitiEpisodeProcessor,
        llm_client: object,
        profile: GraphSyncExecutionProfile,
        policy: GraphSyncPolicy,
        worker_id: str,
    ):
        self.repository = repository
        self.graph_processor = graph_processor
        self.llm_client = llm_client
        self.profile = profile
        self.policy = policy
        self.worker_id = worker_id
        self.shutdown_event = asyncio.Event()
        self._running = False

    def request_shutdown(self) -> None:
        """Stop new claims and interrupt the current provider call, if any."""
        self.shutdown_event.set()

    async def run(self, *, max_episodes: int | None = None) -> WorkerRunSummary:
        """Run until idle, stopped, paused, or the optional finite limit is reached."""
        if self._running:
            raise RuntimeError("Graph sync worker is already running")
        if max_episodes is not None and max_episodes <= 0:
            raise ValueError("Maximum episodes must be positive")

        self._running = True
        started = perf_counter()
        summary = WorkerRunSummary()
        run = None
        try:
            await self.graph_processor.verify_readiness()
            ProviderCallTracker.verify_client(self.llm_client)
            profile_state = await self.repository.profile_snapshot(
                self.profile.sync_profile_fingerprint
            )
            if profile_state["non_synced_other_profile"]:
                raise ProfileMismatchError("Non-synced jobs target a different graph sync profile")
            if not profile_state["matching_jobs"]:
                return summary
            recovered = await self.repository.recover_expired_leases()
            summary.recovered_expired = len(recovered)
            run = await self.repository.start_or_join_run(
                worker_id=self.worker_id,
                sync_profile_fingerprint=self.profile.sync_profile_fingerprint,
            )
            summary.run_id = str(run.id)

            while not self.shutdown_event.is_set():
                if max_episodes is not None and summary.attempted >= max_episodes:
                    break
                leases = await self.repository.claim_jobs(
                    run_id=run.id,
                    worker_id=self.worker_id,
                    route_fingerprint=self.profile.route_fingerprint,
                    policy=self.policy,
                    limit=1,
                )
                if not leases:
                    break
                lease = leases[0]
                summary.attempted += 1
                status, result = await self._process_lease(lease)
                self._record_status(summary, status, result)
                if status is CompletionStatus.PAUSED_SYSTEMIC:
                    break

        finally:
            if run is not None and run.worker_id == self.worker_id and not summary.paused_systemic:
                await self.repository.drain_run(run.id)
                await self.repository.stop_run(run.id)
            summary.elapsed_seconds = round(perf_counter() - started, 3)
            self._running = False
        return summary

    async def _process_lease(
        self, lease: JobLease
    ) -> tuple[CompletionStatus, GraphProcessingResult | None]:
        tracker = ProviderCallTracker(
            self.repository,
            lease,
            self.llm_client,
            self.profile,
        )
        try:
            async with tracker.installed():
                result = await self._process_with_heartbeats(lease)
            status = await self.repository.complete_verified_success(
                lease,
                result.verification,
                graph_counts=result.graph_counts,
            )
            return status, result
        except WorkerShutdownRequested as error:
            failure = classify_sync_failure(error, shutting_down=True)
            status = await self.repository.complete_failure(lease, failure)
            return status, None
        except asyncio.CancelledError as error:
            failure = classify_sync_failure(error, shutting_down=True)
            await asyncio.shield(self.repository.complete_failure(lease, failure))
            raise
        except Exception as error:
            failure = classify_sync_failure(error)
            logger.warning(
                "Graph sync attempt failed (%s, disposition=%s)",
                failure.code,
                failure.disposition.value,
            )
            status = await self.repository.complete_failure(lease, failure)
            return status, None

    async def _process_with_heartbeats(self, lease: JobLease) -> GraphProcessingResult:
        processing = asyncio.create_task(
            self.graph_processor.process(lease),
            name=f"graph-sync-process-{lease.attempt_id}",
        )
        heartbeat = asyncio.create_task(
            self._heartbeat(lease),
            name=f"graph-sync-heartbeat-{lease.attempt_id}",
        )
        shutdown = asyncio.create_task(
            self.shutdown_event.wait(),
            name=f"graph-sync-shutdown-{lease.attempt_id}",
        )
        tasks = {processing, heartbeat, shutdown}
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if shutdown in done and shutdown.result():
                processing.cancel()
                with suppress(asyncio.CancelledError):
                    await processing
                raise WorkerShutdownRequested("Worker shutdown requested")
            if heartbeat in done:
                exception = heartbeat.exception()
                processing.cancel()
                with suppress(asyncio.CancelledError):
                    await processing
                if exception is None:
                    raise RuntimeError("Heartbeat stopped unexpectedly")
                raise exception
            return await processing
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError, Exception):
                    await task

    async def _heartbeat(self, lease: JobLease) -> None:
        interval = max(10.0, min(60.0, self.policy.lease_seconds / 3))
        while True:
            await asyncio.sleep(interval)
            await self.repository.heartbeat_run(lease.run_id)
            await self.repository.heartbeat_lease(
                lease,
                lease_seconds=self.policy.lease_seconds,
            )

    @staticmethod
    def _record_status(
        summary: WorkerRunSummary,
        status: CompletionStatus,
        result: GraphProcessingResult | None,
    ) -> None:
        if status is CompletionStatus.SYNCED:
            summary.synced += 1
            if result is not None and result.reused_existing:
                summary.reused_existing += 1
        elif status is CompletionStatus.RETRY_WAIT:
            summary.retrying += 1
        elif status is CompletionStatus.QUARANTINED:
            summary.quarantined += 1
        elif status is CompletionStatus.PAUSED_SYSTEMIC:
            summary.paused_systemic += 1
        elif status is CompletionStatus.SOURCE_CHANGED:
            summary.source_changed += 1
        elif status is CompletionStatus.ALREADY_COMPLETED:
            summary.already_completed += 1
