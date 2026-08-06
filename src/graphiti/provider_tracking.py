"""Durable pre-request reservation and completion tracking for Graphiti calls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from src.graphiti.sync_failures import classify_sync_failure
from src.graphiti.sync_models import (
    FailureClass,
    JobLease,
    ProviderCallIntent,
    ProviderCallOutcome,
    ProviderCallRecord,
    ProviderCallTicket,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.graphiti.sync_state import GraphSyncRepository


class ProviderTrackingError(ValueError):
    """Raised when an actual provider request cannot be durably accounted for."""


class ProviderLedgerError(ProviderTrackingError):
    """Raised when a reserved or returned call cannot be completed in the ledger."""


def _value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _usage_counts(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = _value(response, "usage")
    if usage is None:
        return None, None, None
    prompt = _value(usage, "prompt_tokens")
    completion = _value(usage, "completion_tokens")
    total = _value(usage, "total_tokens")
    if prompt is None:
        prompt = _value(usage, "input_tokens")
    if completion is None:
        completion = _value(usage, "output_tokens")
    return prompt, completion, total


def _upstream_provider(response: Any) -> str | None:
    direct = _value(response, "provider")
    if direct:
        return str(direct)
    extra = _value(response, "model_extra")
    if isinstance(extra, dict) and extra.get("provider"):
        return str(extra["provider"])
    return None


class ProviderCallTracker:
    """Wrap the OpenAI-compatible request boundary for exactly one leased attempt."""

    def __init__(
        self,
        repository: GraphSyncRepository,
        lease: JobLease,
        llm_client: Any,
        profile: GraphSyncExecutionProfile,
    ):
        self.repository = repository
        self.lease = lease
        self.llm_client = llm_client
        self.profile = profile
        self._logical_model_attempt = 0
        self._installed = False

    def verify_ready(self) -> None:
        """Require a visible one-request transport boundary before installation."""
        self.verify_client(self.llm_client)

    @staticmethod
    def verify_client(llm_client: Any) -> None:
        """Validate a Graphiti client without needing or mutating a leased job."""
        client = getattr(llm_client, "client", None)
        if client is None:
            raise ProviderTrackingError("Graphiti LLM client has no inspectable transport")
        if getattr(client, "max_retries", None) != 0:
            raise ProviderTrackingError(
                "Graphiti provider transport retries must be disabled for durable accounting"
            )
        create = getattr(
            getattr(getattr(client, "chat", None), "completions", None),
            "create",
            None,
        )
        if not callable(create):
            raise ProviderTrackingError(
                "Graphiti LLM client does not expose a chat-completions request boundary"
            )

    @asynccontextmanager
    async def installed(self) -> AsyncIterator[ProviderCallTracker]:
        """Install tracking for a scoped Graphiti call and restore it reliably."""
        self.verify_ready()
        if self._installed:
            raise ProviderTrackingError("Provider tracking is already installed")
        resource = self.llm_client.client.chat.completions
        marker = object()
        prior_instance_value = vars(resource).get("create", marker)
        original_create = resource.create

        async def tracked_create(*args: Any, **kwargs: Any) -> Any:
            return await self._tracked_create(original_create, *args, **kwargs)

        resource.create = tracked_create
        self._installed = True
        try:
            yield self
        finally:
            if prior_instance_value is marker:
                del resource.create
            else:
                resource.create = prior_instance_value
            self._installed = False

    async def _tracked_create(
        self,
        original_create: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        requested_model = kwargs.get("model")
        if requested_model is not None and requested_model != self.profile.model:
            raise ProviderTrackingError("Provider request model does not match the active profile")

        self._logical_model_attempt += 1
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        intent = ProviderCallIntent(
            logical_model_attempt=self._logical_model_attempt,
            transport_attempt=1,
            provider=self.profile.provider,
            model=self.profile.model,
            model_revision=self.profile.model_revision,
            candidate_fingerprint=self.profile.candidate_fingerprint,
            prompt_version=self.profile.prompt_version,
            schema_version=self.profile.schema_version,
            started_at=started_at,
        )
        ticket = await self.repository.reserve_provider_call(self.lease, intent)
        try:
            response = await original_create(*args, **kwargs)
        except asyncio.CancelledError as error:
            record = self._failure_record(
                ticket,
                error,
                started_clock,
                outcome=ProviderCallOutcome.CANCELLED,
                failure_class=FailureClass.CANCELLATION,
                failure_code="provider_call_cancelled",
            )
            await self._complete(ticket, record, shield=True)
            raise
        except Exception as error:
            failure = classify_sync_failure(error)
            record = self._failure_record(
                ticket,
                error,
                started_clock,
                outcome=ProviderCallOutcome.FAILURE,
                failure_class=failure.failure_class,
                failure_code=failure.code,
            )
            await self._complete(ticket, record)
            raise

        completed_at = datetime.now(UTC)
        prompt_tokens, completion_tokens, total_tokens = _usage_counts(response)
        record = ProviderCallRecord(
            logical_model_attempt=intent.logical_model_attempt,
            transport_attempt=intent.transport_attempt,
            provider=intent.provider,
            model=intent.model,
            model_revision=intent.model_revision,
            candidate_fingerprint=intent.candidate_fingerprint,
            prompt_version=intent.prompt_version,
            schema_version=intent.schema_version,
            started_at=intent.started_at,
            completed_at=completed_at,
            latency_ms=max(0, round((perf_counter() - started_clock) * 1000)),
            outcome=ProviderCallOutcome.SUCCESS,
            actual_model=str(_value(response, "model") or intent.model),
            actual_upstream_provider=_upstream_provider(response),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        await self._complete(ticket, record)
        return response

    def _failure_record(
        self,
        ticket: ProviderCallTicket,
        error: BaseException,
        started_clock: float,
        *,
        outcome: ProviderCallOutcome,
        failure_class: FailureClass,
        failure_code: str,
    ) -> ProviderCallRecord:
        intent = ticket.intent
        completed_at = datetime.now(UTC)
        return ProviderCallRecord(
            logical_model_attempt=intent.logical_model_attempt,
            transport_attempt=intent.transport_attempt,
            provider=intent.provider,
            model=intent.model,
            model_revision=intent.model_revision,
            candidate_fingerprint=intent.candidate_fingerprint,
            prompt_version=intent.prompt_version,
            schema_version=intent.schema_version,
            started_at=intent.started_at,
            completed_at=completed_at,
            latency_ms=max(0, round((perf_counter() - started_clock) * 1000)),
            outcome=outcome,
            failure_class=failure_class,
            failure_code=failure_code,
            failure_summary=error,
        )

    async def _complete(
        self,
        ticket: ProviderCallTicket,
        record: ProviderCallRecord,
        *,
        shield: bool = False,
    ) -> None:
        completion = self.repository.complete_provider_call(self.lease, ticket, record)
        try:
            if shield:
                await asyncio.shield(completion)
            else:
                await completion
        except Exception as error:
            raise ProviderLedgerError(
                "Provider request returned but its durable completion could not be recorded"
            ) from error
