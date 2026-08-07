"""Durable pre-request reservation and completion tracking for Graphiti calls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from src.graphiti.sync_models import (
    FailureClass,
    JobLease,
    ProviderCallIntent,
    ProviderCallOutcome,
    ProviderCallRecord,
    ProviderCallTicket,
    validate_label,
)
from src.graphiti.sync_profile import GraphSyncExecutionProfile
from src.graphiti.sync_state import GraphSyncRepository
from src.llm.provider_config import TextModelCandidate
from src.llm.retry import classify_provider_failure


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
    return (_token_count(prompt), _token_count(completion), _token_count(total))


def _token_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= 9_223_372_036_854_775_807 else None


def _safe_response_label(value: Any) -> str | None:
    if value is None:
        return None
    try:
        label = str(value)
        return validate_label(label, "Provider response label")
    except Exception:
        return None


def _upstream_provider(response: Any) -> str | None:
    direct = _value(response, "provider")
    if direct:
        return _safe_response_label(direct)
    extra = _value(response, "model_extra")
    if isinstance(extra, dict) and extra.get("provider"):
        return _safe_response_label(extra["provider"])
    return None


def _candidate_bindings(
    llm_client: Any,
) -> tuple[tuple[TextModelCandidate, Any], ...]:
    reader = getattr(llm_client, "tracked_candidate_clients", None)
    if not callable(reader):
        return ()
    bindings = tuple(reader())
    if not bindings or any(
        not isinstance(binding, tuple)
        or len(binding) != 2
        or not isinstance(binding[0], TextModelCandidate)
        for binding in bindings
    ):
        raise ProviderTrackingError("Graphiti routed client bindings are invalid")
    return bindings


def _take_transport_response(candidate_client: Any) -> Any | None:
    reader = getattr(candidate_client, "take_transport_response", None)
    if not callable(reader):
        return None
    try:
        return reader()
    except Exception:
        return None


def _durable_provider_failure(error: BaseException) -> tuple[FailureClass, str]:
    classified = classify_provider_failure(error)
    return FailureClass(classified.failure_class), classified.code


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
        bindings = _candidate_bindings(self.llm_client)
        if bindings:
            if (
                getattr(self.llm_client, "route_fingerprint", None)
                != self.profile.route_fingerprint
            ):
                raise ProviderTrackingError("Graphiti route fingerprint does not match the lease")
            if bindings[0][0].fingerprint != self.profile.candidate_fingerprint:
                raise ProviderTrackingError("Graphiti primary candidate does not match the profile")

    @staticmethod
    def verify_client(llm_client: Any) -> None:
        """Validate a Graphiti client without needing or mutating a leased job."""
        bindings = _candidate_bindings(llm_client)
        tracked = bindings or ((None, llm_client),)
        for candidate, candidate_client in tracked:
            if (
                candidate is not None
                and getattr(candidate_client, "model", None) != candidate.model
            ):
                raise ProviderTrackingError(
                    "Graphiti candidate client model does not match its route"
                )
            client = getattr(candidate_client, "client", None)
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
        bindings = _candidate_bindings(self.llm_client)
        if bindings:
            install = getattr(self.llm_client, "install_provider_call_boundary", None)
            remove = getattr(self.llm_client, "remove_provider_call_boundary", None)
            if not callable(install) or not callable(remove):
                raise ProviderTrackingError(
                    "Graphiti routed client has no durable provider-call boundary"
                )
            boundary = self._tracked_candidate_call
            install(boundary)
            self._installed = True
            try:
                yield self
            finally:
                remove(boundary)
                self._installed = False
            return

        marker = object()
        tracked = ((None, self.llm_client),)
        installed: list[tuple[Any, object]] = []
        try:
            for candidate, candidate_client in tracked:
                resource = candidate_client.client.chat.completions
                prior_instance_value = vars(resource).get("create", marker)
                original_create = resource.create

                async def tracked_create(
                    *args: Any,
                    _candidate: TextModelCandidate | None = candidate,
                    _original_create: Callable[..., Awaitable[Any]] = original_create,
                    **kwargs: Any,
                ) -> Any:
                    return await self._tracked_create(
                        _original_create,
                        _candidate,
                        *args,
                        **kwargs,
                    )

                resource.create = tracked_create
                installed.append((resource, prior_instance_value))
            self._installed = True
            yield self
        finally:
            for resource, prior_instance_value in reversed(installed):
                if prior_instance_value is marker:
                    del resource.create
                else:
                    resource.create = prior_instance_value
            self._installed = False

    def _candidate_identity(
        self,
        candidate: TextModelCandidate | None,
    ) -> tuple[str, str, str | None, str]:
        if candidate is not None:
            return (
                candidate.connection.provider,
                candidate.model,
                candidate.revision,
                candidate.fingerprint,
            )
        return (
            self.profile.provider,
            self.profile.model,
            self.profile.model_revision,
            self.profile.candidate_fingerprint,
        )

    async def _reserve(
        self,
        candidate: TextModelCandidate | None,
    ) -> tuple[ProviderCallTicket, float]:
        provider, model, revision, fingerprint = self._candidate_identity(candidate)
        self._logical_model_attempt += 1
        started_at = datetime.now(UTC)
        intent = ProviderCallIntent(
            logical_model_attempt=self._logical_model_attempt,
            transport_attempt=1,
            provider=provider,
            model=model,
            model_revision=revision,
            candidate_fingerprint=fingerprint,
            prompt_version=self.profile.prompt_version,
            schema_version=self.profile.schema_version,
            started_at=started_at,
        )
        ticket = await self.repository.reserve_provider_call(self.lease, intent)
        return ticket, perf_counter()

    async def _tracked_candidate_call(
        self,
        candidate: TextModelCandidate,
        candidate_client: Any,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        ticket, started_clock = await self._reserve(candidate)
        try:
            result = await operation()
        except asyncio.CancelledError:
            response = _take_transport_response(candidate_client)
            record = self._failure_record(
                ticket,
                started_clock,
                outcome=ProviderCallOutcome.CANCELLED,
                failure_class=FailureClass.CANCELLATION,
                failure_code="provider_call_cancelled",
                response=response,
            )
            await self._complete(ticket, record, shield=True)
            raise
        except Exception as error:
            response = _take_transport_response(candidate_client)
            failure_class, failure_code = _durable_provider_failure(error)
            record = self._failure_record(
                ticket,
                started_clock,
                outcome=ProviderCallOutcome.FAILURE,
                failure_class=failure_class,
                failure_code=failure_code,
                response=response,
            )
            await self._complete(ticket, record)
            raise

        response = _take_transport_response(candidate_client)
        if response is None:
            response = result
        await self._complete(ticket, self._success_record(ticket, response, started_clock))
        return result

    async def _tracked_create(
        self,
        original_create: Callable[..., Awaitable[Any]],
        candidate: TextModelCandidate | None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        _, expected_model, _, _ = self._candidate_identity(candidate)
        requested_model = kwargs.get("model")
        if requested_model is not None and requested_model != expected_model:
            raise ProviderTrackingError("Provider request model does not match the active profile")

        ticket, started_clock = await self._reserve(candidate)
        try:
            response = await original_create(*args, **kwargs)
        except asyncio.CancelledError:
            record = self._failure_record(
                ticket,
                started_clock,
                outcome=ProviderCallOutcome.CANCELLED,
                failure_class=FailureClass.CANCELLATION,
                failure_code="provider_call_cancelled",
            )
            await self._complete(ticket, record, shield=True)
            raise
        except Exception as error:
            failure_class, failure_code = _durable_provider_failure(error)
            record = self._failure_record(
                ticket,
                started_clock,
                outcome=ProviderCallOutcome.FAILURE,
                failure_class=failure_class,
                failure_code=failure_code,
            )
            await self._complete(ticket, record)
            raise

        await self._complete(ticket, self._success_record(ticket, response, started_clock))
        return response

    @staticmethod
    def _success_record(
        ticket: ProviderCallTicket,
        response: Any,
        started_clock: float,
    ) -> ProviderCallRecord:
        intent = ticket.intent
        prompt_tokens, completion_tokens, total_tokens = _usage_counts(response)
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
            completed_at=datetime.now(UTC),
            latency_ms=max(0, round((perf_counter() - started_clock) * 1000)),
            outcome=ProviderCallOutcome.SUCCESS,
            actual_model=_safe_response_label(_value(response, "model")) or intent.model,
            actual_upstream_provider=_upstream_provider(response),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _failure_record(
        self,
        ticket: ProviderCallTicket,
        started_clock: float,
        *,
        outcome: ProviderCallOutcome,
        failure_class: FailureClass,
        failure_code: str,
        response: Any | None = None,
    ) -> ProviderCallRecord:
        intent = ticket.intent
        completed_at = datetime.now(UTC)
        prompt_tokens, completion_tokens, total_tokens = _usage_counts(response)
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
            failure_summary=f"{failure_class.value}:{failure_code}",
            actual_model=(
                _safe_response_label(_value(response, "model")) or intent.model
                if response is not None
                else None
            ),
            actual_upstream_provider=(
                _upstream_provider(response) if response is not None else None
            ),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
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
