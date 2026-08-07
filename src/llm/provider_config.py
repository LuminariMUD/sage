"""Validated provider-neutral configuration contracts.

This module is the single environment parsing boundary for text generation,
embeddings, and Graphiti provider selection.  Fingerprints intentionally omit
credentials while factory cache identities include a one-way credential digest
so an in-process credential rotation cannot reuse a stale client.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Literal, TypeAlias, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr

logger = logging.getLogger(__name__)

ProviderName: TypeAlias = Literal["ollama", "openrouter", "openai"]
EmbeddingProviderName: TypeAlias = Literal[
    "ollama", "openrouter", "openai", "sentence-transformers"
]
TextTask: TypeAlias = Literal["chat", "creative", "reasoning", "extraction", "tools"]
FailureClassName: TypeAlias = Literal[
    "transport",
    "authentication",
    "authorization",
    "configuration",
    "profile_mismatch",
    "rate_limit",
    "resource_exhaustion",
    "output_limit",
    "malformed_json",
    "schema_validation",
    "graph_validation",
    "persistence",
    "verification",
    "cancellation",
    "shutdown",
    "internal",
]

TEXT_TASKS: tuple[TextTask, ...] = (
    "chat",
    "creative",
    "reasoning",
    "extraction",
    "tools",
)
TARGET_PROVIDERS = frozenset({"ollama", "openrouter"})
SUPPORTED_TEXT_PROVIDERS = frozenset({*TARGET_PROVIDERS, "openai"})
SUPPORTED_EMBEDDING_PROVIDERS = frozenset({*SUPPORTED_TEXT_PROVIDERS, "sentence-transformers"})
FAILURE_CLASSES = frozenset(
    {
        "transport",
        "authentication",
        "authorization",
        "configuration",
        "profile_mismatch",
        "rate_limit",
        "resource_exhaustion",
        "output_limit",
        "malformed_json",
        "schema_validation",
        "graph_validation",
        "persistence",
        "verification",
        "cancellation",
        "shutdown",
        "internal",
    }
)
_TASK_CAPABILITIES: dict[TextTask, frozenset[str]] = {
    "chat": frozenset({"chat", "streaming"}),
    "creative": frozenset({"chat", "streaming"}),
    "reasoning": frozenset({"chat"}),
    "extraction": frozenset({"chat", "structured_output"}),
    "tools": frozenset({"chat", "streaming", "tools"}),
}
_TASK_TEMPERATURES: dict[TextTask, float] = {
    "chat": 0.7,
    "creative": 0.9,
    "reasoning": 0.5,
    "extraction": 0.3,
    "tools": 0.5,
}
_GRAPH_FALLBACK_FAILURES = frozenset({"malformed_json", "schema_validation", "output_limit"})
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,254}$")
_ROUTING_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _canonical_fingerprint(namespace: str, payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("ascii")).hexdigest()
    return f"{namespace}:sha256:{digest}"


def _validate_label(value: str, label: str) -> str:
    if not isinstance(value, str) or not _LABEL.fullmatch(value):
        raise ValueError(f"{label} is missing or invalid")
    return value


def _validate_header_value(value: str, label: str) -> str:
    if not value or len(value) > 1024 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{label} is missing or invalid")
    return value


def _normalized_url(value: str, label: str, *, require_https: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} must be an absolute HTTP URL")
    if require_https and parsed.scheme != "https":
        raise ValueError(f"{label} must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{label} cannot contain credentials, a query, or a fragment")
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _immutable_mapping(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(sorted(values.items())))


@dataclass(frozen=True)
class TransportRetryPolicy:
    """Retry policy for one provider transport and one logical candidate call."""

    maximum_attempts: int = 1
    retry_on: frozenset[FailureClassName] = frozenset({"transport", "rate_limit"})
    base_delay_seconds: float = 0.5
    maximum_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_attempts <= 10:
            raise ValueError("Transport maximum attempts must be between 1 and 10")
        if not self.retry_on.issubset(FAILURE_CLASSES):
            raise ValueError("Transport retry classes are invalid")
        if self.base_delay_seconds < 0 or self.maximum_delay_seconds < self.base_delay_seconds:
            raise ValueError("Transport retry delay bounds are invalid")
        if self.maximum_delay_seconds > 300:
            raise ValueError("Transport maximum delay cannot exceed 300 seconds")


@dataclass(frozen=True)
class ProviderConnection:
    """Validated provider transport details."""

    provider: EmbeddingProviderName
    base_url: str
    api_key: SecretStr | None
    timeout_seconds: float
    transport_retry: TransportRetryPolicy
    default_headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            raise ValueError("Provider connection type is unsupported")
        if self.provider == "sentence-transformers":
            if self.base_url != "local://sentence-transformers":
                raise ValueError("Sentence Transformers must use its local connection")
        else:
            normalized = _normalized_url(
                self.base_url,
                "Provider base URL",
                require_https=self.provider in {"openrouter", "openai"},
            )
            object.__setattr__(self, "base_url", normalized)
        if not 0 < self.timeout_seconds <= 3600:
            raise ValueError("Provider timeout must be between 0 and 3600 seconds")
        if self.provider in {"openrouter", "openai"}:
            if self.api_key is None or not self.api_key.get_secret_value():
                raise ValueError(f"{self.provider.title()} API credentials are required")
        elif self.api_key is not None:
            raise ValueError("Local providers cannot be configured with an API credential")
        headers = {
            str(name): _validate_header_value(str(value), "Provider header value")
            for name, value in self.default_headers.items()
        }
        object.__setattr__(self, "default_headers", _immutable_mapping(headers))

    def cache_identity(self) -> str:
        """Return a non-reversible cache key that detects credential rotation."""
        secret = self.api_key.get_secret_value() if self.api_key else ""
        material = {
            "provider": self.provider,
            "base_url": self.base_url,
            "headers": dict(self.default_headers),
            "timeout": self.timeout_seconds,
            "maximum_attempts": self.transport_retry.maximum_attempts,
            "credential_digest": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
        }
        return _canonical_fingerprint("connection-cache", material)

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "transport_maximum_attempts": self.transport_retry.maximum_attempts,
            "default_header_names": sorted(self.default_headers),
            "credential_configured": self.api_key is not None,
        }


@dataclass(frozen=True)
class OpenRouterRoutingPolicy:
    """Explicit OpenRouter endpoint, capability, and privacy routing policy."""

    allow_fallbacks: bool = False
    require_parameters: bool = True
    data_collection: Literal["allow", "deny"] = "deny"
    zdr: bool = False
    order: tuple[str, ...] = ()
    only: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.data_collection not in {"allow", "deny"}:
            raise ValueError("OpenRouter data collection policy must be allow or deny")
        for values in (self.order, self.only, self.ignore):
            if len(values) != len(set(values)):
                raise ValueError("OpenRouter routing lists cannot contain duplicates")
            if any(not _ROUTING_SLUG.fullmatch(value) for value in values):
                raise ValueError("OpenRouter routing contains an invalid provider slug")
        if set(self.only).intersection(self.ignore):
            raise ValueError("OpenRouter routing cannot both allow and ignore a provider")

    def as_request_body(self) -> dict[str, object]:
        result: dict[str, object] = {
            "allow_fallbacks": self.allow_fallbacks,
            "require_parameters": self.require_parameters,
            "data_collection": self.data_collection,
        }
        if self.zdr:
            result["zdr"] = True
        if self.order:
            result["order"] = list(self.order)
        if self.only:
            result["only"] = list(self.only)
        if self.ignore:
            result["ignore"] = list(self.ignore)
        return result


@dataclass(frozen=True)
class TextModelCandidate:
    """One provider/model call candidate; fallback is owned by a route."""

    name: str
    connection: ProviderConnection
    model: str
    prompt_profile: str
    context_limit: int
    temperature: float
    capabilities: frozenset[str]
    maximum_model_attempts: int
    retry_on: frozenset[FailureClassName]
    fingerprint: str
    routing: OpenRouterRoutingPolicy | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        _validate_label(self.name, "Text candidate name")
        _validate_label(self.model, "Text candidate model")
        _validate_label(self.prompt_profile, "Prompt profile")
        _validate_label(self.fingerprint, "Text candidate fingerprint")
        if self.revision is not None:
            _validate_label(self.revision, "Text model revision")
        if not 1 <= self.context_limit <= 10_000_000:
            raise ValueError("Text context limit is invalid")
        if not 0 <= self.temperature <= 2:
            raise ValueError("Text temperature must be between 0 and 2")
        if not 1 <= self.maximum_model_attempts <= 100:
            raise ValueError("Text model attempts must be between 1 and 100")
        if not self.capabilities or any(not _LABEL.fullmatch(item) for item in self.capabilities):
            raise ValueError("Text candidate capabilities are invalid")
        if not self.retry_on.issubset(FAILURE_CLASSES):
            raise ValueError("Text candidate retry classes are invalid")
        if self.connection.provider == "openrouter" and self.routing is None:
            raise ValueError("OpenRouter text candidates require explicit routing policy")
        if self.connection.provider != "openrouter" and self.routing is not None:
            raise ValueError("OpenRouter routing can only be used with OpenRouter")

    def provider_request_body(self) -> dict[str, object]:
        return {"provider": self.routing.as_request_body()} if self.routing else {}

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provider": self.connection.provider,
            "model": self.model,
            "revision": self.revision,
            "prompt_profile": self.prompt_profile,
            "context_limit": self.context_limit,
            "temperature": self.temperature,
            "capabilities": sorted(self.capabilities),
            "maximum_model_attempts": self.maximum_model_attempts,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class TextRouteProfile:
    """Ordered text candidates plus the only classes allowed to fall back."""

    task: TextTask
    candidates: tuple[TextModelCandidate, ...]
    fallback_on: frozenset[FailureClassName]
    maximum_provider_calls: int
    fingerprint: str

    def __post_init__(self) -> None:
        if self.task not in TEXT_TASKS:
            raise ValueError("Text route task is invalid")
        if not self.candidates:
            raise ValueError("Text route requires at least one candidate")
        if len({candidate.fingerprint for candidate in self.candidates}) != len(self.candidates):
            raise ValueError("Text route candidates must be unique")
        if not self.fallback_on.issubset(FAILURE_CLASSES):
            raise ValueError("Text route fallback classes are invalid")
        if len(self.candidates) == 1 and self.fallback_on:
            raise ValueError("A single-candidate route cannot declare model fallback")
        if not 1 <= self.maximum_provider_calls <= 100:
            raise ValueError("Text route provider-call limit must be between 1 and 100")
        if self.maximum_provider_calls < self.candidates[0].maximum_model_attempts:
            raise ValueError("Text route call limit cannot undercut its primary candidate")
        _validate_label(self.fingerprint, "Text route fingerprint")

    @property
    def primary(self) -> TextModelCandidate:
        return self.candidates[0]

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "task": self.task,
            "candidates": [candidate.sanitized_summary() for candidate in self.candidates],
            "fallback_on": sorted(self.fallback_on),
            "maximum_provider_calls": self.maximum_provider_calls,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class EmbeddingProfile:
    """Immutable identity and request contract for one vector space."""

    connection: ProviderConnection
    model: str
    dimensions: int
    encoding_format: Literal["float", "base64"]
    distance_metric: Literal["cosine"]
    normalize: bool
    revision: str | None
    fingerprint: str
    batch_size: int = 32
    routing: OpenRouterRoutingPolicy | None = None
    input_type: str | None = None

    def __post_init__(self) -> None:
        _validate_label(self.model, "Embedding model")
        _validate_label(self.fingerprint, "Embedding fingerprint")
        if self.revision is not None:
            _validate_label(self.revision, "Embedding revision")
        if self.input_type is not None:
            _validate_label(self.input_type, "Embedding input type")
        if not 1 <= self.dimensions <= 65_536:
            raise ValueError("Embedding dimensions must be between 1 and 65536")
        if self.encoding_format not in {"float", "base64"}:
            raise ValueError("Embedding encoding format is unsupported")
        if self.distance_metric != "cosine":
            raise ValueError("Only cosine distance is supported")
        if not 1 <= self.batch_size <= 2048:
            raise ValueError("Embedding batch size must be between 1 and 2048")
        if self.connection.provider == "openrouter" and self.routing is None:
            raise ValueError("OpenRouter embeddings require explicit routing policy")
        if self.connection.provider != "openrouter" and self.routing is not None:
            raise ValueError("OpenRouter routing can only be used with OpenRouter")

    def provider_request_body(self) -> dict[str, object]:
        return {"provider": self.routing.as_request_body()} if self.routing else {}

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "provider": self.connection.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "encoding_format": self.encoding_format,
            "distance_metric": self.distance_metric,
            "normalize": self.normalize,
            "revision": self.revision,
            "batch_size": self.batch_size,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class GraphSyncPolicySettings:
    """Environment-level graph policy resolved beside its provider route."""

    lease_seconds: int
    max_job_attempts: int
    retry_base_seconds: int
    retry_max_seconds: int
    max_provider_calls: int

    def __post_init__(self) -> None:
        if not 30 <= self.lease_seconds <= 86_400:
            raise ValueError("Graph lease seconds must be between 30 and 86400")
        if not 1 <= self.max_job_attempts <= 100:
            raise ValueError("Graph job attempts must be between 1 and 100")
        if not 1 <= self.retry_base_seconds <= self.retry_max_seconds <= 604_800:
            raise ValueError("Graph retry delay bounds are invalid")
        if not 1 <= self.max_provider_calls <= 100:
            raise ValueError("Graph provider-call limit must be between 1 and 100")

    def as_kwargs(self) -> dict[str, int]:
        return {
            "lease_seconds": self.lease_seconds,
            "max_job_attempts": self.max_job_attempts,
            "retry_base_seconds": self.retry_base_seconds,
            "retry_max_seconds": self.retry_max_seconds,
            "max_provider_calls": self.max_provider_calls,
        }


@dataclass(frozen=True)
class ProviderSettings:
    """Complete resolved application and Graphiti capability configuration."""

    text_provider: ProviderName
    embedding_provider: EmbeddingProviderName
    graphiti_text_provider: ProviderName
    graphiti_embedding_provider: EmbeddingProviderName
    text_routes: Mapping[TextTask, TextRouteProfile]
    embedding_profile: EmbeddingProfile
    graphiti_text_route: TextRouteProfile
    graphiti_embedding_profile: EmbeddingProfile
    graph_sync_policy: GraphSyncPolicySettings

    def __post_init__(self) -> None:
        if set(self.text_routes) != set(TEXT_TASKS):
            raise ValueError("A text route is required for every supported task")
        object.__setattr__(self, "text_routes", MappingProxyType(dict(self.text_routes)))

    def text_route(self, task: TextTask = "chat") -> TextRouteProfile:
        return self.text_routes[task]

    def sanitized_summary(self) -> dict[str, object]:
        return {
            "text_provider": self.text_provider,
            "embedding_provider": self.embedding_provider,
            "graphiti_text_provider": self.graphiti_text_provider,
            "graphiti_embedding_provider": self.graphiti_embedding_provider,
            "text_routes": {
                task: route.sanitized_summary() for task, route in self.text_routes.items()
            },
            "embedding_profile": self.embedding_profile.sanitized_summary(),
            "graphiti_text_route": self.graphiti_text_route.sanitized_summary(),
            "graphiti_embedding_profile": self.graphiti_embedding_profile.sanitized_summary(),
            "graph_sync_policy": self.graph_sync_policy.as_kwargs(),
        }


class ProviderSettingsResolver:
    """Resolve the complete provider contract from one immutable environment view."""

    def __init__(self, environment: Mapping[str, str] | None = None):
        self.environment = dict(os.environ if environment is None else environment)
        self._connections: dict[str, ProviderConnection] = {}
        self._warned_legacy: set[str] = set()

    def _value(self, name: str, default: str = "") -> str:
        value = self.environment.get(name)
        return value.strip() if value is not None and value.strip() else default

    def _warn_legacy(self, legacy: str, replacement: str) -> None:
        if legacy not in self._warned_legacy:
            logger.warning("%s is deprecated; configure %s instead", legacy, replacement)
            self._warned_legacy.add(legacy)

    def _bool(self, name: str, default: bool) -> bool:
        raw = self._value(name)
        if not raw:
            return default
        normalized = raw.lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
        raise ValueError(f"{name} must be a boolean")

    def _int(self, name: str, default: int, minimum: int, maximum: int) -> int:
        raw = self._value(name, str(default))
        try:
            value = int(raw)
        except ValueError as error:
            raise ValueError(f"{name} must be an integer") from error
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    def _float(self, name: str, default: float, minimum: float, maximum: float) -> float:
        raw = self._value(name, str(default))
        try:
            value = float(raw)
        except ValueError as error:
            raise ValueError(f"{name} must be numeric") from error
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    def _csv(self, name: str) -> tuple[str, ...]:
        raw = self._value(name)
        if not raw:
            return ()
        values = tuple(part.strip() for part in raw.split(",") if part.strip())
        if len(values) != len({*values}):
            raise ValueError(f"{name} cannot contain duplicates")
        return values

    def _secret(self, value_name: str, file_name: str, label: str) -> SecretStr:
        direct = self._value(value_name)
        path_value = self._value(file_name)
        if direct and path_value:
            raise ValueError(f"Configure only one of {value_name} or {file_name}")
        if direct:
            return SecretStr(direct)
        if not path_value:
            raise ValueError(f"{label} credentials are required")
        path = Path(path_value)
        try:
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16_384:
                raise ValueError(f"{label} credential file is invalid")
            secret = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ValueError(f"{label} credential file is unreadable") from error
        if not secret:
            raise ValueError(f"{label} credential file is empty")
        return SecretStr(secret)

    def _openrouter_secret(self) -> SecretStr:
        """Resolve the documented key names with one legacy alias window."""
        legacy = self._value("OPENROUTER_KEY")
        current = self._value("OPENROUTER_API_KEY")
        file_value = self._value("OPENROUTER_API_KEY_FILE")
        if legacy and (current or file_value):
            raise ValueError(
                "Configure OPENROUTER_KEY only when OPENROUTER_API_KEY and "
                "OPENROUTER_API_KEY_FILE are unset"
            )
        if legacy:
            self._warn_legacy("OPENROUTER_KEY", "OPENROUTER_API_KEY")
            return SecretStr(legacy)
        return self._secret("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_FILE", "OpenRouter")

    def _text_provider(self) -> ProviderName:
        selected = self._value("TEXT_PROVIDER")
        if not selected:
            selected = self._value("LLM_PROVIDER")
            if selected:
                self._warn_legacy("LLM_PROVIDER", "TEXT_PROVIDER")
        selected = (selected or "ollama").lower()
        if selected not in SUPPORTED_TEXT_PROVIDERS:
            if not self._value("TEXT_PROVIDER") and self._value("LLM_PROVIDER"):
                raise ValueError("Unknown LLM provider; configure TEXT_PROVIDER")
            raise ValueError("TEXT_PROVIDER must be ollama, openrouter, or openai")
        return cast(ProviderName, selected)

    def _embedding_provider(self) -> EmbeddingProviderName:
        selected = self._value("EMBEDDING_PROVIDER")
        if selected:
            selected = selected.lower()
            if selected not in SUPPORTED_TEXT_PROVIDERS:
                raise ValueError("EMBEDDING_PROVIDER must be ollama, openrouter, or openai")
            return cast(EmbeddingProviderName, selected)

        legacy_llm = self._value("LLM_PROVIDER").lower()
        legacy_local_raw = self._value("USE_LOCAL_EMBEDDINGS")
        if legacy_llm or legacy_local_raw:
            self._warn_legacy(
                "USE_LOCAL_EMBEDDINGS/LLM_PROVIDER",
                "EMBEDDING_PROVIDER",
            )
            use_local = self._bool("USE_LOCAL_EMBEDDINGS", False)
            if not use_local:
                return "openai"
            return "ollama" if legacy_llm in {"", "ollama"} else "sentence-transformers"
        return "ollama"

    def _graphiti_provider(
        self,
        selector: str,
        inherited: str,
        *,
        embedding: bool,
    ) -> str:
        selected = self._value(selector)
        if selected:
            selected = selected.lower()
        else:
            selected = self._value("GRAPHITI_PROVIDER").lower()
            if selected:
                self._warn_legacy("GRAPHITI_PROVIDER", selector)
            else:
                selected = inherited
        supported = SUPPORTED_EMBEDDING_PROVIDERS if embedding else SUPPORTED_TEXT_PROVIDERS
        if selected not in supported:
            raise ValueError(f"{selector} is unsupported")
        if selector == "GRAPHITI_TEXT_PROVIDER" and selected == "sentence-transformers":
            raise ValueError("Sentence Transformers cannot provide Graphiti text generation")
        return selected

    def _retry_policy(self, provider: str) -> TransportRetryPolicy:
        prefix = provider.upper().replace("-", "_")
        attempts = self._int(f"{prefix}_TRANSPORT_MAX_ATTEMPTS", 1, 1, 10)
        retry_on = frozenset(
            cast(
                set[FailureClassName],
                set(self._csv(f"{prefix}_TRANSPORT_RETRY_ON") or ("transport", "rate_limit")),
            )
        )
        return TransportRetryPolicy(
            maximum_attempts=attempts,
            retry_on=retry_on,
            base_delay_seconds=self._float(f"{prefix}_RETRY_BASE_SECONDS", 0.5, 0.0, 300.0),
            maximum_delay_seconds=self._float(f"{prefix}_RETRY_MAX_SECONDS", 8.0, 0.0, 300.0),
        )

    def _connection(self, provider: EmbeddingProviderName) -> ProviderConnection:
        if provider in self._connections:
            return self._connections[provider]
        if provider == "ollama":
            connection = ProviderConnection(
                provider=provider,
                base_url=self._value("OLLAMA_BASE_URL", "http://ollama:11434"),
                api_key=None,
                timeout_seconds=self._float("OLLAMA_REQUEST_TIMEOUT", 120.0, 0.001, 3600.0),
                transport_retry=self._retry_policy(provider),
            )
        elif provider == "openrouter":
            headers: dict[str, str] = {}
            site_url = self._value("OPENROUTER_SITE_URL")
            app_name = self._value("OPENROUTER_APP_NAME")
            if site_url:
                headers["HTTP-Referer"] = _normalized_url(
                    site_url, "OPENROUTER_SITE_URL", require_https=True
                )
            if app_name:
                headers["X-OpenRouter-Title"] = _validate_header_value(
                    app_name, "OPENROUTER_APP_NAME"
                )
            connection = ProviderConnection(
                provider=provider,
                base_url=self._value("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                api_key=self._openrouter_secret(),
                timeout_seconds=self._float("OPENROUTER_REQUEST_TIMEOUT", 120.0, 0.001, 3600.0),
                transport_retry=self._retry_policy(provider),
                default_headers=headers,
            )
        elif provider == "openai":
            connection = ProviderConnection(
                provider=provider,
                base_url=self._value("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                api_key=self._secret("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "OpenAI"),
                timeout_seconds=self._float("OPENAI_REQUEST_TIMEOUT", 120.0, 0.001, 3600.0),
                transport_retry=self._retry_policy(provider),
            )
        else:
            connection = ProviderConnection(
                provider="sentence-transformers",
                base_url="local://sentence-transformers",
                api_key=None,
                timeout_seconds=self._float("SENTENCE_TRANSFORMERS_TIMEOUT", 120.0, 0.001, 3600.0),
                transport_retry=TransportRetryPolicy(maximum_attempts=1, retry_on=frozenset()),
            )
        self._connections[provider] = connection
        return connection

    def _routing(self, capability: Literal["TEXT", "EMBEDDING"]) -> OpenRouterRoutingPolicy:
        prefix = f"OPENROUTER_{capability}"
        data_collection = self._value(f"{prefix}_DATA_COLLECTION", "deny").lower()
        if data_collection not in {"allow", "deny"}:
            raise ValueError(f"{prefix}_DATA_COLLECTION must be allow or deny")
        return OpenRouterRoutingPolicy(
            allow_fallbacks=self._bool(f"{prefix}_ALLOW_FALLBACKS", False),
            require_parameters=self._bool(f"{prefix}_REQUIRE_PARAMETERS", True),
            data_collection=cast(Literal["allow", "deny"], data_collection),
            zdr=self._bool(f"{prefix}_ZDR", False),
            order=self._csv(f"{prefix}_PROVIDER_ORDER"),
            only=self._csv(f"{prefix}_PROVIDER_ONLY"),
            ignore=self._csv(f"{prefix}_PROVIDER_IGNORE"),
        )

    def _task_model(self, provider: ProviderName, task: TextTask, *, graphiti: bool) -> str:
        if graphiti:
            explicit = self._value("GRAPHITI_TEXT_MODEL")
            if explicit:
                return explicit
            if provider == "openrouter":
                model = self._value("OPENROUTER_GRAPHITI_MODEL")
                if model:
                    return model
            elif provider == "openai":
                model = self._value("GRAPHITI_LLM_MODEL")
                if model:
                    return model

        if provider == "ollama":
            defaults = {
                "chat": "qwen2.5:7b",
                "creative": self._value("OLLAMA_CHAT_MODEL", "qwen2.5:7b"),
                "reasoning": "qwen2.5:3b",
                "extraction": self._value("OLLAMA_REASONING_MODEL", "qwen2.5:3b"),
                "tools": self._value("OLLAMA_CHAT_MODEL", "qwen2.5:7b"),
            }
            return self._value(f"OLLAMA_{task.upper()}_MODEL", defaults[task])
        if provider == "openrouter":
            chat = self._value("OPENROUTER_CHAT_MODEL")
            defaults = {
                "chat": "",
                "creative": chat,
                "reasoning": chat,
                "extraction": self._value("OPENROUTER_REASONING_MODEL", chat),
                "tools": chat,
            }
            model = self._value(f"OPENROUTER_{task.upper()}_MODEL", defaults[task])
            if not model:
                raise ValueError(
                    f"OPENROUTER_{task.upper()}_MODEL or OPENROUTER_CHAT_MODEL is required"
                )
            return model
        defaults = {
            "chat": self._value("LLM_MODEL", "gpt-4o-mini"),
            "creative": self._value("LLM_MODEL", "gpt-4o-mini"),
            "reasoning": self._value("LLM_MODEL", "gpt-4o-mini"),
            "extraction": self._value("LLM_MODEL", "gpt-4o-mini"),
            "tools": self._value("LLM_MODEL", "gpt-4o-mini"),
        }
        return self._value(f"OPENAI_{task.upper()}_MODEL", defaults[task])

    @staticmethod
    def infer_prompt_profile(model: str) -> str:
        normalized = model.lower()
        if "qwen" in normalized:
            return "qwen"
        if "deepseek" in normalized:
            return "deepseek"
        if "llama" in normalized:
            return "llama"
        if "claude" in normalized:
            return "claude"
        if any(marker in normalized for marker in ("gpt-", "openai/", " o1", " o3", " o4")):
            return "openai"
        return "generic"

    def _candidate(
        self,
        provider: ProviderName,
        task: TextTask,
        *,
        graphiti: bool,
        name: str,
        maximum_model_attempts: int,
        model_override: str = "",
    ) -> TextModelCandidate:
        model = model_override or self._task_model(provider, task, graphiti=graphiti)
        _validate_label(model, "Text model")
        prefix = provider.upper()
        prompt_profile = self._value(
            f"{prefix}_{task.upper()}_PROMPT_PROFILE",
            self.infer_prompt_profile(model),
        )
        capability_values = self._csv(f"{prefix}_{task.upper()}_CAPABILITIES")
        capabilities = frozenset(capability_values or _TASK_CAPABILITIES[task])
        missing = _TASK_CAPABILITIES[task].difference(capabilities)
        if missing:
            raise ValueError(
                f"{prefix}_{task.upper()}_CAPABILITIES is missing required task capabilities"
            )
        context_limit = self._int(
            f"{prefix}_{task.upper()}_CONTEXT_TOKENS",
            self._int(f"{prefix}_MAX_CONTEXT_TOKENS", 8192, 1, 10_000_000),
            1,
            10_000_000,
        )
        temperature = self._float(
            f"{prefix}_{task.upper()}_TEMPERATURE",
            _TASK_TEMPERATURES[task],
            0,
            2,
        )
        revision = (
            self._value(
                "GRAPHITI_TEXT_MODEL_REVISION" if graphiti else f"{prefix}_{task.upper()}_REVISION"
            )
            or None
        )
        routing = self._routing("TEXT") if provider == "openrouter" else None
        connection = self._connection(provider)
        if graphiti:
            connection = replace(
                connection,
                timeout_seconds=self._float("GRAPHITI_REQUEST_TIMEOUT", 600.0, 0.001, 3600.0),
                transport_retry=TransportRetryPolicy(
                    maximum_attempts=1,
                    retry_on=frozenset(),
                    base_delay_seconds=0,
                    maximum_delay_seconds=0,
                ),
            )
            temperature = self._float("GRAPHITI_EXTRACTION_TEMPERATURE", temperature, 0, 2)
        payload: dict[str, object] = {
            "provider": provider,
            "base_url": connection.base_url,
            "model": model,
            "revision": revision,
            "prompt_profile": prompt_profile,
            "context_limit": context_limit,
            "temperature": temperature,
            "capabilities": sorted(capabilities),
            "maximum_model_attempts": maximum_model_attempts,
            "protocol": "openai-chat-completions" if provider != "ollama" else "ollama-chat",
            "routing": routing.as_request_body() if routing else None,
        }
        return TextModelCandidate(
            name=name,
            connection=connection,
            model=model,
            prompt_profile=prompt_profile,
            context_limit=context_limit,
            temperature=temperature,
            capabilities=capabilities,
            maximum_model_attempts=maximum_model_attempts,
            retry_on=frozenset({"transport", "rate_limit", "resource_exhaustion"}),
            fingerprint=_canonical_fingerprint("candidate", payload),
            routing=routing,
            revision=revision,
        )

    @staticmethod
    def _route(
        task: TextTask,
        candidates: tuple[TextModelCandidate, ...],
        fallback_on: frozenset[FailureClassName],
        maximum_provider_calls: int,
    ) -> TextRouteProfile:
        payload: dict[str, object] = {
            "task": task,
            "candidates": [candidate.fingerprint for candidate in candidates],
            "fallback_on": sorted(fallback_on),
            "maximum_provider_calls": maximum_provider_calls,
        }
        return TextRouteProfile(
            task=task,
            candidates=candidates,
            fallback_on=fallback_on,
            maximum_provider_calls=maximum_provider_calls,
            fingerprint=_canonical_fingerprint("route", payload),
        )

    def _application_routes(self, provider: ProviderName) -> Mapping[TextTask, TextRouteProfile]:
        routes: dict[TextTask, TextRouteProfile] = {}
        for task in TEXT_TASKS:
            candidate = self._candidate(
                provider,
                task,
                graphiti=False,
                name=f"application:{task}:primary",
                maximum_model_attempts=1,
            )
            routes[task] = self._route(task, (candidate,), frozenset(), 1)
        return MappingProxyType(routes)

    def _graphiti_route(self, provider: ProviderName) -> TextRouteProfile:
        primary_attempts = self._int("GRAPHITI_EXTRACTION_PRIMARY_ATTEMPTS", 2, 1, 100)
        primary = self._candidate(
            provider,
            "extraction",
            graphiti=True,
            name="graphiti:extraction:primary",
            maximum_model_attempts=primary_attempts,
        )
        candidates = [primary]
        fallback_provider_raw = self._value("GRAPHITI_EXTRACTION_FALLBACK_PROVIDER").lower()
        if fallback_provider_raw:
            if fallback_provider_raw not in SUPPORTED_TEXT_PROVIDERS:
                raise ValueError("GRAPHITI_EXTRACTION_FALLBACK_PROVIDER is unsupported")
            fallback_model = self._value("GRAPHITI_EXTRACTION_FALLBACK_MODEL")
            if not fallback_model:
                raise ValueError("GRAPHITI_EXTRACTION_FALLBACK_MODEL is required")
            fallback = self._candidate(
                cast(ProviderName, fallback_provider_raw),
                "extraction",
                graphiti=True,
                name="graphiti:extraction:fallback",
                maximum_model_attempts=self._int(
                    "GRAPHITI_EXTRACTION_FALLBACK_ATTEMPTS", 1, 1, 100
                ),
                model_override=fallback_model,
            )
            if fallback.fingerprint == primary.fingerprint:
                raise ValueError("Graphiti extraction fallback must differ from the primary")
            candidates.append(fallback)
        route_limit = self._int(
            "GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS",
            self._int("GRAPH_SYNC_MAX_PROVIDER_CALLS", 3, 1, 100),
            1,
            100,
        )
        configured_durable_limit = self._value("GRAPH_SYNC_MAX_PROVIDER_CALLS")
        configured_route_limit = self._value("GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS")
        if (
            configured_durable_limit
            and configured_route_limit
            and int(configured_durable_limit) != int(configured_route_limit)
        ):
            raise ValueError(
                "GRAPHITI_EXTRACTION_MAX_PROVIDER_CALLS and GRAPH_SYNC_MAX_PROVIDER_CALLS must match"
            )
        if route_limit < primary_attempts:
            raise ValueError("Graphiti provider-call limit cannot undercut primary attempts")
        fallback_on = cast(
            frozenset[FailureClassName],
            _GRAPH_FALLBACK_FAILURES if len(candidates) > 1 else frozenset(),
        )
        return self._route("extraction", tuple(candidates), fallback_on, route_limit)

    def _embedding_profile(
        self,
        provider: EmbeddingProviderName,
        *,
        graphiti: bool,
    ) -> EmbeddingProfile:
        if provider == "ollama":
            model = self._value("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
            dimensions = self._int("OLLAMA_EMBEDDING_DIMENSIONS", 768, 1, 65_536)
            batch_size = self._int("OLLAMA_EMBEDDING_BATCH_SIZE", 32, 1, 2048)
            encoding = "float"
            revision = self._value("OLLAMA_EMBEDDING_REVISION") or None
            input_type = self._value("OLLAMA_EMBEDDING_INPUT_TYPE") or None
            routing = None
        elif provider == "openrouter":
            model = self._value("OPENROUTER_EMBEDDING_MODEL")
            if not model:
                raise ValueError("OPENROUTER_EMBEDDING_MODEL is required")
            dimensions = self._int("OPENROUTER_EMBEDDING_DIMENSIONS", 1024, 1, 65_536)
            batch_size = self._int("OPENROUTER_EMBEDDING_BATCH_SIZE", 32, 1, 2048)
            encoding = self._value("OPENROUTER_EMBEDDING_ENCODING_FORMAT", "float").lower()
            if encoding != "float":
                raise ValueError("OpenRouter embeddings must use float encoding")
            revision = self._value("OPENROUTER_EMBEDDING_REVISION") or None
            input_type = self._value("OPENROUTER_EMBEDDING_INPUT_TYPE") or None
            routing = self._routing("EMBEDDING")
        elif provider == "openai":
            model = self._value("EMBEDDING_MODEL", "text-embedding-3-small")
            dimensions = self._int("OPENAI_EMBEDDING_DIMENSIONS", 1536, 1, 65_536)
            batch_size = self._int("OPENAI_EMBEDDING_BATCH_SIZE", 100, 1, 2048)
            encoding = "float"
            revision = self._value("OPENAI_EMBEDDING_REVISION") or None
            input_type = None
            routing = None
        else:
            model = self._value(
                "SENTENCE_TRANSFORMERS_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            )
            dimensions = self._int("SENTENCE_TRANSFORMERS_DIMENSIONS", 384, 1, 65_536)
            batch_size = self._int("SENTENCE_TRANSFORMERS_BATCH_SIZE", 32, 1, 2048)
            encoding = "float"
            revision = self._value("SAGE_SENTENCE_TRANSFORMERS_REVISION") or None
            input_type = None
            routing = None

        if graphiti:
            model = self._value("GRAPHITI_EMBEDDING_MODEL", model)
            dimensions = self._int("GRAPHITI_EMBEDDING_DIMENSIONS", dimensions, 1, 65_536)
            revision = self._value("GRAPHITI_EMBEDDING_MODEL_REVISION", revision or "") or None
        _validate_label(model, "Embedding model")
        connection = self._connection(provider)
        if graphiti:
            connection = replace(
                connection,
                timeout_seconds=self._float("GRAPHITI_REQUEST_TIMEOUT", 600.0, 0.001, 3600.0),
                transport_retry=TransportRetryPolicy(
                    maximum_attempts=1,
                    retry_on=frozenset(),
                    base_delay_seconds=0,
                    maximum_delay_seconds=0,
                ),
            )
        payload: dict[str, object] = {
            "provider": provider,
            "base_url": connection.base_url,
            "model": model,
            "dimensions": dimensions,
            "encoding_format": encoding,
            "distance_metric": "cosine",
            "normalize": False,
            "revision": revision,
            "input_type": input_type,
            "implementation": "sage-provider-v1",
            "routing": routing.as_request_body() if routing else None,
        }
        return EmbeddingProfile(
            connection=connection,
            model=model,
            dimensions=dimensions,
            encoding_format=cast(Literal["float", "base64"], encoding),
            distance_metric="cosine",
            normalize=False,
            revision=revision,
            fingerprint=_canonical_fingerprint("embedding", payload),
            batch_size=batch_size,
            routing=routing,
            input_type=input_type,
        )

    def resolve(self) -> ProviderSettings:
        text_provider = self._text_provider()
        embedding_provider = self._embedding_provider()
        graphiti_text_provider = cast(
            ProviderName,
            self._graphiti_provider("GRAPHITI_TEXT_PROVIDER", text_provider, embedding=False),
        )
        graphiti_embedding_provider = cast(
            EmbeddingProviderName,
            self._graphiti_provider(
                "GRAPHITI_EMBEDDING_PROVIDER", embedding_provider, embedding=True
            ),
        )
        routes = self._application_routes(text_provider)
        graphiti_route = self._graphiti_route(graphiti_text_provider)
        embedding_profile = self._embedding_profile(embedding_provider, graphiti=False)
        graphiti_embedding_profile = self._embedding_profile(
            graphiti_embedding_provider, graphiti=True
        )
        policy = GraphSyncPolicySettings(
            lease_seconds=self._int("GRAPH_SYNC_LEASE_SECONDS", 900, 30, 86_400),
            max_job_attempts=self._int("GRAPH_SYNC_MAX_JOB_ATTEMPTS", 3, 1, 100),
            retry_base_seconds=self._int("GRAPH_SYNC_RETRY_BASE_SECONDS", 60, 1, 604_800),
            retry_max_seconds=self._int("GRAPH_SYNC_RETRY_MAX_SECONDS", 3600, 1, 604_800),
            max_provider_calls=graphiti_route.maximum_provider_calls,
        )
        return ProviderSettings(
            text_provider=text_provider,
            embedding_provider=embedding_provider,
            graphiti_text_provider=graphiti_text_provider,
            graphiti_embedding_provider=graphiti_embedding_provider,
            text_routes=routes,
            embedding_profile=embedding_profile,
            graphiti_text_route=graphiti_route,
            graphiti_embedding_profile=graphiti_embedding_profile,
            graph_sync_policy=policy,
        )


def resolve_provider_settings(
    environment: Mapping[str, str] | None = None,
) -> ProviderSettings:
    """Resolve one complete provider configuration without global caching."""
    return ProviderSettingsResolver(environment).resolve()


def is_text_profile_ready(task: TextTask = "chat") -> bool:
    """Return whether the selected text task has a valid local configuration."""
    try:
        resolve_provider_settings().text_route(task)
    except (OSError, ValueError):
        return False
    return True
