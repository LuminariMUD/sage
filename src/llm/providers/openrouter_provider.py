"""OpenRouter text adapter built on the installed OpenAI-compatible client."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Mapping
from typing import Any

from openai import AsyncOpenAI

from src.llm.base import BaseLLMProvider
from src.llm.config import get_text_route
from src.llm.monitoring import monitor_performance
from src.llm.provider_config import TextModelCandidate
from src.llm.retry import execute_with_transport_retry

_SAFE_ERROR_TYPES = frozenset(
    {
        "model_error",
        "provider_error",
        "rate_limit_exceeded",
        "server_error",
        "stream_error",
        "timeout",
        "upstream_error",
    }
)
_SAFE_MODEL_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,254}$")
_SAFE_PROVIDER_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/+@()-]{0,127}$")


class OpenRouterStreamError(RuntimeError):
    """Sanitized in-band error received after an OpenRouter stream began."""

    def __init__(self, error_type: str = "stream_error"):
        safe_error_type = error_type if error_type in _SAFE_ERROR_TYPES else "stream_error"
        super().__init__(f"OpenRouter stream terminated with {safe_error_type}")
        self.error_type = safe_error_type


def _model_extra(value: object) -> Mapping[str, Any]:
    extra = getattr(value, "model_extra", None)
    return extra if isinstance(extra, Mapping) else {}


def _error_type(error: object) -> str:
    value: object = None
    if isinstance(error, Mapping):
        metadata = error.get("metadata")
        if isinstance(metadata, Mapping) and isinstance(metadata.get("error_type"), str):
            value = metadata["error_type"]
        elif isinstance(error.get("error_type"), str):
            value = error["error_type"]
        elif isinstance(error.get("type"), str):
            value = error["type"]
    return value if isinstance(value, str) and value in _SAFE_ERROR_TYPES else "stream_error"


def _usage_metadata(usage: object) -> dict[str, int]:
    usage_dump = getattr(usage, "model_dump", None)
    dumped = usage_dump() if callable(usage_dump) else {}
    if not isinstance(dumped, Mapping):
        return {}
    return {
        str(key): value
        for key, value in dumped.items()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    }


def _metadata_label(value: object, pattern: re.Pattern[str]) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


class OpenRouterProvider(BaseLLMProvider):
    """Single-candidate OpenRouter Chat Completions adapter."""

    def __init__(self, candidate: TextModelCandidate | None = None):
        self.candidate = candidate or get_text_route("chat").primary
        if self.candidate.connection.provider != "openrouter":
            raise ValueError("OpenRouterProvider requires an OpenRouter text candidate")
        secret = self.candidate.connection.api_key
        if secret is None:  # Protected by ProviderConnection validation.
            raise ValueError("OpenRouter API credentials are required")
        self.client = AsyncOpenAI(
            api_key=secret.get_secret_value(),
            base_url=self.candidate.connection.base_url,
            timeout=self.candidate.connection.timeout_seconds,
            max_retries=0,
            default_headers=self.candidate.connection.default_headers,
        )
        self.default_model = self.candidate.model
        self.last_response_metadata: dict[str, object] = {}
        self.last_transport_attempts = 0

    def _model(self, requested: str | None) -> str:
        model = requested or self.default_model
        if model != self.default_model:
            raise ValueError("OpenRouter model overrides must use the configured candidate")
        return model

    def _record_transport_attempt(self, attempt: int) -> None:
        self.last_transport_attempts = attempt

    def _merge_extra_body(self, supplied: object) -> dict[str, object]:
        configured = self.candidate.provider_request_body()
        if supplied is None:
            return configured
        if not isinstance(supplied, Mapping):
            raise TypeError("extra_body must be a mapping")
        merged = dict(supplied)
        supplied_policy = merged.get("provider")
        if supplied_policy is not None and supplied_policy != configured.get("provider"):
            raise ValueError("OpenRouter provider routing cannot override the configured policy")
        merged.update(configured)
        return merged

    def _capture_metadata(self, response: object) -> None:
        extra = _model_extra(response)
        actual_model = _metadata_label(getattr(response, "model", None), _SAFE_MODEL_LABEL)
        upstream_provider = _metadata_label(
            getattr(response, "provider", None) or extra.get("provider"),
            _SAFE_PROVIDER_LABEL,
        )
        self.last_response_metadata = {
            "requested_model": self.candidate.model,
            "actual_model": actual_model,
            "upstream_provider": upstream_provider,
            "usage": _usage_metadata(getattr(response, "usage", None)),
            "candidate_fingerprint": self.candidate.fingerprint,
            "transport_attempts": self.last_transport_attempts,
        }

    @monitor_performance
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate one non-streaming Chat Completion."""
        self.last_response_metadata = {}
        self.last_transport_attempts = 0
        extra_body = self._merge_extra_body(kwargs.pop("extra_body", None))
        request: dict[str, Any] = {
            "model": self._model(model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "extra_body": extra_body,
            **kwargs,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        response = await execute_with_transport_retry(
            lambda: self.client.chat.completions.create(**request),
            self.candidate.connection.transport_retry,
            on_attempt=self._record_transport_attempt,
        )
        self._capture_metadata(response)
        return response.choices[0].message.content or ""

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Stream content and surface OpenRouter in-band SSE errors."""
        self.last_response_metadata = {}
        self.last_transport_attempts = 0
        extra_body = self._merge_extra_body(kwargs.pop("extra_body", None))
        request = {
            "model": self._model(model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": True,
            "extra_body": extra_body,
            **kwargs,
        }
        stream = await execute_with_transport_retry(
            lambda: self.client.chat.completions.create(**request),
            self.candidate.connection.transport_retry,
            on_attempt=self._record_transport_attempt,
        )
        actual_model: str | None = None
        upstream_provider: object = None
        async for chunk in stream:
            extra = _model_extra(chunk)
            error = getattr(chunk, "error", None) or extra.get("error")
            if error:
                raise OpenRouterStreamError(_error_type(error))
            actual_model = (
                _metadata_label(getattr(chunk, "model", None), _SAFE_MODEL_LABEL) or actual_model
            )
            upstream_provider = (
                _metadata_label(
                    getattr(chunk, "provider", None) or extra.get("provider"),
                    _SAFE_PROVIDER_LABEL,
                )
                or upstream_provider
            )
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        self.last_response_metadata = {
            "requested_model": self.candidate.model,
            "actual_model": actual_model,
            "upstream_provider": upstream_provider,
            "candidate_fingerprint": self.candidate.fingerprint,
            "transport_attempts": self.last_transport_attempts,
        }

    def get_model_info(self) -> dict[str, Any]:
        """Return only sanitized text-route details."""
        return {
            "provider": "openrouter",
            "chat_model": self.default_model,
            "base_url": self.candidate.connection.base_url,
            "candidate_fingerprint": self.candidate.fingerprint,
            "capabilities": sorted(self.candidate.capabilities),
        }
