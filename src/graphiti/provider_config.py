"""Provider-neutral Graphiti client construction from validated Sage profiles."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from openai import AsyncOpenAI
from pydantic import ValidationError

from src.graphiti.sync_models import ProviderCallLimitExceeded
from src.llm.config import get_graphiti_embedding_profile, get_graphiti_text_route
from src.llm.embeddings.factory import create_embedder
from src.llm.provider_config import EmbeddingProfile, TextModelCandidate, TextRouteProfile
from src.llm.retry import (
    ModelOutputLimitError,
    ModelSchemaValidationError,
    classify_provider_failure,
)

logger = logging.getLogger(__name__)


class GraphitiRouteError(ValueError):
    """Raised when routed Graphiti generation is used outside its bounded scope."""


class SingleAttemptOpenAIGenericClient(OpenAIGenericClient):
    """Disable graphiti-core's opaque tenacity loop and validate structured output."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._transport_response: ContextVar[Any | None] = ContextVar(
            f"graphiti_transport_response_{id(self)}",
            default=None,
        )
        resource = self.client.chat.completions
        original_create = resource.create

        async def capture_response(*call_args: Any, **call_kwargs: Any) -> Any:
            self._transport_response.set(None)
            response = await original_create(*call_args, **call_kwargs)
            self._transport_response.set(response)
            return response

        resource.create = capture_response

    def take_transport_response(self) -> Any | None:
        """Consume the task-local raw response after parsing and validation."""
        response = self._transport_response.get()
        self._transport_response.set(None)
        return response

    def _transport_finish_reason(self) -> str | None:
        response = self._transport_response.get()
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        reason = getattr(choices[0], "finish_reason", None)
        return str(reason) if reason is not None else None

    async def generate_response(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Clear raw response content after non-routed legacy calls."""
        try:
            return await super().generate_response(*args, **kwargs)
        finally:
            self._transport_response.set(None)

    async def _generate_response_with_retry(
        self,
        messages: list[Any],
        response_model: type[Any] | None = None,
        max_tokens: int = 4096,
        model_size: Any = None,
    ) -> dict[str, Any]:
        return await self._generate_response(messages, response_model, max_tokens, model_size)

    async def _generate_response(
        self,
        messages: list[Any],
        response_model: type[Any] | None = None,
        max_tokens: int = 4096,
        model_size: Any = None,
    ) -> dict[str, Any]:
        try:
            result = await super()._generate_response(
                messages,
                response_model,
                max_tokens,
                model_size,
            )
            if self._transport_finish_reason() == "length":
                raise ModelOutputLimitError("Model output reached its configured limit")
            validator = getattr(response_model, "model_validate", None)
            if callable(validator):
                try:
                    validator(result)
                except ValidationError:
                    raise ModelSchemaValidationError(
                        "Model output failed schema validation"
                    ) from None
            return result
        except ModelOutputLimitError:
            raise
        except Exception as error:
            if self._transport_finish_reason() == "length":
                raise ModelOutputLimitError("Model output reached its configured limit") from error
            raise


class GraphitiTextRouteClient(LLMClient):
    """Execute every Graphiti generation through one bounded ordered route."""

    def __init__(
        self,
        route: TextRouteProfile,
        *,
        client_factory: Callable[[TextModelCandidate], LLMClient] | None = None,
    ):
        factory = client_factory or create_graphiti_llm_client
        bindings = tuple((candidate, factory(candidate)) for candidate in route.candidates)
        if not bindings:
            raise GraphitiRouteError("Graphiti text route has no candidates")
        super().__init__(bindings[0][1].config, cache=False)
        self.route = route
        self._bindings = bindings
        self._operation_lock = asyncio.Lock()
        self._operation_active = False
        self._operation_calls = 0
        self._operation_degraded = False
        self.last_operation_calls = 0
        self.last_operation_degraded = False
        self._provider_call_boundary: (
            Callable[
                [TextModelCandidate, LLMClient, Callable[[], Awaitable[dict[str, Any]]]],
                Awaitable[dict[str, Any]],
            ]
            | None
        ) = None

    @property
    def route_fingerprint(self) -> str:
        return self.route.fingerprint

    def tracked_candidate_clients(self) -> tuple[tuple[TextModelCandidate, LLMClient], ...]:
        """Expose immutable candidate/client bindings to the durable call tracker."""
        return self._bindings

    def install_provider_call_boundary(
        self,
        boundary: Callable[
            [TextModelCandidate, LLMClient, Callable[[], Awaitable[dict[str, Any]]]],
            Awaitable[dict[str, Any]],
        ],
    ) -> None:
        """Install one durable pre-call reservation boundary for this route."""
        if self._provider_call_boundary is not None:
            raise GraphitiRouteError("Graphiti provider-call boundary is already installed")
        self._provider_call_boundary = boundary

    def remove_provider_call_boundary(self, boundary: object) -> None:
        if self._provider_call_boundary is not boundary:
            raise GraphitiRouteError("Graphiti provider-call boundary identity changed")
        self._provider_call_boundary = None

    @asynccontextmanager
    async def operation(self) -> AsyncIterator[GraphitiTextRouteClient]:
        """Scope one episode to a fresh hard call ceiling and degraded flag."""
        async with self._operation_lock:
            if self._operation_active:
                raise GraphitiRouteError("Graphiti route operation is already active")
            self._operation_active = True
            self._operation_calls = 0
            self._operation_degraded = False
        try:
            yield self
        finally:
            async with self._operation_lock:
                self.last_operation_calls = self._operation_calls
                self.last_operation_degraded = self._operation_degraded
                self._operation_active = False

    async def _reserve_route_call(self) -> None:
        async with self._operation_lock:
            if not self._operation_active:
                raise GraphitiRouteError(
                    "Graphiti routed generation requires a bounded operation scope"
                )
            if self._operation_calls >= self.route.maximum_provider_calls:
                raise ProviderCallLimitExceeded("Graphiti route provider-call limit exhausted")
            self._operation_calls += 1

    async def _mark_degraded(self) -> None:
        async with self._operation_lock:
            if not self._operation_active:
                raise GraphitiRouteError("Graphiti route operation ended during generation")
            self._operation_degraded = True

    async def _generate_response_with_retry(
        self,
        messages: list[Any],
        response_model: type[Any] | None = None,
        max_tokens: int = 4096,
        model_size: Any = None,
    ) -> dict[str, Any]:
        # The route owns retries. Bypass graphiti-core's four-attempt decorator.
        return await self._generate_response(messages, response_model, max_tokens, model_size)

    async def _generate_response(
        self,
        messages: list[Any],
        response_model: type[Any] | None = None,
        max_tokens: int = 4096,
        model_size: Any = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        last_failure_class: str | None = None

        for candidate_number, (candidate, client) in enumerate(self._bindings, 1):
            for model_attempt in range(1, candidate.maximum_model_attempts + 1):
                await self._reserve_route_call()
                try:

                    async def generate() -> dict[str, Any]:
                        return await client._generate_response(
                            deepcopy(messages),
                            response_model,
                            max_tokens,
                            model_size,
                        )

                    if self._provider_call_boundary is None:
                        try:
                            result = await generate()
                        finally:
                            discard_response = getattr(client, "take_transport_response", None)
                            if callable(discard_response):
                                discard_response()
                    else:
                        result = await self._provider_call_boundary(candidate, client, generate)
                except ProviderCallLimitExceeded:
                    raise
                except Exception as error:
                    last_error = error
                    failure = classify_provider_failure(error)
                    last_failure_class = failure.failure_class
                    if (
                        model_attempt < candidate.maximum_model_attempts
                        and failure.failure_class in candidate.retry_on
                    ):
                        continue
                    break

                if candidate_number > 1:
                    await self._mark_degraded()
                return result

            has_fallback = candidate_number < len(self._bindings)
            if has_fallback and last_failure_class in self.route.fallback_on:
                continue
            if last_error is not None:
                raise last_error
            raise GraphitiRouteError("Graphiti route candidate ended without a result")

        if last_error is not None:
            raise last_error
        raise GraphitiRouteError("Graphiti route ended without a result")

    async def close(self) -> None:
        """Close every candidate transport without exposing its configuration."""
        for _, client in self._bindings:
            transport = getattr(client, "client", None)
            close = getattr(transport, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result


def _positive_output_tokens() -> int:
    raw = os.getenv("GRAPHITI_MAX_OUTPUT_TOKENS", "4096")
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("GRAPHITI_MAX_OUTPUT_TOKENS must be an integer") from error
    if not 1 <= value <= 1_000_000:
        raise ValueError("GRAPHITI_MAX_OUTPUT_TOKENS must be between 1 and 1000000")
    return value


def _openai_base_url(candidate: TextModelCandidate) -> str:
    base_url = candidate.connection.base_url
    if candidate.connection.provider == "ollama" and not base_url.endswith("/v1"):
        return f"{base_url}/v1"
    return base_url


def _merge_openrouter_body(candidate: TextModelCandidate, supplied: object) -> dict[str, object]:
    configured = candidate.provider_request_body()
    if supplied is None:
        return configured
    if not isinstance(supplied, Mapping):
        raise TypeError("extra_body must be a mapping")
    merged = dict(supplied)
    supplied_policy = merged.get("provider")
    if supplied_policy is not None and supplied_policy != configured.get("provider"):
        raise ValueError("Graphiti cannot override configured OpenRouter routing")
    merged.update(configured)
    return merged


def _graphiti_transport(candidate: TextModelCandidate) -> AsyncOpenAI:
    """Build a no-hidden-retry transport for durable provider accounting."""
    secret = candidate.connection.api_key
    api_key = secret.get_secret_value() if secret else "ollama"
    transport = AsyncOpenAI(
        api_key=api_key,
        base_url=_openai_base_url(candidate),
        timeout=candidate.connection.timeout_seconds,
        max_retries=0,
        default_headers=candidate.connection.default_headers,
    )
    if candidate.connection.provider == "openrouter":
        create = transport.chat.completions.create

        async def create_with_routing(*args: Any, **kwargs: Any) -> Any:
            kwargs["extra_body"] = _merge_openrouter_body(candidate, kwargs.get("extra_body"))
            return await create(*args, **kwargs)

        transport.chat.completions.create = create_with_routing
    return transport


class ProviderGraphitiEmbedder(EmbedderClient):
    """Adapt Sage's validated batch interface to Graphiti's embedder contract."""

    def __init__(self, profile: EmbeddingProfile):
        self.profile = profile
        self.embedder = create_embedder(profile, transport_max_retries=0)

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        if isinstance(input_data, str):
            return await self.embedder.embed_text(input_data)
        if (
            isinstance(input_data, list)
            and input_data
            and all(isinstance(value, str) for value in input_data)
        ):
            return (await self.embedder.embed_batch(input_data))[0]
        raise TypeError("Graphiti embedding input must contain text")

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await self.embedder.embed_batch(input_data_list)


def create_graphiti_llm_client(
    candidate: TextModelCandidate,
    *,
    verbose: bool = False,
) -> SingleAttemptOpenAIGenericClient:
    """Construct one Graphiti client with all opaque retries disabled."""
    if "structured_output" not in candidate.capabilities:
        raise ValueError("Graphiti extraction candidate lacks structured-output capability")
    max_tokens = _positive_output_tokens()
    secret = candidate.connection.api_key
    api_key = secret.get_secret_value() if secret else "ollama"
    llm_config = LLMConfig(
        api_key=api_key,
        model=candidate.model,
        small_model=candidate.model,
        base_url=_openai_base_url(candidate),
        temperature=candidate.temperature,
        max_tokens=max_tokens,
    )
    if verbose:
        logger.info(
            "Initializing Graphiti text candidate provider=%s model=%s candidate=%s",
            candidate.connection.provider,
            candidate.model,
            candidate.fingerprint,
        )
    return SingleAttemptOpenAIGenericClient(
        config=llm_config,
        client=_graphiti_transport(candidate),
        max_tokens=max_tokens,
    )


def create_graphiti_text_route_client(
    route: TextRouteProfile,
    *,
    verbose: bool = False,
) -> GraphitiTextRouteClient:
    """Construct every declared candidate for bounded durable route execution."""
    return GraphitiTextRouteClient(
        route,
        client_factory=lambda candidate: create_graphiti_llm_client(
            candidate,
            verbose=verbose,
        ),
    )


def get_graphiti_llm_client(verbose: bool = False) -> LLMClient:
    """Construct Graphiti's primary extraction client from its independent route."""
    return create_graphiti_llm_client(get_graphiti_text_route().primary, verbose=verbose)


def get_graphiti_embedding_client(verbose: bool = False) -> EmbedderClient:
    """Construct Graphiti's independently selected embedding client."""
    profile = get_graphiti_embedding_profile()
    if verbose:
        logger.info(
            "Initializing Graphiti embedding profile provider=%s model=%s dimensions=%s profile=%s",
            profile.connection.provider,
            profile.model,
            profile.dimensions,
            profile.fingerprint,
        )
    return ProviderGraphitiEmbedder(profile)


def get_graphiti_config_summary() -> dict[str, object]:
    """Return a secret-free summary with text and embedding identities separated."""
    route = get_graphiti_text_route()
    profile = get_graphiti_embedding_profile()
    return {
        "provider": route.primary.connection.provider,
        "text_provider": route.primary.connection.provider,
        "embedding_provider": profile.connection.provider,
        "llm_model": route.primary.model,
        "embedding_model": profile.model,
        "temperature": route.primary.temperature,
        "embedding_dim": profile.dimensions,
        "route_fingerprint": route.fingerprint,
        "candidate_fingerprints": [candidate.fingerprint for candidate in route.candidates],
        "embedding_profile_fingerprint": profile.fingerprint,
        "maximum_provider_calls": route.maximum_provider_calls,
    }
