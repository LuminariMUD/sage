"""Bounded text-route execution above single-call provider adapters."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any, Literal

from src.llm.base import BaseLLMProvider
from src.llm.config import get_text_route
from src.llm.provider_config import (
    FailureClassName,
    TextModelCandidate,
    TextRouteProfile,
    TextTask,
    TransportRetryPolicy,
)
from src.llm.providers.factory import get_llm_provider
from src.llm.retry import (
    ClassifiedProviderFailure,
    classify_provider_failure,
    retry_delay_seconds,
)

RouteValidator = Callable[[str], str]
ProviderFactory = Callable[[TextModelCandidate], BaseLLMProvider]
_MODEL_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,254}$")
_PROVIDER_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/+@()-]{0,127}$")
_USAGE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True)
class TextRouteAttempt:
    """Sanitized provenance for one actual upstream request."""

    call_number: int
    candidate_number: int
    model_attempt: int
    transport_attempt: int
    provider: str
    model: str
    candidate_fingerprint: str
    outcome: Literal["success", "failure"]
    latency_ms: int
    failure_class: FailureClassName | None = None
    failure_code: str | None = None
    actual_model: str | None = None
    upstream_provider: str | None = None


@dataclass(frozen=True)
class TextRouteResult:
    """Successful text plus its route outcome and secret-free attempt chain."""

    text: str
    route_fingerprint: str
    candidate_fingerprint: str
    degraded: bool
    attempts: tuple[TextRouteAttempt, ...]
    response_metadata: Mapping[str, object]


class TextRouteExecutionError(RuntimeError):
    """A text route ended without a valid response."""

    def __init__(
        self,
        route: TextRouteProfile,
        attempts: list[TextRouteAttempt],
        failure: ClassifiedProviderFailure,
        *,
        budget_exhausted: bool = False,
    ):
        reason = "provider-call budget exhausted" if budget_exhausted else failure.code
        super().__init__(f"Text route failed: {reason}")
        self.route_fingerprint = route.fingerprint
        self.attempts = tuple(attempts)
        self.failure_class = failure.failure_class
        self.failure_code = failure.code
        self.budget_exhausted = budget_exhausted


def _single_transport_candidate(candidate: TextModelCandidate) -> TextModelCandidate:
    """Disable adapter retries so the route owns every actual request count."""
    connection = replace(
        candidate.connection,
        transport_retry=TransportRetryPolicy(
            maximum_attempts=1,
            retry_on=frozenset(),
            base_delay_seconds=0,
            maximum_delay_seconds=0,
        ),
    )
    return replace(candidate, connection=connection)


def _response_metadata(
    provider: BaseLLMProvider, candidate: TextModelCandidate
) -> dict[str, object]:
    metadata = getattr(provider, "last_response_metadata", None)
    if not isinstance(metadata, Mapping):
        metadata = {}
    result: dict[str, object] = {
        "requested_model": candidate.model,
        "candidate_fingerprint": candidate.fingerprint,
    }
    actual_model = metadata.get("actual_model")
    if isinstance(actual_model, str) and _MODEL_LABEL.fullmatch(actual_model):
        result["actual_model"] = actual_model
    upstream_provider = metadata.get("upstream_provider")
    if isinstance(upstream_provider, str) and _PROVIDER_LABEL.fullmatch(upstream_provider):
        result["upstream_provider"] = upstream_provider
    usage = metadata.get("usage")
    if isinstance(usage, Mapping):
        result["usage"] = {
            str(key): value
            for key, value in usage.items()
            if _USAGE_KEY.fullmatch(str(key))
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        }
    transport_attempts = metadata.get("transport_attempts")
    if isinstance(transport_attempts, int) and 1 <= transport_attempts <= 10:
        result["transport_attempts"] = transport_attempts
    return result


def _reset_response_metadata(provider: BaseLLMProvider) -> None:
    metadata = getattr(provider, "last_response_metadata", None)
    if isinstance(metadata, dict):
        metadata.clear()


class TextRouteExecutor:
    """Execute ordered candidates with distinct transport, model, and fallback policy."""

    def __init__(
        self,
        route: TextRouteProfile,
        *,
        provider_factory: ProviderFactory | None = None,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ):
        self.route = route
        self.provider_factory = provider_factory or (
            lambda candidate: get_llm_provider(candidate=candidate)
        )
        self.sleep = sleep

    async def execute(
        self,
        prompt: str,
        *,
        validator: RouteValidator | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> TextRouteResult:
        """Return the first validated response or a sanitized exhausted-route error."""
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("Text route prompt must be a non-empty string")
        attempts: list[TextRouteAttempt] = []
        last_failure = ClassifiedProviderFailure("internal", "route_not_attempted")

        for candidate_number, candidate in enumerate(self.route.candidates, 1):
            try:
                provider = self.provider_factory(_single_transport_candidate(candidate))
            except Exception as error:
                failure = classify_provider_failure(error)
                raise TextRouteExecutionError(self.route, attempts, failure) from None
            candidate_failure: ClassifiedProviderFailure | None = None
            for model_attempt in range(1, candidate.maximum_model_attempts + 1):
                candidate_failure = None
                for transport_attempt in range(
                    1,
                    candidate.connection.transport_retry.maximum_attempts + 1,
                ):
                    if len(attempts) >= self.route.maximum_provider_calls:
                        budget_failure = ClassifiedProviderFailure(
                            "resource_exhaustion", "provider_call_budget_exhausted"
                        )
                        raise TextRouteExecutionError(
                            self.route,
                            attempts,
                            budget_failure,
                            budget_exhausted=True,
                        ) from None
                    started = perf_counter()
                    try:
                        _reset_response_metadata(provider)
                        text = await provider.generate(
                            prompt,
                            model=candidate.model,
                            temperature=candidate.temperature,
                            max_tokens=max_tokens,
                            **kwargs,
                        )
                        if validator is not None:
                            text = validator(text)
                    except Exception as error:
                        candidate_failure = classify_provider_failure(error)
                        last_failure = candidate_failure
                        attempts.append(
                            self._attempt(
                                candidate,
                                attempts,
                                candidate_number=candidate_number,
                                model_attempt=model_attempt,
                                transport_attempt=transport_attempt,
                                outcome="failure",
                                started=started,
                                failure=candidate_failure,
                                metadata=_response_metadata(provider, candidate),
                            )
                        )
                        if (
                            transport_attempt
                            < candidate.connection.transport_retry.maximum_attempts
                            and candidate_failure.failure_class
                            in candidate.connection.transport_retry.retry_on
                        ):
                            delay = retry_delay_seconds(
                                error,
                                candidate.connection.transport_retry,
                                failed_attempt=transport_attempt,
                            )
                            if delay:
                                await self.sleep(delay)
                            continue
                        break

                    metadata = _response_metadata(provider, candidate)
                    attempts.append(
                        self._attempt(
                            candidate,
                            attempts,
                            candidate_number=candidate_number,
                            model_attempt=model_attempt,
                            transport_attempt=transport_attempt,
                            outcome="success",
                            started=started,
                            metadata=metadata,
                        )
                    )
                    return TextRouteResult(
                        text=text,
                        route_fingerprint=self.route.fingerprint,
                        candidate_fingerprint=candidate.fingerprint,
                        degraded=candidate_number > 1,
                        attempts=tuple(attempts),
                        response_metadata=metadata,
                    )

                if candidate_failure is None:
                    break
                if (
                    model_attempt < candidate.maximum_model_attempts
                    and candidate_failure.failure_class in candidate.retry_on
                ):
                    continue
                break

            has_fallback = candidate_number < len(self.route.candidates)
            if (
                has_fallback
                and candidate_failure is not None
                and candidate_failure.failure_class in self.route.fallback_on
            ):
                continue
            raise TextRouteExecutionError(
                self.route,
                attempts,
                candidate_failure or last_failure,
            ) from None

        raise TextRouteExecutionError(self.route, attempts, last_failure) from None

    @staticmethod
    def _attempt(
        candidate: TextModelCandidate,
        attempts: list[TextRouteAttempt],
        *,
        candidate_number: int,
        model_attempt: int,
        transport_attempt: int,
        outcome: Literal["success", "failure"],
        started: float,
        metadata: Mapping[str, object],
        failure: ClassifiedProviderFailure | None = None,
    ) -> TextRouteAttempt:
        actual_model = metadata.get("actual_model")
        upstream = metadata.get("upstream_provider")
        return TextRouteAttempt(
            call_number=len(attempts) + 1,
            candidate_number=candidate_number,
            model_attempt=model_attempt,
            transport_attempt=transport_attempt,
            provider=candidate.connection.provider,
            model=candidate.model,
            candidate_fingerprint=candidate.fingerprint,
            outcome=outcome,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            failure_class=failure.failure_class if failure else None,
            failure_code=failure.code if failure else None,
            actual_model=str(actual_model) if actual_model else None,
            upstream_provider=str(upstream) if upstream else None,
        )


def get_text_route_executor(task: TextTask = "chat") -> TextRouteExecutor:
    """Construct an executor for one configured application text task."""
    return TextRouteExecutor(get_text_route(task))
