"""OpenRouter text adapter built on the installed OpenAI-compatible client."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from typing import Any

from openai import AsyncOpenAI

from src.llm.base import BaseLLMProvider
from src.llm.config import get_text_route
from src.llm.monitoring import monitor_performance
from src.llm.provider_config import TextModelCandidate


class OpenRouterStreamError(RuntimeError):
    """Sanitized in-band error received after an OpenRouter stream began."""

    def __init__(self, error_type: str = "stream_error"):
        super().__init__(f"OpenRouter stream terminated with {error_type}")
        self.error_type = error_type


def _model_extra(value: object) -> Mapping[str, Any]:
    extra = getattr(value, "model_extra", None)
    return extra if isinstance(extra, Mapping) else {}


def _error_type(error: object) -> str:
    if isinstance(error, Mapping):
        metadata = error.get("metadata")
        if isinstance(metadata, Mapping) and isinstance(metadata.get("error_type"), str):
            return metadata["error_type"]
        if isinstance(error.get("error_type"), str):
            return error["error_type"]
        if isinstance(error.get("type"), str):
            return error["type"]
    return "stream_error"


class OpenRouterProvider(BaseLLMProvider):
    """Single-candidate OpenRouter Chat Completions adapter."""

    def __init__(self, candidate: TextModelCandidate | None = None):
        self.candidate = candidate or get_text_route("chat").primary
        if self.candidate.connection.provider != "openrouter":
            raise ValueError("OpenRouterProvider requires an OpenRouter text candidate")
        secret = self.candidate.connection.api_key
        if secret is None:  # Protected by ProviderConnection validation.
            raise ValueError("OpenRouter API credentials are required")
        retry_policy = self.candidate.connection.transport_retry
        self.client = AsyncOpenAI(
            api_key=secret.get_secret_value(),
            base_url=self.candidate.connection.base_url,
            timeout=self.candidate.connection.timeout_seconds,
            max_retries=retry_policy.maximum_attempts - 1,
            default_headers=self.candidate.connection.default_headers,
        )
        self.default_model = self.candidate.model
        self.last_response_metadata: dict[str, object] = {}

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
        usage = getattr(response, "usage", None)
        usage_dump = getattr(usage, "model_dump", None)
        self.last_response_metadata = {
            "requested_model": self.candidate.model,
            "actual_model": getattr(response, "model", None),
            "upstream_provider": getattr(response, "provider", None) or extra.get("provider"),
            "usage": usage_dump() if callable(usage_dump) else None,
            "candidate_fingerprint": self.candidate.fingerprint,
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
        extra_body = self._merge_extra_body(kwargs.pop("extra_body", None))
        request: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "extra_body": extra_body,
            **kwargs,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        response = await self.client.chat.completions.create(**request)
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
        extra_body = self._merge_extra_body(kwargs.pop("extra_body", None))
        stream = await self.client.chat.completions.create(
            model=model or self.default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            stream=True,
            extra_body=extra_body,
            **kwargs,
        )
        actual_model: str | None = None
        upstream_provider: object = None
        async for chunk in stream:
            extra = _model_extra(chunk)
            error = getattr(chunk, "error", None) or extra.get("error")
            if error:
                raise OpenRouterStreamError(_error_type(error))
            actual_model = getattr(chunk, "model", None) or actual_model
            upstream_provider = (
                getattr(chunk, "provider", None) or extra.get("provider") or upstream_provider
            )
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        self.last_response_metadata = {
            "requested_model": self.candidate.model,
            "actual_model": actual_model,
            "upstream_provider": upstream_provider,
            "candidate_fingerprint": self.candidate.fingerprint,
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
